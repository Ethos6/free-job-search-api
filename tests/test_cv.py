import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from jobsearch.cv import CVError, experience_years, extract_text, requirements_from_cv

PDF = Path(__file__).parent / "cv_sample.pdf"

TEXT_CV = """Alex Morgan
Registered Nurse
Manchester, UK · alex@example.com

Professional Experience
Staff Nurse (ICU), Manchester Royal Infirmary
03/2019 - present
Critical care, patient care, EMR (Epic), medication administration.
Healthcare Assistant, NHS
2016 - 2019

Skills
Patient care, nursing, EMR, phlebotomy

Languages
English (native), Spanish (B2)
"""


def make_docx(text: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_pdf_cv():
    req = requirements_from_cv(extract_text(PDF.read_bytes(), "cv.pdf"))
    assert req.titles[0] == "data engineer"
    assert {"python", "spark", "airflow", "aws", "snowflake"} <= set(req.skills)
    assert req.home_country == "IN" and req.places[0].name == "Bengaluru"
    assert req.seniority == "senior" and req.years_experience >= 9
    assert "kannada" in req.languages
    dumped = req.model_dump_json()
    assert "priya" not in dumped.lower() and "example.com" not in dumped  # no personal details carried


def test_docx_and_text_cv():
    for data, name in ((make_docx(TEXT_CV), "cv.docx"), (TEXT_CV.encode(), "cv.txt")):
        req = requirements_from_cv(extract_text(data, name))
        assert req.titles[0] == "nurse", name
        assert "patient care" in req.skills and req.home_country == "GB"
        assert set(req.languages) >= {"english", "spanish"}


def test_experience_years_merges_overlaps():
    text = "Jan 2018 - Dec 2019\nJun 2019 - Present\n2010 - 2011"
    assert experience_years(text, today=date(2026, 6, 1)) == pytest.approx(9.4, abs=0.1)
    assert experience_years("no dates here") is None


@pytest.mark.parametrize("data,name,msg", [
    (b"", "cv.pdf", "empty"),
    (b"x" * (5 * 1024 * 1024 + 1), "cv.pdf", "larger than 5 MB"),
    (b"%PDF-1.4 broken", "cv.pdf", "could not read"),
    (b"PK\x03\x04garbage", "cv.docx", "could not read"),
    (b"{\\rtf1 hello}", "cv.rtf", "not supported"),
    (b"short", "cv.txt", "no text"),
])
def test_bad_files(data, name, msg):
    with pytest.raises(CVError, match=msg):
        extract_text(data, name)


def test_docx_entities_are_not_resolved():
    evil = make_docx("x").replace(b"x", b"x")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:r><w:t>Python developer &e; with ten years of experience in Django</w:t></w:r></w:p>'
                   '</w:body></w:document>')
    text = extract_text(buf.getvalue(), "cv.docx")
    assert "root:" not in text
    assert evil
