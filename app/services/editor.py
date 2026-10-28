"""
PDF Content Editor service.
Handles watermarking, pagination/Bates numbering, headers/footers, text replacement, text block insertion, and annotations.
"""

from __future__ import annotations

from typing import Optional

import fitz  # PyMuPDF


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    """Converts #RRGGBB or #RGB to (r, g, b) normalized 0.0 to 1.0."""
    clean = hex_str.lstrip("#").strip()
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    if len(clean) != 6:
        return (0.0, 0.0, 0.0)
    try:
        return (
            int(clean[0:2], 16) / 255.0,
            int(clean[2:4], 16) / 255.0,
            int(clean[4:6], 16) / 255.0,
        )
    except ValueError:
        return (0.0, 0.0, 0.0)


def add_text_watermark(
    pdf_bytes: bytes,
    text: str = "CONFIDENTIAL",
    opacity: float = 0.25,
    font_size: int = 50,
    angle: int = 45,
    color: tuple[float, float, float] = (0.7, 0.2, 0.2),
) -> bytes:
    """
    Applies a semi-transparent diagonal text watermark across every page.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        rect = page.rect
        center_x = rect.width / 2
        center_y = rect.height / 2
        pt = fitz.Point(center_x - (len(text) * font_size * 0.22), center_y)

        # Use morph for arbitrary rotation angles
        if angle % 90 == 0:
            page.insert_text(
                pt,
                text,
                fontsize=font_size,
                rotate=angle % 360,
                color=color,
                fill_opacity=opacity,
            )
        else:
            page.insert_text(
                pt,
                text,
                fontsize=font_size,
                morph=(pt, fitz.Matrix(angle)),
                color=color,
                fill_opacity=opacity,
            )

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def add_page_numbers(
    pdf_bytes: bytes,
    position: str = "bottom-center",
    format_pattern: str = "Page {page} of {total}",
    pattern: str | None = None,
    font_size: int = 10,
    margin_bottom: int = 30,
) -> bytes:
    """
    Adds dynamic page numbers / Bates numbering to all pages.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    pat = pattern if pattern is not None else format_pattern

    for idx, page in enumerate(doc, 1):
        rect = page.rect
        label = pat.format(page=idx, total=total_pages)
        text_len = len(label) * font_size * 0.5

        if position == "bottom-center":
            pt = fitz.Point((rect.width - text_len) / 2, rect.height - margin_bottom)
        elif position == "bottom-right":
            pt = fitz.Point(rect.width - text_len - 40, rect.height - margin_bottom)
        elif position == "top-right":
            pt = fitz.Point(rect.width - text_len - 40, 40)
        else:
            pt = fitz.Point(40, rect.height - margin_bottom)

        page.insert_text(pt, label, fontsize=font_size, color=(0.3, 0.3, 0.3))

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def add_header_footer(
    pdf_bytes: bytes,
    header_text: str = "",
    footer_text: str = "",
    font_size: int = 9,
) -> bytes:
    """
    Inserts running header and footer text across all pages.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        rect = page.rect
        if header_text:
            page.insert_text(
                fitz.Point(40, 30), header_text, fontsize=font_size, color=(0.4, 0.4, 0.4)
            )
        if footer_text:
            page.insert_text(
                fitz.Point(40, rect.height - 30),
                footer_text,
                fontsize=font_size,
                color=(0.4, 0.4, 0.4),
            )

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def highlight_search_terms(
    pdf_bytes: bytes,
    terms: list[str],
    color: tuple[float, float, float] = (1.0, 1.0, 0.0),
) -> bytes:
    """
    Finds and adds visual highlight annotations for specified keywords or search terms.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        for term in terms:
            if not term.strip():
                continue
            quads = page.search_for(term.strip(), quads=True)
            for quad in quads:
                annot = page.add_highlight_annot(quad)
                annot.set_colors(stroke=color)
                annot.update()

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def _extract_page_spans(page: fitz.Page) -> list[dict]:
    """
    Extracts all text spans on a page with their bounding box,
    font, size, color, flags, and typographical baseline origin.
    """
    spans = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                spans.append(span)
    return spans


