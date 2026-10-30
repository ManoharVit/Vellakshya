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


class ChatMessage(BaseModel):
    """Conversation turn for multi-turn Q&A context."""

    role: str = Field(description="'user' or 'assistant'")
    content: str
    timestamp: Optional[str] = None


class GroundingIndicator(BaseModel):
    """Groundedness and confidence metrics computed from retrieval rank fusion and passage coverage."""

    score: float = Field(ge=0.0, le=1.0, description="Normalized grounding confidence [0.0, 1.0]")
    confidence: str = Field(description="'High', 'Medium', or 'Low'")
    evidence_count: int = Field(
        default=0, description="Number of verified database chunks cited as evidence"
    )


class RAGQueryRequest(BaseModel):
    document_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    allow_external_ai: bool = Field(
        default=False,
        description="Local-first privacy gate for external AI (F13). When False, processing strictly stays offline.",
    )
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation history for multi-turn follow-up queries and context continuity.",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream tokens progressively via Server-Sent Events (SSE).",
    )


class RAGResponse(BaseModel):
    answer: str
    citations: list[CitationSource]
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    grounding: Optional[GroundingIndicator] = None


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


# ---------------------------------------------------------------------------
# Milestone 1: Document Analytics & Smart Summarizer Models
# ---------------------------------------------------------------------------


class ReadabilityMetrics(BaseModel):
    flesch_reading_ease: float
    flesch_kincaid_grade: float
    interpretation: str
    total_syllables: int
    avg_words_per_sentence: float
    avg_syllables_per_word: float


class KeywordFrequency(BaseModel):
    word: str
    count: int
    frequency_percent: float


class PhraseFrequency(BaseModel):
    phrase: str
    count: int
    type: str


class AnalyticsResponse(BaseModel):
    page_count: int
    filtered_page_count: int
    word_count: int
    char_count: int
    char_count_excluding_spaces: int
    sentence_count: int
    paragraph_count: int
    estimated_read_time_seconds: int
    estimated_read_time_human: str
    language_code: str
    language_name: str
    readability: ReadabilityMetrics
    top_keywords: list[KeywordFrequency]
    top_phrases: list[PhraseFrequency]


class AnalyticsRequest(BaseModel):
    document_id: Optional[str] = None
    selected_text: Optional[str] = None
    page_range: Optional[str] = None


class ExtractedInsights(BaseModel):
    action_items: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)


class SummarizeRequest(BaseModel):
    document_id: Optional[str] = None
    selected_text: Optional[str] = None
    page_range: Optional[str] = None
    level: str = Field(
        default="executive_summary",
        description="brief_overview, executive_summary, section_by_section, key_takeaways",
    )
    length: str = Field(default="medium", description="short, medium, long")
    tone: str = Field(default="neutral", description="neutral, executive, technical, simplified")
    output_format: str = Field(
        default="paragraph",
        description="paragraph, bullet_points, table, structured_report",
    )
    allow_external_ai: bool = Field(
        default=False,
        description="Local-first privacy gate. When False, strictly runs offline extractive summarization.",
    )


class SummarizeResponse(BaseModel):
    summary: str
    level: str
    length: str
    tone: str
    output_format: str
    insights: ExtractedInsights
    model_used: str
    page_count: int
    filtered_page_count: int
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Milestone 3: Multi-Format Ingestion & Bilingual Translation Models
# ---------------------------------------------------------------------------


class TranslatedSegment(BaseModel):
    segment_id: int
    source_text: str
    target_text: str
    segment_type: str = Field(
        default="paragraph", description="heading, paragraph, table_cell, list_item"
    )
    expansion_factor: float = Field(
        default=1.0, description="Ratio of target length to source length"
    )
    suggested_font_scale: float = Field(
        default=1.0, description="Recommended font scale (0.7 - 1.0) to prevent overflow"
    )
    glossary_terms_applied: list[str] = Field(default_factory=list)


class TranslationRequest(BaseModel):
    document_id: Optional[str] = None
    selected_text: Optional[str] = None
    source_language: str = Field(default="auto", description="Source ISO language code or 'auto'")
    target_language: str = Field(
        default="es",
        description="Target ISO language code (e.g. es, fr, de, hi, zh, ja, ar, it, pt)",
    )
    domain: str = Field(
        default="general", description="general, legal, financial, medical, technical"
    )
    scope: str = Field(default="selection", description="selection, full_document, current_page")
    page_number: Optional[int] = None
    allow_external_ai: bool = Field(
        default=False,
        description="Local-first privacy gate (F13). When False, zero network egress; uses local glossary & translation memory.",
    )
    preserve_layout: bool = Field(
        default=True, description="Whether to preserve headings, tables, and markup structures"
    )


class TranslationResponse(BaseModel):
    source_language: str
    source_language_name: str
    target_language: str
    target_language_name: str
    domain: str
    original_text: str
    translated_text: str
    segments: list[TranslatedSegment] = Field(default_factory=list)
    total_segments: int = 0
    memory_cache_hits: int = 0
    provider: str = Field(description="'local_deterministic' or 'external_cloud'")
    average_expansion_factor: float = 1.0
    overflow_risk: str = Field(default="low", description="'low', 'moderate', or 'high'")
    latency_ms: float = 0.0


class MultiFormatIngestResponse(BaseModel):
    status: str
    document_id: str
    filename: str
    detected_format: str
    title: str
    page_count: int
    chunks_count: int
    table_count: int
    word_count: int
    text_preview: str
    pdf_url: str
    owner_id: str
    allow_external_ai: bool
