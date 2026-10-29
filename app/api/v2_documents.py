"""
Vellakshya Enterprise Document Workstation V2 REST API Router.
Implements the full Guidebook specification for immutable versioning,
optimistic concurrency control (baseVersion), signed manifests, and presigned object storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import config
from app.models.db import (
    Document,
    DocumentOperation,
    DocumentVersion,
    User,
    get_db,
    init_db,
)
from app.services import auth, editor, organizer
from app.services.document_service import (
    DocumentNotFoundError,
    DocumentService,
    PermissionDeniedError,
    VersionConflictError,
)
from app.services.storage import ObjectNotFoundError, storage_instance

# Initialize DB tables automatically
init_db()

router = APIRouter(prefix="/api/v2", tags=["Enterprise Document Workstation V2"])


# -------------------------------------------------------------
# Request & Response Schemas
# -------------------------------------------------------------


class DocumentOperationRequest(BaseModel):
    operation: str = Field(
        ..., description="Operation type (rotate, reorder, delete-pages, watermark, etc.)"
    )
    baseVersion: Optional[int] = Field(
        None, ge=1, description="Expected base version of active document"
    )
    base_version: Optional[int] = Field(None, ge=1)
    idempotencyKey: Optional[str] = Field(None, description="Unique client key for deduplication")
    idempotency_key: Optional[str] = None
    params: dict[str, Any] = Field(
        default_factory=dict, description="Parameters for transformation"
    )
    parameters: Optional[dict[str, Any]] = None

    @property
    def resolved_base_version(self) -> int:
        v = self.baseVersion if self.baseVersion is not None else self.base_version
        if v is None:
            raise ValueError("baseVersion or base_version is required")
        return v

    @property
    def resolved_idempotency_key(self) -> str:
        k = self.idempotencyKey or self.idempotency_key
        if not k:
            raise ValueError("idempotencyKey or idempotency_key is required")
        return k

    @property
    def resolved_params(self) -> dict[str, Any]:
        return self.parameters or self.params or {}


class ShareDocumentRequest(BaseModel):
    userId: Optional[str] = Field(None, description="Target user ID to grant permission")
    user_id: Optional[str] = None
    target_user_id: Optional[str] = None
    role: str = Field(..., description="Role: 'owner', 'editor', 'reviewer', 'viewer'")

    @property
    def resolved_user_id(self) -> str:
        uid = self.userId or self.user_id or self.target_user_id
        if not uid:
            raise ValueError("userId, user_id, or target_user_id is required")
        return uid


class CreateCommentRequest(BaseModel):
    body: Optional[str] = Field(None, min_length=1, description="Comment text content")
    content: Optional[str] = None
    versionNo: Optional[int] = Field(None, description="Target document version number")
    version_no: Optional[int] = None
    pageNo: Optional[int] = Field(None, description="Page number comment anchors to")
    page_number: Optional[int] = None
    anchor: Optional[Any] = Field(
        None, description="Bounding box geometry {x, y, w, h} or [x, y, w, h]"
    )
    bounding_box: Optional[Any] = None
    parentCommentId: Optional[str] = Field(None, description="Parent comment ID for threading")
    parent_comment_id: Optional[str] = None

    @property
    def resolved_body(self) -> str:
        text = self.body or self.content
        if not text:
            raise ValueError("body or content is required")
        return text

    @property
    def resolved_version_no(self) -> Optional[int]:
        return self.versionNo if self.versionNo is not None else self.version_no

    @property
    def resolved_page_no(self) -> Optional[int]:
        return self.pageNo if self.pageNo is not None else self.page_number

    @property
    def resolved_anchor(self) -> Optional[Any]:
        return self.anchor if self.anchor is not None else self.bounding_box

    @property
    def resolved_parent_comment_id(self) -> Optional[str]:
        return self.parentCommentId or self.parent_comment_id


def _get_current_actor(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> str:
    """
    Derives authenticated actor ID from verified Bearer token or authenticated session.
    Anonymous requests and unverified headers are strictly rejected with HTTP 401.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()

    # 1. Bearer token provided: verify cryptographically / via session store
    if token:
        user_info = auth.get_current_user_from_token(token)
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid or expired Bearer session token.")
        actor_id = str(user_info.get("user_id") or user_info.get("email"))
        # If client also passed X-User-Id, ensure it matches authenticated actor (anti-impersonation)
        if x_user_id and x_user_id != actor_id and user_info.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail=f"Impersonation rejected: Token identity {actor_id} does not match requested X-User-Id {x_user_id}.",
            )
        return actor_id

    # 2. X-User-Id provided without Bearer token
    if x_user_id:
        if config.is_prod:
            raise HTTPException(
                status_code=401,
                detail="Header-based authentication (X-User-Id) is forbidden in production; supply a Bearer session token.",
            )
        # Non-production test/development environment
        return x_user_id

    # 3. Anonymous / No identity provided: strictly reject
    raise HTTPException(
        status_code=401,
        detail="Authentication required: No identity token provided. Pass Authorization: Bearer <token>.",
    )