def _find_matching_span(r: fitz.Rect, spans: list[dict]) -> Optional[dict]:
    """
    Finds the text span on the page that best matches or intersects the target rectangle r.
    """
    if not spans:
        return None
    best_span = None
    max_overlap = -1.0
    for s in spans:
        s_rect = fitz.Rect(s["bbox"])
        intersect = r & s_rect
        if intersect.is_valid and intersect.get_area() > max_overlap:
            max_overlap = intersect.get_area()
            best_span = s

    if best_span is not None and max_overlap > 0:
        return best_span

    # Fallback to closest span by center distance
    min_dist = float("inf")
    c_rx = (r.x0 + r.x1) / 2.0
    c_ry = (r.y0 + r.y1) / 2.0
    for s in spans:
        s_rect = fitz.Rect(s["bbox"])
        c_sx = (s_rect.x0 + s_rect.x1) / 2.0
        c_sy = (s_rect.y0 + s_rect.y1) / 2.0
        dist = (c_rx - c_sx) ** 2 + (c_ry - c_sy) ** 2
        if dist < min_dist:
            min_dist = dist
            best_span = s

    return best_span or spans[0]


def _map_to_standard_pdf_font(font_name: str, flags: int = 0) -> str:
    """
    Maps an arbitrary detected PDF/system font name and style flags
    to the optimal matching standard PDF font variant.
    """
    fn = (font_name or "").lower()
    is_bold = bool(flags & 16) or any(
        k in fn for k in ("bold", "black", "heavy", "medium", "semibold", "bld")
    )
    is_italic = bool(flags & 2) or any(k in fn for k in ("italic", "oblique", "ital", "slanted"))

    if any(k in fn for k in ("courier", "mono", "consolas", "menlo", "code", "fixed")):
        if is_bold and is_italic:
            return "courier-boldoblique"
        if is_bold:
            return "courier-bold"
        if is_italic:
            return "courier-oblique"
        return "courier"

    if any(
        k in fn
        for k in ("times", "serif", "georgia", "cambria", "garamond", "palatino", "minion", "roman")
    ):
        if is_bold and is_italic:
            return "times-bolditalic"
        if is_bold:
            return "times-bold"
        if is_italic:
            return "times-italic"
        return "times-roman"

    if "symbol" in fn:
        return "symb"
    if "dingbat" in fn or "wingding" in fn:
        return "zadb"

    if is_bold and is_italic:
        return "hebi"
    if is_bold:
        return "hebo"
    if is_italic:
        return "heit"
    return "helv"


def _select_target_rect(
    rects: list[fitz.Rect],
    target_rect: Optional[list[float]] = None,
    occurrence: Optional[int] = None,
) -> Optional[fitz.Rect]:
    """
    Selects a single target rectangle from a list of search matches based on
    either an explicit bounding box or a 0-indexed occurrence position.
    """
    if not rects:
        return None

    if target_rect and len(target_rect) == 4:
        target_box = fitz.Rect(target_rect)
        # First priority: find rectangle with greatest valid intersection area
        best_rect = None
        max_overlap = -1.0
        for r in rects:
            intersect = r & target_box
            if intersect.is_valid and intersect.get_area() > max_overlap:
                max_overlap = intersect.get_area()
                best_rect = r
        if best_rect is not None and max_overlap > 0:
            return best_rect

        # Second priority: minimum distance between bounding box centers
        min_dist = float("inf")
        c_target_x = (target_box.x0 + target_box.x1) / 2.0
        c_target_y = (target_box.y0 + target_box.y1) / 2.0
        for r in rects:
            cx = (r.x0 + r.x1) / 2.0
            cy = (r.y0 + r.y1) / 2.0
            dist = (cx - c_target_x) ** 2 + (cy - c_target_y) ** 2
            if dist < min_dist:
                min_dist = dist
                best_rect = r
        return best_rect

    if occurrence is not None and 0 <= occurrence < len(rects):
        return rects[occurrence]

    return rects[0]


