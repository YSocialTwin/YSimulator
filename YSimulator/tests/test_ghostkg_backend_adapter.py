"""Tests for GhostKG adapter backend behavior."""

import types
import sys

from YSimulator.YServer.services.memory_backends.ghostkg_backend import GhostKGMemoryBackend
from YSimulator.YServer.services.memory_backends.base import MemoryQuery


def test_ghostkg_backend_unavailable_is_safe():
    backend = GhostKGMemoryBackend(backend_config={})
    backend.initialize({})
    health = backend.health_check()
    if health.ok:
        # GhostKG is installed; backend should still operate safely.
        result = backend.ingest_event(
            "agent-1", {"action_type": "POST", "topic": "ai"}, {"day": 1, "slot": 1}
        )
        assert result.success is True
    else:
        assert health.details.get("available") is False
        result = backend.ingest_event(
            "agent-1", {"action_type": "POST", "topic": "ai"}, {"day": 1, "slot": 1}
        )
        assert result.success is False


def test_ghostkg_backend_with_fake_module(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeAgent:
        def set_time(self, _time):
            return None

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self._agents = {}
            self.absorb_calls = 0
            self.learn_calls = 0

        def create_agent(self, name, llm_service=None):
            self._agents[name] = FakeAgent()
            return self._agents[name]

        def get_agent(self, name):
            return self._agents[name]

        def learn_triplet(self, *args, **kwargs):
            self.learn_calls += 1
            return None

        def get_context(self, agent_name, topic):
            return "- I posts_about ai\n- I follows user-2"

        def absorb_content(self, *args, **kwargs):
            self.absorb_calls += 1
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(backend_config={"db_path": "fake.db"})
    backend.initialize({"day": 1, "slot": 1})
    assert backend.health_check().ok is True

    ingest = backend.ingest_event(
        "agent-1",
        {"action_type": "POST", "topic": "ai"},
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True

    items = backend.retrieve("agent-1", MemoryQuery(topic="ai", max_items=2), {"day": 1, "slot": 2})
    assert len(items) == 2
    assert items[0].memory_text


def test_ghostkg_backend_fast_extraction_mode_uses_absorb_content(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeAgent:
        def set_time(self, _time):
            return None

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self._agents = {}
            self.absorb_calls = 0
            self.learn_calls = 0

        def create_agent(self, name, llm_service=None):
            self._agents[name] = FakeAgent()
            return self._agents[name]

        def get_agent(self, name):
            return self._agents[name]

        def learn_triplet(self, *args, **kwargs):
            self.learn_calls += 1
            return None

        def absorb_content(self, *args, **kwargs):
            self.absorb_calls += 1
            return None

        def get_context(self, agent_name, topic):
            return "- memory item"

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "fast", "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})
    ingest = backend.ingest_event(
        "agent-1",
        {"action_type": "POST", "topic": "ai", "content": "AI is evolving"},
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert backend.manager.absorb_calls == 1
    assert backend.manager.learn_calls == 0
