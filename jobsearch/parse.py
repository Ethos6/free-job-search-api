"""Built-in understanding of a person's job requirements, written in their own words.

No AI needed: this works with word lists and patterns. It reads roles, skills, places,
remote/hybrid/on-site, seniority, years of experience, salary, job type, visa needs,
how recent the posting should be, spoken languages, industries to prefer and things to
avoid ("no crypto", "not interested in sales"). An optional AI model (llm.py) can refine it.
"""
from __future__ import annotations

import re
from typing import Optional

from . import vocab
from .models import Place, Requirements

NEGATIVE = re.compile(
    r"\b(no|not|don'?t|do not|doesn'?t|won'?t|can'?t|cannot|avoid|avoiding|exclude|excluding|except|never|"
    r"without|nothing in|hate|dislike|rather not|not interested|no interest|uninterested|stay away|skip|"
    r"none of)\b", re.I)
# negative words that don't mean "avoid": "I don't mind travel", "no problem relocating"
NOT_NEGATIVE = re.compile(r"\b(don'?t mind|do not mind|wouldn'?t mind|no problem( with)?|not a problem|"
                          r"doesn'?t matter|does not matter|no preference|not picky|no matter|not fussy|"
                          r"no objection)\b", re.I)
NICE = re.compile(r"\b(nice to have|nice-to-have|bonus|ideally|preferably|preferred|plus|optional|"
                  r"would be great|good to have|a plus)\b", re.I)
DOMAINS = ["fintech", "healthtech", "healthcare", "edtech", "education", "climate", "cleantech", "climate tech",
           "renewable energy", "energy", "crypto", "cryptocurrency", "blockchain", "web3", "defi", "nft", "gambling",
           "betting", "casino", "gaming", "video games", "ecommerce", "e-commerce", "retail", "saas", "b2b", "b2c",
           "startup", "startups", "early stage", "scaleup", "enterprise", "big tech", "faang", "government",
           "public sector", "defense", "defence", "military", "weapons", "nonprofit", "non-profit", "ngo",
           "charity", "social impact", "cybersecurity", "automotive", "aerospace", "space", "biotech",
           "pharma", "pharmaceutical", "medtech", "insurance", "insurtech", "banking", "finance", "consulting",
           "agency", "agencies", "outsourcing", "media", "advertising", "adtech", "marketing agency", "travel",
           "hospitality", "logistics", "manufacturing", "real estate", "proptech", "legaltech", "hr tech",
           "food", "foodtech", "agriculture", "agritech", "tobacco", "alcohol", "oil and gas", "mining",
           "telecom", "social media", "marketplace", "open source", "robotics", "semiconductors", "hardware",
           "construction", "nuclear", "dating", "adult", "mlm", "network marketing", "call center", "bpo"]
_DOMAIN_RE = vocab.alias_pattern(DOMAINS)

WORK_MODE_WORDS = {
    "remote": r"\b(remote|remotely|wfh|work from home|working from home|home office|home-based|telecommut\w*|"
              r"distributed team|fully distributed|work from anywhere|anywhere in the world)\b",
    "hybrid": r"\b(hybrid|flexible office|partly remote|partially remote|few days in office)\b",
    "onsite": r"\b(on-?site|in-?office|in office|in person|in-person|office based|office-based|at the office|"
              r"relocate|relocation)\b",
}
REMOTE_ONLY = re.compile(r"\b(fully remote|remote only|remote-only|100% remote|only remote|full remote|"
                         r"completely remote|remote first|remote-first)\b", re.I)
HOME_COUNTRY = re.compile(r"\b(?:i(?:'m| am)? (?:based|located|living|currently) in|i live in|based in|"
                          r"located in|living in|resident of|i(?:'m| am) from|citizen of|i reside in)\s+"
                          r"([A-Za-z .'-]{2,40})", re.I)
