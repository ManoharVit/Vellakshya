"""
Embedding service abstraction.
Uses a pinned embedding model. Provides deterministic embedding generation for testing
and cloud provider execution when configured.
"""

from __future__ import annotations

import hashlib
import math
import os

# Pinned embedding model per architectural lock
DEFAULT_EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_EMBEDDING_DIM = 768


def generate_deterministic_embedding(text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """
    Generates a deterministic, normalized vector for offline testing, CI,
    and fallback when no external cloud credentials are provided.
    """
    vec = [0.0] * dim
    clean_text = text.lower().strip()
    words = clean_text.split()

    if not words:
        vec[0] = 1.0
        return vec

    for word in words:
        # Hash each token into the vector dimensions
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        slot = h % dim
        weight = 1.0 + (h % 100) / 100.0
        vec[slot] += weight

    # L2-normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [round(v / norm, 6) for v in vec]
    else:
        vec[0] = 1.0
    return vec


def get_embedding(
    text: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[float]:
    """
    Computes embedding vector for input text.
    Uses Gemini API if GEMINI_API_KEY is present; otherwise computes deterministic local vector.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            # When google-genai / google-generativeai is available, query embedding endpoint
            import json
            import urllib.request

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={api_key}"
            payload = json.dumps({"content": {"parts": [{"text": text[:2000]}]}}).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                values = res_data.get("embedding", {}).get("values", [])
                if values and len(values) == dim:
                    return [round(float(v), 6) for v in values]
        except Exception:
            pass  # Fall back to deterministic local embedding on network or auth failure

    return generate_deterministic_embedding(text, dim=dim)
