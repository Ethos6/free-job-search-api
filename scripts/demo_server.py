"""Run the API offline with sample data (no internet needed), for trying the web page and for
UI tests. Every source answers with the sample responses in tests/fixtures.py.

    python scripts/demo_server.py 8010
"""
import asyncio
import json
from contextlib import asynccontextmanager
import re
import sys
import tempfile
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobsearch.api import create_app  # noqa: E402
from jobsearch.config import Settings  # noqa: E402
from jobsearch.http import Http  # noqa: E402
from jobsearch.indexer import refresh_due  # noqa: E402
from jobsearch.service import JobSearch  # noqa: E402
from jobsearch.store import Store  # noqa: E402
from tests import fixtures as F  # noqa: E402

ROUTES = [
    (r"boards-api\.greenhouse\.io/v1/boards/acme/", F.GREENHOUSE),
    (r"boards-api\.greenhouse\.io/v1/boards/newco/", F.NEWCO_GREENHOUSE),
    (r"api\.lever\.co/v0/postings/spotify", F.LEVER),
    (r"api\.ashbyhq\.com/posting-api/job-board/ramp", F.ASHBY),
    (r"apply\.workable\.com/api/v1/widget/accounts/seeq", F.WORKABLE),
    (r"allright\.recruitee\.com/api/offers", F.RECRUITEE),
    (r"api\.smartrecruiters\.com/v1/companies/BoschGroup/", F.SMARTRECRUITERS),
    (r"remotive\.com/api/remote-jobs", F.REMOTIVE), (r"remoteok\.com/api", F.REMOTEOK),
    (r"jobicy\.com/api", F.JOBICY), (r"arbeitnow\.com/api", F.ARBEITNOW), (r"themuse\.com/api", F.MUSE),
    (r"himalayas\.app/jobs/api/search", F.HIMALAYAS), (r"hn\.algolia\.com/api/v1/search_by_date", F.HN_STORIES),
    (r"hn\.algolia\.com/api/v1/search\?", F.HN_COMMENTS), (r"search\.demo/search", F.SEARCH_RESULTS),
]


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    for pat, body in ROUTES:
        if re.search(pat, url):
            return httpx.Response(200, json=body)
    if "careers.example-hospital.de" in url:
        return httpx.Response(200, text=F.JOBPOSTING_HTML, headers={"content-type": "text/html"})
    if "smartrecruiters" in url:
        return httpx.Response(200, json={"content": [], "totalFound": 0})
    return httpx.Response(404, text="not found")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    data = Path(tempfile.mkdtemp())
    settings = Settings(data_dir=data, search_url="http://search.demo", background=False, rate_limit=0,
                        allow_private_urls=True, base_url=f"http://127.0.0.1:{port}")
    http = Http(settings.user_agent, allow_private=True, transport=httpx.MockTransport(handler))
    js = JobSearch(settings, store=Store(data / "demo.db"), http=http)
    js.store.add_board("greenhouse", "acme", "Acme")
    js.store._exec("DELETE FROM boards WHERE NOT (ats||':'||token) IN ('greenhouse:acme','lever:spotify',"
                   "'ashby:ramp','workable:seeq','recruitee:allright','smartrecruiters:BoschGroup')")
    app = create_app(settings, js)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a):
        async with original(a):
            js.store.add_board("greenhouse", "acme", "Acme")
            js.store._exec("DELETE FROM boards WHERE NOT (ats||':'||token) IN ('greenhouse:acme','lever:spotify',"
                           "'ashby:ramp','workable:seeq','recruitee:allright','smartrecruiters:BoschGroup')")
            print(json.dumps(await refresh_due(js.ctx)), flush=True)
            yield

    app.router.lifespan_context = lifespan

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    _ = asyncio


if __name__ == "__main__":
    main()