YEARS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?|yoe)\b", re.I)
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
POSTED = [
    (re.compile(r"\b(today|last 24 hours|past 24 hours|past day|last day)\b", re.I), 1),
    (re.compile(r"\b(?:last|past|within)\s+(\d{1,3})\s+days?\b", re.I), None),
    (re.compile(r"\b(?:last|past|within( a| the)?|this)\s+week\b", re.I), 7),
    (re.compile(r"\b(?:last|past|within)\s+(\d{1,2})\s+weeks?\b", re.I), "weeks"),
    (re.compile(r"\b(?:last|past|within( a| the)?|this)\s+month\b", re.I), 30),
    (re.compile(r"\b(recently posted|new (?:postings?|listings?|openings)|(?:fresh|recent|latest|new) (?:jobs|postings|"
                r"listings|openings|job ads|vacancies)( only)?)\b", re.I), 14),
]
VISA_NEED = re.compile(r"\b(need|needs|require|requires|requiring|looking for|want|offer\w*|provid\w*)\b"
                       r"[^.;\n]{0,30}\b(visa|sponsorship|sponsor|work permit|h-?1b|blue card)\b|"
                       r"\b(visa|h-?1b|blue card) sponsorship\b", re.I)
VISA_NO_NEED = re.compile(r"\b(don'?t|do not|no|won'?t|will not)\b[^.;\n]{0,20}\b(need|require)\b[^.;\n]{0,20}"
                          r"\b(visa|sponsorship|sponsor)\b|\b(have|hold|got|with)\b[^.;\n]{0,20}\b(work permit|"
                          r"blue card|"
                          r"work authori[sz]ation|green card|citizenship|right to work|visa)\b|\b(citizen|"
                          r"permanent resident)\b", re.I)
LANG_RE = re.compile(r"\b(?:speak|speaks|speaking|fluent in|native|fluent|languages?:?|know|proficient in)\s+"
                     r"((?:[A-Za-z]+(?:,\s*|\s+and\s+|\s*&\s*|\s+or\s+|\s+)){0,4}[A-Za-z]+)", re.I)

COUNTRY_CURRENCY = {"US": "USD", "GB": "GBP", "IN": "INR", "CA": "CAD", "AU": "AUD", "NZ": "NZD", "CH": "CHF",
                    "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "BR": "BRL", "MX": "MXN", "SG": "SGD",
                    "AE": "AED", "ZA": "ZAR", "JP": "JPY", "HK": "HKD", "CZ": "CZK", "IL": "ILS", "TR": "TRY",
                    "KR": "KRW", "PH": "PHP", "NG": "NGN", "KE": "KES", "EG": "EGP", "PK": "PKR", "ID": "IDR",
                    "MY": "MYR", "TH": "THB", "VN": "VND", "HU": "HUF", "RO": "RON", "SA": "SAR"}
EUROZONE = {"AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PT",
            "SK", "SI", "ES"}

_MONEY = re.compile(
    r"(?P<cur1>us\$|c\$|a\$|s\$|r\$|\$|€|£|₹|¥|₪|₺|₩|₱|₦|zł|\b(?:usd|eur|gbp|inr|cad|aud|chf|sek|nok|dkk|pln|brl|"
    r"mxn|sgd|aed|zar|nzd|hkd|czk|ils|try|krw|php|ngn|kes|egp|pkr|idr|myr|thb|vnd|huf|ron|sar|jpy|rs\.?)\b)?\s*"
    r"(?P<num>\d{1,3}(?:[,. ]\d{3})+|\d+(?:\.\d+)?)\s*(?P<mult>k|m|mn|million|thousand|lpa|lakhs?|lacs?|cr|crores?)?\b"
    r"(?:\s*(?:-|–|to)\s*(?:us\$|\$|€|£|₹)?\s*\d+(?:[.,]\d+)?\s*(?P<mult2>k|m|lpa|lakhs?)?)?"
    r"\s*(?P<cur2>usd|eur|euros?|gbp|inr|rupees|cad|aud|chf|sek|nok|dkk|pln|brl|mxn|sgd|aed|dirhams?|zar|nzd|"
    r"hkd|czk|ils|jpy)?\b"
    r"\s*(?P<per>(?:per|a|an|/|each)\s*(?:year|yr|annum|month|mo|week|wk|day|hour|hr)\b|annually|yearly|monthly|"
    r"weekly|daily|hourly|p\.?a\.?|pa\b)?", re.I)
