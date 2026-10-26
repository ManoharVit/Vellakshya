# Vellakshya QA Test Plan, Security Review & Release Checklist

**Author & Lead Architect:** Giri Manohar Vemula  
**LinkedIn:** [https://www.linkedin.com/in/manoharv511](https://www.linkedin.com/in/manoharv511)  
**GitHub Repository:** [https://github.com/ManoharVit/Vellakshya.git](https://github.com/ManoharVit/Vellakshya.git)  

---

## 1. Test Design: User Stories, Test Cases & Acceptance Criteria

### Story 1: High-Fidelity PDF-to-HTML Conversion
- **User Story**: As a cross-platform user, I want to convert multi-column, font-embedded PDFs into responsive HTML so that my document retains its exact visual layout without broken formatting on Windows, macOS, iOS, Android, and web browsers.
- **Test Cases**:
  - `TC-CONV-01`: Standard single-column PDF conversion to fixed and semantic HTML.
  - `TC-CONV-02`: Multi-column document with tables, hyperlinks, and vector graphics.
  - `TC-CONV-03`: Multilingual document containing Devanagari, Cyrillic, Japanese (CJK), and Arabic (RTL).
- **Edge Cases**:
  - Overlapping text spans, non-standard embedded Type3 fonts, rotated pages ($$90^\circ$$, $$180^\circ$$, $$270^\circ$$).
  - Standalone link annotations (`LINK_URI`) not attached to continuous text blocks.
- **Acceptance Criteria**:
  - Converted HTML passes WCAG 2.1 AA audits with zero critical violations.
  - Text retention exceeds $$99.0\%$$; visual layout drift is $$0.0\%$$ on untouched page areas.

### Story 2: Permanent Content Redaction & Data Sanitization
- **User Story**: As a compliance officer, I want to permanently redact sensitive identifiers (SSNs, API keys, passwords) so that sensitive data cannot be recovered by any party.
- **Test Cases**:
  - `TC-RED-01`: Redact specific keyword instances across multi-page documents.
  - `TC-RED-02`: Raw binary byte audit of exported PDF output.
- **Edge Cases**:
  - Text split across hyphenated line breaks or multi-line paragraphs.
  - Text stored in uncompressed object streams, compressed XREFs, or font glyph mappings.
- **Acceptance Criteria**:
  - Redacted text is absent from the PDF visual layer (`page.get_text()`).
  - Redacted text byte sequence is absent from the raw uncompressed PDF binary streams.

### Story 3: Role-Based Access Control (RBAC) & Concurrency
- **User Story**: As a document owner, I want to share documents with Viewers who can only inspect content, while Editors collaborate without silent data overwrites.
- **Test Cases**:
  - `TC-RBAC-01`: Viewer role blocked from document download ($$403\text{ Forbidden}$$) and editing ($$403\text{ Forbidden}$$).
  - `TC-RBAC-02`: Concurrent edits by User A and User B trigger Optimistic Concurrency Control ($$409\text{ Conflict}$$) upon version collision.
- **Edge Cases**:
  - Sudden session expiration preserves active unsaved draft state.
  - Two users commenting simultaneously on identical or adjacent coordinates.
- **Acceptance Criteria**:
  - Conflicting edits are never overwritten silently; conflict details are returned to client.
  - Uncommitted session edits can be recovered via `GET /api/sessions/draft/{id}`.

---

## 2. Layered Automation Architecture

| Test Layer | Framework / Engine | Target Scope | Execution Cadence |
|---|---|---|---|
| **Unit / Logic** | Vitest | Typographic conversion (`pt` to `mm`), bitmasks, RGB normalizations | Pre-commit / PR |
| **Component & E2E** | Playwright | Single-page UI, file upload dropzone, live canvas rendering, tool navigation | Every commit / PR |
| **Accessibility (a11y)** | axe-core + Playwright | WCAG 2.0 & 2.1 Level A and AA standards, color contrast, semantic landmarks | Every commit / PR |
| **REST API Contracts** | Playwright API / Pytest | Multipart uploads, conversion, encryption, redaction, digital signing, RBAC | Nightly & PR |
| **PDF Fidelity** | `pdf-lib` & `pdfjs-dist` | Structural page tree validation, embedded metadata, visual pixel hash diff | Nightly |
| **Load & Performance** | k6 | Latency budgets ($$p(95) < 500\text{ ms}$$), health checks ($$p(95) < 2000\text{ ms}$$ at 20 VUs) | Nightly / Pre-release |

---

## 3. Test Data Management & Strict Privacy Standard

> [!CAUTION]
> **Zero Customer Data Policy**: Never upload real customer PDFs, private keys, signing certificates, production database dumps, or confidential credentials into AI tools or testing suites.

### Synthetic Test Data Assets ([`test-data/synthetic/`](file:///Users/girimanoharv/.gemini/antigravity/scratch/Vellakshya/test-data/synthetic))
- **`synthetic_multilingual.pdf`**: Multi-script sample covering English, Hindi, Spanish, Cyrillic, Japanese, and Arabic.
- **`synthetic_table.pdf`**: Multi-column tabular layout with vector borders and financial budget values.
- **`metadata_profiles.json`**: Anonymized metadata dictionaries spanning corporate, legal, and international specs.
- **`edge_case_filenames.json`**: Filenames containing spaces, UTF-8 multi-byte glyphs, special symbols, and maximum length strings ($$> 180\text{ characters}$$).
- **`user_roles_matrix.json`**: Anonymized roles and permission mapping for Admin, Editor, Viewer, and Auditor.

---

## 4. Bug Triage Framework

### Severity Classification Matrix
| Severity | Impact Description | SLA Target | Example Defect |
|---|---|---|---|
| **P0 - Critical** | Data loss, security leakage, unhandled server crash, or broken core editing | Immediate ($$< 2\text{ hours}$$) | Sensitive string found in raw bytes after redaction; unhandled server 500 on valid upload |
| **P1 - High** | Feature failure with no workaround; major performance or visual layout drift | Fix within $$24\text{ hours}$$ | Multi-column converted text reading order inverted; viewer able to trigger file download |
| **P2 - Medium** | Non-critical feature bug with acceptable workaround | Fix within current sprint | Zoom level keyboard shortcut fails inside textarea; minor color contrast warning |
| **P3 - Low** | Cosmetic flaw, spelling error, or non-blocking UI alignment | Scheduled backlog | Button margin offset by 2px in mobile view; tooltip copy typo |

### Root Cause Analysis (RCA) Protocol
1. **Log Capture**: Inspect structured FastAPI request logs and Playwright trace files (`trace.zip`).
2. **Failure Classification**:
   - `PARSER_FAIL`: Corrupt XREF table or unrecognized filter stream.
   - `DOM_SYNC_FAIL`: Frontend canvas rendering timeout before document hydration.
   - `CONCURRENCY_CONFLICT`: Base version mismatch in optimistic locking check.
   - `SECURITY_REJECT`: Polyglot header detection or `/Launch` action execution block.
3. **Reproduction Unit Test**: Create a minimal reproducing test case in `tests/` before applying source fixes.

---

## 5. Security Review Checklist

- [x] **Authentication & Sessions**: Passwords hashed with unique per-user cryptographic salts using SHA-256; session tokens generated via `secrets.token_urlsafe(32)`.
- [x] **Access Control (RBAC)**: Viewer role strictly blocked from downloading ($$403\text{ Forbidden}$$) and mutating ($$403\text{ Forbidden}$$) managed files.
- [x] **File Upload Validation**: Mandatory magic byte verification (`%PDF`); rejection of polyglot files (`.gif.pdf`, `.html.pdf`) and oversized payloads ($$> 100\text{ MB}$$).
- [x] **Malicious Payload Sandboxing**: Automated scanning for embedded scripts (`/JavaScript`, `/JS`), launch actions (`/Launch`), and malformed XREFs.
- [x] **Permanent Redaction**: Destruction of sensitive text in visual text layer and uncompressed stream catalogs.
- [x] **404 Enforceability**: Soft-deleted files immediately return HTTP 404 on direct URL or API access.

---

## 6. PDF Structural & Visual Fidelity Validation

Automated validation utility script: [`scripts/validate_pdf_fidelity.py`](file:///Users/girimanoharv/.gemini/antigravity/scratch/Vellakshya/scripts/validate_pdf_fidelity.py)

```bash
# Execute fidelity comparison between baseline and target PDF
python scripts/validate_pdf_fidelity.py baseline.pdf output.pdf --retention 0.98 --json
```

### Verification Criteria
1. **Page Count & Dimensions**: Zero deviation in page count or bounding box dimensions ($$W \times H\text{ pt}$$).
2. **Text Retention**: Minimum text similarity ratio of $$95.0\%$$ using character-level sequence matching.
3. **Visual Raster Drift**: Pixel-by-pixel color mismatch strictly bounded to $$\le 0.05\%$$ on untouched page surfaces.
4. **Font Subsets**: Preservation of embedded TrueType/OpenType font names and encoding vectors.

---

## 7. Free Browser & Device Coverage Matrix

### Local & Automated Free Tools
- **Google Chrome / Microsoft Edge**: Locally installed Chromium builds run via Playwright (`--with-deps`).
- **Mozilla Firefox**: Standard Gecko automation through Playwright Firefox engine.
- **Apple Safari / WebKit**: Automated via Playwright WebKit headless engine; manual verification on macOS Safari and iOS devices.
- **Mobile Web Emulation**: Chrome DevTools mobile emulation with Pixel 5 ($$393 \times 851\text{ px}$$) and iPhone 13 ($$390 \times 844\text{ px}$$) viewport presets.

### Free Cloud & Academic Programs
- **GitHub Student Developer Pack**:
  - **LambdaTest**: Free live testing tier for interactive cross-browser and physical mobile device verification.
  - **Microsoft Azure**: Free student credits to host temporary staging environments and staging CI runners.
  - **GitHub Codespaces & Actions**: Free compute minutes for continuous test automation on every push.

---

## 8. Pre-Release Quality Gate Checklist

Before promoting any release build to production:
- [x] All 25 MVP Tests pass cleanly (`pytest tests/test_mvp_plan.py`).
- [x] All 79 Python pytest tests pass with zero regressions.
- [x] All 21 Playwright E2E, a11y, and API tests pass in Chromium and Mobile emulation.
- [x] All 4 Vitest unit tests pass in under $$200\text{ ms}$$.
- [x] axe-core reports 0 critical WCAG 2.1 AA violations.
- [x] k6 performance benchmark confirms $$p(95) < 500\text{ ms}$$ latency and $$0.00\%$$ error rate under 20 concurrent VUs.
- [x] Git remote repository synchronized and up to date on `main` branch.
