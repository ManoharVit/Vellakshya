# ADR 0008: Real-Time Collaborative Document Sync & CRDT (Yjs) Architecture

## Status
Accepted

## Context
Vellakshya provides real-time multi-user document collaboration across distributed participants via WebSocket endpoints (`/ws/documents/{doc_id}`). Currently, collaboration uses event-based broadcast messaging for:
- Live participant presence and remote cursor pointers.
- Bounding-box anchored comments and resolution states.
- Highlighting and freehand drawing annotations.

While event broadcasting operates cleanly under standard network latencies, concurrent editing across offline peers or degraded networks introduces potential ordering ambiguity and race conditions. Operational Transformation (OT) requires a central coordinating server, which is incompatible with Vellakshya's zero-backend and offline-first architectural principles.

## Decision
Adopt **Yjs (Conflict-Free Replicated Data Type - CRDT)** as the canonical real-time and offline synchronization standard for all collaborative document structures:
1. **Shared State Representation**:
   - `Y.Doc`: Root container for each active document session (`doc_id`).
   - `Y.Array<Comment>`: Commutative, order-preserving collection of threaded comments.
   - `Y.Map<Annotation>`: Keyed map of vector overlays, highlights, and page redaction geometries.
   - `Y.Awareness`: Ephemeral, non-persisted presence protocol for peer cursors, current viewport, active tool, and participant color tokens.
2. **Wire Protocol Compatibility**:
   - The WebSocket gateway in `app/api/collaboration_ws.py` supports both legacy JSON events and binary `y-websocket` synchronization packets (`sync-step-1`, `sync-step-2`, `update`).
   - Binary updates are decoded using lib0 variable-length integers and applied directly to local `Y.Doc` state vectors.
3. **Storage & Convergence Guarantee**:
   - CRDT updates are commutative and idempotent: Any sequence of received updates converges to mathematically identical document state across all clients without a coordinating authority.
   - Updates are periodically snapshotted to PostgreSQL / Valkey as compressed binary blobs (`bytea` / Redis string).

## Consequences
- **Positive**:
  - Guaranteed eventual consistency across all connected and offline-reconnecting clients ($$0\%$$ state collision).
  - True offline-first editing: Users on flights or mobile devices can annotate PDFs offline and merge cleanly upon reconnection.
  - Sub-millisecond local latency with zero round-trip blocking.
- **Negative / Mitigations**:
  - CRDT state vectors accumulate tombstone metadata over time; mitigated through periodic document garbage collection and version checkpoint snapshotting.
