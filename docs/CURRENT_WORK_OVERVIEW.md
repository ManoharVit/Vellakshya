# Vellakshya v2.0: Comprehensive Technical and Executive Project Overview

- **Lead Architect & Author:** Giri Manohar Vemula
- **Profiles:** [LinkedIn](https://www.linkedin.com/in/manoharv511) | [GitHub](https://github.com/ManoharVit)
- **Repository:** [`ManoharVit/Vellakshya`](https://github.com/ManoharVit/Vellakshya)
- **Production URL:** `https://vellakshya-gcp.web.app`

---

## Section 1: Technical Architecture & Systems Engineering (For Engineers & Architects)

### 1. System Architecture & Component Topology
Vellakshya v2.0 is an enterprise-grade document workstation engineered with a decoupled, high-performance architecture:

```
[ Client Browser / Workstation ]
        |
        v  (HTTPS / WSS)
[ Google Firebase Hosting (Global Edge CDN) ]
        |
        +---> Static Assets (Self-hosted Fonts, Bundled CSS, Vanilla JS Workstation)
        |
        +---> Dynamic API Proxy (Rewrites: /api/** -> Cloud Run)
                    |
                    v
[ Google Cloud Run (vellakshya) ]
  - Runtime: Python 3.12 (Debian Slim container)
  - Framework: FastAPI + Uvicorn ASGI Server
  - Core Processing: PyMuPDF (C-backed MuPDF bindings)
  - Cryptography: Ed25519 (Asymmetric Manifests) & AES-256-GCM
  - AI & Vector Store: In-memory HNSW / pgvector & BM25 Hybrid Retrieval
  - Background Workers: Cloud Run isolated worker pools & OCR jobs
```

### 2. Core Processing Engines & Algorithms
- **Pixel-Perfect PDF Parsing & Layout Analysis:** Utilizes PyMuPDF C-bindings to extract raw glyph spans, typographical baselines, font metrics, and bounding boxes ($$x_0, y_0, x_1, y_1$$). Converts unstructured binary PDF streams into semantic, accessible HTML5/DOM representations without fidelity loss.
- **Font-Matching In-Place Replacement:** Automatically inspects target text bounding boxes, samples color hexadecimal codes and font weights, whiteouts the original vector path, and stamps replacements exactly on the baseline using matched font families (`Noto Sans`, `DejaVu Sans`).
- **Hybrid Retrieval-Augmented Generation (RAG):**
  - **Lexical Layer:** BM25 scoring over tokenized document chunks for exact match precision (acronyms, clause numbers, names).
  - **Semantic Layer:** Dense vector embeddings using cosine similarity:
    $$\text{Cosine Similarity}(u, v) = \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
  - **Grounding & Attribution:** Matches generated tokens against spatial chunk coordinates, returning bounding-box rectangles for page-level verification.
- **Bilingual Synchronized Translation Canvas:** Ingests PDF, DOCX, XLSX, CSV, and Markdown. Preserves dual-pane structural symmetry with cross-iframe bidirectional scroll locking based on relative scroll percentages ($$\%_{\text{scroll}} = \frac{scrollTop}{scrollHeight - clientHeight}$$).

### 3. Cryptographic Governance & Security Posture
- **Ed25519 Asymmetric Manifests:** Document integrity trees are signed with Ed25519 keypairs. Rejection of compromised fallback keys is strictly enforced at startup.
- **Dynamic 256-bit Secrets:** In production environments, per-process high-entropy keys (`secrets.token_bytes(32)`) guarantee zero hardcoded credential vulnerabilities.
- **Tenant Isolation:** Enforces multi-tenant data barriers. Unauthenticated workstation visitors operate within an isolated `demo_user` sandbox; authenticated requests carrying enterprise JWT `Bearer` tokens enforce strict resource ownership checks.
- **Local-First Privacy Gate (F13):** Hardware-level toggle preventing any network egress. When unchecked, RAG, analytics, and summarization run strictly in-process with zero third-party cloud API dependencies.

### 4. Cloud Infrastructure & Quality Assurance Metrics
- **Cloud Run Deployment:** Configured with `concurrency=80`, auto-scaling ($$0$$ to $$4$$ instances), and memory limit of $$1\text{ GiB}$$.
- **Automated Test Coverage:**
  - **Backend (Pytest):** $$189$$ passed test cases spanning unit logic, API endpoints, cryptographic audit remediation, and RAG streaming.
  - **Frontend (Playwright & Vitest):** $$91$$ passed end-to-end specifications verifying WCAG AA contrast standards ($$\ge 4.5:1$$), keyboard navigation, sidebar collapse controls (`Ctrl+B`), and axe-core accessibility audits.

---

## Section 2: Executive & Business Overview (For Non-Technical Stakeholders)

### 1. Executive Summary & Value Proposition
Vellakshya is an **all-in-one, privacy-first digital document workstation** designed for enterprises that handle sensitive contracts, financial statements, medical records, and legal briefs. 

Unlike traditional PDF tools that require expensive per-user licenses (e.g., Adobe Acrobat) or third-party web tools that upload confidential corporate files to public clouds, Vellakshya gives organizations a unified platform to edit, convert, summarize, analyze, and translate documents with guaranteed data security.

### 2. Key Business Capabilities
- **Complete Document Control:** Merge, split, rotate, reorder, crop, and redact pages in seconds with an intuitive, modern interface.
- **Intelligent Text Editing:** Edit text directly inside scanned or generated PDFs while automatically preserving original fonts, sizes, and alignments.
- **Verifiable AI Document Assistant:** Ask questions about complex documents (such as 100-page contracts) and receive immediate, grounded answers with clickable citations that take you directly to the exact paragraph on the page.
- **Smart Summarization & Analytics:** Generate executive summaries, bullet-point briefs, or statistical readability reports with a single click.
- **Parallel Document Translation:** Translate foreign-language documents side-by-side with synchronized scrolling, ensuring teams can review original and translated contracts simultaneously.
- **Zero-Egress Privacy Guarantee:** An explicit privacy gate ensures that sensitive files never leave corporate boundaries or train external AI models.

### 3. Business Impact & ROI
| Strategic Advantage | Traditional Commercial Solutions | Vellakshya v2.0 Workstation |
| :--- | :--- | :--- |
| **Licensing Cost** | High recurring per-seat subscription fees (\$20–\$30/user/month). | Open architecture deployable on low-cost serverless cloud ($$0$$ idle cost). |
| **Data Privacy & Compliance** | Confidential PDFs often sent to third-party proprietary clouds. | Local-first processing with zero network egress option for strict HIPAA/GDPR compliance. |
| **AI Reliability** | Generic LLM responses prone to hallucinations. | 100% grounded hybrid RAG with verifiable bounding-box page citations. |
| **Deployment Agility** | Heavy desktop installations or complex enterprise deployments. | Instant browser access backed by Google Global Edge CDN and auto-scaling Cloud Run. |

Vellakshya combines modern consumer-grade usability with enterprise-grade data sovereignty, dramatically reducing administrative overhead while protecting intellectual property.
