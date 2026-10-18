"""Company careers systems with public job-board APIs.

These are the official, documented endpoints companies use to show their own openings
on their websites. Each board is one company.
"""
from __future__ import annotations

from typing import Any, Optional

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


def _job(**kw: Any) -> Job:
    title = kw.get("title") or ""
    kw.setdefault("seniority", seniority_from_title(title))
    loc = kw.get("location") or ""
    if not kw.get("countries"):
        kw["countries"] = countries_in(loc)
    if kw.get("work_mode") == "remote" and not kw.get("remote_regions"):
        kw["remote_regions"] = remote_regions(loc)
    return Job(**kw)


class Greenhouse(Source):
    id, name, kind = "greenhouse", "Greenhouse", "board"
    homepage = "https://www.greenhouse.com"
    terms = "Public Job Board API (boards-api.greenhouse.io); links go to the company's own posting."

    def board_url(self, token: str) -> str:
        return f"https://job-boards.greenhouse.io/{token}"

    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        data = await ctx.http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                                  params={"content": "true", "pay_transparency": "true"},
                                  max_bytes=40 * 1024 * 1024, cache=False)
        jobs = []
        company = ""
        for j in data.get("jobs", []):
            company = j.get("company_name") or company
            loc = (j.get("location") or {}).get("name", "")
            offices = " / ".join(o.get("location") or o.get("name") or "" for o in j.get("offices") or [])
            desc = html_to_text(j.get("content"))
            meta = {m.get("name", ""): m.get("value") for m in j.get("metadata") or [] if isinstance(m, dict)}
            sal = None
            for r in j.get("pay_input_ranges") or []:
                try:
                    sal = Salary(min=r["min_cents"] / 100, max=r["max_cents"] / 100,
                                 currency=r.get("currency_type") or "USD", period="year", text=r.get("title"))
                    break
                except (KeyError, TypeError):
                    continue
            emp = next((employment_type(str(v)) for k, v in meta.items()
                        if "type" in k.lower() and isinstance(v, str)), None)
            jobs.append(_job(
                title=j.get("title", ""), company=company or token, url=j.get("absolute_url", ""), source=self.id,
                source_name=self.name, location=loc, description=desc,
                countries=countries_in(f"{loc} {offices}"),
                work_mode=work_mode(loc), employment_type=emp, salary=sal,
                posted_at=parse_date(j.get("first_published") or j.get("updated_at")),
                tags=[d.get("name", "") for d in j.get("departments") or [] if d.get("name")]))
        return company, [x for x in jobs if x.url and x.title]


class Lever(Source):
    id, name, kind = "lever", "Lever", "board"
    homepage = "https://www.lever.co"
    terms = "Public Postings API (api.lever.co/v0/postings)."

    def board_url(self, token: str) -> str:
        return f"https://jobs.lever.co/{token}"

    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        data = await ctx.http.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"},
                                  max_bytes=40 * 1024 * 1024, cache=False)
        jobs = []
        for p in data if isinstance(data, list) else []:
            cat = p.get("categories") or {}
            locs = cat.get("allLocations") or ([cat["location"]] if cat.get("location") else [])
            loc = " / ".join(locs)
            wt = (p.get("workplaceType") or "").lower()
            mode = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}.get(wt) or \
                work_mode(loc)
            parts = [p.get("descriptionPlain") or html_to_text(p.get("description"))]
            for lst in p.get("lists") or []:
                parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
            parts.append(p.get("additionalPlain") or "")
            sr = p.get("salaryRange") or {}
            sal = None
            if sr.get("min") or sr.get("max"):
                interval = (sr.get("interval") or "").lower()
                period = "hour" if "hour" in interval else "month" if "month" in interval else "year"
                sal = Salary(min=sr.get("min"), max=sr.get("max"), currency=sr.get("currency") or "USD",
                             period=period)
            countries = countries_in(loc)
            if p.get("country") and p["country"].upper() not in countries:
                countries.append(p["country"].upper())
            jobs.append(_job(
                title=p.get("text", ""), company=token, url=p.get("hostedUrl", ""), source=self.id,
                source_name=self.name, location=loc, countries=countries, work_mode=mode,
                description="\n".join(x for x in parts if x)[:12000],
                employment_type=employment_type(cat.get("commitment")), salary=sal,
                posted_at=parse_date(p.get("createdAt")),
                tags=[t for t in (cat.get("team"), cat.get("department")) if t]))
        return "", [x for x in jobs if x.url and x.title]