def _ensure_user_exists(db: Session, user_id: str):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        if config.is_prod:
            raise HTTPException(
                status_code=401, detail="User account not found in identity registry."
            )
        user = User(
            id=user_id,
            email=f"user_{user_id[:8]}@vellakshya.internal" if "@" not in user_id else user_id,
            display_name=f"Enterprise User {user_id[:6]}",
            hashed_password="mock_hash_for_testing",
            salt="mock_salt",
        )
        db.add(user)
        db.commit()


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------


@router.get("/documents")
async def list_documents(
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Lists documents owned by or accessible to the requesting user.
    """
    _ensure_user_exists(db, actor_id)
    docs = DocumentService.list_documents(db, actor_id)
    return {
        "count": len(docs),
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "current_version": doc.current_version,
                "owner_id": doc.owner_id,
                "status": doc.status,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in docs
        ],
    }


@router.post("/documents", status_code=201)
async def create_document_direct(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Creates a new managed document and initializes Version 1 with signed integrity manifest.
    """
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload Too Large: File exceeds 50MB limit.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

    _ensure_user_exists(db, actor_id)
    safe_filename = Path(file.filename or "Document.pdf").name
    clean_stem = Path(safe_filename).stem.replace("..", "").replace("/", "").replace("\\", "")
    doc_title = title or clean_stem or "Document"

    doc, ver = DocumentService.create_document(
        db=db,
        owner_id=actor_id,
        title=doc_title,
        initial_pdf_bytes=pdf_bytes,
    )

    return {
        "id": doc.id,
        "title": doc.title,
        "owner_id": doc.owner_id,
        "current_version": doc.current_version,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
        "document": {
            "id": doc.id,
            "title": doc.title,
            "owner_id": doc.owner_id,
            "current_version": doc.current_version,
            "status": doc.status,
            "created_at": doc.created_at.isoformat(),
        },
        "version": {
            "id": ver.id,
            "version_no": ver.version_no,
            "sha256": ver.sha256,
            "byte_size": ver.byte_size,
        },
        "version_1": {
            "id": ver.id,
            "version_no": ver.version_no,
            "sha256": ver.sha256,
            "byte_size": ver.byte_size,
        },
    }


@router.post("/documents/{doc_id}/upload-url")
async def get_upload_url(
    doc_id: str,
    filename: str = Query("document.pdf"),
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Obtains a bounded, time-limited presigned upload URL for binary ingestion.
    Requires editor or owner permission on the target document.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="editor")
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    safe_filename = Path(filename).name
    if not safe_filename or ".." in safe_filename:
        safe_filename = "document.pdf"
    target_key = f"documents/{doc_id}/uploads/{safe_filename}"
    presigned_url = storage_instance.generate_presigned_url(
        target_key, expires_in_seconds=300, method="PUT"
    )
    return {
        "document_id": doc_id,
        "object_key": target_key,
        "upload_url": presigned_url,
        "expires_in_seconds": 300,
    }


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Reads document metadata and authorization status.
    """
    _ensure_user_exists(db, actor_id)
    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        role = DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {
        "id": doc.id,
        "title": doc.title,
        "owner_id": doc.owner_id,
        "current_version": doc.current_version,
        "status": doc.status,
        "user_role": role,
        "role": role,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Deletes document metadata, versions, and purges all binary objects from storage.
    Strictly restricted to document 'owner'.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.delete_document(db, doc_id, actor_id)
        return {"status": "deleted", "document_id": doc_id}
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/{doc_id}/versions")
async def list_versions(
    doc_id: str,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Returns full immutable version history graph with parents, digests, and timestamps.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    versions = (
        db.query(DocumentVersion)
        .filter_by(document_id=doc_id)
        .order_by(DocumentVersion.version_no.asc())
        .all()
    )

    return {
        "document_id": doc_id,
        "count": len(versions),
        "versions": [
            {
                "id": v.id,
                "version_no": v.version_no,
                "parent_version_id": v.parent_version_id,
                "sha256": v.sha256,
                "byte_size": v.byte_size,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat(),
            }
            for v in versions
        ],
    }


@router.get("/documents/{doc_id}/versions/{version_no}")
async def get_version(
    doc_id: str,
    version_no: int,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Retrieves specific immutable version metadata and signed cryptographic manifest.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    ver = db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=version_no).first()
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found.")

    manifest = ver.integrity_manifest
    download_url = storage_instance.generate_presigned_url(
        ver.object_key, expires_in_seconds=300, method="GET"
    )
    return {
        "id": ver.id,
        "document_id": ver.document_id,
        "version_no": ver.version_no,
        "parent_version_id": ver.parent_version_id,
        "sha256": ver.sha256,
        "byte_size": ver.byte_size,
        "object_key": ver.object_key,
        "download_url": download_url,
        "created_at": ver.created_at.isoformat(),
        "integrity_manifest": manifest.manifest_json if manifest else None,
        "signature_key_id": manifest.key_id if manifest else None,
    }


@router.post("/documents/{doc_id}/operations")
async def execute_operation(
    doc_id: str,
    op_req: DocumentOperationRequest,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Executes a PDF transformation against a base version.
    Enforces optimistic concurrency checking: returns HTTP 409 Conflict if baseVersion is stale.
    """
    _ensure_user_exists(db, actor_id)
    try:
        doc = db.query(Document).filter_by(id=doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")

        # Check permissions: Requires 'editor' or higher
        DocumentService.check_permission(db, doc_id, actor_id, required_role="editor")

        base_ver_no = op_req.resolved_base_version
        idemp_key = op_req.resolved_idempotency_key
        p = op_req.resolved_params
        op_type = op_req.operation

        # Check idempotency first before fetching base version or computing
        existing_op = (
            db.query(DocumentOperation)
            .filter_by(document_id=doc_id, idempotency_key=idemp_key)
            .first()
        )
        if existing_op and existing_op.output_version_id:
            existing_ver = (
                db.query(DocumentVersion).filter_by(id=existing_op.output_version_id).first()
            )
            if existing_ver:
                return {
                    "status": "succeeded",
                    "is_idempotent_replay": True,
                    "replayed": True,
                    "document_id": doc_id,
                    "version_no": existing_ver.version_no,
                    "base_version": base_ver_no,
                    "operation_type": op_type,
                    "sha256": existing_ver.sha256,
                    "byte_size": existing_ver.byte_size,
                    "created_at": existing_ver.created_at.isoformat(),
                }

        # Concurrency verification: Base version must match active version
        if base_ver_no != doc.current_version:
            raise VersionConflictError(
                f"Version conflict: Operation specified baseVersion={base_ver_no}, "
                f"but active document is at current_version={doc.current_version}."
            )

        # Read base version binary from storage
        base_ver = (
            db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=base_ver_no).first()
        )
        if not base_ver:
            raise HTTPException(status_code=404, detail=f"Base version {base_ver_no} not found.")

        input_pdf_bytes = storage_instance.get_object(base_ver.object_key)

        def resolve_page_list(val: Any) -> list[int]:
            if val is None or val == "all":
                return []
            if isinstance(val, int):
                return [val]
            if isinstance(val, (list, tuple)):
                return [int(x) for x in val]
            if isinstance(val, str):
                return organizer.parse_page_spec(val)
            return []

        # Execute transformation using Vellakshya PDF engine
        if op_type in ("rotate", "rotate_page"):
            angle = int(p.get("angle", p.get("rotation", 90)))
            page_val = p.get("page_number", p.get("page", p.get("pages", None)))
            pages_list = resolve_page_list(page_val) or None
            transformed_bytes = organizer.rotate_pages(
                input_pdf_bytes, pages=pages_list, angle=angle
            )

        elif op_type in ("watermark", "add_watermark"):
            text = str(p.get("text", "CONFIDENTIAL"))
            opacity = float(p.get("opacity", 0.3))
            transformed_bytes = editor.add_watermark(input_pdf_bytes, text=text, opacity=opacity)

        elif op_type in ("reorder", "reorder_pages"):
            order = p.get("order", p.get("new_order"))
            if isinstance(order, (list, tuple)):
                order_list = [int(x) for x in order]
            else:
                order_list = resolve_page_list(order)
            transformed_bytes = organizer.reorder_pages(input_pdf_bytes, new_order=order_list)

        elif op_type in ("delete-pages", "delete_pages", "delete_page"):
            page_val = p.get("pages", p.get("page_number", p.get("page", None)))
            pages_list = resolve_page_list(page_val)
            transformed_bytes = organizer.delete_pages(input_pdf_bytes, pages_to_delete=pages_list)

        elif op_type in ("crop", "crop_margins", "crop_pages"):
            top = float(p.get("top", 0))
            right = float(p.get("right", 0))
            bottom = float(p.get("bottom", 0))
            left = float(p.get("left", 0))
            page_val = p.get("pages", p.get("page_number", p.get("page", None)))
            pages_list = resolve_page_list(page_val) or None
            transformed_bytes = organizer.crop_pages(
                input_pdf_bytes, pages=pages_list, top=top, right=right, bottom=bottom, left=left
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operation type: {op_type}")

        # Commit new version to database and object storage
        new_version, is_replay = DocumentService.apply_operation(
            db=db,
            doc_id=doc_id,
            actor_id=actor_id,
            operation_type=op_type,
            base_version=base_ver_no,
            idempotency_key=idemp_key,
            parameters=p,
            transformed_pdf_bytes=transformed_bytes,
        )

        return {
            "status": "succeeded",
            "is_idempotent_replay": is_replay,
            "replayed": is_replay,
            "document_id": doc_id,
            "version_no": new_version.version_no,
            "base_version": base_ver_no,
            "operation_type": op_type,
            "sha256": new_version.sha256,
            "byte_size": new_version.byte_size,
            "created_at": new_version.created_at.isoformat(),
        }

    except VersionConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/{doc_id}/integrity")
async def verify_integrity(
    doc_id: str,
    version: Optional[int] = Query(None, description="Version number to verify (default: current)"),
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Cryptographic verification endpoint:
    Recomputes SHA-256 over exact stored bytes and checks the signed Ed25519 manifest.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        result = DocumentService.verify_document_integrity(db=db, doc_id=doc_id, version_no=version)
        return result
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/documents/{doc_id}/share")
async def share_document(
    doc_id: str,
    share_req: ShareDocumentRequest,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Grants or modifies collaborator role (owner, editor, reviewer, viewer).
    """
    _ensure_user_exists(db, actor_id)
    target_uid = share_req.resolved_user_id
    _ensure_user_exists(db, target_uid)
    try:
        perm = DocumentService.share_document(
            db=db,
            doc_id=doc_id,
            granter_id=actor_id,
            target_user_id=target_uid,
            role=share_req.role,
        )
        return {
            "document_id": doc_id,
            "user_id": perm.user_id,
            "role": perm.role,
            "updated_at": perm.created_at.isoformat(),
        }
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{doc_id}/comments")
async def list_comments(
    doc_id: str,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Reads all threaded comments and discussion points for a document.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "document_id": doc_id,
        "count": len(doc.comments),
        "comments": [
            {
                "id": c.id,
                "author_id": c.author_id,
                "version_id": c.version_id,
                "parent_comment_id": c.parent_comment_id,
                "page_no": c.page_no,
                "page_number": c.page_no,
                "anchor": c.anchor,
                "bounding_box": c.anchor,
                "body": c.body,
                "content": c.body,
                "created_at": c.created_at.isoformat(),
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
            }
            for c in doc.comments
        ],
    }


@router.post("/documents/{doc_id}/comments", status_code=201)
async def create_comment(
    doc_id: str,
    comment_req: CreateCommentRequest,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Creates a new threaded comment anchored to a page or bounding box.
    """
    _ensure_user_exists(db, actor_id)
    try:
        comment = DocumentService.add_comment(
            db=db,
            doc_id=doc_id,
            author_id=actor_id,
            body=comment_req.resolved_body,
            version_no=comment_req.resolved_version_no,
            page_no=comment_req.resolved_page_no,
            anchor=comment_req.resolved_anchor,
            parent_comment_id=comment_req.resolved_parent_comment_id,
        )
        return {
            "id": comment.id,
            "document_id": doc_id,
            "author_id": comment.author_id,
            "body": comment.body,
            "content": comment.body,
            "page_no": comment.page_no,
            "page_number": comment.page_no,
            "anchor": comment.anchor,
            "bounding_box": comment.anchor,
            "parent_comment_id": comment.parent_comment_id,
            "created_at": comment.created_at.isoformat(),
        }
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/documents/{doc_id}/export")
async def generate_export_download(
    doc_id: str,
    version: Optional[int] = Query(None, description="Version number to export (default: current)"),
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Generates an authorized time-limited presigned download URL for the document.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    target_vno = version if version is not None else doc.current_version
    ver = db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=target_vno).first()
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {target_vno} not found.")

    presigned_url = storage_instance.generate_presigned_url(
        ver.object_key, expires_in_seconds=300, method="GET"
    )
    return {
        "document_id": doc_id,
        "version_no": target_vno,
        "sha256": ver.sha256,
        "download_url": presigned_url,
        "expires_in_seconds": 300,
    }


@router.get("/documents/{doc_id}/audit")
async def get_audit_trail(
    doc_id: str,
    actor_id: str = Depends(_get_current_actor),
    db: Session = Depends(get_db),
):
    """
    Returns the complete, append-only hash-chained audit trail for the document.
    """
    _ensure_user_exists(db, actor_id)
    try:
        DocumentService.check_permission(db, doc_id, actor_id, required_role="viewer")
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    trail = DocumentService.get_audit_trail(db, doc_id)
    return {
        "document_id": doc_id,
        "count": len(trail),
        "events": trail,
    }


@router.get("/storage/presigned")
async def access_presigned_storage(token: str = Query(..., description="Presigned HMAC token")):
    """
    Validates token signature and serves binary object.
    """
    try:
        key, method = storage_instance.validate_presigned_token(token)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if method != "GET":
        raise HTTPException(
            status_code=405, detail=f"Method {method} not supported on download route."
        )

    try:
        data = storage_instance.get_object(key)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="Stored object not found.")

    filename = Path(key).name
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
