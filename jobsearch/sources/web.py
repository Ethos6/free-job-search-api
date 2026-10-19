"""Search the whole web for job postings.

1. Ask a search engine (your own FreeSearch API, or the `freesearch` library if installed)
   for postings that match the person's request.
2. Links to company careers systems (Greenhouse, Lever, Ashby, ...) are added to the
   board directory, so the company's whole board gets indexed from then on, and its
   matching jobs are fetched right away.
3. Other job pages are read for the structured data sites publish for search engines
   (schema.org JobPosting). Pages on big job sites are only read when the person running
   the API has turned that on; otherwise the search result's title and link are shown.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

from lxml import html as lxml_html

from ..http import PAGE_BYTES
from ..models import Job, Requirements, Salary
from ..normalize import (
    countries_in,
    employment_type,
    html_to_text,
    parse_date,
    remote_regions,
    seniority_from_title,
    work_mode,
)
from .base import Context, Source

ATS_PATTERNS = [
    ("greenhouse", re.compile(r"^https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?"
                              r"([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"^https?://boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"^https?://jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9._-]+)", re.I)),
    ("ashby", re.compile(r"^https?://jobs\.ashbyhq\.com/([A-Za-z0-9._%-]+)", re.I)),
    ("workable", re.compile(r"^https?://apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
    ("recruitee", re.compile(r"^https?://([a-z0-9-]+)\.recruitee\.com", re.I)),
    ("smartrecruiters", re.compile(r"^https?://(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
]
NOT_BOARDS = {"embed", "api", "v1", "jobs", "careers", "www", "app", "help", "j", "o", "s"}

BIG_SITES = re.compile(r"(^|\.)(linkedin\.com|indeed\.[a-z.]+|glassdoor\.[a-z.]+|ziprecruiter\.[a-z.]+|"
                       r"monster\.[a-z.]+|naukri\.com|seek\.com\.au|seek\.co\.nz|stepstone\.[a-z.]+|reed\.co\.uk|"
                       r"totaljobs\.com|xing\.com|simplyhired\.[a-z.]+|careerbuilder\.com|dice\.com|"
                       r"wellfound\.com|angel\.co|foundit\.in|shine\.com|timesjobs\.com|bayt\.com|"
                       r"jobstreet\.[a-z.]+|jora\.com|talent\.com|jooble\.org|adzuna\.[a-z.]+)$", re.I)
NOT_JOB_PAGES = re.compile(r"(^|\.)(youtube\.com|reddit\.com|quora\.com|wikipedia\.org|facebook\.com|twitter\.com|"
                           r"x\.com|instagram\.com|tiktok\.com|medium\.com|pinterest\.[a-z.]+)$", re.I)


# What a single posting's address looks like on the big job sites (not their search pages).
POSTING_URL = re.compile(
    r"linkedin\.com/jobs/view/|indeed\.[a-z.]+/(viewjob|rc/clk|pagead/clk|m/viewjob)|[?&]jk=[0-9a-f]+|"
    r"glassdoor\.[a-z.]+/(job-listing/|partner/joblisting)|ziprecruiter\.[a-z.]+/(c/[^/]+/job/|jobs/[^/?]+/[^/?]+)|"
    r"monster\.[a-z.]+/job-openings/|naukri\.com/job-listings-|seek\.com\.au/job/\d|seek\.co\.nz/job/\d|"
    r"stepstone\.[a-z.]+/stellenangebote--|reed\.co\.uk/jobs/[^/]+/\d+|totaljobs\.com/job/|xing\.com/jobs/[^/]+-\d+|"
    r"simplyhired\.[a-z.]+/job/|dice\.com/job-detail/|wellfound\.com/jobs/\d|foundit\.in/job/|bayt\.com/[a-z]+/job/|"
    r"jobstreet\.[a-z.]+/job/\d|careerbuilder\.com/job/", re.I)
LISTING_TITLE = re.compile(r"^\s*[\d,.]+\+?\s|\bjobs?\b[^|]{0,40}\b(in|near|at)\s+[A-Z]|\b(jobs|stellenangebote|"
                           r"vacancies|openings)\b\s*(\(|\||-|,|$)|\bjobs,?\s+(employment|hiring)", re.I)


def board_from_url(url: str) -> Optional[tuple[str, str]]:
    for ats, pat in ATS_PATTERNS:
        m = pat.match(url)
        if m:
            token = m.group(1)
            if token.lower() in NOT_BOARDS:
                continue
            return ats, token
    return None


def jobs_from_jsonld(html: str, page_url: str, source: Source) -> list[Job]:
    """Read schema.org JobPosting data embedded in a page."""
    try:
        doc = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001 - not HTML
        return []
    out: list[Job] = []
    for script in doc.xpath("//script[@type='application/ld+json']"):
        raw = (script.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except ValueError:
                continue
        for item in _walk(data):
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" not in types:
                continue
            job = _posting(item, page_url, source)
            if job:
                out.append(job)
    return out


def _walk(data: Any):
    if isinstance(data, list):
        for x in data:
            yield from _walk(x)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                yield from _walk(data[key])


def _posting(p: dict, page_url: str, source: Source) -> Optional[Job]:
    title = html_to_text(str(p.get("title") or p.get("name") or ""))
    if not title:
        return None
    valid = parse_date(p.get("validThrough"))
    from datetime import datetime, timezone
    if valid and valid < datetime.now(timezone.utc):
        return None  # expired posting
    org = p.get("hiringOrganization") or {}
    company = org.get("name", "") if isinstance(org, dict) else str(org)
    locs = p.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    names, countries = [], []
    for loc in locs:
        addr = (loc or {}).get("address") or {} if isinstance(loc, dict) else {}
        if isinstance(addr, str):
            names.append(addr)
            continue
        country = addr.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), country]
        names.append(", ".join(str(x) for x in parts if x))
        for code in countries_in(str(country or "")) or ([str(country).upper()] if country and len(str(country)) == 2
                                                         else []):
            if code not in countries:
                countries.append(code)
    location = " / ".join(n for n in names if n)
    remote = str(p.get("jobLocationType", "")).upper() == "TELECOMMUTE"
    req_loc = p.get("applicantLocationRequirements") or []
    req_loc = req_loc if isinstance(req_loc, list) else [req_loc]
    region_txt = " ".join((r.get("name", "") if isinstance(r, dict) else str(r)) for r in req_loc)
    sal = None
    bs = p.get("baseSalary") or p.get("estimatedSalary")
    if isinstance(bs, list):
        bs = bs[0] if bs else None
    if isinstance(bs, dict):
        val = bs.get("value") or {}
        if not isinstance(val, dict):
            val = {"value": val}
        unit = str(val.get("unitText") or bs.get("unitText") or "YEAR").upper()
        try:
            lo = float(val.get("minValue") or val.get("value") or 0) or None
            hi = float(val.get("maxValue") or 0) or None
        except (TypeError, ValueError):
            lo = hi = None
        if (lo or hi) and bs.get("currency"):
            sal = Salary(min=lo, max=hi, currency=str(bs["currency"]).upper()[:3],
                         period={"HOUR": "hour", "DAY": "day", "WEEK": "week", "MONTH": "month"}.get(unit, "year"))
    etype = p.get("employmentType")
    etype = etype[0] if isinstance(etype, list) and etype else etype
    # trust the posting's own URL only on the page's site; a page must not point people elsewhere
    url = str(p.get("url") or "")
    if urlparse(url).hostname != urlparse(page_url).hostname:
        url = page_url
    mode = "remote" if remote else work_mode(location)
    site = (urlparse(page_url).hostname or "").removeprefix("www.")
    return Job(title=title[:200], company=company[:120], url=url, source=source.id,
               source_name=f"{site} (via web search)" if site else source.name,
               location=location or region_txt or ("Remote" if remote else ""), countries=countries,
               work_mode=mode, remote_regions=remote_regions(region_txt) if mode == "remote" else [],
               description=html_to_text(str(p.get("description") or ""))[:12000],
               employment_type=employment_type(str(etype)) if etype else None,
               seniority=seniority_from_title(title), salary=sal, posted_at=parse_date(p.get("datePosted")))


def job_from_result(r: dict, source: Source) -> Optional[Job]:
    """A job known only from a search result on a big job site: title, company and link."""
    title = (r.get("title") or "").strip()
    if not title:
        return None
    host = urlparse(r.get("url", "")).hostname or ""
    if not POSTING_URL.search(r.get("url", "")):
        return None  # a search page or a company page, not a single posting
    if LISTING_TITLE.search(title):
        return None  # "246 Registered Nurse jobs in Berlin" is a list of jobs, not a job
    site = BIG_SITES.search(host)
    site_name = (site.group(2).split(".")[0].title() if site else host)
    clean = re.split(r"\s+[-|–]\s+(?:LinkedIn|Indeed|Glassdoor|ZipRecruiter|Monster|Naukri|SEEK|StepStone|Reed|"
                     r"XING|Dice|Wellfound)\b", title, flags=re.I)[0]
    parts = [x.strip() for x in re.split(r"\s+[-|–@]\s+|\s+at\s+", clean) if x.strip()]
    job_title = parts[0] if parts else clean
    company = parts[1] if len(parts) > 1 else ""
    location = parts[2] if len(parts) > 2 else ""
    snippet = r.get("content") or ""
    return Job(title=job_title[:160], company=company[:100], url=r["url"], source=source.id,
               source_name=f"{site_name} (via web search)", location=location,
               countries=countries_in(f"{location} {snippet[:200]}"), work_mode=work_mode(job_title, snippet[:300]),
               description=snippet[:1000], seniority=seniority_from_title(job_title), from_search_snippet=True)


class WebSearch(Source):
    id, name, kind = "web", "Web search", "live"
    homepage = "https://github.com/Ethos6/free-search-api"
    terms = "Uses your own FreeSearch API (JOBS_SEARCH_URL) or the freesearch library."
    max_pages = 8
    max_new_boards = 3
    page_budget = 7.0  # seconds to spend reading pages and new boards during one search

    def available(self, ctx: Context) -> Optional[str]:
        reason = super().available(ctx)
        if reason:
            return reason
        if ctx.settings.search_url or _freesearch() is not None:
            return None
        return "no search engine configured (set JOBS_SEARCH_URL or install the [web] extra)"

    async def _search(self, ctx: Context, query: str) -> list[dict]:
        fs = _freesearch()
        if ctx.settings.search_url:
            data = await ctx.http.get(ctx.settings.search_url.rstrip("/") + "/search",
                                      params={"q": query, "max_results": "20"}, ttl=1800,
                                      untrusted=False)
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                    for r in data.get("results", [])]
        if fs is not None:
            FreeSearch, SearchRequest = fs
            async with FreeSearch() as engine:
                res = await engine.search(SearchRequest(q=query, max_results=20))
            return [{"title": r.title, "url": str(r.url), "content": r.content or ""} for r in res.results]
        return []

    def queries(self, req: Requirements) -> list[str]:
        title = (req.titles or req.skills or req.keywords or ["jobs"])[0]
        place = next((p.name for p in req.places if p.kind in ("city", "country")), "")
        remote = "remote" if "remote" in req.work_modes else ""
        skill = next((s for s in req.skills if s.lower() not in title.lower()), "")
        where = " ".join(x for x in (remote, place) if x)
        q = [f'"{title}" job {skill} {where}'.strip(),
             f'{title} {where} (site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co '
             f'OR site:jobs.ashbyhq.com OR site:apply.workable.com)'.replace("  ", " "),
             f'{title} careers apply {where}'.strip()]
        return [re.sub(r"\s+", " ", x) for x in q]

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        from . import BOARD_SOURCES  # late import: avoids a cycle
        results: list[dict] = []
        for batch in await asyncio.gather(*(self._search(ctx, q) for q in self.queries(req)),
                                          return_exceptions=True):
            if isinstance(batch, list):
                results += batch
        jobs: list[Job] = []
        new_boards: list[tuple[str, str]] = []
        pages: list[str] = []
        seen_urls = set()
        for r in results:
            url = r.get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            board = board_from_url(url)
            if board:
                if ctx.store.add_board(board[0], board[1], added_by="web"):
                    new_boards.append(board)
                continue
            host = urlparse(url).hostname or ""
            if NOT_JOB_PAGES.search(host):
                continue
            if BIG_SITES.search(host):
                if ctx.settings.big_sites:
                    pages.append(url)
                else:
                    j = job_from_result(r, self)
                    if j:
                        jobs.append(j)
                continue
            pages.append(url)

        async def read_page(url: str) -> list[Job]:
            try:
                html = await ctx.http.get(url, as_json=False, untrusted=True, max_bytes=PAGE_BYTES, ttl=3600,
                                          min_interval=1.0, headers={"Accept": "text/html"})
                return jobs_from_jsonld(html, url, self)
            except Exception:  # noqa: BLE001 - a broken page is just skipped
                return []

        async def read_board(ats: str, token: str) -> list[Job]:
            src = BOARD_SOURCES.get(ats)
            if src is None:
                return []
            try:
                company, found = await src.fetch_board(ctx, token)
            except Exception:  # noqa: BLE001
                ctx.store.board_done(ats, token, ok=False)
                return []
            ctx.store.board_done(ats, token, ok=True, job_count=len(found), company=company)
            await asyncio.to_thread(ctx.store.replace_jobs, f"{ats}:{token}", found)
            return found

        tasks = [asyncio.ensure_future(read_page(u)) for u in pages[: self.max_pages]] + \
                [asyncio.ensure_future(read_board(a, t)) for a, t in new_boards[: self.max_new_boards]]
        if tasks:
            # whatever isn't read in time is left for next time (boards are indexed in the background anyway)
            done, pending = await asyncio.wait(tasks, timeout=self.page_budget)
            for t in pending:
                t.cancel()
            for t in done:
                if not t.cancelled() and t.exception() is None and isinstance(t.result(), list):
                    jobs += t.result()
        return jobs


_FS: Any = None


def _freesearch():
    """(FreeSearch, SearchRequest) if the freesearch library is installed, else None."""
    global _FS
    if _FS is None:
        try:
            from freesearch import FreeSearch  # type: ignore
            from freesearch.models import SearchRequest  # type: ignore
            _FS = (FreeSearch, SearchRequest)
        except ImportError:
            _FS = False
    return _FS or None
