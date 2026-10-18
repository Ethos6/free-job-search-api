"""The search pipeline: understand the request, gather jobs, merge duplicates, rank."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

from . import llm, vocab
from .config import Settings
from .cv import requirements_from_cv
from .http import Http
from .indexer import Indexer
from .models import Job, Requirements, SearchResponse, SourceStatus
from .parse import parse
from .rank import rank
from .sources import ALL, BOARD_SOURCES, FEED_SOURCES, LIVE, Context
from .store import Store

SOURCE_RANK = {"greenhouse": 0, "lever": 0, "ashby": 0, "workable": 0, "recruitee": 0, "smartrecruiters": 0,
               "web": 2, "themuse": 2, "remotive": 2, "remoteok": 2, "jobicy": 2, "himalayas": 2, "arbeitnow": 2,
               "hackernews": 2, "linkedin": 3}


class JobSearch:
    def __init__(self, settings: Settings, store: Optional[Store] = None, http: Optional[Http] = None):
        self.settings = settings
        self.store = store or Store(settings.data_dir / "jobs.db")
        self.http = http or Http(settings.user_agent, allow_private=settings.allow_private_urls)
        self.ctx = Context(http=self.http, settings=settings, store=self.store)
        self.indexer = Indexer(self.ctx)

    async def start(self) -> None:
        self.indexer.start()

    async def close(self) -> None:
        await self.indexer.stop()
        await self.http.close()

    # -- understanding -----------------------------------------------------------------------------
    async def understand(self, text: str = "", cv_text: str = "", location: str = "") -> Requirements:
        """Requirements from typed text, a CV, or both. What the person typed wins over the CV."""
        typed = parse(" \n".join(x for x in (text, f"Location: {location}" if location else "") if x))
        if self.settings.llm_url and (text or cv_text):
            ai = await llm.understand(self.ctx, text=text, cv_text=cv_text, location=location,
                                      timeout=min(25.0, self.settings.timeout / 2))
            if ai is not None:
                return merge(ai, typed) if (text or location) else ai
        if cv_text:
            from_cv = requirements_from_cv(cv_text)
            return merge(from_cv, typed)
        return typed

    # -- searching ---------------------------------------------------------------------------------
    def _fts_query(self, req: Requirements) -> str:
        terms: list[str] = []
        for t in req.titles[:3]:
            terms += vocab.role_terms(t)[:8]
        if not terms:
            terms = req.skills[:5] + req.keywords[:3]
        phrases = []
        for t in terms:
            words = [w for w in re.findall(r"[A-Za-z0-9]+", t) if w]
            if words:
                phrases.append('"' + " ".join(words) + '"')
        return " OR ".join(dict.fromkeys(phrases))

    async def search(self, req: Requirements, limit: int = 25, sources: Optional[list[str]] = None) -> SearchResponse:
        started = time.monotonic()
        statuses: list[SourceStatus] = []
        jobs: list[Job] = []

        # 1. the local index (company boards and job-board feeds, refreshed in the background)
        t0 = time.monotonic()
        indexed = await asyncio.to_thread(self.store.search_jobs, self._fts_query(req))
        if sources:
            indexed = [j for j in indexed if j.source in sources]
        jobs += indexed
        statuses.append(SourceStatus(id="index", name=f"Local index ({self.store.job_count()} jobs from "
                                     f"{len(self.store.boards())} company boards and "
                                     f"{len(FEED_SOURCES)} job boards)", ok=True, jobs=len(indexed),
                                     elapsed_ms=int((time.monotonic() - t0) * 1000)))

        # 2. live sources, in parallel, within the time budget
        live = [s for sid, s in LIVE.items() if not sources or sid in sources]
        budget = max(3.0, self.settings.timeout - (time.monotonic() - started) - 1.0)

        async def run(src) -> tuple[list[Job], SourceStatus]:
            reason = src.available(self.ctx)
            if reason:
                return [], SourceStatus(id=src.id, name=src.name, ok=True, skipped=reason)
            t = time.monotonic()
            try:
                found = await asyncio.wait_for(src.search(self.ctx, req), timeout=budget)
                return found, SourceStatus(id=src.id, name=src.name, ok=True, jobs=len(found),
                                           elapsed_ms=int((time.monotonic() - t) * 1000))
            except asyncio.TimeoutError:
                return [], SourceStatus(id=src.id, name=src.name, ok=False, error="took too long",
                                        elapsed_ms=int((time.monotonic() - t) * 1000))
            except Exception as e:  # noqa: BLE001 - one source failing never fails the search
                return [], SourceStatus(id=src.id, name=src.name, ok=False, error=_short(e),
                                        elapsed_ms=int((time.monotonic() - t) * 1000))

        for found, status in await asyncio.gather(*(run(s) for s in live)):
            jobs += found
            statuses.append(status)

        # 3. merge duplicates, rank
        merged = dedupe(jobs)
        matches, total = rank(req, merged, self.settings.fx_rates, limit=max(limit, 40) if self.settings.llm_url
                              else limit)
        left = self.settings.timeout - (time.monotonic() - started)
        if self.settings.llm_url and matches and left > 4:
            matches = await llm.rerank(self.ctx, req, matches, timeout=left - 1)
        names = {s: vocab.display(s) for s in req.skills + req.nice_skills + req.keywords}
        return SearchResponse(requirements=req, results=matches[:limit], total_found=total, sources=statuses,
                              elapsed_ms=int((time.monotonic() - started) * 1000), display=names)

    def source_list(self) -> list[dict]:
        out = []
        for sid, s in ALL.items():
            reason = s.available(self.ctx)
            if sid == "web" and reason is None:
                reason = None
            out.append({"id": sid, "name": s.name, "kind": s.kind, "homepage": s.homepage, "terms": s.terms,
                        "enabled": reason is None, "note": reason,
                        "boards": len(self.store.boards(sid)) if sid in BOARD_SOURCES or sid == "smartrecruiters"
                        else None})
        return out


def merge(base: Requirements, override: Requirements) -> Requirements:
    """Combine requirements; fields the person typed (override) win, lists are joined."""
    out = base.model_copy(deep=True)
    for field in ("titles", "skills", "nice_skills", "keywords", "exclude", "employment_types", "languages"):
        typed = getattr(override, field)
        if typed:
            joined = list(dict.fromkeys(typed + [x for x in getattr(out, field) if x not in typed]))
            setattr(out, field, joined if field != "titles" else joined[:4])
    if override.places:
        out.places = override.places
    for field in ("work_modes",):
        if getattr(override, field):
            setattr(out, field, getattr(override, field))
    for field in ("seniority", "years_experience", "visa_sponsorship", "posted_within_days", "home_country"):
        v = getattr(override, field)
        if v is not None:
            setattr(out, field, v)
    if override.salary_min:
        out.salary_min, out.salary_currency, out.salary_period = (override.salary_min, override.salary_currency,
                                                                  override.salary_period)
    out.exclude = [x for x in out.exclude]
    out.titles = [t for t in out.titles if t not in out.exclude]
    out.text = "\n".join(x for x in (base.text, override.text) if x)
    return out


def dedupe(jobs: list[Job]) -> list[Job]:
    """The same job is often on several sources. Keep the best copy (the company's own board
    first) and remember where else it was seen."""
    by_key: dict[str, Job] = {}
    for j in jobs:
        k = j.key()
        cur = by_key.get(k)
        if cur is None:
            by_key[k] = j
            continue
        better, other = (j, cur) if _quality(j) > _quality(cur) else (cur, j)
        if not better.description and other.description:
            better.description = other.description
        if not better.salary and other.salary:
            better.salary = other.salary
        if not better.posted_at and other.posted_at:
            better.posted_at = other.posted_at
        seen = {a["url"] for a in better.also_on}
        if other.url != better.url and other.url not in seen:
            better.also_on.append({"source": other.source_name or other.source, "url": other.url})
        by_key[k] = better
    return list(by_key.values())


def _quality(j: Job) -> float:
    return (3 - SOURCE_RANK.get(j.source, 2)) * 10 + (5 if j.description else 0) + (3 if j.salary else 0) + \
        (2 if j.posted_at else 0) - (20 if j.from_search_snippet else 0)


def _short(e: Exception) -> str:
    msg = str(e) or type(e).__name__
    return msg[:160]
