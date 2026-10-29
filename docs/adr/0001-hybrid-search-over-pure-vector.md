# 1. Hybrid Search with Reciprocal Rank Fusion Over Pure Vector Search

## Status
Accepted

## Context
Dense vector embeddings excel at semantic and conceptual similarity (e.g., matching "compensation" with "salary"), but regularly fail on exact lexical lookups, statutory codes, tax identifiers, dates, and domain-specific acronyms. Pure vector search alone produced a 72% retrieval hit rate on our technical and legal document benchmark.

## Decision
We implemented a hybrid retrieval architecture:
1. **Dense Vector Search:** Pinned normalized embedding vectors queried via cosine similarity (`HNSW` index in PostgreSQL).
2. **Lexical Full-Text Search:** BM25 / PostgreSQL full-text search (`tsvector` column with `GIN` index).
3. **Rank Fusion:** Reciprocal Rank Fusion (RRF) with constant $k=60$:
   $$RRF(d) = \sum_{m \in M} \frac{1}{60 + \text{rank}_m(d)}$$

## Consequences
- **Positive:** Retrieval Hit Rate@3 on our 25-question golden evaluation dataset increased from 72% to 96.0%.
- **Positive:** System handles empty keyword results gracefully without requiring manual heuristic fallbacks.
- **Negative:** Slightly higher indexing complexity requiring both `tsvector` and vector columns.
