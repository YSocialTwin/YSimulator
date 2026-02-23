"""Client-side memory runtime for pluggable memory computation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine

from YSimulator.YServer.services.memory_backends import MemoryBackendFactory, MemoryQuery


class ClientMemoryRuntime:
    """
    Runs memory backend computation on YClient.

    The runtime writes results directly to the same simulation DB used by YServer
    while avoiding server-side memory computation.
    """

    def __init__(
        self,
        simulation_config: Dict[str, Any],
        config_path: Path,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.config_path = Path(config_path)
        self.simulation_config = simulation_config or {}
        self.cfg = self.simulation_config.get("agent_memory", {})
        self.enabled = bool(self.cfg.get("enabled", False))
        self.compute_location = str(self.cfg.get("compute_location", "client")).strip().lower()
        self.backend_name = str(self.cfg.get("backend", "none")).strip().lower()
        self.backend = None
        self.engine = None

    @property
    def active(self) -> bool:
        return self.enabled and self.compute_location == "client" and self.backend is not None

    def initialize(self) -> None:
        if not self.enabled or self.compute_location != "client" or self.backend_name == "none":
            self.logger.info(
                "Client memory runtime disabled",
                extra={
                    "extra_data": {
                        "memory_enabled": self.enabled,
                        "compute_location": self.compute_location,
                        "backend": self.backend_name,
                    }
                },
            )
            return

        db_url = self._resolve_db_url()
        self.engine = create_engine(db_url)
        self.backend = MemoryBackendFactory.create(
            self.backend_name,
            logger=self.logger,
            backend_config=self.cfg,
            engine=self.engine,
        )
        self.backend.initialize({"config_path": str(self.config_path), "day": 1, "slot": 0})
        self.logger.info(
            "Client memory runtime initialized",
            extra={
                "extra_data": {
                    "backend": self.backend_name,
                    "db_url": db_url,
                    "compute_location": self.compute_location,
                }
            },
        )

    def retrieve(self, agent_id: str, query: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.active:
            return []
        memory_query = MemoryQuery(
            topic=query.get("topic"),
            target_user_id=query.get("target_user_id"),
            thread_id=query.get("thread_id"),
            action_type=query.get("action_type"),
            max_items=int(query.get("max_items", 5)),
            metadata=query.get("metadata", {}),
        )
        items = self.backend.retrieve(agent_id, memory_query, context)
        return [
            {
                "memory_id": item.memory_id,
                "memory_text": item.memory_text,
                "relevance_score": item.relevance_score,
                "confidence": item.confidence,
                "strength": item.strength,
                "sentiment": item.sentiment,
                "metadata": item.metadata,
            }
            for item in items
        ]

    def reinforce(self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]) -> bool:
        if not self.active:
            return False
        result = self.backend.reinforce(agent_id, memory_ids or [], context)
        return bool(result.success)

    def ingest_event(self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]) -> bool:
        if not self.active:
            return False
        result = self.backend.ingest_event(agent_id, event or {}, context)
        return bool(result.success)

    def _resolve_db_url(self) -> str:
        # Use GhostKG-specific DB URL/path settings when backend is ghostkg and custom storage is requested.
        if self.backend_name == "ghostkg":
            ghost_cfg = self.cfg.get("ghostkg", {}) if isinstance(self.cfg.get("ghostkg"), dict) else {}
            explicit_url = ghost_cfg.get("db_url")
            if explicit_url:
                return str(explicit_url)
            explicit_path = ghost_cfg.get("db_path")
            use_main_db = bool(ghost_cfg.get("use_main_db", True))
            if explicit_path and not use_main_db:
                return self._sqlite_url_from_path(str(explicit_path))

        # Default/shared DB for all memory backends.
        return self._sqlite_url_from_path("database_server.db")

    def _sqlite_url_from_path(self, db_path: str) -> str:
        db_path = str(db_path)
        if db_path.startswith("sqlite:///"):
            return db_path
        resolved = Path(db_path)
        if not resolved.is_absolute():
            resolved = self.config_path / resolved
        return f"sqlite:///{resolved.resolve()}"
