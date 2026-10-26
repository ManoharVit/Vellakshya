"""
PDF Workbench Pro — FastAPI backend.
Comprehensive PDF manipulation matching Adobe Acrobat Pro features with high-fidelity PDF-to-HTML conversion.
"""
from __future__ import annotations
import json
from pathlib import Path
import secrets
from typing import Any, Optional
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import STATIC_DIR, config
from app.services import auth, collaboration, converter, editor, forms, inspection, organizer, security, signatures
from app.services.queue import queue_instance

app = FastAPI(
    title=config.title,
    version=config.version,
    description="Full-featured PDF Workstation with Adobe Acrobat Pro capabilities and PDF-to-HTML conversion",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Starts the background worker queue processor upon application launch."""
    queue_instance.start_worker()


@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully terminates background worker routines."""
    await queue_instance.stop_worker()


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint for container orchestrators, monitors, and k6 load tests.
    """
    return {
        "status": "healthy",
        "app": "Vellakshya",
        "version": config.version,
    }


@app.get("/api/sample/{sample_type}")
async def get_sample_document(sample_type: str = "invoice"):
    """
    Generates synthetic high-quality sample PDF documents for instant testing and relief from the blank page.
    """
    import fitz
    doc = fitz.open()

    if sample_type == "report":
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text((50, 70), "Vellakshya Enterprise Document Audit", fontsize=20, color=(0.1, 0.2, 0.5))
        p1.insert_text((50, 100), "Executive Preflight & Compliance Report", fontsize=14, color=(0.4, 0.4, 0.4))
        p1.insert_text((50, 140), "1. Executive Summary\nThis document benchmarks rendering fidelity, typographic metrics, and\naccessibility tagging across multi-page enterprise records.", fontsize=11, color=(0, 0, 0))

        p2 = doc.new_page(width=595, height=842)
        p2.insert_text((50, 70), "2. Security & Compliance", fontsize=16, color=(0.1, 0.2, 0.5))
        p2.insert_text((50, 100), "Digital signature digest: SHA-256 authenticated.\nBitmask permissions: Printing Allowed, Copying Allowed, Annotations Allowed.", fontsize=11, color=(0, 0, 0))

        p3 = doc.new_page(width=595, height=842)
        p3.insert_text((50, 70), "3. Operational Sign-Off", fontsize=16, color=(0.1, 0.2, 0.5))
        p3.insert_text((50, 100), "Lead Architect: Giri Manohar Vemula\nStatus: APPROVED FOR PRODUCTION", fontsize=11, color=(0.1, 0.5, 0.2))
        filename = "Sample_Enterprise_Report.pdf"
    else:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text((50, 70), "INVOICE #INV-2026-001", fontsize=20, color=(0.1, 0.2, 0.5))
        p1.insert_text((50, 100), "Date: October 26, 2026", fontsize=11, color=(0.4, 0.4, 0.4))
        p1.insert_text((50, 125), "Billed To: Acros Global Enterprises Inc.", fontsize=12, color=(0, 0, 0))
        p1.insert_text((50, 165), "Description                          Qty    Unit Price    Total", fontsize=10, color=(0.3, 0.3, 0.3))
        p1.insert_text((50, 185), "PDF Enterprise Workstation License     1     $1,200.00   $1,200.00", fontsize=10, color=(0, 0, 0))
        p1.insert_text((50, 205), "Maintenance & SLA Support (Year 1)     1       $350.00     $350.00", fontsize=10, color=(0, 0, 0))
        p1.insert_text((50, 245), "Total Due: $1,550.00", fontsize=14, color=(0.1, 0.5, 0.2))
        filename = "Sample_Invoice.pdf"

    pdf_bytes = doc.tobytes()
    doc.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# -------------------------------------------------------------
# 0. ASYNCHRONOUS WORKER QUEUE & PROCESS SANDBOX ENDPOINTS
# -------------------------------------------------------------

@app.post("/api/jobs/convert/html", status_code=202)
async def queue_convert_pdf_to_html(
    file: UploadFile = File(...),
    mode: str = Form("fixed"),  # "fixed" or "semantic"
):
    """
    Enqueues an asynchronous, sandboxed PDF-to-HTML conversion task.
    Offloads heavy/untrusted rendering into an isolated worker boundary.
    """
    pdf_bytes = await file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

    task = "html_semantic" if mode == "semantic" else "html_fixed"
    job = await queue_instance.enqueue(
        task=task,
        pdf_bytes=pdf_bytes,
        filename=file.filename or "document.pdf",
        params={"title": Path(file.filename or "document").stem, "mode": mode},
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "task": job.task,
        "filename": job.filename,
        "created_at": job.created_at,
        "status_url": f"/api/jobs/{job.id}",
    }


@app.post("/api/jobs/convert/images", status_code=202)
async def queue_convert_pdf_to_images(
    file: UploadFile = File(...),
    dpi: int = Form(150),
    format: str = Form("png"),
):
    """
    Enqueues an asynchronous, sandboxed PDF-to-Images ZIP generation task.
    """
    pdf_bytes = await file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

    job = await queue_instance.enqueue(
        task="images_zip",
        pdf_bytes=pdf_bytes,
        filename=file.filename or "document.pdf",
        params={"dpi": dpi, "format": format},
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "task": job.task,
        "filename": job.filename,
        "created_at": job.created_at,
        "status_url": f"/api/jobs/{job.id}",
    }


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Queries execution state, progress percentage, and sandbox metrics for an asynchronous task.
    """
    job = queue_instance.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """
    Downloads or renders the persisted output artifact generated by the sandboxed worker.
    """
    job = queue_instance.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status in ("queued", "processing"):
        raise HTTPException(status_code=425, detail="Job is still processing in sandbox.")
    if job.status != "succeeded":
        raise HTTPException(status_code=400, detail=f"Job {job.status}: {job.error or 'Execution failed'}")

    artifact = queue_instance.get_job_artifact(job_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact file not found or expired.")

    content_bytes, media_type, filename = artifact
    if media_type == "text/html":
        return HTMLResponse(content=content_bytes.decode("utf-8"), media_type="text/html")

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancels an active or queued background job.
    """
    success = queue_instance.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled or was not found.")
    return {"job_id": job_id, "status": "cancelled"}


@app.get("/api/jobs")
async def list_recent_jobs(limit: int = Query(20, ge=1, le=100)):
    """
    Lists recent worker queue jobs and audit metrics.
    """
    jobs = queue_instance.list_jobs(limit=limit)
    return {
        "count": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


# -------------------------------------------------------------
# 1. CONVERSION ENDPOINTS
# -------------------------------------------------------------

@app.post("/api/convert/html")
async def convert_pdf_to_html(
    file: UploadFile = File(...),
    mode: str = Form("fixed"),  # "fixed" or "semantic"
):
    """
    Converts uploaded PDF into high-fidelity or semantic responsive HTML.
    """
    pdf_bytes = await file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")
        
    title = Path(file.filename or "document").stem
    if mode == "semantic":
        result_html = converter.pdf_to_html_semantic(pdf_bytes, title=title)
    else:
        result_html = converter.pdf_to_html_fixed(pdf_bytes, title=title)
        
    return HTMLResponse(content=result_html, media_type="text/html")


@app.post("/api/convert/images")
async def convert_pdf_to_images(
    file: UploadFile = File(...),
    dpi: int = Form(150),
    format: str = Form("png"),
):
    """
    Renders every PDF page into images bundled in a ZIP archive.
    """
    pdf_bytes = await file.read()
    zip_bytes = converter.pdf_to_images_zip(pdf_bytes, dpi=dpi, img_format=format)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={Path(file.filename or 'doc').stem}_images.zip"},
    )


@app.post("/api/convert/images-to-pdf")
async def convert_images_to_pdf(
    files: list[UploadFile] = File(...),
):
    """
    Combines uploaded image files into a single multi-page PDF.
    """
    images_data = []
    for f in files:
        data = await f.read()
        images_data.append((f.filename or "image.png", data))
        
    pdf_bytes = converter.images_to_pdf(images_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=combined_from_images.pdf"},
    )


@app.post("/api/convert/markdown")
async def convert_pdf_to_markdown(
    file: UploadFile = File(...),
):
    """
    Extracts text as structured Markdown.
    """
    pdf_bytes = await file.read()
    md_content = converter.pdf_to_markdown(pdf_bytes)
    return {"filename": file.filename, "markdown": md_content}


# -------------------------------------------------------------
# 2. PAGE ORGANIZATION ENDPOINTS (Merge, Split, Rotate, Delete, Reorder, Extract)
# -------------------------------------------------------------

@app.post("/api/organize/merge")
async def merge_pdf_files(
    files: list[UploadFile] = File(...),
):
    """
    Merges multiple PDF documents in given order.
    """
    pdf_bytes_list = [await f.read() for f in files]
    merged = organizer.merge_pdfs(pdf_bytes_list)
    return Response(
        content=merged,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=merged.pdf"},
    )


@app.post("/api/organize/split")
async def split_pdf(
    file: UploadFile = File(...),
    ranges: str = Form("1-2, 3"),  # e.g. "1-2, 3"
):
    """
    Splits PDF by specified page ranges.
    """
    pdf_bytes = await file.read()
    parts = organizer.split_pdf_by_ranges(pdf_bytes, ranges)
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid page ranges specified.")
        
    # Return as single or zip
    if len(parts) == 1:
        return Response(
            content=parts[0][1],
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={parts[0][0]}"},
        )
    else:
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in parts:
                zf.writestr(name, content)
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=split_pages.zip"},
        )


@app.post("/api/organize/rotate")
async def rotate_pdf_pages(
    file: UploadFile = File(...),
    angle: int = Form(90),
    pages: Optional[str] = Form(None),  # e.g. "1,2,5" or "1-3" or blank for all
):
    """
    Rotates all or selected pages by 90, 180, or 270 degrees.
    """
    pdf_bytes = await file.read()
    page_list = organizer.parse_page_spec(pages) if pages else None
    rotated = organizer.rotate_pages(pdf_bytes, pages=page_list, angle=angle)
    return Response(
        content=rotated,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=rotated_{file.filename}"},
    )


@app.post("/api/organize/delete")
async def delete_pdf_pages(
    file: UploadFile = File(...),
    pages: str = Form(...),  # e.g. "2, 4" or "2-3"
):
    """
    Deletes specified pages from the PDF.
    """
    pdf_bytes = await file.read()
    page_list = organizer.parse_page_spec(pages)
    if not page_list:
        raise HTTPException(status_code=400, detail="No valid page numbers or ranges provided to delete.")
    try:
        modified = organizer.delete_pages(pdf_bytes, pages_to_delete=page_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete pages: {str(e)}")

    return Response(
        content=modified,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=pruned_{file.filename}"},
    )


@app.post("/api/organize/reorder")
async def reorder_pdf_pages(
    file: UploadFile = File(...),
    order: str = Form(...),  # e.g. "3, 1, 2"
):
    """
    Reorders pages based on provided sequence.
    """
    pdf_bytes = await file.read()
    order_list = [int(p.strip()) for p in order.split(",") if p.strip()]
    reordered = organizer.reorder_pages(pdf_bytes, new_order=order_list)
    return Response(
        content=reordered,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reordered_{file.filename}"},
    )


@app.post("/api/organize/extract")
async def extract_pdf_pages(
    file: UploadFile = File(...),
    pages: str = Form(...),  # e.g. "1, 3, 5" or "1-3"
):
    """
    Extracts specified pages into a fresh PDF.
    """
    pdf_bytes = await file.read()
    page_list = organizer.parse_page_spec(pages)
    if not page_list:
        raise HTTPException(status_code=400, detail="No valid page numbers or ranges provided to extract.")
    extracted = organizer.extract_pages(pdf_bytes, pages_to_extract=page_list)
    return Response(
        content=extracted,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=extracted_{file.filename}"},
    )


@app.post("/api/organize/crop")
async def crop_pdf_pages(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),  # e.g. "1, 2" or None for all
    x0: Optional[float] = Form(None),
    y0: Optional[float] = Form(None),
    x1: Optional[float] = Form(None),
    y1: Optional[float] = Form(None),
    margin_top: float = Form(0.0),
    margin_bottom: float = Form(0.0),
    margin_left: float = Form(0.0),
    margin_right: float = Form(0.0),
):
    """
    Crops specified or all pages using either a bounding box [x0, y0, x1, y1]
    or margin trim distances (top, bottom, left, right in points).
    """
    pdf_bytes = await file.read()
    page_list = [int(p.strip()) for p in pages.split(",") if p.strip()] if pages else None
    cropped = organizer.crop_pages(
        pdf_bytes,
        pages=page_list,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        margin_left=margin_left,
        margin_right=margin_right,
    )
    return Response(
        content=cropped,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cropped_{file.filename}"},
    )


# -------------------------------------------------------------
# 3. CONTENT EDITING & ANNOTATION (Watermark, Pagination, Header/Footer, Highlight)
# -------------------------------------------------------------

@app.post("/api/edit/watermark")
async def add_watermark(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    opacity: float = Form(0.25),
    font_size: int = Form(48),
    angle: int = Form(45),
):
    """
    Adds semi-transparent watermark text across pages.
    """
    pdf_bytes = await file.read()
    watermarked = editor.add_text_watermark(
        pdf_bytes, text=text, opacity=opacity, font_size=font_size, angle=angle
    )
    return Response(
        content=watermarked,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=watermarked_{file.filename}"},
    )


@app.post("/api/edit/page-numbers")
async def add_page_numbers(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    pattern: str = Form("Page {page} of {total}"),
    font_size: int = Form(10),
):
    """
    Adds dynamic page numbering / Bates numbering.
    """
    pdf_bytes = await file.read()
    paginated = editor.add_page_numbers(
        pdf_bytes, position=position, format_pattern=pattern, font_size=font_size
    )
    return Response(
        content=paginated,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=paginated_{file.filename}"},
    )


@app.post("/api/edit/header-footer")
async def add_header_footer(
    file: UploadFile = File(...),
    header: str = Form(""),
    footer: str = Form(""),
):
    """
    Adds header and footer text across all pages.
    """
    pdf_bytes = await file.read()
    modified = editor.add_header_footer(pdf_bytes, header_text=header, footer_text=footer)
    return Response(
        content=modified,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=header_footer_{file.filename}"},
    )


@app.post("/api/edit/highlight")
async def highlight_terms(
    file: UploadFile = File(...),
    terms: str = Form(...),  # Comma-separated search terms
):
    """
    Highlights search keywords inside the PDF.
    """
    pdf_bytes = await file.read()
    term_list = [t.strip() for t in terms.split(",") if t.strip()]
    highlighted = editor.highlight_search_terms(pdf_bytes, terms=term_list)
    return Response(
        content=highlighted,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=highlighted_{file.filename}"},
    )


def _parse_rect_param(val: Any) -> Optional[list[float]]:
    if not val:
        return None
    if isinstance(val, (list, tuple)) and len(val) == 4:
        try:
            return [float(x) for x in val]
        except (ValueError, TypeError):
            return None
    if isinstance(val, str):
        try:
            cleaned = val.strip().strip("[]()")
            parts = [float(p.strip()) for p in cleaned.split(",") if p.strip()]
            if len(parts) == 4:
                return parts
        except (ValueError, TypeError):
            return None
    return None


@app.post("/api/edit/replace-text")
async def replace_pdf_text(
    file: UploadFile = File(...),
    search_text: Optional[str] = Form(None),
    replacement_text: Optional[str] = Form(""),
    font_size: Optional[int] = Form(None),
    color: Optional[str] = Form(None),
    pages: Optional[str] = Form(None),
    rules: Optional[str] = Form(None),
    single: bool = Form(False),
    occurrence: Optional[int] = Form(None),
    rect: Optional[str] = Form(None),
    page_num: Optional[int] = Form(None),
    preserve_style: bool = Form(True),
    override_color: bool = Form(False),
    override_size: bool = Form(False),
):
    """
    Searches for target text, whites out the original glyphs, and inserts replacement text.
    Automatically detects and preserves the exact font family, style (bold/italic), font size,
    text color, and typographical baseline from the original text being replaced.
    Supports either targeted single-match replacement (single=True) or document-wide Replace All (single=False).
    """
    import json
    pdf_bytes = await file.read()
    page_list = [int(p.strip()) for p in pages.split(",") if p.strip()] if pages else None
    parsed_color = editor.hex_to_rgb(color) if color and color.strip() and color != "auto" else None
    parsed_rect = _parse_rect_param(rect)

    rule_list: list[dict] = []
    if rules:
        try:
            parsed = json.loads(rules)
            if isinstance(parsed, list):
                for r in parsed:
                    r_preserve = bool(r.get("preserve_style", preserve_style))
                    r_override_col = bool(r.get("override_color", override_color))
                    r_override_sz = bool(r.get("override_size", override_size))

                    r_color = None
                    if "color" in r and r.get("color"):
                        c_val = r.get("color")
                        if isinstance(c_val, str) and c_val.strip() and c_val != "auto":
                            r_color = editor.hex_to_rgb(c_val)
                        elif isinstance(c_val, (list, tuple)) and len(c_val) == 3:
                            r_color = tuple(c_val)
                    elif parsed_color is not None and (r_override_col or not r_preserve):
                        r_color = parsed_color

                    r_single = bool(r.get("single", False)) or single
                    r_occ = r.get("occurrence") if r.get("occurrence") is not None else occurrence
                    if r_occ is not None:
                        try:
                            r_occ = int(r_occ)
                        except (ValueError, TypeError):
                            r_occ = None
                    r_rect = _parse_rect_param(r.get("rect")) or parsed_rect
                    r_page = r.get("page_num") or r.get("page") or page_num
                    if r_page is not None:
                        try:
                            r_page = int(r_page)
                        except (ValueError, TypeError):
                            r_page = None

                    rule_list.append(
                        {
                            "search_text": r.get("search_text") or r.get("search", ""),
                            "replacement_text": r.get("replacement_text")
                            if "replacement_text" in r
                            else r.get("replace", ""),
                            "font_size": r.get("font_size") or font_size,
                            "color": r_color,
                            "single": r_single,
                            "occurrence": r_occ,
                            "rect": r_rect,
                            "page_num": r_page,
                            "preserve_style": r_preserve,
                            "override_color": r_override_col,
                            "override_size": r_override_sz,
                        }
                    )
        except Exception:
            pass

    if not rule_list and search_text:
        rule_list.append(
            {
                "search_text": search_text,
                "replacement_text": replacement_text or "",
                "font_size": font_size,
                "color": parsed_color if (override_color or not preserve_style) else None,
                "single": single,
                "occurrence": occurrence,
                "rect": parsed_rect,
                "page_num": page_num,
                "preserve_style": preserve_style,
                "override_color": override_color,
                "override_size": override_size,
            }
        )

    modified, count = editor.replace_text_batch(
        pdf_bytes,
        rules=rule_list,
        pages=page_list,
        preserve_style=preserve_style,
    )
    return Response(
        content=modified,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=edited_{file.filename}",
            "X-Replacement-Count": str(count),
        },
    )


@app.post("/api/edit/insert-text")
async def insert_pdf_text(
    file: UploadFile = File(...),
    page: int = Form(1),
    text: str = Form(...),
    x: float = Form(...),
    y: float = Form(...),
    font_size: int = Form(12),
    color: str = Form("#000000"),
    bg_fill: bool = Form(False),
):
    """
    Inserts a custom text box onto the specified page at point coordinates (x, y).
    """
    pdf_bytes = await file.read()
    rgb_color = editor.hex_to_rgb(color)
    bg_color = (1.0, 1.0, 1.0) if bg_fill else None
    modified = editor.insert_text_block(
        pdf_bytes,
        page_num=page,
        text=text,
        x=x,
        y=y,
        font_size=font_size,
        color=rgb_color,
        bg_fill_color=bg_color,
    )
    return Response(
        content=modified,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=text_inserted_{file.filename}"},
    )


@app.post("/api/edit/whiteout")
async def whiteout_pdf_area(
    file: UploadFile = File(...),
    page: int = Form(1),
    x0: float = Form(...),
    y0: float = Form(...),
    x1: float = Form(...),
    y1: float = Form(...),
):
    """
    Erases and whites out a rectangular region on a specified page.
    """
    pdf_bytes = await file.read()
    modified = editor.whiteout_area(pdf_bytes, page_num=page, x0=x0, y0=y0, x1=x1, y1=y1)
    return Response(
        content=modified,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=whiteout_{file.filename}"},
    )


# -------------------------------------------------------------
# 4. SECURITY & REDACTION (AES-256 Encryption, Decrypt, Redact, Sanitize)
# -------------------------------------------------------------

@app.post("/api/security/encrypt")
async def encrypt_document(
    file: UploadFile = File(...),
    password: str = Form(...),
    owner_password: Optional[str] = Form(None),
    allow_printing: bool = Form(True),
    allow_copying: bool = Form(False),
):
    """
    Secures PDF with AES-256 standard encryption.
    """
    pdf_bytes = await file.read()
    encrypted = security.encrypt_pdf(
        pdf_bytes,
        user_password=password,
        owner_password=owner_password,
        allow_printing=allow_printing,
        allow_copying=allow_copying,
    )
    return Response(
        content=encrypted,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=secured_{file.filename}"},
    )


@app.post("/api/security/decrypt")
async def decrypt_document(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """
    Removes password security from PDF.
    """
    pdf_bytes = await file.read()
    try:
        decrypted = security.decrypt_pdf(pdf_bytes, password=password)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    return Response(
        content=decrypted,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=unlocked_{file.filename}"},
    )


@app.post("/api/security/redact")
async def redact_document(
    file: UploadFile = File(...),
    terms: str = Form(...),  # Comma-separated sensitive keywords/numbers
):
    """
    Permanently blacks out and wipes sensitive text streams from the document.
    """
    pdf_bytes = await file.read()
    term_list = [t.strip() for t in terms.split(",") if t.strip()]
    redacted, count = security.redact_text_permanently(pdf_bytes, terms_to_redact=term_list)
    return Response(
        content=redacted,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=redacted_{file.filename}",
            "X-Redaction-Count": str(count),
        },
    )


@app.post("/api/security/sanitize")
async def sanitize_document(
    file: UploadFile = File(...),
):
    """
    Strips all metadata, tracking stamps, and annotations to sanitize the PDF.
    """
    pdf_bytes = await file.read()
    sanitized = security.sanitize_document(pdf_bytes)
    return Response(
        content=sanitized,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=sanitized_{file.filename}"},
    )


# -------------------------------------------------------------
# 5. FORMS & FIELD HANDLING
# -------------------------------------------------------------

@app.post("/api/forms/fields")
async def list_form_fields(
    file: UploadFile = File(...),
):
    """
    Inspects all interactive AcroForm fields in the PDF.
    """
    pdf_bytes = await file.read()
    fields = forms.get_form_fields(pdf_bytes)
    return {"field_count": len(fields), "fields": fields}


@app.post("/api/forms/fill")
async def fill_form_fields(
    file: UploadFile = File(...),
    data_json: str = Form(...),  # JSON object mapping field_name -> value
):
    """
    Fills interactive AcroForm fields with provided data dictionary.
    """
    pdf_bytes = await file.read()
    field_data = json.loads(data_json)
    filled = forms.fill_form_fields(pdf_bytes, field_data)
    return Response(
        content=filled,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=filled_{file.filename}"},
    )


# -------------------------------------------------------------
# 6. INSPECTION & METADATA
# -------------------------------------------------------------

@app.post("/api/inspect")
async def inspect_document(
    file: UploadFile = File(...),
):
    """
    Provides deep structural analysis: metadata, dimensions, encryption, TOC, fonts, and images.
    """
    pdf_bytes = await file.read()
    info = inspection.inspect_pdf(pdf_bytes)
    return info


@app.post("/api/inspect/update-metadata")
async def update_metadata(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    creator: Optional[str] = Form(None),
    producer: Optional[str] = Form(None),
):
    """
    Updates PDF document metadata.
    """
    pdf_bytes = await file.read()
    updates = {
        "title": title,
        "author": author,
        "subject": subject,
        "keywords": keywords,
        "creator": creator,
        "producer": producer,
    }
    clean_updates = {k: v for k, v in updates.items() if v is not None}
    updated = inspection.update_metadata(pdf_bytes, clean_updates)
    return Response(
        content=updated,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=updated_meta_{file.filename}"},
    )


@app.post("/api/inspect/delete-metadata")
async def delete_metadata(
    file: UploadFile = File(...),
    fields: Optional[str] = Form(None),
):
    """
    Deletes metadata from a PDF file.
    If fields is empty or None, clears all metadata and extended XMP metadata.
    If fields is provided (comma-separated), clears only those specific fields.
    """
    pdf_bytes = await file.read()
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    cleared = inspection.delete_metadata(pdf_bytes, field_list)
    return Response(
        content=cleared,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cleared_meta_{file.filename}"},
    )


# -------------------------------------------------------------
# 7. SIGNATURES, COLLABORATION, AND SECURITY VALIDATION
# -------------------------------------------------------------

@app.post("/api/signatures/sign")
async def sign_document(
    file: UploadFile = File(...),
    signer_name: str = Form(...),
    reason: str = Form("Document Approval"),
    location: str = Form("Workbench Secure Sign"),
):
    """
    Digitally signs a PDF document, affixing visual stamp and cryptographic digest.
    """
    pdf_bytes = await file.read()
    signed_bytes = signatures.sign_pdf(pdf_bytes, signer_name, reason, location)
    return Response(
        content=signed_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=signed_{file.filename}"},
    )


@app.post("/api/signatures/verify")
async def verify_signature(
    file: UploadFile = File(...),
):
    """
    Verifies digital signature integrity, detecting any content tampering or modification.
    """
    pdf_bytes = await file.read()
    result = signatures.verify_pdf_signature(pdf_bytes)
    return result


@app.post("/api/collab/merge")
async def merge_concurrent_edits(
    file: UploadFile = File(...),
    user_a_comments: str = Form("[]"),
    user_b_comments: str = Form("[]"),
    base_version: int = Form(1),
):
    """
    Merges concurrent comments from multiple users without lost updates or duplicate comments.
    """
    pdf_bytes = await file.read()
    comments_a = json.loads(user_a_comments)
    comments_b = json.loads(user_b_comments)
    merged_bytes, summary = collaboration.merge_concurrent_comments(
        pdf_bytes, comments_a, comments_b, base_version=base_version
    )
    return Response(
        content=merged_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=collab_merged_{file.filename}",
            "x-collab-summary": json.dumps(summary),
        },
    )


@app.post("/api/collab/sync-offline")
async def sync_offline_actions(
    file: UploadFile = File(...),
    actions_queue: str = Form("[]"),
    current_version: int = Form(1),
):
    """
    Replays queued mutations executed on mobile/offline clients upon reconnection.
    """
    pdf_bytes = await file.read()
    queue = json.loads(actions_queue)
    synced_bytes, summary = collaboration.sync_offline_actions(
        pdf_bytes, queue, current_version=current_version
    )
    return Response(
        content=synced_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=offline_synced_{file.filename}",
            "x-sync-summary": json.dumps(summary),
        },
    )


@app.post("/api/security/validate")
async def validate_document_security(
    file: UploadFile = File(...),
    max_size_mb: float = Form(100.0),
):
    """
    Validates file against malicious payloads, polyglot headers, oversized files, and embedded scripts.
    """
    pdf_bytes = await file.read()
    validation_report = security.validate_pdf_security(pdf_bytes, max_size_mb=max_size_mb)
    if not validation_report["safe"]:
        # Return 400 with security details
        raise HTTPException(
            status_code=400,
            detail=validation_report,
        )
    return validation_report


# -------------------------------------------------------------
# 11. AUTHENTICATION, RBAC & DOCUMENT LIFECYCLE ENDPOINTS
# -------------------------------------------------------------

def _resolve_user(token: Optional[str] = None, authorization: Optional[str] = None) -> Optional[dict[str, Any]]:
    active_token = token
    if not active_token and authorization and authorization.startswith("Bearer "):
        active_token = authorization.split(" ")[1].strip()
    if active_token:
        return auth.get_current_user_from_token(active_token)
    return None


@app.post("/api/auth/register")
async def auth_register(request: Request):
    """
    Registers a new user account with role.
    """
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)

    email = str(data.get("email", "")).strip()
    password = str(data.get("password", "")).strip()
    role = str(data.get("role", "editor")).strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    try:
        res = auth.register_user(email=email, password=password, role=role)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def auth_login(request: Request):
    """
    Logs in a user and returns an active session token.
    """
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)

    email = str(data.get("email", "")).strip()
    password = str(data.get("password", "")).strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    try:
        session = auth.login_user(email=email, password=password)
        return session
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/auth/logout")
async def auth_logout(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Form(None),
):
    """
    Logs out a user and invalidates their session.
    """
    active_token = token
    if not active_token and authorization and authorization.startswith("Bearer "):
        active_token = authorization.split(" ")[1].strip()
    if not active_token:
        try:
            data = await request.json()
            active_token = data.get("token")
        except Exception:
            pass

    if not active_token:
        raise HTTPException(status_code=400, detail="Session token required.")

    success = auth.logout_user(active_token)
    return {"success": success}


@app.post("/api/documents")
async def upload_managed_document(
    file: UploadFile = File(...),
    token: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    Uploads and stores a document in the managed document store.
    """
    user = _resolve_user(token, authorization)
    if user and not auth.verify_role_permission(user["role"], "upload"):
        raise HTTPException(status_code=403, detail="Role not permitted to upload documents.")

    pdf_bytes = await file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

    doc_id = secrets.token_hex(12)
    owner = user["email"] if user else "anonymous"
    meta = auth.store_document(doc_id=doc_id, content=pdf_bytes, owner=owner)
    return meta


@app.get("/api/documents/{doc_id}")
async def get_managed_document(
    doc_id: str,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """
    Retrieves document content. Enforces RBAC download restrictions and 404 for deleted files.
    """
    user = _resolve_user(token, authorization)
    if download and user:
        if not auth.verify_role_permission(user["role"], "download"):
            raise HTTPException(status_code=403, detail="Viewer role cannot download restricted files.")

    content = auth.get_document(doc_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found or has been deleted.")

    headers = {
        "Content-Disposition": f"{'attachment' if download else 'inline'}; filename={doc_id}.pdf"
    }
    return Response(content=content, media_type="application/pdf", headers=headers)


@app.delete("/api/documents/{doc_id}")
async def delete_managed_document(
    doc_id: str,
    token: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    Soft-deletes a document. Subsequent requests to this document URL will return 404.
    """
    rec = auth.get_document_record(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found or already deleted.")

    auth.delete_document(doc_id)
    return {"success": True, "detail": "Document successfully deleted."}


@app.post("/api/documents/{doc_id}/edit")
async def edit_managed_document(
    doc_id: str,
    file: UploadFile = File(...),
    base_version: int = Form(1),
    token: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    Applies edits with optimistic concurrency control. Rejects silent overwrites with 409 Conflict.
    Enforces viewer editing restriction with 403 Forbidden.
    """
    user = _resolve_user(token, authorization)
    if user and not auth.verify_role_permission(user["role"], "edit"):
        raise HTTPException(status_code=403, detail="Viewer role cannot edit restricted files.")

    new_bytes = await file.read()
    try:
        updated = auth.update_document_content(doc_id, new_bytes, expected_version=base_version)
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found or has been deleted.")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/sessions/draft")
async def save_draft_state(request: Request):
    """
    Preserves in-progress session draft edits against sudden expiration or disconnects.
    """
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)
        if isinstance(data.get("draft_state"), str):
            try:
                data["draft_state"] = json.loads(data["draft_state"])
            except Exception:
                pass

    session_id = data.get("session_id")
    draft_state = data.get("draft_state")
    if not session_id or draft_state is None:
        raise HTTPException(status_code=400, detail="session_id and draft_state are required.")

    auth.save_session_draft(session_id, draft_state)
    return {"status": "DRAFT_SAVED", "session_id": session_id}


@app.get("/api/sessions/draft/{session_id}")
async def recover_draft_state(session_id: str):
    """
    Recovers in-progress draft edits for a given session.
    """
    draft = auth.recover_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found for this session.")
    return {"session_id": session_id, "draft_state": draft}


# Mount static directory for the single-page application UI
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
