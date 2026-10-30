"""
Hybrid Retrieval Engine implementing Reciprocal Rank Fusion (RRF).
Merges dense vector similarity and full-text keyword retrieval.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.models import DocumentChunk
from app.ai.storage import query_keyword_chunks, query_vector_chunks


def reciprocal_rank_fusion(
    ranked_lists: list[list[DocumentChunk]],
    k: int = 60,
    top_n: int = 5,
) -> list[DocumentChunk]:
    """
    Combines multiple ranked candidate lists using Reciprocal Rank Fusion (RRF).
    Score for each document d = sum(1 / (k + rank_i(d)))
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, DocumentChunk] = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            doc_map[chunk.id] = chunk
            current_score = scores.get(chunk.id, 0.0)
            scores[chunk.id] = current_score + (1.0 / (k + rank))

    # Sort candidates by descending RRF score
    sorted_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    results: list[DocumentChunk] = []
    for cid in sorted_chunk_ids[:top_n]:
        chunk = doc_map[cid]
        chunk.score = round(scores[cid], 5)
        results.append(chunk)

    return results


def hybrid_search(
    db: Session,
    document_id: str,
    query: str,
    top_n: int = 5,
) -> list[DocumentChunk]:
    """
    Executes hybrid retrieval:
    1. Computes query vector in the matching document embedding space.
    2. Runs vector similarity search (if spaces match and provider is healthy).
    3. Runs full-text keyword search.
    4. Fuses rankings with RRF (k=60).
    """
    from app.ai.embeddings import LOCAL_DETERMINISTIC_HASH_MODEL, get_embedding_with_metadata
    from app.ai.storage import AIDocument

    ai_doc = db.query(AIDocument).filter_by(id=document_id).first()
    model_name: str = (
        str(ai_doc.embedding_model)
        if ai_doc and ai_doc.embedding_model
        else "local-deterministic-hash-v1"
    )
    allow_ext: bool = bool(ai_doc.allow_external_ai) if ai_doc else False
    dim: int = int(ai_doc.embedding_dim) if ai_doc and ai_doc.embedding_dim else 768

    vector_candidates: list[DocumentChunk] = []
    # 1. Compute query vector preserving space provenance
    query_res = get_embedding_with_metadata(
        text=query,
        model_name=model_name,
        dim=dim,
        allow_external=allow_ext,
        allow_silent_fallback=True,
    )

    # Invariant: Never compare mismatched spaces (e.g. hash fallback query against dense cloud vectors)
    space_compatible = not (
        query_res.is_fallback
        and model_name not in (LOCAL_DETERMINISTIC_HASH_MODEL, "text-embedding-004")
    )

    if space_compatible:
        vector_candidates = query_vector_chunks(db, document_id, query_res.vector, limit=20)

    # 2. Keyword candidates
    keyword_candidates = query_keyword_chunks(db, document_id, query, limit=20)

    # 3. Fuse via RRF
    candidates_to_fuse = [keyword_candidates]
    if vector_candidates:
        candidates_to_fuse.insert(0, vector_candidates)

    fused = reciprocal_rank_fusion(
        candidates_to_fuse,
        k=60,
        top_n=top_n,
    )
    return fused
