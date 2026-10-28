"""
Comprehensive Adversarial Security Test Suite for Vellakshya PDF Workstation.
Validates the full Guidebook Security Checklist:
1. Malicious non-PDF & polyglot header rejection
2. Oversized payload threshold enforcement (HTTP 413)
3. Path traversal attack neutralization on storage and upload paths
4. RBAC privilege escalation prevention (Viewer -> Editor / Owner)
5. Unauthorized document isolation (stranger UUID rejection)
6. Presigned URL forgery and expiration enforcement (HTTP 403)
7. Permanent redaction & sensitive metadata sanitization
8. HTML converter Content Security Policy (CSP) enforcement
9. Owner-only retention purging & object storage deletion
"""

from __future__ import annotations

import base64
import json
import uuid

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.security import redact_text_permanently, sanitize_document, validate_pdf_security
from app.services.storage import storage_instance

client = TestClient(app)


def create_sample_pdf(num_pages: int = 2, secret_text: str = "") -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1} Standard Content", fontsize=14)
        if secret_text:
            page.insert_text((72, 200), secret_text, fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def test_adversarial_non_pdf_and_polyglot_rejection():
    r"""
    Rejects disguised non-PDF binaries (.exe, .sh, .png renamed to .pdf) and invalid magic bytes.
    """
    fake_exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00This is an executable payload disguised as PDF"
    headers = {"X-User-Id": "attacker_user"}

    # 1. API upload rejection
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        files={"file": ("malicious.exe.pdf", fake_exe_bytes, "application/pdf")},
    )
    assert res.status_code == 400
    assert "not a valid pdf" in res.text.lower()

    # 2. Security service validation inspection
    sec_audit = validate_pdf_security(fake_exe_bytes)
    assert sec_audit["safe"] is False
    assert sec_audit["error_type"] == "INVALID_HEADER_POLYGLOT"


def test_adversarial_oversized_payload_rejection():
    r"""
    Enforces maximum upload ceiling (HTTP 413 Payload Too Large) to prevent memory exhaustion.
    """
    # 51 MB dummy payload starting with %PDF-
    oversized_size = 51 * 1024 * 1024
    oversized_bytes = b"%PDF-1.7\n" + (b"A" * (oversized_size - 9))
    headers = {"X-User-Id": "dos_attacker"}

    res = client.post(
        "/api/v2/documents",
        headers=headers,
        files={"file": ("bomb.pdf", oversized_bytes, "application/pdf")},
    )
    assert res.status_code == 413
    assert "payload too large" in res.text.lower()


