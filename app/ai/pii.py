"""
Local-First PII Detection and Cryptographic Redaction Service.
Implements detection for Indian statutory IDs, financial identifiers, and universal contact info.
Executes complete physical scrubbing and multi-pass byte sanitization via PyMuPDF.
"""

from __future__ import annotations

import io
import re
import uuid

import fitz

from app.ai.models import PIIEntityMatch, PIIScanResponse

# High-precision statutory and personal recognizers
PII_PATTERNS: dict[str, tuple[str, float]] = {
    # India Statutory Identifiers
    "IN_PAN": (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", 0.95),
    "IN_AADHAAR": (r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b", 0.90),
    "IN_PASSPORT": (r"\b[A-PR-WYa-pr-wy][1-9]\d\s?\d{4}[1-9]\b", 0.85),
    "IN_VOTER": (r"\b[A-Z]{3}[0-9]{7}\b", 0.85),
    "IN_VEHICLE_REGISTRATION": (r"\b[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}\b", 0.85),
    # International & Financial Identifiers
    "EMAIL_ADDRESS": (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", 0.98),
    "PHONE_NUMBER": (r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", 0.85),
    "CREDIT_CARD": (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", 0.92),
    "US_SSN": (r"\b\d{3}-\d{2}-\d{4}\b", 0.90),
}


def scan_pdf_for_pii(pdf_bytes: bytes, document_id: str) -> PIIScanResponse:
    """
    Scans PDF text page-by-page locally using statutory pattern recognizers.
    Calculates exact bounding box coordinates [x0, y0, x1, y1] for every match.
    Zero document bytes leave the local server memory.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matches: list[PIIEntityMatch] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        page_text = page.get_text("text")

        for entity_type, (pattern, confidence) in PII_PATTERNS.items():
            for match in re.finditer(pattern, page_text):
                matched_str = match.group(0).strip()
                if not matched_str:
                    continue

                # 1. Search with page.search_for
                rects = page.search_for(matched_str)
                bbox_list: list[list[float]] = []

                if rects:
                    for r in rects:
                        bbox_list.append(
                            [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]
                        )
                else:
                    # 2. Fallback to get_text('words') for hyphenated or wrapped words
                    words = page.get_text("words")
                    for w in words:
                        if matched_str in w[4]:
                            bbox_list.append(
                                [round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2)]
                            )

                if bbox_list:
                    match_id = f"pii_{uuid.uuid4().hex[:12]}"
                    matches.append(
                        PIIEntityMatch(
                            id=match_id,
                            entity_type=entity_type,
                            matched_text=matched_str,
                            confidence=confidence,
                            page=page_num,
                            rects=bbox_list,
                        )
                    )

    doc.close()
    return PIIScanResponse(
        document_id=document_id,
        total_detected=len(matches),
        entities=matches,
    )


def apply_physical_redactions(
    pdf_bytes: bytes,
    approved_entities: list[PIIEntityMatch],
) -> bytes:
    """
    Applies permanent physical redaction and byte scrubbing to all target coordinates.
    Configures image, graphic, and text blanking explicitly.
    Applies doc.scrub() and saves with garbage=4 and deflate=True.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Group approved rectangles by page number
    page_rects: dict[int, list[list[float]]] = {}
    for entity in approved_entities:
        p = entity.page
        if p not in page_rects:
            page_rects[p] = []
        page_rects[p].extend(entity.rects)

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1

        rects = page_rects.get(page_num, [])
        for r in rects:
            rect_obj = fitz.Rect(r[0], r[1], r[2], r[3])
            page.add_redact_annot(rect_obj, fill=(0, 0, 0))

        if rects:
            # Explicitly set image, graphics, and text removal flags
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )

    # Scrub all metadata, XML schemas, hidden annotations, and embedded attachments
    doc.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        metadata=True,
    )

    out_buffer = io.BytesIO()
    doc.save(out_buffer, garbage=4, deflate=True)
    doc.close()

    return out_buffer.getvalue()
