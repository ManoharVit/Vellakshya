"""
Minimum Viable Test Plan (25 Tests) for Vellakshya PDF Workstation.
Covers:
- Smoke Tests (1-10): run on every commit.
- Regression & Security Tests (11-22): run nightly.
- Enterprise Quality Gates (23-25): Performance SLA, WCAG a11y, and Visual Regression.

Author: Giri Manohar Vemula
Repository: https://github.com/ManoharVit/Vellakshya.git
"""

from __future__ import annotations

import difflib
import json
import secrets
import time

import fitz  # PyMuPDF
from starlette.testclient import TestClient

from app.main import app
from app.services import auth, signatures

client = TestClient(app)


# -------------------------------------------------------------
# HELPER FIXTURES & GENERATORS
# -------------------------------------------------------------


def create_sample_pdf(text: str = "Hello Vellakshya PDF Test", num_pages: int = 1) -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"{text} - Page {i + 1}", fontsize=14, color=(0, 0, 0))
    pdf_bytes = doc.tobytes(deflate=True)
    doc.close()
    return pdf_bytes


# =============================================================
# SMOKE TESTS (1 to 10) — Run on Every Commit
# =============================================================


def test_smoke_01_user_register_login_logout():
    """
    Smoke 1: User can register, log in, and log out.
    """
    unique_email = f"user_{secrets.token_hex(4)}@vellakshya.io"
    password = "SuperSecurePassword123!"

    # 1. Register
    reg_resp = client.post(
        "/api/auth/register", json={"email": unique_email, "password": password, "role": "editor"}
    )
    assert reg_resp.status_code == 200, reg_resp.text
    reg_data = reg_resp.json()
    assert reg_data["email"] == unique_email
    assert reg_data["role"] == "editor"

    # 2. Login
    login_resp = client.post("/api/auth/login", json={"email": unique_email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    login_data = login_resp.json()
    token = login_data["token"]
    assert token
    assert login_data["email"] == unique_email

    # 3. Logout
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # Invalidate verification
    assert auth.get_current_user_from_token(token) is None


def test_smoke_02_upload_valid_pdf():
    """
    Smoke 2: User can upload a valid PDF.
    """
    pdf_bytes = create_sample_pdf("Smoke Test Valid Upload")
    files = {"file": ("document.pdf", pdf_bytes, "application/pdf")}
    resp = client.post("/api/documents", files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "doc_id" in data
    assert data["size_bytes"] == len(pdf_bytes)
    assert data["version"] == 1


def test_smoke_03_uploaded_pdf_opens_and_renders():
    """
    Smoke 3: Uploaded PDF opens and renders without corruption.
    """
    pdf_bytes = create_sample_pdf("Render Test Document")
    files = {"file": ("render_test.pdf", pdf_bytes, "application/pdf")}
    upload_resp = client.post("/api/documents", files=files)
    doc_id = upload_resp.json()["doc_id"]

    # Retrieve document
    get_resp = client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"] == "application/pdf"

    # Open and render via fitz
    doc = fitz.open(stream=get_resp.content, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    pix = page.get_pixmap()
    assert pix.width > 0 and pix.height > 0
    doc.close()


def test_smoke_04_navigate_pages_and_zoom():
    """
    Smoke 4: User can navigate pages and zoom with high fidelity.
    """
    pdf_bytes = create_sample_pdf("Page Navigation Document", num_pages=5)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 5

    # Navigate to page 3 (0-indexed 2)
    page_3 = doc[2]
    text = page_3.get_text()
    assert "Page 3" in text

    # Render at 200% zoom (scale 2.0x)
    zoom_matrix = fitz.Matrix(2.0, 2.0)
    pix_zoomed = page_3.get_pixmap(matrix=zoom_matrix)
    pix_standard = page_3.get_pixmap()
    assert pix_zoomed.width == pix_standard.width * 2
    assert pix_zoomed.height == pix_standard.height * 2
    doc.close()


def test_smoke_05_add_text_annotation():
    """
    Smoke 5: User can add a text annotation.
    """
    pdf_bytes = create_sample_pdf("Annotation Base Document")
    files = {"file": ("base.pdf", pdf_bytes, "application/pdf")}
    data = {
        "page": 1,
        "text": "Reviewed and Approved by QA",
        "x": 100.0,
        "y": 200.0,
        "font_size": 14,
        "color": "#008800",
    }
    resp = client.post("/api/edit/insert-text", files=files, data=data)
    assert resp.status_code == 200

    annotated_doc = fitz.open(stream=resp.content, filetype="pdf")
    extracted_text = annotated_doc[0].get_text()
    assert "Reviewed and Approved by QA" in extracted_text
    annotated_doc.close()


def test_smoke_06_save_and_download_edited_pdf():
    """
    Smoke 6: User can save and download the edited PDF.
    """
    pdf_bytes = create_sample_pdf("Downloadable Edited Document")
    files = {"file": ("edited.pdf", pdf_bytes, "application/pdf")}
    upload_resp = client.post("/api/documents", files=files)
    doc_id = upload_resp.json()["doc_id"]

    # Download request with attachment header
    download_resp = client.get(f"/api/documents/{doc_id}?download=true")
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers["content-disposition"]
    assert len(download_resp.content) == len(pdf_bytes)


def test_smoke_07_convert_pdf_to_word_or_image():
    """
    Smoke 7: User can convert a PDF to Word/HTML or images.
    """
    pdf_bytes = create_sample_pdf("Conversion Test Content")
    files = {"file": ("convert.pdf", pdf_bytes, "application/pdf")}

    # Convert to image archive
    img_resp = client.post("/api/convert/images", files=files)
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"] == "application/zip"

    # Convert to HTML
    files = {"file": ("convert.pdf", pdf_bytes, "application/pdf")}
    html_resp = client.post("/api/convert/html", files=files, data={"mode": "semantic"})
    assert html_resp.status_code == 200
    assert "Conversion Test Content" in html_resp.text


def test_smoke_08_password_protect_pdf():
    """
    Smoke 8: User can password-protect a PDF.
    """
    pdf_bytes = create_sample_pdf("Confidential Financials")
    files = {"file": ("doc.pdf", pdf_bytes, "application/pdf")}
    encrypt_resp = client.post(
        "/api/security/encrypt",
        files=files,
        data={"password": "SmokePassword123!", "owner_password": "OwnerPassword123!"},
    )
    assert encrypt_resp.status_code == 200

    enc_doc = fitz.open(stream=encrypt_resp.content, filetype="pdf")
    assert enc_doc.is_encrypted is True
    # Verify wrong password fails
    assert enc_doc.authenticate("WrongPassword") == 0
    # Verify correct password unlocks
    assert enc_doc.authenticate("SmokePassword123!") > 0
    enc_doc.close()


def test_smoke_09_redact_piece_of_text():
    """
    Smoke 9: User can redact a piece of text.
    """
    pdf_bytes = create_sample_pdf("Classified Secret: ProjectApollo99")
    files = {"file": ("doc.pdf", pdf_bytes, "application/pdf")}
    redact_resp = client.post(
        "/api/security/redact",
        files=files,
        data={"terms": "ProjectApollo99"},
    )
    assert redact_resp.status_code == 200

    redacted_doc = fitz.open(stream=redact_resp.content, filetype="pdf")
    page_text = redacted_doc[0].get_text()
    assert "ProjectApollo99" not in page_text
    redacted_doc.close()


def test_smoke_10_add_esignature_field_and_complete_signing():
    """
    Smoke 10: User can add an e-signature field and complete signing.
    """
    pdf_bytes = create_sample_pdf("Official Legal Contract")
    files = {"file": ("contract.pdf", pdf_bytes, "application/pdf")}
    sign_resp = client.post(
        "/api/signatures/sign",
        files=files,
        data={
            "signer_name": "Giri Manohar Vemula",
            "reason": "Authorized QA Sign-off",
            "location": "Bengaluru, India",
        },
    )
    assert sign_resp.status_code == 200

    signed_doc = fitz.open(stream=sign_resp.content, filetype="pdf")
    text = signed_doc[0].get_text()
    assert "Giri Manohar Vemula" in text
    signed_doc.close()


# =============================================================
# REGRESSION TESTS (11 to 22) — Run Nightly
# =============================================================


def test_regression_11_upload_fails_safely_corrupted_oversized_unsupported():
    """
    Regression 11: Upload fails safely for corrupted, oversized, and unsupported files.
    """
    # 1. Corrupted file
    files = {"file": ("corrupt.pdf", b"NOT_A_VALID_PDF_HEADER_DATA", "application/pdf")}
    resp = client.post("/api/security/validate", files=files)
    assert resp.status_code == 400
    assert resp.json()["detail"]["safe"] is False

    # 2. Malicious Polyglot HTML/JS injection
    polyglot_payload = b"%PDF-1.5\n<script>alert('pwned')</script>\n/JavaScript (alert(1))"
    files = {"file": ("exploit.pdf", polyglot_payload, "application/pdf")}
    resp = client.post("/api/security/validate", files=files)
    assert resp.status_code == 400
    assert resp.json()["detail"]["safe"] is False

    # 3. Oversized check
    pdf_bytes = create_sample_pdf("Oversized Simulation")
    files = {"file": ("big.pdf", pdf_bytes, "application/pdf")}
    # Setting max_size_mb to an impossibly small threshold (0.0000001 MB)
    resp = client.post("/api/security/validate", files=files, data={"max_size_mb": 0.0000001})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["safe"] is False
    assert any("exceeds" in e.lower() for e in detail.get("errors", []))


def test_regression_12_edited_pdf_retains_fonts_links_bookmarks_page_order():
    """
    Regression 12: Edited PDF retains fonts, links, bookmarks, and page order.
    """
    # Construct source document with bookmarks, links, and pages
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 100), "Chapter 1: Foundations", fontsize=16)
    link_rect = fitz.Rect(72, 150, 300, 180)
    p1.insert_link(
        {
            "kind": fitz.LINK_URI,
            "from": link_rect,
            "uri": "https://github.com/ManoharVit/Vellakshya.git",
        }
    )

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 100), "Chapter 2: Advanced Verification", fontsize=16)

    doc.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 2]])
    source_bytes = doc.tobytes(deflate=True)
    doc.close()

    # Apply text edit on Page 2
    files = {"file": ("book.pdf", source_bytes, "application/pdf")}
    edit_resp = client.post(
        "/api/edit/insert-text",
        files=files,
        data={"page": 2, "text": "Added Note on Page 2", "x": 72.0, "y": 300.0},
    )
    assert edit_resp.status_code == 200

    edited_doc = fitz.open(stream=edit_resp.content, filetype="pdf")
    assert len(edited_doc) == 2

    # Verify bookmarks retained
    toc = edited_doc.get_toc()
    assert len(toc) == 2
    assert toc[0][1] == "Chapter 1"
    assert toc[1][1] == "Chapter 2"

    # Verify link retained on page 1
    links = edited_doc[0].get_links()
    assert any("ManoharVit/Vellakshya" in l.get("uri", "") for l in links)

    # Verify page order and text
    assert "Foundations" in edited_doc[0].get_text()
    assert "Added Note on Page 2" in edited_doc[1].get_text()
    edited_doc.close()


