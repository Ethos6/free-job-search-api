"""Sources asked at search time with the person's own keywords."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from lxml import html as lxml_html

from .. import vocab
from ..models import Job, Requirements, Salary
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

# canonical role -> The Muse category
MUSE_CATEGORIES = {
    "software engineer": "Software Engineering", "backend engineer": "Software Engineering",
    "frontend engineer": "Software Engineering", "full stack engineer": "Software Engineering",
    "mobile engineer": "Software Engineering", "devops engineer": "Software Engineering",
    "qa engineer": "Software Engineering", "embedded engineer": "Software Engineering",
    "game developer": "Software Engineering", "tech lead": "Software Engineering",
    "engineering manager": "Software Engineering", "solutions architect": "Software Engineering",
    "machine learning engineer": "Software Engineering", "blockchain engineer": "Software Engineering",
    "security engineer": "Computer and IT", "it support": "Computer and IT", "database administrator": "Computer and IT",
    "data engineer": "Data and Analytics", "data scientist": "Data and Analytics", "data analyst": "Data and Analytics",
    "product manager": "Product Management", "project manager": "Project Management",
    "product designer": "Design and UX", "graphic designer": "Design and UX",
    "marketing manager": "Advertising and Marketing", "seo specialist": "Advertising and Marketing",
    "social media manager": "Media, PR, and Communications", "content writer": "Writing and Editing",
    "sales representative": "Sales", "business development manager": "Sales", "account manager": "Account Management",
    "customer success manager": "Account Management", "customer support": "Customer Service",
    "accountant": "Accounting and Finance", "financial analyst": "Accounting and Finance",
    "finance manager": "Accounting and Finance", "auditor": "Accounting and Finance",
    "hr manager": "Human Resources and Recruitment", "recruiter": "Human Resources and Recruitment",
    "operations manager": "Business Operations", "supply chain manager": "Transportation and Logistics",
    "administrative assistant": "Administration and Office", "data entry": "Administration and Office",
    "nurse": "Healthcare", "doctor": "Healthcare", "pharmacist": "Healthcare", "medical assistant": "Healthcare",
    "therapist": "Healthcare", "lab technician": "Science and Engineering",
    "clinical research associate": "Science and Engineering", "teacher": "Education",
    "mechanical engineer": "Science and Engineering", "electrical engineer": "Science and Engineering",
    "civil engineer": "Science and Engineering", "architect": "Construction", "construction manager": "Construction",
    "electrician": "Installation, Maintenance, and Repairs", "driver": "Transportation and Logistics",
    "chef": "Food and Hospitality Services", "retail associate": "Retail", "hospitality": "Food and Hospitality Services",
    "consultant": "Business Operations", "researcher": "Science and Engineering", "translator": "Writing and Editing",
    "video editor": "Media, PR, and Communications", "lawyer": "Business Operations",
    "compliance officer": "Business Operations", "paralegal": "Administration and Office",
}
MUSE_LEVEL = {"intern": "Internship", "junior": "Entry Level", "mid": "Mid Level", "senior": "Senior Level",
              "lead": "Senior Level", "principal": "Senior Level", "manager": "management",
              "director": "management", "executive": "management"}


class TheMuse(Source):
    id, name, kind = "themuse", "The Muse", "live"
    homepage = "https://www.themuse.com"
    terms = "Public jobs API (themuse.com/api/public/jobs); listings link to The Muse."

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        cats = []
        for t in req.titles:
            canon = vocab.role_lookup()[1].get(t.lower(), t.lower())
            if canon in MUSE_CATEGORIES and MUSE_CATEGORIES[canon] not in cats:
                cats.append(MUSE_CATEGORIES[canon])
        if not cats:
            return []
        params: list[tuple[str, str]] = [("category", c) for c in cats[:2]]
        if req.seniority and req.seniority in MUSE_LEVEL:
            params.append(("level", MUSE_LEVEL[req.seniority]))
        locs = [p for p in req.places if p.kind == "city"][:3]
        for p in locs:
            country = next((n for n in vocab.places()["countries"].get(p.country or "", [])), "")
            params.append(("location", f"{p.name}, {country.title()}" if country else p.name))
        if "remote" in req.work_modes or not locs:
            params.append(("location", "Flexible / Remote"))
        out: list[Job] = []
        for page in (1, 2):
            url = "https://www.themuse.com/api/public/jobs?" + "&".join(
                f"{k}={quote(v)}" for k, v in params + [("page", str(page))])
            data = await ctx.http.get(url, ttl=1800)
            for j in data.get("results", []):
                locs_txt = " / ".join(l.get("name", "") for l in j.get("locations") or [])
                remote = "remote" in locs_txt.lower() or "flexible" in locs_txt.lower()
                level = " ".join(l.get("short_name", "") for l in j.get("levels") or [])
                out.append(Job(
                    title=j.get("name", ""), company=(j.get("company") or {}).get("name", ""),
                    url=(j.get("refs") or {}).get("landing_page", ""), source=self.id, source_name=self.name,
                    location=locs_txt, countries=countries_in(locs_txt), work_mode="remote" if remote else None,
                    description=html_to_text(j.get("contents")), posted_at=parse_date(j.get("publication_date")),
                    seniority={"internship": "intern", "entry": "junior", "mid": "mid", "senior": "senior",
                               "management": "manager"}.get(level.split(" ")[0]) or
                    seniority_from_title(j.get("name", "")),
                    tags=[c.get("name", "") for c in j.get("categories") or []]))
            if page >= int(data.get("page_count") or 1):
                break
        return [x for x in out if x.url and x.title]


class Himalayas(Source):
    id, name, kind = "himalayas", "Himalayas", "live"
    homepage = "https://himalayas.app"
    terms = "Public jobs API (himalayas.app/jobs/api); listings link back to Himalayas."

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        if req.work_modes and "remote" not in req.work_modes:
            return []  # remote-only board
        out: list[Job] = []
        for term in req.search_terms()[:2]:
            data = await ctx.http.get("https://himalayas.app/jobs/api/search", params={"q": term}, ttl=1800,
                                      min_interval=0.5)
            for j in data.get("jobs", []):
                sal = None
                if j.get("minSalary") or j.get("maxSalary"):
                    per = (j.get("salaryPeriod") or "annual").lower()
                    sal = Salary(min=j.get("minSalary"), max=j.get("maxSalary"), currency=j.get("currency") or "USD",
                                 period="hour" if "hour" in per else "month" if "month" in per else "year")
                regions = " ".join(j.get("locationRestrictions") or [])
                sen = [s.lower() for s in j.get("seniority") or []]
                seniority = next(({"entry-level": "junior", "entry level": "junior", "mid-level": "mid",
                                   "senior": "senior", "manager": "manager", "director": "director",
                                   "executive": "executive", "internship": "intern"}.get(s) for s in sen), None)
                out.append(Job(
                    title=j.get("title", ""), company=j.get("companyName", ""),
                    url=j.get("applicationLink") or j.get("guid") or "", source=self.id, source_name=self.name,
                    location=regions or "Remote", work_mode="remote", remote_regions=remote_regions(regions),
                    description=html_to_text(j.get("description") or j.get("excerpt")), salary=sal,
                    employment_type=employment_type(j.get("employmentType")),
                    seniority=seniority or seniority_from_title(j.get("title", "")),
                    posted_at=parse_date(j.get("pubDate")),
                    tags=[c.replace("-", " ") for c in j.get("categories") or []]))
        return [x for x in out if x.url and x.title]


class HackerNews(Source):
    id, name, kind = "hackernews", "Hacker News: Who is hiring", "live"
    homepage = "https://news.ycombinator.com"
    terms = "Monthly 'Ask HN: Who is hiring?' thread, read through the public HN Algolia API."

    async def _thread(self, ctx: Context) -> Optional[tuple[str, str]]:
        data = await ctx.http.get("https://hn.algolia.com/api/v1/search_by_date",
                                  params={"tags": "story,author_whoishiring", "hitsPerPage": "6"}, ttl=6 * 3600)
        for h in data.get("hits", []):
            if "who is hiring" in (h.get("title") or "").lower():
                return h["objectID"], h.get("created_at", "")
        return None

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        thread = await self._thread(ctx)
        if not thread:
            return []
        story_id, _ = thread
        terms = req.search_terms()[:2] or req.skills[:2]
        out: list[Job] = []
        seen = set()
        for term in terms:
            q = term
            if "remote" in req.work_modes:
                q += " remote"
            data = await ctx.http.get("https://hn.algolia.com/api/v1/search",
                                      params={"tags": f"comment,story_{story_id}", "query": q, "hitsPerPage": "60"},
                                      ttl=3600)
            for h in data.get("hits", []):
                if str(h.get("parent_id")) != str(story_id) or h["objectID"] in seen:
                    continue  # only top-level posts are job ads
                seen.add(h["objectID"])
                job = self.parse_post(h)
                if job:
                    out.append(job)
        return out

    def parse_post(self, h: dict) -> Optional[Job]:
        raw = h.get("comment_text") or ""
        text = html_to_text(raw)
        first = text.split("\n", 1)[0]
        parts = [p.strip() for p in re.split(r"\s+\|\s+|\s+\|\s*|\s*\|\s+", first) if p.strip()]
        if len(parts) < 2:
            return None
        company = re.sub(r"\(.*?\)", "", parts[0]).strip()[:80]
        title = next((p for p in parts[1:] if vocab.find_roles(p) or re.search(
            r"engineer|developer|designer|manager|scientist|analyst|lead|head|architect|founding|researcher",
            p, re.I)), parts[1])
        rest = " | ".join(p for p in parts[1:] if p != title)
        mode = work_mode(rest)
        sal = salary_from_text(rest, "USD") if re.search(r"[$€£]\s?\d", rest) else None
        return Job(
            title=title[:140], company=company, url=f"https://news.ycombinator.com/item?id={h['objectID']}",
            source=self.id, source_name="Hacker News", location=rest[:160], countries=countries_in(rest),
            work_mode=mode, remote_regions=remote_regions(rest) if mode == "remote" else [],
            description=text[:8000], salary=sal, employment_type=employment_type(rest),
            seniority=seniority_from_title(title), posted_at=parse_date(h.get("created_at")),
            visa_sponsorship=_visa(text))


class LinkedIn(Source):
    """LinkedIn's public, logged-out job search pages. LinkedIn's User Agreement forbids automated
    access, so this is off unless the person running the API turns it on. No login, no tricks:
    if LinkedIn refuses, we stop asking for a while."""
    id, name, kind = "linkedin", "LinkedIn (public job search)", "live"
    homepage = "https://www.linkedin.com/jobs"
    terms = "LinkedIn's terms forbid scraping. Off by default; whoever runs the API decides."
    big_site = True

    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        terms = req.search_terms()[:2]
        if not terms:
            return []
        loc = next((p.name for p in req.places if p.kind in ("city", "country")), "")
        if not loc and req.remote_only:
            loc = "Worldwide"
        out: list[Job] = []
        for term in terms:
            params = {"keywords": term, "location": loc, "start": "0"}
            wt = {"remote": "2", "hybrid": "3", "onsite": "1"}
            if req.work_modes:
                params["f_WT"] = ",".join(wt[m] for m in req.work_modes)
            if req.posted_within_days:
                params["f_TPR"] = f"r{req.posted_within_days * 86400}"
            html = await ctx.http.get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                                      params=params, as_json=False, ttl=1800, min_interval=3.0)
            out += self.parse_cards(html)
        return out

    def parse_cards(self, html: str) -> list[Job]:
        if not html.strip():
            return []
        doc = lxml_html.fromstring(html)
        jobs = []
        for card in doc.xpath("//div[contains(@class,'base-search-card')]"):
            urn = card.get("data-entity-urn") or ""
            m = re.search(r"jobPosting:(\d+)", urn)
            title = _text(card, ".//h3[contains(@class,'base-search-card__title')]")
            if not m or not title:
                continue
            company = _text(card, ".//h4[contains(@class,'base-search-card__subtitle')]")
            loc = _text(card, ".//span[contains(@class,'job-search-card__location')]")
            dt = card.xpath(".//time/@datetime")
            sal_txt = _text(card, ".//span[contains(@class,'job-search-card__salary-info')]")
            jobs.append(Job(
                title=title, company=company, url=f"https://www.linkedin.com/jobs/view/{m.group(1)}/",
                source=self.id, source_name="LinkedIn", location=loc, countries=countries_in(loc),
                work_mode=work_mode(loc), salary=salary_from_text(sal_txt) if sal_txt else None,
                seniority=seniority_from_title(title), posted_at=parse_date(dt[0]) if dt else None))
        return jobs


NO_VISA = re.compile(r"\b(no|not|without|unable to|cannot|can'?t|don'?t|do not|won'?t|will not|isn'?t|is not)\b"
                     r"[^.\n]{0,30}\b(visa|sponsor\w*)|\bvisa sponsorship\b[^.\n]{0,15}\b(not|unavailable)\b", re.I)


def _visa(text: str):
    if NO_VISA.search(text):
        return False
    if re.search(r"\b(visa sponsorship|sponsor (your |a |work )?visas?|h-?1b (transfer|sponsorship)|relocation and "
                 r"visa|we sponsor)\b", text, re.I):
        return True
    return None


def _text(node, xpath: str) -> str:
    found = node.xpath(xpath)
    return " ".join(found[0].text_content().split()) if found else ""


LIVE_SOURCES: dict[str, Source] = {s.id: s for s in (TheMuse(), Himalayas(), HackerNews(), LinkedIn())}
