"""Client-side memory runtime for pluggable memory computation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from YSimulator.YClient.memory.config import normalize_memory_backend


class ClientMemoryRuntime:
    """
    Runs memory backend computation on YClient.

    The runtime keeps client-side memory computation enabled/disabled state.
    Persistence/retrieval/reinforcement are delegated to YServer hooks.
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
        self.backend_name = normalize_memory_backend(self.cfg.get("backend", "none"))
        self._initialized = False

    @property
    def active(self) -> bool:
        return (
            self._initialized
            and self.enabled
            and self.compute_location == "client"
            and self.backend_name != "none"
        )

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

        self._initialized = True
        self.logger.info(
            "Client memory runtime initialized",
            extra={
                "extra_data": {
                    "backend": self.backend_name,
                    "compute_location": self.compute_location,
                    "storage": "server_sqlalchemy_hooks",
                }
            },
        )

    def retrieve(self, agent_id: str, query: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Storage/retrieval are handled by YServer hooks.
        return []

    def reinforce(self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]) -> bool:
        # Reinforcement is handled by YServer hooks.
        return False

    def ingest_event(self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]) -> bool:
        # Ingestion is handled by YServer hooks.
        return False

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
            # Normalize relative sqlite URLs against experiment config_path.
            if db_path == "sqlite:///:memory:" or db_path.startswith("sqlite:////"):
                return db_path
            raw_path = db_path[len("sqlite:///") :]
            resolved = Path(raw_path)
            if not resolved.is_absolute():
                resolved = self.config_path / resolved
            return f"sqlite:///{resolved.resolve()}"
        resolved = Path(db_path)
        if not resolved.is_absolute():
            resolved = self.config_path / resolved
        return f"sqlite:///{resolved.resolve()}"
