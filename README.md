# Vellakshya (वेल्लक्ष्य)
### Enterprise Swiss Army Knife PDF Workstation & Document Intelligence Platform

**Vellakshya** is an enterprise-grade document workstation providing full Adobe Acrobat Pro and Adobe Acrobat Studio capabilities alongside high-fidelity PDF-to-HTML conversion, cryptographic tamper detection, multi-user collaboration, and security sandboxing.

---

## Author & Project Attribution
- **Author / Developer:** Giri Manohar Vemula
- **Lead Architect:** Giri Manohar Vemula
- **LinkedIn Profile:** [https://www.linkedin.com/in/manoharv511](https://www.linkedin.com/in/manoharv511)
- **GitHub Profile:** [https://github.com/ManoharVit](https://github.com/ManoharVit)
- **Repository:** [https://github.com/ManoharVit/Vellakshya.git](https://github.com/ManoharVit/Vellakshya.git)
- **Production Deployment (Netlify):** [https://vellakshya.netlify.app](https://vellakshya.netlify.app)

---

## Architectural Modules & Implementation Roadmap

### Phase 1: Isolated Worker Architecture & Queue (Milestones 8 & 9)
- **Standalone Runner:** Independent background worker (`app/worker/runner.py`) decoupling compute-intensive PDF operations from the HTTP event loop.
- **Resource Sandbox:** Subprocess execution sandbox (`app/services/sandbox.py`) enforcing a hard $$512\text{ MB}$$ memory limit and $$30\text{ s}$$ CPU timeout.
- **Job Queue:** Redis-backed worker queue (`app/services/queue.py`) with transparent local in-memory fallback for high availability.
- **Docker Seccomp Isolation:** Rootless container definition (`deploy/sandbox/Dockerfile`) with dropped Linux capabilities and restricted system calls.

### Phase 2: Relational DB Persistence, Immutable Versioning & Cryptographic Integrity (Milestones 4 & 10)
- **Enterprise Relational Schema:** Complete Section 4 schema (`app/models/db.py`) covering `User`, `Document`, `DocumentPermission`, `DocumentVersion`, `DocumentOperation`, `IntegrityManifest`, `Comment`, and `AuditEvent`.
- **Presigned Object Storage:** S3-compatible HMAC-SHA256 presigned token storage service (`app/services/storage.py`) preventing unauthorized binary exfiltration.
- **Optimistic Concurrency Control:** Enforces strict `base_version` validation across transformation operations, returning HTTP 409 Conflict upon state divergence.
- **Idempotency Replay:** Cached idempotency keys replay exact prior version outputs without re-executing document transformations.
- **Linear Hash Chaining:** Audit trails secured by immutable SHA-256 chain links: $$event\_hash = \text{SHA-256}(canonical \mathbin{\Vert} previous\_hash)$$.
- **Ed25519 Signed Manifests:** Cryptographically signed version manifests verifying byte size, SHA-256 digest, and timestamp authenticity.

### Phase 3: Real-Time Multi-User Collaboration & WebSockets (Milestone 11)
- **WebSocket Broadcast Gateway:** Central room manager (`app/services/collaboration.py` & `app/api/collaboration_ws.py`) broadcasting presence, live cursor tracking, and real-time annotations.
- **Collaborator Presence UI:** Visual presence bar displaying live collaborator avatars with page indicators and connected status pills.
- **Threaded Geometric Comments:** Anchors comments to normalized bounding boxes `{x, y, w, h}` with parent-child discussion trees.

### Phase 4: Sandboxing, Privacy Controls & Adversarial Security (Milestone 12)
- **Owner-Only Retention Purging:** `DELETE /api/v2/documents/{doc_id}` purges relational metadata and scrubs all binary objects from storage.
- **Strict Content Security Policy:** PDF-to-HTML converter injects `script-src 'none'` CSP headers to prevent stored XSS attacks.
- **Payload & Path Traversal Guards:** Enforces $$50\text{ MB}$$ payload limits (HTTP 413) and strips directory traversal artifacts (`..`, `/`, `\`).
- **Adversarial Security Test Suite:** Dedicated 8-test suite (`tests/test_adversarial_security.py`) auditing RBAC boundaries, polyglot rejection, and presigned token tampering.

### Phase 5: Automated Verification & CI/CD Pipeline (Milestones 13 & 14)
- **77 Passing Automated Tests:**
  - 55 Pytest backend tests (Core MVP cases, REST API, worker queue, persistence, collaboration, and adversarial security).
  - 4 Vitest frontend unit tests (typographic geometry, sRGB color normalization, PDF permission masks).
  - 18 Playwright end-to-end browser tests (SPA shell navigation, file upload, conversion, export hub touchpoints, undo/redo).
- **Secure Dependency Management:** Bounded versioning constraints across all production dependencies.

---

## Automated Verification Suite (77 / 77 Passed)

```bash
Backend Pytest Suite:     55 passed in 3.67s
Frontend Vitest Suite:     4 passed in 87ms
Playwright Browser E2E:   18 passed in 9.60s
Total Automated Tests:    77 passed (100% pass rate)
```

| Test Suite | File | Tests | Status |
| :--- | :--- | :---: | :---: |
| **Core MVP Engineering Cases** | [`tests/test_core_cases.py`](tests/test_core_cases.py) | 10 | **PASSED** |
| **REST API Layer** | [`tests/test_api_endpoints.py`](tests/test_api_endpoints.py) | 14 | **PASSED** |
| **Worker Queue & Sandbox** | [`tests/test_worker_queue_and_sandbox.py`](tests/test_worker_queue_and_sandbox.py) | 9 | **PASSED** |
| **V2 Persistence & Ed25519 Manifests** | [`tests/test_v2_persistence.py`](tests/test_v2_persistence.py) | 8 | **PASSED** |
| **Real-Time WebSockets Collaboration** | [`tests/test_collaboration_websockets.py`](tests/test_collaboration_websockets.py) | 6 | **PASSED** |
| **Adversarial Security Audit** | [`tests/test_adversarial_security.py`](tests/test_adversarial_security.py) | 8 | **PASSED** |
| **Frontend Geometry & Masks (Vitest)** | [`tests/unit/app.test.js`](tests/unit/app.test.js) | 4 | **PASSED** |
| **Browser E2E Workflows (Playwright)** | [`tests/e2e/workstation.spec.js`](tests/e2e/workstation.spec.js) | 18 | **PASSED** |

---

## Local Development & Setup

### 1. Prerequisites
- Python 3.11+
- `pip` or `uv` package manager

### 2. Installation
```bash
git clone https://github.com/ManoharVit/Vellakshya.git
cd Vellakshya
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Running the Server
```bash
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

### 4. Running the Complete Test Suite
```bash
PYTHONPATH=. pytest tests/ -v
```

---

## License
Proprietary / All Rights Reserved.  
Architected & Developed by **Giri Manohar Vemula** ([LinkedIn](https://www.linkedin.com/in/manoharv511) | [GitHub](https://github.com/ManoharVit)).
