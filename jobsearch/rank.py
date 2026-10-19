"""Score how well each job fits the person's requirements, and explain why in plain words.

Score out of 100:
  role/title 35 · skills 25 · location and work mode 15 · seniority 10 · salary 10 · freshness 5
Hard filters drop a job outright: things the person said to avoid, a work mode or place they
can't do, a salary clearly below their minimum, postings older than they asked for.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from . import vocab
from .models import SENIORITY_ORDER, Job, Match, Requirements
from .normalize import to_usd
from .parse import DOMAINS

DOMAIN_WORDS = set(DOMAINS)
GENERIC = {"engineer", "developer", "manager", "specialist", "analyst", "associate", "consultant", "lead",
           "officer", "assistant", "coordinator", "representative", "executive", "technician", "director",
           "head", "staff", "senior", "junior", "expert", "professional", "agent", "worker", "operator"}
LIFESTYLE = {
    "travel": r"\b(travel\w*\s+(is\s+)?(required|expected|up to \d+\s*%)|\d+\s*%\s+travel|willing(ness)? to "
              r"travel|frequent travel|extensive travel)",
    "relocation": r"\b(must|required to|need to|willing(ness)? to) relocate\b",
    "weekends": r"\b(weekend (work|shifts?) (required|expected)|work(ing)? (on )?weekends)\b",
    "weekend": r"\b(weekend (work|shifts?) (required|expected)|work(ing)? (on )?weekends)\b",
    "on-call": r"\bon-?call (rotation|duty|shifts?|required)\b", "oncall": r"\bon-?call (rotation|duty|shifts?)\b",
    "night shift": r"\bnight shifts?\b", "night shifts": r"\bnight shifts?\b",
    "cold calling": r"\bcold[- ]call", "commission-only": r"\bcommission[- ]only\b",
    "commission only": r"\bcommission[- ]only\b", "sales": r"\b(sales (quota|targets?)|quota-carrying)\b",
}
_WORD = re.compile(r"[a-z0-9+#.]+")
STOP = {"and", "or", "the", "a", "an", "of", "for", "to", "in", "with", "at", "on", "senior", "junior", "lead",
        "sr", "jr", "i", "ii", "iii", "iv", "staff", "principal", "remote", "hybrid", "intern", "new", "grad"}


def _tokens(s: str) -> set[str]:
    return {t.strip(".") for t in _WORD.findall(s.lower()) if t.strip(".") and t.strip(".") not in STOP}


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w+#])" + re.escape(phrase.lower()) + r"(?![\w+#])", text) is not None


def title_score(req: Requirements, job: Job) -> tuple[float, Optional[str]]:
    """0..1: how well the job title fits the wanted roles."""
    if not req.titles:
        return 0.5, None  # no role given: neutral
    jt = job.title.lower()
    best, label = 0.0, None
    for want in req.titles:
        for i, term in enumerate(vocab.role_terms(want)):
            if _contains(jt, term):
                s = 1.0 if i == 0 or term == want.lower() else 0.9
                if s > best:
                    best, label = s, want
        wt, jtok = _tokens(want), _tokens(jt)
        if wt and jtok:
            # a shared generic word ("engineer", "manager") alone is not the same role
            specific = (wt & jtok) - GENERIC
            overlap = (len(specific) / max(1, len(wt - GENERIC))) if wt - GENERIC else len(wt & jtok) / len(wt)
            if not specific and wt - GENERIC:
                overlap = 0.25 if wt & jtok else 0.0
            # the role's main noun ("engineer", "nurse", "designer") must be there for a partial match
            head_ok = any(_contains(jt, w) for w in [want.split()[-1]] + [t.split()[-1] for t in vocab.role_terms(want)])
            s = overlap * (0.75 if head_ok else 0.35)
            if s > best:
                best, label = s, want
    return best, label


def skill_hits(req: Requirements, job: Job) -> tuple[list[str], list[str]]:
    body = f"{job.title} {' '.join(job.tags)} {job.description}".lower()
    have = [s for s in req.skills if _skill_in(s, body)]
    nice = [s for s in req.nice_skills if _skill_in(s, body)]
    return have, nice


def _skill_in(skill: str, body: str) -> bool:
    terms = [skill] + vocab.SKILLS.get(skill, [])
    for t in terms:
        if len(t) <= 2 and t not in ("c#", "go", "r", "c"):
            continue
        if t in ("go", "r", "c"):
            if re.search(r"(?<![\w+#.])" + {"go": r"(go|golang)", "r": r"r", "c": r"c"}[t] + r"(?![\w+#])(?=[\s,/;)]|$)",
                         body) and (t != "go" or re.search(r"\bgolang\b|\bgo\b[ ,/]+(and|or|developer|engineer|"
                                                            r"programming|lang)|[,/(] ?go\b", body)):
                return True
            continue
        if _contains(body, t):
            return True
    return False


def place_fit(req: Requirements, job: Job) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """(score 0..1 or None to drop, reason, warning)."""
    wanted_modes = set(req.work_modes)
    mode = job.work_mode
    want_countries = set(req.countries)
    regions = vocab.region_countries()
    for p in req.places:
        if p.kind == "continent":
            want_countries |= regions.get(p.name.lower(), set())
    home = req.home_country

    if mode == "remote":
        if wanted_modes and "remote" not in wanted_modes and not (job.countries and want_countries & set(job.countries)):
            return None, None, None  # they want office/hybrid only
        allowed = set(job.remote_regions) or (set(job.countries) if job.countries and job.source != "remotive"
                                              and not req.remote_only else set())
        check = {home} if home else want_countries
        if allowed and check and not (allowed & check):
            return None, None, None  # remote, but only for people living elsewhere
        worldwide = any(w in job.location.lower() for w in vocab.WORLDWIDE_WORDS)
        if not allowed and not wanted_modes and check and not worldwide:
            # they named a place and didn't ask for remote; a remote job of unknown region is a guess
            return None, None, None
        if allowed and not check:
            return 0.8, "Remote", f"Remote only for people in: {_names(allowed)}"
        where = f" ({_names(allowed)})" if allowed and len(allowed) <= 6 else " (worldwide)" if not allowed else ""
        fit = 1.0 if (not wanted_modes or "remote" in wanted_modes) else 0.7
        return fit, f"Remote{where}", None

    # on-site, hybrid or unknown
    if req.remote_only:
        if mode in ("onsite", "hybrid"):
            return None, None, None
        if job.countries:
            return None, None, None  # a job tied to a place, with no sign it is remote
        return 0.3, None, "Work mode not stated; may not be remote"
    if wanted_modes and mode and mode not in wanted_modes:
        if not (mode == "hybrid" and "onsite" in wanted_modes):
            return None, None, None
    if not want_countries and not req.places:
        return 0.7, None, None
    job_c = set(job.countries)
    loc = job.location.lower()
    cities = [p for p in req.places if p.kind == "city"]
    for c in cities:
        if _contains(loc, c.name.lower()) or any(_contains(loc, a) for a, m in vocab.places()["city_aliases"].items()
                                                 if m == c.name.lower()):
            label = "Hybrid" if mode == "hybrid" else "On-site"
            return 1.0, f"{label} in {c.name}", None
    if job_c & want_countries:
        names = _names(job_c & want_countries)
        return (0.75 if cities else 0.95), f"In {names}", (f"Not in {', '.join(c.name for c in cities)}"
                                                         if cities else None)
    if not job_c and not loc.strip():
        return 0.4, None, "Location not stated"
    if "remote" in wanted_modes and mode is None and re.search(r"remote", loc) and not job_c:
        return 0.9, "Remote", None
    return None, None, None


def _names(codes: set[str]) -> str:
    special = {"US": "US", "GB": "UK", "AE": "UAE", "KR": "South Korea", "RU": "Russia", "IR": "Iran",
               "VN": "Vietnam", "TW": "Taiwan", "CZ": "Czechia", "TR": "Turkey", "NL": "Netherlands"}
    countries = vocab.places()["countries"]
    names = []
    for c in sorted(codes)[:4]:
        if c in special:
            names.append(special[c])
            continue
        options = [o for o in countries.get(c, []) if not o.startswith(("the ", "republic", "federal", "kingdom"))]
        names.append(min(options, key=len).title() if options else c)
    more = f" +{len(codes) - 4} more" if len(codes) > 4 else ""
    return ", ".join(names) + more


def seniority_fit(req: Requirements, job: Job) -> tuple[float, Optional[str], Optional[str]]:
    if not req.seniority:
        return 0.6, None, None
    if not job.seniority:
        return 0.6, None, None
    a, b = SENIORITY_ORDER.index(req.seniority), SENIORITY_ORDER.index(job.seniority)
    gap = abs(a - b)
    if gap == 0:
        return 1.0, f"{job.seniority.title()} level", None
    if gap == 1:
        return 0.7, None, f"Level: {job.seniority}"
    if b > a:
        return 0.2, None, f"Probably too senior ({job.seniority})"
    return 0.25, None, f"Probably too junior ({job.seniority})"


def salary_fit(req: Requirements, job: Job, fx: dict) -> tuple[Optional[float], Optional[str], Optional[str]]:
    if not req.salary_min:
        return 0.6, (_sal_label(job) if job.salary else None), None
    if not job.salary or not (job.salary.min or job.salary.max):
        return 0.5, None, "Salary not listed"
    want_annual = req.salary_min * {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}[req.salary_period]
    top = job.salary.annual(job.salary.max or job.salary.min)
    same = (job.salary.currency or "").upper() == (req.salary_currency or "").upper()
    if same:
        offered, wanted, approx = top, want_annual, ""
    else:
        offered = to_usd(top, job.salary.currency, fx)
        wanted = to_usd(want_annual, req.salary_currency, fx)
        approx = " (currency converted, approximate)"
        if offered is None or wanted is None:
            return 0.5, _sal_label(job), "Salary in another currency"
    if offered >= wanted:
        return 1.0, f"Pays {_sal_label(job)}{approx}", None
    if offered >= wanted * 0.85:
        return 0.5, None, f"Pays a bit less than you asked: {_sal_label(job)}{approx}"
    return None, None, None


def _sal_label(job: Job) -> str:
    s = job.salary
    if not s:
        return ""
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get((s.currency or "").upper(), (s.currency or "") + " ")

    def fmt(v: Optional[float]) -> str:
        if v is None:
            return ""
        if s.currency == "INR" and v >= 100_000:
            return f"{v / 100_000:.1f} lakh".replace(".0 ", " ")
        if v >= 1000:
            return f"{v / 1000:.0f}k"
        return f"{v:g}"
    rng = fmt(s.min) + (f"–{fmt(s.max)}" if s.max and s.max != s.min else "")
    per = {"year": "/year", "month": "/month", "hour": "/hour", "week": "/week", "day": "/day"}[s.period]
    return f"{sym}{rng}{per}"


def excluded(req: Requirements, job: Job) -> Optional[str]:
    head = f"{job.title} | {job.company} | {' '.join(job.tags)}".lower()
    body = job.description.lower()
    company = re.sub(r"[^a-z0-9]", "", job.company.lower())
    for word in req.exclude:
        w = word.lower()
        if _contains(head, w):
            return word
        if w in LIFESTYLE:
            # "no travel" means jobs that *require* travel, not every job mentioning a travel budget
            if re.search(LIFESTYLE[w], body):
                return word
            continue
        # industry words also inside company names ("crypto" -> "CryptoCorp"), not company names ("meta")
        if w in DOMAIN_WORDS and len(w) >= 4 and w.replace(" ", "") in company:
            return word
        if len(re.findall(r"(?<![\w+#])" + re.escape(w) + r"(?![\w+#])", body)) >= 3:
            return word
    return None


def score(req: Requirements, job: Job, fx: Optional[dict] = None,
          now: Optional[datetime] = None) -> Optional[Match]:
    """A Match with score and reasons, or None if the job fails a hard requirement."""
    fx = fx or {}
    if excluded(req, job):
        return None
    age = job.age_days(now)
    if req.posted_within_days and age is not None and age > req.posted_within_days:
        return None
    if req.employment_types and job.employment_type and job.employment_type not in req.employment_types:
        if not (job.employment_type == "contract" and "freelance" in req.employment_types):
            return None
    if req.visa_sponsorship and job.visa_sponsorship is False:
        return None

    reasons: list[str] = []
    warnings: list[str] = []

    t, label = title_score(req, job)
    if req.titles and t < 0.3 and not req.skills:
        return None
    if t >= 0.85 and label:
        reasons.append(f"Role matches “{label}”")
    elif t >= 0.4 and label:
        reasons.append(f"Role is close to “{label}”")

    have, nice = skill_hits(req, job)
    if req.skills:
        sk = min(1.0, len(have) / min(len(req.skills), 4))
    else:
        sk = 0.5
    if req.titles and t < 0.3:
        # not the role they asked for: only keep it when the skills fit very well
        if sk < 0.75:
            return None
        warnings.append("Different job title, but your skills fit")
    if have:
        reasons.append("Uses " + ", ".join(vocab.display(x) for x in have[:6]))
    if nice:
        reasons.append("Also mentions " + ", ".join(vocab.display(x) for x in nice[:4]))
        sk = min(1.0, sk + 0.1 * len(nice))

    pf, preason, pwarn = place_fit(req, job)
    if pf is None:
        return None
    if preason:
        reasons.append(preason)
    if pwarn:
        warnings.append(pwarn)

    sf, sreason, swarn = seniority_fit(req, job)
    if sreason:
        reasons.append(sreason)
    if swarn:
        warnings.append(swarn)

    pay, payreason, paywarn = salary_fit(req, job, fx)
    if pay is None:
        return None
    if payreason:
        reasons.append(payreason)
    if paywarn:
        warnings.append(paywarn)

    if age is None:
        fresh = 0.4
    else:
        fresh = 1.0 if age <= 7 else 0.8 if age <= 21 else 0.5 if age <= 60 else 0.2
        if age <= 3:
            reasons.append("Posted in the last 3 days")
        elif age > 60:
            warnings.append(f"Posted {int(age)} days ago")

    if req.employment_types and job.employment_type in req.employment_types:
        reasons.append(job.employment_type.replace("_", "-").capitalize())
    if req.visa_sponsorship and job.visa_sponsorship:
        reasons.append("Offers visa sponsorship")
    elif req.visa_sponsorship and job.visa_sponsorship is None:
        warnings.append("Visa sponsorship not mentioned")
    if req.keywords:
        kw = [k for k in req.keywords if _contains(f"{job.title} {job.company} {' '.join(job.tags)} "
                                                   f"{job.description[:3000]}".lower(), k)]
        if kw:
            reasons.append("Matches " + ", ".join(kw[:3]))
    if req.languages:
        need = [l for l in vocab.SPOKEN_LANGUAGES if l not in req.languages and l != "english" and
                re.search(r"\b(fluent|native|business[- ]level|proficien\w*|c1|c2)\b[^.\n]{0,40}\b" + l + r"\b|\b" +
                          l + r"\b[^.\n]{0,20}\b(required|is a must|mandatory|fluent|native)", job.description,
                          re.I)]
        if need:
            warnings.append(f"Asks for {need[0].title()}")
    if job.from_search_snippet:
        warnings.append("Details not read; open the link to check")

    other_lang = _title_language_conflict(req, job)
    if other_lang:
        warnings.append(f"Title asks for {vocab.display(other_lang)}")

    total = 35 * t + 25 * sk + 15 * pf + 10 * sf + 10 * pay + 5 * fresh - (12 if other_lang else 0)
    if req.keywords and any(r.startswith("Matches ") for r in reasons):
        total += 3
    if job.from_search_snippet:
        total -= 8
    total -= 6 * sum(1 for w in warnings if w.startswith(("Probably too", "Asks for")))
    return Match(job=job, score=round(max(0.0, min(100.0, total)), 1), reasons=reasons, warnings=warnings)


LANGUAGES = {"python", "java", "javascript", "typescript", "go", "rust", "c++", "c#", "ruby", "php", "kotlin",
             "swift", "scala", "elixir", "dart", ".net", "rails", "node.js", "react", "angular", "vue", "django",
             "laravel", "spring", "flutter", "android", "ios"}


def _title_language_conflict(req: Requirements, job: Job) -> Optional[str]:
    """'Backend Engineer (Ruby)' for someone who asked for Python -> 'ruby'."""
    mine = {s for s in req.skills + req.nice_skills if s in LANGUAGES}
    if not mine:
        return None
    in_title = [s for s in vocab.find_skills(job.title) if s in LANGUAGES]
    if in_title and not (set(in_title) & mine):
        return in_title[0]
    return None


def _same_role(m: Match) -> str:
    j = m.job
    title = re.sub(r"\s*[-–|,(].*$", "", j.title.lower()).strip()
    return f"{re.sub(r'[^a-z0-9]', '', j.company.lower())}|{title}"


def rank(req: Requirements, jobs: list[Job], fx: Optional[dict] = None, limit: int = 25) -> tuple[list[Match], int]:
    now = datetime.now(timezone.utc)
    matches = [m for m in (score(req, j, fx, now) for j in jobs) if m is not None]
    matches.sort(key=lambda m: (m.score, m.job.posted_at.timestamp() if m.job.posted_at else 0), reverse=True)
    # one result per company + role (companies often post the same job once per country),
    # and at most two results per company near the top, so one employer can't fill the list
    out: list[Match] = []
    seen: dict[str, Match] = {}
    per_company: dict[str, int] = {}
    later: list[Match] = []
    for m in matches:
        key = _same_role(m)
        if key in seen:
            first = seen[key]
            if len(first.job.also_on) < 6 and m.job.url != first.job.url:
                first.job.also_on.append({"source": m.job.location or m.job.source_name, "url": m.job.url})
            continue
        seen[key] = m
        company = re.sub(r"[^a-z0-9]", "", m.job.company.lower())
        if company and per_company.get(company, 0) >= 2:
            later.append(m)
            continue
        per_company[company] = per_company.get(company, 0) + 1
        out.append(m)
    out += later
    return out[:limit], len(seen)
