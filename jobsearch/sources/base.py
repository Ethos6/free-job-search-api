"""What every job source looks like."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Optional

from ..models import Job, Requirements

if TYPE_CHECKING:
    from ..config import Settings
    from ..http import Http
    from ..store import Store


@dataclass
class Context:
    http: "Http"
    settings: "Settings"
    store: "Store"


class Source:
    """A place jobs come from.

    kind:
      - "board": a company careers system (Greenhouse, Lever, ...). Boards are indexed locally
        in the background; `fetch_board` downloads one company's open jobs.
      - "feed":  a public job board with an API (Remotive, Remote OK, ...). Indexed locally too.
      - "live":  asked at search time with the person's keywords (The Muse, Hacker News, web search).
    """
    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    kind: ClassVar[str] = "live"
    homepage: ClassVar[str] = ""
    terms: ClassVar[str] = ""  # what the source asks of us, shown in /v1/sources
    big_site: ClassVar[bool] = False  # needs JOBS_ENABLE_BIG_SITES

    def available(self, ctx: Context) -> Optional[str]:
        """None if usable, otherwise the reason it is skipped."""
        if not ctx.settings.source_enabled(self.id):
            return "turned off in JOBS_SOURCES"
        if self.big_site and not ctx.settings.big_sites:
            return "off by default (set JOBS_ENABLE_BIG_SITES=1; see README)"
        return None

    # boards
    async def fetch_board(self, ctx: Context, token: str) -> tuple[str, list[Job]]:
        raise NotImplementedError

    def board_url(self, token: str) -> str:
        return ""

    # feeds
    async def fetch_feed(self, ctx: Context) -> list[Job]:
        raise NotImplementedError

    # live
    async def search(self, ctx: Context, req: Requirements) -> list[Job]:
        raise NotImplementedError
