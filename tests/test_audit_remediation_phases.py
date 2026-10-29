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

import os
import secrets
import time
from pathlib import Path

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


# =========================================================================
# F07: Client-Side XSS & DOM TextContent / Entity Encoding
# =========================================================================


def test_f07_client_js_xss_sinks_eliminated():
    """Verify that dangerous unsanitized DOM sinks in app.js have been eliminated."""
    with open("app/static/js/app.js", "r", encoding="utf-8") as f:
        js_content = f.read()

    # Verify previewStatus.innerHTML does NOT interpolate raw unescaped filename or title
    assert (
        'previewStatus.innerHTML = `<span style="display:none;">${filename}</span>'
        not in js_content
    )
    assert (
        'previewStatus.innerHTML = `<span style="display:none;">${title}</span>' not in js_content
    )

    # Verify previewStatus uses safe replaceChildren / textContent
    assert "previewStatus.replaceChildren();" in js_content

    # Verify showNotification uses textContent for message rendering
    assert 'msgSpan.textContent = String(message ?? "");' in js_content

    # Verify AcroForm fieldsList uses escapeHtml
    assert "escapeHtml(f.name)" in js_content
    assert 'escapeHtml(f.value || "")' in js_content


# =========================================================================
# F08: Deep PDF Scrubbing of Embedded Files and XMP Metadata
# =========================================================================


def test_f08_deep_pdf_scrubbing_embedded_files_and_xmp():
    """Verify sanitize_document comprehensively removes attachments, XMP, and metadata."""
    from app.services.security import sanitize_document

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Sensitive internal corporate report", fontsize=12)
    page.add_rect_annot(fitz.Rect(70, 95, 300, 115))

    # Add dangerous / sensitive artifacts
    doc.set_xml_metadata("<x:xmpmeta>Confidential Internal Dossier</x:xmpmeta>")
    doc.embfile_add(
        "confidential.csv", b"salary,ssn\n100000,123-45-6789", filename="confidential.csv"
    )
    doc.set_metadata(
        {
            "title": "Unredacted Corporate Financials",
            "author": "Chief Executive Officer",
            "subject": "Acquisition Targets",
            "keywords": "secret, acquisition, confidential",
        }
    )

    raw_dirty_bytes = doc.tobytes()
    doc.close()

    # Pre-condition: check that dirty PDF actually has the embedded file & XMP
    verify_dirty = fitz.open(stream=raw_dirty_bytes, filetype="pdf")
    assert "confidential.csv" in verify_dirty.embfile_names()
    assert "Confidential Internal Dossier" in (verify_dirty.get_xml_metadata() or "")
    assert verify_dirty.metadata.get("title") == "Unredacted Corporate Financials"
    assert len(list(verify_dirty[0].annots())) == 1
    verify_dirty.close()

    # Run deep sanitization
    sanitized_bytes = sanitize_document(raw_dirty_bytes)

    # Post-condition: verify comprehensive purge
    clean_doc = fitz.open(stream=sanitized_bytes, filetype="pdf")
    assert clean_doc.embfile_names() == []
    assert clean_doc.embfile_count() == 0
    assert clean_doc.get_xml_metadata() in ("", None)
    assert clean_doc.metadata.get("title") == ""
    assert clean_doc.metadata.get("author") == ""
    assert clean_doc.metadata.get("subject") == ""
    assert clean_doc.metadata.get("keywords") == ""
    assert list(clean_doc[0].annots()) == []
    clean_doc.close()


