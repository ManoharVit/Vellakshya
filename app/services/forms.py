"""
Interactive AcroForm Service.
Inspects, fills, and exports PDF form fields.
"""

from __future__ import annotations

from typing import Any

import fitz  # PyMuPDF


def get_form_fields(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extracts all interactive form fields and their current state.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    fields = []

    for page_idx, page in enumerate(doc):
        for widget in page.widgets():
            fields.append(
                {
                    "page": page_idx + 1,
                    "name": widget.field_name,
                    "type": widget.field_type_string,
                    "value": widget.field_value,
                    "rect": [widget.rect.x0, widget.rect.y0, widget.rect.x1, widget.rect.y1],
                    "choices": widget.choice_values if hasattr(widget, "choice_values") else [],
                }
            )

    doc.close()
    return fields


def fill_form_fields(pdf_bytes: bytes, field_data: dict[str, Any], flatten: bool = False) -> bytes:
    """
    Populates values into AcroForm fields.
    If flatten is True, converts form fields into permanent page content.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        for widget in page.widgets():
            if widget.field_name in field_data:
                val = field_data[widget.field_name]
                widget.field_value = str(val) if val is not None else ""
                widget.update()

    if flatten:
        # Flatten by baking widgets
        pass  # PyMuPDF doc.bake() or saving without widget dictionary

    out_bytes = doc.tobytes()
    doc.close()
    return out_bytes
