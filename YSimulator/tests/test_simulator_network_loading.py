"""
Regression tests for YSimulator network loading on client startup.
"""

import logging
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from YSimulator.YClient.simulation.simulator import Simulator


@pytest.fixture
def simulator_deps():
    """Create lightweight simulator dependencies."""
    return {
        "server": SimpleNamespace(
            check_network_edges_exist=SimpleNamespace(remote=MagicMock(return_value=False))
        ),
        "agent_scheduler": MagicMock(),
        "batch_processor": MagicMock(),
        "lifecycle_manager": MagicMock(),
        "round_executor": MagicMock(),
        "secondary_follow_processor": MagicMock(),
        "logger": MagicMock(spec=logging.Logger),
        "parse_network_edges_fn": MagicMock(return_value=[("alice", "bob")]),
        "load_and_create_social_network_fn": MagicMock(),
        "create_action_generator_factory_fn": MagicMock(),
        "log_action_fn": MagicMock(),
        "log_hourly_summary_fn": MagicMock(),
        "log_daily_summary_fn": MagicMock(),
    }


def _build_simulator(config_path: Path, client_id: str, deps: dict) -> Simulator:
    return Simulator(
        server=deps["server"],
        client_id=client_id,
        agent_profiles=[],
        config_path=config_path,
        num_days=1,
        num_slots_per_day=1,
        heartbeat_interval=1.0,
        agent_scheduler=deps["agent_scheduler"],
        batch_processor=deps["batch_processor"],
        lifecycle_manager=deps["lifecycle_manager"],
        round_executor=deps["round_executor"],
        secondary_follow_processor=deps["secondary_follow_processor"],
        logger=deps["logger"],
        parse_network_edges_fn=deps["parse_network_edges_fn"],
        load_and_create_social_network_fn=deps["load_and_create_social_network_fn"],
        create_action_generator_factory_fn=deps["create_action_generator_factory_fn"],
        log_action_fn=deps["log_action_fn"],
        log_hourly_summary_fn=deps["log_hourly_summary_fn"],
        log_daily_summary_fn=deps["log_daily_summary_fn"],
    )


def test_namespaced_client_loads_legacy_client_network_file(monkeypatch, simulator_deps):
    """
    A runtime client ID like 'matrix_1:test_client' must still load
    'test_client_network.csv' so legacy matrix experiments keep working.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)
        legacy_network = config_path / "test_client_network.csv"
        legacy_network.write_text("source,target\nalice,bob\n", encoding="utf-8")
        (config_path / "network.csv").write_text("source,target\ncarol,dave\n", encoding="utf-8")

        simulator = _build_simulator(config_path, "matrix_1:test_client", simulator_deps)

        monkeypatch.setattr("YSimulator.YClient.simulation.simulator.ray.get", lambda value: value)

        simulator._load_network_if_available()

        simulator_deps["parse_network_edges_fn"].assert_called_once_with(legacy_network)
        simulator_deps["load_and_create_social_network_fn"].assert_called_once_with(legacy_network)


def test_namespaced_client_prefers_runtime_specific_network_file(monkeypatch, simulator_deps):
    """
    If a runtime-specific network file exists, it should win over the legacy alias.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)
        runtime_network = config_path / "matrix_1:test_client_network.csv"
        runtime_network.write_text("source,target\nalice,bob\n", encoding="utf-8")
        legacy_network = config_path / "test_client_network.csv"
        legacy_network.write_text("source,target\ncarol,dave\n", encoding="utf-8")

        simulator = _build_simulator(config_path, "matrix_1:test_client", simulator_deps)

        monkeypatch.setattr("YSimulator.YClient.simulation.simulator.ray.get", lambda value: value)

        simulator._load_network_if_available()

        simulator_deps["parse_network_edges_fn"].assert_called_once_with(runtime_network)
        simulator_deps["load_and_create_social_network_fn"].assert_called_once_with(runtime_network)
