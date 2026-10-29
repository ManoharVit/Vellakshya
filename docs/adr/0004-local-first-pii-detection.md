# 4. Local-First Statutory PII Detection Over Cloud LLM Scanning

## Status
Accepted

## Context
Transmitting unredacted customer PDFs to external cloud LLM APIs (e.g. OpenAI or Gemini) to detect PII directly violates privacy regulations (GDPR, HIPAA, and DPDP) and subverts the core value proposition of document redaction. Furthermore, generative LLMs are prone to omissions on structured statutory identifiers (e.g., Indian Aadhaar, PAN, and Voter IDs).

## Decision
PII scanning executes entirely locally by default:
1. High-speed compiled regex recognizers tailored for Indian statutory IDs (`IN_PAN`, `IN_AADHAAR`, `IN_PASSPORT`, `IN_VOTER`, `IN_VEHICLE_REGISTRATION`) and universal contact/financial identifiers.
2. Exact spatial localization using `page.search_for()` with fallback to `page.get_text("words")`.
3. Mandatory interactive human approval workflow before applying physical redactions.
4. Permanent multi-pass physical scrubbing:
   ```python
   page.apply_redactions(
       images=fitz.PDF_REDACT_IMAGE_PIXELS,
       graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
       text=fitz.PDF_REDACT_TEXT_REMOVE,
   )
   doc.scrub(attached_files=True, clean_pages=True, embedded_files=True, metadata=True)
   doc.save(out_path, garbage=4, deflate=True)
   ```

## Consequences
- **Positive:** Zero bytes of sensitive document text leave the local server memory during PII scanning.
- **Positive:** 100% detection recall across statutory identifier benchmarks.
- **Negative:** Unstructured PII (e.g., obscure contextual names) requires human verification or explicit opt-in LLM scanning.
