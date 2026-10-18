"""Regression tests for problems found in code review."""
import asyncio
import ipaddress

import pytest
import respx
from fastapi.testclient import TestClient

from jobsearch.api import create_app
from jobsearch.cv import CVError, extract_text
from jobsearch.http import FetchError, Http, _ip_is_public
from jobsearch.models import Job
from jobsearch.normalize import employment_type, work_mode
from jobsearch.parse import parse
from jobsearch.rank import score
from jobsearch.service import JobSearch
from jobsearch.sources import ALL
from jobsearch.sources.live import _visa
from jobsearch.sources.web import jobs_from_jsonld
from jobsearch.store import Store

from . import fixtures as F


async def test_cancelled_request_gives_its_slot_back():
    http = Http("t", allow_private=True)
    with respx.mock:
        respx.get(url__regex=r"https://slow\.example/.*").respond(json={})
        for _ in range(4):  # paced requests cancelled while waiting their turn
            task = asyncio.create_task(http.get("https://slow.example/a", min_interval=5, cache=False))
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        http._host_last.clear()
        assert await asyncio.wait_for(http.get("https://slow.example/b", cache=False), 2) == {}
    await http.close()


async def test_webhook_reply_is_capped():
    http = Http("t", allow_private=True)
    with respx.mock:
        respx.post("https://hook.example/x").respond(200, content=b"x" * (5 * 1024 * 1024))
        assert await http.post_json("https://hook.example/x", {"a": 1}) is None  # read 64 KB, then stop
    await http.close()


@pytest.mark.parametrize("ip", ["64:ff9b::a9fe:a9fe", "2002:7f00:1::", "::ffff:10.0.0.1"])
def test_ipv6_wrappers_of_private_addresses(ip):
    assert not _ip_is_public(ipaddress.ip_address(ip))


def test_job_urls_must_be_http():
    assert Job(title="x", url="javascript:alert(1)", source="s").url == ""
    html = F.JOBPOSTING_HTML.replace('"title": "Registered Nurse - ICU"',
                                     '"title": "Registered Nurse - ICU", "url": "https://evil.example/phish"')
    jobs = jobs_from_jsonld(html, "https://careers.example-hospital.de/jobs/42", ALL["web"])
    assert jobs[0].url == "https://careers.example-hospital.de/jobs/42"  # not sent to another site


async def test_null_fields_from_a_feed_do_not_break_indexing(settings, tmp_path):
    from jobsearch.sources import Context
    bad = {"jobs": [dict(F.REMOTIVE["jobs"][0], company_name=None, title="Python Developer")]}
    http = Http("t", allow_private=True)
    ctx = Context(http=http, settings=settings, store=Store(tmp_path / "n.db"))
    with respx.mock:
        respx.get(url__regex=r"https://remotive\.com/.*").respond(json=bad)
        jobs = await ALL["remotive"].fetch_feed(ctx)
    await http.close()
    assert jobs[0].company == "" and jobs[0].title == "Python Developer"


def test_non_latin_jobs_stay_distinct():
    a = Job(title="Инженер-программист", company="Яндекс", url="https://x/1", source="s", location="Москва")
    b = Job(title="Бухгалтер", company="Сбер", url="https://x/2", source="s", location="Москва")
    assert a.key() != b.key()


def test_ranking_fixes():
    la = parse("Software engineer in Los Angeles")
    atlanta = Job(title="Software Engineer", company="X", url="https://x/1", source="s", location="Atlanta, GA",
                  countries=["US"], work_mode="onsite")
    m = score(la, atlanta)
    assert m is None or not any("Los Angeles" in r for r in m.reasons)
    assert work_mode("San Francisco, CA") is None  # titles no longer decide remote/hybrid
    assert employment_type("REMOTE (International) | Full-time") == "full_time"
    assert employment_type("contemporary art") is None
    assert _visa("We do not offer visa sponsorship.") is False
    assert _visa("Visa sponsorship available") is True
    travel = parse("Account manager in London. No travel please")
    job = Job(title="Account Manager", company="X", url="https://x/1", source="s", location="London", countries=["GB"],
              description="Travel budget. Travel perks. We love travel stories.")
    assert score(travel, job) is not None
    job.description = "Travel up to 50% required."
    assert score(travel, job) is None


def test_cv_text_encodings_and_broken_docx():
    cp = "Jürgen Müller\nSoftware Entwickler, Python und Django, München\nErfahrung 2015 - 2020".encode("cp1252")
    assert "Müller" in extract_text(cp + b" ", "cv.txt")
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<not really xml")
    with pytest.raises(CVError):
        extract_text(buf.getvalue(), "cv.docx")


@pytest.fixture
def secured(settings, mocked):
    settings.api_keys = {"k1"}
    settings.trust_proxy = True
    settings.rate_limit = 2
    js = JobSearch(settings, store=Store(settings.data_dir / "s.db"), http=Http("t", allow_private=True))
    with TestClient(create_app(settings, js)) as c:
        yield c


def test_upload_rejected_before_reading(secured):
    r = secured.post("/v1/search/cv", files={"cv": ("cv.pdf", b"%PDF" + b"0" * 100, "application/pdf")})
    assert r.status_code == 401
    big = b"0" * (6 * 1024 * 1024)
    r = secured.post("/v1/search/cv", files={"cv": ("cv.pdf", big, "application/pdf")}, headers={"X-API-Key": "k1"})
    assert r.status_code == 413


def test_non_ascii_key_and_forged_forwarding(secured):
    assert secured.get("/v1/search", params={"q": "nurse"}, headers={"X-API-Key": b"\xe9"}).status_code == 401
    codes = [secured.get("/v1/search", params={"q": "nurse in Berlin"},
                         headers={"X-API-Key": "k1", "X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}).status_code
             for i in range(3)]
    assert codes[2] == 429  # the client can't escape the limit by inventing addresses


async def test_alert_webhook_error_does_not_reveal_dns(js, settings):
    from jobsearch import alerts
    settings.allow_private_urls = False
    with pytest.raises(ValueError, match="public"):
        await alerts.create(js, parse("python developer"), 24, "http://127.0.0.1/x")
    _ = FetchError
