"""Keeps the local job index fresh: downloads company boards and job-board feeds in the
background, a few at a time, so searches are instant and sources are not hit on every search."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .http import FetchError
from .seeds import SEED_BOARDS
from .sources import BOARD_SOURCES, FEED_SOURCES, Context

log = logging.getLogger("jobsearch.indexer")


def seed(ctx: Context) -> int:
    added = 0
    for ats, tokens in SEED_BOARDS.items():
        for t in tokens:
            added += ctx.store.add_board(ats, t, added_by="seed")
    for entry in ctx.settings.companies:
        ats, _, token = entry.partition(":")
        if ats in BOARD_SOURCES or ats == "smartrecruiters":
            added += ctx.store.add_board(ats, token, added_by="config")
    return added


def _pretty(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").title()


async def refresh_board(ctx: Context, ats: str, token: str, company_hint: str = "") -> int:
    src = BOARD_SOURCES.get(ats)
    if src is None or src.available(ctx):
        return 0
    try:
        company, jobs = await src.fetch_board(ctx, token)
    except Exception as e:  # noqa: BLE001 - one broken board must never stop the indexer
        log.info("board %s:%s failed: %s", ats, token, e)
        ctx.store.board_done(ats, token, ok=False)
        if isinstance(e, FetchError) and e.status == 404:  # board closed: give up on it sooner
            ctx.store.board_done(ats, token, ok=False)
        return 0
    name = company or company_hint or _pretty(token)
    for j in jobs:
        if not j.company or j.company == token:
            j.company = name
    ctx.store.board_done(ats, token, ok=True, job_count=len(jobs), company=name)
    return await asyncio.to_thread(ctx.store.replace_jobs, f"{ats}:{token}", jobs)


async def refresh_feed(ctx: Context, feed_id: str) -> int:
    src = FEED_SOURCES[feed_id]
    if src.available(ctx):
        return 0
    try:
        jobs = await src.fetch_feed(ctx)
    except Exception as e:  # noqa: BLE001 - one broken feed must never stop the indexer
        log.info("feed %s failed: %s", feed_id, e)
        # try again after a quarter of the refresh interval, not on every pass
        ctx.store.set_meta(f"feed:{feed_id}", str(time.time() - ctx.settings.refresh_hours * 2700))
        return 0
    ctx.store.set_meta(f"feed:{feed_id}", str(time.time()))
    return await asyncio.to_thread(ctx.store.replace_jobs, f"feed:{feed_id}", jobs)


async def refresh_due(ctx: Context, max_boards: int = 40, concurrency: int = 4) -> dict[str, int]:
    """One pass: refresh feeds and boards older than the refresh interval."""
    stale = time.time() - ctx.settings.refresh_hours * 3600
    stats = {"boards": 0, "feeds": 0, "jobs": 0}
    for fid in FEED_SOURCES:
        last = float(ctx.store.get_meta(f"feed:{fid}", "0") or 0)
        if last < stale:
            n = await refresh_feed(ctx, fid)
            stats["feeds"] += 1
            stats["jobs"] += n
    due = [b for b in ctx.store.due_boards(stale, limit=max_boards) if b["ats"] in BOARD_SOURCES]
    sem = asyncio.Semaphore(concurrency)

    async def one(b: dict) -> int:
        async with sem:
            return await refresh_board(ctx, b["ats"], b["token"], b.get("company") or "")

    for n in await asyncio.gather(*(one(b) for b in due)):
        stats["boards"] += 1
        stats["jobs"] += n
    return stats


class Indexer:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self._task: Optional[asyncio.Task] = None
        self.last_pass: Optional[dict] = None

    def start(self) -> None:
        seed(self.ctx)
        if self.ctx.settings.background and self._task is None:
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
        await asyncio.sleep(2)
        while True:
            try:
                self.last_pass = await refresh_due(self.ctx)
                if time.time() - float(self.ctx.store.get_meta("pruned", "0") or 0) > 86400:
                    self.ctx.store.prune_jobs()
                    self.ctx.store.set_meta("pruned", str(time.time()))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("index refresh failed")
            # quick passes while there is a backlog, then rest
            backlog = self.ctx.store.due_boards(time.time() - self.ctx.settings.refresh_hours * 3600, limit=1)
            await asyncio.sleep(20 if backlog else 300)
