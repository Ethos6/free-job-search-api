"""Command line: run the API, search from the terminal, run the MCP server."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Settings


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .api import create_app
    settings = Settings.from_env()
    if args.port:
        settings.base_url = settings.base_url if settings.base_url != "http://localhost:8000" else \
            f"http://localhost:{args.port}"
    uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=settings.trust_proxy,
                log_level="info")


async def _search(args: argparse.Namespace) -> int:
    from .cv import CVError, extract_text
    from .mcp_server import format_results
    from .service import JobSearch
    settings = Settings.from_env()
    js = JobSearch(settings)
    try:
        if args.refresh:
            from .indexer import refresh_due, seed
            seed(js.ctx)
            print("Refreshing the local index (first run takes a few minutes)...", file=sys.stderr)
            print(await refresh_due(js.ctx, max_boards=500, concurrency=6), file=sys.stderr)
        cv_text = ""
        if args.cv:
            try:
                cv_text = extract_text(Path(args.cv).read_bytes(), args.cv)
            except (CVError, OSError) as e:
                print(f"Could not read the CV: {e}", file=sys.stderr)
                return 2
        req = await js.understand(text=" ".join(args.requirements), cv_text=cv_text, location=args.location)
        if not (req.titles or req.skills or req.keywords):
            print("Say what kind of job: a job title or a few skills.", file=sys.stderr)
            return 2
        res = await js.search(req, limit=args.n)
        print(res.model_dump_json(indent=2) if args.json else format_results(res))
        return 0
    finally:
        await js.close()


async def _refresh() -> None:
    from .indexer import refresh_due, seed
    from .service import JobSearch
    js = JobSearch(Settings.from_env())
    try:
        seed(js.ctx)
        print(json.dumps(await refresh_due(js.ctx, max_boards=1000, concurrency=6)))
    finally:
        await js.close()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="jobsearch", description="Free Job Search API")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the API and web page")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s = sub.add_parser("search", help="search from the terminal")
    s.add_argument("requirements", nargs="*", help="what you are looking for, in your own words")
    s.add_argument("--cv", help="path to your CV (PDF, .docx or .txt)")
    s.add_argument("--location", default="")
    s.add_argument("-n", type=int, default=15)
    s.add_argument("--json", action="store_true")
    s.add_argument("--refresh", action="store_true", help="fill the local index first")
    sub.add_parser("refresh", help="refresh the local job index once")
    s = sub.add_parser("mcp", help="run the MCP server for AI agents")
    s.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8002)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    if args.cmd == "serve":
        _serve(args)
    elif args.cmd == "search":
        if not args.requirements and not args.cv:
            p.error("give your requirements or --cv")
        sys.exit(asyncio.run(_search(args)))
    elif args.cmd == "refresh":
        asyncio.run(_refresh())
    elif args.cmd == "mcp":
        from .mcp_server import run
        run(args.transport, args.host, args.port)


if __name__ == "__main__":
    main()
