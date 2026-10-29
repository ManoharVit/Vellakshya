"""
Hybrid Retrieval Engine implementing Reciprocal Rank Fusion (RRF).
Merges dense vector similarity and full-text keyword retrieval.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedding
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
    1. Computes vector embeddings and runs cosine similarity search.
    2. Runs full-text keyword search.
    3. Fuses rankings with RRF (k=60).
    """
    # 1. Vector candidates
    query_vector = get_embedding(query)
    vector_candidates = query_vector_chunks(db, document_id, query_vector, limit=20)

    # 2. Keyword candidates
    keyword_candidates = query_keyword_chunks(db, document_id, query, limit=20)

    # 3. Fuse via RRF
    fused = reciprocal_rank_fusion(
        [vector_candidates, keyword_candidates],
        k=60,
        top_n=top_n,
    )
    return fused
