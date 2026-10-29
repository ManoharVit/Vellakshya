"""
Pydantic data schemas for Vellakshya AI & RAG system.
Includes strict server-side validation models for citations, chunks, and PII entities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized rectangle representation in PDF coordinates [x0, y0, x1, y1]."""

    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class ChunkMetadata(BaseModel):
    """Metadata recorded for each document chunk in raw unrotated PDF coordinates."""

    page: int
    rects: list[list[float]] = Field(
        default_factory=list,
        description="List of bounding boxes [x0, y0, x1, y1] for text spans in this chunk",
    )
    page_w: float
    page_h: float
    rotation: int = 0


class DocumentChunk(BaseModel):
    """Internal indexed chunk representation."""

    id: str
    document_id: str
    page: int
    rects: list[list[float]]
    page_w: float
    page_h: float
    rotation: int = 0
    content: str
    score: Optional[float] = None


class CitationSource(BaseModel):
    """Server-resolved citation mapping back to verified database coordinates."""

    chunk_id: str
    page: int
    quote: str
    rects: list[list[float]]
    page_w: float
    page_h: float
    rotation: int = 0


class LLMAnswerOutput(BaseModel):
    """Schema returned by the LLM. The model never emits coordinates or bounding boxes."""

    answer: str
    used_chunk_ids: list[str] = Field(default_factory=list)


class RAGQueryRequest(BaseModel):
    document_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    allow_external_ai: bool = Field(
        default=False,
        description="Local-first privacy gate for external AI (F13). When False, processing strictly stays offline.",
    )


class RAGResponse(BaseModel):
    answer: str
    citations: list[CitationSource]
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False


class PIIEntityMatch(BaseModel):
    """Proposed PII candidate for user approval."""

    id: str
    entity_type: str
    matched_text: str
    confidence: float
    page: int
    rects: list[list[float]]


class PIIScanResponse(BaseModel):
    document_id: str
    total_detected: int
    entities: list[PIIEntityMatch]


class PIIApplyRequest(BaseModel):
    document_id: str
    approved_entity_ids: list[str]