SALARY_CONTEXT = re.compile(r"\b(salary|pay|paid|compensation|comp|ctc|package|earn|earning|income|rate|"
                            r"at least|minimum|min\.?|more than|over|above|upwards of|starting|base|lpa|per hour|"
                            r"/hour|/hr|hourly|per month|a year|per year|k\b)", re.I)


def parse(text: str) -> Requirements:
    text = (text or "").strip()
    req = Requirements(text=text)
    if not text:
        return req
    clauses = _clauses(text)
    # In each sentence, the short list right after a negative word is to avoid; the rest is wanted.
    pos_parts, negative = [], []
    for c in clauses:
        keep, avoid = _split_negation(c)
        pos_parts.append(keep)
        if avoid:
            negative.append(avoid)
    positive = " . ".join(p for p in pos_parts if p.strip())

    # roles and skills
    req.titles = vocab.find_roles(positive) or _skill_titles(positive) or _free_titles(positive)
    nice_text = " . ".join(c for c in pos_parts if NICE.search(c))
    nice = vocab.find_skills(nice_text) if nice_text else []
    req.skills = [s for s in vocab.find_skills(positive) if s not in nice]
    req.nice_skills = nice
    req.keywords = _unique(m.group(1).lower() for m in _DOMAIN_RE.finditer(positive))

    # things to avoid
    excl: list[str] = []
    for part in negative:
        if re.search(r"\b(sponsor|visa)\b", part, re.I) and VISA_NO_NEED.search(text):
            continue  # "I don't need sponsorship" is not an exclusion
        excl += [m.group(1).lower() for m in _DOMAIN_RE.finditer(part)]
        pat, _ = vocab.role_lookup()
        excl += [m.group(1).lower() for m in pat.finditer(part)]
        excl += [w.lower() for w in re.findall(r"\b(sales|cold calling|commission[- ]only|on-?call|night shifts?|"
                                               r"weekends?|travel|relocation|agencies|agency)\b", part, re.I)]
        excl += [s for s in vocab.find_skills(part)]
        excl += _named_companies(part)
    req.exclude = _unique(e for e in excl if e and e not in ("remote",))
    req.titles = [t for t in req.titles if t not in req.exclude]
    req.skills = [s for s in req.skills if s not in req.exclude]

    # where
    home = _home_country(text)
    places = _places(pos_parts)
    excluded_places = _places(negative)
    if home:
        req.home_country = home.country
        if not any(p.country == home.country for p in places):
            places.append(home)
    req.places = [p for p in places if p.country not in {x.country for x in excluded_places} or p.kind != "country"]
    req.work_modes = _work_modes(text)
    if req.work_modes == ["remote"] and not REMOTE_ONLY.search(text) and any(p.kind == "city" for p in req.places):
        # "London or remote UK", "Berlin, remote is fine": a city named next to remote means both are fine
        for p in (p for p in req.places if p.kind == "city"):
            city = re.escape(p.name)
            near = (rf"\b{city}\b\W+(?:\w+\W+){{0,4}}?(?:or|/|and|also)\W+(?:\w+\W+){{0,3}}?remote|"
                    rf"remote\W+(?:\w+\W+){{0,4}}?(?:or|/|and|also)\W+(?:\w+\W+){{0,3}}?{city}\b")
            if re.search(near, text, re.I):
                req.work_modes = ["remote", "hybrid", "onsite"]
                break

    # level
    req.years_experience = _years(text)
    req.seniority = _seniority(positive, req.years_experience)

    # money
    countries = [p.country for p in req.places if p.country]
    sal = _salary(text, (home.country if home else None) or (countries[0] if countries else None))
    if sal:
        req.salary_min, req.salary_currency, req.salary_period = sal

    # other
    req.employment_types = _employment(positive)
    if VISA_NO_NEED.search(text):
        req.visa_sponsorship = None
    elif VISA_NEED.search(text):
        req.visa_sponsorship = True
    req.posted_within_days = _posted(text)
    req.languages = _languages(text)
    return req


