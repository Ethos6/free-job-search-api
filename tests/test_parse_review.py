"""Requests the code review found misunderstood; each must now be read correctly."""
import pytest

from jobsearch.parse import parse

cases = {
 "Data engineer, salary $80-100k, remote US": lambda r: (r.salary_min, r.salary_period) == (80000, "year"),
 "Python developer in London, salary 60-70k GBP": lambda r: (r.salary_min, r.salary_currency, r.salary_period) == (60000, "GBP", "year"),
 "Backend engineer, distributed systems experience, Berlin office": lambda r: "remote" not in r.work_modes,
 "Hybrid in Munich, not fully remote.": lambda r: r.work_modes == ["hybrid"],
 "I don't mind travel, sales manager in Paris": lambda r: r.titles and not r.exclude and r.places and r.places[0].name == "Paris",
 "React developer without a degree, Austin": lambda r: any(p.name == "Austin" for p in r.places),
 "Product designer. I can't do agencies.": lambda r: "agencies" in r.exclude and "agencies" not in r.keywords,
 "Fresh graduate looking for a data analyst job": lambda r: r.posted_within_days is None,
 "work with the latest tech as a react developer": lambda r: r.posted_within_days is None,
 "Nurse in Dublin, 2 year contract is fine": lambda r: r.years_experience is None,
 "Python backend developer in Berlin.\nNice to have: Docker": lambda r: [p.name for p in r.places] == ["Berlin"],
 "I'm in Germany with a Blue Card, python developer": lambda r: r.visa_sponsorship is None,
 "Junior developer who wants to grow into a senior role": lambda r: r.seniority == "junior",
 "Java developer, available starting 2027": lambda r: r.salary_min is None,
 "Python dev in Austin, no crypto, gambling or adult companies, remote": lambda r: set(r.exclude) == {"crypto", "gambling", "adult"} and "remote" in r.work_modes,
 "Move to Nice, France as a chef": lambda r: any(p.name == "Nice" for p in r.places),
 "Looking for new jobs posted recently: fresh jobs only, python developer": lambda r: r.posted_within_days == 14,
}


@pytest.mark.parametrize("text", list(cases))
def test_review_case(text):
    r = parse(text)
    assert cases[text](r), r.model_dump(exclude={"text"}, exclude_defaults=True)
