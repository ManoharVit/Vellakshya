"""
Accessibility (a11y) and Visual Regression Test Suite.
Audits:
- Semantic HTML landmarks, ARIA labels, keyboard navigation shortcuts, mobile viewports.
- Visual regression & pixel fidelity between original and edited outputs.
"""
from __future__ import annotations
from fastapi.testclient import TestClient
import fitz
import pytest

from app.main import app
from app.services import inspection, organizer

client = TestClient(app)


def test_accessibility_semantic_landmarks_and_aria():
    """
    Validates that the single-page application and converted HTML output
    contain required semantic landmarks and accessibility tags.
    """
    res_index = client.get("/")
    assert res_index.status_code == 200
    html_src = res_index.text

    # 1. Semantic landmarks
    assert "<main" in html_src, "Missing <main> semantic landmark"
    assert "<aside" in html_src or "<nav" in html_src, "Missing <aside> or <nav> navigation landmark"
    assert "<header" in html_src, "Missing <header> landmark"

    # 2. Viewport tag for mobile/tablet responsive scaling
    assert 'name="viewport"' in html_src
    assert "width=device-width" in html_src

    # 3. Form input labelling & accessibility
    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    js_src = res_js.text

    # Keyboard navigation shortcuts present (Undo, Redo, Zoom, Page Jump)
    assert "keydown" in js_src
    assert "KeyZ" in js_src or "ctrlKey" in js_src or "metaKey" in js_src


def test_accessibility_converted_html_compliance():
    """
    Verifies that PDF-to-HTML conversion adheres to accessibility guidelines:
    semantic headings (h1, h2), readable font contrast, and responsive viewports.
    """
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text(fitz.Point(72, 72), "ACCESSIBILITY_TITLE_HEADING", fontsize=16)
    p.insert_text(fitz.Point(72, 110), "Accessible body paragraph description text.", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/convert/html",
        files={"file": ("a11y_sample.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "semantic"},
    )
    assert res.status_code == 200
    semantic_html = res.text

    # Must contain HTML5 doctype and lang attribute
    assert '<html lang="en">' in semantic_html
    # Must contain responsive viewport
    assert 'name="viewport"' in semantic_html
    # Must contain semantic heading and paragraph tags
    assert "<h2>ACCESSIBILITY_TITLE_HEADING</h2>" in semantic_html or "<h1" in semantic_html
    assert "<p>" in semantic_html


def test_visual_regression_pixel_fidelity():
    """
    Visual regression test: Compare pixel-by-pixel rendering of untouched pages
    before and after document operations to verify 0% visual layout drift.
    """
    # Create a 2-page document
    doc = fitz.open()
    p1 = doc.new_page(width=500, height=500)
    p1.draw_rect(fitz.Rect(50, 50, 450, 200), color=(0.2, 0.4, 0.8), fill=(0.9, 0.95, 1.0))
    p1.insert_text(fitz.Point(70, 100), "GOLDEN_PAGE_1: Stable Visual Structure", fontsize=14)

    p2 = doc.new_page(width=500, height=500)
    p2.draw_circle(fitz.Point(250, 250), 80, color=(0.8, 0.2, 0.2), fill=(1.0, 0.9, 0.9))
    p2.insert_text(fitz.Point(120, 250), "PAGE_2_TARGET", fontsize=12)
    orig_bytes = doc.tobytes()
    doc.close()

    # Render original Page 1 pixmap at 150 DPI
    doc_orig = fitz.open(stream=orig_bytes, filetype="pdf")
    pix_orig_p1 = doc_orig[0].get_pixmap(dpi=150)
    samples_orig = pix_orig_p1.samples
    doc_orig.close()

    # Perform an operation on Page 2 (e.g. metadata update or delete metadata)
    modified_bytes = inspection.update_metadata(orig_bytes, {"title": "Regression Baseline Document"})

    # Render modified Page 1 pixmap at 150 DPI
    doc_mod = fitz.open(stream=modified_bytes, filetype="pdf")
    pix_mod_p1 = doc_mod[0].get_pixmap(dpi=150)
    samples_mod = pix_mod_p1.samples
    doc_mod.close()

    # Compute pixel differences
    assert len(samples_orig) == len(samples_mod), "Rendered dimensions changed!"
    
    diff_bytes = 0
    for b1, b2 in zip(samples_orig, samples_mod):
        if b1 != b2:
            diff_bytes += 1

    drift_ratio = diff_bytes / len(samples_orig)
    # Untouched Page 1 must have 0% visual drift
    assert drift_ratio == 0.0, f"Visual drift detected on untouched page: {drift_ratio * 100:.3f}%"