def replace_text_batch(
    pdf_bytes: bytes,
    rules: list[dict],
    fill_bg_color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pages: Optional[list[int]] = None,
    preserve_style: bool = True,
) -> tuple[bytes, int]:
    """
    Applies text search & replace rules on the document.
    Automatically detects and preserves the exact font family, style (bold/italic),
    font size, color, and typographical baseline from the original text being replaced.
    Supports either targeted single-occurrence replacement (single=True with optional
    occurrence index or bounding box rect) or full document/page replacement (single=False).
    Each rule is a dict:
      {
        "search_text": str,
        "replacement_text": str,
        "font_size": Optional[int],
        "color": Optional[tuple],
        "font_name": Optional[str],
        "single": Optional[bool],
        "occurrence": Optional[int],
        "rect": Optional[list[float]],
        "page_num": Optional[int],
        "preserve_style": Optional[bool],
        "override_color": Optional[bool],
        "override_size": Optional[bool]
      }
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_replaced = 0
    target_pages = set(pages) if pages is not None else set(range(1, len(doc) + 1))

    for rule in rules:
        clean_search = (rule.get("search_text") or rule.get("search") or "").strip()
        if not clean_search:
            continue
        replacement = (
            rule.get("replacement_text") if "replacement_text" in rule else rule.get("replace", "")
        )
        font_size = rule.get("font_size")
        color = rule.get("color")
        font_name_override = rule.get("font_name")
        is_single = bool(rule.get("single", False))
        rule_occ = rule.get("occurrence")
        rule_rect = rule.get("rect")
        rule_page = rule.get("page_num") or rule.get("page")
        rule_preserve_style = bool(rule.get("preserve_style", preserve_style))
        override_color = bool(rule.get("override_color", False))
        override_size = bool(rule.get("override_size", False))

        rule_target_pages = target_pages
        if rule_page is not None and 1 <= rule_page <= len(doc):
            rule_target_pages = {rule_page}

        for idx, page in enumerate(doc, 1):
            if idx not in rule_target_pages:
                continue
            rects = page.search_for(clean_search)
            if not rects:
                continue

            if is_single:
                target_r = _select_target_rect(rects, target_rect=rule_rect, occurrence=rule_occ)
                rects_to_process = [target_r] if target_r else []
            else:
                rects_to_process = rects

            if not rects_to_process:
                continue

            # Extract untouched page text structure BEFORE applying redactions
            spans = _extract_page_spans(page)

            # Build replacement execution plan matching original font, size, color & baseline
            plan = []
            for r in rects_to_process:
                best_span = _find_matching_span(r, spans) if spans else None

                # 1. Resolve Font Family & Style
                if best_span and (rule_preserve_style or not font_name_override):
                    final_font = _map_to_standard_pdf_font(
                        best_span.get("font", ""), best_span.get("flags", 0)
                    )
                elif font_name_override:
                    final_font = _map_to_standard_pdf_font(font_name_override)
                else:
                    final_font = "helv"

                # 2. Resolve Font Size
                if override_size and font_size is not None and font_size > 0:
                    final_fs = float(font_size)
                elif (
                    best_span
                    and best_span.get("size")
                    and (rule_preserve_style or font_size is None or font_size <= 0)
                ):
                    final_fs = float(best_span["size"])
                elif font_size is not None and font_size > 0:
                    final_fs = float(font_size)
                else:
                    final_fs = max(8.0, r.height * 0.85)

                # 3. Resolve Font Color
                if override_color and color is not None:
                    final_color = color
                elif (
                    best_span
                    and (rule_preserve_style or color is None)
                    and best_span.get("color") is not None
                ):
                    c_int = best_span["color"]
                    r_col = ((c_int >> 16) & 255) / 255.0
                    g_col = ((c_int >> 8) & 255) / 255.0
                    b_col = (c_int & 255) / 255.0
                    final_color = (round(r_col, 4), round(g_col, 4), round(b_col, 4))
                elif color is not None:
                    final_color = color
                else:
                    final_color = (0.0, 0.0, 0.0)

                # 4. Resolve Typographical Baseline Origin
                origin = best_span.get("origin") if best_span else None
                if origin and (r.y0 - 2.0 <= origin[1] <= r.y1 + 4.0):
                    insert_pt = fitz.Point(r.x0, origin[1])
                else:
                    insert_pt = fitz.Point(r.x0, r.y1 - (r.height * 0.15))

                plan.append((r, final_font, final_fs, final_color, insert_pt))

            # Apply redactions to erase original glyphs cleanly
            for r in rects_to_process:
                page.add_redact_annot(r, fill=fill_bg_color)
                total_replaced += 1

            page.apply_redactions()

            # Insert replacement text with identical font, size, color, and baseline
            if replacement:
                for r, f_font, f_size, f_col, pt in plan:
                    page.insert_text(pt, replacement, fontname=f_font, fontsize=f_size, color=f_col)

            if is_single:
                break

    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes, total_replaced


def replace_text(
    pdf_bytes: bytes,
    search_text: str,
    replacement_text: str,
    font_size: Optional[int] = None,
    color: Optional[tuple[float, float, float]] = None,
    fill_bg_color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pages: Optional[list[int]] = None,
    single: bool = False,
    occurrence: Optional[int] = None,
    rect: Optional[list[float]] = None,
    page_num: Optional[int] = None,
    preserve_style: bool = True,
    override_color: bool = False,
    override_size: bool = False,
) -> tuple[bytes, int]:
    """
    Finds occurrences of search_text, whites out the existing text glyphs,
    and inserts the replacement_text at the matching positions.
    When single=True, replaces only one target occurrence (specified by rect or occurrence index).
    When single=False, replaces all occurrences.
    Preserves exact original font family, bold/italic style, font size, color and baseline.
    Returns (modified_pdf_bytes, replacement_count).
    """
    return replace_text_batch(
        pdf_bytes=pdf_bytes,
        rules=[
            {
                "search_text": search_text,
                "replacement_text": replacement_text,
                "font_size": font_size,
                "color": color,
                "single": single,
                "occurrence": occurrence,
                "rect": rect,
                "page_num": page_num,
                "preserve_style": preserve_style,
                "override_color": override_color,
                "override_size": override_size,
            }
        ],
        fill_bg_color=fill_bg_color,
        pages=pages,
        preserve_style=preserve_style,
    )


def insert_text_block(
    pdf_bytes: bytes,
    page_num: int,
    text: str,
    x: float,
    y: float,
    font_size: int = 12,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bg_fill_color: Optional[tuple[float, float, float]] = None,
) -> bytes:
    """
    Inserts a custom text block at a specified (x, y) coordinate on page_num (1-indexed).
    Optionally draws a clean background fill rectangle behind the text.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if 1 <= page_num <= len(doc):
        page = doc[page_num - 1]
        pt = fitz.Point(x, y)

        # If background fill requested, draw a clean background box first
        if bg_fill_color is not None:
            text_lines = text.split("\n")
            max_line_len = max(len(l) for l in text_lines) if text_lines else 1
            box_w = max_line_len * font_size * 0.65 + 10
            box_h = len(text_lines) * font_size * 1.35 + 6
            bg_rect = fitz.Rect(x - 4, y - font_size - 2, x + box_w, y - font_size + box_h)
            page.draw_rect(bg_rect, color=bg_fill_color, fill=bg_fill_color)

        page.insert_text(pt, text, fontsize=font_size, color=color)

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes


def whiteout_area(
    pdf_bytes: bytes,
    page_num: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fill_color: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bytes:
    """
    Whites out / erases a rectangular area [x0, y0, x1, y1] on page_num.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if 1 <= page_num <= len(doc):
        page = doc[page_num - 1]
        r = fitz.Rect(x0, y0, x1, y1)
        page.add_redact_annot(r, fill=fill_color)
        page.apply_redactions()

    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes
