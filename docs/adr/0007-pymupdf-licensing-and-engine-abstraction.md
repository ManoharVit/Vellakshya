# ADR 0007: PyMuPDF Dual-Licensing Compliance & Multi-Engine Abstraction

## Status
Accepted

## Date
2026-10-29

## Context
Vellakshya relies on **PyMuPDF (`fitz` v1.28.x)** for high-fidelity fixed-layout HTML generation, vector graphics extraction (`_drawings_to_svg`), embedded font stream extraction (`_extract_embedded_fonts`), text redaction, watermarking, and coordinate geometry.

PyMuPDF is maintained by Artifex Software and is dual-licensed under:
1. **GNU Affero General Public License v3.0 (AGPLv3)** (Free Open Source)
2. **Artifex Commercial License** (Proprietary / Closed-Source SaaS)

Under AGPLv3 Section 13 (Remote Network Interaction), any user interacting with the software remotely through a computer network has the legal right to receive the complete corresponding source code under the AGPLv3 license. If Vellakshya is deployed as a hosted SaaS or multi-tenant cloud service without disclosing the surrounding backend codebase, AGPLv3 network copyleft obligations are triggered, presenting a legal and licensing risk for commercial proprietary deployments.

## Decision
We resolve the PyMuPDF licensing posture through a three-tier strategy:

1. **Open-Source Community Edition (Current Repository)**:
   - Vellakshya remains 100% open-source under AGPLv3-compatible terms on [GitHub](https://github.com/ManoharVit/Vellakshya).
   - Corresponding source code is continuously provided to all remote network users, fully satisfying AGPLv3 Section 13 requirements.
   - An explicit license disclosure is declared in the root documentation and dependency manifest.

2. **Enterprise & Closed-Source SaaS Lane**:
   - For commercial distributions or private hosted deployments that cannot satisfy AGPLv3 copyleft terms, operators must acquire an **Artifex Commercial License** for PyMuPDF.

3. **Pluggable Engine Abstraction Layer**:
   - To avoid vendor and licensing lock-in, document conversion workflows are decoupled behind an engine interface:
     - **Primary Tier**: PyMuPDF 1.28.x (High-fidelity fixed HTML, SVG extraction, embedded fonts).
     - **Permissive Modern Tier**: **Docling (MIT)** for layout analysis, table parsing, and semantic Markdown/HTML generation.
     - **Fallback Permissive PDF Manipulation**: **pypdf (BSD-3-Clause)** and **pdfminer.six (MIT)** for non-copyleft page management.
     - **In-Browser Client Tier**: **@cantoo/pdf-lib (MIT)** for zero-backend client-side execution on edge CDN runtimes.

## Consequences
- **Positive**: Complete legal clarity across both open-source and commercial deployments. No risk of accidental AGPL license contamination for proprietary hosted instances.
- **Positive**: Maintains PyMuPDF's performance and font/SVG synthesis as a key competitive differentiator while establishing a migration path to Docling (MIT).
- **Negative**: Commercial SaaS operators must either maintain AGPL open-source compliance or purchase a commercial license from Artifex.
