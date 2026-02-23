"""Pluggable memory backend interfaces and implementations."""

from .base import (
    BackendHealth,
    ForgetResult,
    IngestResult,
    MemoryBackend,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)
from .factory import MemoryBackendFactory
from .ghostkg_backend import GhostKGMemoryBackend
from .native_backend import NativeMemoryBackend
from .none_backend import NoMemoryBackend

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
