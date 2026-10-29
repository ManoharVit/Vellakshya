"""
WebSocket Collaboration & Real-Time Presence Router.
Implements Guidebook Milestone 4: Multi-user presence, synchronized comments,
real-time annotation overlays, and offline action replay.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import config
from app.models.db import Document, get_db
from app.services import auth
from app.services.collaboration import (
    collaboration_manager,
    merge_concurrent_comments,
    sync_offline_actions,
)
from app.services.storage import storage_instance

router = APIRouter(tags=["Real-Time Collaboration & WebSockets"])

ALLOWED_WS_ORIGIN_PATTERNS = (
    "localhost",
    "127.0.0.1",
    "testserver",
    "vellakshya",
    "web.app",
    "run.app",
)


class OfflineSyncRequest(BaseModel):
    actions: list[dict[str, Any]] = Field(
        ..., description="Ordered list of mutations executed while offline"
    )
    baseVersion: int = Field(1, ge=1, description="Base version before disconnect")


class MergeCommentsRequest(BaseModel):
    commentsUserA: list[dict[str, Any]] = Field(..., description="Comments authored by client A")
    commentsUserB: list[dict[str, Any]] = Field(..., description="Comments authored by client B")
    baseVersion: int = Field(1, ge=1)


@router.websocket("/ws/documents/{doc_id}")
async def websocket_document_collaboration(
    websocket: WebSocket,
    doc_id: str,
    token: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
):
    """
    Real-time bi-directional WebSocket gateway for collaborative document viewing.
    Validates Origin header and authenticates participant session.
    """
    # 1. Validate Origin header
    origin = websocket.headers.get("origin")
    if origin:
        if not any(pat in origin.lower() for pat in ALLOWED_WS_ORIGIN_PATTERNS):
            await websocket.close(code=4003, reason="Forbidden Origin")
            return

    # 2. Authenticate session
    authenticated_actor = None
    if token:
        user_info = auth.get_current_user_from_token(token)
        if user_info:
            authenticated_actor = str(user_info.get("user_id") or user_info.get("email"))

    if not authenticated_actor and user_id:
        if config.is_prod:
            await websocket.close(code=4001, reason="Authentication token required in production")
            return
        authenticated_actor = user_id

    if not authenticated_actor and config.is_prod:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    assigned_user_id = authenticated_actor or user_id or f"user_{secrets.token_hex(4)}"
    assigned_name = name or f"Collaborator {assigned_user_id[-4:].upper()}"

    presence = await collaboration_manager.join_room(
        doc_id=doc_id,
        websocket=websocket,
        user_id=assigned_user_id,
        display_name=assigned_name,
        color=color,
    )

    try:
        while True:
            data = await websocket.receive_json()
            await collaboration_manager.handle_client_message(doc_id, websocket, data)
    except WebSocketDisconnect:
        await collaboration_manager.leave_room(doc_id, websocket)
    except Exception:
        await collaboration_manager.leave_room(doc_id, websocket)


@router.get("/api/v2/documents/{doc_id}/collaborators")
async def get_active_collaborators(doc_id: str):
    """
    Returns live list of active users currently viewing and collaborating on the document.
    """
    active_users = collaboration_manager.get_active_users(doc_id)
    return {
        "document_id": doc_id,
        "count": len(active_users),
        "collaborators": active_users,
    }


@router.post("/api/v2/documents/{doc_id}/sync-offline")
async def sync_offline_mutations(
    doc_id: str,
    sync_req: OfflineSyncRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    """
    Reconciles queued actions performed during temporary network disconnects or mobile sessions.
    """
    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Read active version
    active_ver = doc.versions[-1] if doc.versions else None
    if not active_ver:
        raise HTTPException(status_code=404, detail="Document has no active versions.")

    pdf_bytes = storage_instance.get_object(active_ver.object_key)
    out_bytes, summary = sync_offline_actions(
        pdf_bytes=pdf_bytes,
        offline_actions_queue=sync_req.actions,
        current_version=doc.current_version,
    )

    return {
        "status": "reconciled",
        "document_id": doc_id,
        "summary": summary,
        "actions_processed": len(sync_req.actions),
    }


@router.post("/api/v2/documents/{doc_id}/merge-comments")
async def merge_concurrent_user_comments(
    doc_id: str,
    merge_req: MergeCommentsRequest,
    db: Session = Depends(get_db),
):
    """
    Non-destructive merge of two diverging concurrent comment sets with deduplication.
    """
    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    active_ver = doc.versions[-1] if doc.versions else None
    if not active_ver:
        raise HTTPException(status_code=404, detail="Document has no active versions.")

    pdf_bytes = storage_instance.get_object(active_ver.object_key)
    out_bytes, summary = merge_concurrent_comments(
        pdf_bytes=pdf_bytes,
        comments_user_a=merge_req.commentsUserA,
        comments_user_b=merge_req.commentsUserB,
        base_version=merge_req.baseVersion,
    )

    return {
        "status": "merged",
        "document_id": doc_id,
        "summary": summary,
    }