# -- helpers --------------------------------------------------------------------------------------

def _unique(items) -> list:
    out = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[\n;.!?]+|\s+-\s+|\bbut\b|\bhowever\b|\balthough\b", text, flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def _split_negation(clause: str) -> tuple[str, str]:
    """('wanted part', 'part to avoid'). "Python dev in Austin, no crypto, gambling or adult companies, remote"
    -> avoid "crypto, gambling or adult companies", keep the rest."""
    masked = NOT_NEGATIVE.sub(" ok ", clause)
    m = NEGATIVE.search(masked)
    if not m:
        return masked, ""
    after = masked[m.end():]
    pieces = re.split(r",|\band i\b|\bi'?m\b|\bi am\b|\blooking\b|\bwant\b|\bprefer", after, flags=re.I)
    avoid = [pieces[0]]
    rest: list[str] = []
    for i, piece in enumerate(pieces[1:], start=1):
        words = piece.split()
        positive_info = (vocab.find_roles(piece) or re.search(r"\d", piece) or
                         re.search(r"\b(remote|hybrid|on-?site|office)\b", piece, re.I) or
                         _places([piece]))
        if words and len(words) <= 5 and not positive_info and (_DOMAIN_RE.search(piece) or
                                                                 _named_companies(piece)):
            avoid.append(piece)
        else:
            rest = pieces[i:]
            break
    return masked[:m.start()] + " , " + " , ".join(rest), " , ".join(avoid)


def _skill_titles(text: str) -> list[str]:
    """'Go engineer', 'Python developer', 'Salesforce consultant' -> a role plus the literal title."""
    pat, canon = vocab.skill_lookup()
    out = []
    for m in re.finditer(pat.pattern[:-len(r"(?![\w+#])")] + r"\s+(engineer|developer|programmer|dev|consultant|"
                         r"specialist|administrator|architect|analyst|designer)s?\b", text, re.I):
        skill = canon.get(m.group(1).lower(), m.group(1).lower())
        kind = m.group(2).lower()
        role = {"consultant": "consultant", "analyst": "data analyst", "designer": "product designer",
                "administrator": "it support", "architect": "solutions architect"}.get(kind, "software engineer")
        out += [f"{skill} {kind if kind != 'dev' else 'developer'}", role]
    return _unique(out)


def _free_titles(text: str) -> list[str]:
    pats = [r"\b(?:as an?|looking for an?|want an?|seeking an?|searching for an?|job as an?|work as an?|"
            r"position as an?|role as an?|i am an?|i'm an?|currently an?)\s+([a-z][a-z/&+ -]{2,40}?)"
            r"(?=\s+(?:role|job|position|opening|work|in|at|with|for|and|or|,|$)|[,.;]|$)",
            r"\b([a-z][a-z/&+ -]{2,30}?)\s+(?:role|roles|job|jobs|position|positions|openings)\b"]
    found = []
    for p in pats:
        for m in re.finditer(p, text, re.I):
            t = re.sub(r"\b(senior|junior|lead|remote|new|good|great|full[- ]time|part[- ]time|a|an|the|some|"
                       r"entry[- ]level|mid[- ]level)\b", " ", m.group(1), flags=re.I)
            t = re.sub(r"\s+", " ", t).strip(" -/").lower()
            t = re.sub(r"^(i'?m |i am |i )?(looking for|searching for|seeking|want|wanting|need|find|get|"
                       r"apply for|work as|working as)\s+", "", t).strip()
            if 2 < len(t) <= 40 and t not in ("job", "jobs", "role", "work", "remote", "any") and \
                    not re.fullmatch(r"(looking|searching|seeking|want|need|find|get)( \w+)?", t):
                found.append(t)
    return _unique(found)[:3]


