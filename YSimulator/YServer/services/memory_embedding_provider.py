"""Embedding utilities for server-side memory retrieval.

This module isolates embedding backend imports from memory_service so the
memory service itself stays free of direct model SDK imports.
"""

from __future__ import annotations

import math
import re
import threading
from typing import List, Optional


def cosine_similarity(vec_a, vec_b) -> float:
    if not isinstance(vec_a, list) or not isinstance(vec_b, list):
        return 0.0
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        try:
            fa = float(a)
            fb = float(b)
        except Exception:
            continue
        dot += fa * fb
        norm_a += fa * fa
        norm_b += fb * fb
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return float(dot / (math.sqrt(norm_a) * math.sqrt(norm_b)))


def lexical_relevance(query_text: str, memory_text: str) -> float:
    if not isinstance(query_text, str) or not isinstance(memory_text, str):
        return 0.0
    q_tokens = set(re.findall(r"[a-z0-9]+", query_text.lower()))
    m_tokens = set(re.findall(r"[a-z0-9]+", memory_text.lower()))
    if not q_tokens or not m_tokens:
        return 0.0
    overlap = len(q_tokens & m_tokens)
    if overlap <= 0:
        return 0.0
    return float(overlap / math.sqrt(len(q_tokens) * len(m_tokens)))


class MemoryEmbeddingProvider:
    """Lazy embedding provider backed by Ollama."""

    def __init__(self, model_name: str, host: str):
        self.model_name = str(model_name or "").strip()
        self.host = str(host or "").strip().rstrip("/")
        self._client = None
        self._available = None
        self._lock = threading.Lock()
        self._last_error = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._ensure_client()
        return bool(self._available)

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def _ensure_client(self):
        if self._available is False:
            return None
        if self._client is not None:
            return self._client

        with self._lock:
            if self._available is False:
                return None
            if self._client is not None:
                return self._client
            if not self.model_name or not self.host:
                self._available = False
                self._last_error = "embedding service not configured"
                return None
            try:
                from ollama import Client as OllamaClient
            except Exception as exc:
                self._available = False
                self._last_error = f"ollama import failed: {exc}"
                return None
            try:
                client = OllamaClient(host=self.host)
                client.embed(model=self.model_name, input="test")
                self._client = client
                self._available = True
            except Exception as exc:
                self._client = None
                self._available = False
                self._last_error = f"ollama connect/encode failed ({self.model_name}): {exc}"
            return self._client

    def encode(self, text: str) -> Optional[List[float]]:
        if not isinstance(text, str) or not text.strip():
            return None
        client = self._ensure_client()
        if client is None:
            return None
        try:
            response = client.embed(model=self.model_name, input=text.strip())
            rows = getattr(response, "embeddings", None)
            if not isinstance(rows, list) or not rows:
                return None
            vec = rows[0]
            if not isinstance(vec, list):
                return None
            return [float(value) for value in vec]
        except Exception:
            return None
