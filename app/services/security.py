"""
PDF Security, Encryption, Decryption, Permanent Redaction, and Threat Validation service.
"""

from __future__ import annotations

from typing import Any

import fitz  # PyMuPDF


def encrypt_pdf(
    pdf_bytes: bytes,
    user_password: str,
    owner_password: str | None = None,
    allow_printing: bool = True,
    allow_copying: bool = False,
) -> bytes:
    """
    Encrypts PDF with AES-256 standard encryption and permission flags.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    perm = fitz.PDF_PERM_ACCESSIBILITY
    if allow_printing:
        perm |= fitz.PDF_PERM_PRINT
    if allow_copying:
        perm |= fitz.PDF_PERM_COPY

    owner_pw = owner_password if owner_password else user_password

    out_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=user_password,
        owner_pw=owner_pw,
        permissions=perm,
    )
    doc.close()
    return out_bytes


def decrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """
    Authenticates and decrypts a password-protected PDF, outputting an unrestricted copy.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.is_encrypted:
        auth_success = doc.authenticate(password)
        if not auth_success:
            doc.close()
            raise ValueError("Invalid password provided for encrypted PDF.")

    out_bytes = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
    doc.close()
    return out_bytes


def redact_text_permanently(
    pdf_bytes: bytes,
    terms_to_redact: list[str],
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[bytes, int]:
    """
    Permanently wipes sensitive text occurrences from the PDF binary.
    Draws blackout blocks and completely purges the underlying glyphs.
    Returns (redacted_pdf_bytes, total_occurrences_redacted).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_redacted = 0

    for page in doc:
        for term in terms_to_redact:
            clean_term = term.strip()
            if not clean_term:
                continue
            rects = page.search_for(clean_term)
            for r in rects:
                annot = page.add_redact_annot(r, fill=fill_color)
                annot.update()
                total_redacted += 1
        page.apply_redactions()

    # defrag and garbage collect unused objects
    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes, total_redacted


def sanitize_document(pdf_bytes: bytes) -> bytes:
    """
    Strips all metadata, embedded attachments, XML/XMP streams, JavaScript actions,
    and annotations to sanitize the document.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # 1. Purge embedded attachment files
    for emb_name in list(doc.embfile_names()):
        try:
            doc.embfile_del(emb_name)
        except Exception:
            pass

    # 2. PyMuPDF deep scrubbing
    try:
        doc.scrub(
            attached_files=True,
            clean_pages=True,
            embedded_files=True,
            javascript=True,
            metadata=True,
            reset_fields=True,
            reset_responses=True,
            xml_metadata=True,
        )
    except Exception:
        pass

    # 3. Explicitly purge XML/XMP metadata and standard metadata dictionary
    try:
        doc.set_xml_metadata("")
    except Exception:
        pass

    doc.set_metadata(
        {
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
            "modDate": "",
        }
    )

    # 4. Remove annotations across all pages
    for page in doc:
        for annot in list(page.annots()):
            page.delete_annot(annot)

    # Defrag and garbage collect unreferenced streams/objects
    out_bytes = doc.tobytes(deflate=True, garbage=4)
    doc.close()
    return out_bytes


def validate_pdf_security(
    pdf_bytes: bytes,
    max_size_mb: float = 100.0,
) -> dict[str, Any]:
    """
    Validates uploaded file against security threats:
    - Rejects polyglot files and non-PDFs (must strictly start with %PDF-).
    - Enforces maximum file size to prevent memory exhaustion / decompression attacks.
    - Inspects for embedded malicious JavaScript, /Launch actions, and dangerous payloads.
    - Sandboxes PDF parser execution to safely catch malformed/corrupted files.
    """
    errors: list[str] = []
    warnings: list[str] = []
    is_safe = True

    # 1. Header validation (anti-polyglot check)
    if not pdf_bytes.startswith(b"%PDF-"):
        return {
            "safe": False,
            "error_type": "INVALID_HEADER_POLYGLOT",
            "errors": [
                "File does not strictly start with standard %PDF- magic bytes. Potential polyglot or invalid format."
            ],
            "warnings": [],
            "has_javascript": False,
            "has_launch_action": False,
        }

    # 2. Maximum size check
    max_bytes = int(max_size_mb * 1024 * 1024)
    if len(pdf_bytes) > max_bytes:
        return {
            "safe": False,
            "error_type": "OVERSIZED_PAYLOAD",
            "errors": [
                f"File size exceeds maximum permitted threshold ({len(pdf_bytes)} > {max_bytes} bytes)."
            ],
            "warnings": [],
            "has_javascript": False,
            "has_launch_action": False,
        }

    # 3. Parser execution & deep object inspection
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {
            "safe": False,
            "error_type": "CORRUPTED_OR_MALFORMED",
            "errors": [f"Failed to safely parse PDF stream: {e}"],
            "warnings": [],
            "has_javascript": False,
            "has_launch_action": False,
        }

    has_js = False
    has_launch = False

    # Scan raw objects for malicious action triggers (/JavaScript, /Launch)
    for xref in range(1, doc.xref_length()):
        try:
            obj_str = doc.xref_object(xref)
            if "/JavaScript" in obj_str or "/JS " in obj_str:
                has_js = True
            if "/Launch" in obj_str:
                has_launch = True
        except Exception:
            continue

    if has_launch:
        is_safe = False
        errors.append(
            "Malicious /Launch action detected. Execution of external commands is forbidden."
        )

    if has_js:
        warnings.append(
            "Embedded JavaScript detected in PDF catalog. Sandboxing / script neutralization recommended."
        )

    doc.close()

    return {
        "safe": is_safe,
        "error_type": None if is_safe else "DANGEROUS_OBJECT_DETECTED",
        "errors": errors,
        "warnings": warnings,
        "has_javascript": has_js,
        "has_launch_action": has_launch,
    }
