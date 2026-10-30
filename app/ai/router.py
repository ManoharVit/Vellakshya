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
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.analytics import analyze_pdf_document, compute_document_analytics
from app.ai.chunking import extract_chunks_from_pdf_bytes
from app.ai.embeddings import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL, get_embedding
from app.ai.models import (
    AnalyticsRequest,
    AnalyticsResponse,
    MultiFormatIngestResponse,
    PIIApplyRequest,
    PIIScanResponse,
    RAGQueryRequest,
    SummarizeRequest,
    SummarizeResponse,
    TranslationRequest,
    TranslationResponse,
)
from app.ai.observability import check_rate_limit
from app.ai.pii import apply_physical_redactions, scan_pdf_for_pii
from app.ai.rag import answer_question_with_citations, stream_answer_with_citations
from app.ai.storage import (
    AIChunk,
    AIDocument,
    delete_ai_document,
    store_document_and_chunks,
)
from app.ai.summarizer import (
    summarize_pdf_document,
    summarize_text_extractive,
)
from app.ai.translation import (
    DOMAIN_GLOSSARIES,
    SUPPORTED_LANGUAGES,
    execute_document_translation,
)
from app.models.db import get_db
from app.services import auth
from app.services.multi_format import process_multi_format_document

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


@router.post("/chat", summary="Query PDF with Hybrid RAG & Server Citations")
async def query_rag_endpoint(
    req: RAGQueryRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Any:
    """Answers user queries with page-level citations grounded in the server database index."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    ai_doc = db.query(AIDocument).filter_by(id=req.document_id).first()
    if not ai_doc:
        raise HTTPException(status_code=404, detail="Document not found in AI index.")

    # Enforce tenant isolation when document is bound to an authenticated owner (F05)
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

    if req.stream:
        return StreamingResponse(
            stream_answer_with_citations(
                db=db,
                document_id=req.document_id,
                query=req.query,
                top_k=req.top_k,
                history=req.messages,
                owner_id=str(ai_doc.owner_id),
                allow_external=effective_allow_external,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return answer_question_with_citations(
        db=db,
        document_id=req.document_id,
        query=req.query,
        top_k=req.top_k,
        history=req.messages,
        owner_id=str(ai_doc.owner_id),
        allow_external=effective_allow_external,
    )


@router.post("/chat/stream", summary="Streaming Hybrid RAG with Real-Time SSE and Page Citations")
async def query_rag_stream_endpoint(
    req: RAGQueryRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Streams token-by-token answer with confidence scores and database citation sources via SSE."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    ai_doc = db.query(AIDocument).filter_by(id=req.document_id).first()
    if not ai_doc:
        raise HTTPException(status_code=404, detail="Document not found in AI index.")

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
    return StreamingResponse(
        stream_answer_with_citations(
            db=db,
            document_id=req.document_id,
            query=req.query,
            top_k=req.top_k,
            history=req.messages,
            owner_id=str(ai_doc.owner_id),
            allow_external=effective_allow_external,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


# ---------------------------------------------------------------------------
# Milestone 1: Document Analytics Endpoints
# ---------------------------------------------------------------------------


@router.post("/analytics", response_model=AnalyticsResponse, summary="Compute Document Analytics")
async def compute_analytics_endpoint(
    req: AnalyticsRequest,
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    """Computes lexical density, readability scores, and n-gram frequencies for text or document."""
    if req.selected_text and req.selected_text.strip():
        data = compute_document_analytics(
            req.selected_text.strip(), page_count=1, filtered_page_count=1
        )
        return AnalyticsResponse(**data)

    if req.document_id:
        item = _TRANSIENT_PDF_STORE.get(req.document_id)
        if item and "bytes" in item:
            data = analyze_pdf_document(
                pdf_bytes=item["bytes"],
                page_range=req.page_range,
                selected_text=req.selected_text,
            )
            return AnalyticsResponse(**data)

        # Fallback to database indexed chunks
        chunks = db.query(AIChunk).filter_by(document_id=req.document_id).all()
        if chunks:
            full_text = "\n\n".join(str(c.content) for c in chunks)
            pages = set(c.page for c in chunks)
            data = compute_document_analytics(
                full_text, page_count=len(pages), filtered_page_count=len(pages)
            )
            return AnalyticsResponse(**data)
        raise HTTPException(status_code=404, detail="Document not found or session expired.")

    raise HTTPException(
        status_code=400, detail="Either document_id or selected_text must be provided."
    )


@router.post(
    "/analytics/file", response_model=AnalyticsResponse, summary="Upload PDF and Compute Analytics"
)
async def compute_analytics_file_endpoint(
    file: UploadFile = File(...),
    page_range: Optional[str] = Form(None),
    selected_text: Optional[str] = Form(None),
) -> AnalyticsResponse:
    """Uploads a PDF file directly and computes comprehensive statistical metrics."""
    import time

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file.")

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    purge_expired_transient_ai_data()
    _TRANSIENT_PDF_STORE[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    data = analyze_pdf_document(
        pdf_bytes=pdf_bytes,
        page_range=page_range,
        selected_text=selected_text,
    )
    return AnalyticsResponse(**data)


# ---------------------------------------------------------------------------
# Milestone 1: Smart Summarization Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Smart Multi-Tier Document Summarization",
)
async def summarize_document_endpoint(
    req: SummarizeRequest,
    db: Session = Depends(get_db),
) -> SummarizeResponse:
    """Summarizes document with selectable depth, tone, format, and structured insight extraction."""
    import time

    if req.selected_text and req.selected_text.strip():
        return summarize_pdf_document(
            pdf_bytes=b"",
            selected_text=req.selected_text,
            level=req.level,
            length=req.length,
            tone=req.tone,
            output_format=req.output_format,
            allow_external_ai=req.allow_external_ai,
        )

    if req.document_id:
        item = _TRANSIENT_PDF_STORE.get(req.document_id)
        if item and "bytes" in item:
            return summarize_pdf_document(
                pdf_bytes=item["bytes"],
                page_range=req.page_range,
                selected_text=req.selected_text,
                level=req.level,
                length=req.length,
                tone=req.tone,
                output_format=req.output_format,
                allow_external_ai=req.allow_external_ai,
            )

        chunks = db.query(AIChunk).filter_by(document_id=req.document_id).all()
        if chunks:
            full_text = "\n\n".join(str(c.content) for c in chunks)
            pages = sorted([int(c.page) for c in chunks if c.page is not None])
            unique_pages = sorted(list(set(pages)))
            pages_text = [
                (f"Page {p}", "\n".join(str(c.content) for c in chunks if c.page == p))
                for p in unique_pages
            ]
            t_start = time.perf_counter()
            summary_text, insights = summarize_text_extractive(
                text=full_text,
                level=req.level,
                length=req.length,
                tone=req.tone,
                output_format=req.output_format,
                pages_text=pages_text,
            )
            return SummarizeResponse(
                summary=summary_text,
                level=req.level,
                length=req.length,
                tone=req.tone,
                output_format=req.output_format,
                insights=insights,
                model_used="offline-extractive-v1",
                page_count=len(pages),
                filtered_page_count=len(pages),
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )
        raise HTTPException(status_code=404, detail="Document not found or session expired.")

    raise HTTPException(
        status_code=400, detail="Either document_id or selected_text must be provided."
    )


@router.post(
    "/summarize/file", response_model=SummarizeResponse, summary="Upload PDF and Summarize"
)
async def summarize_file_endpoint(
    file: UploadFile = File(...),
    page_range: Optional[str] = Form(None),
    selected_text: Optional[str] = Form(None),
    level: str = Form("executive_summary"),
    length: str = Form("medium"),
    tone: str = Form("neutral"),
    output_format: str = Form("paragraph"),
    allow_external_ai: bool = Form(False),
) -> SummarizeResponse:
    """Uploads a PDF directly and generates a multi-tier summary with structured insights."""
    import time

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file.")

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    purge_expired_transient_ai_data()
    _TRANSIENT_PDF_STORE[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    return summarize_pdf_document(
        pdf_bytes=pdf_bytes,
        page_range=page_range,
        selected_text=selected_text,
        level=level,
        length=length,
        tone=tone,
        output_format=output_format,
        allow_external_ai=allow_external_ai,
    )


# ---------------------------------------------------------------------------
# Milestone 3: Multi-Format Ingestion & Translation Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/ingest-multi-format",
    response_model=MultiFormatIngestResponse,
    summary="Ingest DOCX, XLSX, CSV, Markdown, or PDF",
)
async def ingest_multi_format_endpoint(
    file: UploadFile = File(...),
    allow_external_ai: bool = Query(
        False, description="Local-first privacy gate (F13). When False, zero network egress."
    ),
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> MultiFormatIngestResponse:
    """Ingests multi-format documents, converts them to high-fidelity PDF, and indexes chunks."""
    actor = _resolve_ai_actor(authorization, x_user_id, token)
    owner_id = actor or "demo_user"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = file.filename or "uploaded_document"
    return process_multi_format_document(
        file_bytes=file_bytes,
        filename=filename,
        owner_id=owner_id,
        db=db,
        allow_external_ai=allow_external_ai,
    )


@router.get(
    "/documents/{document_id}/download", summary="Download viewable PDF for ingested document"
)
async def download_ingested_pdf_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Returns the synthesized or ingested viewable PDF bytes."""
    purge_expired_transient_ai_data()
    item = _TRANSIENT_PDF_STORE.get(document_id)
    if not item or not item.get("bytes"):
        raise HTTPException(status_code=404, detail="Document PDF stream not found or expired.")

    return Response(
        content=item["bytes"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={document_id}.pdf",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.post("/translate", response_model=TranslationResponse, summary="Translate Document or Text")
async def translate_text_endpoint(
    req: TranslationRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> TranslationResponse:
    """Bilingual layout-preserving translation with domain glossaries and privacy gates."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    # Enforce tenant isolation if document_id is provided
    if req.document_id:
        ai_doc = db.query(AIDocument).filter_by(id=req.document_id).first()
        if ai_doc and ai_doc.owner_id != "demo_user":
            actor = _resolve_ai_actor(authorization, x_user_id, token)
            if not actor:
                raise HTTPException(
                    status_code=401, detail="Authentication required to translate this document."
                )
            if actor != ai_doc.owner_id and actor != "admin":
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: You do not own this document in the AI index.",
                )

    return execute_document_translation(req)


@router.post(
    "/translate/file", response_model=TranslationResponse, summary="Upload PDF/Doc and Translate"
)
async def translate_file_endpoint(
    file: UploadFile = File(...),
    target_language: str = Form("es"),
    source_language: str = Form("auto"),
    domain: str = Form("general"),
    allow_external_ai: bool = Form(False),
    scope: str = Form("full_document"),
) -> TranslationResponse:
    """Uploads file directly and runs bilingual layout-preserving translation."""
    import time

    import fitz

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty uploaded file.")

    sha256 = hashlib.sha256(file_bytes).hexdigest()
    doc_id = f"doc_{sha256[:16]}"
    purge_expired_transient_ai_data()

    # Extract text from PDF or text bytes
    extracted_text = ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        _TRANSIENT_PDF_STORE[doc_id] = {"bytes": file_bytes, "created_at": time.time()}
        extracted_text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception:
        # Fallback to UTF-8 decoding
        extracted_text = file_bytes.decode("utf-8", errors="replace")

    req = TranslationRequest(
        document_id=doc_id,
        selected_text=extracted_text,
        source_language=source_language,
        target_language=target_language,
        domain=domain,
        scope=scope,
        allow_external_ai=allow_external_ai,
    )
    return execute_document_translation(req)


@router.get("/translate/glossaries", summary="List Available Translation Glossaries and Languages")
async def list_translation_glossaries_endpoint() -> dict[str, Any]:
    """Returns list of supported domain glossaries and language codes."""
    return {
        "status": "success",
        "supported_languages": SUPPORTED_LANGUAGES,
        "domains": list(DOMAIN_GLOSSARIES.keys()),
        "glossaries": {dom: list(terms.keys()) for dom, terms in DOMAIN_GLOSSARIES.items()},
    }
