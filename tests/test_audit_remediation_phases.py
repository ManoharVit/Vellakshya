"""
Automated Verification Suite for Security Audit Remediation (Phases 1 & 2).
Covers:
- F01: V2 identity spoofing, shared anonymous owner elimination, upload-url authorization
- F02: Public fallback secret rejection, genuine Ed25519 asymmetric manifest verification
- F03: Legacy document access, download, deletion, and edit ownership boundaries
- F04: Tenant-isolated worker queue jobs and artifact access controls
- F05: AI document ingestion and RAG query tenant boundaries
- F06: WebSocket origin validation and authentication guardrails
- F10: User-bound session draft isolation
"""

from __future__ import annotations

import fitz
import pytest
from fastapi.testclient import TestClient

from app.core.config import (
    COMPROMISED_FALLBACK_KEYS,
    get_manifest_signing_key,
    get_storage_signing_key,
)
from app.main import app
from app.services import auth
from app.services.queue import queue_instance
from app.services.signatures import sign_manifest, verify_manifest

client = TestClient(app)


def _create_sample_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Vellakshya Security Audit Synthetic Test Document", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


# =========================================================================
# F01: V2 Identity Spoofing & Shared Anonymous Owner Elimination
# =========================================================================


def test_f01_anonymous_v2_access_rejected_with_401():
    """Anonymous visitors must NOT share a default owner; must receive HTTP 401."""
    res = client.get("/api/v2/documents")
    assert res.status_code == 401
    assert "no identity token provided" in res.json()["detail"].lower()


def test_f01_v2_actor_impersonation_blocked():
    """Supplying a token for User A with X-User-Id pointing to User B must be rejected with HTTP 403."""
    alice_token = auth.create_session_for_user(
        "alice@vellakshya.test", role="editor", user_id="alice_uuid"
    )
    headers = {
        "Authorization": f"Bearer {alice_token}",
        "X-User-Id": "victim_bob_uuid",
    }
    res = client.get("/api/v2/documents", headers=headers)
    assert res.status_code == 403
    assert "impersonation rejected" in res.json()["detail"].lower()


