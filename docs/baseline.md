# Vellakshya Baseline Metrics (v0-baseline)

Recorded: 28 October 2026
Git Tag: `v0-baseline`
Git Commit: `38efd7f`

## Test Suite Baseline
- **Framework:** `pytest 8.3.5` on `Python 3.12.2`
- **Total Test Cases:** 111 tests
- **Passed:** 111 (100%)
- **Failed:** 0
- **Errors:** 0
- **Duration:** 29.64s
- **Warning Count:** 10 deprecation warnings (Starlette `anyio.abc.BlockingPortal`, FastAPI `on_event` handlers to migrate to `lifespan`).

## Application Startup Time
- **FastAPI App Import & Initialization Time:** ~784.92 ms
- **Health Check Endpoint Latency:** < 5 ms

## Environment & Dependency Baseline
- **PyMuPDF Version:** `1.25.5`
- **FastAPI Version:** `0.119.1`
- **Starlette Version:** `0.48.0`
- **Uvicorn Version:** `0.32.1`
- **Pydantic Version:** `2.14.1`
- **Base Docker Image:** `python:3.12-slim` (contains `build-essential` and `libmupdf-dev`, slated for removal in Step 1 to shrink image size).
