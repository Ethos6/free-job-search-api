"""Regenerate jobsearch/data/places.json from open datasets.

Countries: ISO 3166 names (pycountry). Cities and continents: GeoNames (CC BY 4.0),
via the geonamescache package. Run:  pip install pycountry geonamescache && python scripts/build_places.py
"""
import json
import unicodedata
from pathlib import Path

import geonamescache
import pycountry

OUT = Path(__file__).resolve().parent.parent / "jobsearch" / "data" / "places.json"
MIN_POPULATION = 300_000

# Extra names people commonly use for countries.
COUNTRY_ALIASES = {
    "US": ["usa", "u.s.", "u.s.a.", "united states of america", "america", "the us", "the states"],
    "GB": ["uk", "u.k.", "united kingdom", "great britain", "britain", "england", "scotland", "wales",
           "northern ireland"],
    "AE": ["uae", "u.a.e.", "emirates"],
    "KR": ["south korea", "korea"],
    "KP": ["north korea"],
    "RU": ["russia"],
    "IR": ["iran"],
    "VN": ["vietnam", "viet nam"],
    "TW": ["taiwan"],
    "CZ": ["czech republic", "czechia"],
    "NL": ["holland", "the netherlands"],
    "BO": ["bolivia"],
    "VE": ["venezuela"],
    "TZ": ["tanzania"],
    "SY": ["syria"],
    "LA": ["laos"],
    "MD": ["moldova"],
    "TR": ["turkey", "turkiye", "türkiye"],
    "CD": ["drc", "dr congo"],
    "CI": ["ivory coast", "cote d'ivoire"],
    "PS": ["palestine"],
    "BN": ["brunei"],
    "MK": ["north macedonia", "macedonia"],
    "VA": ["vatican"],
    "FM": ["micronesia"],
}

# City names people use that differ from GeoNames' main name.
CITY_ALIASES = {
    "bengaluru": ["bangalore"], "mumbai": ["bombay"], "chennai": ["madras"], "kolkata": ["calcutta"],
    "gurgaon": ["gurugram"], "new york city": ["new york", "nyc", "manhattan", "brooklyn"],
    "san francisco": ["sf", "san fran", "bay area", "sf bay area"], "los angeles": ["la", "l.a."],
    "washington": ["washington dc", "washington d.c.", "dc", "d.c."], "ho chi minh city": ["saigon", "hcmc"],
    "munich": ["münchen", "muenchen"], "cologne": ["köln", "koeln"], "zurich": ["zürich", "zuerich"],
    "lisbon": ["lisboa"], "prague": ["praha"], "warsaw": ["warszawa"], "kyiv": ["kiev"],
    "the hague": ["den haag"], "copenhagen": ["københavn"], "rome": ["roma"], "milan": ["milano"],
    "vienna": ["wien"], "brussels": ["bruxelles", "brussel"], "frankfurt am main": ["frankfurt"],
    "hyderabad": ["hyderabad"], "noida": ["noida"], "pune": ["pune"],
}
# Smaller tech hubs that are below the population cut but matter for jobs.
EXTRA_CITIES = {
    "noida": "IN", "gurgaon": "IN", "mountain view": "US", "palo alto": "US", "sunnyvale": "US",
    "menlo park": "US", "redmond": "US", "cambridge": "GB", "oxford": "GB", "boulder": "US",
    "eindhoven": "NL", "delft": "NL", "utrecht": "NL", "tallinn": "EE", "luxembourg": "LU",
    "zug": "CH", "lausanne": "CH", "geneva": "CH", "basel": "CH", "aarhus": "DK", "gothenburg": "SE",
    "malmo": "SE", "espoo": "FI", "tampere": "FI", "cork": "IE", "galway": "IE", "limerick": "IE",
    "reykjavik": "IS", "ljubljana": "SI", "bratislava": "SK", "vilnius": "LT", "riga": "LV",
    "valletta": "MT", "nicosia": "CY", "kochi": "IN", "trivandrum": "IN", "coimbatore": "IN",
    "mysore": "IN", "chandigarh": "IN", "mohali": "IN", "waterloo": "CA", "victoria": "CA",
    "halifax": "CA", "raleigh": "US", "durham": "US", "pittsburgh": "US", "salt lake city": "US",
    "ann arbor": "US", "berkeley": "US", "santa clara": "US", "san mateo": "US", "irvine": "US",
}
# Real cities whose names are also common English words: only matched when Capitalized.
AMBIGUOUS = {"nice", "mobile", "reading", "split", "orange", "bath", "sale", "aurora", "independence",
             "providence", "victoria", "florence", "york", "jackson", "salem", "eugene", "deal",
             "santa", "mission", "temple", "tyler", "paris", "london", "lincoln", "columbia", "concord",
             "hope", "university", "garden", "marathon", "remote", "home", "anywhere", "can", "us",
             "la", "dc", "sf", "male", "of", "san", "bern", "agra", "patna", "rome", "kochi", "cork",
             "durham", "waterloo", "halifax", "zug", "basel", "delft"}

CONTINENTS = {"AF": "africa", "AS": "asia", "EU": "europe", "NA": "north america", "OC": "oceania",
              "SA": "south america", "AN": "antarctica"}


def ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def main() -> None:
    gc = geonamescache.GeonamesCache()
    countries = {}
    for c in pycountry.countries:
        names = {c.name.lower(), ascii_fold(c.name).lower()}
        for attr in ("common_name", "official_name"):
            if getattr(c, attr, None):
                names.add(getattr(c, attr).lower())
        names.update(COUNTRY_ALIASES.get(c.alpha_2, []))
        countries[c.alpha_2] = sorted(n for n in names if "," not in n and len(n) > 2 or n in
                                      COUNTRY_ALIASES.get(c.alpha_2, []))
    continent_of = {code: CONTINENTS.get(info["continentcode"], "") for code, info in gc.get_countries().items()
                    if code in countries}

    cities = {}
    for city in gc.get_cities().values():
        if city["population"] < MIN_POPULATION:
            continue
        name = ascii_fold(city["name"]).lower()
        prev = cities.get(name)
        if prev is None or city["population"] > prev[1]:
            cities[name] = (city["countrycode"], city["population"])
    out_cities = {name: cc for name, (cc, _) in sorted(cities.items())}
    for name, cc in EXTRA_CITIES.items():
        out_cities.setdefault(name, cc)
    aliases = {}
    for main_name, alts in CITY_ALIASES.items():
        if main_name in out_cities:
            for a in alts:
                aliases[a] = main_name
    data = {
        "_source": "ISO 3166 country names (pycountry); cities and continents from GeoNames (CC BY 4.0)",
        "countries": countries,
        "continents": continent_of,
        "cities": out_cities,
        "city_aliases": aliases,
        "ambiguous": sorted(AMBIGUOUS),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    print(f"{len(countries)} countries, {len(out_cities)} cities, {len(aliases)} aliases -> {OUT}")


if __name__ == "__main__":
    main()
