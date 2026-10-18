import re

import httpx
import pytest
import respx

from jobsearch.config import Settings
from jobsearch.http import Http
from jobsearch.service import JobSearch
from jobsearch.store import Store

from . import fixtures as F


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, search_url="http://search.test", background=False, rate_limit=0,
                    allow_private_urls=True, refresh_hours=6, base_url="http://testserver")


@pytest.fixture
def mocked():
    """All job sources answer with the sample responses."""
    with respx.mock(assert_all_called=False) as r:
        r.get(url__regex=r"https://boards-api\.greenhouse\.io/v1/boards/acme/jobs.*").respond(json=F.GREENHOUSE)
        r.get(url__regex=r"https://boards-api\.greenhouse\.io/v1/boards/newco/jobs.*").respond(json=F.NEWCO_GREENHOUSE)
        r.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").respond(404)
        r.get(url__regex=r"https://api\.lever\.co/v0/postings/spotify.*").respond(json=F.LEVER)
        r.get(url__regex=r"https://api\.lever\.co/.*").respond(404)
        r.get(url__regex=r"https://api\.ashbyhq\.com/posting-api/job-board/ramp.*").respond(json=F.ASHBY)
        r.get(url__regex=r"https://api\.ashbyhq\.com/.*").respond(404)
        r.get(url__regex=r"https://apply\.workable\.com/api/v1/widget/accounts/seeq.*").respond(json=F.WORKABLE)
        r.get(url__regex=r"https://apply\.workable\.com/.*").respond(404)
        r.get(url__regex=r"https://allright\.recruitee\.com/api/offers/.*").respond(json=F.RECRUITEE)
        r.get(url__regex=r"https://[a-z0-9-]+\.recruitee\.com/.*").respond(404)
        r.get(url__regex=r"https://api\.smartrecruiters\.com/v1/companies/BoschGroup/postings.*").respond(
            json=F.SMARTRECRUITERS)
        r.get(url__regex=r"https://api\.smartrecruiters\.com/.*").respond(json={"content": [], "totalFound": 0})
        r.get(url__regex=r"https://remotive\.com/api/remote-jobs.*").respond(json=F.REMOTIVE)
        r.get("https://remoteok.com/api").respond(json=F.REMOTEOK)
        r.get(url__regex=r"https://jobicy\.com/api/v2/remote-jobs.*").respond(json=F.JOBICY)
        r.get(url__regex=r"https://www\.arbeitnow\.com/api/job-board-api.*").respond(json=F.ARBEITNOW)
        r.get(url__regex=r"https://www\.themuse\.com/api/public/jobs.*").respond(json=F.MUSE)
        r.get(url__regex=r"https://himalayas\.app/jobs/api/search.*").respond(json=F.HIMALAYAS)
        r.get(url__regex=r"https://hn\.algolia\.com/api/v1/search_by_date.*").respond(json=F.HN_STORIES)
        r.get(url__regex=r"https://hn\.algolia\.com/api/v1/search\?.*").respond(json=F.HN_COMMENTS)
        r.get(url__regex=r"https://www\.linkedin\.com/jobs-guest/.*").respond(text=F.LINKEDIN_HTML)
        r.get(url__regex=r"http://search\.test/search.*").respond(json=F.SEARCH_RESULTS)
        r.get("https://careers.example-hospital.de/jobs/42").respond(
            text=F.JOBPOSTING_HTML, headers={"content-type": "text/html; charset=utf-8"})
        r.get(url__regex=r"https://de\.indeed\.com/.*").respond(403)
        yield r


@pytest.fixture
async def js(settings, mocked):
    s = JobSearch(settings, store=Store(settings.data_dir / "t.db"),
                  http=Http(settings.user_agent, allow_private=True))
    yield s
    await s.close()


def only_boards(store, keep: set[str]):
    """Limit the seeded directory to the boards the mocks answer for (keeps tests fast)."""
    for b in store.boards():
        if f"{b['ats']}:{b['token']}" not in keep:
            store._exec("DELETE FROM boards WHERE ats=? AND token=?", (b["ats"], b["token"]))


KEEP = {"greenhouse:acme", "lever:spotify", "ashby:ramp", "workable:seeq", "recruitee:allright",
        "smartrecruiters:BoschGroup"}
_ = (re, httpx)
