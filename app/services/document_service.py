"""
Vellakshya Document Lifecycle, Immutable Versioning, and Audit Service.
Orchestrates relational metadata, optimistic concurrency checks (base_version),
cryptographic Ed25519 manifests, and hash-chained audit trails.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.db import (
    AuditEvent,
    Comment,
    Document,
    DocumentOperation,
    DocumentPermission,
    DocumentVersion,
    IntegrityManifest,
    User,
    utc_now,
)
from app.services.signatures import sign_manifest, verify_manifest
from app.services.storage import storage_instance, ObjectNotFoundError


class DocumentNotFoundError(Exception):
    pass


class VersionConflictError(Exception):
    """Raised when an operation targets a stale base version (HTTP 409)."""
    pass


class PermissionDeniedError(Exception):
    """Raised when a user attempts an unauthorized document action (HTTP 403)."""
    pass


class DocumentService:
    @staticmethod
    def _canonical_json(data: dict[str, Any]) -> str:
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _compute_event_hash(event_data: dict[str, Any], previous_hash: Optional[str]) -> str:
        canonical = DocumentService._canonical_json(event_data)
        combined = f"{canonical}:{previous_hash or 'GENESIS'}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    @staticmethod
    def check_permission(
        db: Session,
        doc_id: str,
        user_id: str,
        required_role: str = "viewer"  # 'viewer' < 'reviewer' < 'editor' < 'owner'
    ) -> str:
        hierarchy = {"viewer": 1, "reviewer": 2, "editor": 3, "owner": 4}
        perm = db.query(DocumentPermission).filter_by(document_id=doc_id, user_id=user_id).first()
        if not perm:
            raise PermissionDeniedError(f"User {user_id} does not have access to document {doc_id}.")

        user_level = hierarchy.get(perm.role, 0)
        req_level = hierarchy.get(required_role, 1)
        if user_level < req_level:
            raise PermissionDeniedError(
                f"Operation requires '{required_role}' permission; user role is '{perm.role}'."
            )
        return perm.role

    @classmethod
    def create_document(
        cls,
        db: Session,
        owner_id: str,
        title: str,
        initial_pdf_bytes: bytes,
    ) -> tuple[Document, DocumentVersion]:
        doc_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        object_key = f"documents/{doc_id}/versions/1.pdf"

        # 1. Store immutable binary object
        storage_instance.store_object(object_key, initial_pdf_bytes, "application/pdf")
        sha256_digest = storage_instance.compute_sha256(initial_pdf_bytes)

        # 2. Create Document record
        doc = Document(
            id=doc_id,
            owner_id=owner_id,
            title=title,
            current_version=1,
            status="active",
        )
        db.add(doc)

        # 3. Grant owner permission
        perm = DocumentPermission(
            document_id=doc_id,
            user_id=owner_id,
            role="owner",
        )
        db.add(perm)

        # 4. Create DocumentVersion record
        ver = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_no=1,
            parent_version_id=None,
            object_key=object_key,
            byte_size=len(initial_pdf_bytes),
            sha256=sha256_digest,
            created_by=owner_id,
        )
        db.add(ver)

        # 5. Generate signed integrity manifest
        time_iso = utc_now().isoformat()
        manifest_payload = {
            "document_id": doc_id,
            "version_no": 1,
            "sha256": sha256_digest,
            "byte_size": len(initial_pdf_bytes),
            "created_by": owner_id,
            "timestamp": time_iso,
        }
        signed_result = sign_manifest(manifest_payload)
        manifest_record = IntegrityManifest(
            version_id=version_id,
            manifest_json=manifest_payload,
            manifest_hash=signed_result["manifest_hash"],
            signature=signed_result["signature"],
            key_id=signed_result["key_id"],
            verified_at=utc_now(),
        )
        db.add(manifest_record)

        # 6. Record genesis audit event
        audit_data = {
            "action": "document_created",
            "doc_id": doc_id,
            "version_no": 1,
            "actor_id": owner_id,
            "sha256": sha256_digest,
        }
        event_hash = cls._compute_event_hash(audit_data, None)
        audit_event = AuditEvent(
            document_id=doc_id,
            actor_id=owner_id,
            action="document_created",
            event_data=audit_data,
            previous_event_hash=None,
            event_hash=event_hash,
        )
        db.add(audit_event)

        db.commit()
        db.refresh(doc)
        db.refresh(ver)
        return doc, ver

    @classmethod
    def list_documents(cls, db: Session, actor_id: str) -> list[Document]:
        """
        Lists documents owned by or shared with the actor.
        """
        perm_doc_ids = db.query(DocumentPermission.document_id).filter_by(user_id=actor_id).subquery()
        docs = (
            db.query(Document)
            .filter((Document.owner_id == actor_id) | (Document.id.in_(perm_doc_ids)))
            .order_by(Document.updated_at.desc())
            .all()
        )
        return docs

    @classmethod
    def apply_operation(
        cls,
        db: Session,
        doc_id: str,
        actor_id: str,
        operation_type: str,
        base_version: int,
        idempotency_key: str,
        parameters: dict[str, Any],
        transformed_pdf_bytes: bytes,
    ) -> tuple[DocumentVersion, bool]:
        """
        Applies a destructive operation creating a traceable, immutable new version.
        Enforces optimistic concurrency checking against base_version (HTTP 409 on conflict).
        Returns: (new_or_existing_version, is_idempotent_replay)
        """
        # Idempotency check scoped to this document
        existing_op = db.query(DocumentOperation).filter_by(document_id=doc_id, idempotency_key=idempotency_key).first()
        if existing_op and existing_op.output_version_id:
            existing_ver = db.query(DocumentVersion).filter_by(id=existing_op.output_version_id).first()
            if existing_ver:
                return existing_ver, True

        doc = db.query(Document).filter_by(id=doc_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document {doc_id} not found.")

        # Check permissions: Requires 'editor' or higher
        cls.check_permission(db, doc_id, actor_id, required_role="editor")

        # Concurrency verification: Base version must match active version
        if base_version != doc.current_version:
            raise VersionConflictError(
                f"Version conflict: Operation specified baseVersion={base_version}, "
                f"but active document is at current_version={doc.current_version}."
            )

        parent_ver = db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=base_version).first()
        if not parent_ver:
            raise DocumentNotFoundError(f"Base version {base_version} not found for document {doc_id}.")

        next_version_no = doc.current_version + 1
        new_version_id = str(uuid.uuid4())
        new_object_key = f"documents/{doc_id}/versions/{next_version_no}.pdf"

        # 1. Store immutable output binary in object store
        storage_instance.store_object(new_object_key, transformed_pdf_bytes, "application/pdf")
        sha256_digest = storage_instance.compute_sha256(transformed_pdf_bytes)

        # 2. Create new DocumentVersion record
        new_ver = DocumentVersion(
            id=new_version_id,
            document_id=doc_id,
            version_no=next_version_no,
            parent_version_id=parent_ver.id,
            object_key=new_object_key,
            byte_size=len(transformed_pdf_bytes),
            sha256=sha256_digest,
            created_by=actor_id,
        )
        db.add(new_ver)
        db.flush()

        # 3. Create DocumentOperation log record
        op_record = DocumentOperation(
            document_id=doc_id,
            input_version_id=parent_ver.id,
            output_version_id=new_version_id,
            actor_id=actor_id,
            operation_type=operation_type,
            parameters=parameters,
            idempotency_key=idempotency_key,
            status="succeeded",
            completed_at=utc_now(),
        )
        db.add(op_record)

        # 4. Generate signed integrity manifest
        manifest_payload = {
            "document_id": doc_id,
            "version_no": next_version_no,
            "parent_sha256": parent_ver.sha256,
            "sha256": sha256_digest,
            "byte_size": len(transformed_pdf_bytes),
            "operation": operation_type,
            "actor_id": actor_id,
            "timestamp": utc_now().isoformat(),
        }
        signed_result = sign_manifest(manifest_payload)
        manifest_record = IntegrityManifest(
            version_id=new_version_id,
            manifest_json=manifest_payload,
            manifest_hash=signed_result["manifest_hash"],
            signature=signed_result["signature"],
            key_id=signed_result["key_id"],
            verified_at=utc_now(),
        )
        db.add(manifest_record)

        # 5. Append-only Hash Chained Audit Event
        all_audits = db.query(AuditEvent).filter_by(document_id=doc_id).all()
        prev_hashes = {a.previous_event_hash for a in all_audits}
        head_event = None
        for a in all_audits:
            if a.event_hash not in prev_hashes:
                head_event = a
                break
        prev_hash = head_event.event_hash if head_event else None

        audit_data = {
            "action": f"operation_{operation_type}",
            "doc_id": doc_id,
            "from_version": base_version,
            "to_version": next_version_no,
            "actor_id": actor_id,
            "sha256": sha256_digest,
            "idempotency_key": idempotency_key,
        }
        event_hash = cls._compute_event_hash(audit_data, prev_hash)
        audit_event = AuditEvent(
            document_id=doc_id,
            actor_id=actor_id,
            action=f"operation_{operation_type}",
            event_data=audit_data,
            previous_event_hash=prev_hash,
            event_hash=event_hash,
        )
        db.add(audit_event)

        # 6. Advance document active current_version
        doc.current_version = next_version_no
        doc.updated_at = utc_now()

        db.commit()
        db.refresh(new_ver)
        return new_ver, False

    @classmethod
    def verify_document_integrity(
        cls,
        db: Session,
        doc_id: str,
        version_no: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Recomputes SHA-256 over exact stored bytes and verifies Ed25519 digital manifest signature.
        Reports: verified | content_modified | manifest_invalid
        """
        doc = db.query(Document).filter_by(id=doc_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document {doc_id} not found.")

        target_vno = version_no if version_no is not None else doc.current_version
        ver = db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=target_vno).first()
        if not ver:
            raise DocumentNotFoundError(f"Version {target_vno} not found for document {doc_id}.")

        # 1. Read stored bytes
        try:
            stored_bytes = storage_instance.get_object(ver.object_key)
        except ObjectNotFoundError:
            return {
                "status": "content_missing",
                "verified": False,
                "document_id": doc_id,
                "version_no": target_vno,
                "error": "Stored object not found in storage repository.",
            }

        # 2. Recompute SHA-256
        actual_sha256 = storage_instance.compute_sha256(stored_bytes)
        manifest = ver.integrity_manifest
        is_sig_valid = verify_manifest(manifest.manifest_json, manifest.signature) if manifest else False

        if actual_sha256 != ver.sha256:
            return {
                "status": "content_modified",
                "verified": False,
                "signature_valid": is_sig_valid,
                "document_id": doc_id,
                "version_no": target_vno,
                "stored_sha256": ver.sha256,
                "expected_sha256": ver.sha256,
                "computed_sha256": actual_sha256,
                "actual_sha256": actual_sha256,
                "error": "Tamper detected: File bytes do not match expected version digest.",
            }

        # 3. Verify digital signature of manifest
        if not manifest:
            return {
                "status": "manifest_missing",
                "verified": False,
                "signature_valid": False,
                "document_id": doc_id,
                "version_no": target_vno,
                "error": "Integrity manifest record is missing.",
            }

        if not is_sig_valid:
            return {
                "status": "manifest_invalid",
                "verified": False,
                "signature_valid": False,
                "document_id": doc_id,
                "version_no": target_vno,
                "error": "Cryptographic signature over manifest failed verification.",
            }

        return {
            "status": "verified",
            "verified": True,
            "signature_valid": True,
            "document_id": doc_id,
            "version_no": target_vno,
            "stored_sha256": ver.sha256,
            "computed_sha256": actual_sha256,
            "sha256": actual_sha256,
            "byte_size": ver.byte_size,
            "signature_key_id": manifest.key_id,
            "verified_at": utc_now().isoformat(),
        }

    @classmethod
    def share_document(
        cls,
        db: Session,
        doc_id: str,
        granter_id: str,
        target_user_id: str,
        role: str,
    ) -> DocumentPermission:
        # Only 'owner' can share/change roles
        cls.check_permission(db, doc_id, granter_id, required_role="owner")

        if role not in ("owner", "editor", "reviewer", "viewer"):
            raise ValueError(f"Invalid role: {role}")

        perm = db.query(DocumentPermission).filter_by(document_id=doc_id, user_id=target_user_id).first()
        if perm:
            perm.role = role
        else:
            perm = DocumentPermission(document_id=doc_id, user_id=target_user_id, role=role)
            db.add(perm)

        db.commit()
        db.refresh(perm)
        return perm

    @classmethod
    def add_comment(
        cls,
        db: Session,
        doc_id: str,
        author_id: str,
        body: str,
        version_no: Optional[int] = None,
        page_no: Optional[int] = None,
        anchor: Optional[dict[str, Any]] = None,
        parent_comment_id: Optional[str] = None,
    ) -> Comment:
        # Requires at least 'reviewer'
        cls.check_permission(db, doc_id, author_id, required_role="reviewer")

        doc = db.query(Document).filter_by(id=doc_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document {doc_id} not found.")

        target_vno = version_no if version_no is not None else doc.current_version
        ver = db.query(DocumentVersion).filter_by(document_id=doc_id, version_no=target_vno).first()

        comment = Comment(
            document_id=doc_id,
            version_id=ver.id if ver else None,
            parent_comment_id=parent_comment_id,
            author_id=author_id,
            page_no=page_no,
            anchor=anchor,
            body=body,
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return comment

    @classmethod
    def get_audit_trail(cls, db: Session, doc_id: str) -> list[dict[str, Any]]:
        raw_events = db.query(AuditEvent).filter_by(document_id=doc_id).all()
        if not raw_events:
            return []

        # Reconstruct chain order starting from genesis (previous_event_hash is None)
        by_prev: dict[Optional[str], AuditEvent] = {ev.previous_event_hash: ev for ev in raw_events}
        ordered: list[AuditEvent] = []
        curr_prev = None
        while curr_prev in by_prev:
            ev = by_prev[curr_prev]
            ordered.append(ev)
            curr_prev = ev.event_hash
            if len(ordered) == len(raw_events):
                break

        if len(ordered) < len(raw_events):
            seen_ids = {e.id for e in ordered}
            for ev in raw_events:
                if ev.id not in seen_ids:
                    ordered.append(ev)

        return [
            {
                "id": ev.id,
                "action": ev.action,
                "actor_id": ev.actor_id,
                "event_data": ev.event_data,
                "previous_event_hash": ev.previous_event_hash,
                "event_hash": ev.event_hash,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in ordered
        ]
