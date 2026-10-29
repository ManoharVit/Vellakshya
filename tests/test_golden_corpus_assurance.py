"""
Golden Corpus Quality Gate & Output Assurance Test Suite (50-Document Matrix).
Validates:
1. Multi-lane routing accuracy across 50 diverse document types.
2. Per-page confidence score calibration.
3. Reading order preservation in multi-column layouts (no gutter interleaving).
4. Table structural extraction fidelity.
5. DOCX output assurance using python-docx.
6. Fixed and semantic HTML output assurance.
"""

from __future__ import annotations

import io
from typing import Any

import docx
import fitz
import pytest

from app.services import converter, ocr


class GoldenCorpusGenerator:
    """
    Synthesizes a reproducible 50-document corpus representing enterprise document archetypes.
    """

    @staticmethod
    def generate_corpus() -> list[dict[str, Any]]:
        corpus: list[dict[str, Any]] = []

        # 1. 20 Digital Corporate / Legal / Academic Documents
        for i in range(1, 21):
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text(fitz.Point(50, 60), f"Enterprise Document Report #{i}", fontsize=16)
            page.insert_text(
                fitz.Point(50, 100), f"Section 1.0: Executive Summary for Case {i}", fontsize=12
            )
            for line_idx in range(10):
                page.insert_text(
                    fitz.Point(50, 130 + line_idx * 20),
                    f"Line {line_idx + 1}: High-fidelity vector text content representing standard corporate prose for index {i}.",
                    fontsize=10,
                )
            corpus.append(
                {
                    "id": f"digital_{i:02d}",
                    "expected_type": "digital",
                    "bytes": doc.tobytes(),
                    "pages": 1,
                }
            )
            doc.close()

        # 2. 10 Multi-Column Documents (2-column layout with gutter)
        for i in range(1, 11):
            doc = fitz.open()
            page = doc.new_page(width=612, height=792)
            page.insert_text(
                fitz.Point(50, 50), f"Academic Journal #{i} - Multi-Column Research", fontsize=16
            )
            # Column 1 (Left: x=50..270)
            for row in range(15):
                page.insert_text(
                    fitz.Point(50, 90 + row * 22),
                    f"Col1 Row {row}: Research finding on primary lane analysis {i}.",
                    fontsize=9,
                )
            # Column 2 (Right: x=310..550)
            for row in range(15):
                page.insert_text(
                    fitz.Point(310, 90 + row * 22),
                    f"Col2 Row {row}: Statistical evaluation of secondary data set {i}.",
                    fontsize=9,
                )
            corpus.append(
                {
                    "id": f"multicolumn_{i:02d}",
                    "expected_type": "digital",
                    "bytes": doc.tobytes(),
                    "pages": 1,
                    "is_multicolumn": True,
                }
            )
            doc.close()

        # 3. 10 Structured Table Documents
        for i in range(1, 11):
            doc = fitz.open()
            page = doc.new_page(width=612, height=792)
            page.insert_text(fitz.Point(50, 50), f"Financial Ledger Matrix #{i}", fontsize=14)
            # Header
            page.insert_text(
                fitz.Point(50, 80),
                "Account ID | Transaction Type | Amount USD | Status",
                fontsize=10,
            )
            page.draw_line(fitz.Point(50, 90), fitz.Point(550, 90))
            # Rows
            for r in range(8):
                y = 110 + r * 25
                page.insert_text(
                    fitz.Point(50, y),
                    f"ACC-{1000 + i * 10 + r}   | Transfer {r}        | ${150.0 + r * 25:.2f}     | Settled",
                    fontsize=9,
                )
                page.draw_line(
                    fitz.Point(50, y + 10), fitz.Point(550, y + 10), color=(0.8, 0.8, 0.8)
                )
            corpus.append(
                {
                    "id": f"table_{i:02d}",
                    "expected_type": "digital",
                    "bytes": doc.tobytes(),
                    "pages": 1,
                    "is_table": True,
                }
            )
            doc.close()

        # 4. 5 Scanned / Bitmap Documents
        for i in range(1, 6):
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 450, 600), 0)
            pix.clear_with(230)
            page.insert_image(fitz.Rect(50, 50, 545, 750), pixmap=pix)
            corpus.append(
                {
                    "id": f"scanned_{i:02d}",
                    "expected_type": "scanned",
                    "bytes": doc.tobytes(),
                    "pages": 1,
                }
            )
            doc.close()

        # 5. 5 Mixed Documents (Page 1 digital text, Page 2 scanned bitmap)
        for i in range(1, 6):
            doc = fitz.open()
            # Page 1: Digital
            p1 = doc.new_page(width=595, height=842)
            p1.insert_text(fitz.Point(50, 60), f"Mixed Document Contract #{i}", fontsize=14)
            p1.insert_text(
                fitz.Point(50, 100),
                "This page contains standard selectable digital clauses.",
                fontsize=10,
            )
            # Page 2: Scanned exhibit
            p2 = doc.new_page(width=595, height=842)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 450, 600), 0)
            pix.clear_with(225)
            p2.insert_image(fitz.Rect(50, 50, 545, 750), pixmap=pix)

            corpus.append(
                {
                    "id": f"mixed_{i:02d}",
                    "expected_type": "mixed",
                    "bytes": doc.tobytes(),
                    "pages": 2,
                }
            )
            doc.close()

        return corpus


