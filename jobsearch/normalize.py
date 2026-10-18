"""Turn the different shapes sources use into the same clean fields."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Optional

from lxml import html as lxml_html

from . import vocab
from .models import Salary

_TAGS = re.compile(r"<[^>]+>")


def html_to_text(s: Optional[str], limit: int = 12000) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    if "<" in s:
        try:
            doc = lxml_html.fromstring(s)
            for bad in doc.xpath("//script|//style"):
                bad.drop_tree()
            for br in doc.xpath("//br|//p|//li|//h1|//h2|//h3|//h4|//div"):
                br.tail = "\n" + (br.tail or "")
            s = doc.text_content()
        except Exception:  # noqa: BLE001 - fall back to a crude strip on broken HTML
            s = _TAGS.sub(" ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()[:limit]


def parse_date(value: Any) -> Optional[datetime]:
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        s = str(value).strip()
        if re.fullmatch(r"\d{9,13}", s):
            return parse_date(int(s))
        s = re.sub(r"\s*UTC$", "+00:00", s).replace("Z", "+00:00")
        if re.match(r"\d{4}-\d{2}-\d{2} \d", s):
            s = s.replace(" ", "T", 1).replace(" +", "+")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            s += "T00:00:00+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def work_mode(*texts: Optional[str], remote_flag: Optional[bool] = None) -> Optional[str]:
    blob = " ".join(t for t in texts if t).lower()
    if re.search(r"\bhybrid\b", blob):
        return "hybrid"
    if remote_flag or re.search(r"\b(remote|work from home|wfh|telecommute|work from anywhere|"
                                r"fully distributed)\b", blob):
        return "remote"
    if remote_flag is False or re.search(r"\b(on-?site|in-?office|in office)\b", blob):
        return "onsite"
    return None


def countries_in(text: Optional[str]) -> list[str]:
    """ISO codes of countries named (or implied by a known city or region) in a location string."""
    if not text:
        return []
    found: list[str] = []
    names = vocab.country_names()
    data = vocab.places()
    low = text.lower()
    for m in vocab.alias_pattern(list(names)).finditer(low):
        code = names[m.group(1)]
        if code not in found:
            found.append(code)
    if re.search(r"\b(US|USA)\b", text) and "US" not in found:
        found.append("US")
    if re.search(r"\bUK\b", text) and "GB" not in found:
        found.append("GB")
    # "City, ST" US state codes
    if re.search(r",\s*(A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|"
                 r"S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b", text) and "US" not in found:
        found.append("US")
    if not found:
        for m in _city_re().finditer(low):
            word = data["city_aliases"].get(m.group(1), m.group(1))
            code = data["cities"].get(word)
            if code and code not in found and word not in data["ambiguous"]:
                found.append(code)
                break
    return found


_CITY: Optional[re.Pattern] = None


def _city_re() -> re.Pattern:
    global _CITY
    if _CITY is None:
        d = vocab.places()
        _CITY = vocab.alias_pattern(list(d["cities"]) + list(d["city_aliases"]))
    return _CITY


def remote_regions(text: Optional[str]) -> list[str]:
    """For a remote job, which countries applicants may live in. [] = anywhere / unknown."""
    if not text:
        return []
    low = text.lower()
    if any(w in low for w in vocab.WORLDWIDE_WORDS):
        return []
    out: set[str] = set(countries_in(text))
    regions = vocab.region_countries()
    for m in vocab.alias_pattern(list(regions)).finditer(low):
        word = m.group(1)
        if word == "eu" and not re.search(r"\bEU\b", text):
            continue
        out |= regions[word]
    return sorted(out)


def employment_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower().replace("_", " ").replace("-", " ")
    for kind, words in (("internship", ["intern", "internship", "werkstudent", "working student"]),
                        ("part_time", ["part time", "parttime"]),
                        ("contract", ["contract", "contractor", "b2b"]), ("freelance", ["freelance", "freelancer"]),
                        ("temporary", ["temporary", "temp", "fixed term", "seasonal"]),
                        ("full_time", ["full time", "fulltime", "permanent", "regular", "employee"])):
        if any(re.search(r"\b" + re.escape(w) + r"\b", v) for w in words):
            return kind
    return None


def seniority_from_title(title: str) -> Optional[str]:
    t = title.lower()
    rules = [("intern", r"\b(intern|internship|trainee|apprentice|werkstudent|working student)\b"),
             ("executive", r"\b(chief|ceo|cto|cfo|coo|cmo|cpo|ciso)\b"),
             ("director", r"\b(director|vp|vice president|head of)\b"),
             ("principal", r"\b(principal|staff|distinguished|fellow)\b"),
             ("lead", r"\b(lead|team lead|tech lead)\b"),
             ("manager", r"\b(manager)\b"),
             ("senior", r"\b(senior|sr\.?|expert)\b|\b(iii|iv)\b"),
             ("junior", r"\b(junior|jr\.?|entry[- ]level|graduate|new grad|associate)\b|\b(i)\b$"),
             ("mid", r"\b(mid[- ]level|intermediate|ii)\b")]
    for level, pat in rules:
        if re.search(pat, t):
            if level == "manager" and re.search(r"\b(account|product|project|program|community|social media|"
                                                r"marketing|case|office|success)\s+manager\b", t):
                continue  # these are job names, not people managers
            return level
    return None


_SAL = re.compile(r"(?P<cur>[$€£₹]|usd|eur|gbp|inr|cad|aud|chf)?\s*(?P<a>\d[\d,.]*)\s*(?P<ka>[kKmM])?\s*"
                  r"(?:-|–|—|to)\s*(?P<cur2>[$€£₹])?\s*(?P<b>\d[\d,.]*)\s*(?P<kb>[kKmM])?", re.I)


def salary_from_text(text: Optional[str], default_currency: Optional[str] = None) -> Optional[Salary]:
    """Read '$170k - $200k', '€60,000–75,000 a year', '$40 - $55 / hour'."""
    if not text:
        return None
    m = _SAL.search(text)
    single = None
    if not m:
        single = re.search(r"(?P<cur>[$€£₹])\s*(?P<a>\d[\d,.]*)\s*(?P<ka>[kK])?", text)
        if not single:
            return None

    def num(v: str, k: Optional[str]) -> Optional[float]:
        v = v.rstrip(".,")
        if re.fullmatch(r"\d{1,3}([,.]\d{3})+", v):
            v = re.sub(r"[,.]", "", v)
        else:
            v = v.replace(",", "")
        try:
            n = float(v)
        except ValueError:
            return None
        if k and k.lower() == "k":
            n *= 1000
        elif k and k.lower() == "m":
            n *= 1_000_000
        return n

    g = (m or single).groupdict()
    a = num(g["a"], g.get("ka") or g.get("kb"))
    b = num(g["b"], g.get("kb") or g.get("ka")) if m else None
    cur_raw = (g.get("cur") or g.get("cur2") or "").lower()
    currency = vocab.CURRENCY_SYMBOLS.get(cur_raw) or default_currency
    if a is None or not currency:
        return None
    low = text.lower()
    period = "year"
    if re.search(r"(/|per|an|a)\s*(hour|hr)\b|hourly", low):
        period = "hour"
    elif re.search(r"(/|per|a)\s*month|monthly", low):
        period = "month"
    elif a < 300 and (b is None or b < 300):
        period = "hour"
    if b is not None and b < a:
        a, b = b, a
    return Salary(min=a, max=b, currency=currency.upper(), period=period, text=text.strip()[:80])


def to_usd(amount: Optional[float], currency: Optional[str], overrides: Optional[dict] = None) -> Optional[float]:
    if amount is None or not currency:
        return None
    rates = dict(vocab.FX_TO_USD)
    if overrides:
        rates.update(overrides)
    rate = rates.get(currency.upper())
    return amount * rate if rate else None