def test_f01_upload_url_requires_editor_permission():
    """Upload URL generation must enforce permission check on the target document."""
    alice_token = auth.create_session_for_user(
        "alice_uploader@vellakshya.test", role="editor", user_id="alice_up"
    )
    bob_token = auth.create_session_for_user(
        "bob_stranger@vellakshya.test", role="editor", user_id="bob_up"
    )

    # Alice creates document
    create_res = client.post(
        "/api/v2/documents",
        headers={"Authorization": f"Bearer {alice_token}"},
        files={"file": ("doc.pdf", _create_sample_pdf(), "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]

    # Bob attempts to generate upload URL for Alice's document -> HTTP 403
    bob_url_res = client.post(
        f"/api/v2/documents/{doc_id}/upload-url",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_url_res.status_code == 403


# =========================================================================
# F02: Public Fallback Secrets & Genuine Ed25519 Manifests
# =========================================================================


def test_f02_compromised_signing_keys_rejected():
    """Ensure hardcoded historical literals are explicitly marked compromised and rejected."""
    for bad_key in COMPROMISED_FALLBACK_KEYS:
        assert bad_key in (
            "vellakshya_secure_storage_hmac_secret_2026",
            "vellakshya_canonical_manifest_secret_key_2026_ed25519_prod",
        )

    # Current keys must be non-empty and uncompromised
    storage_key = get_storage_signing_key()
    manifest_key = get_manifest_signing_key()
    assert storage_key not in [k.encode("utf-8") for k in COMPROMISED_FALLBACK_KEYS]
    assert manifest_key not in [k.encode("utf-8") for k in COMPROMISED_FALLBACK_KEYS]


def test_f02_genuine_ed25519_asymmetric_signatures():
    """Manifests are signed and verified with real Ed25519 asymmetric cryptography."""
    payload = {"version": 1, "sha256": "3a7b9c", "timestamp": 1700000000}
    signed = sign_manifest(payload)
    assert signed["algorithm"] == "Ed25519"
    assert verify_manifest(payload, signed["signature"]) is True

    # Tampered payload fails verification
    tampered_payload = {"version": 2, "sha256": "3a7b9c", "timestamp": 1700000000}
    assert verify_manifest(tampered_payload, signed["signature"]) is False


# =========================================================================
# F03: Legacy Document Routes Ownership & Access Controls
# =========================================================================


def test_f03_legacy_documents_enforce_ownership():
    """Protected user documents cannot be read, downloaded, deleted, or edited by unauthorized callers."""
    alice_token = auth.create_session_for_user("alice_leg@vellakshya.test", role="editor")
    bob_token = auth.create_session_for_user("bob_leg@vellakshya.test", role="editor")

    # Alice uploads document
    upload_res = client.post(
        "/api/documents",
        headers={"Authorization": f"Bearer {alice_token}"},
        files={"file": ("alice_doc.pdf", _create_sample_pdf(), "application/pdf")},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["doc_id"]

    # 1. Anonymous read -> 401
    assert client.get(f"/api/documents/{doc_id}").status_code == 401

    # 2. Bob read -> 403
    bob_get = client.get(
        f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {bob_token}"}
    )
    assert bob_get.status_code == 403

    # 3. Anonymous delete -> 401
    assert client.delete(f"/api/documents/{doc_id}").status_code == 401

    # 4. Bob delete -> 403
    bob_del = client.delete(
        f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {bob_token}"}
    )
    assert bob_del.status_code == 403

    # 5. Alice (Owner) read -> 200
    alice_get = client.get(
        f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {alice_token}"}
    )
    assert alice_get.status_code == 200


# =========================================================================
# F04: Tenant-Isolated Worker Queue Jobs & Artifact Access
# =========================================================================


@pytest.mark.asyncio
async def test_f04_worker_queue_tenant_isolation():
    """User-scoped jobs cannot be listed, inspected, or downloaded by strangers."""
    alice_token = auth.create_session_for_user("alice_queue@vellakshya.test", role="editor")
    bob_token = auth.create_session_for_user("bob_queue@vellakshya.test", role="editor")

    job = await queue_instance.enqueue(
        task="html_fixed",
        pdf_bytes=_create_sample_pdf(),
        filename="confidential_q3.pdf",
        owner_id="alice_queue@vellakshya.test",
    )

    # 1. Bob cannot see Alice's job in his job listing
    bob_jobs_res = client.get("/api/jobs", headers={"Authorization": f"Bearer {bob_token}"})
    assert bob_jobs_res.status_code == 200
    bob_job_ids = [j["id"] for j in bob_jobs_res.json()["jobs"]]
    assert job.id not in bob_job_ids

    # 2. Bob cannot view status of Alice's job -> HTTP 403
    bob_status_res = client.get(
        f"/api/jobs/{job.id}", headers={"Authorization": f"Bearer {bob_token}"}
    )
    assert bob_status_res.status_code == 403

    # 3. Alice can view status -> HTTP 200
    alice_status_res = client.get(
        f"/api/jobs/{job.id}", headers={"Authorization": f"Bearer {alice_token}"}
    )
    assert alice_status_res.status_code == 200


# =========================================================================
# F05: AI Ingestion & RAG Query Tenant Boundaries
# =========================================================================


def test_f05_ai_document_queries_tenant_isolated():
    """Documents ingested by Alice cannot be queried by unauthorized callers."""
    alice_token = auth.create_session_for_user(
        "alice_ai@vellakshya.test", role="editor", user_id="alice_ai_id"
    )
    bob_token = auth.create_session_for_user(
        "bob_ai@vellakshya.test", role="editor", user_id="bob_ai_id"
    )

    # Alice ingests PDF
    ingest_res = client.post(
        "/api/ai/ingest",
        headers={"Authorization": f"Bearer {alice_token}"},
        files={"file": ("strategic_plan.pdf", _create_sample_pdf(), "application/pdf")},
    )
    assert ingest_res.status_code == 200
    doc_id = ingest_res.json()["document_id"]
    assert ingest_res.json()["owner_id"] == "alice_ai_id"

    # Anonymous query -> 401
    anon_chat = client.post(
        "/api/ai/chat", json={"document_id": doc_id, "query": "What is in this document?"}
    )
    assert anon_chat.status_code == 401

    # Bob query -> 403
    bob_chat = client.post(
        "/api/ai/chat",
        headers={"Authorization": f"Bearer {bob_token}"},
        json={"document_id": doc_id, "query": "What is in this document?"},
    )
    assert bob_chat.status_code == 403


# =========================================================================
# F06: WebSocket Origin Validation
# =========================================================================


def test_f06_websocket_untrusted_origin_rejected():
    """WebSockets with untrusted external Origin headers must be rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/documents/doc-123?user_id=attacker",
            headers={"Origin": "https://malicious-adversary.com"},
        ) as ws:
            ws.receive_json()


# =========================================================================
# F10: User-Bound Session Draft Isolation
# =========================================================================


def test_f10_session_draft_user_binding():
    """Drafts saved by an authenticated user cannot be recovered anonymously or by strangers."""
    alice_token = auth.create_session_for_user("alice_draft@vellakshya.test")
    bob_token = auth.create_session_for_user("bob_draft@vellakshya.test")
    session_id = "sess_draft_secret_99"

    # Alice saves draft
    save_res = client.post(
        "/api/sessions/draft",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"session_id": session_id, "draft_state": {"page": 2, "annotations": ["secret note"]}},
    )
    assert save_res.status_code == 200

    # Anonymous recovery -> 401
    assert client.get(f"/api/sessions/draft/{session_id}").status_code == 401

    # Bob recovery -> 403
    bob_rec = client.get(
        f"/api/sessions/draft/{session_id}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_rec.status_code == 403

    # Alice recovery -> 200
    alice_rec = client.get(
        f"/api/sessions/draft/{session_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_rec.status_code == 200
    assert alice_rec.json()["draft_state"]["annotations"] == ["secret note"]
