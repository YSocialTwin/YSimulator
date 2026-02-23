"""Tests for memory backend factory and no-op service behavior."""

from YSimulator.YClient.memory.backends.factory import MemoryBackendFactory
from YSimulator.YClient.memory.service import MemoryService


def test_backend_factory_creates_expected_backends():
    assert MemoryBackendFactory.create("none").name == "none"
    assert MemoryBackendFactory.create("native").name == "native"
    assert MemoryBackendFactory.create("ghostkg").name == "ghostkg"
    engine = type("E", (), {"url": "sqlite:////tmp/main.db"})()
    assert MemoryBackendFactory.create("ghostkg", engine=engine).engine is engine


def test_memory_service_disabled_uses_none_backend():
    service = MemoryService(simulation_config={"agent_memory": {"enabled": False}})
    assert service.get_backend_name() == "none"
    assert service.retrieve("agent-1", {}, {}) == []
