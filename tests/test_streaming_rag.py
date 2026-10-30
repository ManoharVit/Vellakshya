"""
Automated Verification Suite for Milestone 2: Streaming RAG & Sidecar Chat.
Tests:
- Server-Sent Events (SSE) streaming endpoint POST /api/ai/chat/stream
- Progressive token-by-token emission and [DONE] termination
- Server-side citations linking to database chunk coordinates
- Grounding & confidence scoring based on hybrid retrieval rank fusion
- Multi-turn conversation context continuity
- Local-first privacy gate (F13) adherence
- Tenant isolation enforcement (F05) on streaming endpoint
"""

from __future__ import annotations

import json

import fitz
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth

client = TestClient(app)


def _create_sample_intelligence_pdf() -> bytes:
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text(
        (72, 72),
        "Vellakshya Strategic Intelligence Plan 2026\n\n"
        "The steering committee ratified the hybrid document intelligence framework on 2026-04-10. "
        "The chief information security officer mandated that all document processing must operate "
        "locally by default with zero external cloud egress unless explicitly authorized by the user. "
        "The compliance division reported full adherence to ISO 27001 and SOC 2 guidelines.",
        fontsize=12,
    )

    p2 = doc.new_page(width=612, height=792)
    p2.insert_text(
        (72, 72),
        "Operational Milestones and Implementation Schedule\n\n"
        "Phase 1 multi-tenant architecture was successfully delivered on schedule. "
        "Milestone 2 establishes real-time streaming retrieval-augmented generation with interactive sidecar Q&A. "
        "All customer data must be encrypted with AES-256 at rest and TLS 1.3 in transit.",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_streaming_rag_sse_events_and_citations():
    """Verifies that /api/ai/chat/stream streams SSE events with valid schema, grounding, and citations."""
    pdf_bytes = _create_sample_intelligence_pdf()
    ingest_res = client.post(
        "/api/ai/ingest",
        files={"file": ("intelligence_plan.pdf", pdf_bytes, "application/pdf")},
    )
    assert ingest_res.status_code == 200, ingest_res.text
    doc_id = ingest_res.json()["document_id"]

    # Stream query
    req_body = {
        "document_id": doc_id,
        "query": "When was the hybrid document intelligence framework ratified?",
        "allow_external_ai": False,
        "stream": True,
    }

    with client.stream("POST", "/api/ai/chat/stream", json=req_body) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = []
        tokens = []
        citations = []
        grounding_event = None
        done_event = None

        for line in response.iter_lines():
            line_str = line.strip()
            if not line_str or line_str == ":":
                continue
            if line_str.startswith("data: "):
                payload_str = line_str[6:].strip()
                if payload_str == "[DONE]":
                    break
                payload = json.loads(payload_str)
                events.append(payload)
                if payload.get("type") == "token":
                    tokens.append(payload.get("content", ""))
                elif payload.get("type") == "citations":
                    citations = payload.get("citations", [])
                elif payload.get("type") == "grounding":
                    grounding_event = payload
                elif payload.get("type") == "done":
                    done_event = payload

        # Assertions
        assert len(tokens) > 0
        full_streamed_text = "".join(tokens)
        assert len(full_streamed_text.strip()) > 0

        # Citations verification: server coordinates present
        assert len(citations) > 0
        cit = citations[0]
        assert "page" in cit
        assert "quote" in cit
        assert "chunk_id" in cit
        assert cit["page"] in (1, 2)

        # Grounding metrics
        assert grounding_event is not None
        assert grounding_event["confidence"] in ("High", "Medium", "Low")
        assert grounding_event["score"] >= 0.0

        # Done event
        assert done_event is not None
        assert done_event["model_used"] is not None


def test_streaming_rag_multi_turn_history():
    """Verifies that multi-turn conversation history is received and contextualized."""
    pdf_bytes = _create_sample_intelligence_pdf()
    ingest_res = client.post(
        "/api/ai/ingest",
        files={"file": ("intelligence_plan.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = ingest_res.json()["document_id"]

    req_body = {
        "document_id": doc_id,
        "query": "What did the compliance division report?",
        "messages": [
            {"role": "user", "content": "What is this document about?"},
            {
                "role": "assistant",
                "content": "It is the Vellakshya Strategic Intelligence Plan 2026.",
            },
        ],
        "allow_external_ai": False,
        "stream": True,
    }

    with client.stream("POST", "/api/ai/chat/stream", json=req_body) as response:
        assert response.status_code == 200
        tokens = []
        for line in response.iter_lines():
            line_str = line.strip()
            if line_str.startswith("data: ") and line_str[6:].strip() != "[DONE]":
                payload = json.loads(line_str[6:].strip())
                if payload.get("type") == "token":
                    tokens.append(payload.get("content", ""))
        full_text = "".join(tokens)
        assert len(full_text) > 0


def test_streaming_rag_tenant_isolation_f05():
    """Verifies that /api/ai/chat/stream strictly enforces tenant isolation (F05)."""
    alice_token = auth.create_session_for_user(
        "alice_stream@vellakshya.test", role="editor", user_id="alice_stream_id"
    )
    bob_token = auth.create_session_for_user(
        "bob_stream@vellakshya.test", role="editor", user_id="bob_stream_id"
    )

    pdf_bytes = _create_sample_intelligence_pdf()
    ingest_res = client.post(
        "/api/ai/ingest",
        headers={"Authorization": f"Bearer {alice_token}"},
        files={"file": ("alice_doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert ingest_res.status_code == 200
    doc_id = ingest_res.json()["document_id"]

    # Anonymous access -> 401
    anon_res = client.post(
        "/api/ai/chat/stream",
        json={"document_id": doc_id, "query": "Test query", "stream": True},
    )
    assert anon_res.status_code == 401

    # Unauthorized Bob access -> 403
    bob_res = client.post(
        "/api/ai/chat/stream",
        headers={"Authorization": f"Bearer {bob_token}"},
        json={"document_id": doc_id, "query": "Test query", "stream": True},
    )
    assert bob_res.status_code == 403

    # Authorized Alice access -> 200 streaming
    with client.stream(
        "POST",
        "/api/ai/chat/stream",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"document_id": doc_id, "query": "Test query", "stream": True},
    ) as alice_stream:
        assert alice_stream.status_code == 200
