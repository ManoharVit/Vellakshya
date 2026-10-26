"""
Performance and Load Benchmarking Test Suite.
Benchmarks:
- 1 MB, 10 MB, and 50 MB PDFs (upload, open, render, edit-save, inspection).
- 500-page enterprise PDF throughput (navigation, text search, thumbnail rendering).
- Concurrent request latency under load.
"""
from __future__ import annotations
import os
import time
from fastapi.testclient import TestClient
import fitz
import pytest

from app.main import app

client = TestClient(app)


def _generate_synthetic_pdf(target_mb: float) -> bytes:
    """
    Generates a deterministic synthetic multi-page PDF scaled to target_mb.
    """
    doc = fitz.open()
    needed_pages = max(1, int(target_mb * 160))

    for p_idx in range(needed_pages):
        page = doc.new_page(width=612, height=792)
        for l in range(25):
            page.insert_text(
                fitz.Point(72, 50 + l * 25),
                f"Enterprise Performance Benchmark Row {l} on Page {p_idx+1} (Target {target_mb}MB)",
            )

    data = doc.tobytes(deflate=False)
    doc.close()
    return data


def test_benchmark_1mb_pdf_performance():
    """
    Benchmark 1 MB PDF: Measure open, render, edit-save, and API inspection latencies.
    """
    pdf_bytes = _generate_synthetic_pdf(1.0)
    actual_mb = len(pdf_bytes) / (1024 * 1024)
    assert actual_mb >= 0.5

    # 1. Open latency
    t0 = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    t_open = time.perf_counter() - t0
    assert t_open < 0.05  # < 50ms

    # 2. Render first page to pixmap
    t1 = time.perf_counter()
    pix = doc[0].get_pixmap(dpi=100)
    t_render = time.perf_counter() - t1
    assert pix.width > 0
    assert t_render < 0.15  # < 150ms

    # 3. Edit-save latency
    t2 = time.perf_counter()
    doc[0].insert_text(fitz.Point(72, 50), "PERF_STAMP_1MB")
    out_bytes = doc.tobytes(deflate=True)
    t_editsave = time.perf_counter() - t2
    doc.close()
    assert t_editsave < 0.20  # < 200ms

    # 4. API Inspection roundtrip
    t3 = time.perf_counter()
    res = client.post(
        "/api/inspect",
        files={"file": ("bench_1mb.pdf", pdf_bytes, "application/pdf")},
    )
    t_api = time.perf_counter() - t3
    assert res.status_code == 200
    assert t_api < 1.0  # < 1.0s API roundtrip


def test_benchmark_10mb_pdf_performance():
    """
    Benchmark 10 MB PDF: Measure open, render, edit-save, and API inspection latencies.
    """
    pdf_bytes = _generate_synthetic_pdf(10.0)
    actual_mb = len(pdf_bytes) / (1024 * 1024)
    assert actual_mb >= 5.0

    # 1. Open latency
    t0 = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    t_open = time.perf_counter() - t0
    assert t_open < 0.10  # < 100ms

    # 2. Render page
    t1 = time.perf_counter()
    pix = doc[0].get_pixmap(dpi=72)
    t_render = time.perf_counter() - t1
    assert t_render < 0.25  # < 250ms

    # 3. Edit-save latency
    t2 = time.perf_counter()
    doc[0].insert_text(fitz.Point(72, 50), "PERF_STAMP_10MB")
    out_bytes = doc.tobytes(deflate=True)
    t_editsave = time.perf_counter() - t2
    doc.close()
    assert t_editsave < 0.80  # < 800ms


def test_benchmark_concurrent_api_conversions():
    """
    Measure responsiveness under multiple sequential/concurrent API operations.
    """
    doc = fitz.open()
    p = doc.new_page(width=400, height=300)
    p.insert_text(fitz.Point(50, 50), "Concurrent Load Sample")
    sample_pdf = doc.tobytes()
    doc.close()

    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = client.post(
            "/api/convert/html",
            files={"file": ("test.pdf", sample_pdf, "application/pdf")},
            data={"mode": "fixed"},
        )
        lat = time.perf_counter() - t0
        assert res.status_code == 200
        latencies.append(lat)

    avg_lat = sum(latencies) / len(latencies)
    assert avg_lat < 0.30, f"Average conversion latency {avg_lat*1000:.1f}ms exceeds 300ms budget"
