"""
Comprehensive persistence and integrity tests for Vellakshya V2 API.
Tests relational DB persistence, version tracking, S3-compatible presigned storage,
optimistic concurrency control (HTTP 409), idempotency replay, Ed25519 manifests,
tamper detection, RBAC authorization, threaded geometry comments, and hash-chained audit trails.
"""

import hashlib
import uuid

import fitz
from fastapi.testclient import TestClient

from app.main import app
from app.services.document_service import DocumentService
from app.services.storage import storage_instance

client = TestClient(app)


def create_sample_pdf(num_pages: int = 3, text: str = "Enterprise Workstation Document") -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"{text} - Page {i + 1}", fontsize=16)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_v2_document_creation_and_version1():
    pdf_bytes = create_sample_pdf(num_pages=2, text="Version 1 Document")
    headers = {"X-User-Id": "alice_test"}

    # 1. Create document
    response = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Quarterly Financial Report"},
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    doc_id = data["document"]["id"]
    assert data["document"]["title"] == "Quarterly Financial Report"
    assert data["document"]["current_version"] == 1
    assert data["document"]["owner_id"] == "alice_test"
    assert data["version"]["version_no"] == 1
    assert data["version"]["byte_size"] == len(pdf_bytes)
    assert data["version"]["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert "upload_url" in data or "download_url" in data or "id" in data["version"]

    # 2. Query document info
    get_res = client.get(f"/api/v2/documents/{doc_id}", headers=headers)
    assert get_res.status_code == 200
    doc_info = get_res.json()
    assert doc_info["id"] == doc_id
    assert doc_info["current_version"] == 1
    assert doc_info["role"] == "owner"

    # 3. List versions
    versions_res = client.get(f"/api/v2/documents/{doc_id}/versions", headers=headers)
    assert versions_res.status_code == 200
    versions_data = versions_res.json()
    assert versions_data["count"] == 1
    assert versions_data["versions"][0]["version_no"] == 1


def test_v2_presigned_storage_access_and_tamper_proofing():
    pdf_bytes = create_sample_pdf(num_pages=1, text="Secure Storage PDF")
    headers = {"X-User-Id": "alice_sec"}

    # Upload document
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Secure Document"},
        files={"file": ("secure.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    # Get version 1 info with presigned download url
    ver_res = client.get(f"/api/v2/documents/{doc_id}/versions/1", headers=headers)
    assert ver_res.status_code == 200
    ver_data = ver_res.json()
    download_url = ver_data["download_url"]
    assert "/api/v2/storage/presigned?token=" in download_url

    # Download binary using the presigned URL
    binary_res = client.get(download_url)
    assert binary_res.status_code == 200
    assert binary_res.content == pdf_bytes
    assert hashlib.sha256(binary_res.content).hexdigest() == ver_data["sha256"]

    # Test forged token
    forged_url = "/api/v2/storage/presigned?token=forged.invalid.token"
    forged_res = client.get(forged_url)
    assert forged_res.status_code == 403


def test_v2_optimistic_concurrency_control():
    r"""
    Validates optimistic concurrency control ($$base\_version$$ check).
    Submitting an operation against an obsolete baseVersion MUST return HTTP 409 Conflict.
    """
    pdf_bytes = create_sample_pdf(num_pages=4, text="Multi Page Doc")
    headers = {"X-User-Id": "editor_user"}

    # 1. Create document (current_version = 1)
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Concurrency Doc"},
        files={"file": ("conc.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    # 2. Valid operation with baseVersion=1 -> advances to version 2
    k1 = f"op-rot-{uuid.uuid4().hex[:8]}"
    rotate_res = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=headers,
        json={
            "operation": "rotate_page",
            "base_version": 1,
            "idempotency_key": k1,
            "parameters": {"page_number": 1, "rotation": 90},
        },
    )
    assert rotate_res.status_code == 200, rotate_res.text
    rot_data = rotate_res.json()
    assert rot_data["version_no"] == 2
    assert rot_data["base_version"] == 1
    assert rot_data["operation_type"] == "rotate_page"

    # Verify document current_version is now 2
    doc_res = client.get(f"/api/v2/documents/{doc_id}", headers=headers)
    assert doc_res.json()["current_version"] == 2

    # 3. Conflicting operation: Client submits with stale base_version=1
    k_stale = f"op-del-{uuid.uuid4().hex[:8]}"
    conflict_res = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=headers,
        json={
            "operation": "delete_page",
            "base_version": 1,  # Stale! Current is 2
            "idempotency_key": k_stale,
            "parameters": {"page_number": 2},
        },
    )
    assert conflict_res.status_code == 409, "Expected 409 Conflict for stale base_version"
    conflict_err = conflict_res.json()
    assert "version conflict" in conflict_err["detail"].lower()

    # 4. Correct operation with base_version=2 -> advances to version 3
    k_valid = f"op-del-{uuid.uuid4().hex[:8]}"
    valid_next = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=headers,
        json={
            "operation": "delete_page",
            "base_version": 2,
            "idempotency_key": k_valid,
            "parameters": {"page_number": 2},
        },
    )
    assert valid_next.status_code == 200
    assert valid_next.json()["version_no"] == 3


def test_v2_idempotency_replay():
    """
    Submitting the exact same operation with the same idempotencyKey returns
    the previously computed version without incrementing version or re-executing.
    """
    pdf_bytes = create_sample_pdf(num_pages=3, text="Idempotency Test")
    headers = {"X-User-Id": "idemp_user"}

    # Create doc
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Idempotent Document"},
        files={"file": ("idemp.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    idem_key = f"client-tx-{uuid.uuid4().hex}"
    payload = {
        "operation": "rotate_page",
        "base_version": 1,
        "idempotency_key": idem_key,
        "parameters": {"page_number": 1, "rotation": 180},
    }

    # First attempt
    res1 = client.post(f"/api/v2/documents/{doc_id}/operations", headers=headers, json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["version_no"] == 2
    assert data1.get("replayed", False) is False

    # Second attempt (exact same idempotency key)
    res2 = client.post(f"/api/v2/documents/{doc_id}/operations", headers=headers, json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["version_no"] == 2
    assert data2["replayed"] is True
    assert data2["sha256"] == data1["sha256"]

    # Verify versions table only has 2 versions total
    versions_res = client.get(f"/api/v2/documents/{doc_id}/versions", headers=headers)
    assert versions_res.json()["count"] == 2


def test_v2_tamper_detection_and_ed25519_manifest():
    """
    Validates cryptographic tamper detection via Ed25519 integrity manifests.
    Direct modification of stored bytes triggers 'content_modified' status.
    """
    pdf_bytes = create_sample_pdf(num_pages=2, text="Tamper Audit PDF")
    headers = {"X-User-Id": "audit_user"}

    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Tamper Test"},
        files={"file": ("tamper.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    # 1. Clean verification
    int_res = client.get(f"/api/v2/documents/{doc_id}/integrity", headers=headers)
    assert int_res.status_code == 200
    int_data = int_res.json()
    assert int_data["status"] == "verified"
    assert int_data["signature_valid"] is True
    assert int_data["stored_sha256"] == int_data["computed_sha256"]

    # 2. Deliberately tamper with binary object in storage
    object_key = f"documents/{doc_id}/versions/1.pdf"
    corrupted_bytes = pdf_bytes[:-10] + b"CORRUPTED!"
    storage_instance.store_object(object_key, corrupted_bytes, "application/pdf")

    # 3. Verification must fail and report content_modified
    tamper_res = client.get(f"/api/v2/documents/{doc_id}/integrity", headers=headers)
    assert tamper_res.status_code == 200
    tamper_data = tamper_res.json()
    assert tamper_data["status"] == "content_modified"
    assert tamper_data["signature_valid"] is True  # Manifest was signed legitimately
    assert tamper_data["stored_sha256"] != tamper_data["computed_sha256"]  # Content modified!


def test_v2_role_based_access_control():
    """
    Tests fine-grained authorization:
    - Owner can share and edit
    - Viewer can read but cannot perform operations (HTTP 403)
    - Reviewer can comment
    - Non-permitted user is denied (HTTP 403)
    """
    pdf_bytes = create_sample_pdf(num_pages=2, text="RBAC Testing PDF")
    owner_headers = {"X-User-Id": "alice_owner"}
    bob_headers = {"X-User-Id": "bob_viewer"}
    charlie_headers = {"X-User-Id": "charlie_stranger"}

    # Alice creates document
    create_res = client.post(
        "/api/v2/documents",
        headers=owner_headers,
        data={"title": "Confidential Strategy"},
        files={"file": ("strat.pdf", pdf_bytes, "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]

    # Charlie (stranger) tries to access
    charlie_res = client.get(f"/api/v2/documents/{doc_id}", headers=charlie_headers)
    assert charlie_res.status_code == 403

    # Alice shares with Bob as viewer
    share_res = client.post(
        f"/api/v2/documents/{doc_id}/share",
        headers=owner_headers,
        json={"target_user_id": "bob_viewer", "role": "viewer"},
    )
    assert share_res.status_code == 200

    # Bob can view document
    bob_view = client.get(f"/api/v2/documents/{doc_id}", headers=bob_headers)
    assert bob_view.status_code == 200
    assert bob_view.json()["role"] == "viewer"

    # Bob (viewer) tries to perform an edit operation -> rejected with 403
    bob_key1 = f"bob-op1-{uuid.uuid4().hex[:8]}"
    bob_op = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=bob_headers,
        json={
            "operation": "rotate_page",
            "base_version": 1,
            "idempotency_key": bob_key1,
            "parameters": {"page_number": 1, "rotation": 90},
        },
    )
    assert bob_op.status_code == 403
    assert "requires 'editor' permission" in bob_op.json()["detail"].lower()

    # Alice upgrades Bob to editor
    upgrade_res = client.post(
        f"/api/v2/documents/{doc_id}/share",
        headers=owner_headers,
        json={"target_user_id": "bob_viewer", "role": "editor"},
    )
    assert upgrade_res.status_code == 200

    # Now Bob can perform the operation
    bob_key2 = f"bob-op2-{uuid.uuid4().hex[:8]}"
    bob_op2 = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=bob_headers,
        json={
            "operation": "rotate_page",
            "base_version": 1,
            "idempotency_key": bob_key2,
            "parameters": {"page_number": 1, "rotation": 90},
        },
    )
    assert bob_op2.status_code == 200
    assert bob_op2.json()["version_no"] == 2


def test_v2_threaded_comments_with_geometry():
    """
    Validates page-anchored, bounding-box contextual comments with reply threading.
    """
    pdf_bytes = create_sample_pdf(num_pages=3, text="Review Doc")
    headers = {"X-User-Id": "reviewer_dan"}

    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Design Specs"},
        files={"file": ("specs.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    # 1. Post top-level comment anchored to page 1 with bounding box
    c1_res = client.post(
        f"/api/v2/documents/{doc_id}/comments",
        headers=headers,
        json={
            "page_number": 1,
            "bounding_box": [50.0, 100.0, 200.0, 40.0],
            "content": "Please verify font contrast on this header.",
        },
    )
    assert c1_res.status_code == 201
    c1_data = c1_res.json()
    comment_id = c1_data["id"]
    assert c1_data["page_number"] == 1
    assert c1_data["bounding_box"] == [50.0, 100.0, 200.0, 40.0]

    # 2. Share with author_eve as reviewer so they have permission to comment
    share_res = client.post(
        f"/api/v2/documents/{doc_id}/share",
        headers=headers,
        json={"target_user_id": "author_eve", "role": "reviewer"},
    )
    assert share_res.status_code == 200

    # 3. Post reply
    reply_res = client.post(
        f"/api/v2/documents/{doc_id}/comments",
        headers={"X-User-Id": "author_eve"},
        json={
            "page_number": 1,
            "content": "Confirmed, updated to WCAG AA 4.5:1 ratio.",
            "parent_comment_id": comment_id,
        },
    )
    assert reply_res.status_code == 201
    assert reply_res.json()["parent_comment_id"] == comment_id

    # 4. List comments
    list_res = client.get(f"/api/v2/documents/{doc_id}/comments", headers=headers)
    assert list_res.status_code == 200
    comments = list_res.json()["comments"]
    assert len(comments) == 2


def test_v2_hash_chained_audit_trail():
    r"""
    Validates tamper-evident hash chaining ($$event\_hash = SHA-256(canonical \mathbin{\Vert} prev\_hash)$$).
    """
    pdf_bytes = create_sample_pdf(num_pages=3, text="Audited Workflow")
    headers = {"X-User-Id": "auditor_user"}

    # 1. Document creation records genesis audit event
    res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Audit Compliance Report"},
        files={"file": ("audit.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]

    # 2. Perform two operations
    op1_key = f"audit-op1-{uuid.uuid4().hex[:8]}"
    op2_key = f"audit-op2-{uuid.uuid4().hex[:8]}"
    op1_res = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=headers,
        json={
            "operation": "rotate_page",
            "base_version": 1,
            "idempotency_key": op1_key,
            "parameters": {"page_number": 1, "rotation": 90},
        },
    )
    assert op1_res.status_code == 200, op1_res.text

    op2_res = client.post(
        f"/api/v2/documents/{doc_id}/operations",
        headers=headers,
        json={
            "operation": "delete_page",
            "base_version": 2,
            "idempotency_key": op2_key,
            "parameters": {"page_number": 3},
        },
    )
    assert op2_res.status_code == 200, op2_res.text

    # 3. Retrieve audit trail
    audit_res = client.get(f"/api/v2/documents/{doc_id}/audit", headers=headers)
    assert audit_res.status_code == 200
    trail = audit_res.json()["events"]
    assert len(trail) >= 3  # created + 2 operations

    # 4. Verify cryptographic hash chain
    prev_hash = None
    for event in trail:
        assert event["previous_event_hash"] == prev_hash
        expected_hash = DocumentService._compute_event_hash(event["event_data"], prev_hash)
        assert event["event_hash"] == expected_hash, (
            f"Hash mismatch in audit chain at event {event['id']}"
        )
        prev_hash = event["event_hash"]
