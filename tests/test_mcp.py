from datetime import datetime, timezone

from jobsearch.mcp_server import build_server, format_results
from jobsearch.models import Job, Match, SearchResponse
from jobsearch.parse import parse


async def test_tools_registered():
    server = build_server()
    tools = {t.name for t in await server.list_tools()}
    assert {"search_jobs", "search_jobs_from_cv", "job_sources"} <= tools


def test_format_results():
    req = parse("python developer in Berlin")
    job = Job(title="Backend Developer", company="Acme", url="https://x/1", source="greenhouse",
              source_name="Greenhouse", location="Berlin", posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    res = SearchResponse(requirements=req, results=[Match(job=job, score=88.4, reasons=["Uses Python"],
                                                          warnings=["Salary not listed"])],
                         total_found=1, sources=[], elapsed_ms=5)
    text = format_results(res)
    assert "Backend Developer at Acme (88/100)" in text and "https://x/1" in text
    assert "Why: Uses Python" in text and "Check: Salary not listed" in text
