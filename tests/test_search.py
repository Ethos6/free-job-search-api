from datetime import timedelta

from jobsearch.indexer import refresh_due, seed
from jobsearch.models import Job, Salary
from jobsearch.parse import parse
from jobsearch.rank import score
from jobsearch.service import dedupe, merge

from .conftest import KEEP, only_boards
from .fixtures import NOW


def job(**kw):
    base = dict(title="Senior Backend Engineer", company="Acme", url="https://x/1", source="greenhouse",
                location="Berlin, Germany", countries=["DE"], work_mode="onsite",
                description="Python, Django, PostgreSQL", posted_at=NOW - timedelta(days=2), seniority="senior")
    base.update(kw)
    return Job(**base)


def test_score_explains_and_filters():
    req = parse("Senior backend developer, Python and Django, Berlin, at least €70k, no crypto")
    m = score(req, job(salary=Salary(min=80000, max=95000, currency="EUR")))
    assert m and m.score > 80
    assert any("Role matches" in r for r in m.reasons) and any("Python" in r for r in m.reasons)
    assert any("Berlin" in r for r in m.reasons) and any("€80k–95k/year" in r for r in m.reasons)
    # hard filters
    assert score(req, job(company="CryptoCorp")) is None
    assert score(req, job(salary=Salary(min=40000, max=50000, currency="EUR"))) is None
    assert score(req, job(countries=["US"], location="Austin, TX")) is None


def test_remote_rules():
    req = parse("Python backend developer, fully remote, I live in India")
    assert score(req, job(work_mode="onsite")) is None
    assert score(req, job(work_mode="remote", remote_regions=["US"], countries=[])) is None  # US residents only
    ok = score(req, job(work_mode="remote", remote_regions=[], countries=[]))
    assert ok and any("worldwide" in r for r in ok.reasons)


def test_seniority_and_salary_conversion():
    req = parse("junior data analyst, SQL, at least $50k")
    m = score(req, job(title="Principal Data Analyst", seniority="principal", description="SQL",
                       salary=Salary(min=60000, currency="EUR"), countries=[], location=""))
    assert m and any("too senior" in w for w in m.warnings)
    assert any("approximate" in r for r in m.reasons)


def test_dedupe_prefers_company_board_and_keeps_links():
    a = job(source="remotive", url="https://remotive.com/1", description="")
    b = job(source="greenhouse", url="https://boards/1", salary=Salary(min=1, currency="EUR"))
    out = dedupe([a, b])
    assert len(out) == 1 and out[0].url == "https://boards/1"
    assert out[0].also_on == [{"source": "remotive", "url": "https://remotive.com/1"}]


def test_merge_typed_overrides_cv():
    cv = parse("Data analyst in Pune, India. SQL, Excel.")
    typed = parse("remote only, Python")
    m = merge(cv, typed)
    assert m.work_modes == ["remote"] and m.skills[0] == "python" and "sql" in m.skills
    assert m.titles == ["data analyst"]


async def test_index_then_search_end_to_end(js):
    seed(js.ctx)
    js.store.add_board("greenhouse", "acme")
    only_boards(js.store, KEEP)
    stats = await refresh_due(js.ctx)
    assert stats["boards"] == 5 and stats["feeds"] == 4 and js.store.job_count() >= 10
    res = await js.search(parse("Senior backend engineer, Python, Django. Remote in Europe. Full-time. No crypto."))
    titles = [m.job.title for m in res.results]
    assert titles and titles[0] == "Senior Backend Engineer (Python)"
    assert "SEO Manager" not in titles  # crypto company, and not the role
    ids = {s.id: s for s in res.sources}
    assert ids["index"].jobs > 0 and ids["linkedin"].skipped
    assert all(m.score >= 0 for m in res.results)


async def test_web_search_discovers_boards_and_reads_pages(js):
    res = await js.search(parse("ICU nurse in Berlin"))
    by_url = {m.job.url: m for m in res.results}
    assert "https://careers.example-hospital.de/jobs/42" in by_url  # read from the page's JobPosting data
    assert "https://job-boards.greenhouse.io/newco/jobs/5" in by_url  # board found by search, fetched at once
    assert ("greenhouse", "newco") in {(b["ats"], b["token"]) for b in js.store.boards()}
    indeed = by_url.get("https://de.indeed.com/viewjob?jk=abc")
    assert indeed and indeed.job.from_search_snippet  # big site: link only, page not fetched
    assert all("reddit" not in u for u in by_url)
