import pytest

from jobsearch.parse import parse


def test_full_request_from_india():
    r = parse("""I'm a backend developer with 6 years of experience in Python, Django and PostgreSQL.
    Looking for a senior remote role, ideally with Kubernetes and AWS.
    I live in Pune, India. Salary at least 35 LPA.
    No crypto or gambling companies. Full-time only, posted in the last 2 weeks.""")
    assert r.titles == ["backend engineer"]
    assert r.skills == ["python", "django", "postgresql"]
    assert set(r.nice_skills) == {"kubernetes", "aws"}
    assert r.exclude == ["crypto", "gambling"]
    assert r.home_country == "IN" and r.work_modes == ["remote"]
    assert r.seniority == "senior" and r.years_experience == 6
    assert (r.salary_min, r.salary_currency, r.salary_period) == (3_500_000, "INR", "year")
    assert r.employment_types == ["full_time"] and r.posted_within_days == 14


def test_nurse_in_germany_with_visa_and_languages():
    r = parse("Registered nurse, 3 years ICU experience. Want a job in Berlin or Munich, Germany. "
              "I speak English and German (B2). Need visa sponsorship. Part-time or full-time is fine.")
    assert r.titles == ["nurse"]
    assert {p.name for p in r.places} >= {"Berlin", "Munich"}
    assert r.countries == {"DE"}
    assert r.visa_sponsorship is True
    assert set(r.languages) == {"english", "german"}
    assert set(r.employment_types) == {"full_time", "part_time"}


def test_designer_london_salary_and_avoid_agencies():
    r = parse("Looking for a product designer job, remote or hybrid in London. Figma, user research. "
              "Minimum £70,000 a year. Not interested in agencies. Prefer fintech or healthtech startups.")
    assert r.titles == ["product designer"]
    assert set(r.work_modes) == {"remote", "hybrid"}
    assert (r.salary_min, r.salary_currency) == (70000, "GBP")
    assert r.exclude == ["agencies"]
    assert {"fintech", "healthtech"} <= set(r.keywords)


def test_negation_only_covers_what_follows():
    r = parse("entry level data analyst, sql excel tableau, new york or remote US, $65k+, no sales roles please")
    assert r.titles == ["data analyst"] and r.seniority == "junior"
    assert r.skills == ["sql", "excel", "tableau"]
    assert r.exclude == ["sales"]
    assert "US" in r.countries and r.salary_min == 65000


def test_skill_based_title_and_home_country():
    r = parse("Senior Go engineer, I know Go, gRPC and Kafka. Remote in Europe only, I'm based in Lisbon. "
              "€90k minimum. I don't need sponsorship.")
    assert "software engineer" in r.titles and r.skills == ["go", "grpc", "kafka"]
    assert r.home_country == "PT" and r.work_modes == ["remote"]
    assert r.visa_sponsorship is None and r.salary_currency == "EUR"


def test_hourly_freelance_and_excluded_companies():
    r = parse("Freelance React Native developer, $60/hour, worldwide remote, contract roles. Avoid Amazon and Meta.")
    assert r.salary_period == "hour" and r.salary_min == 60
    assert set(r.employment_types) == {"contract", "freelance"}
    assert {"amazon", "meta"} <= set(r.exclude)


def test_monthly_salary_in_aed_and_teacher():
    r = parse("I want to work as a primary school teacher in Dubai, UAE. 5 years experience. "
              "Salary above 12000 AED per month.")
    assert r.titles == ["teacher"]
    assert (r.salary_min, r.salary_currency, r.salary_period) == (12000, "AED", "month")


@pytest.mark.parametrize("text", ["", "   ", "hello"])
def test_nothing_to_understand(text):
    r = parse(text)
    assert not r.titles and not r.skills


def test_numbers_that_are_not_salaries():
    r = parse("Python developer, team of 50 people, 3 years experience")
    assert r.salary_min is None and r.years_experience == 3


def test_free_text_title_not_in_vocabulary():
    r = parse("Looking for a beekeeper job in Portugal")
    assert r.titles == ["beekeeper"] and r.countries == {"PT"}


def test_ambiguous_city_words_are_not_places():
    r = parse("python developer, nice to have docker, reading lots of code")
    assert r.places == []