def _named_companies(part: str) -> list[str]:
    """Capitalised names after 'like', 'such as', or in lists in an exclusion ("no Amazon or Meta")."""
    names = re.findall(r"\b([A-Z][A-Za-z0-9&.\-]{1,30}(?:\s[A-Z][A-Za-z0-9&.\-]{1,30}){0,2})\b", part)
    stop = {"I", "I'm", "No", "Not", "Don't", "Please", "Also", "And", "Or", "The", "My", "We", "Any", "Avoid",
            "Remote", "Hybrid", "Thanks", "Jobs", "Job", "Roles", "Role", "Companies", "Company", "Except"}
    out = []
    for n in names:
        if n in stop or n.lower() in vocab.country_names() or n.lower() in vocab.places()["cities"]:
            continue
        if vocab.find_skills(n) or vocab.find_roles(n):
            continue
        out.append(n.lower())
    return out


def _home_country(text: str) -> Optional[Place]:
    m = HOME_COUNTRY.search(text)
    if not m:
        return None
    for p in _places([m.group(1)]):
        if p.country:
            return Place(name=p.name, country=p.country, kind=p.kind)
    return None


def _places(texts: list[str]) -> list[Place]:
    data = vocab.places()
    countries = vocab.country_names()
    regions = vocab.region_countries()
    ambiguous = set(data["ambiguous"])
    city_pat = _city_pattern()
    country_pat = _country_pattern()
    region_pat = vocab.alias_pattern(list(regions))
    found: list[Place] = []
    for text in texts:
        hits: list[tuple[int, Place]] = []
        for m in country_pat.finditer(text):
            word = m.group(1).lower()
            if word in ("america",) and re.search(r"\b(north|south|latin) america", text, re.I):
                continue
            hits.append((m.start(), Place(name=m.group(1), country=countries[word], kind="country")))
        for m in re.finditer(r"\b(US|USA|U\.S\.)(?![\w.])", text):
            hits.append((m.start(), Place(name="United States", country="US", kind="country")))
        for m in region_pat.finditer(text):
            word = m.group(1).lower()
            if word in ("eu", "sea") and not m.group(1).isupper():
                continue
            hits.append((m.start(), Place(name=m.group(1), country=None, kind="continent")))
        for m in city_pat.finditer(text):
            raw = m.group(1)
            word = raw.lower()
            name = data["city_aliases"].get(word, word)
            if name not in data["cities"]:
                continue
            if word in ("la", "dc", "sf", "nyc") and not raw.isupper():
                continue
            if word in ambiguous or len(word) <= 3:
                # common words that are also cities count only when written like a place: "in Nice", "Bath, UK"
                before = text[max(0, m.start() - 8):m.start()]
                after = text[m.end():m.end() + 12]
                if not raw[0].isupper() or re.match(r"\s+to have", after, re.I) or not (
                        re.search(r"\b(in|to|at|near|from|around|or|and)\s+$|[,/]\s*$", before, re.I) or
                        re.match(r"\s*,\s*[A-Z]", after)):
                    continue
            hits.append((m.start(), Place(name=name.title(), country=data["cities"][name], kind="city")))
        found += [p for _, p in sorted(hits, key=lambda h: h[0])]
    uniq: list[Place] = []
    seen = set()
    for p in found:
        key = ("country", p.country) if p.kind == "country" else (p.name.lower(), p.country)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


_COUNTRY_RE: Optional[re.Pattern] = None


def _country_pattern() -> re.Pattern:
    global _COUNTRY_RE
    if _COUNTRY_RE is None:
        _COUNTRY_RE = vocab.alias_pattern(list(vocab.country_names()))
    return _COUNTRY_RE


