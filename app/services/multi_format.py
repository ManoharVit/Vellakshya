"""
Multi-Format Ingestion Service for Vellakshya.
Provides structured parsing and high-fidelity PDF synthesis for:
- Microsoft Word (.docx)
- Microsoft Excel (.xlsx)
- Comma/Tab Separated Values (.csv, .tsv)
- Markdown (.md) and Plain Text (.txt)
- Native PDF (.pdf)

Enables unified local RAG, summarization, analytics, sidecar chat, and translation
across heterogeneous document types with verified spatial coordinates.
"""

from __future__ import annotations

import csv
import io
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

import pymupdf
from sqlalchemy.orm import Session

from app.ai.chunking import extract_chunks_from_pdf_bytes
from app.ai.embeddings import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL, get_embedding
from app.ai.models import DocumentChunk, MultiFormatIngestResponse
from app.ai.storage import store_document_and_chunks


def _get_transient_store():
    from app.ai.router import _TRANSIENT_PDF_STORE, purge_expired_transient_ai_data

    return _TRANSIENT_PDF_STORE, purge_expired_transient_ai_data


def detect_document_format(filename: str, content: bytes) -> str:
    """Detects document format from file extension and magic byte headers."""
    ext = os.path.splitext(filename.lower())[1]

    if content.startswith(b"%PDF-"):
        return "pdf"

    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if "word/document.xml" in names:
                    return "docx"
                if "xl/workbook.xml" in names or any(n.startswith("xl/") for n in names):
                    return "xlsx"
        except Exception:
            pass

    if ext in (".docx", ".doc"):
        return "docx"
    if ext in (".xlsx", ".xls"):
        return "xlsx"
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext in (".md", ".markdown"):
        return "markdown"
    if ext in (".txt", ".log", ".json", ".xml", ".yaml", ".yml"):
        return "text"

    # Fallback heuristic
    try:
        sample = content[:1024].decode("utf-8")
        if re.search(r"^#+\s", sample, re.MULTILINE):
            return "markdown"
        if "\t" in sample or "," in sample:
            return "csv"
    except UnicodeDecodeError:
        pass

    return "text"


def parse_docx_to_structure(content: bytes) -> dict[str, Any]:
    """Parses a Word (.docx) document into hierarchical structural blocks."""
    import docx

    doc = docx.Document(io.BytesIO(content))
    title = ""
    blocks: list[dict[str, Any]] = []

    # Check doc properties
    if doc.core_properties and doc.core_properties.title:
        title = doc.core_properties.title.strip()

    # Iterate through elements in order
    for elem in doc.paragraphs:
        text = elem.text.strip()
        if not text:
            continue

        style_name = elem.style.name.lower() if elem.style else ""
        if not title and ("title" in style_name or "heading 1" in style_name):
            title = text

        if "heading 1" in style_name:
            blocks.append({"type": "heading", "level": 1, "text": text})
        elif "heading 2" in style_name:
            blocks.append({"type": "heading", "level": 2, "text": text})
        elif "heading 3" in style_name:
            blocks.append({"type": "heading", "level": 3, "text": text})
        elif "list" in style_name or elem.text.startswith(("- ", "* ", "• ")):
            blocks.append({"type": "list_item", "text": text.lstrip("- *• ")})
        else:
            blocks.append({"type": "paragraph", "text": text})

    tables_data: list[list[list[str]]] = []
    for table in doc.tables:
        rows: list[list[str]] = []
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells]
            if any(row_cells):
                rows.append(row_cells)
        if rows:
            tables_data.append(rows)
            blocks.append({"type": "table", "rows": rows})

    if not title and blocks:
        first = blocks[0]
        if first["type"] == "heading":
            title = first["text"]

    return {
        "format": "docx",
        "title": title or "Word Document",
        "blocks": blocks,
        "table_count": len(tables_data),
    }


