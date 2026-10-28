"""
Vellakshya Relational Database Schema.
Defines immutable document versions, role-based permissions, operations,
signed integrity manifests, threaded comments, and hash-chained audit trails.
"""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    owned_documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    permissions = relationship(
        "DocumentPermission", back_populates="user", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    owner_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    current_version = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="active", nullable=False)  # active, archived, deleted
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    owner = relationship("User", back_populates="owned_documents")
    permissions = relationship(
        "DocumentPermission", back_populates="document", cascade="all, delete-orphan"
    )
    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    operations = relationship(
        "DocumentOperation", back_populates="document", cascade="all, delete-orphan"
    )
    comments = relationship("Comment", back_populates="document", cascade="all, delete-orphan")
    audit_events = relationship(
        "AuditEvent", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPermission(Base):
    __tablename__ = "document_permissions"

    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(32), nullable=False)  # 'owner', 'editor', 'reviewer', 'viewer'
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="permissions")
    user = relationship("User", back_populates="permissions")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no = Column(Integer, nullable=False)
    parent_version_id = Column(
        String(36), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    object_key = Column(String(512), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version_no"),)

    document = relationship("Document", back_populates="versions")
    parent_version = relationship("DocumentVersion", remote_side=[id])
    integrity_manifest = relationship(
        "IntegrityManifest", back_populates="version", uselist=False, cascade="all, delete-orphan"
    )


class DocumentOperation(Base):
    __tablename__ = "document_operations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    input_version_id = Column(String(36), ForeignKey("document_versions.id"), nullable=False)
    output_version_id = Column(String(36), ForeignKey("document_versions.id"), nullable=True)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    operation_type = Column(
        String(64), nullable=False
    )  # rotate, reorder, delete, watermark, crop, etc.
    parameters = Column(SQLITE_JSON, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    status = Column(String(32), default="succeeded", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="operations")


class IntegrityManifest(Base):
    __tablename__ = "integrity_manifests"

    version_id = Column(
        String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True
    )
    manifest_json = Column(SQLITE_JSON, nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    signature = Column(Text, nullable=False)  # Base64 encoded Ed25519 digital signature
    key_id = Column(String(64), nullable=False)
    verified_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    version = relationship("DocumentVersion", back_populates="integrity_manifest")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id = Column(
        String(36), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    parent_comment_id = Column(
        String(36), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    page_no = Column(Integer, nullable=True)
    anchor = Column(SQLITE_JSON, nullable=True)  # Geometry bounding box {x, y, w, h}
    body = Column(Text, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="comments")
    parent_comment = relationship("Comment", remote_side=[id])


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)
    event_data = Column(SQLITE_JSON, nullable=False)
    previous_event_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="audit_events")


# -------------------------------------------------------------
# Database Engine & Session Factory
# -------------------------------------------------------------


def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'vellakshya.db')}",
    )


def create_db_engine(db_url: Optional[str] = None):
    url = db_url or get_database_url()
    is_sqlite = url.startswith("sqlite")

    # Ensure data directory exists if sqlite
    if is_sqlite and ":///" in url:
        db_path = url.split(":///", 1)[1]
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=True,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine_override=None):
    """Creates all database tables."""
    eng = engine_override or engine
    Base.metadata.create_all(bind=eng)


def get_db():
    """FastAPI dependency for yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
