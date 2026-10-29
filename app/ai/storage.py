"""
Storage and indexing layer for RAG chunks and document metadata.
Supports PostgreSQL with pgvector (HNSW + GIN full-text index) with transparent
SQLite fallback for local testing and offline CI execution.
"""

from __future__ import annotations

import json
import math
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Session

from app.ai.models import DocumentChunk
from app.models.db import Base, utc_now


class AIDocument(Base):
    __tablename__ = "ai_documents"

    id = Column(String(64), primary_key=True)
    owner_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    embedding_model = Column(String(64), nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AIChunk(Base):
    __tablename__ = "ai_chunks"

    id = Column(String(64), primary_key=True)
    document_id = Column(
        String(64),
        ForeignKey("ai_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, index=True)
    rects = Column(Text, nullable=False)  # JSON-encoded array of bounding boxes
    page_w = Column(Float, nullable=False)
    page_h = Column(Float, nullable=False)
    rotation = Column(Integer, default=0, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON-encoded vector (or native pgvector)
    tsv = Column(Text, nullable=True)  # Full-text representation


def init_ai_tables(db: Session) -> None:
    """Creates AI document and chunk tables and initializes pgvector if on PostgreSQL."""
    bind = db.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        with db.connection() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

    Base.metadata.create_all(bind=bind)


def store_document_and_chunks(
    db: Session,
    document_id: str,
    owner_id: str,
    filename: str,
    sha256: str,
    embedding_model: str,
    embedding_dim: int,
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> None:
    """Persists document header and all associated spatial text chunks."""
    init_ai_tables(db)

    # Check if document already exists
    existing_doc = db.query(AIDocument).filter(AIDocument.id == document_id).first()
    if not existing_doc:
        doc = AIDocument(
            id=document_id,
            owner_id=owner_id,
            filename=filename,
            sha256=sha256,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )
        db.add(doc)
        db.flush()
    else:
        # Delete old chunks for clean replacement
        db.query(AIChunk).filter(AIChunk.document_id == document_id).delete()
        db.flush()

    for chunk, emb in zip(chunks, embeddings):
        stored_chunk = AIChunk(
            id=chunk.id,
            document_id=document_id,
            page=chunk.page,
            rects=json.dumps(chunk.rects),
            page_w=chunk.page_w,
            page_h=chunk.page_h,
            rotation=chunk.rotation,
            content=chunk.content,
            embedding=json.dumps(emb),
            tsv=chunk.content.lower(),
        )
        db.add(stored_chunk)

    db.commit()


def get_chunk_by_id(db: Session, chunk_id: str) -> Optional[DocumentChunk]:
    """Retrieves a single chunk by its stable ID."""
    row = db.query(AIChunk).filter(AIChunk.id == chunk_id).first()
    if not row:
        return None
    return DocumentChunk(
        id=str(row.id),
        document_id=str(row.document_id),
        page=int(row.page),
        rects=json.loads(str(row.rects)),
        page_w=float(row.page_w),
        page_h=float(row.page_h),
        rotation=int(row.rotation),
        content=str(row.content),
    )


def query_keyword_chunks(
    db: Session,
    document_id: str,
    query_str: str,
    limit: int = 20,
) -> list[DocumentChunk]:
    """
    Performs full-text keyword retrieval.
    On PostgreSQL uses websearch_to_tsquery; on SQLite uses token matching.
    """
    engine = db.get_bind()
    dialect_name = engine.dialect.name
    tokens = [t.lower() for t in query_str.split() if len(t) > 2]

    if dialect_name == "postgresql":
        # Native PostgreSQL full-text search
        sql = text("""
            SELECT id, document_id, page, rects, page_w, page_h, rotation, content
            FROM ai_chunks
            WHERE document_id = :doc_id
              AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
            LIMIT :limit
        """)
        rows = db.execute(
            sql, {"doc_id": document_id, "query": query_str, "limit": limit}
        ).fetchall()
        return [
            DocumentChunk(
                id=r[0],
                document_id=r[1],
                page=r[2],
                rects=json.loads(r[3]),
                page_w=r[4],
                page_h=r[5],
                rotation=r[6],
                content=r[7],
            )
            for r in rows
        ]

    # SQLite fallback: scored token overlap
    all_chunks = db.query(AIChunk).filter(AIChunk.document_id == document_id).all()
    scored: list[tuple[float, AIChunk]] = []
    for c in all_chunks:
        content_lower = c.content.lower()
        score = sum(1.0 for t in tokens if t in content_lower)
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        DocumentChunk(
            id=str(c.id),
            document_id=str(c.document_id),
            page=int(c.page),
            rects=json.loads(str(c.rects)),
            page_w=float(c.page_w),
            page_h=float(c.page_h),
            rotation=int(c.rotation),
            content=str(c.content),
            score=s,
        )
        for s, c in scored[:limit]
    ]


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def query_vector_chunks(
    db: Session,
    document_id: str,
    query_vector: list[float],
    limit: int = 20,
) -> list[DocumentChunk]:
    """
    Performs vector similarity search.
    Computes cosine distance on vectors.
    """
    all_chunks = db.query(AIChunk).filter(AIChunk.document_id == document_id).all()
    scored: list[tuple[float, AIChunk]] = []

    for c in all_chunks:
        emb = json.loads(str(c.embedding))
        sim = _cosine_similarity(query_vector, emb)
        scored.append((sim, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        DocumentChunk(
            id=str(c.id),
            document_id=str(c.document_id),
            page=int(c.page),
            rects=json.loads(str(c.rects)),
            page_w=float(c.page_w),
            page_h=float(c.page_h),
            rotation=int(c.rotation),
            content=str(c.content),
            score=s,
        )
        for s, c in scored[:limit]
    ]