_CITY_RE: Optional[re.Pattern] = None


def _city_pattern() -> re.Pattern:
    global _CITY_RE
    if _CITY_RE is None:
        data = vocab.places()
        _CITY_RE = vocab.alias_pattern(list(data["cities"]) + list(data["city_aliases"]))
    return _CITY_RE


def _work_modes(text: str) -> list:
    for m in REMOTE_ONLY.finditer(text):
        if not re.search(r"\b(not|no|n't|never)\s+(\w+\s+)?$", text[max(0, m.start() - 15):m.start()], re.I):
            return ["remote"]
    modes = []
    for mode, pat in WORK_MODE_WORDS.items():
        for m in re.finditer(pat, text, re.I):
            before = text[max(0, m.start() - 25):m.start()]
            if re.search(r"\b(no|not|don'?t want|avoid|never)\b[^.;\n]*$", before, re.I):
                break
            if mode == "onsite" and m.group(1).lower().startswith("reloc") and \
                    re.search(r"\b(no|not|won'?t|don'?t)\b", before, re.I):
                break
            modes.append(mode)
            break
    if modes == ["remote"] and re.search(r"\bor\b[^.;\n]{0,25}\b(office|on-?site)\b", text, re.I):
        modes.append("onsite")
    return modes


def _years(text: str) -> Optional[float]:
    best = None
    for m in YEARS.finditer(text):
        ctx = text[max(0, m.start() - 40):m.end() + 40].lower()
        after = text[m.end():m.end() + 16].lower()
        if re.search(r"\b(old|age|aged|ago|warranty|contract of)\b", ctx) or \
                re.match(r"[\s-]*(-?old|contract|visa|plan|lease|term|degree|program|course|gap)", after):
            continue
        val = float(m.group(1))
        if val <= 50:
            best = val if best is None else max(best, val)
    if best is None:
        m = re.search(r"\b(" + "|".join(WORD_NUMBERS) + r")\s+(?:years?|yrs?)\b", text, re.I)
        if m:
            best = float(WORD_NUMBERS[m.group(1).lower()])
    return best