def test_adversarial_path_traversal_prevention():
    r"""
    Prevents path traversal attacks (../../../../etc/passwd) from escaping storage directory.
    """
    pdf_bytes = create_sample_pdf(num_pages=1)
    headers = {"X-User-Id": "traversal_tester"}

    # 1. Traversal attempt in document creation filename
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        files={"file": ("../../../../etc/passwd.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]
    title = res.json()["document"]["title"]
    # Path traversal dots must be eliminated from title
    assert ".." not in title
    assert "/" not in title
    assert "\\" not in title

    # 2. Traversal attempt in presigned upload URL endpoint
    upload_res = client.post(
        f"/api/v2/documents/{doc_id}/upload-url?filename=../../../../var/log/syslog",
        headers=headers,
    )
    assert upload_res.status_code == 200
    target_key = upload_res.json()["object_key"]
    assert ".." not in target_key
    assert target_key.startswith(f"documents/{doc_id}/uploads/")

    # 3. Direct storage layer containment check
    with pytest.raises(ValueError, match="Path traversal detected"):
        storage_instance.get_object("../../../../etc/passwd")


def test_adversarial_privilege_escalation_rbac():
    r"""
    Prevents role bypasses:
    - Viewer attempting editor endpoint -> HTTP 403
    - Viewer attempting owner share endpoint -> HTTP 403
    - Viewer attempting owner delete endpoint -> HTTP 403
    - Stranger attempting to read private document -> HTTP 403
    """
    pdf_bytes = create_sample_pdf(num_pages=2)
    owner_headers = {"X-User-Id": "doc_owner"}
    viewer_headers = {"X-User-Id": "doc_viewer"}
    stranger_headers = {"X-User-Id": "doc_stranger"}

    # Owner creates document
    create_res = client.post(
        "/api/v2/documents",
        headers=owner_headers,
        files={"file": ("confidential.pdf", pdf_bytes, "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]

    # Share with viewer
    client.post(
        f"/api/v2/documents/{doc_id}/share",
        headers=owner_headers,
        json={"target_user_id": "doc_viewer", "role": "viewer"},
    )

    # 1. Stranger blocked from reading
    stranger_get = client.get(f"/api/v2/documents/{doc_id}", headers=stranger_headers)
    assert stranger_get.status_code == 403

    # 2. Viewer attempts transformation (Editor role required) -> HTTP 403
    viewer_op = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=viewer_headers,
        json={
            "operation": "rotate",
            "base_version": 1,
            "idempotency_key": f"unauth-{uuid.uuid4().hex[:8]}",
            "parameters": {"angle": 90},
        },
    )
    assert viewer_op.status_code == 403
    assert "requires 'editor' permission" in viewer_op.json()["detail"].lower()

    # 3. Viewer attempts to share or elevate permissions (Owner role required) -> HTTP 403
    viewer_share = client.post(
        f"/api/v2/documents/{doc_id}/share",
        headers=viewer_headers,
        json={"target_user_id": "doc_viewer", "role": "owner"},
    )
    assert viewer_share.status_code == 403

    # 4. Viewer attempts to delete document (Owner role required) -> HTTP 403
    viewer_del = client.delete(f"/api/v2/documents/{doc_id}", headers=viewer_headers)
    assert viewer_del.status_code == 403


def test_adversarial_presigned_url_tampering_and_expiration():
    r"""
    Enforces cryptographic validation on presigned URLs:
    - Modified token signature rejected (HTTP 403)
    - Expired token rejected (HTTP 403)
    """
    pdf_bytes = create_sample_pdf(num_pages=1)
    headers = {"X-User-Id": "signer_tester"}

    res = client.post(
        "/api/v2/documents",
        headers=headers,
        files={"file": ("signed.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    ver_res = client.get(f"/api/v2/documents/{doc_id}/versions/1", headers=headers)
    download_url = ver_res.json()["download_url"]
    token = download_url.split("token=")[1]

    # 1. Tamper with token payload (substitute document key without valid signature)
    raw_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
    token_json = json.loads(raw_bytes.decode("utf-8"))
    token_json["key"] = "documents/forged_unauthorized_key.pdf"
    tampered_token = base64.urlsafe_b64encode(json.dumps(token_json).encode("utf-8")).decode(
        "utf-8"
    )
    tampered_res = client.get(f"/api/v2/storage/presigned?token={tampered_token}")
    assert tampered_res.status_code == 403

    # 2. Expired token simulation
    expired_token = storage_instance.generate_presigned_url(
        f"documents/{doc_id}/versions/1.pdf",
        expires_in_seconds=-10,  # Expired in past
    ).split("token=")[1]
    expired_res = client.get(f"/api/v2/storage/presigned?token={expired_token}")
    assert expired_res.status_code == 403


def test_adversarial_retention_and_deletion():
    r"""
    Tests complete document lifecycle termination:
    - Owner can delete document
    - Relational records and object store binaries are purged
    - Subsequent access returns HTTP 404
    """
    pdf_bytes = create_sample_pdf(num_pages=2)
    headers = {"X-User-Id": "purge_owner"}

    create_res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "To Be Purged"},
        files={"file": ("purge.pdf", pdf_bytes, "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]
    object_key = f"documents/{doc_id}/versions/1.pdf"
    assert storage_instance.object_exists(object_key) is True

    # Owner deletes document
    del_res = client.delete(f"/api/v2/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Stored binary must be purged
    assert storage_instance.object_exists(object_key) is False

    # Document metadata query returns 404
    get_res = client.get(f"/api/v2/documents/{doc_id}", headers=headers)
    assert get_res.status_code == 404


def test_adversarial_html_converter_content_security_policy():
    r"""
    Ensures PDF-to-HTML converter applies strict Content Security Policy (CSP)
    to prevent cross-site scripting (XSS) and active script execution.
    """
    pdf_bytes = create_sample_pdf(num_pages=1, secret_text="Confidential Security Analysis")

    # 1. Fixed layout mode
    res_fixed = client.post(
        "/api/convert/html",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "fixed"},
    )
    assert res_fixed.status_code == 200
    html_fixed = res_fixed.text
    assert '<meta http-equiv="Content-Security-Policy"' in html_fixed
    assert "script-src 'none'" in html_fixed

    # 2. Semantic responsive layout mode
    res_semantic = client.post(
        "/api/convert/html",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "semantic"},
    )
    assert res_semantic.status_code == 200
    html_semantic = res_semantic.text
    assert '<meta http-equiv="Content-Security-Policy"' in html_semantic
    assert "script-src 'none'" in html_semantic


def test_adversarial_redaction_and_metadata_sanitization():
    r"""
    Validates permanent cryptographic redaction (glyphs completely purged)
    and metadata sanitization (author, title, keywords erased).
    """
    sensitive_word = "SUPER_SECRET_TOKEN_9999"
    pdf_bytes = create_sample_pdf(num_pages=2, secret_text=sensitive_word)

    # Verify sensitive word initially present in stream
    doc_initial = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc_initial[0].search_for(sensitive_word)) >= 1
    doc_initial.close()

    # 1. Apply permanent redaction
    redacted_bytes, count = redact_text_permanently(pdf_bytes, [sensitive_word])
    assert count >= 1

    # Verify sensitive word is completely absent from redacted binary
    doc_redacted = fitz.open(stream=redacted_bytes, filetype="pdf")
    for page in doc_redacted:
        assert len(page.search_for(sensitive_word)) == 0
    assert sensitive_word.encode("utf-8") not in redacted_bytes
    doc_redacted.close()

    # 2. Sanitize metadata
    doc_meta = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc_meta.set_metadata(
        {
            "title": "Secret Strategy",
            "author": "Dr. Confidential",
            "keywords": "sensitive,classified",
        }
    )
    staged_bytes = doc_meta.tobytes()
    doc_meta.close()

    sanitized_bytes = sanitize_document(staged_bytes)
    doc_clean = fitz.open(stream=sanitized_bytes, filetype="pdf")
    meta = doc_clean.metadata
    assert meta.get("title") == ""
    assert meta.get("author") == ""
    assert meta.get("keywords") == ""
    doc_clean.close()
