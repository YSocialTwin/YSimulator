"""Skeleton GhostKG adapter backend.

Phase 1 only adds the backend scaffold and health signaling.
"""

from __future__ import annotations

from typing import Any, Dict, List

from YSimulator.YServer.services.memory_backends.base import (
    BackendHealth,
    ForgetResult,
    IngestResult,
    MemoryBackend,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)


class GhostKGMemoryBackend(MemoryBackend):
    """Placeholder adapter for GhostKG-backed memory."""

    def __init__(self, backend_config: Dict[str, Any], logger: Any = None):
        self.config = backend_config or {}
        self.logger = logger

    @property
    def name(self) -> str:
        return "ghostkg"

    def initialize(self, simulation_context: Dict[str, Any]) -> None:
        return None

    def ingest_event(
        self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]
    ) -> IngestResult:
        return IngestResult(success=True, skipped=1)

    def retrieve(
        self, agent_id: str, query: MemoryQuery, context: Dict[str, Any]
    ) -> List[MemoryItemDTO]:
        return []

    def reinforce(
        self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]
    ) -> ReinforceResult:
        return ReinforceResult(success=True, skipped=len(memory_ids))

    def forget_cycle(self, context: Dict[str, Any]) -> ForgetResult:
        return ForgetResult(success=True)

    def health_check(self) -> BackendHealth:
        return BackendHealth(
            ok=True,
            backend=self.name,
            details={"status": "phase_1_scaffold", "implemented": False},
        )
