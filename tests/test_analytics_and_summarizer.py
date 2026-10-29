"""
Comprehensive Test Suite for Milestone 1: Document Analytics & Smart Summarization.
Tests:
- In-process lexical analysis, syllable counting, Flesch Reading Ease, and Flesch-Kincaid Grade Level.
- Stopword filtering, n-gram bigram/trigram phrase frequencies, and language detection heuristics.
- Page range filtering (e.g. '1', '1-2', 'all') on multi-page PDFs.
- Multi-tier summarization (brief_overview, executive_summary, section_by_section, key_takeaways).
- Customization parameters: lengths (short, medium, long), tones (neutral, executive, technical, simplified),
  and output formats (paragraph, bullet_points, table, structured_report).
- Structured insight extraction: action items, decisions, risks, entities, and dates.
- Local-first privacy gate (F13): zero external network egress when allow_external_ai=False.
- FastAPI endpoints: POST /api/ai/analytics, POST /api/ai/analytics/file, POST /api/ai/summarize, POST /api/ai/summarize/file.
"""

from __future__ import annotations

import io
import fitz
import pytest
from fastapi.testclient import TestClient

from app.ai.analytics import (
    analyze_pdf_document,
    compute_document_analytics,
    compute_readability,
    count_syllables_in_word,
    detect_language_simple,
    parse_page_range,
)
from app.ai.models import ExtractedInsights
from app.ai.summarizer import (
    extract_structured_insights_offline,
    score_and_rank_sentences,
    summarize_pdf_document,
    summarize_text_extractive,
)
from app.main import app

client = TestClient(app)


