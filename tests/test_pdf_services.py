"""
Automated unit tests for PDF Workbench Pro services.
"""
import io
import fitz  # PyMuPDF
import pytest
from app.services import converter, editor, forms, inspection, organizer, security


def create_sample_pdf(num_pages: int = 3, text_prefix: str = "Test Page") -> bytes:
    """Helper to generate an in-memory sample PDF for tests."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)  # US Letter
        page.insert_text((50, 80), f"{text_prefix} {i + 1}", fontsize=20)
        page.insert_text((50, 120), "Sample body text for verification.", fontsize=12)
        page.insert_text((50, 160), "Confidential Code: SECRET-9988", fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_pdf_to_html_fixed():
    pdf = create_sample_pdf(num_pages=2)
    html_fixed = converter.pdf_to_html_fixed(pdf, title="Unit Test Doc")
    assert "<!DOCTYPE html>" in html_fixed
    assert "pdf-page-container" in html_fixed
    assert "Test Page 1" in html_fixed
    assert "Test Page 2" in html_fixed
    assert "Helvetica" in html_fixed
    assert "toggleFitWidth" in html_fixed
    assert "text-size-adjust" in html_fixed
    assert "maximum-scale=5.0" in html_fixed


def test_pdf_to_html_semantic():
    pdf = create_sample_pdf(num_pages=2)
    html_sem = converter.pdf_to_html_semantic(pdf, title="Semantic Doc")
    assert "<!DOCTYPE html>" in html_sem
    assert "semantic-page-card" in html_sem
    assert "Test Page 1" in html_sem


def test_organizer_merge_and_split():
    pdf1 = create_sample_pdf(num_pages=2, text_prefix="Doc A")
    pdf2 = create_sample_pdf(num_pages=3, text_prefix="Doc B")
    merged = organizer.merge_pdfs([pdf1, pdf2])
    
    doc = fitz.open(stream=merged, filetype="pdf")
    assert len(doc) == 5
    doc.close()
    
    parts = organizer.split_pdf_by_ranges(merged, "1-2, 3-5")
    assert len(parts) == 2


def test_organizer_rotate_and_delete():
    pdf = create_sample_pdf(num_pages=3)
    rotated = organizer.rotate_pages(pdf, pages=[1], angle=90)
    
    doc = fitz.open(stream=rotated, filetype="pdf")
    assert doc[0].rotation == 90
    assert doc[1].rotation == 0
    doc.close()
    
    deleted = organizer.delete_pages(pdf, pages_to_delete=[2])
    doc_del = fitz.open(stream=deleted, filetype="pdf")
    assert len(doc_del) == 2
    doc_del.close()


def test_editor_watermark_and_numbers():
    pdf = create_sample_pdf(num_pages=2)
    wm = editor.add_text_watermark(pdf, text="SAMPLE WATERMARK", opacity=0.3)
    doc_wm = fitz.open(stream=wm, filetype="pdf")
    text = doc_wm[0].get_text()
    assert "SAMPLE WATERMARK" in text
    doc_wm.close()
    
    paginated = editor.add_page_numbers(pdf, pattern="Page {page} of {total}")
    doc_pg = fitz.open(stream=paginated, filetype="pdf")
    text_pg = doc_pg[0].get_text()
    assert "Page 1 of 2" in text_pg
    doc_pg.close()


def test_security_redaction():
    pdf = create_sample_pdf(num_pages=1)
    redacted_pdf, count = security.redact_text_permanently(pdf, terms_to_redact=["SECRET-9988"])
    assert count == 1
    
    doc = fitz.open(stream=redacted_pdf, filetype="pdf")
    text = doc[0].get_text()
    assert "SECRET-9988" not in text
    doc.close()


def test_security_encryption_and_decryption():
    pdf = create_sample_pdf(num_pages=1)
    encrypted = security.encrypt_pdf(pdf, user_password="testpassword123")
    
    # Verify it is encrypted
    doc = fitz.open(stream=encrypted, filetype="pdf")
    assert doc.is_encrypted
    doc.close()
    
    # Decrypt
    decrypted = security.decrypt_pdf(encrypted, password="testpassword123")
    doc_dec = fitz.open(stream=decrypted, filetype="pdf")
    assert not doc_dec.is_encrypted
    doc_dec.close()


def test_inspection():
    pdf = create_sample_pdf(num_pages=3)
    info = inspection.inspect_pdf(pdf)
    assert info["page_count"] == 3
    assert not info["is_encrypted"]
    assert len(info["pages"]) == 3


def test_delete_metadata():
    pdf = create_sample_pdf(num_pages=1)
    # Set metadata first
    doc = fitz.open(stream=pdf, filetype="pdf")
    doc.set_metadata({
        "title": "Confidential Research",
        "author": "Dr. Smith",
        "subject": "Bioinformatics",
        "keywords": "DNA, RNA",
    })
    meta_pdf = doc.tobytes()
    doc.close()

    # Verify metadata is set
    info = inspection.inspect_pdf(meta_pdf)
    assert info["metadata"]["title"] == "Confidential Research"
    assert info["metadata"]["author"] == "Dr. Smith"

    # Delete specific field (author)
    cleared_author = inspection.delete_metadata(meta_pdf, fields=["author"])
    info_author = inspection.inspect_pdf(cleared_author)
    assert info_author["metadata"]["author"] == ""
    assert info_author["metadata"]["title"] == "Confidential Research"

    # Delete all metadata
    cleared_all = inspection.delete_metadata(meta_pdf)
    info_all = inspection.inspect_pdf(cleared_all)
    assert info_all["metadata"]["title"] == ""
    assert info_all["metadata"]["author"] == ""
    assert info_all["metadata"]["subject"] == ""
    assert info_all["metadata"]["keywords"] == ""


def test_replace_text():
    pdf = create_sample_pdf(num_pages=1, text_prefix="Original Report")
    modified_pdf, count = editor.replace_text(
        pdf,
        search_text="SECRET-9988",
        replacement_text="PUBLIC-1234",
    )
    assert count == 1
    doc = fitz.open(stream=modified_pdf, filetype="pdf")
    text = doc[0].get_text()
    assert "PUBLIC-1234" in text
    assert "SECRET-9988" not in text
    doc.close()


def test_insert_text_block():
    pdf = create_sample_pdf(num_pages=1)
    modified = editor.insert_text_block(
        pdf,
        page_num=1,
        text="Appended Notice 2026",
        x=50.0,
        y=200.0,
        font_size=14,
        bg_fill_color=(1.0, 1.0, 1.0),
    )
    doc = fitz.open(stream=modified, filetype="pdf")
    text = doc[0].get_text()
    assert "Appended Notice 2026" in text
    doc.close()


def test_whiteout_area():
    pdf = create_sample_pdf(num_pages=1)
    modified = editor.whiteout_area(pdf, page_num=1, x0=40, y0=70, x1=300, y1=95)
    doc = fitz.open(stream=modified, filetype="pdf")
    text = doc[0].get_text()
    assert "Test Page 1" not in text
    doc.close()


def test_replace_text_batch_and_sequential_chaining():
    # Verify both multiple rules in one pass AND sequential chaining across passes
    pdf = create_sample_pdf(num_pages=1, text_prefix="First Sentence SECRET-9988 Second Sentence")
    # Batch replace
    batch_pdf, count = editor.replace_text_batch(
        pdf,
        rules=[
            {"search": "First", "replace": "Alpha"},
            {"search": "Second", "replace": "Beta"},
        ],
    )
    assert count >= 2
    doc1 = fitz.open(stream=batch_pdf, filetype="pdf")
    t1 = doc1[0].get_text()
    assert "Alpha" in t1
    assert "Beta" in t1
    assert "First" not in t1
    assert "Second" not in t1
    doc1.close()

    # Sequential chaining: take batch_pdf as input and replace another term
    chained_pdf, count2 = editor.replace_text(
        batch_pdf,
        search_text="SECRET-9988",
        replacement_text="SAVED-VALUE",
    )
    assert count2 >= 1
    doc2 = fitz.open(stream=chained_pdf, filetype="pdf")
    t2 = doc2[0].get_text()
    assert "Alpha" in t2
    assert "Beta" in t2
    assert "SAVED-VALUE" in t2
    assert "SECRET-9988" not in t2
    doc2.close()


def test_crop_pages_box_and_margins():
    pdf = create_sample_pdf(num_pages=2)
    # Test bounding box crop
    cropped_box = organizer.crop_pages(pdf, x0=50, y0=50, x1=400, y1=600)
    doc_box = fitz.open(stream=cropped_box, filetype="pdf")
    assert doc_box[0].rect.width == 350
    assert doc_box[0].rect.height == 550
    doc_box.close()

    # Test margin trimming
    cropped_margins = organizer.crop_pages(
        pdf,
        margin_top=36,
        margin_bottom=36,
        margin_left=36,
        margin_right=36,
    )
    doc_margins = fitz.open(stream=cropped_margins, filetype="pdf")
    # Original is 612 x 792, minus 72 on both width and height
    assert doc_margins[0].rect.width == 540
    assert doc_margins[0].rect.height == 720
    doc_margins.close()


def test_replace_single_vs_replace_all():
    # Create sample document with three repeated words
    pdf = create_sample_pdf(num_pages=1, text_prefix="ALPHA BETA ALPHA GAMMA ALPHA")

    # 1. Single Replace: only replace match #1 (second occurrence, occurrence=1)
    single_pdf, count_single = editor.replace_text(
        pdf,
        search_text="ALPHA",
        replacement_text="DELTA",
        single=True,
        occurrence=1,
    )
    assert count_single == 1
    doc_single = fitz.open(stream=single_pdf, filetype="pdf")
    text_single = doc_single[0].get_text()
    # The replacement DELTA should appear, AND original ALPHA must still be present!
    assert "DELTA" in text_single
    assert "ALPHA" in text_single
    matches_after = doc_single[0].search_for("ALPHA")
    assert len(matches_after) == 2
    doc_single.close()

    # 2. Replace All: replace all occurrences of ALPHA with OMEGA
    all_pdf, count_all = editor.replace_text(
        pdf,
        search_text="ALPHA",
        replacement_text="OMEGA",
        single=False,
    )
    assert count_all == 3
    doc_all = fitz.open(stream=all_pdf, filetype="pdf")
    text_all = doc_all[0].get_text()
    assert "OMEGA" in text_all
    assert "ALPHA" not in text_all
    assert len(doc_all[0].search_for("ALPHA")) == 0
    doc_all.close()


def test_replace_text_preserves_same_font_and_color():
    # Construct document with 3 distinctly styled text elements
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # 1. Blue italic Times serif
    page.insert_text(fitz.Point(72, 100), "Status: PENDING_APPROVAL on page", fontname="times-italic", fontsize=15, color=(0.1, 0.4, 0.9))
    # 2. Red bold Helvetica sans-serif
    page.insert_text(fitz.Point(72, 160), "Priority: HIGH_URGENCY note", fontname="hebo", fontsize=20, color=(0.85, 0.15, 0.15))
    # 3. Purple bold Courier monospace
    page.insert_text(fitz.Point(72, 220), "Token: SEC_KEY_9988 hash", fontname="courier-bold", fontsize=12, color=(0.6, 0.1, 0.7))
    sample_pdf = doc.tobytes()
    doc.close()

    # Apply batch replacements with automatic style preservation
    replaced_pdf, count = editor.replace_text_batch(
        sample_pdf,
        rules=[
            {"search_text": "PENDING_APPROVAL", "replacement_text": "ACCEPTED_OFFICIAL"},
            {"search_text": "HIGH_URGENCY", "replacement_text": "RESOLVED_NORMAL"},
            {"search_text": "SEC_KEY_9988", "replacement_text": "SEC_AUTH_2026"},
        ],
        preserve_style=True,
    )
    assert count == 3

    # Inspect the resulting spans
    res_doc = fitz.open(stream=replaced_pdf, filetype="pdf")
    res_page = res_doc[0]
    blocks = res_page.get_text("dict")["blocks"]
    spans = [s for b in blocks if b.get("type") == 0 for l in b.get("lines", []) for s in l.get("spans", [])]

    # Verify 1: ACCEPTED_OFFICIAL preserved Times-Italic font and (0.1, 0.4, 0.9) color
    span1 = next(s for s in spans if "ACCEPTED_OFFICIAL" in s["text"])
    assert span1["font"] == "Times-Italic"
    assert abs(span1["size"] - 15.0) < 0.2
    c1 = span1["color"]
    rgb1 = (((c1 >> 16) & 255) / 255.0, ((c1 >> 8) & 255) / 255.0, (c1 & 255) / 255.0)
    assert abs(rgb1[0] - 0.1) < 0.05
    assert abs(rgb1[1] - 0.4) < 0.05
    assert abs(rgb1[2] - 0.9) < 0.05

    # Verify 2: RESOLVED_NORMAL preserved Helvetica-Bold font and red color
    span2 = next(s for s in spans if "RESOLVED_NORMAL" in s["text"])
    assert span2["font"] == "Helvetica-Bold"
    assert abs(span2["size"] - 20.0) < 0.2
    c2 = span2["color"]
    rgb2 = (((c2 >> 16) & 255) / 255.0, ((c2 >> 8) & 255) / 255.0, (c2 & 255) / 255.0)
    assert abs(rgb2[0] - 0.85) < 0.05
    assert abs(rgb2[1] - 0.15) < 0.05
    assert abs(rgb2[2] - 0.15) < 0.05

    # Verify 3: SEC_AUTH_2026 preserved Courier-Bold font and purple color
    span3 = next(s for s in spans if "SEC_AUTH_2026" in s["text"])
    assert span3["font"] == "Courier-Bold"
    assert abs(span3["size"] - 12.0) < 0.2
    c3 = span3["color"]
    rgb3 = (((c3 >> 16) & 255) / 255.0, ((c3 >> 8) & 255) / 255.0, (c3 & 255) / 255.0)
    assert abs(rgb3[0] - 0.6) < 0.05
    assert abs(rgb3[1] - 0.1) < 0.05
    assert abs(rgb3[2] - 0.7) < 0.05

    res_doc.close()


def test_parse_page_spec_ranges_and_keywords():
    from app.services.organizer import parse_page_spec
    assert parse_page_spec("1-5", total_pages=10) == [1, 2, 3, 4, 5]
    assert parse_page_spec("odd", total_pages=6) == [1, 3, 5]
    assert parse_page_spec("even", total_pages=6) == [2, 4, 6]
    assert parse_page_spec("all", total_pages=4) == [1, 2, 3, 4]
    assert parse_page_spec("1, 3, 5-7, odd", total_pages=8) == [1, 3, 5, 6, 7]




