"""Optional AI help, through any OpenAI-compatible chat API (a free local Ollama works:
JOBS_LLM_URL=http://localhost:11434/v1, JOBS_LLM_MODEL=llama3.1).

Used for two things, and only when configured:
  1. understanding long or unusual requests and CVs more precisely;
  2. re-ordering the top matches by reading them.
Everything falls back to the built-in rules if the model is slow, down or returns junk.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import ValidationError

from .models import SENIORITY_ORDER, Match, Place, Requirements
from .sources.base import Context

log = logging.getLogger("jobsearch.llm")

SCHEMA_HINT = {
    "titles": ["job titles to search for, most important first (max 4)"],
    "skills": ["skills the person has or wants to use (max 15)"],
    "nice_skills": ["nice-to-have skills"],
    "keywords": ["industries or domains they prefer"],
    "exclude": ["words, companies or industries they want to avoid"],
    "places": [{"name": "city, country or region", "country": "ISO 3166 alpha-2 or null",
                "kind": "city|region|country|continent"}],
    "home_country": "ISO alpha-2 of where they live, or null",
    "work_modes": ["remote|hybrid|onsite; empty if any"],
    "seniority": "|".join(SENIORITY_ORDER) + " or null",
    "years_experience": "number or null",
    "salary_min": "number or null", "salary_currency": "ISO 4217 or null",
    "salary_period": "year|month|week|day|hour",
    "employment_types": ["full_time|part_time|contract|internship|temporary|freelance"],
    "visa_sponsorship": "true if they need sponsorship, else null",
    "posted_within_days": "number or null", "languages": ["spoken languages, lower case"],
}


async def _chat(ctx: Context, system: str, user: str, timeout: float = 25.0) -> Optional[str]:
    s = ctx.settings
    headers = {"Authorization": f"Bearer {s.llm_key}"} if s.llm_key else None
    payload = {"model": s.llm_model, "temperature": 0, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    try:
        data = await ctx.http.post_json(s.llm_url.rstrip("/") + "/chat/completions", payload, untrusted=False,
                                        headers=headers, timeout=timeout)
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001 - AI is optional; never fail the search because of it
        log.info("AI request failed: %s", e)
        return None


def _json(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


async def understand(ctx: Context, text: str = "", cv_text: str = "", location: str = "",
                     timeout: float = 25.0) -> Optional[Requirements]:
    system = ("You turn a job seeker's request and/or CV into search requirements. Answer with one JSON object "
              "only, using exactly these keys:\n" + json.dumps(SCHEMA_HINT) +
              "\nWhat the person typed overrides the CV. Do not invent facts. Never include their name, email, "
              "phone or address.")
    parts = []
    if text:
        parts.append(f"What they typed:\n{text[:4000]}")
    if location:
        parts.append(f"Location they typed: {location[:200]}")
    if cv_text:
        parts.append(f"Their CV:\n{cv_text[:12000]}")
    data = _json(await _chat(ctx, system, "\n\n".join(parts), timeout=timeout))
    if not data:
        return None
    try:
        data["places"] = [Place(**p) for p in data.get("places") or [] if isinstance(p, dict) and p.get("name")]
        for k in ("seniority", "salary_currency", "home_country"):
            if data.get(k) in ("", "null"):
                data[k] = None
        if data.get("seniority") not in SENIORITY_ORDER:
            data["seniority"] = None
        clean = {k: v for k, v in data.items() if k in Requirements.model_fields and v is not None}
        req = Requirements(**clean)
    except (ValidationError, TypeError, ValueError):
        return None
    req.text = text
    req.understood_by = "ai"
    return req


async def rerank(ctx: Context, req: Requirements, matches: list[Match], top: int = 30,
                 timeout: float = 40.0) -> list[Match]:
    head, tail = matches[:top], matches[top:]
    listing = "\n".join(
        f"{i}. {m.job.title} | {m.job.company} | {m.job.location} | {m.job.description[:400].replace(chr(10), ' ')}"
        for i, m in enumerate(head))
    system = ("Rate how well each job fits the job seeker, 0-10. Answer with JSON only: "
              '{"ratings": [{"i": <number>, "score": <0-10>, "why": "<max 12 words>"}]}')
    user = f"Job seeker wants:\n{req.model_dump_json(exclude={'text'})}\n\nJobs:\n{listing}"
    data = _json(await _chat(ctx, system, user, timeout=timeout))
    if not data or not isinstance(data.get("ratings"), list):
        return matches
    by_i = {}
    for r in data["ratings"]:
        try:
            by_i[int(r["i"])] = (max(0.0, min(10.0, float(r["score"]))), str(r.get("why", ""))[:120])
        except (KeyError, TypeError, ValueError):
            continue
    for i, m in enumerate(head):
        if i in by_i:
            ai_score, why = by_i[i]
            m.score = round(0.6 * m.score + 4.0 * ai_score, 1)
            if why:
                m.reasons.append(f"AI: {why}")
    out = head + tail
    out.sort(key=lambda m: m.score, reverse=True)
    return out
