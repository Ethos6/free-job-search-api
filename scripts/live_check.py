"""Search the real job sources end to end and print what comes back. Used by the "Live check"
GitHub workflow; you can run it yourself too:

    JOBS_SEARCH_URL=http://localhost:8000 python scripts/live_check.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobsearch.config import Settings  # noqa: E402
from jobsearch.cv import extract_text  # noqa: E402
from jobsearch.indexer import refresh_due, seed  # noqa: E402
from jobsearch.service import JobSearch  # noqa: E402

REQUESTS = [
    "Senior backend developer, Python and Django, 5+ years. Remote in Europe. Full-time. No crypto or gambling.",
    "Registered nurse in Berlin, Germany. I speak English and German.",
    "Junior data analyst in New York or remote US. SQL, Excel, Tableau. At least $60k.",
    "Product designer, Figma and user research, London or remote UK.",
    "Machine learning engineer, PyTorch, LLMs, remote anywhere, posted in the last 2 weeks.",
    "Customer support specialist, remote, part-time is fine.",
]


async def main() -> int:
    s = Settings.from_env()
    s.data_dir = Path(os.environ.get("JOBS_DATA") or tempfile.mkdtemp())
    s.background = False
    js = JobSearch(s)
    try:
        seed(js.ctx)
        stats = await refresh_due(js.ctx, max_boards=int(os.environ.get("LIVE_BOARDS", "80")), concurrency=6)
        print(f"Index: {js.store.job_count()} jobs from {stats['boards']} boards and {stats['feeds']} feeds\n")
        found_any = 0
        for text in REQUESTS:
            req = await js.understand(text=text)
            res = await js.search(req, limit=5)
            found_any += bool(res.results)
            print(f"## {text}\n   understood: roles={req.titles} skills={req.skills[:6]} "
                  f"places={[p.name for p in req.places]} work={req.work_modes} level={req.seniority}")
            print(f"   {res.total_found} matches in {res.elapsed_ms} ms")
            for m in res.results:
                j = m.job
                print(f"   {m.score:5.1f}  {j.title[:60]} | {j.company[:30]} | {j.location[:40]} | {j.source_name}")
                print(f"          {j.url}")
            print("   sources: " + ", ".join(f"{x.id}={x.jobs if x.ok and not x.skipped else 'off' if x.skipped else x.error}"
                                           f"({x.elapsed_ms}ms)" for x in res.sources) + "\n")
        cv = Path(__file__).resolve().parent.parent / "tests" / "cv_sample.pdf"
        req = await js.understand(cv_text=extract_text(cv.read_bytes(), "cv.pdf"), location="remote")
        res = await js.search(req, limit=5)
        print(f"## CV (data engineer, Bengaluru) + 'remote': {res.total_found} matches")
        for m in res.results:
            print(f"   {m.score:5.1f}  {m.job.title[:60]} | {m.job.company[:30]} | {m.job.source_name}")
        if js.store.job_count() < 500 or found_any < len(REQUESTS) // 2:
            print("\nFAIL: too few jobs indexed or too many empty searches")
            return 1
        return 0
    finally:
        await js.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
