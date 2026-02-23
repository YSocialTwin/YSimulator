"""
Memory service with pluggable backend support.

Phase 1 integrates backend selection/wiring while preserving no-op behavior.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.services.memory_backends import (
    ForgetResult,
    IngestResult,
    MemoryBackendFactory,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)
from YSimulator.YServer.services.memory_config import resolve_memory_settings


class MemoryService:
    """Facade over configurable memory backend implementations."""

    def __init__(self, simulation_config: Optional[Dict[str, Any]] = None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.simulation_config = simulation_config or {}

        settings = resolve_memory_settings(self.simulation_config)
        self.settings = settings
        self.backend = MemoryBackendFactory.create(settings.backend, logger=self.logger)

    def initialize(self, simulation_context: Optional[Dict[str, Any]] = None) -> None:
        context = simulation_context or {}
        self.backend.initialize(context)
        self.logger.info(f"Memory backend initialized: {self.backend.name}")

    def get_backend_name(self) -> str:
        """Return selected backend name."""
        return self.backend.name

    def ingest_event(
        self, agent_id: str, event: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> IngestResult:
        ctx = context or {}
        try:
            return self.backend.ingest_event(agent_id, event, ctx)
        except Exception as e:
            self.logger.error(
                f"Memory ingest failed for backend {self.backend.name}: {e}",
                extra={"extra_data": {"backend": self.backend.name, "agent_id": agent_id}},
            )
            return IngestResult(success=False, error=str(e))

    def retrieve(
        self, agent_id: str, query: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> List[MemoryItemDTO]:
        ctx = context or {}
        memory_query = MemoryQuery(
            topic=query.get("topic"),
            target_user_id=query.get("target_user_id"),
            thread_id=query.get("thread_id"),
            action_type=query.get("action_type"),
            max_items=int(query.get("max_items", 5)),
            metadata=query.get("metadata", {}),
        )
        try:
            return self.backend.retrieve(agent_id, memory_query, ctx)
        except Exception as e:
            self.logger.error(
                f"Memory retrieval failed for backend {self.backend.name}: {e}",
                extra={"extra_data": {"backend": self.backend.name, "agent_id": agent_id}},
            )
            return []

    def reinforce(
        self, agent_id: str, memory_ids: List[str], context: Optional[Dict[str, Any]] = None
    ) -> ReinforceResult:
        ctx = context or {}
        try:
            return self.backend.reinforce(agent_id, memory_ids, ctx)
        except Exception as e:
            self.logger.error(
                f"Memory reinforce failed for backend {self.backend.name}: {e}",
                extra={"extra_data": {"backend": self.backend.name, "agent_id": agent_id}},
            )
            return ReinforceResult(success=False, error=str(e))

    def forget_cycle(self, context: Optional[Dict[str, Any]] = None) -> ForgetResult:
        ctx = context or {}
        try:
            return self.backend.forget_cycle(ctx)
        except Exception as e:
            self.logger.error(
                f"Memory forget cycle failed for backend {self.backend.name}: {e}",
                extra={"extra_data": {"backend": self.backend.name}},
            )
            return ForgetResult(success=False, error=str(e))

    def health_check(self) -> Dict[str, Any]:
        """Return backend health as dictionary for RPC compatibility."""
        health = self.backend.health_check()
        return {"ok": health.ok, "backend": health.backend, "details": health.details}
