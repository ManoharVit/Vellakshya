"""
Integration and Unit Tests for Vellakshya Asynchronous Worker Queue & Process Sandbox.
Validates isolated process boundaries, job lifecycle, resource limits, and API contracts.
"""

import asyncio
import io
import time

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.queue import queue_instance
from app.services.sandbox import (
    SandboxExecutionError,
    run_sandboxed_task,
)


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "Vellakshya Sandboxed Worker Test Document", fontsize=16)
    page.insert_text(
        (50, 140), "Verifying isolated process execution and Redis job queue.", fontsize=11
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# -------------------------------------------------------------
# 1. PROCESS SANDBOX UNIT TESTS
# -------------------------------------------------------------


def test_sandbox_runs_html_fixed_in_isolated_process(sample_pdf_bytes):
    output_bytes, media_type, metrics = asyncio.run(
        run_sandboxed_task(
            task="html_fixed",
            pdf_bytes=sample_pdf_bytes,
            params={"title": "TestDoc"},
            timeout_seconds=10,
        )
    )

    assert media_type == "text/html"
    assert b"<!DOCTYPE html>" in output_bytes
    assert b"Vellakshya Sandboxed Worker" in output_bytes
    assert metrics["status"] == "succeeded"
    assert metrics["sandbox_isolated"] is True
    assert metrics["worker_pid"] is not None
    assert metrics["duration_ms"] > 0


def test_sandbox_runs_images_zip_in_isolated_process(sample_pdf_bytes):
    output_bytes, media_type, metrics = asyncio.run(
        run_sandboxed_task(
            task="images_zip",
            pdf_bytes=sample_pdf_bytes,
            params={"dpi": 72, "format": "png"},
            timeout_seconds=10,
        )
    )

    assert media_type == "application/zip"
    assert output_bytes.startswith(b"PK")  # ZIP magic bytes
    assert metrics["status"] == "succeeded"
    assert metrics["output_bytes"] > 0


def test_sandbox_rejects_corrupted_input():
    corrupted_bytes = b"NOT_A_VALID_PDF_HEADER_1234567890"

    with pytest.raises(SandboxExecutionError) as exc_info:
        asyncio.run(
            run_sandboxed_task(
                task="html_fixed",
                pdf_bytes=corrupted_bytes,
                timeout_seconds=5,
            )
        )

    assert "failed" in str(exc_info.value).lower() or "syntax" in str(exc_info.value).lower()


# -------------------------------------------------------------
# 2. JOB QUEUE ASYNC LIFECYCLE TESTS
# -------------------------------------------------------------


def test_job_queue_enqueue_and_process(sample_pdf_bytes):
    async def _test():
        # Ensure worker is running in this event loop
        queue_instance.start_worker()
        try:
            # Enqueue task
            job = await queue_instance.enqueue(
                task="html_semantic",
                pdf_bytes=sample_pdf_bytes,
                filename="lifecycle_test.pdf",
                params={"title": "LifecycleTest"},
            )

            assert job.status == "queued"
            assert job.id is not None
            assert job.task == "html_semantic"

            # Poll until completed (timeout 10s)
            start_time = time.time()
            completed_job = None
            while time.time() - start_time < 10:
                await asyncio.sleep(0.2)
                j = queue_instance.get_job(job.id)
                if j and j.status in ("succeeded", "failed"):
                    completed_job = j
                    break

            assert completed_job is not None, "Job did not complete within timeout"
            assert completed_job.status == "succeeded"
            assert completed_job.progress == 100
            assert completed_job.stage == "completed"
            assert completed_job.duration_ms is not None
            assert completed_job.duration_ms > 0

            # Retrieve output artifact
            artifact = queue_instance.get_job_artifact(job.id)
            assert artifact is not None
            content_bytes, media_type, out_filename = artifact
            assert media_type == "text/html"
            assert b"LifecycleTest" in content_bytes or b"Vellakshya" in content_bytes
        finally:
            await queue_instance.stop_worker()

    asyncio.run(_test())


def test_job_queue_cancellation():
    async def _test():
        job = await queue_instance.enqueue(
            task="html_fixed",
            pdf_bytes=b"%PDF-1.4 dummy placeholder",
            filename="cancel_test.pdf",
        )

        success = queue_instance.cancel_job(job.id)
        assert success is True

        cancelled_job = queue_instance.get_job(job.id)
        assert cancelled_job is not None
        assert cancelled_job.status == "cancelled"

    asyncio.run(_test())


# -------------------------------------------------------------
# 3. FASTAPI REST CONTRACT TESTS FOR ASYNC JOBS
# -------------------------------------------------------------


def test_api_jobs_html_lifecycle(client, sample_pdf_bytes):
    # 1. Enqueue job via HTTP POST
    response = client.post(
        "/api/jobs/convert/html",
        files={"file": ("api_test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        data={"mode": "fixed"},
    )
    assert response.status_code == 202
    data = response.json()
    job_id = data["job_id"]
    assert data["status"] == "queued"
    assert data["task"] == "html_fixed"

    # 2. Poll job status
    poll_success = False
    for _ in range(30):
        time.sleep(0.25)
        status_res = client.get(f"/api/jobs/{job_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        if status_data["status"] == "succeeded":
            poll_success = True
            assert status_data["progress"] == 100
            assert status_data["metrics"]["sandbox_isolated"] is True
            break
        elif status_data["status"] == "failed":
            pytest.fail(f"Job failed unexpectedly: {status_data.get('error')}")

    assert poll_success, "Job polling timed out"

    # 3. Retrieve result artifact
    result_res = client.get(f"/api/jobs/{job_id}/result")
    assert result_res.status_code == 200
    assert "text/html" in result_res.headers.get("content-type", "")
    assert "Vellakshya" in result_res.text


def test_api_jobs_images_lifecycle(client, sample_pdf_bytes):
    # Enqueue image conversion job
    response = client.post(
        "/api/jobs/convert/images",
        files={"file": ("images_test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        data={"dpi": "72", "format": "png"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Poll status
    for _ in range(30):
        time.sleep(0.25)
        status_res = client.get(f"/api/jobs/{job_id}")
        if status_res.json()["status"] == "succeeded":
            break

    # Download ZIP result
    result_res = client.get(f"/api/jobs/{job_id}/result")
    assert result_res.status_code == 200
    assert result_res.headers.get("content-type") == "application/zip"
    assert result_res.content.startswith(b"PK")


def test_api_jobs_invalid_file_rejected(client):
    response = client.post(
        "/api/jobs/convert/html",
        files={"file": ("bad.exe", io.BytesIO(b"MZ\x90\x00NotAPdf"), "application/octet-stream")},
        data={"mode": "fixed"},
    )
    assert response.status_code == 400
    assert "valid pdf" in response.json()["detail"].lower()


def test_api_jobs_not_found(client):
    response = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
