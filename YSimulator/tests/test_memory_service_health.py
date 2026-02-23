"""Tests for memory service health/status reporting."""

import logging

from sqlalchemy import create_engine

from YSimulator.YServer.services.memory_service import MemoryService


def test_memory_service_health_reports_none_backend_when_disabled():
    service = MemoryService(simulation_config={"agent_memory": {"enabled": False}})
    service.initialize({"day": 1, "slot": 1, "current_round_id": "r1"})
    status = service.health_check()
    assert status["backend"] == "none"
    assert status["enabled"] is False
    assert status["ok"] is True


def test_memory_service_health_reports_native_backend_when_enabled(tmp_path):
    db_file = tmp_path / "memory_health.db"
    engine = create_engine(f"sqlite:///{db_file}")
    service = MemoryService(
        simulation_config={"agent_memory": {"enabled": True, "backend": "native"}},
        engine=engine,
    )
    service.initialize({"day": 1, "slot": 1, "current_round_id": "r1"})
    status = service.health_check()
    assert status["backend"] == "native"
    assert status["enabled"] is True
    assert status["ok"] is True


def test_memory_service_bind_logger_propagates_to_backend():
    engine = create_engine("sqlite:///:memory:")
    service = MemoryService(
        simulation_config={"agent_memory": {"enabled": True, "backend": "native"}},
        engine=engine,
    )
    memory_logger = logging.getLogger("test.memory")
    service.bind_logger(memory_logger)
    assert service.logger is memory_logger
    assert getattr(service.backend, "logger", None) is memory_logger
