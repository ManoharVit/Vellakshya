"""
Tests for Step 3: OCR Lane, Scanned-PDF Detection, PyMuPDF4LLM Markdown,
and Pandoc DOCX Path.
"""

from __future__ import annotations

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import converter, ocr
from app.services.inspection import inspect_pdf


@pytest.fixture
def digital_pdf_bytes() -> bytes:
    """Creates a clean vector digital PDF with headings and body text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(50, 70), "Vellakshya Enterprise Document Intelligence", fontsize=18)
    page.insert_text(
        fitz.Point(50, 110), "Architectural modernization and verification report.", fontsize=12
    )
    page.insert_text(
        fitz.Point(50, 150),
        "This document contains clean selectable digital text across all sections and paragraphs.",
        fontsize=10,
    )
    b = doc.tobytes()
    doc.close()
    return b


@pytest.fixture
def scanned_pdf_bytes() -> bytes:
    """Creates a simulated scanned PDF with a raster image and zero selectable text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Create a dummy bitmap image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 500, 700), 0)
    pix.clear_with(240)
    page.insert_image(fitz.Rect(50, 50, 545, 750), pixmap=pix)
    b = doc.tobytes()
    doc.close()
    return b


@pytest.fixture
def mixed_pdf_bytes(digital_pdf_bytes: bytes, scanned_pdf_bytes: bytes) -> bytes:
    """Creates a 2-page mixed PDF: Page 1 digital text, Page 2 scanned bitmap."""
    doc1 = fitz.open(stream=digital_pdf_bytes, filetype="pdf")
    doc2 = fitz.open(stream=scanned_pdf_bytes, filetype="pdf")
    doc1.insert_pdf(doc2)
    b = doc1.tobytes()
    doc1.close()
    doc2.close()
    return b


def test_classify_document_digital(digital_pdf_bytes: bytes):
    """Verifies that clean vector PDFs are classified as 'digital' with no OCR recommendation."""
    result = ocr.classify_document(digital_pdf_bytes)
    assert result["classification"] == "digital"
    assert result["ocr_recommended"] is False
    assert result["page_count"] == 1
    assert len(result["scanned_pages"]) == 0
    assert result["per_page_confidence"][0]["confidence_score"] >= 0.70


def test_classify_document_scanned(scanned_pdf_bytes: bytes):
    """Verifies that bitmap/image-only PDFs are classified as 'scanned' requiring OCR."""
    result = ocr.classify_document(scanned_pdf_bytes)
    assert result["classification"] == "scanned"
    assert result["ocr_recommended"] is True
    assert result["page_count"] == 1
    assert 1 in result["scanned_pages"]
    assert result["per_page_confidence"][0]["ocr_needed"] is True


def test_classify_document_mixed(mixed_pdf_bytes: bytes):
    """Verifies that multi-page documents with mixed content are flagged appropriately."""
    result = ocr.classify_document(mixed_pdf_bytes)
    assert result["classification"] == "mixed"
    assert result["ocr_recommended"] is True
    assert result["page_count"] == 2
    assert 2 in result["scanned_pages"]
    assert 1 in result["digital_pages"]


def test_inspection_includes_classification(digital_pdf_bytes: bytes):
    """Verifies inspect_pdf embeds classification and confidence metadata."""
    info = inspect_pdf(digital_pdf_bytes)
    assert "classification" in info
    assert "document_classification" in info
    assert "ocr_recommended" in info
    assert info["classification"] == "digital"
    assert info["ocr_recommended"] is False


def test_ocr_searchable_pdf(digital_pdf_bytes: bytes):
    """Verifies that make_searchable_pdf produces a valid PDF and returns processing statistics."""
    out_pdf, stats = ocr.ocr_lane.make_searchable_pdf(digital_pdf_bytes)
    assert out_pdf.startswith(b"%PDF")
    assert stats["pages_processed"] == 1
    doc = fitz.open(stream=out_pdf, filetype="pdf")
    assert len(doc) == 1
    doc.close()


def test_pdf_to_markdown_pymupdf4llm(digital_pdf_bytes: bytes):
    """Verifies PyMuPDF4LLM extraction converts document content to structured markdown."""
    md_content = converter.pdf_to_markdown(digital_pdf_bytes, engine="pymupdf4llm")
    assert isinstance(md_content, str)
    assert len(md_content.strip()) > 0
    assert "Vellakshya" in md_content


def test_pdf_to_docx_pandoc(digital_pdf_bytes: bytes):
    """Verifies Pandoc-based PDF -> Markdown -> DOCX conversion generates valid DOCX archive."""
    docx_bytes = converter.pdf_to_docx_pandoc(digital_pdf_bytes)
    assert isinstance(docx_bytes, bytes)
    # Word docx files are PK zip archives
    assert docx_bytes.startswith(b"PK\x03\x04")


def test_pdf_to_docx_engine_dispatch(digital_pdf_bytes: bytes):
    """Verifies dual-engine dispatch between pdf2docx and pandoc."""
    docx_pandoc = converter.pdf_to_docx(digital_pdf_bytes, engine="pandoc")
    assert docx_pandoc.startswith(b"PK\x03\x04")

    docx_rule = converter.pdf_to_docx(digital_pdf_bytes, engine="pdf2docx")
    assert docx_rule.startswith(b"PK\x03\x04")


def test_api_ocr_classify_endpoint(digital_pdf_bytes: bytes, scanned_pdf_bytes: bytes):
    """Tests the /api/ocr/classify FastAPI route."""
    client = TestClient(app)

    res_digital = client.post(
        "/api/ocr/classify",
        files={"file": ("test.pdf", digital_pdf_bytes, "application/pdf")},
    )
    assert res_digital.status_code == 200
    data_digital = res_digital.json()
    assert data_digital["classification"] == "digital"
    assert data_digital["ocr_recommended"] is False

    res_scanned = client.post(
        "/api/ocr/classify",
        files={"file": ("scanned.pdf", scanned_pdf_bytes, "application/pdf")},
    )
    assert res_scanned.status_code == 200
    data_scanned = res_scanned.json()
    assert data_scanned["classification"] == "scanned"
    assert data_scanned["ocr_recommended"] is True


def test_api_ocr_searchable_endpoint(digital_pdf_bytes: bytes):
    """Tests the /api/ocr/searchable FastAPI route."""
    client = TestClient(app)
    res = client.post(
        "/api/ocr/searchable",
        files={"file": ("test.pdf", digital_pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert int(res.headers["X-OCR-Pages-Processed"]) == 1


def test_api_convert_markdown_with_engine(digital_pdf_bytes: bytes):
    """Tests /api/convert/markdown supporting the engine parameter."""
    client = TestClient(app)
    res = client.post(
        "/api/convert/markdown",
        files={"file": ("test.pdf", digital_pdf_bytes, "application/pdf")},
        data={"engine": "pymupdf4llm"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "markdown" in body
    assert "Vellakshya" in body["markdown"]


def test_api_convert_docx_with_pandoc(digital_pdf_bytes: bytes):
    """Tests /api/convert/docx supporting engine=pandoc."""
    client = TestClient(app)
    res = client.post(
        "/api/convert/docx",
        files={"file": ("document.pdf", digital_pdf_bytes, "application/pdf")},
        data={"engine": "pandoc"},
    )
    assert res.status_code == 200
    assert res.headers["X-Conversion-Engine"] == "pandoc"
    assert res.content.startswith(b"PK\x03\x04")