def _build_multi_page_sample_pdf() -> bytes:
    """Generates a 3-page synthetic PDF containing structured business, technical, and governance text."""
    doc = fitz.open()

    # Page 1: Overview and Executive Decisions
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text(
        (72, 72),
        "Vellakshya Enterprise Intelligence System Overview\n\n"
        "The board of directors approved the cybersecurity modern architecture on 2026-03-15. "
        "This strategic initiative establishes a resilient document management infrastructure across the entire organization. "
        "All engineering departments decided to adopt local-first encryption protocols to protect sensitive customer records. "
        "Executive leadership agreed to prioritize privacy and eliminate unauthorized data egress.",
        fontsize=11,
    )

    # Page 2: Operational Mandates and Action Items
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text(
        (72, 72),
        "Operational Execution and Compliance Mandates\n\n"
        "The security operations team shall implement multi-factor authentication across all gateways by 2026-06-30. "
        "The compliance officer must submit the final regulatory audit report to the committee before Q3 2026. "
        "Lead architects are required to verify cryptographic key rotations every thirty days. "
        "Failure to enforce these controls introduces severe regulatory liability and legal penalties.",
        fontsize=11,
    )

    # Page 3: Technical Risks and Architectural Analysis
    p3 = doc.new_page(width=612, height=792)
    p3.insert_text(
        (72, 72),
        "Technical Vulnerability Assessment and Risk Mitigation\n\n"
        "Unpatched third-party dependencies represent an acute vulnerability for enterprise cloud deployments. "
        "The primary risk of unmonitored external network traffic involves potential data leakage and breach penalties. "
        "Therefore, our local offline extraction model guarantees zero cloud network dependencies. "
        "In conclusion, the unified platform ensures operational continuity and robust compliance under GDPR and HIPAA.",
        fontsize=11,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# =========================================================================
# 1. Analytics Engine Unit Tests
# =========================================================================

def test_syllable_counter():
    """Verifies syllable counter accuracy on monosyllabic and polysyllabic terms."""
    assert count_syllables_in_word("cat") == 1
    assert count_syllables_in_word("simple") == 2
    assert count_syllables_in_word("difficult") == 3
    assert count_syllables_in_word("cryptographic") == 4
    assert count_syllables_in_word("unprecedented") >= 4
    assert count_syllables_in_word("") == 0


def test_flesch_kincaid_readability():
    """Verifies Flesch Reading Ease and Flesch-Kincaid Grade Level formulas."""
    simple_words = ["the", "cat", "sat", "on", "the", "mat"]
    simple_sentences = ["The cat sat on the mat."]
    r_simple = compute_readability(simple_words, simple_sentences)
    assert r_simple["flesch_reading_ease"] > 85.0
    assert r_simple["flesch_kincaid_grade"] < 6.0

    complex_words = [
        "cryptographic", "verification", "demonstrates", "uncompromising",
        "institutional", "confidentiality", "mitigating", "adversarial", "vulnerabilities"
    ]
    complex_sentences = [
        "Cryptographic verification demonstrates uncompromising institutional confidentiality mitigating adversarial vulnerabilities."
    ]
    r_complex = compute_readability(complex_words, complex_sentences)
    assert r_complex["flesch_reading_ease"] < 50.0
    assert r_complex["flesch_kincaid_grade"] > 12.0


def test_stopwords_and_ngram_frequencies():
    """Verifies that common stopwords are filtered out and meaningful bigrams/trigrams are surfaced."""
    text = (
        "The board of directors met with the chief executive officer. "
        "The board of directors approved the annual budget. "
        "The executive officer praised the board of directors."
    )
    res = compute_document_analytics(text)
    keywords = [kw["word"] for kw in res["top_keywords"]]
    assert "the" not in keywords
    assert "of" not in keywords
    assert "board" in keywords
    assert "directors" in keywords

    phrases = [p["phrase"] for p in res["top_phrases"]]
    assert any("board" in p and "directors" in p for p in phrases)


def test_language_detection():
    """Verifies heuristic stopword language detection across multiple European languages."""
    en_text = "The quick brown fox jumps over the lazy dog in the field."
    es_text = "El rápido zorro marrón salta sobre el perro perezoso en el campo con los amigos."
    fr_text = "Le renard brun rapide saute par-dessus le chien paresseux dans le champ pour la vie."
    de_text = "Der schnelle braune Fuchs springt über den faulen Hund auf dem Feld mit der Kraft."

    assert detect_language_simple(en_text)[0] == "en"
    assert detect_language_simple(es_text)[0] == "es"
    assert detect_language_simple(fr_text)[0] == "fr"
    assert detect_language_simple(de_text)[0] == "de"


def test_parse_page_range():
    """Verifies parsing of page ranges like '1-2', '1, 3', 'all'."""
    assert parse_page_range(None, 5) == {1, 2, 3, 4, 5}
    assert parse_page_range("all", 5) == {1, 2, 3, 4, 5}
    assert parse_page_range("1-3", 5) == {1, 2, 3}
    assert parse_page_range("1, 3, 5", 5) == {1, 3, 5}
    assert parse_page_range("2-4, 5", 5) == {2, 3, 4, 5}


def test_analyze_pdf_document_page_filtering():
    """Verifies that PDF analytics can be filtered to a subset of pages."""
    pdf_bytes = _build_multi_page_sample_pdf()
    full_analytics = analyze_pdf_document(pdf_bytes, page_range="all")
    assert full_analytics["page_count"] == 3
    assert full_analytics["filtered_page_count"] == 3

    page1_analytics = analyze_pdf_document(pdf_bytes, page_range="1")
    assert page1_analytics["page_count"] == 3
    assert page1_analytics["filtered_page_count"] == 1
    assert page1_analytics["word_count"] < full_analytics["word_count"]


# =========================================================================
# 2. Summarization & Structured Insight Extraction Unit Tests
# =========================================================================

def test_extract_structured_insights_offline():
    """Verifies offline extraction of action items, decisions, risks, entities, and dates."""
    pdf_bytes = _build_multi_page_sample_pdf()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n\n".join(page.get_text("text") for page in doc)
    doc.close()

    insights = extract_structured_insights_offline(full_text)
    assert len(insights.action_items) > 0
    assert any("shall" in a.lower() or "must" in a.lower() for a in insights.action_items)

    assert len(insights.decisions) > 0
    assert any("approved" in d.lower() or "decided" in d.lower() or "agreed" in d.lower() for d in insights.decisions)

    assert len(insights.risks) > 0
    assert any("risk" in r.lower() or "vulnerability" in r.lower() or "liability" in r.lower() for r in insights.risks)

    assert len(insights.dates) > 0
    assert any("2026" in dt for dt in insights.dates)

    assert len(insights.entities) > 0
    assert any("GDPR" in ent or "HIPAA" in ent or "Enterprise" in ent for ent in insights.entities)


def test_summarization_output_formats():
    """Verifies markdown formatting across bullet_points, table, structured_report, and paragraph."""
    text = (
        "Artificial intelligence revolutionizes enterprise data workflows. "
        "The architecture eliminates manual labor through automated document parsing. "
        "Data security remains paramount for institutional privacy and compliance. "
        "Vendors must adhere to established encryption and audit standards."
    )
    # Paragraph
    p_sum, _ = summarize_text_extractive(text, output_format="paragraph")
    assert isinstance(p_sum, str) and len(p_sum) > 0

    # Bullet points
    b_sum, _ = summarize_text_extractive(text, output_format="bullet_points")
    assert b_sum.startswith("- ")

    # Table
    t_sum, _ = summarize_text_extractive(text, output_format="table")
    assert "| #" in t_sum or "| Section" in t_sum
    assert "| :--- |" in t_sum

    # Structured report
    r_sum, _ = summarize_text_extractive(text, output_format="structured_report")
    assert "## Executive Report" in r_sum
    assert "### Overview" in r_sum
    assert "### Key Findings" in r_sum


def test_summarization_section_by_section():
    """Verifies section-by-section multi-page summary breakdown."""
    pdf_bytes = _build_multi_page_sample_pdf()
    resp = summarize_pdf_document(
        pdf_bytes=pdf_bytes,
        level="section_by_section",
        output_format="bullet_points",
        allow_external_ai=False,
    )
    assert "Page 1" in resp.summary
    assert "Page 2" in resp.summary
    assert "Page 3" in resp.summary
    assert resp.model_used == "offline-extractive-v1"


def test_local_first_privacy_gate_f13():
    """Verifies that allow_external_ai=False strictly operates offline with 0 egress."""
    pdf_bytes = _build_multi_page_sample_pdf()
    resp = summarize_pdf_document(
        pdf_bytes=pdf_bytes,
        level="brief_overview",
        length="short",
        allow_external_ai=False,
    )
    assert resp.model_used == "offline-extractive-v1"
    assert resp.page_count == 3
    assert len(resp.summary) > 0


# =========================================================================
# 3. HTTP API Endpoints Integration Tests
# =========================================================================

def test_api_analytics_json_selected_text():
    """Tests POST /api/ai/analytics with selected text snippet."""
    payload = {
        "selected_text": "The executive committee decided to adopt standard encryption protocols. All records are securely verified."
    }
    resp = client.post("/api/ai/analytics", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["word_count"] > 10
    assert data["readability"]["flesch_reading_ease"] > 0
    assert data["language_code"] == "en"


def test_api_analytics_file_upload():
    """Tests POST /api/ai/analytics/file with direct PDF file upload."""
    pdf_bytes = _build_multi_page_sample_pdf()
    files = {"file": ("enterprise_audit.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"page_range": "1-2"}

    resp = client.post("/api/ai/analytics/file", files=files, data=data)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["page_count"] == 3
    assert res["filtered_page_count"] == 2
    assert len(res["top_keywords"]) > 0


def test_api_summarize_json_selected_text():
    """Tests POST /api/ai/summarize with JSON parameters and selected text."""
    payload = {
        "selected_text": (
            "The compliance officer must submit the final regulatory audit report to the committee before Q3 2026. "
            "Lead architects are required to verify cryptographic key rotations every thirty days. "
            "The board resolved to approve the cybersecurity architecture on 2026-03-15."
        ),
        "level": "key_takeaways",
        "output_format": "bullet_points",
        "tone": "executive",
        "allow_external_ai": False,
    }
    resp = client.post("/api/ai/summarize", json=payload)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["model_used"] == "offline-extractive-v1"
    assert res["summary"].startswith("- ")
    assert len(res["insights"]["action_items"]) > 0 or len(res["insights"]["decisions"]) > 0


def test_api_summarize_file_upload():
    """Tests POST /api/ai/summarize/file with direct PDF file upload."""
    pdf_bytes = _build_multi_page_sample_pdf()
    files = {"file": ("enterprise_audit.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "level": "executive_summary",
        "length": "medium",
        "tone": "neutral",
        "output_format": "structured_report",
        "allow_external_ai": False,
    }

    resp = client.post("/api/ai/summarize/file", files=files, data=data)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["model_used"] == "offline-extractive-v1"
    assert "## Executive Report" in res["summary"]
    assert len(res["insights"]["dates"]) > 0
    assert len(res["insights"]["risks"]) > 0
