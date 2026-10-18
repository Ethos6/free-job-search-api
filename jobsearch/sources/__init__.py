"""All job sources."""
from __future__ import annotations

from .ats import BOARD_SOURCES, SmartRecruiters
from .base import Context, Source
from .feeds import FEED_SOURCES
from .live import LIVE_SOURCES
from .web import WebSearch

LIVE: dict[str, Source] = {**LIVE_SOURCES, "smartrecruiters": SmartRecruiters(), "web": WebSearch()}
ALL: dict[str, Source] = {**BOARD_SOURCES, **FEED_SOURCES, **LIVE}

__all__ = ["ALL", "BOARD_SOURCES", "FEED_SOURCES", "LIVE", "Context", "Source"]