def _seniority(text: str, years: Optional[float]):
    """The level the person names first ("junior developer who wants to grow into senior" -> junior)."""
    lower = text.lower()
    hits: list[tuple[int, str]] = []
    for level, words in vocab.SENIORITY_WORDS.items():
        for w in words:
            for m in re.finditer(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", lower):
                if level == "manager" and not re.search(r"\b(engineering|product|people|team|general|store|"
                                                        r"operations|project|program) manager|head of",
                                                        lower[max(0, m.start() - 15):m.end() + 5]):
                    continue
                if level == "lead" and not re.search(r"\b(tech|team|technical) lead\b|\blead (engineer|"
                                                     r"developer|designer|data|role|position)",
                                                     lower[max(0, m.start() - 10):m.end() + 15]):
                    continue
                if level == "principal" and w == "architect":
                    continue
                if level == "junior" and w == "associate" and not re.search(
                        r"\bassociate (level|role|position)", lower[m.start():m.end() + 12]):
                    continue
                if level == "executive" and w == "executive" and re.search(
                        r"\b(account|sales|marketing|accounts) executive", lower[max(0, m.start() - 12):m.end()]):
                    continue
                if level == "intern" and re.search(r"\binternal|international", lower[m.start():m.end() + 6]):
                    continue
                hits.append((m.start(), level))
                break
    if hits:
        return min(hits)[1]
    if years is None:
        return None
    if years < 1:
        return "intern" if re.search(r"\b(student|intern)", lower) else "junior"
    if years < 3:
        return "junior"
    if years < 5:
        return "mid"
    return "senior"


def _to_number(num: str) -> Optional[float]:
    s = num.strip()
    if re.fullmatch(r"\d{1,3}(?:[,. ]\d{3})+", s):
        s = re.sub(r"[,. ]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _salary(text: str, country: Optional[str]):
    best = None
    for m in _MONEY.finditer(text):
        num = _to_number(m.group("num"))
        if num is None or num == 0:
            continue
        cur_raw = (m.group("cur1") or m.group("cur2") or "").lower().strip()
        mult = (m.group("mult") or m.group("mult2") or "").lower()
        if not cur_raw and not mult and 1900 <= num <= 2100 and float(num).is_integer():
            continue  # a year, not a salary
        per = (m.group("per") or "").lower()
        window = text[max(0, m.start() - 45):m.end() + 15]
        if not (cur_raw or mult in ("k", "lpa", "lakh", "lakhs", "lac", "lacs") or SALARY_CONTEXT.search(window)):
            continue
        if re.search(r"\b(years?|yrs?|employees|people|users|team|days?|weeks?|hours a week|hrs a week|%)\b",
                     text[m.end():m.end() + 12], re.I) and not per:
            continue
        if not cur_raw and not mult and num < 1000 and "hour" not in per and "hr" not in per:
            continue
        value = num
        if mult == "k" or mult == "thousand":
            value *= 1_000
        elif mult in ("m", "mn", "million"):
            value *= 1_000_000
        elif mult in ("lpa", "lakh", "lakhs", "lac", "lacs"):
            value *= 100_000
            cur_raw = cur_raw or "inr"
        elif mult in ("cr", "crore", "crores"):
            value *= 10_000_000
            cur_raw = cur_raw or "inr"
        currency = vocab.CURRENCY_SYMBOLS.get(cur_raw.rstrip("."), None) if cur_raw else None
        if cur_raw in ("euro", "euros"):
            currency = "EUR"
        if not currency:
            currency = _currency_for(country) or "USD"
        period = "year"
        if re.search(r"hour|hr|hourly", per):
            period = "hour"
        elif re.search(r"month|mo\b|monthly", per):
            period = "month"
        elif re.search(r"week|wk|weekly", per):
            period = "week"
        elif re.search(r"day|daily", per):
            period = "day"
        elif not per and value < 300 and not mult:
            period = "hour"
        cand = (value, currency, period)
        if best is None or re.search(r"\b(at least|minimum|min|more than|over|above|starting|upwards)\b",
                                     window, re.I):
            best = cand
    return best


def _currency_for(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    if country in EUROZONE:
        return "EUR"
    return COUNTRY_CURRENCY.get(country)


def _employment(text: str) -> list:
    out = []
    for kind, words in vocab.EMPLOYMENT_WORDS.items():
        for w in words:
            if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text, re.I):
                if kind == "internship" and w == "intern" and re.search(r"\binternal\b", text, re.I):
                    continue
                if kind == "contract" and re.search(r"\b(permanent|full[- ]time)\b", text, re.I) and w == "contract" \
                        and re.search(r"\bno contract|not contract", text, re.I):
                    continue
                out.append(kind)
                break
    return out


def _posted(text: str) -> Optional[int]:
    for pat, days in POSTED:
        m = pat.search(text)
        if not m:
            continue
        if days is None:
            return max(1, min(365, int(m.group(1))))
        if days == "weeks":
            return int(m.group(1)) * 7
        return int(days)
    return None


def _languages(text: str) -> list[str]:
    out = []
    for m in LANG_RE.finditer(text):
        for w in re.split(r",\s*|\s+and\s+|\s*&\s*|\s+or\s+|\s+", m.group(1)):
            if w.lower() in vocab.SPOKEN_LANGUAGES:
                out.append(w.lower())
    for lang in vocab.SPOKEN_LANGUAGES:
        if re.search(r"\b" + lang + r"\s+(speaker|speaking|native|fluent|\(native\)|\(fluent\)|c1|c2|b2)\b",
                     text, re.I):
            out.append(lang)
    return _unique(out)