class Ashby(Source):
    id, name, kind = "ashby", "Ashby", "board"
    homepage = "https://www.ashbyhq.com"
    terms = "Public Job Posting API (api.ashbyhq.com/posting-api)."

    def board_url(self, token: str) -> str:
        return f"https://jobs.ashbyhq.com/{token}"

    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        data = await ctx.http.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                                  params={"includeCompensation": "true"}, max_bytes=40 * 1024 * 1024, cache=False)
        jobs = []
        for p in data.get("jobs", []):
            if p.get("isListed") is False:
                continue
            locs = [p.get("location") or ""] + [s.get("location", "") for s in p.get("secondaryLocations") or []]
            loc = " / ".join(x for x in locs if x)
            countries: list[str] = []
            for a in [p.get("address")] + [s.get("address") for s in p.get("secondaryLocations") or []]:
                c = ((a or {}).get("postalAddress") or {}).get("addressCountry")
                for code in countries_in(c or ""):
                    if code not in countries:
                        countries.append(code)
            for code in countries_in(loc):
                if code not in countries:
                    countries.append(code)
            wt = (p.get("workplaceType") or "").lower()
            mode = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}.get(wt) or \
                work_mode(loc, remote_flag=p.get("isRemote"))
            sal = None
            for tier in ((p.get("compensation") or {}).get("compensationTiers") or []):
                for comp in tier.get("components") or []:
                    if comp.get("compensationType") == "Salary" and (comp.get("minValue") or comp.get("maxValue")):
                        interval = (comp.get("interval") or "").upper()
                        period = "hour" if "HOUR" in interval else "month" if "MONTH" in interval else "year"
                        sal = Salary(min=comp.get("minValue"), max=comp.get("maxValue"),
                                     currency=comp.get("currencyCode") or "USD", period=period,
                                     text=comp.get("summary"))
                        break
                if sal:
                    break
            jobs.append(_job(
                title=p.get("title", ""), company=token, url=p.get("jobUrl") or p.get("applyUrl") or "",
                source=self.id, source_name=self.name, location=loc, countries=countries, work_mode=mode,
                description=(p.get("descriptionPlain") or html_to_text(p.get("descriptionHtml")))[:12000],
                employment_type=employment_type(p.get("employmentType")), salary=sal,
                posted_at=parse_date(p.get("publishedAt")),
                tags=[t for t in (p.get("department"), p.get("team")) if t]))
        return "", [x for x in jobs if x.url and x.title]


class Workable(Source):
    id, name, kind = "workable", "Workable", "board"
    homepage = "https://www.workable.com"
    terms = "Public careers widget API (apply.workable.com/api/v1/widget)."

    def board_url(self, token: str) -> str:
        return f"https://apply.workable.com/{token}/"

    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        data = await ctx.http.get(f"https://apply.workable.com/api/v1/widget/accounts/{token}",
                                  params={"details": "true"}, cache=False)
        company = data.get("name") or token
        jobs = []
        for p in data.get("jobs", []):
            locs = [", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x)
                    for l in p.get("locations") or [] if not l.get("hidden")]
            loc = " / ".join(x for x in locs if x) or ", ".join(
                x for x in (p.get("city"), p.get("state"), p.get("country")) if x)
            countries = [l["countryCode"].upper() for l in p.get("locations") or [] if l.get("countryCode")]
            mode = "remote" if p.get("telecommuting") else work_mode(loc)
            exp = (p.get("experience") or "").lower()
            seniority = {"entry level": "junior", "internship": "intern", "associate": "junior",
                         "mid-senior level": "senior", "director": "director", "executive": "executive"}.get(exp)
            jobs.append(_job(
                title=p.get("title", ""), company=company,
                url=p.get("url") or p.get("shortlink") or p.get("application_url") or "",
                source=self.id, source_name=self.name, location=loc, countries=countries or countries_in(loc),
                work_mode=mode, description=html_to_text(p.get("description")),
                employment_type=employment_type(p.get("employment_type")),
                seniority=seniority or seniority_from_title(p.get("title", "")),
                posted_at=parse_date(p.get("published_on") or p.get("created_at")),
                tags=[t for t in (p.get("department"), p.get("function"), p.get("industry")) if t]))
        return company, [x for x in jobs if x.url and x.title]


