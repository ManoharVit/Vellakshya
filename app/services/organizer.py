"""
PDF page organization service.
Provides page merge, split, rotate, delete, reorder, and extract capabilities.
"""

from __future__ import annotations

import fitz  # PyMuPDF


def merge_pdfs(pdf_list: list[bytes]) -> bytes:
    """
    Merges multiple PDF byte streams into a single composite document.
    """
    merged_doc = fitz.open()
    for pdf_bytes in pdf_list:
        sub_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        merged_doc.insert_pdf(sub_doc)
        sub_doc.close()

    out_bytes = merged_doc.tobytes()
    merged_doc.close()
    return out_bytes


def rotate_pages(pdf_bytes: bytes, pages: list[int] | None = None, angle: int = 90) -> bytes:
    """
    Rotates specified pages (1-indexed) or all pages by angle degrees (90, 180, 270).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    target_pages = set(pages) if pages is not None else set(range(1, total_pages + 1))

    for page_num in range(1, total_pages + 1):
        if page_num in target_pages:
            page = doc[page_num - 1]
            current_rot = page.rotation
            page.set_rotation((current_rot + angle) % 360)

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def parse_page_spec(spec: str, total_pages: int | None = None) -> list[int]:
    """
    Parses comma-separated pages, ranges, and keywords (e.g. '1-5', 'odd', 'even', 'all', '1, 3, 5-7')
    into a sorted unique list of 1-indexed page numbers.
    """
    if not spec:
        return []
    pages: set[int] = set()
    tot = total_pages if (total_pages is not None and total_pages > 0) else 10000
    for part in spec.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token == "odd":
            pages.update(p for p in range(1, tot + 1) if p % 2 != 0)
        elif token == "even":
            pages.update(p for p in range(1, tot + 1) if p % 2 == 0)
        elif token == "all":
            pages.update(range(1, tot + 1))
        elif "-" in token:
            bounds = [b.strip() for b in token.split("-", 1)]
            try:
                start = int(bounds[0])
                end = int(bounds[1])
                if start <= end:
                    pages.update(range(start, end + 1))
                else:
                    pages.update(range(end, start + 1))
            except ValueError:
                continue
        else:
            try:
                pages.add(int(token))
            except ValueError:
                continue
    if total_pages is not None:
        pages = {p for p in pages if 1 <= p <= total_pages}
    return sorted(pages)


def delete_pages(pdf_bytes: bytes, pages_to_delete: list[int]) -> bytes:
    """
    Deletes specified 1-indexed pages from the PDF.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    # Convert 1-indexed to 0-indexed and sort descending to prevent index shifts
    zero_indexed = sorted({p - 1 for p in pages_to_delete if 1 <= p <= len(doc)}, reverse=True)

    if len(zero_indexed) >= len(doc):
        doc.close()
        raise ValueError("Cannot delete all pages from a document. At least one page must remain.")

    for idx in zero_indexed:
        doc.delete_page(idx)

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def reorder_pages(pdf_bytes: bytes, new_order: list[int]) -> bytes:
    """
    Reorders pages based on a 1-indexed list, e.g. [3, 1, 2].
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    new_doc = fitz.open()

    for page_num in new_order:
        if 1 <= page_num <= len(doc):
            new_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)

    out_bytes = new_doc.tobytes()
    doc.close()
    new_doc.close()
    return out_bytes


def extract_pages(pdf_bytes: bytes, pages_to_extract: list[int]) -> bytes:
    """
    Extracts a subset of 1-indexed pages into a fresh PDF document.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    new_doc = fitz.open()

    for page_num in pages_to_extract:
        if 1 <= page_num <= len(doc):
            new_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)

    out_bytes = new_doc.tobytes()
    doc.close()
    new_doc.close()
    return out_bytes


def split_pdf_by_ranges(pdf_bytes: bytes, range_str: str) -> list[tuple[str, bytes]]:
    """
    Splits PDF into multiple files based on comma-separated ranges, e.g., '1-2, 3, 4-5'.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    results: list[tuple[str, bytes]] = []

    chunks = [c.strip() for c in range_str.split(",") if c.strip()]
    for idx, chunk in enumerate(chunks, 1):
        target_pages: list[int] = []
        if "-" in chunk:
            parts = chunk.split("-")
            start = max(1, int(parts[0]))
            end = min(total_pages, int(parts[1]))
            target_pages = list(range(start, end + 1))
        else:
            p = int(chunk)
            if 1 <= p <= total_pages:
                target_pages = [p]

        if target_pages:
            sub_doc = fitz.open()
            for p in target_pages:
                sub_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
            results.append((f"split_part_{idx}_pages_{chunk}.pdf", sub_doc.tobytes()))
            sub_doc.close()

    doc.close()
    return results


def crop_pages(
    pdf_bytes: bytes,
    pages: list[int] | None = None,
    x0: float | None = None,
    y0: float | None = None,
    x1: float | None = None,
    y1: float | None = None,
    margin_top: float = 0.0,
    margin_bottom: float = 0.0,
    margin_left: float = 0.0,
    margin_right: float = 0.0,
) -> bytes:
    """
    Crops specified 1-indexed pages (or all pages) using either an explicit bounding box
    [x0, y0, x1, y1] or margin trim distances (top, bottom, left, right in points).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    target_pages = set(pages) if pages is not None else set(range(1, total_pages + 1))

    for page_num in range(1, total_pages + 1):
        if page_num in target_pages:
            page = doc[page_num - 1]
            orig_rect = page.rect
            if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
                # Direct bounding box crop
                new_rect = fitz.Rect(
                    max(orig_rect.x0, min(x0, x1)),
                    max(orig_rect.y0, min(y0, y1)),
                    min(orig_rect.x1, max(x0, x1)),
                    min(orig_rect.y1, max(y0, y1)),
                )
            else:
                # Margin-based trim
                new_rect = fitz.Rect(
                    orig_rect.x0 + margin_left,
                    orig_rect.y0 + margin_top,
                    orig_rect.x1 - margin_right,
                    orig_rect.y1 - margin_bottom,
                )
            # Ensure valid rectangle dimensions
            if new_rect.width > 10 and new_rect.height > 10:
                page.set_cropbox(new_rect)

    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes
