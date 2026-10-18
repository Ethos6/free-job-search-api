"""Saved searches: re-run on a schedule; new matches go to a webhook and an RSS feed.

No email addresses are collected. Each alert gets a secret token; whoever has it can read
the feed or delete the alert. Only a hash of the token is stored.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from xml.sax.saxutils import escape

from .http import check_url
from .models import Requirements

if TYPE_CHECKING:
    from .service import JobSearch

log = logging.getLogger("jobsearch.alerts")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_ok(alert: dict, token: str) -> bool:
    return bool(token) and hmac.compare_digest(alert["token_hash"], hash_token(token))


async def create(js: "JobSearch", req: Requirements, every_hours: float,
                 webhook: Optional[str]) -> tuple[str, str]:
    if js.settings.max_alerts and js.store.alerts_count() >= js.settings.max_alerts:
        raise ValueError("this server has reached its limit of saved searches")
    if webhook:
        try:
            await asyncio.to_thread(check_url, webhook, js.settings.allow_private_urls)
        except Exception as e:  # noqa: BLE001 - same message whatever the reason, so nothing is revealed
            raise ValueError("the webhook must be a public https or http address") from e
    alert_id = secrets.token_hex(8)
    token = secrets.token_urlsafe(24)
    stored = req.model_copy()
    stored.text = (req.text or "")[:2000]
    js.store.add_alert(alert_id, hash_token(token), stored.model_dump_json(), every_hours, webhook)
    return alert_id, token


async def run_one(js: "JobSearch", alert: dict) -> int:
    req = Requirements.model_validate_json(alert["text"])
    res = await js.search(req, limit=30)
    pairs = [(m.job.key(), m.model_dump_json()) for m in res.results if m.score >= 45]
    fresh = js.store.new_hits(alert["id"], pairs)
    error = None
    if fresh and alert.get("webhook"):
        new = [json.loads(d) for k, d in pairs if k in fresh]
        payload = {"alert_id": alert["id"], "new_matches": new,
                   "feed": f"{js.settings.base_url}/v1/alerts/{alert['id']}/feed.xml"}
        try:
            await js.http.post_json(alert["webhook"], payload, untrusted=True)
        except Exception as e:  # noqa: BLE001
            error = f"webhook failed: {e}"[:200]
    js.store.alert_ran(alert["id"], alert["every_hours"], error)
    return len(fresh)


class AlertRunner:
    def __init__(self, js: "JobSearch"):
        self.js = js
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self.js.settings.background and self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                for alert in self.js.store.due_alerts():
                    try:
                        await run_one(self.js, alert)
                    except Exception:  # noqa: BLE001
                        log.exception("alert %s failed", alert["id"])
                        self.js.store.alert_ran(alert["id"], alert["every_hours"], "search failed")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("alert loop failed")
            await asyncio.sleep(60)


def rss(js: "JobSearch", alert: dict) -> str:
    items = []
    for h in js.store.hits(alert["id"], limit=50):
        m = h["match"]
        job = m["job"]
        when = datetime.fromtimestamp(h["seen"], tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        desc = " · ".join([f"{m['score']:.0f}/100"] + m.get("reasons", [])[:4])
        title = f"{job['title']} at {job['company']}" if job.get("company") else job["title"]
        items.append(
            f"<item><title>{escape(title)}</title><link>{escape(job['url'])}</link>"
            f"<guid isPermaLink=\"false\">{escape(h['key'])}</guid><pubDate>{when}</pubDate>"
            f"<description>{escape(desc + ' · ' + (job.get('location') or '') + ' · via ' + (job.get('source_name') or job['source']))}"
            f"</description></item>")
    req = Requirements.model_validate_json(alert["text"])
    name = ", ".join(req.titles[:2]) or ", ".join(req.skills[:3]) or "your saved search"
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\"><channel>"
            f"<title>{escape('New jobs: ' + name)}</title><link>{escape(js.settings.base_url)}</link>"
            "<description>New matches for a saved job search (Free Job Search API)</description>"
            + "".join(items) + "</channel></rss>")
