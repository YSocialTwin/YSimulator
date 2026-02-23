"""GhostKG adapter backend for pluggable memory."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

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
    """Adapter that bridges YSimulator memory contract to GhostKG APIs."""

    def __init__(self, backend_config: Dict[str, Any], logger: Any = None):
        self.config = backend_config or {}
        self.logger = logger or logging.getLogger(__name__)
        self.manager = None
        self.rating = None
        self._available = False
        self._initialized = False
        self._known_agents: set[str] = set()

    @property
    def name(self) -> str:
        return "ghostkg"

    def initialize(self, simulation_context: Dict[str, Any]) -> None:
        try:
            from ghost_kg import AgentManager, Rating

            # Prefer explicit db_url/db_path if provided, otherwise default to shared db file.
            db_path = self.config.get("db_path") or self._resolve_default_db_path(simulation_context)
            store_log_content = bool(self.config.get("store_log_content", False))
            self.manager = AgentManager(db_path=db_path, store_log_content=store_log_content)
            self.rating = Rating
            self._available = True
            self._initialized = True
        except Exception as e:
            self._available = False
            self._initialized = False
            self.logger.warning(f"GhostKG backend unavailable, running inert adapter: {e}")

    def ingest_event(
        self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]
    ) -> IngestResult:
        if not self._available:
            return IngestResult(success=False, skipped=1, error="ghostkg_unavailable")

        try:
            self._ensure_agent(agent_id, context)

            action_type = str(event.get("action_type", "")).upper()
            topic = event.get("topic")
            target_user_id = event.get("target_user_id")

            if action_type == "POST" and topic:
                self.manager.learn_triplet(agent_id, "I", "posts_about", str(topic), rating=self.rating.Good)
            elif action_type == "COMMENT" and topic:
                self.manager.learn_triplet(
                    agent_id, "I", "comments_about", str(topic), rating=self.rating.Good
                )
            elif action_type == "FOLLOW" and target_user_id:
                self.manager.learn_triplet(
                    agent_id, "I", "follows", str(target_user_id), rating=self.rating.Good
                )
            elif action_type == "UNFOLLOW" and target_user_id:
                self.manager.learn_triplet(
                    agent_id, "I", "unfollows", str(target_user_id), rating=self.rating.Hard
                )
            else:
                relation_target = str(topic or target_user_id or "simulation_event")
                self.manager.learn_triplet(
                    agent_id, "I", f"performed_{action_type.lower() or 'action'}", relation_target
                )

            return IngestResult(success=True, created=1)
        except Exception as e:
            self.logger.error(f"GhostKG ingest failed: {e}")
            return IngestResult(success=False, error=str(e))

    def retrieve(
        self, agent_id: str, query: MemoryQuery, context: Dict[str, Any]
    ) -> List[MemoryItemDTO]:
        if not self._available:
            return []

        try:
            self._ensure_agent(agent_id, context)
            topic = query.topic or "simulation"
            raw_context = self.manager.get_context(agent_id, topic)
            if not raw_context:
                return []

            max_items = max(1, int(query.max_items))
            context_lines = [line.strip("- ").strip() for line in raw_context.splitlines() if line.strip()]
            context_lines = [line for line in context_lines if line][:max_items]
            items: List[MemoryItemDTO] = []
            for idx, line in enumerate(context_lines):
                items.append(
                    MemoryItemDTO(
                        memory_id=f"ghostkg:{agent_id}:{idx}",
                        memory_text=line,
                        relevance_score=max(0.0, 1.0 - (idx * 0.1)),
                        confidence=0.6,
                        strength=max(0.0, 0.7 - (idx * 0.05)),
                        sentiment=0.0,
                        metadata={"source": "ghostkg", "topic": topic},
                    )
                )
            return items
        except Exception as e:
            self.logger.error(f"GhostKG retrieval failed: {e}")
            return []

    def reinforce(
        self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]
    ) -> ReinforceResult:
        if not self._available:
            return ReinforceResult(success=False, skipped=len(memory_ids), error="ghostkg_unavailable")
        # GhostKG reinforcement is event-driven by additional triplet learning.
        # We keep this call lightweight and successful to satisfy contract semantics.
        return ReinforceResult(success=True, reinforced=len(memory_ids))

    def forget_cycle(self, context: Dict[str, Any]) -> ForgetResult:
        # GhostKG models forgetting through FSRS retrievability over time.
        # Explicit forget cycle is not required in adapter mode.
        if not self._available:
            return ForgetResult(success=False, error="ghostkg_unavailable")
        return ForgetResult(success=True)

    def health_check(self) -> BackendHealth:
        return BackendHealth(
            ok=self._available and self._initialized,
            backend=self.name,
            details={
                "initialized": self._initialized,
                "available": self._available,
            },
        )

    def _ensure_agent(self, agent_id: str, context: Dict[str, Any]) -> None:
        if agent_id not in self._known_agents:
            self.manager.create_agent(agent_id)
            self._known_agents.add(agent_id)

        # Keep GhostKG clock synchronized with simulation day/slot.
        day = int(context.get("day", 1) or 1)
        slot = int(context.get("slot", 0) or 0)
        agent = self.manager.get_agent(agent_id)
        agent.set_time((max(1, day), min(23, max(0, slot))))

    def _resolve_default_db_path(self, simulation_context: Dict[str, Any]) -> str:
        configured = self.config.get("db_path")
        if configured:
            return configured
        config_path = simulation_context.get("config_path")
        if config_path:
            return os.path.join(str(config_path), "database_server.db")
        return "database_server.db"
