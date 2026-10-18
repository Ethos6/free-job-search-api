"""Read a CV (PDF, Word .docx, or text) and work out what jobs fit the person.

The CV is processed in memory and never stored or sent to job sites. Only the derived
search words (roles, skills, place) leave the server, and the CV text is not echoed back.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from datetime import date
from typing import Optional

from lxml import etree

from . import vocab
from .models import Place, Requirements
from .parse import _languages, _places

MAX_CV_BYTES = 5 * 1024 * 1024
MAX_PAGES = 12


class CVError(ValueError):
    pass


def extract_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Plain text from a CV file."""
    if len(data) > MAX_CV_BYTES:
        raise CVError("the file is larger than 5 MB")
    if not data:
        raise CVError("the file is empty")
    name = filename.lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf") or "pdf" in content_type:
        text = _pdf(data)
    elif data[:2] == b"PK" or name.endswith(".docx"):
        text = _docx(data)
    elif name.endswith((".doc", ".rtf")) or data[:5] == b"{\\rtf":
        raise CVError("old .doc and .rtf files are not supported; save the CV as PDF or .docx")
    else:
        text = _plain(data)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 40:
        raise CVError("no text found in the file; if it is a scanned image, save it as a text PDF or .docx")
    return text[:60000]


def _child(conn, data: bytes, filename: str, content_type: str, cpu_seconds: int) -> None:
    """Runs in a separate process with hard limits, so a hostile file cannot hurt the server."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 2))
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    except (ImportError, ValueError, OSError):  # pragma: no cover - not available on this OS
        pass
    try:
        conn.send(("ok", extract_text(data, filename, content_type)))
    except CVError as e:
        conn.send(("cv", str(e)))
    except BaseException as e:  # noqa: BLE001
        conn.send(("err", type(e).__name__))
    finally:
        conn.close()


def extract_text_isolated(data: bytes, filename: str = "", content_type: str = "", timeout: float = 20.0) -> str:
    """extract_text() in a child process that is killed if it takes too long or uses too much memory."""
    import multiprocessing as mp
    if len(data) > MAX_CV_BYTES:
        raise CVError("the file is larger than 5 MB")
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, data, filename, content_type, int(timeout)), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise CVError("the CV took too long to read; try a simpler PDF or a .docx")
        try:
            kind, value = parent.recv()
        except EOFError as e:
            raise CVError("could not read this file (it may be damaged or too complex)") from e
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(2)
    if kind == "ok":
        return value
    if kind == "cv":
        raise CVError(value)
    raise CVError("could not read this file (it may be damaged or too complex)")


def _pdf(data: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text as pdf_text
        from pdfminer.layout import LAParams
    except ImportError as e:  # pragma: no cover
        raise CVError("PDF support is not installed (pip install pdfminer.six)") from e
    try:
        return pdf_text(io.BytesIO(data), maxpages=MAX_PAGES, laparams=LAParams(line_margin=0.3))
    except Exception as e:  # noqa: BLE001 - broken or encrypted PDFs
        raise CVError("could not read this PDF (it may be encrypted or damaged)") from e


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 20 * 1024 * 1024:
                raise CVError("the document is too large")
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError, OSError, EOFError) as e:
        raise CVError("could not read this Word file; save it as .docx or PDF") from e
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    try:
        root = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError as e:
        raise CVError("could not read this Word file; save it as .docx or PDF") from e
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for p in root.iter("{%s}p" % ns["w"]):
        parts = []
        for node in p.iter():
            if not isinstance(node.tag, str):
                continue  # entity references, comments, processing instructions
            tag = etree.QName(node).localname
            if tag == "t":
                parts.append(node.text or "")
                parts += [child.tail or "" for child in node]  # text after skipped entity references
            elif tag == "tab":
                parts.append("\t")
        lines.append("".join(parts))
    return "\n".join(lines)


def _plain(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace")
    for enc in ("utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# -- understanding the CV -------------------------------------------------------------------------

SECTION = re.compile(r"^\s*(work experience|professional experience|experience|employment history|employment|"
                     r"career history|work history|skills|technical skills|core skills|key skills|competencies|"
                     r"education|languages|certifications|projects|summary|profile|about me|objective|"
                     r"interests|references|publications|awards)\s*:?\s*$", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]{{0,6}}"
_DATE = r"(?:(?P<m{n}>" + _MONTH + r")\.?[ \t]+|(?P<mm{n}>\d{{1,2}})[/.-])?(?P<y{n}>(?:19|20)\d{{2}})"
RANGE = re.compile(_DATE.format(n=1) + r"[ \t]*(?:-|–|—|to|until|till)[ \t]*(?:(?P<now>present|current|now|"
                   r"today|ongoing|date)\b|" + _DATE.format(n=2) + r")", re.I)


def sections(text: str) -> dict[str, str]:
    out: dict[str, list[str]] = {"_top": []}
    current = "_top"
    for line in text.splitlines():
        m = SECTION.match(line)
        if m and len(line.strip()) < 40:
            key = m.group(1).lower()
            current = ("experience" if "experience" in key or "employment" in key or "history" in key
                       else "skills" if "skill" in key or "competenc" in key else key)
            out.setdefault(current, [])
            continue
        out.setdefault(current, []).append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def experience_years(text: str, today: Optional[date] = None) -> Optional[float]:
    today = today or date.today()
    spans = []
    for m in RANGE.finditer(text):
        start = _ym(m.group("m1"), m.group("mm1"), m.group("y1"))
        if m.group("now"):
            end = (today.year, today.month)
        else:
            end = _ym(m.group("m2"), m.group("mm2"), m.group("y2"))
        if not start or not end or end < start or start[0] < 1960 or end > (today.year, 12):
            continue
        spans.append((start[0] * 12 + start[1], end[0] * 12 + end[1]))
    if not spans:
        return None
    spans.sort()
    total, (cs, ce) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += ce - cs
            cs, ce = s, e
    total += ce - cs
    years = round(total / 12, 1)
    return years if 0 < years <= 50 else None


def _ym(mon: Optional[str], mm: Optional[str], year: str) -> Optional[tuple[int, int]]:
    y = int(year)
    if mon:
        m = MONTHS.get(mon[:3].lower())
        if m is None:
            return (y, 1)
        return (y, m)
    if mm:
        m = int(mm)
        return (y, m) if 1 <= m <= 12 else (y, 1)
    return (y, 1)


def requirements_from_cv(text: str) -> Requirements:
    secs = sections(text)
    top = secs.get("_top", "")
    exp = secs.get("experience", "")
    summary = " ".join(secs.get(k, "") for k in ("summary", "profile", "about me", "objective"))

    # roles: the headline and the most recent jobs count most
    role_score: Counter = Counter()
    for weight, chunk in ((5, "\n".join(top.splitlines()[:8])), (2, summary),
                          (4, "\n".join(exp.splitlines()[:12])), (1, exp)):
        for i, r in enumerate(vocab.find_roles(chunk)):
            role_score[r] += weight - min(i, 3) * 0.5
    titles = [r for r, _ in role_score.most_common(3)]

    # skills: frequency, with the skills section counting double
    skill_score: Counter = Counter()
    for weight, chunk in ((2, secs.get("skills", "")), (1, text)):
        pat, canon = vocab.skill_lookup()
        for m in pat.finditer(chunk):
            name = canon[m.group(1).lower()]
            if name in vocab.find_skills(m.group(0)) or len(m.group(1)) > 2:
                skill_score[name] += weight
    skills = [s for s, _ in skill_score.most_common(14)]

    # place: from the contact block at the top
    places = _places(["\n".join(top.splitlines()[:15])])
    places = [p for p in places if p.kind in ("city", "country")][:2]
    home = next((p.country for p in places if p.country), None)

    years = experience_years(exp or text)
    seniority = None
    latest_line = next((l for l in exp.splitlines() if vocab.find_roles(l)), "") or top
    for level, words in (("principal", ["principal", "staff engineer", "architect"]),
                         ("lead", ["lead", "head of", "team lead"]), ("director", ["director", "vp "]),
                         ("senior", ["senior", "sr."]), ("junior", ["junior", "jr.", "graduate", "trainee"]),
                         ("intern", ["intern"])):
        if any(w in latest_line.lower() for w in words):
            seniority = level
            break
    if seniority is None and years is not None:
        seniority = "junior" if years < 2 else "mid" if years < 5 else "senior"

    langs = _languages(secs.get("languages", "") + "\n" + text[:3000])
    for line in secs.get("languages", "").splitlines():
        for l in vocab.SPOKEN_LANGUAGES:
            if re.search(r"\b" + l + r"\b", line, re.I) and l not in langs:
                langs.append(l)

    return Requirements(
        text="", titles=titles, skills=skills, places=[Place(**p.model_dump()) for p in places],
        home_country=home, seniority=seniority, years_experience=years, languages=langs,
        understood_by="rules")
