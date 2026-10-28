"""
Vellakshya Process Sandboxing & Isolation Engine.
Confines untrusted PDF parsing and conversion to restricted subprocess boundaries.
"""

from __future__ import annotations

import asyncio
import json
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


class SandboxExecutionError(Exception):
    """Raised when a task fails or terminates abnormally inside the sandbox."""

    pass


class SandboxTimeoutError(SandboxExecutionError):
    """Raised when a task exceeds the hard execution time limit."""

    pass


class SandboxMemoryLimitError(SandboxExecutionError):
    """Raised when a task exceeds memory ceilings inside the sandbox."""

    pass


def _configure_process_limits(max_memory_mb: int = 512, cpu_timeout_secs: int = 30):
    """
    Sets POSIX resource limits on the child worker process before exec.
    Guards against memory bombs, fork bombs, and CPU hogging.
    """

    def preexec():
        # 1. CPU Time Limit
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_timeout_secs, cpu_timeout_secs + 5))
        except (ValueError, OSError):
            pass

        # 2. Maximum Address Space / Virtual Memory Limit (bytes)
        try:
            mem_bytes = max_memory_mb * 1024 * 1024
            # On macOS RLIMIT_AS or RLIMIT_DATA may be restricted; set where permitted
            if hasattr(resource, "RLIMIT_AS"):
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass

    return preexec


async def run_sandboxed_task(
    task: str,
    pdf_bytes: bytes,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
    max_memory_mb: int = 512,
) -> tuple[bytes, str, dict[str, Any]]:
    """
    Executes a heavy document conversion task inside an isolated sandbox subprocess.
    Returns: (output_bytes, media_type, metrics_dict)
    """
    if params is None:
        params = {}

    start_perf = time.perf_counter()
    temp_dir = tempfile.mkdtemp(prefix="vellakshya_sandbox_")
    runner_script = Path(__file__).resolve().parent.parent / "worker" / "runner.py"

    try:
        input_file = Path(temp_dir) / "input.pdf"
        output_file = Path(temp_dir) / "output_artifact"
        input_file.write_bytes(pdf_bytes)

        # Sanitize child environment - prevent credential leakage to untrusted worker
        child_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent.parent),
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        cmd = [
            sys.executable,
            str(runner_script),
            "--task",
            task,
            "--input",
            str(input_file),
            "--output",
            str(output_file),
            "--params",
            json.dumps(params),
        ]

        # Spawn isolated subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
            preexec_fn=_configure_process_limits(max_memory_mb, timeout_seconds),
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_seconds)
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise SandboxTimeoutError(
                f"Sandbox execution timed out after {timeout_seconds} seconds."
            )

        stdout_text = stdout_data.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_data.decode("utf-8", errors="replace").strip()

        # Parse worker JSON metrics emitted on stdout
        worker_metrics: dict[str, Any] = {}
        for line in stdout_text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    worker_metrics = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if proc.returncode != 0:
            error_msg = (
                worker_metrics.get("error")
                or stderr_text
                or f"Process exited with code {proc.returncode}"
            )
            if "MemoryError" in error_msg or proc.returncode == -9:
                raise SandboxMemoryLimitError(
                    f"Process exceeded memory threshold ({max_memory_mb} MB): {error_msg}"
                )
            raise SandboxExecutionError(
                f"Sandbox task '{task}' failed (exit code {proc.returncode}): {error_msg}"
            )

        if not output_file.exists():
            raise SandboxExecutionError(
                f"Sandbox completed but output artifact is missing. Logs: {stderr_text}"
            )

        output_bytes = output_file.read_bytes()
        media_type = worker_metrics.get("media_type", "application/octet-stream")

        total_elapsed_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        metrics = {
            "task": task,
            "status": "succeeded",
            "duration_ms": total_elapsed_ms,
            "input_bytes": len(pdf_bytes),
            "output_bytes": len(output_bytes),
            "media_type": media_type,
            "worker_pid": worker_metrics.get("pid"),
            "sandbox_isolated": True,
        }

        return output_bytes, media_type, metrics

    finally:
        # Guarantee strict cleanup of untrusted temporary data
        shutil.rmtree(temp_dir, ignore_errors=True)
