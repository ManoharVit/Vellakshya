"""
Vellakshya Asynchronous Job Queue System.
Backed by Valkey 9.x (BSD-3-Clause) / Redis with seamless local fallback to Fakeredis.
Orchestrates worker jobs and offloads untrusted PDF processing to the sandbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import fakeredis
import redis

from app.services.sandbox import (
    SandboxExecutionError,
    SandboxMemoryLimitError,
    SandboxTimeoutError,
    run_sandboxed_task,
)

logger = logging.getLogger("vellakshya.queue")

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "data" / "job_artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_url(url: str) -> str:
    """Masks credentials from connection URLs to prevent secret leakage in logs."""
    try:
        parts = urlsplit(url)
        if parts.password or parts.username:
            netloc = parts.netloc.split("@")[-1]
            return urlunsplit(
                (parts.scheme, f"***@{netloc}", parts.path, parts.query, parts.fragment)
            )
    except Exception:
        pass
    return url


@dataclass
class JobInfo:
    id: str
    task: str
    status: str  # "queued", "processing", "succeeded", "failed", "cancelled"
    progress: int = 0  # 0 to 100
    stage: str = "queued"
    filename: str = "document.pdf"
    output_filename: str = ""
    media_type: str = "application/octet-stream"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    owner_id: str = "anonymous"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobQueue:
    """
    Asynchronous job dispatcher and worker pool.
    Supports Valkey 9.x (BSD) and Redis protocols transparently.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = (
            redis_url
            or os.environ.get("VALKEY_URL")
            or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )
        self.client: redis.Redis = self._init_redis_client()
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running: bool = False
        self._input_cache: dict[str, bytes] = {}  # In-memory transient buffer for input payloads

    def _init_redis_client(self) -> redis.Redis:
        """
        Attempts live Valkey/Redis connection; falls back to Fakeredis seamlessly.
        """
        try:
            r = redis.from_url(self.redis_url, socket_connect_timeout=1.0)
            r.ping()
            logger.info(
                "Connected to live Valkey/Redis server at %s", _sanitize_url(self.redis_url)
            )
            return r
        except Exception as err:
            logger.info(
                "Valkey/Redis server unavailable (%s); using in-memory Fakeredis backend", err
            )
            return fakeredis.FakeRedis()

    def start_worker(self):
        """Starts the background worker queue processor."""
        if not self._is_running:
            self._is_running = True
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            logger.info("Vellakshya Job Queue worker started.")

    async def stop_worker(self):
        """Stops the background worker loop gracefully."""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("Vellakshya Job Queue worker stopped.")

    def _job_key(self, job_id: str) -> str:
        return f"job:{job_id}"

    def _save_job_state(self, job: JobInfo):
        key = self._job_key(job.id)
        raw_data = json.dumps(job.to_dict())
        self.client.set(key, raw_data)

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        key = self._job_key(job_id)
        raw_data = self.client.get(key)
        if not raw_data:
            return None
        data = json.loads(raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data)
        return JobInfo(**data)

    def list_jobs(self, limit: int = 50, owner_id: Optional[str] = None) -> list[JobInfo]:
        job_ids = self.client.lrange("jobs:history", 0, limit * 2)
        results: list[JobInfo] = []
        for jid in job_ids:
            jid_str = jid.decode("utf-8") if isinstance(jid, bytes) else str(jid)
            job = self.get_job(jid_str)
            if job:
                if owner_id is not None and job.owner_id != owner_id:
                    continue
                results.append(job)
                if len(results) >= limit:
                    break
        return results

    async def enqueue(
        self,
        task: str,
        pdf_bytes: bytes,
        filename: str = "document.pdf",
        params: Optional[dict[str, Any]] = None,
        owner_id: str = "anonymous",
    ) -> JobInfo:
        if params is None:
            params = {}

        job_id = str(uuid.uuid4())
        base_name = Path(filename).stem

        # Determine target output filename
        if task in ("html_fixed", "html_semantic"):
            out_filename = f"{base_name}.html"
            media_type = "text/html"
        elif task == "images_zip":
            out_filename = f"{base_name}_images.zip"
            media_type = "application/zip"
        elif task == "markdown":
            out_filename = f"{base_name}.md"
            media_type = "text/markdown"
        else:
            out_filename = f"{base_name}_output.bin"
            media_type = "application/octet-stream"

        job = JobInfo(
            id=job_id,
            task=task,
            status="queued",
            progress=0,
            stage="queued",
            filename=filename,
            output_filename=out_filename,
            media_type=media_type,
            created_at=time.time(),
            owner_id=owner_id,
        )

        # Cache input bytes for worker execution
        self._input_cache[job_id] = pdf_bytes

        # Store initial job state in Redis
        self._save_job_state(job)
        self.client.lpush("jobs:history", job_id)

        # Enqueue job ID with parameters
        queue_payload = json.dumps({"job_id": job_id, "params": params})
        self.client.lpush("jobs:queue", queue_payload)

        safe_log_name = Path(filename).name[:24]
        logger.info("Enqueued job %s (%s) for file %s", job_id, task, safe_log_name)
        return job

    async def _process_queue_loop(self):
        while self._is_running:
            try:
                # Non-blocking pop from queue
                raw_item = self.client.rpop("jobs:queue")
                if not raw_item:
                    await asyncio.sleep(0.15)
                    continue

                item = json.loads(
                    raw_item.decode("utf-8") if isinstance(raw_item, bytes) else raw_item
                )
                job_id = item["job_id"]
                params = item.get("params", {})

                job = self.get_job(job_id)
                if not job or job.status == "cancelled":
                    continue

                # Execute job in sandbox
                await self._execute_job(job, params)

            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Queue loop error: %s", err, exc_info=True)
                await asyncio.sleep(0.5)

    async def _execute_job(self, job: JobInfo, params: dict[str, Any]):
        job.status = "processing"
        job.stage = "sandbox_initializing"
        job.progress = 15
        job.started_at = time.time()
        self._save_job_state(job)

        pdf_bytes = self._input_cache.pop(job.id, None)
        if not pdf_bytes:
            job.status = "failed"
            job.stage = "failed"
            job.error = "Input payload expired or unavailable."
            job.completed_at = time.time()
            self._save_job_state(job)
            return

        try:
            job.stage = "sandbox_executing"
            job.progress = 40
            self._save_job_state(job)

            # Delegate to isolated sandbox subprocess
            output_bytes, media_type, metrics = await run_sandboxed_task(
                task=job.task,
                pdf_bytes=pdf_bytes,
                params=params,
                timeout_seconds=30,
                max_memory_mb=512,
            )

            job.stage = "persisting_artifact"
            job.progress = 85
            self._save_job_state(job)

            # Persist output artifact
            artifact_dir = ARTIFACTS_DIR / job.id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_dir / job.output_filename
            artifact_path.write_bytes(output_bytes)

            # Finalize succeeded state
            job.status = "succeeded"
            job.stage = "completed"
            job.progress = 100
            job.completed_at = time.time()
            job.duration_ms = metrics.get("duration_ms", 0.0)
            job.metrics = metrics
            job.media_type = media_type
            self._save_job_state(job)
            logger.info("Job %s succeeded in %.2f ms", job.id, job.duration_ms)

        except SandboxTimeoutError as err:
            job.status = "failed"
            job.stage = "timeout"
            job.error = str(err)
            job.completed_at = time.time()
            self._save_job_state(job)
            logger.warning("Job %s timed out: %s", job.id, err)

        except SandboxMemoryLimitError as err:
            job.status = "failed"
            job.stage = "out_of_memory"
            job.error = str(err)
            job.completed_at = time.time()
            self._save_job_state(job)
            logger.warning("Job %s hit memory limit: %s", job.id, err)

        except SandboxExecutionError as err:
            job.status = "failed"
            job.stage = "execution_error"
            job.error = str(err)
            job.completed_at = time.time()
            self._save_job_state(job)
            logger.warning("Job %s failed: %s", job.id, err)

        except Exception as err:
            job.status = "failed"
            job.stage = "system_error"
            job.error = f"Unhandled error: {err}"
            job.completed_at = time.time()
            self._save_job_state(job)
            logger.error("Job %s unhandled error: %s", job.id, err, exc_info=True)

    def get_job_artifact(self, job_id: str) -> Optional[tuple[bytes, str, str]]:
        job = self.get_job(job_id)
        if not job or job.status != "succeeded":
            return None

        artifact_path = ARTIFACTS_DIR / job.id / job.output_filename
        if not artifact_path.exists():
            return None

        return artifact_path.read_bytes(), job.media_type, job.output_filename

    def cancel_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if not job:
            return False
        if job.status in ("succeeded", "failed", "cancelled"):
            return False

        job.status = "cancelled"
        job.stage = "cancelled"
        job.completed_at = time.time()
        self._save_job_state(job)
        self._input_cache.pop(job_id, None)
        return True


# Global Singleton Job Queue
queue_instance = JobQueue()
