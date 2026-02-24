"""Tests for pluggable memory configuration resolution."""

import pytest

from YSimulator.YClient.memory.config import resolve_memory_settings


def test_memory_disabled_forces_none_backend():
    settings = resolve_memory_settings({"agent_memory": {"enabled": False, "backend": "ghostkg"}})
    assert settings.enabled is False
    assert settings.backend == "none"


def test_memory_enabled_defaults_to_client_compute_and_server_none_backend():
    settings = resolve_memory_settings({"agent_memory": {"enabled": True}})
    assert settings.enabled is False
    assert settings.backend == "none"


@pytest.mark.parametrize("backend", ["none", "native", "ghostkg"])
def test_memory_enabled_accepts_valid_backends(backend):
    settings = resolve_memory_settings(
        {
            "agent_memory": {
                "enabled": True,
                "compute_location": "server",
                "backend": backend,
            }
        }
    )
    assert settings.enabled is True
    assert settings.backend == backend


def test_memory_enabled_rejects_invalid_backend():
    with pytest.raises(ValueError, match="Invalid memory backend"):
        resolve_memory_settings(
            {
                "agent_memory": {
                    "enabled": True,
                    "compute_location": "server",
                    "backend": "invalid_backend",
                }
            }
        )


def test_memory_enabled_accepts_ghostkg_alias_ghost_kg():
    settings = resolve_memory_settings(
        {
            "agent_memory": {
                "enabled": True,
                "compute_location": "server",
                "backend": "ghost_kg",
            }
        }
    )
    assert settings.enabled is True
    assert settings.backend == "ghostkg"
