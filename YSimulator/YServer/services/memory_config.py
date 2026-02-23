"""
Memory backend configuration resolver.

Provides strict, testable rules for selecting pluggable memory backend mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

VALID_MEMORY_BACKENDS = {"none", "native", "ghostkg"}


@dataclass(frozen=True)
class MemorySettings:
    """Resolved memory runtime settings."""

    enabled: bool
    backend: str
    raw_config: Dict[str, Any]


def resolve_memory_settings(simulation_config: Dict[str, Any]) -> MemorySettings:
    """
    Resolve memory settings from simulation config.

    Rules:
    1. If `agent_memory.enabled` is falsey -> backend forced to `none`
    2. If `agent_memory.compute_location=client` -> server backend forced to `none`
    3. If enabled and backend missing -> default `native`
    4. If enabled and backend invalid -> raise ValueError
    """
    agent_memory_cfg = simulation_config.get("agent_memory", {})
    enabled = bool(agent_memory_cfg.get("enabled", False))
    compute_location = str(agent_memory_cfg.get("compute_location", "client")).strip().lower()

    if not enabled:
        return MemorySettings(enabled=False, backend="none", raw_config=agent_memory_cfg)
    if compute_location == "client":
        # In client-compute mode the server remains persistence-only.
        return MemorySettings(enabled=False, backend="none", raw_config=agent_memory_cfg)

    backend = str(agent_memory_cfg.get("backend", "native")).strip().lower()
    if backend not in VALID_MEMORY_BACKENDS:
        raise ValueError(
            f"Invalid memory backend '{backend}'. Expected one of: {sorted(VALID_MEMORY_BACKENDS)}"
        )

    return MemorySettings(enabled=True, backend=backend, raw_config=agent_memory_cfg)
