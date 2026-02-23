"""Pluggable memory backend interfaces and implementations (client-owned)."""

from YSimulator.YClient.memory.backends.base import (
    BackendHealth,
    ForgetResult,
    IngestResult,
    MemoryBackend,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)
from YSimulator.YClient.memory.backends.factory import MemoryBackendFactory
from YSimulator.YClient.memory.backends.ghostkg_backend import GhostKGMemoryBackend
from YSimulator.YClient.memory.backends.native_backend import NativeMemoryBackend
from YSimulator.YClient.memory.backends.none_backend import NoMemoryBackend

__all__ = [
    "MemoryBackend",
    "MemoryQuery",
    "MemoryItemDTO",
    "IngestResult",
    "ReinforceResult",
    "ForgetResult",
    "BackendHealth",
    "MemoryBackendFactory",
    "NoMemoryBackend",
    "NativeMemoryBackend",
    "GhostKGMemoryBackend",
]
