"""
Backend-agnostic memory interface for pluggable memory systems.

This module defines the stable contract that all memory backends must implement:
- none (no-op)
- native (YSimulator implementation)
- ghostkg (external adapter)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MemoryQuery:
    """Backend-neutral query payload for memory retrieval."""

    topic: Optional[str] = None
    target_user_id: Optional[str] = None
    thread_id: Optional[str] = None
    action_type: Optional[str] = None
    max_items: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryItemDTO:
    """Backend-neutral memory item returned to callers."""

    memory_id: str
    memory_text: str
    relevance_score: float
    confidence: float = 0.0
    strength: float = 0.0
    sentiment: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestResult:
    """Result of memory event ingestion."""

    success: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class ReinforceResult:
    """Result of memory reinforcement operation."""

    success: bool
    reinforced: int = 0
    skipped: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class ForgetResult:
    """Result of forgetting cycle."""

    success: bool
    decayed: int = 0
    soft_forgotten: int = 0
    hard_deleted: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class BackendHealth:
    """Backend health and diagnostics payload."""

    ok: bool
    backend: str
    details: Dict[str, Any] = field(default_factory=dict)


class MemoryBackend(ABC):
    """Stable pluggable backend contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend name: none/native/ghostkg."""

    @abstractmethod
    def initialize(self, simulation_context: Dict[str, Any]) -> None:
        """Initialize backend-specific state."""

    @abstractmethod
    def ingest_event(
        self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]
    ) -> IngestResult:
        """Ingest a simulation event into backend memory state."""

    @abstractmethod
    def retrieve(
        self, agent_id: str, query: MemoryQuery, context: Dict[str, Any]
    ) -> List[MemoryItemDTO]:
        """Retrieve backend memory items for action context building."""

    @abstractmethod
    def reinforce(
        self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]
    ) -> ReinforceResult:
        """Reinforce used memories."""

    @abstractmethod
    def forget_cycle(self, context: Dict[str, Any]) -> ForgetResult:
        """Run backend forgetting cycle."""

    @abstractmethod
    def health_check(self) -> BackendHealth:
        """Return backend health state."""
