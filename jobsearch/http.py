"""Polite HTTP: one shared client, an honest User-Agent, per-host pacing, a small cache,
response size limits, and SSRF protection for URLs that come from search results or users.

No browser imitation, no CAPTCHA solving, no proxy rotation: if a site says no, we stop.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

MAX_BYTES = 8 * 1024 * 1024  # biggest response we read (some ATS boards are large)
PAGE_BYTES = 1_500_000  # biggest web page we read when looking for job data
NAT64 = ipaddress.ip_network("64:ff9b::/96")
SIX_TO_FOUR = ipaddress.ip_network("2002::/16")


class FetchError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class Blocked(FetchError):
    """The site refused us (rate limit, bot wall, login wall). We back off instead of working around it."""


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    if ip.version == 6:
        embedded = None
        if ip.ipv4_mapped:
            embedded = ip.ipv4_mapped
        elif ip in NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip in SIX_TO_FOUR:
            embedded = ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
        if embedded is not None and not _ip_is_public(embedded):
            return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified) and ip.is_global


def public_addresses(host: str) -> list[str]:
    """The host's addresses if every one of them is public, else []."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    addrs = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not _ip_is_public(ip):
            return []
        addrs.append(str(ip))
    return addrs


def is_public_host(host: str) -> bool:
    return bool(public_addresses(host))


def check_url(url: str, allow_private: bool = False) -> Optional[str]:
    """Reject URLs that could reach the server's own network (SSRF). Returns a checked IP to connect
    to (None when private addresses are allowed)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("only http(s) URLs are allowed", 400)
    if p.username or p.password:
        raise FetchError("URLs with credentials are not allowed", 400)
    if allow_private:
        return None
    if p.port not in (None, 80, 443):
        raise FetchError("only the standard web ports are allowed", 400)
    addrs = public_addresses(p.hostname)
    if not addrs:
        raise FetchError("the URL must point to a public website", 400)
    return addrs[0]


def _pinned(url: str, ip: Optional[str]) -> tuple[str, dict, dict]:
    """Connect to the address we checked, while still talking to (and verifying TLS for) the host."""
    if not ip:
        return url, {}, {}
    u = httpx.URL(url)
    host = u.host
    pinned = u.copy_with(host=ip)
    headers = {"Host": host if u.port in (None, 80, 443) else f"{host}:{u.port}"}
    ext = {"sni_hostname": host} if u.scheme == "https" else {}
    return str(pinned), headers, ext


class Http:
    def __init__(self, user_agent: str, allow_private: bool = False,
                 transport: Optional[httpx.AsyncBaseTransport] = None, cache_ttl: float = 900):
        self.allow_private = allow_private
        self.cache_ttl = cache_ttl
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
                     "Accept-Language": "en"},
            timeout=httpx.Timeout(12.0, connect=6.0), follow_redirects=False, transport=transport,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20))
        self._host_locks: dict[str, asyncio.Semaphore] = {}
        self._host_last: dict[str, float] = {}
        self._backoff: dict[str, float] = {}  # host -> time until which we leave it alone
        self._cache: dict[str, tuple[float, Any]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    def blocked_until(self, host: str) -> float:
        return self._backoff.get(host, 0.0)

    async def _paced(self, host: str, min_interval: float) -> asyncio.Semaphore:
        sem = self._host_locks.setdefault(host, asyncio.Semaphore(2))
        await sem.acquire()
        try:
            wait = self._host_last.get(host, 0) + min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()
        except BaseException:
            sem.release()  # cancelled while waiting: give the slot back
            raise
        return sem

    async def get(self, url: str, *, params: Optional[dict] = None, as_json: bool = True,
                  cache: bool = True, ttl: Optional[float] = None, min_interval: float = 0.25,
                  max_bytes: int = MAX_BYTES, untrusted: bool = False, headers: Optional[dict] = None) -> Any:
        """GET a URL and return parsed JSON or text. `untrusted` URLs get SSRF checks on every hop and
        the connection goes to the checked address."""
        key = url + "?" + json.dumps(params or {}, sort_keys=True) + ("j" if as_json else "t")
        now = time.monotonic()
        if cache and key in self._cache and self._cache[key][0] > now:
            return self._cache[key][1]
        host = urlparse(url).hostname or ""
        if self._backoff.get(host, 0) > now:
            raise Blocked(f"{host} asked us to slow down; trying again later", 429)
        current, hops = url, 0
        if params:
            current = str(httpx.URL(url, params=params))
        while True:
            ip = await asyncio.to_thread(check_url, current, self.allow_private) if untrusted else None
            target, extra_headers, ext = _pinned(current, ip)
            hop_host = urlparse(current).hostname or host
            sem = await self._paced(hop_host, min_interval)
            try:
                req = self._client.build_request("GET", target, headers={**(headers or {}), **extra_headers},
                                                 extensions=ext)
                r = await self._client.send(req, stream=True)
                try:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        hops += 1
                        if hops > 4:
                            raise FetchError("too many redirects", 502)
                        current = str(httpx.URL(current).join(r.headers["location"]))
                        continue
                    if r.status_code in (403, 429, 999) or (r.status_code == 503 and "captcha" in (
                            r.headers.get("content-type", "") + r.headers.get("server", "")).lower()):
                        retry = r.headers.get("retry-after", "")
                        delay = float(retry) if retry.isdigit() else 900.0
                        self._backoff[hop_host] = time.monotonic() + min(delay, 6 * 3600)
                        raise Blocked(f"{hop_host} refused the request (HTTP {r.status_code})", r.status_code)
                    if r.status_code == 404:
                        raise FetchError("not found", 404)
                    if r.status_code >= 400:
                        raise FetchError(f"HTTP {r.status_code}", r.status_code)
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > max_bytes:
                            raise FetchError("response too large", 502)
                    ctype = r.headers.get("content-type", "")
                    break
                finally:
                    await r.aclose()
            except httpx.TimeoutException as e:
                raise FetchError("timed out", 504) from e
            except httpx.HTTPError as e:
                raise FetchError(f"network error: {type(e).__name__}", 502) from e
            finally:
                sem.release()
        text = body.decode(_charset(ctype), errors="replace")
        if as_json:
            try:
                value = json.loads(text)
            except ValueError as e:
                raise FetchError("the response was not JSON", 502) from e
        else:
            value = text
        if cache:
            self._cache[key] = (now + (ttl if ttl is not None else self.cache_ttl), value)
            if len(self._cache) > 2000:
                for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:500]:
                    self._cache.pop(k, None)
        return value

    async def post_json(self, url: str, payload: Any, *, untrusted: bool = True, headers: Optional[dict] = None,
                        timeout: float = 10.0, max_bytes: int = 64 * 1024) -> Any:
        """POST JSON. The reply is read only up to `max_bytes`, and the whole call has a hard deadline."""
        async def go() -> Any:
            ip = await asyncio.to_thread(check_url, url, self.allow_private) if untrusted else None
            target, extra_headers, ext = _pinned(url, ip)
            req = self._client.build_request("POST", target, json=payload,
                                             headers={**(headers or {}), **extra_headers}, extensions=ext)
            r = await self._client.send(req, stream=True)
            try:
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code}", r.status_code)
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        break
                try:
                    return json.loads(bytes(body))
                except ValueError:
                    return None
            finally:
                await r.aclose()
        try:
            return await asyncio.wait_for(go(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise FetchError("timed out", 504) from e
        except httpx.HTTPError as e:
            raise FetchError(f"network error: {type(e).__name__}", 502) from e


def _charset(ctype: str) -> str:
    for part in ctype.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip('"') or "utf-8"
    return "utf-8"
