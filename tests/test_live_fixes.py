"""Problems seen in the first run against the real job sources."""
from jobsearch.models import Job
from jobsearch.parse import parse
from jobsearch.rank import rank, score


def job(**kw):
    base = dict(title="Product Designer", company="X", url="https://x/1", source="greenhouse",
                description="Figma, user research")
    base.update(kw)
    return Job(**base)


def test_city_or_remote_is_not_remote_only():
    req = parse("Product designer, Figma and user research, London or remote UK.")
    assert set(req.work_modes) == {"remote", "hybrid", "onsite"}
    assert score(req, job(location="London, UK", countries=["GB"])) is not None
    assert score(req, job(location="San Francisco Bay Area", countries=["US"])) is None


def test_remote_only_still_respects_country():
    req = parse("Python developer, fully remote. I live in India.")
    assert score(req, job(title="Python Developer", location="Austin, TX", countries=["US"], description="Python")) is None


def test_remote_jobs_for_other_countries_are_dropped():
    req = parse("Registered nurse in Berlin, Germany. I speak English and German.")
    us_only = job(title="Triage Nurse (Remote)", location="United States", work_mode="remote", remote_regions=["US"],
                  description="nursing")
    assert score(req, us_only) is None
    germany = job(title="Telehealth Nurse", location="Remote, Germany", work_mode="remote", remote_regions=["DE"],
                  description="nursing")
    assert score(req, germany) is not None


def test_other_language_in_title_is_pushed_down():
    req = parse("Senior backend developer, Python and Django. Remote in Europe.")
    ruby = job(title="Senior Backend Engineer (Ruby)", location="Remote, Poland", work_mode="remote",
               remote_regions=["PL"], description="Ruby on Rails, some Python")
    py = job(title="Senior Backend Engineer (Python)", url="https://x/2", location="Remote, Poland", work_mode="remote",
             remote_regions=["PL"], description="Python, Django")
    a, b = score(req, ruby), score(req, py)
    assert "Title asks for Ruby" in a.warnings and b.score > a.score + 10


def test_repeats_collapse_and_one_company_cannot_fill_the_list():
    req = parse("Machine learning engineer, PyTorch, remote")
    jobs = [job(title="Machine Learning Engineer", company="GitLab", url=f"https://x/{c}", location=f"Remote, {c}",
                work_mode="remote", description="PyTorch") for c in ("Poland", "Spain", "UK")]
    jobs += [job(title=f"ML Engineer {i}", company="Jobgether", url=f"https://y/{i}", work_mode="remote",
                 description="PyTorch machine learning") for i in range(5)]
    jobs += [job(title="Machine Learning Engineer", company="Acme", url="https://z/1", work_mode="remote",
                 description="PyTorch")]
    out, total = rank(req, jobs, limit=5)
    companies = [m.job.company for m in out]
    assert companies.count("GitLab") == 1 and len(out[companies.index("GitLab")].job.also_on) == 2
    assert companies[:4].count("Jobgether") <= 2 and "Acme" in companies


def test_job_site_search_pages_are_not_jobs():
    from jobsearch.sources import ALL
    from jobsearch.sources.web import job_from_result
    pages = [("246 Registered Nurse jobs in Berlin", "https://de.linkedin.com/jobs/registered-nurse-jobs-berlin"),
             ("Registered Nurse: 704 Jobs - Stellenangebote in Berlin | StepStone",
              "https://www.stepstone.de/jobs/registered-nurse/in-berlin")]
    for title, url in pages:
        assert job_from_result({"title": title, "url": url}, ALL["web"]) is None
    real = job_from_result({"title": "Registered Nurse - Charité - Berlin | LinkedIn",
                            "url": "https://de.linkedin.com/jobs/view/registered-nurse-at-charite-4012345678"}, ALL["web"])
    assert real and real.title == "Registered Nurse" and real.company == "Charité"


def test_remote_guesses_are_dropped():
    nurse = parse("Registered nurse in Berlin, Germany.")
    unknown_region = job(title="Nurse Practitioner", location="Remote - East", work_mode="remote", description="nursing")
    assert score(nurse, unknown_region) is None  # they never asked for remote
    designer = parse("Product designer, Figma, London or remote UK.")
    sydney = job(title="Senior UX Designer", location="Sydney, Australia / Remote", countries=["AU"])
    assert score(designer, sydney) is None
    anywhere = parse("Machine learning engineer, PyTorch, remote anywhere")
    office = job(title="Machine Learning Engineer", location="Amsterdam", countries=["NL"], description="PyTorch")
    assert score(anywhere, office) is None


def test_states_and_provinces_are_not_countries():
    from jobsearch.normalize import countries_in
    assert countries_in("Sydney, Australia / Sydney, New South Wales, Australia") == ["AU"]
    assert countries_in("Jersey City, NJ") == ["US"] and countries_in("New Mexico, US") == ["US"]
    assert countries_in("Atlanta, Georgia") == ["US"] and countries_in("Tbilisi, Georgia") == ["GE"]
    assert countries_in("Paris, Texas") == ["US"] and countries_in("Toronto, Ontario") == ["CA"]
    designer = parse("Product designer, Figma, London or remote UK.")
    sydney = job(title="Senior UX Designer", location="Sydney, Australia",
                 countries=countries_in("Sydney, Australia / Sydney, New South Wales, Australia"))
    assert score(designer, sydney) is None


def test_city_alias_or_remote():
    req = parse("Junior data analyst in New York or remote US. SQL, Excel, Tableau.")
    assert set(req.work_modes) == {"remote", "hybrid", "onsite"}


def test_same_city_name_in_another_country():
    from jobsearch.normalize import countries_in
    nurse = parse("Registered nurse in Berlin, Germany.")
    pa = job(title="Nurse Practitioner", location="East Berlin, Pennsylvania",
             countries=countries_in("East Berlin, Pennsylvania"), description="nursing")
    assert score(nurse, pa) is None


def test_remote_of_unknown_region_ranks_below_a_known_match():
    designer = parse("Product designer, Figma and user research, London or remote UK.")
    vague = job(title="Product Designer", location="Flexible / Remote", work_mode="remote")
    uk = job(title="Product Designer", url="https://x/2", location="Remote (UK)", work_mode="remote",
             remote_regions=["GB"])
    a, b = score(designer, vague), score(designer, uk)
    assert a and b and b.score > a.score and a.warnings