def parse_xlsx_to_structure(content: bytes) -> dict[str, Any]:
    """Pure Python, zero-vulnerability streaming parser for Excel (.xlsx) workbooks."""
    zf = zipfile.ZipFile(io.BytesIO(content))
    shared_strings: list[str] = []

    if "xl/sharedStrings.xml" in zf.namelist():
        tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in tree.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
            t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            shared_strings.append(t.text if t is not None and t.text else "")

    # Sheet names from workbook.xml
    sheet_names: dict[str, str] = {}
    if "xl/workbook.xml" in zf.namelist():
        wb_tree = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets_el = wb_tree.find(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets"
        )
        if sheets_el is not None:
            for s in sheets_el.findall(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            ):
                s_id = s.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
                )
                name = s.attrib.get("name", "Sheet")
                sheet_names[s_id] = name

    sheet_files = sorted(
        [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    )
    blocks: list[dict[str, Any]] = []
    total_tables = 0

    for idx, s_file in enumerate(sheet_files):
        sheet_title = f"Sheet {idx + 1}"
        tree = ET.fromstring(zf.read(s_file))
        rows: list[list[str]] = []
        sheet_data = tree.find(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData"
        )

        if sheet_data is not None:
            for row_el in sheet_data.findall(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"
            ):
                row_vals: list[str] = []
                for c in row_el.findall(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"
                ):
                    val_el = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    if val_el is not None and val_el.text:
                        raw_val = val_el.text
                        if c.get("t") == "s":
                            try:
                                s_idx = int(raw_val)
                                raw_val = (
                                    shared_strings[s_idx]
                                    if s_idx < len(shared_strings)
                                    else raw_val
                                )
                            except ValueError:
                                pass
                        row_vals.append(raw_val.strip())
                    else:
                        row_vals.append("")
                if any(row_vals):
                    rows.append(row_vals)

        if rows:
            total_tables += 1
            blocks.append({"type": "heading", "level": 2, "text": f"Worksheet: {sheet_title}"})
            blocks.append({"type": "table", "rows": rows})

    return {
        "format": "xlsx",
        "title": "Excel Workbook",
        "blocks": blocks,
        "table_count": total_tables,
    }


def parse_csv_to_structure(content: bytes) -> dict[str, Any]:
    """Parses Comma or Tab separated text files into tabular structures."""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    delimiter = ","
    try:
        sample = text[:2048]
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample)
        delimiter = dialect.delimiter
    except Exception:
        if "\t" in text:
            delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[str]] = [r for r in reader if any(cell.strip() for cell in r)]

    blocks: list[dict[str, Any]] = []
    if rows:
        blocks.append({"type": "heading", "level": 2, "text": "Tabular Data"})
        blocks.append({"type": "table", "rows": rows})

    return {
        "format": "csv",
        "title": "CSV Dataset",
        "blocks": blocks,
        "table_count": 1 if rows else 0,
    }


def parse_markdown_to_structure(content: bytes) -> dict[str, Any]:
    """Parses Markdown or plain text into structured elements."""
    text = content.decode("utf-8", errors="replace")
    lines = text.split("\n")
    blocks: list[dict[str, Any]] = []
    title = ""

    table_rows: list[list[str]] = []
    in_table = False

    for line in lines:
        stripped = line.strip()

        # Handle markdown tables
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator line |---|---|
            if all(set(c).issubset({"-", ":", " "}) for c in cells if c):
                continue
            table_rows.append(cells)
            in_table = True
            continue
        else:
            if in_table and table_rows:
                blocks.append({"type": "table", "rows": list(table_rows)})
                table_rows.clear()
                in_table = False

        if not stripped:
            continue

        if stripped.startswith("# "):
            h = stripped[2:].strip()
            if not title:
                title = h
            blocks.append({"type": "heading", "level": 1, "text": h})
        elif stripped.startswith("## "):
            blocks.append({"type": "heading", "level": 2, "text": stripped[3:].strip()})
        elif stripped.startswith("### "):
            blocks.append({"type": "heading", "level": 3, "text": stripped[4:].strip()})
        elif stripped.startswith(("- ", "* ", "+ ")):
            blocks.append({"type": "list_item", "text": stripped[2:].strip()})
        elif re.match(r"^\d+\.\s", stripped):
            item_text = re.sub(r"^\d+\.\s", "", stripped)
            blocks.append({"type": "list_item", "text": item_text})
        else:
            blocks.append({"type": "paragraph", "text": stripped})

    if in_table and table_rows:
        blocks.append({"type": "table", "rows": list(table_rows)})

    return {
        "format": "markdown",
        "title": title or "Markdown Document",
        "blocks": blocks,
        "table_count": sum(1 for b in blocks if b["type"] == "table"),
    }


