"""
PDF Inspection and Metadata Service.
Provides comprehensive structural analysis, TOC extraction, and metadata editing.
"""

from __future__ import annotations

from typing import Any

import fitz  # PyMuPDF


def inspect_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Extracts deep structural information, security flags, permissions, resources,
    TOC, fonts, and metadata from a PDF file.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    meta = doc.metadata or {}

    pages_info = []
    page_metrics = []
    total_images = 0
    total_annots = 0
    total_links = 0
    total_widgets = 0
    total_words = 0
    total_chars = 0
    font_set = set()

    def get_paper_format(w_pt: float, h_pt: float) -> str:
        dims = sorted([round(w_pt), round(h_pt)])
        w, h = dims[0], dims[1]
        if abs(w - 612) <= 3 and abs(h - 792) <= 3:
            return "Letter"
        if abs(w - 595) <= 3 and abs(h - 842) <= 3:
            return "A4"
        if abs(w - 612) <= 3 and abs(h - 1008) <= 3:
            return "Legal"
        if abs(w - 792) <= 3 and abs(h - 1224) <= 3:
            return "Tabloid"
        if abs(w - 420) <= 3 and abs(h - 595) <= 3:
            return "A5"
        if abs(w - 842) <= 3 and abs(h - 1191) <= 3:
            return "A3"
        return f"{w} × {h} pt"

    for idx, page in enumerate(doc, 1):
        rect = page.rect
        images = page.get_images()
        total_images += len(images)

        # Page annotations
        annots = list(page.annots())
        total_annots += len(annots)

        # Page links
        links = list(page.get_links())
        total_links += len(links)

        # Page widgets (interactive form fields)
        widgets = list(page.widgets())
        total_widgets += len(widgets)

        # Text counts
        p_text = page.get_text()
        p_chars = len(p_text)
        p_words = len(p_text.split())
        total_chars += p_chars
        total_words += p_words

        # Compute image coverage for classification if images present and text is sparse
        page_area = max(1.0, rect.width * rect.height)
        img_coverage = 0.0
        if len(images) > 0 and p_chars < 150:
            for img in images:
                xref = img[0]
                try:
                    for ir in page.get_image_rects(xref):
                        img_coverage += ir.width * ir.height
                except Exception:
                    pass
            img_coverage = min(1.0, img_coverage / page_area)

        page_metrics.append(
            {
                "page_number": idx,
                "char_count": p_chars,
                "word_count": p_words,
                "image_count": len(images),
                "image_coverage_ratio": round(img_coverage, 2),
            }
        )

        # Extract fonts
        for font in page.get_fonts():
            font_set.add(font[3])  # font name

        orientation = "Portrait" if rect.height >= rect.width else "Landscape"
        paper_size = get_paper_format(rect.width, rect.height)

        pages_info.append(
            {
                "page_number": idx,
                "width_pt": round(rect.width, 2),
                "height_pt": round(rect.height, 2),
                "width_mm": round(rect.width * 25.4 / 72, 1),
                "height_mm": round(rect.height * 25.4 / 72, 1),
                "format": paper_size,
                "orientation": orientation,
                "rotation": page.rotation,
                "images_count": len(images),
                "annots_count": len(annots),
                "links_count": len(links),
                "widgets_count": len(widgets),
            }
        )

    toc = doc.get_toc()  # [[lvl, title, page, ...]]
    formatted_toc = [{"level": item[0], "title": item[1], "page": item[2]} for item in toc]

    # Embedded files in catalog
    embfile_count = doc.embfile_count() if hasattr(doc, "embfile_count") else 0
    embfile_names = doc.embfile_names() if hasattr(doc, "embfile_names") else []

    # Permissions breakdown
    perms = doc.permissions
    permissions_dict = {
        "print_allowed": bool(perms & getattr(fitz, "PDF_PERM_PRINT", 4)),
        "modify_allowed": bool(perms & getattr(fitz, "PDF_PERM_MODIFY", 8)),
        "copy_allowed": bool(perms & getattr(fitz, "PDF_PERM_COPY", 16)),
        "annot_allowed": bool(perms & getattr(fitz, "PDF_PERM_ANNOTATE", 32)),
        "form_fill_allowed": bool(perms & getattr(fitz, "PDF_PERM_FORM", 256)),
    }

    result = {
        "page_count": len(doc),
        "file_size_bytes": len(pdf_bytes),
        "file_size_kb": round(len(pdf_bytes) / 1024, 1),
        "pdf_format": meta.get("format", "PDF 1.7"),
        "is_encrypted": doc.is_encrypted,
        "is_repaired": doc.is_repaired,
        "has_layers": doc.has_layers() if hasattr(doc, "has_layers") else False,
        "has_signatures": doc.has_sigflags() if hasattr(doc, "has_sigflags") else False,
        "permissions": permissions_dict,
        "permissions_code": perms,
        "metadata": {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
            "creator": meta.get("creator", ""),
            "producer": meta.get("producer", ""),
            "creation_date": meta.get("creationDate", ""),
            "modification_date": meta.get("modDate", ""),
            "trapped": meta.get("trapped", ""),
        },
        "stats": {
            "total_words": total_words,
            "total_characters": total_chars,
            "total_images": total_images,
            "total_fonts": len(font_set),
            "total_annotations": total_annots,
            "total_links": total_links,
            "total_form_fields": total_widgets,
            "total_embedded_files": embfile_count,
        },
        "total_images": total_images,
        "fonts": sorted(list(font_set)),
        "embedded_files": embfile_names,
        "table_of_contents": formatted_toc,
        "pages": pages_info,
    }

    doc.close()

    # Document Classifier & OCR recommendation
    from app.services.ocr import classify_document

    classification = classify_document(page_metrics=page_metrics)
    result["classification"] = classification["classification"]
    result["document_classification"] = classification
    result["ocr_recommended"] = classification["ocr_recommended"]

    return result


def update_metadata(pdf_bytes: bytes, metadata_updates: dict[str, str]) -> bytes:
    """
    Updates PDF metadata fields (title, author, subject, keywords, creator, producer).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    current_meta = doc.metadata or {}

    for key, val in metadata_updates.items():
        if val is not None:
            current_meta[key] = str(val)

    doc.set_metadata(current_meta)
    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes


def delete_metadata(
    pdf_bytes: bytes,
    fields: list[str] | None = None,
) -> bytes:
    """
    Deletes metadata from a PDF file.
    If fields is None or empty, completely wipes all metadata and XMP XML metadata.
    If fields is provided, clears only the requested metadata fields.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    editable_keys = [
        "title",
        "author",
        "subject",
        "keywords",
        "creator",
        "producer",
        "creationDate",
        "modDate",
        "trapped",
    ]

    if not fields:
        # Wipe all standard metadata dictionary entries
        doc.set_metadata({})
        # Wipe extended XMP XML metadata if present
        try:
            doc.del_xml_metadata()
        except Exception:
            try:
                doc.set_xml_metadata("")
            except Exception:
                pass
    else:
        current_meta = doc.metadata or {}
        # Normalize fields to lowercase alphanumeric for robust matching
        field_set = {f.lower().replace("_", "").replace("-", "") for f in fields}
        for k in editable_keys:
            norm_k = k.lower().replace("_", "").replace("-", "")
            if norm_k in field_set or k in fields:
                current_meta[k] = ""
        doc.set_metadata(current_meta)

    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes
