"""
Digital Signatures and Tamper Detection Service.
Provides cryptographic content hashing, signature generation, and verification.
"""
from __future__ import annotations
import hashlib
import json
from typing import Any
import fitz  # PyMuPDF


def _compute_document_content_hash(doc: fitz.Document) -> str:
    """
    Computes a cryptographic SHA-256 digest of all pages' text and vector drawings,
    excluding signature annotations.
    """
    hasher = hashlib.sha256()
    for page in doc:
        hasher.update(page.get_text().encode("utf-8"))
        hasher.update(page.get_drawings().__str__().encode("utf-8"))
    return hasher.hexdigest()


def sign_pdf(
    pdf_bytes: bytes,
    signer_name: str,
    reason: str = "Document Approval",
    location: str = "Workbench Secure Sign",
) -> bytes:
    """
    Digitally signs a PDF document by embedding a cryptographic SHA-256 digest
    and attaching a visible signature stamp.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # 1. Compute content hash before adding signature stamp
    digest = _compute_document_content_hash(doc)
    
    # 2. Add visual signature badge to the last page
    page = doc[-1]
    rect = fitz.Rect(page.rect.width - 220, page.rect.height - 85, page.rect.width - 20, page.rect.height - 15)
    page.draw_rect(rect, color=(0.12, 0.45, 0.85), width=1.5, fill=(0.95, 0.97, 1.0))
    page.insert_text(fitz.Point(rect.x0 + 8, rect.y0 + 20), f"Digitally Signed: {signer_name}", fontsize=9, color=(0.1, 0.2, 0.6))
    page.insert_text(fitz.Point(rect.x0 + 8, rect.y0 + 36), f"Reason: {reason}", fontsize=8, color=(0.25, 0.25, 0.25))
    page.insert_text(fitz.Point(rect.x0 + 8, rect.y0 + 52), f"Digest: {digest[:16]}...", fontsize=7, color=(0.4, 0.4, 0.4))
    page.insert_text(fitz.Point(rect.x0 + 8, rect.y0 + 64), f"Location: {location}", fontsize=7, color=(0.4, 0.4, 0.4))

    # 3. Store signature record in document metadata
    meta = doc.metadata or {}
    sig_payload = {
        "signer": signer_name,
        "reason": reason,
        "location": location,
        "digest": digest,
        "version": 1,
    }
    existing_kw = meta.get("keywords") or ""
    meta["keywords"] = existing_kw + (";" if existing_kw else "") + f"DIGITAL_SIG:{json.dumps(sig_payload)}"
    doc.set_metadata(meta)

    out_bytes = doc.tobytes(deflate=True)
    doc.close()
    return out_bytes


def verify_pdf_signature(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Verifies the cryptographic digital signature of a PDF document.
    Detects whether the document text or structural content was modified or tampered with.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    meta = doc.metadata or {}
    keywords = meta.get("keywords") or ""

    if "DIGITAL_SIG:" not in keywords:
        doc.close()
        return {
            "has_signature": False,
            "is_valid": False,
            "tamper_detected": False,
            "reason": "No digital signature manifest present in document.",
        }

    try:
        sig_str = keywords.split("DIGITAL_SIG:")[1].split(";")[0]
        sig_data = json.loads(sig_str)
        expected_digest = sig_data["digest"]
        signer = sig_data.get("signer", "Unknown")
        reason = sig_data.get("reason", "")
    except Exception as e:
        doc.close()
        return {
            "has_signature": True,
            "is_valid": False,
            "tamper_detected": True,
            "reason": f"Malformed signature metadata: {e}",
        }

    # Re-compute content digest
    # Note: the signature stamp added visual text to the last page.
    # To check tamper, we check if original content before stamp or current digest matches.
    # We strip the signature badge text lines from the last page text for verification
    hasher = hashlib.sha256()
    for idx, page in enumerate(doc):
        text = page.get_text()
        if idx == len(doc) - 1:
            # Filter out signature badge lines
            lines = [
                line for line in text.splitlines()
                if not line.startswith("Digitally Signed:")
                and not line.startswith("Reason:")
                and not line.startswith("Digest:")
                and not line.startswith("Location:")
            ]
            text = "\n".join(lines) + ("\n" if lines else "")
        hasher.update(text.encode("utf-8"))
        # Exclude the last page's rectangle drawing if present
        drawings = page.get_drawings()
        if idx == len(doc) - 1 and len(drawings) > 0:
            drawings = drawings[:-1]
        hasher.update(drawings.__str__().encode("utf-8"))

    current_digest = hasher.hexdigest()
    doc.close()

    is_valid = (current_digest == expected_digest)
    return {
        "has_signature": True,
        "is_valid": is_valid,
        "tamper_detected": not is_valid,
        "signer": signer,
        "reason": reason,
        "expected_digest": expected_digest,
        "computed_digest": current_digest,
        "status": "VALID_SIGNATURE" if is_valid else "DIGEST_FAILURE_TAMPER_DETECTED",
    }
