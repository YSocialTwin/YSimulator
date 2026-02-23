"""Factory for selecting pluggable memory backend implementations."""

from __future__ import annotations

from typing import Any

from YSimulator.YServer.services.memory_backends.base import MemoryBackend
from YSimulator.YServer.services.memory_backends.ghostkg_backend import GhostKGMemoryBackend
from YSimulator.YServer.services.memory_backends.native_backend import NativeMemoryBackend
from YSimulator.YServer.services.memory_backends.none_backend import NoMemoryBackend


class MemoryBackendFactory:
    """Resolves backend string to concrete backend implementation."""

    @staticmethod
    def create(
        backend: str,
        logger: Any = None,
        backend_config: dict | None = None,
        engine: Any = None,
    ) -> MemoryBackend:
        backend_normalized = backend.lower().strip()
        backend_config = backend_config or {}

        if backend_normalized == "none":
            return NoMemoryBackend()
        if backend_normalized == "native":
            return NativeMemoryBackend(
                backend_config=backend_config,
                engine=engine,
                logger=logger,
            )
        if backend_normalized == "ghostkg":
            return GhostKGMemoryBackend(
                backend_config=backend_config,
                engine=engine,
                logger=logger,
            )

        raise ValueError(f"Unknown memory backend: {backend}")
