"""Settings, read from environment variables (or a .env file in the working folder)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import __version__

REPO = "https://github.com/Ethos6/free-job-search-api"


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name, default))))
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = Path("./data")
    search_url: Optional[str] = None  # a FreeSearch API (or compatible) base URL for web search
    llm_url: Optional[str] = None  # OpenAI-compatible base URL, e.g. http://localhost:11434/v1 for Ollama
    llm_model: str = "llama3.1"
    llm_key: Optional[str] = None
    big_sites: bool = False  # LinkedIn guest pages and job pages on Indeed/Glassdoor etc. (their terms forbid it)
    sources: Optional[set[str]] = None  # None = all available
    companies: list[str] = field(default_factory=list)  # extra boards, e.g. "greenhouse:stripe"
    api_keys: set[str] = field(default_factory=set)
    rate_limit: int = 20  # searches per minute per client
    timeout: float = 20.0  # seconds a search may take in total
    max_alerts: int = 200
    refresh_hours: float = 6.0
    background: bool = True  # keep the local job index fresh in the background
    user_agent: str = f"free-job-search-api/{__version__} (+{REPO})"
    allow_private_urls: bool = False  # tests only
    trust_proxy: bool = False
    base_url: str = "http://localhost:8000"
    fx_rates: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        e = os.environ.get
        sources = {s.strip() for s in e("JOBS_SOURCES", "").split(",") if s.strip()} or None
        fx = {}
        if e("JOBS_FX_RATES"):
            try:
                fx = {k.upper(): float(v) for k, v in json.loads(e("JOBS_FX_RATES", "{}")).items()}
            except (ValueError, AttributeError):
                fx = {}
        return cls(
            data_dir=Path(e("JOBS_DATA", "./data")).resolve(),
            search_url=(e("JOBS_SEARCH_URL") or None),
            llm_url=(e("JOBS_LLM_URL") or None),
            llm_model=e("JOBS_LLM_MODEL", "llama3.1"),
            llm_key=(e("JOBS_LLM_KEY") or None),
            big_sites=_flag("JOBS_ENABLE_BIG_SITES"),
            sources=sources,
            companies=[c.strip() for c in e("JOBS_COMPANIES", "").split(",") if c.strip()],
            api_keys={k.strip() for k in e("JOBS_API_KEYS", "").split(",") if k.strip()},
            rate_limit=_int("JOBS_RATE_LIMIT", 20, 0, 10_000),
            timeout=float(_int("JOBS_TIMEOUT", 20, 3, 120)),
            max_alerts=_int("JOBS_MAX_ALERTS", 200, 0, 100_000),
            refresh_hours=float(_int("JOBS_REFRESH_HOURS", 6, 1, 168)),
            background=_flag("JOBS_BACKGROUND", True),
            user_agent=e("JOBS_USER_AGENT") or cls.user_agent,
            trust_proxy=_flag("JOBS_TRUST_PROXY"),
            base_url=e("JOBS_BASE_URL", "http://localhost:8000").rstrip("/"),
            fx_rates=fx,
        )

    def source_enabled(self, source_id: str) -> bool:
        return self.sources is None or source_id in self.sources
