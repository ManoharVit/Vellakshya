"""
Production telemetry, structured audit logging, token cost tracking, and rate limiting.
Ensures zero PII or raw document text is ever written to telemetry logs.
Gracefully degrades when Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger("vellakshya.ai.telemetry")
logger.setLevel(logging.INFO)

# Token pricing approximations per 1M tokens ($0.075 input, $0.30 output for lightweight models)
COST_PER_PROMPT_TOKEN = 0.075 / 1_000_000.0
COST_PER_COMPLETION_TOKEN = 0.30 / 1_000_000.0

# In-memory sliding window fallback for rate limiting
_MEMORY_RATE_LIMITS: dict[str, list[float]] = {}
_MEMORY_CACHE: dict[str, tuple[float, str]] = {}


def log_ai_transaction(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    status: str = "success",
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Logs structured telemetry event without logging any document text or query payloads.
    Computes estimated cost in USD.
    """
    tid = trace_id or f"tr_{uuid.uuid4().hex[:12]}"
    estimated_cost = round(
        (prompt_tokens * COST_PER_PROMPT_TOKEN) + (completion_tokens * COST_PER_COMPLETION_TOKEN),
        6,
    )

    telemetry_record = {
        "event": "ai_rag_transaction",
        "trace_id": tid,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": estimated_cost,
        "latency_ms": latency_ms,
        "status": status,
        "timestamp": time.time(),
    }

    logger.info(json.dumps(telemetry_record))
    return telemetry_record


def check_rate_limit(
    client_ip: str,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> bool:
    """
    Sliding window rate limiter.
    Returns True if allowed, False if rate limit is exceeded.
    Degrades to in-memory tracking if Redis is unreachable.
    """
    now = time.time()
    cutoff = now - window_seconds

    # Attempt Redis sliding window if redis configured
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url, socket_timeout=1)
            key = f"rl:{client_ip}"
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = pipe.execute()
            req_count = int(results[2])
            return bool(req_count <= max_requests)
        except Exception:
            pass  # Fall back to local memory tracking

    # In-memory fallback
    timestamps = _MEMORY_RATE_LIMITS.setdefault(client_ip, [])
    # Evict expired
    _MEMORY_RATE_LIMITS[client_ip] = [t for t in timestamps if t > cutoff]
    if len(_MEMORY_RATE_LIMITS[client_ip]) >= max_requests:
        return False
    _MEMORY_RATE_LIMITS[client_ip].append(now)
    return True


def get_cached_answer(cache_key: str) -> Optional[str]:
    """Retrieves cached response string. Bypasses on cache miss or Redis error."""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url, socket_timeout=1)
            raw_val = r.get(f"cache:{cache_key}")
            if raw_val is not None:
                return raw_val.decode("utf-8") if isinstance(raw_val, bytes) else str(raw_val)
        except Exception:
            pass

    # In-memory check
    if cache_key in _MEMORY_CACHE:
        expires_at, mem_val = _MEMORY_CACHE[cache_key]
        if time.time() < expires_at:
            return mem_val
        del _MEMORY_CACHE[cache_key]
    return None


def set_cached_answer(cache_key: str, answer_json: str, ttl_seconds: int = 86400) -> None:
    """Sets cached response string. Bypasses cleanly on Redis errors."""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url, socket_timeout=1)
            r.setex(f"cache:{cache_key}", ttl_seconds, answer_json)
            return
        except Exception:
            pass

    # In-memory store
    _MEMORY_CACHE[cache_key] = (time.time() + ttl_seconds, answer_json)