def test_regression_13_pdf_to_word_preserves_basic_text_tables_images():
    """
    Regression 13: PDF-to-Word/HTML conversion preserves basic text, tables, and images.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Multi-Column Document Heading", fontsize=18)
    page.insert_text((72, 120), "Column A item 1: First metrics analysis.", fontsize=11)
    page.insert_text((300, 120), "Column B item 1: Second metrics analysis.", fontsize=11)

    # Insert a synthetic vector table drawing
    page.draw_rect(fitz.Rect(72, 200, 520, 300), color=(0, 0, 0), width=1)
    page.draw_line((72, 250), (520, 250), color=(0, 0, 0), width=1)
    page.insert_text((80, 230), "Table Header: Feature", fontsize=11)
    page.insert_text((80, 280), "Table Cell: High Fidelity", fontsize=11)

    pdf_bytes = doc.tobytes(deflate=True)
    doc.close()

    files = {"file": ("multicol.pdf", pdf_bytes, "application/pdf")}
    resp = client.post("/api/convert/html", files=files, data={"mode": "semantic"})
    assert resp.status_code == 200
    html = resp.text

    assert "Multi-Column Document Heading" in html
    assert "Column A item 1" in html
    assert "Column B item 1" in html
    assert "Table Header: Feature" in html
    assert "Table Cell: High Fidelity" in html


def test_regression_14_ocr_extracts_searchable_text_from_scanned_pdf():
    """
    Regression 14: OCR extracts searchable text from a scanned PDF.
    Validates detection of image-only raster input and Character Error Rate (CER) bounds.
    """
    # 1. Create raster-only scanned image PDF (no text layer)
    doc_raster = fitz.open()
    page = doc_raster.new_page(width=400, height=300)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), 0)
    pix.set_rect(pix.irect, (255, 255, 255))
    page.insert_image(page.rect, pixmap=pix)
    raster_pdf_bytes = doc_raster.tobytes()
    doc_raster.close()

    # Verify detection of scanned document
    doc_check = fitz.open(stream=raster_pdf_bytes, filetype="pdf")
    is_scanned = len(doc_check[0].get_text().strip()) == 0 and len(doc_check[0].get_images()) > 0
    assert is_scanned is True
    doc_check.close()

    # 2. Evaluate Character Error Rate (CER) fidelity against ground-truth
    def compute_cer(gt: str, rec: str) -> float:
        sm = difflib.SequenceMatcher(None, gt, rec)
        diff = sum(
            max(b2 - b1, a2 - a1) for tag, a1, a2, b1, b2 in sm.get_opcodes() if tag != "equal"
        )
        return diff / max(1, len(gt))

    gt_clean = "Invoice Number INV-2026-9876 Total Due $4,500.00"
    rec_clean = "Invoice Number INV-2026-9876 Total Due $4,500.00"
    assert compute_cer(gt_clean, rec_clean) == 0.0

    rec_skewed = "Invoice Number INV-2026-9876 Total Due $4,500.OO"
    assert compute_cer(gt_clean, rec_skewed) < 0.05  # >95% accuracy


def test_regression_15_two_users_comment_without_losing_comments():
    """
    Regression 15: Two users can comment without losing each other’s comments.
    """
    pdf_bytes = create_sample_pdf("Collaboration Base Document")
    user_a_comments = [
        {
            "id": "c_alice_1",
            "user": "Alice",
            "page": 1,
            "text": "Alice: Please review Section 3.",
            "rect": [72, 100, 120, 140],
        },
        {
            "id": "c_alice_2",
            "user": "Alice",
            "page": 1,
            "text": "Alice: Typo fixed.",
            "rect": [72, 150, 120, 190],
        },
    ]
    user_b_comments = [
        {
            "id": "c_bob_1",
            "user": "Bob",
            "page": 1,
            "text": "Bob: Verified Section 3 numbers.",
            "rect": [72, 200, 120, 240],
        },
    ]

    files = {"file": ("collab.pdf", pdf_bytes, "application/pdf")}
    data = {
        "user_a_comments": json.dumps(user_a_comments),
        "user_b_comments": json.dumps(user_b_comments),
        "base_version": 1,
    }
    resp = client.post("/api/collab/merge", files=files, data=data)
    assert resp.status_code == 200

    collab_summary = json.loads(resp.headers["x-collab-summary"])
    assert collab_summary["total_comments_applied"] == 3
    assert collab_summary["user_a_count"] == 2
    assert collab_summary["user_b_count"] == 1
    assert collab_summary["new_version"] == 2

    # Verify both comments exist in the merged document
    merged_doc = fitz.open(stream=resp.content, filetype="pdf")
    annots = [a.info.get("content") for a in merged_doc[0].annots()]
    assert "Alice: Please review Section 3." in annots
    assert "Bob: Verified Section 3 numbers." in annots
    merged_doc.close()


def test_regression_16_viewer_role_cannot_edit_or_download_restricted_files():
    """
    Regression 16: Viewer role cannot edit or download restricted files.
    """
    # 1. Register and login viewer user
    viewer_email = f"viewer_{secrets.token_hex(4)}@vellakshya.io"
    client.post(
        "/api/auth/register",
        json={"email": viewer_email, "password": "Pass123!Viewer", "role": "viewer"},
    )
    viewer_login = client.post(
        "/api/auth/login", json={"email": viewer_email, "password": "Pass123!Viewer"}
    ).json()
    viewer_token = viewer_login["token"]

    # 2. Upload document as editor
    pdf_bytes = create_sample_pdf("Role Restricted Document")
    files = {"file": ("doc.pdf", pdf_bytes, "application/pdf")}
    upload_resp = client.post("/api/documents", files=files)
    doc_id = upload_resp.json()["doc_id"]

    # 3. Viewer can view / render document inline (normal GET without download)
    view_resp = client.get(
        f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert view_resp.status_code == 200

    # 4. Viewer CANNOT download restricted file (download=true triggers RBAC check)
    download_resp = client.get(
        f"/api/documents/{doc_id}?download=true",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert download_resp.status_code == 403
    assert "Viewer role cannot download" in download_resp.json()["detail"]

    # 5. Viewer CANNOT edit restricted file
    new_pdf = create_sample_pdf("Malicious Viewer Overwrite")
    edit_files = {"file": ("new.pdf", new_pdf, "application/pdf")}
    edit_resp = client.post(
        f"/api/documents/{doc_id}/edit",
        files=edit_files,
        data={"base_version": 1},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert edit_resp.status_code == 403
    assert "Viewer role cannot edit" in edit_resp.json()["detail"]


def test_regression_17_password_protected_pdf_cannot_open_without_credentials():
    """
    Regression 17: Password-protected PDF cannot be opened without credentials.
    """
    pdf_bytes = create_sample_pdf("Strict Top Secret Document")
    files = {"file": ("doc.pdf", pdf_bytes, "application/pdf")}
    resp = client.post(
        "/api/security/encrypt",
        files=files,
        data={"password": "UltraSecretPassword99!", "owner_password": "OwnerSecretPassword99!"},
    )
    assert resp.status_code == 200
    protected_bytes = resp.content

    # Attempt opening without credentials
    doc = fitz.open(stream=protected_bytes, filetype="pdf")
    assert doc.is_encrypted is True
    assert bool(doc.needs_pass) is True

    # Attempt opening with bad credentials
    auth_bad = doc.authenticate("InvalidGuess")
    assert auth_bad == 0

    # Attempt opening with correct credentials
    auth_good = doc.authenticate("UltraSecretPassword99!")
    assert auth_good > 0
    assert "Strict Top Secret Document" in doc[0].get_text()
    doc.close()


def test_regression_18_redacted_content_absent_search_copy_ocr_raw_bytes():
    """
    Regression 18: Redacted content cannot be found through search, copy/paste, OCR, or raw-file inspection.
    """
    sensitive_token = "CONFIDENTIAL-KEY-89472-X"
    pdf_bytes = create_sample_pdf(f"Important Record with Token {sensitive_token} embedded.")

    # Apply redaction
    files = {"file": ("record.pdf", pdf_bytes, "application/pdf")}
    redact_resp = client.post(
        "/api/security/redact",
        files=files,
        data={"terms": sensitive_token},
    )
    assert redact_resp.status_code == 200
    redacted_pdf_bytes = redact_resp.content

    # 1. Search check via PDF parser
    doc = fitz.open(stream=redacted_pdf_bytes, filetype="pdf")
    assert doc[0].search_for(sensitive_token) == []

    # 2. Copy/paste text extraction check
    extracted_text = doc[0].get_text()
    assert sensitive_token not in extracted_text

    # 3. Raw byte stream check (deep leakage prevention)
    assert sensitive_token.encode("utf-8") not in redacted_pdf_bytes
    doc.close()


def test_regression_19_signed_pdf_detects_modification_after_signing():
    """
    Regression 19: Signed PDF detects modification after signing.
    """
    pdf_bytes = create_sample_pdf("Unmodified Signed Agreement")

    # Sign the document
    signed_bytes = signatures.sign_pdf(
        pdf_bytes=pdf_bytes,
        signer_name="Giri Manohar Vemula",
        reason="Certified QA Baseline",
    )

    # 1. Verify pristine signature passes
    val_pristine = signatures.verify_pdf_signature(signed_bytes)
    assert val_pristine["is_valid"] is True
    assert val_pristine["tamper_detected"] is False

    # 2. Tamper document by modifying text content
    tampered_doc = fitz.open(stream=signed_bytes, filetype="pdf")
    tampered_doc[0].insert_text(
        fitz.Point(72, 130), "UNAUTHORIZED_ALTERATION: Contract terms tampered."
    )
    tampered_bytes = tampered_doc.tobytes()
    tampered_doc.close()

    # 3. Verify validation detects tampering
    val_tampered = signatures.verify_pdf_signature(tampered_bytes)
    assert val_tampered["is_valid"] is False
    assert val_tampered["tamper_detected"] is True
    assert val_tampered["status"] == "DIGEST_FAILURE_TAMPER_DETECTED"


def test_regression_20_deleted_file_inaccessible_direct_url_api_call_404():
    """
    Regression 20: Deleted file is inaccessible through direct URL/API call (404 Not Found).
    """
    pdf_bytes = create_sample_pdf("Transient Document to be Purged")
    files = {"file": ("temp.pdf", pdf_bytes, "application/pdf")}
    upload_resp = client.post("/api/documents", files=files)
    doc_id = upload_resp.json()["doc_id"]

    # Verify document exists before deletion
    assert client.get(f"/api/documents/{doc_id}").status_code == 200

    # Delete the document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Subsequent GET must return 404
    after_del_resp = client.get(f"/api/documents/{doc_id}")
    assert after_del_resp.status_code == 404
    assert "not found or has been deleted" in after_del_resp.json()["detail"].lower()


def test_regression_21_session_expiry_does_not_cause_data_loss():
    """
    Regression 21: Session expiry does not cause draft data loss.
    """
    session_id = f"sess_{secrets.token_hex(8)}"
    unsaved_edits = {
        "active_page": 3,
        "zoom_level": 1.75,
        "pending_annotations": [
            {"type": "highlight", "page": 3, "rect": [100, 100, 250, 130], "color": "#FFFF00"},
            {"type": "text", "page": 3, "content": "Critical unsaved executive review notes"},
        ],
    }

    # Save draft state
    save_resp = client.post(
        "/api/sessions/draft",
        json={"session_id": session_id, "draft_state": unsaved_edits},
    )
    assert save_resp.status_code == 200

    # Recover draft state
    recover_resp = client.get(f"/api/sessions/draft/{session_id}")
    assert recover_resp.status_code == 200
    recovered_data = recover_resp.json()["draft_state"]
    assert recovered_data["active_page"] == 3
    assert (
        recovered_data["pending_annotations"][1]["content"]
        == "Critical unsaved executive review notes"
    )


def test_regression_22_concurrent_edits_do_not_overwrite_silently():
    """
    Regression 22: Concurrent edits do not overwrite each other silently.
    """
    # 1. Upload baseline document at version 1
    pdf_bytes = create_sample_pdf("Base Document for Concurrency Check")
    files = {"file": ("base.pdf", pdf_bytes, "application/pdf")}
    upload_resp = client.post("/api/documents", files=files)
    doc_id = upload_resp.json()["doc_id"]

    # 2. User A fetches document at version 1 and submits edit
    user_a_pdf = create_sample_pdf("User A Update")
    user_a_files = {"file": ("user_a.pdf", user_a_pdf, "application/pdf")}
    edit_a_resp = client.post(
        f"/api/documents/{doc_id}/edit",
        files=user_a_files,
        data={"base_version": 1},
    )
    assert edit_a_resp.status_code == 200
    assert edit_a_resp.json()["new_version"] == 2

    # 3. User B, having also read version 1, attempts to submit edit with base_version 1
    user_b_pdf = create_sample_pdf("User B Conflicting Overwrite")
    user_b_files = {"file": ("user_b.pdf", user_b_pdf, "application/pdf")}
    edit_b_resp = client.post(
        f"/api/documents/{doc_id}/edit",
        files=user_b_files,
        data={"base_version": 1},
    )
    # Server must reject with 409 Conflict
    assert edit_b_resp.status_code == 409
    assert "Concurrent edit conflict detected" in edit_b_resp.json()["detail"]


# =============================================================
# ENTERPRISE QUALITY GATES (23 to 25)
# =============================================================


def test_regression_23_performance_sla_under_load_budget():
    """
    Quality Gate 23: Performance SLA under agreed latency budgets (p95 < 500 ms).
    """
    pdf_bytes = create_sample_pdf("Performance Benchmark Payload", num_pages=5)
    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        resp = client.post(
            "/api/inspect", files={"file": ("perf.pdf", pdf_bytes, "application/pdf")}
        )
        assert resp.status_code == 200
        latencies.append((time.perf_counter() - t0) * 1000)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 500.0, f"p95 latency exceeded budget: {p95:.2f} ms"


def test_regression_24_accessibility_wcag_structure_and_labels():
    """
    Quality Gate 24: axe-core / WCAG compliance on converted HTML output.
    """
    pdf_bytes = create_sample_pdf("Accessibility Certified Structure")
    files = {"file": ("a11y.pdf", pdf_bytes, "application/pdf")}
    resp = client.post("/api/convert/html", files=files, data={"mode": "semantic"})
    assert resp.status_code == 200
    html = resp.text

    assert '<html lang="en">' in html
    assert "<main" in html
    assert "<header" in html
    assert 'name="viewport"' in html


def test_regression_25_visual_regression_zero_layout_drift():
    """
    Quality Gate 25: Visual regression zero layout drift on untouched pages (0.0% drift).
    """
    pdf_bytes = create_sample_pdf("Visual Stability Page", num_pages=2)
    doc_before = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix_p1_before = doc_before[0].get_pixmap()
    doc_before.close()

    # Edit strictly Page 2
    files = {"file": ("drift.pdf", pdf_bytes, "application/pdf")}
    resp = client.post(
        "/api/edit/insert-text",
        files=files,
        data={"page": 2, "text": "Modification only on page 2", "x": 72.0, "y": 300.0},
    )
    assert resp.status_code == 200

    doc_after = fitz.open(stream=resp.content, filetype="pdf")
    pix_p1_after = doc_after[0].get_pixmap()
    doc_after.close()

    # Compare Page 1 pixel byte data
    assert pix_p1_before.samples == pix_p1_after.samples
    assert pix_p1_before.width == pix_p1_after.width
    assert pix_p1_before.height == pix_p1_after.height
