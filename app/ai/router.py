"""
FastAPI Router for Vellakshya AI Features.
Provides endpoints for document ingestion, hybrid RAG chat with server-side citations,
and local-first PII redaction workflows.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.ai.chunking import extract_chunks_from_pdf_bytes
from app.ai.embeddings import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL, get_embedding
from app.ai.models import (
    PIIApplyRequest,
    PIIScanResponse,
    RAGQueryRequest,
    RAGResponse,
)
from app.ai.observability import check_rate_limit
from app.ai.pii import apply_physical_redactions, scan_pdf_for_pii
from app.ai.rag import answer_question_with_citations
from app.ai.storage import (
    AIDocument,
    delete_ai_document,
    store_document_and_chunks,
)
from app.core.config import config
from app.models.db import get_db
from app.services import auth

router = APIRouter(prefix="/api/ai", tags=["AI & Document Intelligence"])

# In-memory document buffer with retention TTL (F12)
TRANSIENT_AI_TTL_SECONDS = 3600  # 1 hour retention TTL
_TRANSIENT_PDF_STORE: dict[str, dict[str, Any]] = {}
_TRANSIENT_PII_MATCHES: dict[str, dict[str, Any]] = {}


def purge_transient_document_cache(doc_id: str) -> None:
    """Purges matching document from transient in-memory buffers (F12)."""
    _TRANSIENT_PDF_STORE.pop(doc_id, None)
    _TRANSIENT_PII_MATCHES.pop(doc_id, None)


def purge_expired_transient_ai_data(max_age_seconds: int = TRANSIENT_AI_TTL_SECONDS) -> int:
    """Purges entries older than retention TTL (F12)."""
    import time

    now = time.time()
    purged = 0
    for k in list(_TRANSIENT_PDF_STORE.keys()):
        item = _TRANSIENT_PDF_STORE.get(k)
        if item and (now - float(item.get("created_at", 0))) > max_age_seconds:
            _TRANSIENT_PDF_STORE.pop(k, None)
            purged += 1
    for k in list(_TRANSIENT_PII_MATCHES.keys()):
        item = _TRANSIENT_PII_MATCHES.get(k)
        if item and (now - float(item.get("created_at", 0))) > max_age_seconds:
            _TRANSIENT_PII_MATCHES.pop(k, None)
    return purged


def _resolve_ai_actor(
    authorization: Optional[str] = None,
    x_user_id: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[str]:
    active_token = token
    if not active_token and authorization and authorization.startswith("Bearer "):
        active_token = authorization.split(" ", 1)[1].strip()
    if active_token:
        user_info = auth.get_current_user_from_token(active_token)
        if user_info:
            return str(user_info.get("user_id") or user_info.get("email"))
    if x_user_id:
        return x_user_id
    return None


@router.post("/ingest", summary="Ingest PDF for RAG Chat")
async def ingest_document_for_rag(
    file: UploadFile = File(...),
    allow_external_ai: bool = Query(
        False, description="Local-first privacy gate. When False, embeddings stay in-process (F13)."
    ),
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extracts text blocks with coordinate metadata, computes embeddings, and stores chunks with tenant ownership."""
    import time

    actor = _resolve_ai_actor(authorization, x_user_id, token)
    if config.is_prod and not actor:
        raise HTTPException(
            status_code=401, detail="Authentication required to ingest document into AI repository."
        )
    owner_id = actor or "demo_user"

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

    # Compute embeddings respecting allow_external_ai privacy gate (F13)
    embeddings = [get_embedding(c.content, allow_external=allow_external_ai) for c in chunks]

    # Store in database
    store_document_and_chunks(
        db=db,
        document_id=doc_id,
        owner_id=owner_id,
        filename=filename,
        sha256=sha256,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dim=DEFAULT_EMBEDDING_DIM,
        chunks=chunks,
        embeddings=embeddings,
        allow_external_ai=allow_external_ai,
    )

    purge_expired_transient_ai_data()
    _TRANSIENT_PDF_STORE[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    return {
        "status": "success",
        "document_id": doc_id,
        "filename": filename,
        "owner_id": owner_id,
        "chunks_indexed": len(chunks),
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "allow_external_ai": allow_external_ai,
    }


@router.post(
    "/chat", response_model=RAGResponse, summary="Query PDF with Hybrid RAG & Server Citations"
)
async def query_rag_endpoint(
    req: RAGQueryRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> RAGResponse:
    """Answers user queries with page-level citations grounded in the server database index."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    ai_doc = db.query(AIDocument).filter_by(id=req.document_id).first()
    if not ai_doc:
        raise HTTPException(status_code=404, detail="Document not found in AI index.")

    # Enforce tenant isolation when document is bound to an authenticated owner
    if ai_doc.owner_id != "demo_user":
        actor = _resolve_ai_actor(authorization, x_user_id, token)
        if not actor:
            raise HTTPException(
                status_code=401, detail="Authentication required to query this document."
            )
        if actor != ai_doc.owner_id and actor != "admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied: You do not own this document in the AI index.",
            )

    effective_allow_external = bool(ai_doc.allow_external_ai and req.allow_external_ai)
    return answer_question_with_citations(
        db=db,
        document_id=req.document_id,
        query=req.query,
        top_k=req.top_k,
        allow_external=effective_allow_external,
    )


@router.delete("/documents/{document_id}", summary="Delete document from AI index")
async def delete_ai_document_endpoint(
    document_id: str,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cascades deletion of document and its spatial chunks from AI index and transient caches (F12)."""
    ai_doc = db.query(AIDocument).filter_by(id=document_id).first()
    if not ai_doc:
        raise HTTPException(status_code=404, detail="Document not found in AI index.")

    if ai_doc.owner_id != "demo_user":
        actor = _resolve_ai_actor(authorization, x_user_id, token)
        if not actor:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to delete this document from AI index.",
            )
        if actor != ai_doc.owner_id and actor != "admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied: You do not own this document in the AI index.",
            )

    delete_ai_document(db, document_id)
    return {"status": "deleted", "document_id": document_id}


@router.post("/pii/scan", response_model=PIIScanResponse, summary="Scan PDF for PII locally")
async def scan_pii_endpoint(
    file: UploadFile = File(...),
) -> PIIScanResponse:
    """Detects PII locally without sending text to any external cloud provider."""
    import time

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file.")

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    purge_expired_transient_ai_data()
    _TRANSIENT_PDF_STORE[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    result = scan_pdf_for_pii(pdf_bytes, document_id=doc_id)
    _TRANSIENT_PII_MATCHES[doc_id] = {"entities": result.entities, "created_at": time.time()}
    return result


@router.post("/pii/apply", summary="Apply approved physical redactions and scrub document")
async def apply_pii_endpoint(
    req: PIIApplyRequest,
) -> Response:
    """Applies permanent redaction to approved boxes and returns scrubbed PDF bytes."""
    doc_id = req.document_id
    item = _TRANSIENT_PDF_STORE.get(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document session not found or expired.")
    pdf_bytes = item["bytes"]

    pii_item = _TRANSIENT_PII_MATCHES.get(doc_id)
    all_matches = pii_item["entities"] if pii_item else []
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
