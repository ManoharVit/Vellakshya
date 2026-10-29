"""
FastAPI Router for Vellakshya AI Features.
Provides endpoints for document ingestion, hybrid RAG chat with server-side citations,
and local-first PII redaction workflows.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.ai.chunking import extract_chunks_from_pdf_bytes
from app.ai.embeddings import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL, get_embedding
from app.ai.models import (
    PIIApplyRequest,
    PIIEntityMatch,
    PIIScanResponse,
    RAGQueryRequest,
    RAGResponse,
)
from app.ai.observability import check_rate_limit
from app.ai.pii import apply_physical_redactions, scan_pdf_for_pii
from app.ai.rag import answer_question_with_citations
from app.ai.storage import (
    store_document_and_chunks,
)
from app.models.db import get_db

router = APIRouter(prefix="/api/ai", tags=["AI & Document Intelligence"])

# In-memory document buffer for demo and transient operations
_TRANSIENT_PDF_STORE: dict[str, bytes] = {}
_TRANSIENT_PII_MATCHES: dict[str, list[PIIEntityMatch]] = {}


@router.post("/ingest", summary="Ingest PDF for RAG Chat")
async def ingest_document_for_rag(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extracts text blocks with coordinate metadata, computes embeddings, and stores chunks."""
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    filename = file.filename or "document.pdf"

    # Extract spatial chunks
    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, document_id=doc_id)
    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text found in document.")

    # Compute embeddings
    embeddings = [get_embedding(c.content) for c in chunks]

    # Store in database
    store_document_and_chunks(
        db=db,
        document_id=doc_id,
        owner_id="demo_user",
        filename=filename,
        sha256=sha256,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dim=DEFAULT_EMBEDDING_DIM,
        chunks=chunks,
        embeddings=embeddings,
    )

    _TRANSIENT_PDF_STORE[doc_id] = pdf_bytes

    return {
        "status": "success",
        "document_id": doc_id,
        "filename": filename,
        "chunks_indexed": len(chunks),
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
    }


@router.post(
    "/chat", response_model=RAGResponse, summary="Query PDF with Hybrid RAG & Server Citations"
)
async def query_rag_endpoint(
    req: RAGQueryRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> RAGResponse:
    """Answers user queries with page-level citations grounded in the server database index."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    return answer_question_with_citations(
        db=db,
        document_id=req.document_id,
        query=req.query,
        top_k=req.top_k,
    )


@router.post("/pii/scan", response_model=PIIScanResponse, summary="Scan PDF for PII locally")
async def scan_pii_endpoint(
    file: UploadFile = File(...),
) -> PIIScanResponse:
    """Detects PII locally without sending text to any external cloud provider."""
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file.")

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    _TRANSIENT_PDF_STORE[doc_id] = pdf_bytes

    result = scan_pdf_for_pii(pdf_bytes, document_id=doc_id)
    _TRANSIENT_PII_MATCHES[doc_id] = result.entities
    return result


@router.post("/pii/apply", summary="Apply approved physical redactions and scrub document")
async def apply_pii_endpoint(
    req: PIIApplyRequest,
) -> Response:
    """Applies permanent redaction to approved boxes and returns scrubbed PDF bytes."""
    doc_id = req.document_id
    pdf_bytes = _TRANSIENT_PDF_STORE.get(doc_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Document session not found or expired.")

    all_matches = _TRANSIENT_PII_MATCHES.get(doc_id, [])
    approved_set = set(req.approved_entity_ids)
    approved_matches = [m for m in all_matches if m.id in approved_set]

    if not approved_matches:
        raise HTTPException(status_code=400, detail="No valid approved PII entity IDs provided.")

    redacted_bytes = apply_physical_redactions(pdf_bytes, approved_matches)

    return Response(
        content=redacted_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=redacted_{doc_id}.pdf"},
    )
