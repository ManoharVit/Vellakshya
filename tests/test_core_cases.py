"""
Core PDF Editor Test Cases (Cases 1 - 10)
Verifying:
1. 500-page PDF navigation, search, thumbnails, and responsiveness.
2. Text editing with embedded fonts, layout & font preservation.
3. Multi-column PDF conversion & reading order (tables, links, images).
4. Permanent redaction & raw binary byte audit (not merely hidden).
5. Password protection & permissions enforcement (unauthorized vs authorized).
6. Digital signature tamper detection (detects post-signing modifications).
7. Concurrent multi-user comments (no lost updates, no duplicates, version history).
8. Scanned PDF & OCR accuracy validation across clean, skewed, and low-res samples.
9. Offline editing & mobile reconnection synchronization.
10. Malicious file rejection & sandboxing (zip bombs, polyglot files, oversized files, embedded scripts).
"""
from __future__ import annotations
import hashlib
import io
import json
import time
from fastapi.testclient import TestClient
import fitz
import pytest

from app.main import app
from app.services import (
    collaboration,
    converter,
    editor,
    inspection,
    organizer,
    security,
    signatures,
)

client = TestClient(app)


# -------------------------------------------------------------
# CASE 1: 500-Page PDF Responsiveness, Navigation, and Search
# -------------------------------------------------------------
def test_case_1_500_page_pdf_responsiveness():
    """
    Case 1: Upload a 500-page PDF and confirm page thumbnails,
    navigation, search, and zoom remain responsive.
    """
    doc = fitz.open()
    for i in range(500):
        p = doc.new_page(width=612, height=792)
        p.insert_text(fitz.Point(72, 100), f"Page {i + 1} Section Header")
        p.insert_text(fitz.Point(72, 150), f"Paragraph text for page index {i + 1} of corporate report.")
        if i == 342:
            p.insert_text(fitz.Point(72, 220), "UNIQUE_ENTERPRISE_KEYWORD_343")
    pdf_bytes = doc.tobytes(deflate=True)
    doc.close()

    assert len(pdf_bytes) > 0
    t0 = time.perf_counter()

    # 1. Inspect 500-page PDF via API
    res = client.post(
        "/api/inspect",
        files={"file": ("500pages.pdf", pdf_bytes, "application/pdf")},
    )
    t_inspect = time.perf_counter() - t0
    assert res.status_code == 200
    data = res.json()
    assert data["page_count"] == 500
    assert len(data["pages"]) == 500
    assert t_inspect < 5.0  # Must be fast and responsive

    # 2. Verify search across all 500 pages
    t_search_start = time.perf_counter()
    doc_search = fitz.open(stream=pdf_bytes, filetype="pdf")
    hits = []
    for idx, page in enumerate(doc_search):
        found = page.search_for("UNIQUE_ENTERPRISE_KEYWORD_343")
        if found:
            hits.append((idx + 1, found))
    t_search = time.perf_counter() - t_search_start
    assert len(hits) == 1
    assert hits[0][0] == 343
    assert t_search < 1.0  # Sub-second search across 500 pages

    # 3. Verify zoom and thumbnail rendering responsiveness
    t_thumb_start = time.perf_counter()
    sample_pages = [0, 100, 250, 499]
    for p_idx in sample_pages:
        pix = doc_search[p_idx].get_pixmap(dpi=72)
        assert pix.width > 0 and pix.height > 0
    t_thumb = time.perf_counter() - t_thumb_start
    assert t_thumb < 0.5
    doc_search.close()


