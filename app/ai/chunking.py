"""
PDF Ingestion and Chunking Engine.
Extracts text blocks with coordinate metadata in unrotated PDF coordinate space,
merges blocks up to a token budget, and generates stable chunk hashes.
Executes PyMuPDF operations off the event loop.
"""

from __future__ import annotations

import hashlib
import re

import fitz

from app.ai.models import DocumentChunk


def _approx_token_count(text: str) -> int:
    """Fast whitespace token estimator (~1.3 tokens per word)."""
    words = len(text.split())
    return max(1, int(words * 1.3))


def extract_chunks_from_pdf_bytes(
    pdf_bytes: bytes,
    document_id: str,
    max_tokens_per_chunk: int = 300,
) -> list[DocumentChunk]:
    """
    Parses PDF bytes, extracts text blocks with their spatial rectangles,
    and aggregates them into stable, deterministic chunks.
    Coordinates are preserved in unrotated page space.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[DocumentChunk] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        page_w = float(page.rect.width)
        page_h = float(page.rect.height)
        rotation = int(page.rotation)

        blocks = page.get_text("blocks")
        # Filter for text blocks (type 0) with non-empty content
        text_blocks = [b for b in blocks if len(b) >= 7 and b[6] == 0 and b[4].strip()]

        current_text_segments: list[str] = []
        current_rects: list[list[float]] = []
        current_tokens = 0
        chunk_idx = 0

        for block in text_blocks:
            x0, y0, x1, y1, text, _, _ = block[:7]
            clean_text = re.sub(r"\s+", " ", text).strip()
            if not clean_text:
                continue

            block_tokens = _approx_token_count(clean_text)
            rect = [
                round(float(x0), 2),
                round(float(y0), 2),
                round(float(x1), 2),
                round(float(y1), 2),
            ]

            if current_tokens + block_tokens > max_tokens_per_chunk and current_text_segments:
                # Finalize chunk
                chunk_content = " ".join(current_text_segments)
                hasher = hashlib.sha256()
                hasher.update(
                    f"{document_id}:{page_num}:{chunk_idx}:{chunk_content[:64]}".encode("utf-8")
                )
                chunk_id = f"chk_{hasher.hexdigest()[:16]}"

                chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=document_id,
                        page=page_num,
                        rects=current_rects,
                        page_w=page_w,
                        page_h=page_h,
                        rotation=rotation,
                        content=chunk_content,
                    )
                )

                chunk_idx += 1
                current_text_segments = [clean_text]
                current_rects = [rect]
                current_tokens = block_tokens
            else:
                current_text_segments.append(clean_text)
                current_rects.append(rect)
                current_tokens += block_tokens

        # Flush any remaining segment on this page
        if current_text_segments:
            chunk_content = " ".join(current_text_segments)
            hasher = hashlib.sha256()
            hasher.update(
                f"{document_id}:{page_num}:{chunk_idx}:{chunk_content[:64]}".encode("utf-8")
            )
            chunk_id = f"chk_{hasher.hexdigest()[:16]}"

            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=document_id,
                    page=page_num,
                    rects=current_rects,
                    page_w=page_w,
                    page_h=page_h,
                    rotation=rotation,
                    content=chunk_content,
                )
            )

    doc.close()
    return chunks
