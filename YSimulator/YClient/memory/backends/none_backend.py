"""No-op memory backend for `none` mode."""

from __future__ import annotations

from typing import Any, Dict, List

from YSimulator.YClient.memory.backends.base import (
    BackendHealth,
    ForgetResult,
    IngestResult,
    MemoryBackend,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)


class NoMemoryBackend(MemoryBackend):
    """No-op backend that safely disables memory operations."""

    @property
    def name(self) -> str:
        return "none"

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
        return BackendHealth(ok=True, backend=self.name, details={"mode": "disabled"})
