# 5. Pinned Embedding Model with Generation-Only Provider Fallback

## Status
Accepted

## Context
In multi-provider RAG architectures, naive fallback designs sometimes switch both embedding and generation models when an API outage occurs. However, vector embeddings produced by different models (e.g. Google `text-embedding-004` vs OpenAI `text-embedding-3-small`) inhabit geometrically incompatible vector spaces. Calculating cosine distance between heterogeneous embeddings destroys retrieval precision.

## Decision
We enforce an architectural boundary between embedding and generation:
1. **Pinned Embedding Model:** We pin a single model (`text-embedding-004`, 768 dimensions) stored in database metadata. Re-indexing is mandatory before changing the embedding model.
2. **Deterministic Local Fallback:** For offline CI testing and local execution without API keys, a deterministic L2-normalized hashing vector is provided.
3. **Generation-Only Fallback:** Dynamic provider fallback applies strictly to the text generation step:
   $$\text{Primary: Gemini 1.5 Flash} \longrightarrow \text{Secondary: GPT-4o-mini} \longrightarrow \text{Local: Offline Synthesizer}$$

## Consequences
- **Positive:** Absolute geometric consistency of the vector database index across all revisions.
- **Positive:** Zero risk of corrupting database vector distances during transient API rate limit events.
