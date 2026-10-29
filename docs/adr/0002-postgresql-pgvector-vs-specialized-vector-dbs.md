# 2. PostgreSQL with pgvector Over Dedicated Vector Databases

## Status
Accepted

## Context
Deploying specialized standalone vector databases (Pinecone, Qdrant, Milvus) fragments the document data model. Storing user authentication, access control lists (ACLs), audit logs, and version manifests in a relational database while storing vectors in a third-party service leads to dual-write race conditions, synchronization failures, and complex backup topologies.

## Decision
We standardized all relational metadata, version tracking, audit chains, and vector embeddings in a single **PostgreSQL 16** database utilizing the official `pgvector` extension:
- `vector(768)` column with an `HNSW` index using `vector_cosine_ops`.
- Filter-first execution guaranteeing tenant isolation by `owner_id` and `document_id`.

## Consequences
- **Positive:** ACID transactional atomicity: deleting or scrubbing a document instantly cascades to its vector chunks and audit events.
- **Positive:** Zero additional network latency to external SaaS vector providers.
- **Positive:** Seamless SQLite fallback for offline local testing and lightweight developer environments.
- **Negative:** Requires PostgreSQL with C extension support (`pgvector/pgvector:pg16` Docker image).
