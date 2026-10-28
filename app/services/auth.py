"""
Authentication, Role-Based Access Control (RBAC), and Session Lifecycle Service.
Implements:
- User registration, login, logout, and token validation.
- Role permissions (Admin, Editor, Viewer).
- Document lifecycle (storage, retrieval, deletion, 404 enforcement).
- Session draft preservation against sudden expiry.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Optional

# In-memory stores (in production backed by Redis / Postgres)
_USERS_DB: dict[str, dict[str, Any]] = {}
_SESSIONS_DB: dict[str, dict[str, Any]] = {}
_DOCUMENTS_DB: dict[str, dict[str, Any]] = {}
_DRAFTS_DB: dict[str, dict[str, Any]] = {}

SESSION_TTL_SECONDS = 3600


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return hashed, salt


def register_user(email: str, password: str, role: str = "editor") -> dict[str, Any]:
    """
    Registers a new user with hashed password and role.
    """
    email_clean = email.lower().strip()
    if email_clean in _USERS_DB:
        raise ValueError("User with this email already exists.")

    hashed_pw, salt = _hash_password(password)
    user_record = {
        "email": email_clean,
        "password_hash": hashed_pw,
        "salt": salt,
        "role": role,
        "created_at": time.time(),
    }
    _USERS_DB[email_clean] = user_record
    return {"email": email_clean, "role": role}


def login_user(email: str, password: str) -> dict[str, Any]:
    """
    Authenticates user and returns an active session token.
    """
    email_clean = email.lower().strip()
    user = _USERS_DB.get(email_clean)
    if not user:
        raise ValueError("Invalid email or password.")

    hashed_input, _ = _hash_password(password, user["salt"])
    if hashed_input != user["password_hash"]:
        raise ValueError("Invalid email or password.")

    token = secrets.token_urlsafe(32)
    session_data = {
        "token": token,
        "email": email_clean,
        "role": user["role"],
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    _SESSIONS_DB[token] = session_data
    return {
        "token": token,
        "email": email_clean,
        "role": user["role"],
        "expires_in": SESSION_TTL_SECONDS,
    }


def logout_user(token: str) -> bool:
    """
    Terminates the active session.
    """
    if token in _SESSIONS_DB:
        del _SESSIONS_DB[token]
        return True
    return False


def get_current_user_from_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    """
    Retrieves authenticated user details or returns None if invalid/expired.
    """
    if not token or token not in _SESSIONS_DB:
        return None

    session = _SESSIONS_DB[token]
    if time.time() > session["expires_at"]:
        del _SESSIONS_DB[token]
        return None

    return {
        "email": session["email"],
        "role": session["role"],
    }


def verify_role_permission(role: str, action: str) -> bool:
    """
    Enforces Role-Based Access Control (RBAC):
    - Admin: All actions permitted.
    - Editor: View, upload, edit, annotate, convert, sign.
    - Viewer: View and render only (cannot edit, annotate, or download restricted content).
    """
    if role == "admin":
        return True
    if role == "editor":
        return action in ("view", "upload", "edit", "annotate", "convert", "sign", "download")
    if role == "viewer":
        return action in ("view", "render")
    return False


def store_document(doc_id: str, content: bytes, owner: str) -> dict[str, Any]:
    """
    Stores document in managed storage with versioning.
    """
    doc_record = {
        "doc_id": doc_id,
        "content": content,
        "owner": owner,
        "size_bytes": len(content),
        "created_at": time.time(),
        "is_deleted": False,
        "version": 1,
    }
    _DOCUMENTS_DB[doc_id] = doc_record
    return {"doc_id": doc_id, "size_bytes": len(content), "owner": owner, "version": 1}


def get_document_record(doc_id: str) -> Optional[dict[str, Any]]:
    """
    Retrieves document metadata record if not deleted.
    """
    doc_record = _DOCUMENTS_DB.get(doc_id)
    if not doc_record or doc_record.get("is_deleted"):
        return None
    return doc_record


def get_document(doc_id: str) -> Optional[bytes]:
    """
    Retrieves document content if not deleted.
    """
    doc_record = get_document_record(doc_id)
    if not doc_record:
        return None
    return doc_record["content"]


def update_document_content(
    doc_id: str,
    new_content: bytes,
    expected_version: int,
) -> dict[str, Any]:
    """
    Updates document content ensuring optimistic concurrency control (OCC).
    Rejects concurrent silent overwrites if expected_version != current version.
    """
    doc_record = get_document_record(doc_id)
    if not doc_record:
        raise KeyError("Document not found or has been deleted.")

    current_version = doc_record.get("version", 1)
    if expected_version != current_version:
        raise ValueError(
            f"Concurrent edit conflict detected. Base version {expected_version} does not match current version {current_version}."
        )

    doc_record["version"] = current_version + 1
    doc_record["content"] = new_content
    doc_record["size_bytes"] = len(new_content)
    doc_record["updated_at"] = time.time()
    return {
        "doc_id": doc_id,
        "new_version": doc_record["version"],
        "size_bytes": len(new_content),
    }


def delete_document(doc_id: str) -> bool:
    """
    Soft-deletes document, ensuring subsequent direct URLs return 404.
    """
    if doc_id in _DOCUMENTS_DB and not _DOCUMENTS_DB[doc_id].get("is_deleted"):
        _DOCUMENTS_DB[doc_id]["is_deleted"] = True
        _DOCUMENTS_DB[doc_id]["content"] = b""
        return True
    return False


def save_session_draft(session_id: str, draft_state: dict[str, Any]) -> None:
    """
    Saves work-in-progress edits to prevent data loss upon session expiry.
    """
    _DRAFTS_DB[session_id] = {
        "draft_state": draft_state,
        "updated_at": time.time(),
    }


def recover_session_draft(session_id: str) -> Optional[dict[str, Any]]:
    """
    Restores uncommitted draft edits.
    """
    record = _DRAFTS_DB.get(session_id)
    return record["draft_state"] if record else None
