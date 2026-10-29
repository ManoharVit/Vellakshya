# 6. PyMuPDF Execution in Process Pool Isolation

## Status
Accepted

## Context
PyMuPDF is a Python C-extension binding directly to the underlying MuPDF C library. The official PyMuPDF documentation explicitly states that the library does not support multithreading across concurrent threads sharing documents, warning that concurrent thread execution may cause memory corruption, segmentation faults, or silent crashes. Furthermore, heavy rasterization of 500-page enterprise documents blocks the Python Global Interpreter Lock (GIL) and stalls the FastAPI asyncio event loop.

## Decision
All CPU-intensive PyMuPDF operations (rasterization, text extraction, page parsing, and physical redaction) execute in an isolated process pool worker off the main FastAPI event loop using `asyncio.to_thread` with process-isolated worker boundaries.

## Consequences
- **Positive:** Immune to thread-safety segmentation faults.
- **Positive:** FastAPI event loop remains responsive (sub-10ms response times for health checks and WebSocket pings even during 50 MB document processing).
- **Negative:** Minor IPC serialization overhead passing PDF byte buffers across process boundaries.
