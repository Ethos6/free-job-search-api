"""MCP server: lets Claude, Cursor and other AI agents search jobs for a person.

    jobsearch mcp                                  # stdio, for desktop apps
    jobsearch mcp --transport streamable-http      # http://127.0.0.1:8002/mcp
"""
from __future__ import annotations

from typing import Any, Optional

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from .config import Settings
from .models import SearchResponse
from .service import JobSearch

_js: Optional[JobSearch] = None


async def _get() -> JobSearch:
    global _js
    if _js is None:
        _js = JobSearch(Settings.from_env())
        await _js.start()
    return _js


def format_results(res: SearchResponse) -> str:
    r = res.requirements
    head = [f"Understood: roles={', '.join(r.titles) or '-'}; skills={', '.join(r.skills[:8]) or '-'}; "
            f"places={', '.join(p.name for p in r.places) or '-'}; work={', '.join(r.work_modes) or 'any'}"
            + (f"; seniority={r.seniority}" if r.seniority else "")
            + (f"; min salary={r.salary_min:g} {r.salary_currency}/{r.salary_period}" if r.salary_min else ""),
            f"{res.total_found} matching jobs; showing {len(res.results)}.", ""]
    lines = []
    for i, m in enumerate(res.results, 1):
        j = m.job
        lines.append(f"{i}. {j.title} at {j.company or '?'} ({m.score:.0f}/100)\n"
                     f"   {j.location or '-'} · via {j.source_name or j.source}"
                     + (f" · posted {j.posted_at.date()}" if j.posted_at else "") + f"\n   {j.url}"
                     + (f"\n   Why: {'; '.join(m.reasons[:4])}" if m.reasons else "")
                     + (f"\n   Check: {'; '.join(m.warnings[:3])}" if m.warnings else ""))
    return "\n".join(head + lines) if lines else "\n".join(head) + "No matching jobs found. Try fewer limits."


def build_server() -> Any:
    server = MCPServer(
        "jobsearch",
        instructions="Free job search across company career boards, public job boards and the web. "
                     "Use search_jobs with the person's own words (role, skills, place, remote, salary, things to "
                     "avoid). If they share a CV, use search_jobs_from_cv. Always show the job links.")

    @server.tool()
    async def search_jobs(requirements: str, location: str = "", limit: int = 10) -> str:
        """Find jobs that match what a person wants, described in plain words.

        Args:
            requirements: e.g. "Senior Python backend developer, 6 years, remote in Europe, at least €80k, no crypto"
            location: optional place, e.g. "Berlin" or "remote"
            limit: number of results, 1-30
        """
        js = await _get()
        req = await js.understand(text=requirements, location=location)
        if not (req.titles or req.skills or req.keywords):
            return "Please say what kind of job: a job title or a few skills."
        return format_results(await js.search(req, limit=max(1, min(limit, 30))))

    @server.tool()
    async def search_jobs_from_cv(cv_text: str, requirements: str = "", location: str = "", limit: int = 10) -> str:
        """Find jobs that fit a person's CV. Anything in `requirements` or `location` overrides the CV.

        Args:
            cv_text: the CV as plain text
            requirements: optional extra wishes, e.g. "remote only, no agencies"
            location: optional place
            limit: number of results, 1-30
        """
        js = await _get()
        req = await js.understand(text=requirements, cv_text=cv_text[:60000], location=location)
        if not (req.titles or req.skills):
            return "Could not find job titles or skills in that CV."
        return format_results(await js.search(req, limit=max(1, min(limit, 30))))

    @server.tool()
    async def job_sources() -> str:
        """List where jobs come from and whether each source is on."""
        js = await _get()
        rows = [f"- {s['name']} ({s['kind']}): {'on' if s['enabled'] else 'off: ' + str(s['note'])}"
                for s in js.source_list()]
        return f"{js.store.job_count()} jobs indexed from {len(js.store.boards())} company boards.\n" + "\n".join(rows)

    return server


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8002) -> None:
    server = build_server()
    if transport == "stdio":
        server.run("stdio")
    else:
        server.settings.host = host
        server.settings.port = port
        server.run(transport)
