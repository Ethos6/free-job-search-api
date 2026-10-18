"""HTTP API and the web page."""
from __future__ import annotations

import asyncio
import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from importlib import resources
from typing import Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, alerts
from .config import REPO, Settings
from .cv import MAX_CV_BYTES, CVError, extract_text_isolated
from .http import FetchError
from .models import Requirements, SearchResponse
from .service import JobSearch

STATIC = resources.files("jobsearch") / "static"


class SearchBody(BaseModel):
    requirements: str = Field("", description="What you are looking for, in your own words (5-10 lines is plenty)",
                              max_length=6000)
    location: str = Field("", description="Optional place, e.g. 'Berlin' or 'remote, Europe'", max_length=200)
    limit: int = Field(25, ge=1, le=100)
    sources: Optional[list[str]] = Field(None, description="Only use these source ids (see /v1/sources)")


class AlertBody(BaseModel):
    requirements: str = Field("", max_length=6000)
    location: str = Field("", max_length=200)
    understood: Optional[Requirements] = Field(
        None, description="Requirements returned by a previous search (lets a CV-based search be saved "
                          "without sending the CV again)")
    every_hours: float = Field(24, ge=6, le=168)
    webhook_url: Optional[str] = Field(None, max_length=500)


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        if len(self.hits) > 50_000:  # forget idle clients only, never reset active ones
            for k in [k for k, q in self.hits.items() if not q or q[-1] < now - 60]:
                del self.hits[k]
        q = self.hits[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


def create_app(settings: Optional[Settings] = None, js: Optional[JobSearch] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    js = js or JobSearch(settings)
    runner = alerts.AlertRunner(js)
    limiter = RateLimiter(settings.rate_limit)
    cv_slots = asyncio.Semaphore(2)  # CVs are read in child processes; at most two at a time

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await js.start()
        runner.start()
        yield
        await runner.stop()
        await js.close()

    app = FastAPI(title="Free Job Search API", version=__version__, lifespan=lifespan,
                  description="Describe the job you want in your own words, or upload your CV, and get the best "
                              f"matching jobs from across the web. Free and open source: {REPO}")
    app.state.js = js
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", "X-API-Key", "Authorization"])

    def key_ok(request: Request) -> bool:
        if not settings.api_keys:
            return True
        key = (request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix(
            "Bearer ").strip()).encode()
        return any(hmac.compare_digest(key, k.encode()) for k in settings.api_keys)

    @app.middleware("http")
    async def upload_gate(request: Request, call_next):
        # check the key and the size before a single byte of an upload is read
        if request.method == "POST" and request.url.path == "/v1/search/cv":
            if not key_ok(request):
                return JSONResponse({"detail": "an API key is required (X-API-Key header)"}, status_code=401)
            length = request.headers.get("content-length")
            if not length or not length.isdigit():
                return JSONResponse({"detail": "send the CV as a normal file upload"}, status_code=411)
            if int(length) > MAX_CV_BYTES + 64 * 1024:
                return JSONResponse({"detail": "the CV must be smaller than 5 MB"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    def client_ip(request: Request) -> str:
        if settings.trust_proxy:
            # the right-most address was added by our own proxy; anything left of it the client could forge
            fwd = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
            if fwd:
                return fwd[-1]
        return request.client.host if request.client else "unknown"

    def guard(request: Request, limited: bool = True) -> None:
        if not key_ok(request):
            raise HTTPException(401, "an API key is required (X-API-Key header)")
        if limited and not limiter.allow(client_ip(request)):
            raise HTTPException(429, "too many searches; please wait a minute")

    @app.exception_handler(FetchError)
    async def fetch_error(_: Request, e: FetchError):
        return JSONResponse({"detail": str(e)}, status_code=e.status if e.status and 400 <= e.status < 600 else 502)

    # -- page ---------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(str(STATIC / "index.html"))

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True, "version": __version__}

    # -- search -------------------------------------------------------------------------------------
    async def do_search(text: str, location: str, limit: int, sources: Optional[list[str]],
                        cv_text: str = "") -> SearchResponse:
        if not (text.strip() or location.strip() or cv_text.strip()):
            raise HTTPException(400, "describe what you are looking for, or upload a CV")
        req = await js.understand(text=text, cv_text=cv_text, location=location)
        if not (req.titles or req.skills or req.keywords):
            raise HTTPException(422, "I could not tell what kind of job you want. Add a job title or a few "
                                     "skills, e.g. 'nurse in Berlin' or 'Python backend developer, remote'.")
        return await js.search(req, limit=limit, sources=sources)

    @app.get("/v1/search", response_model=SearchResponse, tags=["search"],
             summary="Search jobs from a description in your own words")
    async def search_get(request: Request,
                         q: str = Query(..., max_length=6000, description="What you are looking for"),
                         location: str = Query("", max_length=200), limit: int = Query(25, ge=1, le=100),
                         sources: Optional[str] = Query(None, description="comma-separated source ids")):
        guard(request)
        return await do_search(q, location, limit, [s for s in (sources or "").split(",") if s] or None)

    @app.post("/v1/search", response_model=SearchResponse, tags=["search"],
              summary="Search jobs from a description in your own words")
    async def search_post(request: Request, body: SearchBody = Body(...)):
        guard(request)
        return await do_search(body.requirements, body.location, body.limit, body.sources)

    @app.post("/v1/search/cv", response_model=SearchResponse, tags=["search"],
              summary="Search jobs from your CV, optionally with a location or extra requirements")
    async def search_cv(request: Request, cv: UploadFile = File(..., description="PDF, .docx or .txt, up to 5 MB"),
                        requirements: str = Form("", max_length=6000), location: str = Form("", max_length=200),
                        limit: int = Form(25, ge=1, le=100)):
        guard(request)
        data = await cv.read(MAX_CV_BYTES + 1)
        try:
            async with cv_slots:
                text = await asyncio.to_thread(extract_text_isolated, data, cv.filename or "",
                                               cv.content_type or "")
        except CVError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            del data
        return await do_search(requirements, location, limit, None, cv_text=text)

    @app.post("/v1/understand", response_model=Requirements, tags=["search"],
              summary="See how a description is understood, without searching")
    async def understand(request: Request, body: SearchBody = Body(...)):
        guard(request)
        return await js.understand(text=body.requirements, location=body.location)

    @app.get("/v1/sources", tags=["info"], summary="Where jobs come from")
    async def sources(request: Request):
        guard(request, limited=False)
        return {"sources": js.source_list(), "indexed_jobs": js.store.job_count(),
                "company_boards": len(js.store.boards())}

    # -- alerts -------------------------------------------------------------------------------------
    @app.post("/v1/alerts", tags=["alerts"], summary="Save a search; new matches arrive by webhook and RSS")
    async def create_alert(request: Request, body: AlertBody = Body(...)):
        guard(request)
        if body.understood is not None:
            req = body.understood
            if body.requirements or body.location:
                from .service import merge
                req = merge(req, await js.understand(text=body.requirements, location=body.location))
        else:
            if not (body.requirements.strip() or body.location.strip()):
                raise HTTPException(400, "describe what you are looking for")
            req = await js.understand(text=body.requirements, location=body.location)
        if not (req.titles or req.skills or req.keywords):
            raise HTTPException(422, "add a job title or a few skills so the alert knows what to look for")
        try:
            alert_id, token = await alerts.create(js, req, body.every_hours, body.webhook_url)
        except (ValueError, FetchError) as e:
            raise HTTPException(400, str(e)) from e
        base = settings.base_url
        return {"id": alert_id, "token": token, "every_hours": body.every_hours,
                "feed_url": f"{base}/v1/alerts/{alert_id}/feed.xml?token={token}",
                "manage_url": f"{base}/v1/alerts/{alert_id}?token={token}",
                "note": "Keep the token: it is shown only once and is needed to read or delete this alert."}

    def get_alert(alert_id: str, token: str) -> dict:
        a = js.store.alert(alert_id)
        if not a or not alerts.token_ok(a, token):
            raise HTTPException(404, "no such alert")
        return a

    @app.get("/v1/alerts/{alert_id}", tags=["alerts"], summary="An alert and its latest matches")
    async def alert_info(alert_id: str, token: str = Query(..., max_length=100)):
        a = get_alert(alert_id, token)
        return {"id": a["id"], "requirements": Requirements.model_validate_json(a["text"]),
                "every_hours": a["every_hours"], "last_run": a["last_run"] or None, "next_run": a["next_run"],
                "last_error": a["last_error"], "matches": [h["match"] for h in js.store.hits(alert_id, 30)]}

    @app.get("/v1/alerts/{alert_id}/feed.xml", tags=["alerts"], summary="RSS feed of new matches")
    async def alert_feed(alert_id: str, token: str = Query(..., max_length=100)):
        a = get_alert(alert_id, token)
        return Response(alerts.rss(js, a), media_type="application/rss+xml")

    @app.delete("/v1/alerts/{alert_id}", tags=["alerts"], summary="Delete an alert")
    async def alert_delete(alert_id: str, token: str = Query(..., max_length=100)):
        get_alert(alert_id, token)
        js.store.delete_alert(alert_id)
        return {"ok": True}

    @app.post("/v1/alerts/{alert_id}/run", tags=["alerts"], summary="Run an alert now")
    async def alert_run(request: Request, alert_id: str, token: str = Query(..., max_length=100)):
        guard(request)
        a = get_alert(alert_id, token)
        return {"new_matches": await alerts.run_one(js, a)}

    return app