class Recruitee(Source):
    id, name, kind = "recruitee", "Recruitee", "board"
    homepage = "https://recruitee.com"
    terms = "Public Careers Site API ({company}.recruitee.com/api/offers)."

    def board_url(self, token: str) -> str:
        return f"https://{token}.recruitee.com/"

    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        data = await ctx.http.get(f"https://{token}.recruitee.com/api/offers/", max_bytes=40 * 1024 * 1024,
                                  cache=False)
        jobs = []
        company = ""
        for o in data.get("offers", []):
            company = o.get("company_name") or company
            loc = o.get("location") or ", ".join(x for x in (o.get("city"), o.get("country")) if x)
            mode = "remote" if o.get("remote") else "hybrid" if o.get("hybrid") else \
                "onsite" if o.get("on_site") else work_mode(loc)
            countries = [o["country_code"].upper()] if o.get("country_code") else countries_in(loc)
            s = o.get("salary") or {}
            sal = None
            if s.get("min") or s.get("max"):
                per = (s.get("period") or "year").lower()
                sal = Salary(min=_num(s.get("min")), max=_num(s.get("max")), currency=s.get("currency") or None,
                             period="hour" if "hour" in per else "month" if "month" in per else "year")
                if not sal.currency:
                    sal = None
            exp = (o.get("experience_code") or "").lower()
            seniority = {"internship": "intern", "entry_level": "junior", "associate": "junior",
                         "mid_level": "mid", "senior_level": "senior", "director": "director",
                         "executive": "executive"}.get(exp)
            jobs.append(_job(
                title=o.get("title", ""), company=company or token, url=o.get("careers_url", ""),
                source=self.id, source_name=self.name, location=loc, countries=countries, work_mode=mode,
                description=html_to_text((o.get("description") or "") + "\n" + (o.get("requirements") or "")),
                employment_type=employment_type(o.get("employment_type_code")),
                seniority=seniority or seniority_from_title(o.get("title", "")), salary=sal,
                posted_at=parse_date(o.get("published_at") or o.get("created_at")),
                tags=[t for t in [o.get("department")] + list(o.get("tags") or []) if isinstance(t, str) and t]))
        return company, [x for x in jobs if x.url and x.title]


class SmartRecruiters(Source):
    """Large employers with thousands of openings: searched live by keyword instead of indexed."""
    id, name, kind = "smartrecruiters", "SmartRecruiters", "live"
    homepage = "https://www.smartrecruiters.com"
    terms = "Public Posting API (api.smartrecruiters.com/v1/companies/{id}/postings)."

    def board_url(self, token: str) -> str:
        return f"https://jobs.smartrecruiters.com/{token}"

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        import asyncio
        terms = req.search_terms()
        if not terms:
            return []
        companies = [b["token"] for b in ctx.store.boards("smartrecruiters")][:30]
        countries = sorted(req.countries)

        async def one(company: str) -> list[Job]:
            params = {"q": terms[0], "limit": "50"}
            if len(countries) == 1 and not req.remote_only:
                params["country"] = countries[0].lower()
            try:
                data = await ctx.http.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings",
                                          params=params, ttl=1800)
            except Exception:  # noqa: BLE001 - one company failing must not fail the source
                return []
            return [self._job(company, p) for p in data.get("content", [])]

        lists = await asyncio.gather(*(one(c) for c in companies))
        return [j for lst in lists for j in lst if j.url and j.title]

    def _job(self, company: str, p: dict) -> Job:
        loc = p.get("location") or {}
        full = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
        mode = "remote" if loc.get("remote") else "hybrid" if loc.get("hybrid") else "onsite"
        exp = ((p.get("experienceLevel") or {}).get("id") or "").lower()
        seniority = {"internship": "intern", "entry_level": "junior", "associate": "junior",
                     "mid_senior_level": "senior", "director": "director", "executive": "executive"}.get(exp)
        ident = (p.get("company") or {}).get("identifier") or company
        return _job(
            title=p.get("name", ""), company=(p.get("company") or {}).get("name") or company,
            url=f"https://jobs.smartrecruiters.com/{ident}/{p.get('id')}", source=self.id, source_name=self.name,
            location=full, countries=[loc["country"].upper()] if loc.get("country") else countries_in(full),
            work_mode=mode, employment_type=employment_type(((p.get("typeOfEmployment") or {}).get("label"))),
            seniority=seniority or seniority_from_title(p.get("name", "")),
            posted_at=parse_date(p.get("releasedDate")),
            tags=[x for x in (((p.get("function") or {}).get("label")), ((p.get("industry") or {}).get("label"))) if x])


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


BOARD_SOURCES: dict[str, Source] = {s.id: s for s in (Greenhouse(), Lever(), Ashby(), Workable(), Recruitee())}
