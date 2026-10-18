from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobsearch.api import create_app
from jobsearch.http import Http
from jobsearch.indexer import refresh_due
from jobsearch.service import JobSearch
from jobsearch.store import Store

from .conftest import KEEP, only_boards
from .test_cv import TEXT_CV, make_docx

PDF = Path(__file__).parent / "cv_sample.pdf"


@pytest.fixture
def client(settings, mocked):
    js = JobSearch(settings, store=Store(settings.data_dir / "api.db"), http=Http("test", allow_private=True))
    app = create_app(settings, js)
    with TestClient(app) as c:
        js.store.add_board("greenhouse", "acme")
        only_boards(js.store, KEEP)
        c.portal.call(refresh_due, js.ctx)
        yield c


def test_page_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and "Find jobs" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/healthz").json()["ok"]
    assert client.get("/static/app.js").status_code == 200


def test_search_get_and_post(client):
    r = client.get("/v1/search", params={"q": "senior backend engineer python, remote in Europe", "limit": 5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["requirements"]["titles"] == ["backend engineer"]
    assert data["results"][0]["job"]["title"] == "Senior Backend Engineer (Python)"
    assert data["results"][0]["reasons"]
    r = client.post("/v1/search", json={"requirements": "data analyst, SQL and Tableau", "location": "New York"})
    assert r.status_code == 200
    assert any(m["job"]["title"] == "Data Analyst" for m in r.json()["results"])


def test_search_needs_something_to_go_on(client):
    assert client.post("/v1/search", json={"requirements": ""}).status_code == 400
    r = client.post("/v1/search", json={"requirements": "hello there"})
    assert r.status_code == 422 and "job title" in r.json()["detail"]


def test_cv_upload_alone_and_with_requirements(client):
    with PDF.open("rb") as f:
        r = client.post("/v1/search/cv", files={"cv": ("cv.pdf", f, "application/pdf")})
    assert r.status_code == 200, r.text
    req = r.json()["requirements"]
    assert req["titles"][0] == "data engineer" and req["home_country"] == "IN"
    assert "priya" not in r.text.lower()  # the CV is not echoed back
    r = client.post("/v1/search/cv", files={"cv": ("cv.docx", make_docx(TEXT_CV), "application/octet-stream")},
                    data={"requirements": "remote only", "location": "Germany"})
    req = r.json()["requirements"]
    assert req["titles"][0] == "nurse" and req["work_modes"] == ["remote"]
    assert [p["country"] for p in req["places"]] == ["DE"]  # typed location wins over the CV


def test_cv_errors(client):
    r = client.post("/v1/search/cv", files={"cv": ("cv.pdf", b"%PDF-1.4 junk", "application/pdf")})
    assert r.status_code == 400 and "PDF" in r.json()["detail"]


def test_understand_and_sources(client):
    r = client.post("/v1/understand", json={"requirements": "nurse in Berlin, need visa sponsorship"})
    assert r.json()["visa_sponsorship"] is True
    s = client.get("/v1/sources").json()
    ids = {x["id"]: x for x in s["sources"]}
    assert ids["linkedin"]["enabled"] is False and ids["greenhouse"]["enabled"] is True
    assert s["indexed_jobs"] > 0


def test_alerts_lifecycle(client):
    r = client.post("/v1/alerts", json={"requirements": "senior backend engineer python remote europe",
                                        "every_hours": 24})
    assert r.status_code == 200, r.text
    a = r.json()
    assert client.get(f"/v1/alerts/{a['id']}", params={"token": "wrong"}).status_code == 404
    run = client.post(f"/v1/alerts/{a['id']}/run", params={"token": a["token"]})
    assert run.json()["new_matches"] >= 1
    again = client.post(f"/v1/alerts/{a['id']}/run", params={"token": a["token"]})
    assert again.json()["new_matches"] == 0  # only new jobs count
    feed = client.get(f"/v1/alerts/{a['id']}/feed.xml", params={"token": a["token"]})
    assert feed.status_code == 200 and "<rss" in feed.text and "Senior Backend Engineer" in feed.text
    assert client.delete(f"/v1/alerts/{a['id']}", params={"token": a["token"]}).json()["ok"]
    assert client.get(f"/v1/alerts/{a['id']}", params={"token": a["token"]}).status_code == 404


def test_alert_from_previous_cv_search(client):
    with PDF.open("rb") as f:
        understood = client.post("/v1/search/cv", files={"cv": ("cv.pdf", f, "application/pdf")}).json()["requirements"]
    r = client.post("/v1/alerts", json={"understood": understood, "every_hours": 168})
    assert r.status_code == 200
    info = client.get(f"/v1/alerts/{r.json()['id']}", params={"token": r.json()["token"]}).json()
    assert info["requirements"]["titles"][0] == "data engineer"


def test_alert_webhook_must_be_public(client, settings):
    settings.allow_private_urls = False
    r = client.post("/v1/alerts", json={"requirements": "python developer", "webhook_url": "http://127.0.0.1:9/x"})
    assert r.status_code == 400


def test_api_keys_and_rate_limit(settings, mocked):
    settings.api_keys = {"secret-key"}
    settings.rate_limit = 2
    js = JobSearch(settings, store=Store(settings.data_dir / "k.db"), http=Http("test", allow_private=True))
    with TestClient(create_app(settings, js)) as c:
        assert c.get("/v1/search", params={"q": "nurse"}).status_code == 401
        h = {"X-API-Key": "secret-key"}
        codes = [c.get("/v1/search", params={"q": "nurse in Berlin"}, headers=h).status_code for _ in range(3)]
        assert codes[:2] == [200, 200] and codes[2] == 429
        assert c.get("/").status_code == 200  # the page itself stays open
