---
title: Vellakshya PDF Workstation
emoji: 📑
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Vellakshya (वेल्लक्ष्य)
### Enterprise Swiss Army Knife PDF Workstation & Document Intelligence Platform

**Vellakshya** is an enterprise-grade document workstation providing full Adobe Acrobat Pro and Adobe Acrobat Studio capabilities alongside high-fidelity PDF-to-HTML conversion, cryptographic tamper detection, multi-user collaboration, and security sandboxing.

---

## Author & Attribution
- **Author / Developer:** Giri Manohar Vemula
- **Lead Architect:** Giri Manohar Vemula
- **LinkedIn Profile:** [https://www.linkedin.com/in/manoharv511](https://www.linkedin.com/in/manoharv511)
- **GitHub Profile:** [https://github.com/ManoharVit](https://github.com/ManoharVit)
- **Repository:** [https://github.com/ManoharVit/Vellakshya.git](https://github.com/ManoharVit/Vellakshya.git)

---

## Key Architectural Modules

### 1. High-Fidelity & Semantic PDF-to-HTML Engine
- **Fixed Point-Based Layout:** Translates arbitrary PDF pages into responsive HTML with exact CSS coordinates, point-based viewport boundaries, vector layers, embedded fonts, and typographic baselines.
- **Semantic Responsive Flow:** Automatically analyzes text blocks, headings ($$h1$$, $$h2$$), paragraphs, lists, hyperlinks, and image placeholders for accessibility and mobile screen readers.
- **Live Side-by-Side Dual Preview:** Live preview pane with full-text inspection, raw HTML extraction, and standalone export.

### 2. Professional Document Editing & Word-Style Replacement
- **Font & Color Preserving Find & Replace:** Detects font family, bold/italic weight, font size, sRGB color, and typographic baseline, whiting out the original glyphs and re-rendering replacement text with identical styling.
- **Pointer Coordinate Detection & Locking:** Interactive pointer coordinate capture directly from mouse clicks on the canvas, eliminating manual coordinate guessing.
- **Single vs. Replace All & Sequential Chaining:** Supports targeting specific occurrence indices or global replacement batches across documents.
- **Undo / Redo History Stack:** Robust multi-state history engine supporting keyboard shortcuts (`Ctrl+Z`, `Ctrl+Y`, `Cmd+Z`, `Cmd+Shift+Z`).
- **Page Operations:** Native rotation, multi-box cropping, deletion, reordering, extraction, and split/merge pipelines.

### 3. Deep Document Inspector & Preflight Audit
- **Executive Preflight Statistics:** Page count, file size ($$KB = \frac{\text{bytes}}{1024}$$), PDF specification version, encryption status, repair flags, OCG layer presence, word count, character count, embedded font count, image count, and form field counts.
- **Security Permissions Breakdown:** Bitmask permission decoding for printing, modification, content copying, annotations, and form filling.
- **Page Geometry Profiling:** Page dimensions in typographical points ($$pt$$) and metric millimeters ($$mm = \frac{pt \times 25.4}{72}$$), paper format detection (Letter, A4, Legal, Tabloid, A5, A3, Custom), orientation (Portrait/Landscape), and rotation.
- **Metadata Editor & Selective Deletion:** Live editing of Title, Author, Subject, Keywords, Creator, and Producer. Selective per-field deletion or 1-click total metadata sanitization with XMP XML stream stripping.
- **Table of Contents & Export:** Hierarchical TOC bookmark navigation and JSON report export.

### 4. Cryptographic Signatures & Tamper Detection
- **Digital Signatures:** Digitally signs PDF documents with visible approval badges and cryptographic SHA-256 document content digests.
- **Integrity & Tamper Verification:** Recalculates document digests on demand; flags `DIGEST_FAILURE_TAMPER_DETECTED` if any text, drawing, or structural object is modified after signing.

### 5. Multi-User Collaboration & Mobile Offline Sync
- **Concurrent Comment Merging:** Non-destructive three-way annotation merge preventing lost updates and duplicate comments. Monotonically increments document revision history.
- **Mobile Offline Queue:** Records local client mutations (annotations, rotation, highlights) while offline and reconciles them upon reconnection.

### 6. Security Sandboxing & Threat Prevention
- **Anti-Polyglot Defense:** Strictly validates `%PDF-` magic header at offset 0, rejecting GIF/HTML/EXE polyglots.
- **Payload Boundaries:** Prevents decompression bombs and oversized uploads exceeding memory budgets.
- **Executable Script Neutralization:** Scans for and neutralizes malicious `/Launch` actions and `/JavaScript` payloads.

---

## Layered Testing Suite (54 / 54 Passed)

The platform is covered by an automated layered test suite:

```bash
======================= 54 passed, 6 warnings in 20.12s ========================
```

| Layer / Test Suite | Description | Status |
| :--- | :--- | :--- |
| [`test_core_cases.py`](tests/test_core_cases.py) | 10 Core Test Cases (500-page responsiveness, font preservation, multi-column flow, deep redaction, password enforcement, digital signatures, concurrent collab, OCR accuracy, mobile offline sync, security rejection). | **10 / 10 PASSED** |
| [`test_performance_benchmarks.py`](tests/test_performance_benchmarks.py) | Performance benchmarks for 1 MB, 10 MB, 50 MB PDFs and 500-page enterprise documents. | **3 / 3 PASSED** |
| [`test_security_audit.py`](tests/test_security_audit.py) | DAST vulnerability audit, path traversal defenses, secret scanning, and dependency check. | **4 / 4 PASSED** |
| [`test_accessibility_and_visual.py`](tests/test_accessibility_and_visual.py) | Semantic landmarks, ARIA labels, mobile viewports, and 0% pixel drift visual regression. | **3 / 3 PASSED** |
| [`test_api_endpoints.py`](tests/test_api_endpoints.py) | REST API endpoints, streaming responses, and multipart file upload validation. | **14 / 14 PASSED** |
| [`test_interactive_ui.py`](tests/test_interactive_ui.py) | Frontend DOM contracts, vendor libraries, undo/redo stack, and Deep Inspector UI. | **4 / 4 PASSED** |
| [`test_pdf_services.py`](tests/test_pdf_services.py) | Backend PyMuPDF services, text replacement engine, and vector geometry. | **16 / 16 PASSED** |

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
