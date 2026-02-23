"""GhostKG adapter backend for pluggable memory."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
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
        self.backend_config = self.config.get("ghostkg", {}) if isinstance(self.config.get("ghostkg"), dict) else {}
        self.logger = logger or logging.getLogger(__name__)
        self.manager = None
        self.rating = None
        self._available = False
        self._initialized = False
        self._known_agents: set[str] = set()
        self._llm_service = None
        self._extraction_mode = str(self._cfg("extraction_mode", "triplets")).lower()
        self._relation_whitelist = set(self._cfg("relation_whitelist", []) or [])

    @property
    def name(self) -> str:
        return "ghostkg"

    def initialize(self, simulation_context: Dict[str, Any]) -> None:
        try:
            from ghost_kg import AgentManager, Rating

            # Prefer explicit db_url/db_path if provided, otherwise default to shared db file.
            db_path = self._cfg("db_path") or self._resolve_default_db_path(simulation_context)
            db_url = self._cfg("db_url")
            store_log_content = bool(self._cfg("store_log_content", False))
            self.manager = AgentManager(
                db_path=db_path,
                db_url=db_url,
                store_log_content=store_log_content,
            )
            self.rating = Rating
            self._llm_service = self._build_llm_service_if_needed()
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
            content = event.get("content") or self._default_content(action_type, topic, target_user_id)

            try:
                if self._extraction_mode in {"fast", "llm"} and content:
                    self._ingest_with_content_extraction(agent_id, content, action_type, target_user_id)
                else:
                    self._ingest_with_direct_triplet(agent_id, action_type, topic, target_user_id)
            except Exception as primary_error:
                # Compatibility fallback for older GhostKG timestamp constraints.
                if "created_at" not in str(primary_error):
                    raise
                self._set_agent_synthetic_datetime(agent_id, context)
                if self._extraction_mode in {"fast", "llm"} and content:
                    self._ingest_with_content_extraction(agent_id, content, action_type, target_user_id)
                else:
                    self._ingest_with_direct_triplet(agent_id, action_type, topic, target_user_id)

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
            self.manager.create_agent(agent_id, llm_service=self._llm_service)
            self._known_agents.add(agent_id)

        # Keep GhostKG clock synchronized with simulation day/slot using round tuple.
        day = int(context.get("day", 1) or 1)
        slot = int(context.get("slot", 0) or 0)
        agent = self.manager.get_agent(agent_id)
        agent.set_time((max(1, day), min(23, max(0, slot))))

    def _set_agent_synthetic_datetime(self, agent_id: str, context: Dict[str, Any]) -> None:
        """
        Fallback clock sync for GhostKG versions requiring non-null datetime timestamps.
        """
        day = int(context.get("day", 1) or 1)
        slot = int(context.get("slot", 0) or 0)
        safe_day = max(1, day)
        safe_hour = min(23, max(0, slot))
        synthetic_now = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=safe_day - 1, hours=safe_hour
        )
        agent = self.manager.get_agent(agent_id)
        agent.set_time(synthetic_now)

    def _build_llm_service_if_needed(self):
        if self._extraction_mode != "llm":
            return None

        try:
            from ghost_kg.llm import get_llm_service

            provider = str(self._cfg("llm_provider", "ollama"))
            model = str(self._cfg("llm_model", "llama3.2"))
            api_key = self._cfg("llm_api_key")
            api_key_env = self._cfg("llm_api_key_env")
            if not api_key and api_key_env:
                api_key = os.getenv(str(api_key_env))
            base_url = self._cfg("llm_base_url")
            return get_llm_service(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        except Exception as e:
            self.logger.warning(f"GhostKG LLM service unavailable, falling back to direct triplets: {e}")
            self._extraction_mode = "triplets"
            return None

    def _ingest_with_content_extraction(
        self, agent_id: str, content: str, action_type: str, target_user_id: Optional[str]
    ) -> None:
        author = str(target_user_id or "User")
        use_fast_mode = self._extraction_mode == "fast"
        self.manager.absorb_content(
            agent_id,
            str(content),
            author=author,
            triplets=None,
            fast_mode=use_fast_mode,
        )

    def _ingest_with_direct_triplet(
        self,
        agent_id: str,
        action_type: str,
        topic: Optional[str],
        target_user_id: Optional[str],
    ) -> None:
        relation, target, rating = self._event_to_triplet(action_type, topic, target_user_id)
        self.manager.learn_triplet(agent_id, "I", relation, target, rating=rating)

    def _event_to_triplet(
        self, action_type: str, topic: Optional[str], target_user_id: Optional[str]
    ) -> tuple[str, str, int]:
        if action_type == "POST" and topic:
            relation, target, rating = "posts_about", str(topic), self.rating.Good
        elif action_type == "COMMENT" and topic:
            relation, target, rating = "comments_about", str(topic), self.rating.Good
        elif action_type == "FOLLOW" and target_user_id:
            relation, target, rating = "follows", str(target_user_id), self.rating.Good
        elif action_type == "UNFOLLOW" and target_user_id:
            relation, target, rating = "unfollows", str(target_user_id), self.rating.Hard
        else:
            relation = f"performed_{action_type.lower() or 'action'}"
            target = str(topic or target_user_id or "simulation_event")
            rating = self.rating.Good

        if self._relation_whitelist and relation not in self._relation_whitelist:
            relation = "mentions"
        return relation, target, rating

    def _default_content(
        self, action_type: str, topic: Optional[str], target_user_id: Optional[str]
    ) -> str:
        if topic:
            return f"{action_type} about {topic}"
        if target_user_id:
            return f"{action_type} targeting {target_user_id}"
        return action_type or "action"

    def _resolve_default_db_path(self, simulation_context: Dict[str, Any]) -> str:
        configured = self._cfg("db_path")
        if configured:
            return configured
        config_path = simulation_context.get("config_path")
        if config_path:
            return os.path.join(str(config_path), "database_server.db")
        return "database_server.db"

    def _cfg(self, key: str, default: Any = None) -> Any:
        """Read backend configuration with support for nested `agent_memory.ghostkg`."""
        if key in self.backend_config:
            return self.backend_config[key]
        return self.config.get(key, default)