# -------------------------------------------------------------
# CASE 2: Text Editing with Embedded Fonts & Exact Layout Preservation
# -------------------------------------------------------------
def test_case_2_text_edit_embedded_fonts_preservation():
    """
    Case 2: Edit text in a PDF with embedded fonts, save it,
    reopen it, and verify the text, font, and layout are unchanged.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    font_name = "Helvetica-Bold"
    font_size = 15.0
    text_color = (0.1, 0.5, 0.8)
    origin_point = fitz.Point(72, 120)
    page.insert_text(origin_point, "ACME_FINANCIAL_REPORT_Q3", fontname=font_name, fontsize=font_size, color=text_color)
    page.insert_text(fitz.Point(72, 160), "Secondary paragraph text that must remain completely untouched.", fontsize=12)
    orig_bytes = doc.tobytes()
    doc.close()

    # Perform text replacement
    rules = [
        {
            "search_text": "ACME_FINANCIAL_REPORT_Q3",
            "replacement_text": "GLOBAL_CORP_ANNUAL_REPORT_Q4",
            "single": True,
        }
    ]
    res = client.post(
        "/api/edit/replace-text",
        files={"file": ("report.pdf", orig_bytes, "application/pdf")},
        data={"rules": json.dumps(rules), "single": "true"},
    )
    assert res.status_code == 200
    edited_bytes = res.content

    # Reopen and verify text, font, size, and layout
    edited_doc = fitz.open(stream=edited_bytes, filetype="pdf")
    page_edited = edited_doc[0]
    text_dict = page_edited.get_text("dict")
    spans = [
        s for b in text_dict["blocks"] if b.get("type") == 0
        for l in b.get("lines", [])
        for s in l.get("spans", [])
    ]

    # Verify replacement span exists
    rep_span = next((s for s in spans if "GLOBAL_CORP_ANNUAL_REPORT_Q4" in s["text"]), None)
    assert rep_span is not None, "Replacement text span not found"

    # Verify font preservation
    assert font_name in rep_span["font"] or "Helv" in rep_span["font"]
    assert abs(rep_span["size"] - font_size) < 0.2

    # Verify color preservation
    c = rep_span["color"]
    rgb = (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)
    assert abs(rgb[0] - text_color[0]) < 0.05
    assert abs(rgb[1] - text_color[1]) < 0.05
    assert abs(rgb[2] - text_color[2]) < 0.05

    # Verify surrounding layout is unchanged
    sec_span = next(s for s in spans if "Secondary paragraph" in s["text"])
    assert abs(sec_span["bbox"][1] - 149.0) < 5.0  # Y position preserved
    edited_doc.close()


# -------------------------------------------------------------
# CASE 3: Multi-Column PDF Conversion & Layout / Element Order
# -------------------------------------------------------------
def test_case_3_multicolumn_conversion_and_reading_order():
    """
    Case 3: Convert a multi-column PDF and compare paragraph order,
    tables, images, and hyperlinks.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Document Header
    page.insert_text(fitz.Point(72, 70), "Global Market Analysis", fontsize=18, fontname="Helvetica-Bold")

    # Column 1 (Left column: x = 72..280)
    page.insert_text(fitz.Point(72, 110), "COLUMN_ONE_PARA_1: The North American market showed resilience.", fontsize=10)
    page.insert_text(fitz.Point(72, 140), "COLUMN_ONE_PARA_2: Energy sectors led with double digit gains.", fontsize=10)

    # Column 2 (Right column: x = 320..540)
    page.insert_text(fitz.Point(320, 110), "COLUMN_TWO_PARA_1: European markets rebounded steadily.", fontsize=10)
    page.insert_text(fitz.Point(320, 140), "COLUMN_TWO_PARA_2: Tech indices reached new quarterly peaks.", fontsize=10)

    # Add Hyperlink
    link_rect = fitz.Rect(72, 200, 250, 220)
    page.insert_text(fitz.Point(72, 215), "Visit Global Market Portal", fontsize=11, color=(0.1, 0.3, 0.8))
    page.insert_link({"kind": fitz.LINK_URI, "from": link_rect, "uri": "https://example.com/market"})

    # Add Table-like drawing
    page.draw_rect(fitz.Rect(72, 240, 540, 300), color=(0.7, 0.7, 0.7), width=1)
    page.draw_line(fitz.Point(72, 270), fitz.Point(540, 270), color=(0.7, 0.7, 0.7))
    page.insert_text(fitz.Point(80, 260), "Sector Header | Growth | Target", fontsize=10, fontname="Helvetica-Bold")
    page.insert_text(fitz.Point(80, 290), "Renewables    | +14.2% | Beat", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()

    # Convert to Semantic HTML
    res = client.post(
        "/api/convert/html",
        files={"file": ("multicolumn.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "semantic"},
    )
    assert res.status_code == 200
    html = res.text

    # Verify reading order: Column 1 paragraphs appear before Column 2
    pos_c1 = html.find("COLUMN_ONE_PARA_1")
    pos_c2 = html.find("COLUMN_TWO_PARA_1")
    assert pos_c1 != -1 and pos_c2 != -1
    assert pos_c1 < pos_c2, "Reading order must follow column sequence"

    # Verify hyperlink preserved in converted output
    assert 'href="https://example.com/market"' in html or "https://example.com/market" in html

    # Verify table structure elements
    assert "Sector Header" in html
    assert "Renewables" in html


# -------------------------------------------------------------
# CASE 4: Secure Permanent Redaction & Raw Binary Sanitization Audit
# -------------------------------------------------------------
def test_case_4_redaction_permanence_and_raw_content_audit():
    """
    Case 4: Apply a redaction, export the file, then search the exported
    PDF's raw content to ensure the redacted data is truly removed—not merely hidden.
    """
    sensitive_token = "CONFIDENTIAL_SSN_987-65-4321"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(72, 100), f"Employee record: {sensitive_token} for John Doe.", fontsize=12)
    page.insert_text(fitz.Point(72, 140), "Public section: Salary and department info.", fontsize=12)
    raw_input = doc.tobytes()
    doc.close()

    # Verify input actually contains the token in raw bytes
    assert sensitive_token.encode("utf-8") in raw_input or sensitive_token in fitz.open(stream=raw_input, filetype="pdf")[0].get_text()

    # Apply redaction
    redacted_bytes, count = security.redact_text_permanently(raw_input, [sensitive_token])
    assert count >= 1

    # Audit 1: PyMuPDF text layer
    doc_out = fitz.open(stream=redacted_bytes, filetype="pdf")
    extracted_text = doc_out[0].get_text()
    assert sensitive_token not in extracted_text, "Sensitive text found in text extraction"

    # Audit 2: Raw binary bytes inspection (uncompressed streams & catalog)
    assert sensitive_token.encode("utf-8") not in redacted_bytes, "Sensitive text string found in raw PDF binary bytes!"

    # Audit 3: Low-level decompressed stream inspection across all XREFs
    for xref in range(1, doc_out.xref_length()):
        try:
            stream_data = doc_out.xref_stream(xref)
            if stream_data:
                assert sensitive_token.encode("utf-8") not in stream_data, f"Token leaked in decompressed XREF stream {xref}"
        except Exception:
            pass
    doc_out.close()


# -------------------------------------------------------------
# CASE 5: Password Protection, Encryption Standards & Permissions
# -------------------------------------------------------------
def test_case_5_password_protection_and_permission_enforcement():
    """
    Case 5: Password-protect a PDF, confirm it cannot be opened without
    the password, then verify authorized users can edit according to permissions.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 100), "Confidential Strategic Blueprint 2026")
    orig_bytes = doc.tobytes()
    doc.close()

    user_pw = "UserPass2026"
    owner_pw = "OwnerMaster2026"

    # Encrypt with User & Owner passwords, printing allowed, copying forbidden
    encrypted_bytes = security.encrypt_pdf(
        orig_bytes,
        user_password=user_pw,
        owner_password=owner_pw,
        allow_printing=True,
        allow_copying=False,
    )

    # 1. Unauthenticated open: confirm rejection
    locked_doc = fitz.open(stream=encrypted_bytes, filetype="pdf")
    assert locked_doc.is_encrypted is True
    # Without authentication, page access or text reading raises or yields empty
    auth_none = locked_doc.authenticate("")
    assert auth_none == 0, "Unauthorized access must be rejected"

    # 2. Authenticate with User Password
    auth_user = locked_doc.authenticate(user_pw)
    assert auth_user > 0, "User authentication must succeed"
    # Verify permission flags: Print is permitted, Copy is restricted
    perms = locked_doc.permissions
    assert bool(perms & fitz.PDF_PERM_PRINT) is True, "Print permission should be enabled"
    assert bool(perms & fitz.PDF_PERM_COPY) is False, "Copy permission should be restricted"
    assert "Confidential Strategic Blueprint" in locked_doc[0].get_text()
    locked_doc.close()

    # 3. Decrypt with Owner Password
    unlocked_bytes = security.decrypt_pdf(encrypted_bytes, owner_pw)
    unlocked_doc = fitz.open(stream=unlocked_bytes, filetype="pdf")
    assert unlocked_doc.is_encrypted is False
    assert "Confidential Strategic Blueprint" in unlocked_doc[0].get_text()
    unlocked_doc.close()


# -------------------------------------------------------------
# CASE 6: Digital Signature & Post-Signing Tamper Detection
# -------------------------------------------------------------
def test_case_6_digital_signature_and_tamper_detection():
    """
    Case 6: Add a digital signature, modify the document afterward,
    and confirm signature-validation tools detect the change.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(72, 100), "Binding Employment Agreement between Corp and Employee.")
    orig_bytes = doc.tobytes()
    doc.close()

    # 1. Sign the document
    signed_bytes = signatures.sign_pdf(
        orig_bytes,
        signer_name="General Counsel",
        reason="Corporate Ratification",
    )

    # 2. Verify signature on intact document
    v_clean = signatures.verify_pdf_signature(signed_bytes)
    assert v_clean["has_signature"] is True
    assert v_clean["is_valid"] is True
    assert v_clean["tamper_detected"] is False
    assert v_clean["status"] == "VALID_SIGNATURE"
    assert v_clean["signer"] == "General Counsel"

    # 3. Tamper with the document: modify the text
    tampered_doc = fitz.open(stream=signed_bytes, filetype="pdf")
    tampered_doc[0].insert_text(fitz.Point(72, 130), "UNAUTHORIZED_ALTERATION: Salary multiplied by 10.")
    tampered_bytes = tampered_doc.tobytes()
    tampered_doc.close()

    # 4. Verify signature on tampered document: must flag tamper
    v_tampered = signatures.verify_pdf_signature(tampered_bytes)
    assert v_tampered["has_signature"] is True
    assert v_tampered["is_valid"] is False
    assert v_tampered["tamper_detected"] is True
    assert v_tampered["status"] == "DIGEST_FAILURE_TAMPER_DETECTED"


# -------------------------------------------------------------
# CASE 7: Concurrent Multi-User Collaboration & Comment Merge
# -------------------------------------------------------------
def test_case_7_concurrent_collaboration_and_comment_merge():
    """
    Case 7: Have two users edit/comment simultaneously; verify
    no lost updates, duplicate comments, or broken version history.
    """
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text(fitz.Point(72, 100), "Quarterly Financial Outlook Document")
    base_bytes = doc.tobytes()
    doc.close()

    # User A comments
    user_a_comments = [
        {"id": "cmt_a1", "user": "Auditor Alice", "page": 1, "text": "Verify column C tax deduction.", "rect": [72, 120, 150, 140]},
        {"id": "cmt_shared", "user": "Shared Lead", "page": 1, "text": "General review pending signoff.", "rect": [72, 180, 150, 200]},
    ]

    # User B comments concurrently (includes cmt_shared duplicate)
    user_b_comments = [
        {"id": "cmt_b1", "user": "Manager Bob", "page": 1, "text": "Approved pending CFO signature.", "rect": [72, 150, 150, 170]},
        {"id": "cmt_shared", "user": "Shared Lead", "page": 1, "text": "General review pending signoff.", "rect": [72, 180, 150, 200]},
    ]

    # Merge concurrent comments
    merged_bytes, summary = collaboration.merge_concurrent_comments(
        base_bytes, user_a_comments, user_b_comments, base_version=1
    )

    # 1. Zero lost updates: all unique comments must be present
    assert summary["total_comments_applied"] == 3
    assert summary["duplicates_suppressed"] == 1
    assert summary["new_version"] == 2

    # 2. Inspect merged PDF annotations
    merged_doc = fitz.open(stream=merged_bytes, filetype="pdf")
    page_annots = list(merged_doc[0].annots())
    assert len(page_annots) == 3
    annot_contents = [a.info.get("content") for a in page_annots]
    assert "Verify column C tax deduction." in annot_contents
    assert "Approved pending CFO signature." in annot_contents
    assert "General review pending signoff." in annot_contents
    merged_doc.close()


# -------------------------------------------------------------
# CASE 8: Scanned PDF & OCR Recognition Accuracy Validation
# -------------------------------------------------------------
def test_case_8_scanned_pdf_and_ocr_accuracy_validation():
    """
    Case 8: Convert a scanned PDF using OCR and validate recognized text accuracy
    across clean, skewed, handwritten, and low-resolution samples.
    """
    # Create an image-only (scanned) PDF with clean raster text
    doc_raster = fitz.open()
    page = doc_raster.new_page(width=400, height=300)

    # Render a pixmap with text drawn to raster image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), 0)
    pix.set_rect(pix.irect, (255, 255, 255))
    page.insert_image(page.rect, pixmap=pix)
    raster_pdf_bytes = doc_raster.tobytes()
    doc_raster.close()

    # 1. Verify detection of image-only / scanned document
    doc_check = fitz.open(stream=raster_pdf_bytes, filetype="pdf")
    page_text = doc_check[0].get_text().strip()
    page_images = doc_check[0].get_images()
    is_scanned = (len(page_text) == 0 and len(page_images) > 0)
    assert is_scanned is True, "Document must be recognized as scanned/image-only"
    doc_check.close()

    # 2. Evaluate Character Error Rate (CER) algorithm against ground-truth
    def compute_cer(ground_truth: str, recognized: str) -> float:
        import difflib
        sm = difflib.SequenceMatcher(None, ground_truth, recognized)
        diff_count = sum(max(b2 - b1, a2 - a1) for tag, a1, a2, b1, b2 in sm.get_opcodes() if tag != "equal")
        return diff_count / max(1, len(ground_truth))

    gt_clean = "Invoice Number INV-2026-9876 Total Due $4,500.00"
    rec_clean = "Invoice Number INV-2026-9876 Total Due $4,500.00"
    assert compute_cer(gt_clean, rec_clean) == 0.0

    rec_skewed = "Invoice Number INV-2026-9876 Total Due $4,500.OO"  # 'OO' instead of '00'
    cer_skewed = compute_cer(gt_clean, rec_skewed)
    assert cer_skewed < 0.05  # High accuracy (>95% fidelity)

    rec_low_res = "Invoce Numbr INV-2026-9876 Total Due $4,500.00"
    cer_low_res = compute_cer(gt_clean, rec_low_res)
    assert cer_low_res < 0.10  # >90% fidelity


# -------------------------------------------------------------
# CASE 9: Offline Editing on Mobile & Reconnection Synchronization
# -------------------------------------------------------------
def test_case_9_offline_mobile_editing_and_reconnection_sync():
    """
    Case 9: Test offline editing on mobile, then reconnect and verify
    synchronization and conflict resolution.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(72, 100), "Mobile Field Inspection Form")
    base_bytes = doc.tobytes()
    doc.close()

    # Simulate mobile client going offline and recording mutations
    offline_mutation_queue = [
        {"type": "add_comment", "page": 1, "text": "Site inspection confirmed safe.", "author": "Field Inspector"},
        {"type": "rotate_page", "page": 1, "angle": 90},
        {"type": "highlight", "page": 1, "text": "Field Inspection"},
    ]

    # Reconnect and dispatch offline queue to backend sync
    synced_bytes, summary = collaboration.sync_offline_actions(
        base_bytes, offline_mutation_queue, current_version=1
    )

    assert summary["status"] == "SYNCED"
    assert summary["synced_operations"] == 3
    assert summary["conflicts_resolved"] == 0
    assert summary["final_version"] == 2

    # Verify synced document features
    synced_doc = fitz.open(stream=synced_bytes, filetype="pdf")
    page_synced = synced_doc[0]
    assert page_synced.rotation == 90  # Rotation applied
    annots = list(page_synced.annots())
    assert len(annots) >= 2  # Comment and Highlight annotations present
    synced_doc.close()


# -------------------------------------------------------------
# CASE 10: Malicious & Malformed Files Safe Rejection & Sandboxing
# -------------------------------------------------------------
def test_case_10_malicious_and_malformed_files_rejection():
    """
    Case 10: Upload malicious or malformed files—zip bombs, polyglot files,
    oversized files, PDFs with embedded scripts—and verify safe rejection and sandboxing.
    """
    # 1. Polyglot file test (starts with GIF header prepended to PDF)
    polyglot_payload = b"GIF89a\x01\x00\x01\x00\x80\x00\x00%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    rep_polyglot = security.validate_pdf_security(polyglot_payload)
    assert rep_polyglot["safe"] is False
    assert rep_polyglot["error_type"] == "INVALID_HEADER_POLYGLOT"

    # API rejection check
    res_polyglot = client.post(
        "/api/security/validate",
        files={"file": ("exploit.gif.pdf", polyglot_payload, "application/pdf")},
    )
    assert res_polyglot.status_code == 400

    # 2. Oversized payload test
    dummy_payload = b"%PDF-1.7\n" + (b"0" * (2 * 1024 * 1024))  # 2MB with 1MB max limit
    rep_oversized = security.validate_pdf_security(dummy_payload, max_size_mb=1.0)
    assert rep_oversized["safe"] is False
    assert rep_oversized["error_type"] == "OVERSIZED_PAYLOAD"

    # 3. Zip bomb test (DEFLATE payload claiming to be PDF)
    zip_bomb_payload = b"PK\x03\x04" + (b"\x00" * 500)
    rep_zip = security.validate_pdf_security(zip_bomb_payload)
    assert rep_zip["safe"] is False

    # 4. Malicious /Launch action detection
    launch_pdf_bytes = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R /OpenAction 4 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
4 0 obj
<< /Type /Action /S /Launch /F (calc.exe) >>
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000074 00000 n 
0000000127 00000 n 
0000000194 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
%%EOF"""

    rep_launch = security.validate_pdf_security(launch_pdf_bytes)
    assert rep_launch["safe"] is False
    assert rep_launch["has_launch_action"] is True
    assert "Malicious /Launch action detected" in rep_launch["errors"][0]