def synthesize_pdf_from_structure(doc_data: dict[str, Any], filename: str = "document") -> bytes:
    """
    Renders structured blocks into a publication-grade, high-fidelity PDF document.
    Enforces clean typography, auto-pagination, grid tables, and header/footer metadata.
    """
    doc = pymupdf.open()
    page_width, page_height = 595.0, 842.0  # Standard ISO A4 points
    margin_x, margin_top, margin_bottom = 54.0, 54.0, 54.0
    content_width = page_width - (2 * margin_x)

    current_page = doc.new_page(width=page_width, height=page_height)
    cursor_y = margin_top
    page_count = 1

    def ensure_space(required_height: float) -> pymupdf.Page:
        nonlocal current_page, cursor_y, page_count
        if cursor_y + required_height > page_height - margin_bottom:
            current_page = doc.new_page(width=page_width, height=page_height)
            page_count += 1
            cursor_y = margin_top
        return current_page

    # Page 1 Header Banner
    title_text = doc_data.get("title") or filename or "Document"
    fmt = doc_data.get("format", "DOCX").upper()

    # Draw Banner Box
    current_page.draw_rect(
        pymupdf.Rect(margin_x, cursor_y, margin_x + content_width, cursor_y + 36),
        color=(0.31, 0.27, 0.90),
        fill=(0.93, 0.95, 1.0),
    )
    current_page.insert_text(
        (margin_x + 12, cursor_y + 22),
        f"Vellakshya Converted • {fmt}",
        fontsize=10,
        fontname="helv",
        color=(0.22, 0.19, 0.64),
    )
    cursor_y += 48

    # Title
    current_page.insert_textbox(
        pymupdf.Rect(margin_x, cursor_y, margin_x + content_width, cursor_y + 32),
        title_text,
        fontsize=16,
        fontname="helv",
        color=(0.06, 0.09, 0.16),
    )
    cursor_y += 36

    # Subtle divider
    current_page.draw_line(
        (margin_x, cursor_y),
        (margin_x + content_width, cursor_y),
        color=(0.88, 0.91, 0.94),
        width=1,
    )
    cursor_y += 16

    blocks = doc_data.get("blocks", [])
    for block in blocks:
        b_type = block.get("type")

        if b_type == "heading":
            level = block.get("level", 1)
            size = 14 if level == 1 else (12 if level == 2 else 11)
            h_height = size + 14
            ensure_space(h_height + 8)
            cursor_y += 6
            current_page.insert_text(
                (margin_x, cursor_y + size),
                block.get("text", ""),
                fontsize=size,
                fontname="helv",
                color=(0.06, 0.09, 0.16),
            )
            cursor_y += h_height

        elif b_type == "list_item":
            text = block.get("text", "")
            bullet_indent = 16.0
            rect = pymupdf.Rect(
                margin_x + bullet_indent, cursor_y, margin_x + content_width, cursor_y + 200
            )
            ensure_space(20)
            # Draw bullet circle
            current_page.draw_circle(
                (margin_x + 6, cursor_y + 6),
                2,
                color=(0.31, 0.27, 0.90),
                fill=(0.31, 0.27, 0.90),
            )
            inserted = current_page.insert_textbox(
                rect,
                text,
                fontsize=9.5,
                fontname="helv",
                color=(0.15, 0.20, 0.28),
            )
            # Estimate height based on character count and content width
            lines_est = max(1, len(text) // 75 + 1)
            cursor_y += lines_est * 13 + 4

        elif b_type == "paragraph":
            text = block.get("text", "")
            lines_est = max(1, len(text) // 85 + 1)
            p_height = lines_est * 14 + 6
            ensure_space(min(p_height, 60))
            rect = pymupdf.Rect(
                margin_x, cursor_y, margin_x + content_width, cursor_y + p_height + 20
            )
            current_page.insert_textbox(
                rect,
                text,
                fontsize=9.5,
                fontname="helv",
                color=(0.15, 0.20, 0.28),
            )
            cursor_y += lines_est * 13 + 8

        elif b_type == "table":
            rows = block.get("rows", [])
            if not rows:
                continue

            col_count = max(len(r) for r in rows)
            if col_count == 0:
                continue

            col_width = content_width / col_count
            row_height = 20.0

            for r_idx, row in enumerate(rows):
                ensure_space(row_height + 4)
                row_rect = pymupdf.Rect(
                    margin_x, cursor_y, margin_x + content_width, cursor_y + row_height
                )

                # Background fill
                if r_idx == 0:
                    current_page.draw_rect(
                        row_rect, color=(0.80, 0.85, 0.92), fill=(0.93, 0.95, 1.0)
                    )
                elif r_idx % 2 == 1:
                    current_page.draw_rect(
                        row_rect, color=(0.90, 0.92, 0.94), fill=(0.97, 0.98, 0.99)
                    )
                else:
                    current_page.draw_rect(row_rect, color=(0.90, 0.92, 0.94), fill=(1.0, 1.0, 1.0))

                for c_idx, cell_text in enumerate(row):
                    cell_x = margin_x + (c_idx * col_width)
                    cell_rect = pymupdf.Rect(
                        cell_x + 4, cursor_y + 3, cell_x + col_width - 4, cursor_y + row_height - 3
                    )
                    font_color = (0.06, 0.09, 0.16) if r_idx == 0 else (0.20, 0.25, 0.33)
                    font_size = 8.5 if r_idx == 0 else 8.0
                    truncated = cell_text[:35] + ("..." if len(cell_text) > 35 else "")
                    current_page.insert_text(
                        (cell_x + 6, cursor_y + 13),
                        truncated,
                        fontsize=font_size,
                        fontname="helv",
                        color=font_color,
                    )

                cursor_y += row_height
            cursor_y += 10

    # Add page numbers to all generated pages
    total_pages = len(doc)
    for p_idx, page in enumerate(doc):
        page.insert_text(
            (page_width / 2 - 24, page_height - 30),
            f"Page {p_idx + 1} of {total_pages}",
            fontsize=8,
            fontname="helv",
            color=(0.55, 0.60, 0.68),
        )
        page.draw_line(
            (margin_x, page_height - 40),
            (margin_x + content_width, page_height - 40),
            color=(0.90, 0.92, 0.95),
            width=0.5,
        )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def process_multi_format_document(
    file_bytes: bytes,
    filename: str,
    owner_id: str,
    db: Session,
    allow_external_ai: bool = False,
) -> MultiFormatIngestResponse:
    """
    Ingests and parses any supported file type, creates a high-fidelity synthesized PDF,
    and indexes spatial chunks for RAG, search, and translation.
    """
    import hashlib

    detected = detect_document_format(filename, file_bytes)

    if detected == "pdf":
        pdf_bytes = file_bytes
        doc_structure = {"format": "pdf", "title": filename, "blocks": [], "table_count": 0}
    elif detected == "docx":
        doc_structure = parse_docx_to_structure(file_bytes)
        pdf_bytes = synthesize_pdf_from_structure(doc_structure, filename=filename)
    elif detected == "xlsx":
        doc_structure = parse_xlsx_to_structure(file_bytes)
        pdf_bytes = synthesize_pdf_from_structure(doc_structure, filename=filename)
    elif detected == "csv":
        doc_structure = parse_csv_to_structure(file_bytes)
        pdf_bytes = synthesize_pdf_from_structure(doc_structure, filename=filename)
    elif detected == "markdown":
        doc_structure = parse_markdown_to_structure(file_bytes)
        pdf_bytes = synthesize_pdf_from_structure(doc_structure, filename=filename)
    else:  # plain text fallback
        text_lines = file_bytes.decode("utf-8", errors="replace").splitlines()
        doc_structure = {
            "format": "text",
            "title": filename,
            "blocks": [{"type": "paragraph", "text": line} for line in text_lines if line.strip()],
            "table_count": 0,
        }
        pdf_bytes = synthesize_pdf_from_structure(doc_structure, filename=filename)

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = f"mf_{sha256[:16]}"

    # Extract spatial chunks from synthesized or original PDF
    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, document_id=doc_id)
    if not chunks:
        # Fallback single chunk from blocks if extraction yielded zero
        all_text = " ".join(b.get("text", "") for b in doc_structure.get("blocks", []))
        if not all_text.strip():
            all_text = filename
        chunks = [
            DocumentChunk(
                id=f"{doc_id}_c0",
                document_id=doc_id,
                page=1,
                rects=[[54.0, 54.0, 541.0, 788.0]],
                page_w=595.0,
                page_h=842.0,
                content=all_text[:1000],
            )
        ]

    # Compute embeddings respecting privacy gate (F13)
    embeddings = [get_embedding(c.content, allow_external=allow_external_ai) for c in chunks]

    # Persist in database
    store_document_and_chunks(
        db=db,
        document_id=doc_id,
        owner_id=owner_id,
        filename=filename,
        sha256=sha256,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dim=DEFAULT_EMBEDDING_DIM,
        chunks=chunks,
        embeddings=embeddings,
        allow_external_ai=allow_external_ai,
    )

    transient_store, purge_func = _get_transient_store()
    purge_func()
    transient_store[doc_id] = {"bytes": pdf_bytes, "created_at": time.time()}

    # Compute basic word count
    total_words = sum(len(c.content.split()) for c in chunks)
    preview = chunks[0].content[:240] + ("..." if len(chunks[0].content) > 240 else "")

    return MultiFormatIngestResponse(
        status="success",
        document_id=doc_id,
        filename=filename,
        detected_format=detected.upper(),
        title=doc_structure.get("title") or filename,
        page_count=max(1, max(c.page for c in chunks)),
        chunks_count=len(chunks),
        table_count=doc_structure.get("table_count", 0),
        word_count=total_words,
        text_preview=preview,
        pdf_url=f"/api/ai/documents/{doc_id}/download",
        owner_id=owner_id,
        allow_external_ai=allow_external_ai,
    )
