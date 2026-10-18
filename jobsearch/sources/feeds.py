"""Public job boards with free APIs. Each asks to be credited and linked; we always return
the original listing URL and the board's name, and never their logos."""
from __future__ import annotations

from ..models import Job, Salary
from ..normalize import (
    countries_in,
    employment_type,
    html_to_text,
    parse_date,
    remote_regions,
    salary_from_text,
    seniority_from_title,
    work_mode,
)
from .base import Context, Source


def _remote(title: str, company: str, url: str, src: Source, region_text: str, **kw) -> Job:
    regions = remote_regions(region_text)
    return Job(title=title, company=company, url=url, source=src.id, source_name=src.name,
               location=region_text or "Remote", work_mode="remote", remote_regions=regions,
               countries=[], seniority=kw.pop("seniority", None) or seniority_from_title(title), **kw)


class Remotive(Source):
    id, name, kind = "remotive", "Remotive", "feed"
    homepage = "https://remotive.com"
    terms = "Remotive asks to be credited with a link to the original listing. Listings are delayed 24h."

    async def fetch_feed(self, ctx: Context) -> list[Job]:
        data = await ctx.http.get("https://remotive.com/api/remote-jobs", max_bytes=60 * 1024 * 1024, cache=False)
        out = []
        for j in data.get("jobs", []):
            out.append(_remote(
                j.get("title", ""), j.get("company_name", ""), j.get("url", ""), self,
                j.get("candidate_required_location") or "",
                description=html_to_text(j.get("description")), employment_type=employment_type(j.get("job_type")),
                salary=salary_from_text(j.get("salary"), "USD"), posted_at=parse_date(j.get("publication_date")),
                tags=[t for t in [j.get("category")] + list(j.get("tags") or []) if t]))
        return [x for x in out if x.url and x.title]


class RemoteOK(Source):
    id, name, kind = "remoteok", "Remote OK", "feed"
    homepage = "https://remoteok.com"
    terms = "Remote OK asks to be credited and linked (followed link). Logos are not used."

    async def fetch_feed(self, ctx: Context) -> list[Job]:
        data = await ctx.http.get("https://remoteok.com/api", max_bytes=30 * 1024 * 1024, cache=False)
        out = []
        for j in data[1:] if isinstance(data, list) else []:
            if not isinstance(j, dict) or not j.get("position"):
                continue
            sal = None
            if j.get("salary_min") or j.get("salary_max"):
                sal = Salary(min=j.get("salary_min") or None, max=j.get("salary_max") or None, currency="USD")
            out.append(_remote(
                j.get("position", ""), j.get("company", ""), j.get("url") or j.get("apply_url") or "", self,
                j.get("location") or "", description=html_to_text(j.get("description")), salary=sal,
                posted_at=parse_date(j.get("epoch") or j.get("date")), tags=list(j.get("tags") or [])))
        return [x for x in out if x.url]


class Jobicy(Source):
    id, name, kind = "jobicy", "Jobicy", "feed"
    homepage = "https://jobicy.com"
    terms = "Jobicy asks to be credited with a direct link; apply buttons go to the original job URL."

    async def fetch_feed(self, ctx: Context) -> list[Job]:
        data = await ctx.http.get("https://jobicy.com/api/v2/remote-jobs", params={"count": "100"}, cache=False)
        out = []
        for j in data.get("jobs", []):
            sal = None
            if j.get("annualSalaryMin") or j.get("annualSalaryMax"):
                sal = Salary(min=j.get("annualSalaryMin"), max=j.get("annualSalaryMax"),
                             currency=j.get("salaryCurrency") or "USD")
            level = (j.get("jobLevel") or "").lower()
            seniority = {"senior": "senior", "midweight": "mid", "junior": "junior", "lead": "lead",
                         "manager": "manager", "director": "director", "executive": "executive",
                         "internship": "intern"}.get(level)
            types = j.get("jobType") or []
            out.append(_remote(
                j.get("jobTitle", ""), j.get("companyName", ""), j.get("url", ""), self, j.get("jobGeo") or "",
                description=html_to_text(j.get("jobDescription") or j.get("jobExcerpt")), salary=sal,
                employment_type=employment_type(types[0] if types else None), seniority=seniority,
                posted_at=parse_date(j.get("pubDate")),
                tags=list(j.get("jobIndustry") or [])))
        return [x for x in out if x.url and x.title]


class Arbeitnow(Source):
    id, name, kind = "arbeitnow", "Arbeitnow", "feed"
    homepage = "https://www.arbeitnow.com"
    terms = "Free public job board API (mostly Germany and Europe)."
    pages = 5

    async def fetch_feed(self, ctx: Context) -> list[Job]:
        out = []
        for page in range(1, self.pages + 1):
            data = await ctx.http.get("https://www.arbeitnow.com/api/job-board-api", params={"page": str(page)},
                                      cache=False, min_interval=1.0)
            for j in data.get("data", []):
                loc = j.get("location") or ""
                remote = bool(j.get("remote"))
                types = j.get("job_types") or []
                out.append(Job(
                    title=j.get("title", ""), company=j.get("company_name", ""), url=j.get("url", ""),
                    source=self.id, source_name=self.name, location=loc, countries=countries_in(loc),
                    work_mode="remote" if remote else work_mode(loc),
                    remote_regions=countries_in(loc) if remote else [],
                    description=html_to_text(j.get("description")),
                    employment_type=next((employment_type(t) for t in types if employment_type(t)), None),
                    seniority=seniority_from_title(j.get("title", "")), posted_at=parse_date(j.get("created_at")),
                    tags=list(j.get("tags") or [])))
            if not (data.get("links") or {}).get("next"):
                break
        return [x for x in out if x.url and x.title]


FEED_SOURCES: dict[str, Source] = {s.id: s for s in (Remotive(), RemoteOK(), Jobicy(), Arbeitnow())}
