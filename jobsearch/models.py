"""Data shapes shared by the parser, the sources, the ranker and the API."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

WorkMode = Literal["remote", "hybrid", "onsite"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "manager", "director",
                    "executive"]
EmploymentType = Literal["full_time", "part_time", "contract", "internship", "temporary", "freelance"]

SENIORITY_ORDER: list[str] = ["intern", "junior", "mid", "senior", "lead", "principal", "manager",
                              "director", "executive"]


class Place(BaseModel):
    """A place the person wants to work in, or where a job is."""
    name: str
    country: Optional[str] = None  # ISO 3166-1 alpha-2, upper case
    kind: Literal["city", "region", "country", "continent"] = "city"


class Salary(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = None  # ISO 4217
    period: Literal["year", "month", "week", "day", "hour"] = "year"
    text: Optional[str] = None  # as written by the source

    def annual(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return value * {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}[self.period]


class Requirements(BaseModel):
    """What the person is looking for, understood from their own words."""
    text: str = ""
    titles: list[str] = Field(default_factory=list, description="job titles or roles")
    skills: list[str] = Field(default_factory=list, description="skills the person has or wants to use")
    nice_skills: list[str] = Field(default_factory=list, description="nice-to-have skills")
    keywords: list[str] = Field(default_factory=list, description="other words that matter (industry, domain)")
    exclude: list[str] = Field(default_factory=list, description="words, companies or industries to avoid")
    places: list[Place] = Field(default_factory=list)
    home_country: Optional[str] = Field(None, description="where the person lives (ISO code), for remote rules")
    work_modes: list[WorkMode] = Field(default_factory=list, description="acceptable work modes; empty = any")
    seniority: Optional[Seniority] = None
    years_experience: Optional[float] = None
    salary_min: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_period: Literal["year", "month", "week", "day", "hour"] = "year"
    employment_types: list[EmploymentType] = Field(default_factory=list)
    visa_sponsorship: Optional[bool] = None
    posted_within_days: Optional[int] = None
    languages: list[str] = Field(default_factory=list, description="spoken languages the person has")
    understood_by: Literal["rules", "ai"] = "rules"

    @property
    def countries(self) -> set[str]:
        return {p.country for p in self.places if p.country}

    @property
    def remote_only(self) -> bool:
        return self.work_modes == ["remote"]

    def search_terms(self) -> list[str]:
        """Short keyword phrases to send to sources that do keyword search."""
        terms = list(self.titles[:3])
        if not terms:
            terms = self.skills[:2] or self.keywords[:2]
        return [t for t in terms if t]


class Job(BaseModel):
    title: str
    company: str = ""
    url: str
    source: str  # source id, e.g. "greenhouse"
    source_name: str = ""  # human name to credit, e.g. "Remotive"
    location: str = ""
    countries: list[str] = Field(default_factory=list)
    work_mode: Optional[WorkMode] = None
    remote_regions: list[str] = Field(default_factory=list, description="where remote applicants may live")
    description: str = ""
    employment_type: Optional[EmploymentType] = None
    seniority: Optional[Seniority] = None
    salary: Optional[Salary] = None
    posted_at: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    visa_sponsorship: Optional[bool] = None
    from_search_snippet: bool = False  # only the search engine's title/snippet is known
    also_on: list[dict] = Field(default_factory=list, description="the same job seen on other sources")

    @field_validator("title", "company", "location", "description", "source_name", mode="before")
    @classmethod
    def _text(cls, v):  # sources sometimes send null
        return "" if v is None else str(v)

    @field_validator("tags", "countries", "remote_regions", mode="before")
    @classmethod
    def _list(cls, v):
        return [str(x) for x in v if x] if isinstance(v, (list, tuple)) else []

    @field_validator("url", mode="before")
    @classmethod
    def _url(cls, v):
        v = "" if v is None else str(v).strip()
        return v if v.lower().startswith(("https://", "http://")) else ""  # never javascript:, data:, ...

    def key(self) -> str:
        """Identity used to merge the same job seen on several sources."""
        company = _norm(self.company)
        title = _norm(re.sub(r"\(.*?\)|\[.*?\]", " ", self.title))
        place = ",".join(sorted(self.countries)) or _norm(self.location)[:40]
        return hashlib.sha1(f"{company}|{title}|{place}".encode()).hexdigest()[:16]

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if not self.posted_at:
            return None
        now = now or datetime.now(timezone.utc)
        posted = self.posted_at if self.posted_at.tzinfo else self.posted_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now - posted).total_seconds() / 86400)


class Match(BaseModel):
    job: Job
    score: float  # 0..100
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceStatus(BaseModel):
    id: str
    name: str
    ok: bool
    jobs: int = 0
    elapsed_ms: int = 0
    error: Optional[str] = None
    skipped: Optional[str] = None


class SearchResponse(BaseModel):
    requirements: Requirements
    results: list[Match]
    total_found: int
    sources: list[SourceStatus]
    elapsed_ms: int
    display: dict[str, str] = Field(default_factory=dict, description="how to write skills for people")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"\b(inc|llc|ltd|gmbh|corp|corporation|co|plc|sa|ag|bv|pvt|private|limited)\b\.?", " ", s)
    return re.sub(r"[\W_]+", " ", s).strip()