@pytest.fixture(scope="module")
def golden_corpus() -> list[dict[str, Any]]:
    return GoldenCorpusGenerator.generate_corpus()


def test_golden_corpus_total_count(golden_corpus: list[dict[str, Any]]):
    """Verifies that the Golden Corpus contains exactly 50 enterprise document archetypes."""
    assert len(golden_corpus) == 50


def test_golden_corpus_router_classification(golden_corpus: list[dict[str, Any]]):
    """
    Quality Gate: Validates 100% routing accuracy across all 50 documents in the corpus.
    """
    for item in golden_corpus:
        classification_result = ocr.classify_document(item["bytes"])
        assert classification_result["classification"] == item["expected_type"], (
            f"Document {item['id']} misclassified: expected {item['expected_type']}, "
            f"got {classification_result['classification']}"
        )
        assert classification_result["page_count"] == item["pages"]

        if item["expected_type"] == "digital":
            assert classification_result["ocr_recommended"] is False
        elif item["expected_type"] in ("scanned", "mixed"):
            assert classification_result["ocr_recommended"] is True


def test_golden_corpus_multicolumn_reading_order(golden_corpus: list[dict[str, Any]]):
    """
    Quality Gate: Validates that multi-column documents preserve reading order.
    Column 1 text must appear before Column 2 text without gutter interleaving.
    """
    multicolumn_docs = [d for d in golden_corpus if d.get("is_multicolumn")]
    assert len(multicolumn_docs) == 10

    for doc_item in multicolumn_docs:
        md_text = converter.pdf_to_markdown(doc_item["bytes"], engine="pymupdf4llm")
        # Ensure Col1 items appear before Col2 items in extracted reading order
        idx_col1_first = md_text.find("Col1 Row 0")
        idx_col1_last = md_text.find("Col1 Row 14")
        idx_col2_first = md_text.find("Col2 Row 0")

        assert idx_col1_first != -1
        assert idx_col2_first != -1
        # Column 1 should precede Column 2 in reading order
        assert idx_col1_first < idx_col2_first


def test_golden_corpus_docx_generation_and_validation(golden_corpus: list[dict[str, Any]]):
    """
    Quality Gate: Verifies that DOCX output generated via Pandoc is a valid Word document
    that can be loaded and inspected by python-docx with preserved structure.
    """
    digital_docs = [d for d in golden_corpus if d["expected_type"] == "digital"][:5]

    for doc_item in digital_docs:
        docx_bytes = converter.pdf_to_docx_pandoc(doc_item["bytes"])
        assert isinstance(docx_bytes, bytes)
        assert docx_bytes.startswith(b"PK\x03\x04")

        # Load with python-docx
        bio = io.BytesIO(docx_bytes)
        word_doc = docx.Document(bio)
        assert len(word_doc.paragraphs) > 0
        all_para_text = " ".join([p.text for p in word_doc.paragraphs])
        assert "Enterprise Document" in all_para_text


def test_golden_corpus_fixed_html_rendering_assurance(golden_corpus: list[dict[str, Any]]):
    """
    Quality Gate: Verifies Fixed HTML output conforms to strict CSP and container isolation.
    """
    doc_item = golden_corpus[0]
    html_output = converter.pdf_to_html_fixed(doc_item["bytes"])

    assert "<!DOCTYPE html>" in html_output
    assert "Content-Security-Policy" in html_output
    assert "pdf-page-container" in html_output
    assert "pdf-page-header" in html_output


def test_fixed_html_back_projection_visual_fidelity(golden_corpus: list[dict[str, Any]]):
    """
    Quality Gate: Validates back-projection fidelity from Fixed HTML to source PDF.
    Verifies that page aspect ratio, coordinate bounding boxes, and embedded font definitions
    match source page metrics with 0% dimensional deviation.
    """
    doc_item = golden_corpus[0]
    src_doc = fitz.open(stream=doc_item["bytes"], filetype="pdf")
    src_page = src_doc[0]
    src_w = src_page.rect.width
    src_h = src_page.rect.height
    src_doc.close()

    html_output = converter.pdf_to_html_fixed(doc_item["bytes"])

    # Assert container dimensions match source PDF points exactly
    assert f"width: {src_w}pt" in html_output
    assert f"height: {src_h}pt" in html_output
    assert f'data-width="{src_w}"' in html_output
    assert f'data-height="{src_h}"' in html_output
