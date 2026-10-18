import httpx
import pytest
import respx

from jobsearch.http import Blocked, FetchError, Http, check_url


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:8080/", "http://10.0.0.5/x",
                                 "http://169.254.169.254/latest/meta-data", "http://[::1]/", "file:///etc/passwd",
                                 "ftp://example.com/", "http://user:pw@example.com/", "http://0.0.0.0/"])
def test_ssrf_blocked(url):
    with pytest.raises(FetchError):
        check_url(url)


async def test_redirect_to_private_address_is_blocked():
    http = Http("test")
    with respx.mock:
        respx.get("https://93.184.216.34/start").respond(302, headers={"location": "http://127.0.0.1/admin"})
        with pytest.raises(FetchError):
            await http.get("https://93.184.216.34/start", as_json=False, untrusted=True)
    await http.close()


async def test_backs_off_when_refused():
    http = Http("test", allow_private=True)
    with respx.mock:
        route = respx.get("https://api.example.com/x").respond(429, headers={"retry-after": "120"})
        with pytest.raises(Blocked):
            await http.get("https://api.example.com/x")
        with pytest.raises(Blocked):
            await http.get("https://api.example.com/x")  # not even asked again
        assert route.call_count == 1
    await http.close()


async def test_size_limit_and_cache():
    http = Http("test", allow_private=True)
    with respx.mock:
        respx.get("https://api.example.com/big").respond(200, content=b"x" * 2000)
        with pytest.raises(FetchError, match="too large"):
            await http.get("https://api.example.com/big", as_json=False, max_bytes=1000)
        r = respx.get("https://api.example.com/j").respond(json={"a": 1})
        assert await http.get("https://api.example.com/j") == {"a": 1}
        assert await http.get("https://api.example.com/j") == {"a": 1}
        assert r.call_count == 1
    await http.close()


async def test_honest_user_agent():
    http = Http("free-job-search-api/0.1 (+https://github.com/Ethos6/free-job-search-api)", allow_private=True)
    with respx.mock:
        r = respx.get("https://api.example.com/ua").respond(json={})
        await http.get("https://api.example.com/ua")
        assert r.calls[0].request.headers["user-agent"].startswith("free-job-search-api/")
    await http.close()
    _ = httpx
