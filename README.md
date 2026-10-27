# Vellakshya: Enterprise Document Workstation & PDF Intelligence System

[![CI/CD Pipeline](https://github.com/ManoharVit/Vellakshya/actions/workflows/ci-full.yml/badge.svg)](https://github.com/ManoharVit/Vellakshya/actions/workflows/ci-full.yml)
[![Production Deployment](https://img.shields.io/badge/Production-vellakshya.netlify.app-00ad9f?style=flat&logo=netlify)](https://vellakshya.netlify.app/)
[![Automated Tests](https://img.shields.io/badge/Tests-166%20Passed-brightgreen)](https://github.com/ManoharVit/Vellakshya/actions)
[![Python Version](https://img.shields.io/badge/Python-3.12-blue)](pyproject.toml)
[![Node Version](https://img.shields.io/badge/Node.js-20.x-green)](package.json)

**Production Web Application:** [https://vellakshya.netlify.app/](https://vellakshya.netlify.app/)  
**Source Code Repository:** [https://github.com/ManoharVit/Vellakshya.git](https://github.com/ManoharVit/Vellakshya.git)  

---

## Author & Engineering Attribution
- **Lead Architect & Developer:** Giri Manohar Vemula
- **LinkedIn Profile:** [https://www.linkedin.com/in/manoharv511](https://www.linkedin.com/in/manoharv511)
- **GitHub Profile:** [https://github.com/ManoharVit](https://github.com/ManoharVit)

---

## 1. Executive Summary & Problem Definition

Organizations that manage sensitive document workflows frequently encounter a structural dilemma: desktop software suites impose steep licensing fees and platform lock-in, whereas public software-as-a-service (SaaS) utilities route unencrypted document binaries through external third-party infrastructure. This data transmission introduces unacceptable compliance risks under GDPR, HIPAA, and internal security mandates. Furthermore, traditional browser-based document editors often suffer from high operational latency, unpredictable network failures, and layout deformation during document format conversions.

Vellakshya resolves this dilemma by implementing a **hybrid dual-engine architecture**:
1. **Edge Client Engine:** A zero-backend, browser-native processing layer running on [Netlify Edge CDN](https://vellakshya.netlify.app/) that executes PDF parsing, page transformations, coordinate-accurate word replacement, text insertion, cropping, and document assembly entirely within the user's browser memory via WebAssembly and JavaScript (`pdf-lib`, `pdfjs-dist`). In this operational mode, documents never leave the client's device, eliminating network latency and data exposure risks.
2. **Full-Stack Enterprise Service:** A containerized backend service powered by Python 3.12, FastAPI, and PyMuPDF that handles server-side rasterization, relational document version trees, optimistic concurrency control, cryptographic manifest signing (RFC 8032 Ed25519), and real-time multi-user WebSocket collaboration.

---

## 2. System Architecture & Dual Operating Modes

Vellakshya operates under two distinct deployment targets depending on infrastructure requirements and data sensitivity:

```
                                  [ User Web Browser ]
                                           |
                   +-----------------------+-----------------------+
                   |                                               |
                   v                                               v
        [ Edge Client Engine ]                          [ Full-Stack Server ]
       Hosted on Netlify Edge CDN                     FastAPI + PyMuPDF Service
  +---------------------------------+             +---------------------------------+
  | - In-memory execution (pdf-lib) |             | - High-throughput REST API      |
  | - Zero data exfiltration        |             | - SQLite / PostgreSQL relational|
  | - Sub-10ms response latency     |             | - Background worker & queue     |
  | - Offline functionality         |             | - Ed25519 cryptographic signing |
  | - Pure client-side PDF render   |             | - Multi-user WebSocket rooms    |
  +---------------------------------+             +---------------------------------+
```

### Architectural Trade-off Analysis

| Dimension | Edge Client Mode (Netlify) | Full-Stack Enterprise Mode (Self-Hosted) |
| :--- | :--- | :--- |
| **Primary URL** | [https://vellakshya.netlify.app/](https://vellakshya.netlify.app/) | `http://localhost:8000` (or private cluster) |
| **Backend Dependency** | None (Static Edge CDN distribution) | Python 3.12, FastAPI, Uvicorn, SQLite/PostgreSQL |
| **Data Privacy** | Absolute: document bytes stay in local memory | Controlled: document binaries stored in private storage |
| **Execution Latency** | Near-zero ($$< 10\text{ ms}$$ for typical edits) | Network-bound ($$50\text{ ms} - 250\text{ ms}$$ round-trip) |
| **Text Find & Replace** | Bounding-box canvas redaction & redraw | Structural content stream replacement via PyMuPDF |
| **Multi-User Collaboration** | Local session state | Synchronized WebSocket rooms with live presence |
| **Cryptographic Signatures** | Client-side verification | Server-side Ed25519 signing and SHA-256 linear audit |
| **Conversion (PDF to HTML)** | Local text layer inspection | Semantic multi-column DOM conversion with strict CSP |

This separation of concerns ensures that organizations can deploy the client interface as an independent static site on Netlify with zero server hosting costs while retaining the option to connect to a private FastAPI cluster for enterprise features.

---

## 3. Core Functional Capabilities

### Document Editing & Typography
- **Coordinate-Accurate Find & Replace:** Locates specific keyword occurrences using PDF text matrix extraction, paints an opaque background rectangle to mask previous glyphs, and renders replacement text at corresponding typographic metrics ($$\text{size} \approx h \times 0.85$$).
- **Text Insertion & Annotations:** Positions custom text boxes onto designated page coordinates with selectable font sizes, hex color codes, and optional opaque background fills.
- **Area Redaction & Whiteout:** Overwrites sensitive regions (SSNs, account numbers, private keys) with opaque white masking boxes at exact coordinate boundaries ($$x_0, y_0, x_1, y_1$$).
- **Watermarking Engine:** Applies semi-transparent running watermarks across designated page sets with adjustable opacity ($$0.05 - 1.0$$), font scaling, and rotation angles ($$0^\circ - 360^\circ$$).
- **Running Headers & Footers:** Generates standardized running headers and footers with customizable typographic margins.
- **Dynamic Page Numbering:** Injects sequential page numbers using format strings (`Page {n} of {total}`) at bottom-center, bottom-left, or bottom-right alignments.

### Document Assembly & Geometry
- **Document Merge & Page Splitting:** Merges disparate PDF streams into unified documents or extracts specific page ranges into standalone outputs.
- **Page Rotation & Deletion:** Modifies internal page rotation dictionaries ($$90^\circ$$, $$180^\circ$$, $$270^\circ$$) and strips unneeded pages in descending order to preserve index consistency.
- **Page Sequence Reordering:** Reorganizes arbitrary page sequences based on comma-separated index specifications.
- **Bounding-Box Cropping:** Adjusts the document `/CropBox` geometry using points ($$\text{pt}$$) or millimeters ($$\text{mm}$$) with live interactive previews.

### Security, Cryptography & Auditability
- **RFC 8032 Ed25519 Signatures:** Generates digital signatures over document byte arrays and timestamped manifests to detect post-export tampering.
- **Linear Hash Chaining:** Secures audit event trails using recursive SHA-256 hash chains:
  $$event\_hash = \text{SHA-256}(canonical\_payload \mathbin{\Vert} previous\_hash)$$
- **Strict Content Security Policy (CSP):** Emits PDF-to-HTML conversions with `script-src 'none'` headers to prevent Cross-Site Scripting (XSS) from malicious embedded scripts.
- **Polyglot & Traversal Rejection:** Validates magic byte signatures to block malicious file wrappers and sanitizes paths against directory traversal (`../`).

---

## 4. Automated Verification & Quality Assurance

Vellakshya maintains a comprehensive automated testing suite encompassing **166 tests** across four distinct frameworks. Every commit to `main` executes this suite via GitHub Actions.

```
Total Test Suite: 166 Passed / 0 Failed (100% Pass Rate)
=========================================================
- Pytest Backend & Security:   111 passed in 26.08s
- Vitest Frontend Geometry:      4 passed in 94ms
- Playwright Browser & a11y:    51 passed in 24.80s
- k6 Load Benchmark:            20 VUs, p(95) < 500ms, 0% error rate
```

### Test Coverage Matrix

| Test Module | File Path | Tests | Scope & Assertions |
| :--- | :--- | :---: | :--- |
| **Core Engineering Cases** | [`tests/test_core_cases.py`](tests/test_core_cases.py) | 10 | Validates rotation angles, page deletion, merge ordering, and crop bounds. |
| **REST API Layer** | [`tests/test_api_endpoints.py`](tests/test_api_endpoints.py) | 14 | Verifies status codes, MIME types, error handling, and response payloads. |
| **Adversarial Security Audit** | [`tests/test_adversarial_security.py`](tests/test_adversarial_security.py) | 8 | Audits RBAC access boundaries, polyglot rejection, and presigned tokens. |
| **Worker Queue & Sandbox** | [`tests/test_worker_queue_and_sandbox.py`](tests/test_worker_queue_and_sandbox.py) | 9 | Tests process timeouts ($$30\text{ s}$$), memory bounds ($$512\text{ MB}$$), and job states. |
| **Relational Persistence** | [`tests/test_v2_persistence.py`](tests/test_v2_persistence.py) | 8 | Validates immutable version nodes, optimistic locking ($$409$$), and manifests. |
| **WebSocket Collaboration** | [`tests/test_collaboration_websockets.py`](tests/test_collaboration_websockets.py) | 6 | Tests presence tracking, broadcast events, and comment tree serialization. |
| **Interactive UI Endpoints** | [`tests/test_interactive_ui.py`](tests/test_interactive_ui.py) | 4 | Verifies SPA index serving, static assets, and viewer mount points. |
| **PDF Processing Services** | [`tests/test_pdf_services.py`](tests/test_pdf_services.py) | 17 | Tests PyMuPDF service wrappers, font handling, and document metadata. |
| **Accessibility & Visual** | [`tests/test_accessibility_and_visual.py`](tests/test_accessibility_and_visual.py) | 3 | Checks semantic HTML structure and visual contrast ratios. |
| **Comprehensive MVP Suite** | [`tests/test_mvp_plan.py`](tests/test_mvp_plan.py) | 25 | End-to-end verification of all core PDF transformation milestones. |
| **Performance Benchmarks** | [`tests/test_performance_benchmarks.py`](tests/test_performance_benchmarks.py) | 3 | Benchmarks throughput and memory consumption across operations. |
| **Security Audit Protocols** | [`tests/test_security_audit.py`](tests/test_security_audit.py) | 4 | Validates secret storage, sanitized logs, and permission bitmasks. |
| **Frontend Geometry (Vitest)** | [`tests/unit/app.test.js`](tests/unit/app.test.js) | 4 | Unit tests typography conversion ($$\text{pt} \to \text{mm}$$) and sRGB normalization. |
| **Browser E2E (Playwright)** | [`tests/e2e/workstation.spec.js`](tests/e2e/workstation.spec.js) | 44 | Verifies UI tools, upload handlers, sidebar navigation, and tool switching. |
| **Netlify Offline Fallback** | [`tests/e2e/netlify_client_replace.spec.js`](tests/e2e/netlify_client_replace.spec.js) | 2 | Simulates edge environment by blocking backend `/api` and validating `pdf-lib`. |
| **WCAG 2.1 AA Compliance** | [`tests/accessibility/wcag.spec.js`](tests/accessibility/wcag.spec.js) | 2 | Executes automated axe-core audits ensuring 0 critical a11y violations. |
| **API Contract Validation** | [`tests/api/contracts.spec.js`](tests/api/contracts.spec.js) | 3 | Verifies end-to-end HTTP contracts against running instances. |

---

## 5. Local Setup & Reproducible Execution

Follow these steps to configure a local development environment, run the backend service, and execute the automated test suites.

### Prerequisites
- **Python:** Version 3.12 (with `pip` and virtual environment support)
- **Node.js:** Version 20.x or higher (with `npm`)

### Step 1: Clone and Set Up Dependencies
```bash
# Clone the repository
git clone https://github.com/ManoharVit/Vellakshya.git
cd Vellakshya

# Configure Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install locked Python dependencies
pip install --upgrade pip
pip install -r requirements.txt pytest uvicorn

# Install Node.js testing dependencies
npm ci
```

### Step 2: Run the Development Server
```bash
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser to inspect the application.

### Step 3: Execute the Test Suites
```bash
# 1. Run backend pytest suite (111 tests)
PYTHONPATH=. pytest tests/ -v

# 2. Run frontend unit tests (Vitest)
npm run test:unit

# 3. Run browser end-to-end and accessibility tests (Playwright)
npx playwright install chromium --with-deps
npx playwright test

# 4. Run performance benchmark (k6)
k6 run k6/load-test.js
```

### Step 4: Build Netlify Production Bundle
```bash
node netlify-build.js
```
Expected output:
```
[Netlify Build] Zero-backend edge mode active: in-browser pdf-lib engine enabled
[Netlify Build] Successfully wrote _redirects to app/static/_redirects
```

---

## 6. Technical Limitations & Engineering Trade-offs

To maintain architectural transparency, the following technical trade-offs are documented:

1. **Client-Side Typographic Replacement:** When running on Netlify Edge without a backend, `clientReplaceText` embeds standard Helvetica glyphs. If the source PDF uses custom embedded font subsets with non-standard glyph encodings, minor visual discrepancy in character spacing may occur. The full-stack PyMuPDF engine avoids this by modifying existing font descriptors directly on the server.
2. **Client Memory Ceilings:** While `pdf-lib` handles documents with several hundred pages efficiently, extremely large PDF binaries ($$> 150\text{ MB}$$) containing uncompressed high-resolution raster images may experience memory pressure in constrained mobile browser tabs. In such scenarios, the self-hosted backend worker sandbox is recommended.
3. **Collaboration Sync Scope:** Real-time multi-user cursor tracking and threaded comments depend on WebSocket connectivity provided by the backend service. On static Netlify deployments, document edits remain scoped to the active browser tab session unless connected to a running collaboration server.

---

## 7. License & Attribution

This project is authored and maintained by **Giri Manohar Vemula**.

- **Lead Architect & Developer:** Giri Manohar Vemula
- **LinkedIn Profile:** [https://www.linkedin.com/in/manoharv511](https://www.linkedin.com/in/manoharv511)
- **GitHub Profile:** [https://github.com/ManoharVit](https://github.com/ManoharVit)
- **Live Netlify Production Application:** [https://vellakshya.netlify.app/](https://vellakshya.netlify.app/)