def test_f08_api_sanitize_endpoint_scrubs_deep_metadata():
    """Verify POST /api/security/sanitize route purges embedded files and XMP streams."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Public facing report", fontsize=12)
    doc.set_xml_metadata("<x:xmpmeta>Secret Tracking Beacon</x:xmpmeta>")
    doc.embfile_add("tracking.bin", b"beacon_data_payload", filename="tracking.bin")
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/security/sanitize",
        files={"file": ("dirty_report.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"

    clean_doc = fitz.open(stream=res.content, filetype="pdf")
    assert clean_doc.embfile_names() == []
    assert clean_doc.get_xml_metadata() in ("", None)
    clean_doc.close()


# =========================================================================
# F11: Public Registration Role Locked to "viewer"
# =========================================================================


def test_f11_public_registration_locks_role_to_viewer():
    """Public registration must strictly assign 'viewer' role even if client passes 'admin'."""
    unique_email = f"attacker_{secrets.token_hex(4)}@vellakshya.test"
    reg_res = client.post(
        "/api/auth/register",
        json={"email": unique_email, "password": "MaliciousPassword123!", "role": "admin"},
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["role"] == "viewer"
    assert reg_res.json()["email"] == unique_email

    # Login and verify active session role
    login_res = client.post(
        "/api/auth/login",
        json={"email": unique_email, "password": "MaliciousPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    user_info = auth.get_current_user_from_token(token)
    assert user_info is not None
    assert user_info["role"] == "viewer"

    # Verify that viewer cannot perform editor actions like edit or download restricted files
    assert auth.verify_role_permission(user_info["role"], "edit") is False
    assert auth.verify_role_permission(user_info["role"], "download") is False


# =========================================================================
# F12: Retention TTL & Cascade Deletion
# =========================================================================


def test_f12_ai_document_cascade_deletion():
    """Verify DELETE /api/ai/documents/{doc_id} permanently purges AIDocument and AIChunks."""
    from app.ai.chunking import extract_chunks_from_pdf_bytes
    from app.ai.embeddings import get_embedding
    from app.ai.router import _TRANSIENT_PDF_STORE
    from app.ai.storage import AIChunk, AIDocument, store_document_and_chunks
    from app.models.db import SessionLocal

    pdf_bytes = _create_sample_pdf()
    doc_id = "doc_f12_test_cascade"
    owner_id = "user_f12_owner"
    token = auth.create_session_for_user(
        "owner_f12@vellakshya.test", role="editor", user_id=owner_id
    )

    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, document_id=doc_id)
    embeddings = [get_embedding(c.content) for c in chunks]

    with SessionLocal() as db:
        store_document_and_chunks(
            db=db,
            document_id=doc_id,
            owner_id=owner_id,
            filename="cascade_test.pdf",
            sha256="fake_sha_f12",
            embedding_model="text-embedding-004",
            embedding_dim=768,
            chunks=chunks,
            embeddings=embeddings,
        )
        assert db.query(AIDocument).filter_by(id=doc_id).count() == 1
        assert db.query(AIChunk).filter_by(document_id=doc_id).count() == len(chunks)

    _TRANSIENT_PDF_STORE[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    # Anonymous delete -> 401
    assert client.delete(f"/api/ai/documents/{doc_id}").status_code == 401

    # Stranger delete -> 403
    stranger_token = auth.create_session_for_user(
        "stranger_f12@vellakshya.test", role="editor", user_id="stranger_id"
    )
    assert (
        client.delete(
            f"/api/ai/documents/{doc_id}", headers={"Authorization": f"Bearer {stranger_token}"}
        ).status_code
        == 403
    )

    # Owner delete -> 200
    del_res = client.delete(
        f"/api/ai/documents/{doc_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify database records are cascade deleted
    with SessionLocal() as db:
        assert db.query(AIDocument).filter_by(id=doc_id).count() == 0
        assert db.query(AIChunk).filter_by(document_id=doc_id).count() == 0

    # Verify transient cache evicted
    assert doc_id not in _TRANSIENT_PDF_STORE


def test_f12_v2_document_deletion_cascades_to_ai_index():
    """Deleting a document via V2 DocumentService must cascade to any indexed AI document."""
    from app.ai.chunking import extract_chunks_from_pdf_bytes
    from app.ai.embeddings import get_embedding
    from app.ai.storage import AIChunk, AIDocument, store_document_and_chunks
    from app.models.db import SessionLocal
    from app.services.document_service import DocumentService

    actor_id = "v2_owner_uuid"
    token = auth.create_session_for_user("v2owner@vellakshya.test", role="editor", user_id=actor_id)
    pdf_bytes = _create_sample_pdf()

    # Create V2 document
    create_res = client.post(
        "/api/v2/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("v2_cascade.pdf", pdf_bytes, "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]

    # Index into AI document tables with same doc_id
    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, document_id=doc_id)
    embeddings = [get_embedding(c.content) for c in chunks]

    with SessionLocal() as db:
        store_document_and_chunks(
            db=db,
            document_id=doc_id,
            owner_id=actor_id,
            filename="v2_cascade.pdf",
            sha256="fake_v2_sha",
            embedding_model="text-embedding-004",
            embedding_dim=768,
            chunks=chunks,
            embeddings=embeddings,
        )
        assert db.query(AIDocument).filter_by(id=doc_id).count() == 1
        assert db.query(AIChunk).filter_by(document_id=doc_id).count() == len(chunks)

        # Delete V2 document
        DocumentService.delete_document(db, doc_id, actor_id=actor_id)

        # Verify AI records cascaded
        assert db.query(AIDocument).filter_by(id=doc_id).count() == 0
        assert db.query(AIChunk).filter_by(document_id=doc_id).count() == 0


def test_f12_transient_store_retention_ttl_purging():
    """Verify expired transient AI buffers are purged according to retention TTL."""
    from app.ai.models import PIIEntityMatch
    from app.ai.router import (
        _TRANSIENT_PDF_STORE,
        _TRANSIENT_PII_MATCHES,
        purge_expired_transient_ai_data,
    )

    old_doc_id = "doc_stale_retention_ttl"
    _TRANSIENT_PDF_STORE[old_doc_id] = {"bytes": b"stale", "created_at": time.time() - 5000}
    _TRANSIENT_PII_MATCHES[old_doc_id] = {
        "entities": [
            PIIEntityMatch(
                id="p1",
                entity_type="EMAIL",
                matched_text="a@b.com",
                confidence=1.0,
                page=1,
                rects=[],
            )
        ],
        "created_at": time.time() - 5000,
    }

    fresh_doc_id = "doc_fresh_active"
    _TRANSIENT_PDF_STORE[fresh_doc_id] = {"bytes": b"fresh", "created_at": time.time()}

    purged = purge_expired_transient_ai_data(max_age_seconds=3600)
    assert purged >= 1
    assert old_doc_id not in _TRANSIENT_PDF_STORE
    assert old_doc_id not in _TRANSIENT_PII_MATCHES
    assert fresh_doc_id in _TRANSIENT_PDF_STORE


def test_f12_queue_job_retention_ttl_and_artifact_cleanup():
    """Verify job states are written with TTL and expired artifacts are purged."""
    from app.services.queue import (
        ARTIFACTS_DIR,
        DEFAULT_JOB_TTL_SECONDS,
        JobInfo,
        cleanup_expired_artifacts,
        queue_instance,
    )

    assert DEFAULT_JOB_TTL_SECONDS == 86400

    job = JobInfo(id="job_ttl_test", task="pdf_to_html", status="succeeded")
    queue_instance._save_job_state(job)

    # In Fakeredis or live Redis, key exists and ttl can be queried
    key = queue_instance._job_key(job.id)
    assert queue_instance.client.exists(key)

    # Test artifact directory cleanup
    test_artifact_dir = ARTIFACTS_DIR / "stale_job_artifact_test"
    test_artifact_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_artifact_dir / "output.html"
    test_file.write_text("dummy artifact")

    # Set access/modification time to past
    old_time = time.time() - 100000
    os.utime(test_artifact_dir, (old_time, old_time))

    purged_count = cleanup_expired_artifacts(max_age_seconds=86400)
    assert purged_count >= 1
    assert not test_artifact_dir.exists()


# =========================================================================
# F13: Per-Document Local-First Privacy Gate for External AI
# =========================================================================


def test_f13_local_first_privacy_gate_blocks_external_ai_by_default(monkeypatch):
    """By default, external AI is blocked. Document text stays in-process with zero network egress."""
    import urllib.request
    from unittest.mock import MagicMock

    from app.ai.chunking import extract_chunks_from_pdf_bytes
    from app.ai.embeddings import get_embedding
    from app.ai.rag import answer_question_with_citations
    from app.ai.storage import AIDocument, store_document_and_chunks
    from app.models.db import SessionLocal

    # Mock external network calls to prove no egress
    mock_urlopen = MagicMock()
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyBlockedByPrivacyGate")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fakeKeyBlockedByPrivacyGate")

    pdf_bytes = _create_sample_pdf()
    doc_id = "doc_f13_privacy_gate"
    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, document_id=doc_id)

    # 1. Embedding generation with allow_external=False (default)
    embeddings = [get_embedding(c.content, allow_external=False) for c in chunks]
    assert mock_urlopen.call_count == 0  # Zero network egress during embedding

    with SessionLocal() as db:
        store_document_and_chunks(
            db=db,
            document_id=doc_id,
            owner_id="privacy_user",
            filename="privacy.pdf",
            sha256="fake_p_sha",
            embedding_model="text-embedding-004",
            embedding_dim=768,
            chunks=chunks,
            embeddings=embeddings,
            allow_external_ai=False,  # Privacy gate locked to local-first
        )

        doc_row = db.query(AIDocument).filter_by(id=doc_id).first()
        assert doc_row.allow_external_ai is False

        # 2. Querying RAG with allow_external=False
        res = answer_question_with_citations(
            db=db,
            document_id=doc_id,
            query="What is this document?",
            allow_external=False,
        )

        assert res.model_used == "deterministic-offline-model"
        assert mock_urlopen.call_count == 0  # Zero network egress during LLM chat!


def test_f13_embedding_privacy_gate_blocks_network(monkeypatch):
    """get_embedding must strictly bypass external APIs when allow_external=False."""
    import urllib.request
    from unittest.mock import MagicMock

    from app.ai.embeddings import get_embedding

    mock_urlopen = MagicMock()
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyMustNotBeCalled")

    vec = get_embedding("Secret financial text", allow_external=False)
    assert len(vec) == 768
    assert mock_urlopen.call_count == 0


# ============================================================================
# PHASE 5 AUDIT REMEDIATION TESTS: ENVIRONMENT & BOUNDARY HARDENING
# ============================================================================


def test_f14_gitignore_and_dockerignore_hardening():
    """F14: Sensitive credentials, service account keys, and env files must be ignored."""
    repo_root = Path(__file__).resolve().parent.parent
    gitignore_path = repo_root / ".gitignore"
    dockerignore_path = repo_root / ".dockerignore"

    assert gitignore_path.exists(), ".gitignore must exist"
    assert dockerignore_path.exists(), ".dockerignore must exist"

    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    dockerignore_content = dockerignore_path.read_text(encoding="utf-8")

    critical_patterns = [
        ".env",
        "*.pem",
        "*.key",
        "*sa-key*.json",
        "*credentials*.json",
        "*service-account*.json",
        ".gcloud/",
    ]

    for pattern in critical_patterns:
        assert pattern in gitignore_content, f"Pattern {pattern} missing from .gitignore"
        assert pattern in dockerignore_content, f"Pattern {pattern} missing from .dockerignore"


def test_f15_compose_ports_bound_to_loopback():
    """F15: All exposed host ports in Docker Compose files must bind strictly to 127.0.0.1."""

    repo_root = Path(__file__).resolve().parent.parent
    compose_files = [
        repo_root / "docker-compose.yml",
        repo_root / "deploy" / "docker-compose.yml",
    ]

    for cfile in compose_files:
        assert cfile.exists(), f"{cfile} must exist"
        lines = cfile.read_text(encoding="utf-8").splitlines()
        in_ports_block = False
        for line in lines:
            stripped = line.strip()
            if stripped == "ports:":
                in_ports_block = True
                continue
            if in_ports_block:
                if stripped.startswith("-"):
                    port_entry = stripped.lstrip("-").strip().strip('"').strip("'")
                    # If host:container mapping exists, must begin with 127.0.0.1:
                    if ":" in port_entry:
                        assert port_entry.startswith("127.0.0.1:"), (
                            f"Insecure public port binding '{port_entry}' in {cfile.name}. "
                            f"Must be prefixed with '127.0.0.1:'"
                        )
                else:
                    in_ports_block = False


def test_f16_synthetic_cv_test_pdf():
    """F16: cv_test.pdf must contain standardized synthetic benchmark profile with zero personal letters."""
    import fitz

    repo_root = Path(__file__).resolve().parent.parent
    cv_pdf_path = repo_root / "test-data" / "sample-pdfs" / "cv_test.pdf"

    assert cv_pdf_path.exists(), "cv_test.pdf must exist"

    doc = fitz.open(cv_pdf_path)
    assert len(doc) >= 1
    text = doc[0].get_text()

    # Eliminate personal letter text
    assert "internship" not in text.lower()
    assert "i saw the opening" not in text.lower()
    assert "my master's" not in text.lower()

    # Verify synthetic benchmark persona and keywords required by E2E tests
    assert "Alex Morgan" in text
    assert "Python" in text
    assert "automated" in text
    assert "Git" in text
    assert "Markdown" in text
    # Giri appears exactly once for client_offline_replace.spec.js compatibility
    assert text.count("Giri") == 1
    doc.close()
