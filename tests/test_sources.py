from jobsearch.parse import parse
from jobsearch.sources import ALL
from jobsearch.sources.live import HackerNews, LinkedIn
from jobsearch.sources.web import board_from_url, job_from_result, jobs_from_jsonld

from . import fixtures as F


async def test_greenhouse(js):
    company, jobs = await ALL["greenhouse"].fetch_board(js.ctx, "acme")
    assert company == "Acme" and len(jobs) == 3
    j = jobs[0]
    assert j.title == "Senior Backend Engineer (Python)" and j.work_mode == "remote"
    assert "Python" in j.description and "<" not in j.description
    assert j.salary.min == 90000 and j.salary.currency == "EUR"
    assert j.employment_type == "full_time" and j.seniority == "senior"
    assert "DE" in j.remote_regions  # "Remote, Europe"
    assert jobs[2].countries == ["DE"]


async def test_lever(js):
    _, jobs = await ALL["lever"].fetch_board(js.ctx, "spotify")
    j = jobs[0]
    assert j.url == "https://jobs.lever.co/spotify/abc" and j.work_mode == "hybrid"
    assert j.countries == ["MX"] and "gRPC" in j.description and j.salary.max == 70000


async def test_ashby_skips_unlisted_and_reads_salary(js):
    _, jobs = await ALL["ashby"].fetch_board(js.ctx, "ramp")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.salary.min == 90000 and j.salary.currency == "USD" and j.work_mode == "hybrid"
    assert "US" in j.countries and j.employment_type == "full_time"


async def test_workable_recruitee(js):
    company, jobs = await ALL["workable"].fetch_board(js.ctx, "seeq")
    assert company == "Seeq" and jobs[0].work_mode == "remote" and jobs[0].countries == ["US"]
    company, jobs = await ALL["recruitee"].fetch_board(js.ctx, "allright")
    assert company == "AllRight" and jobs[0].employment_type == "freelance" and jobs[0].posted_at is not None
    assert jobs[0].seniority == "junior"


async def test_feeds(js):
    remotive = await ALL["remotive"].fetch_feed(js.ctx)
    assert remotive[0].source_name == "Remotive" and remotive[0].salary.min == 70000
    assert "DE" in remotive[0].remote_regions and remotive[1].remote_regions == []
    ok = await ALL["remoteok"].fetch_feed(js.ctx)
    assert len(ok) == 1 and ok[0].url.startswith("https://remoteok.com") and ok[0].salary.max == 110000
    jobicy = await ALL["jobicy"].fetch_feed(js.ctx)
    assert jobicy[0].seniority == "director" and jobicy[0].remote_regions == ["US"]
    arb = await ALL["arbeitnow"].fetch_feed(js.ctx)
    assert arb[0].countries == ["DE"]


async def test_live_sources(js):
    req = parse("senior software engineer, remote, python")
    muse = await ALL["themuse"].search(js.ctx, req)
    assert muse[0].company == "SpaceX" and muse[0].url.startswith("https://www.themuse.com/")
    him = await ALL["himalayas"].search(js.ctx, req)
    assert him[0].remote_regions == ["US"] and him[0].salary.min == 120000
    sr = await ALL["smartrecruiters"].search(js.ctx, parse("python developer in Germany"))
    assert sr == []  # no SmartRecruiters companies in the directory yet
    js.store.add_board("smartrecruiters", "BoschGroup")
    sr = await ALL["smartrecruiters"].search(js.ctx, parse("python developer in Germany"))
    assert sr[0].url == "https://jobs.smartrecruiters.com/BoschGroup/744000156179239"
    assert sr[0].work_mode == "hybrid" and sr[0].countries == ["DE"]


async def test_hacker_news_posts(js):
    jobs = await ALL["hackernews"].search(js.ctx, parse("backend engineer python remote"))
    assert len(jobs) == 1  # replies are not job ads
    j = jobs[0]
    assert j.company == "NeuralFrame" and "Backend Engineer" in j.title
    assert j.work_mode == "remote" and j.remote_regions == ["US"]
    assert j.salary.min == 170000 and j.visa_sponsorship is False
    assert HackerNews().parse_post({"objectID": "1", "comment_text": "just a comment"}) is None


def test_linkedin_cards_and_off_by_default(js):
    jobs = LinkedIn().parse_cards(F.LINKEDIN_HTML)
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4477761949/"
    assert jobs[0].company == "Athereon GRC GmbH" and jobs[0].countries == ["DE"]
    assert "off by default" in ALL["linkedin"].available(js.ctx)


def test_board_urls():
    assert board_from_url("https://job-boards.greenhouse.io/newco/jobs/5") == ("greenhouse", "newco")
    assert board_from_url("https://boards.greenhouse.io/embed/job_board?for=acme") == ("greenhouse", "acme")
    assert board_from_url("https://jobs.lever.co/spotify/abc") == ("lever", "spotify")
    assert board_from_url("https://jobs.ashbyhq.com/ramp") == ("ashby", "ramp")
    assert board_from_url("https://acme.recruitee.com/o/x") == ("recruitee", "acme")
    assert board_from_url("https://example.com/jobs") is None


def test_jsonld_posting_and_expired():
    src = ALL["web"]
    jobs = jobs_from_jsonld(F.JOBPOSTING_HTML, "https://careers.example-hospital.de/jobs/42", src)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Registered Nurse - ICU" and j.company == "Charité" and j.countries == ["DE"]
    assert j.salary.min == 48000 and j.salary.currency == "EUR" and j.employment_type == "full_time"
    assert jobs_from_jsonld(F.EXPIRED_HTML, "https://x", src) == []
    assert jobs_from_jsonld("<html>no data</html>", "https://x", src) == []


def test_big_site_result_is_link_only():
    j = job_from_result({"title": "ICU Nurse - Vivantes - Berlin | Indeed", "url": "https://de.indeed.com/viewjob?jk=1",
                         "content": "Berlin"}, ALL["web"])
    assert j.from_search_snippet and j.title == "ICU Nurse" and j.company == "Vivantes"
    assert job_from_result({"title": "Search jobs", "url": "https://www.indeed.com/"}, ALL["web"]) is None
