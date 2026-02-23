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
        backend_config={
            "extraction_mode": "fast",
            "db_path": "fake.db",
            "external_triplets_only": False,
        }
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


def test_ghostkg_backend_uses_external_absorb_triplets_when_provided(monkeypatch):
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
            self.last_absorb_triplets = None

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
            self.last_absorb_triplets = kwargs.get("triplets")
            return None

        def get_context(self, agent_name, topic):
            return "- memory item"

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "llm", "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})
    ingest = backend.ingest_event(
        "agent-1",
        {
            "action_type": "POST",
            "topic": "ai",
            "content": "AI is everywhere",
            "metadata": {
                "ghostkg_absorb_triplets": [
                    ["AI", "is", "discussed"],
                    ["author", "supports", "AI"],
                ]
            },
        },
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert backend.manager.absorb_calls == 1
    assert backend.manager.learn_calls == 0
    assert backend.manager.last_absorb_triplets == [
        ("AI", "is", "discussed"),
        ("author", "supports", "AI"),
    ]


def test_ghostkg_backend_write_back_updates_personal_beliefs(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeAgent:
        def set_time(self, _time):
            return None

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self._agents = {}
            self.update_calls = 0
            self.last_triplets = None
            self.last_context = None

        def create_agent(self, name, llm_service=None):
            self._agents[name] = FakeAgent()
            return self._agents[name]

        def get_agent(self, name):
            return self._agents[name]

        def learn_triplet(self, *args, **kwargs):
            return None

        def absorb_content(self, *args, **kwargs):
            return None

        def update_with_response(self, agent_name, response, triplets=None, context=None):
            self.update_calls += 1
            self.last_triplets = triplets
            self.last_context = context
            return None

        def get_context(self, agent_name, topic):
            return "- memory item"

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "triplets", "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})

    ingest = backend.ingest_event(
        "agent-1",
        {
            "action_type": "POST",
            "topic": "ai",
            "content": "I think AI can improve healthcare access",
            "metadata": {
                "memory_phase": "write_back",
                "context_used": ["Known facts: AI in medicine", "Others think: mixed sentiment"],
            },
        },
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert backend.manager.update_calls == 1
    assert backend.manager.last_triplets == [("stated_about", "ai", 0.0)]
    assert "Known facts" in backend.manager.last_context


def test_ghostkg_backend_write_back_prefers_external_reflection_triplets(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeAgent:
        def set_time(self, _time):
            return None

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self._agents = {}
            self.last_triplets = None

        def create_agent(self, name, llm_service=None):
            self._agents[name] = FakeAgent()
            return self._agents[name]

        def get_agent(self, name):
            return self._agents[name]

        def learn_triplet(self, *args, **kwargs):
            return None

        def absorb_content(self, *args, **kwargs):
            return None

        def update_with_response(self, agent_name, response, triplets=None, context=None):
            self.last_triplets = triplets
            return None

        def get_context(self, agent_name, topic):
            return "- memory item"

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "llm", "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})

    ingest = backend.ingest_event(
        "agent-1",
        {
            "action_type": "POST",
            "topic": "ai",
            "content": "I oppose unsafe AI",
            "metadata": {
                "memory_phase": "write_back",
                "ghostkg_reflection_triplets": [["oppose", "unsafe AI", -0.8]],
            },
        },
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert backend.manager.last_triplets == [("oppose", "unsafe AI", -0.8)]


def test_ghostkg_backend_defaults_to_engine_db_url(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self.db_path = db_path
            self.db_url = db_url

        def create_agent(self, name, llm_service=None):
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    engine = types.SimpleNamespace(url="sqlite:////tmp/main_simulation.db")
    backend = GhostKGMemoryBackend(backend_config={}, engine=engine)
    backend.initialize({})

    assert backend.health_check().ok is True
    assert backend.manager.db_url == "sqlite:////tmp/main_simulation.db"
    assert backend.manager.db_path is None


def test_ghostkg_backend_default_prefers_main_db_even_when_db_path_configured(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self.db_path = db_path
            self.db_url = db_url

        def create_agent(self, name, llm_service=None):
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    engine = types.SimpleNamespace(url="sqlite:////tmp/main_simulation.db")
    backend = GhostKGMemoryBackend(backend_config={"db_path": "/tmp/ghostkg_only.db"}, engine=engine)
    backend.initialize({})

    assert backend.health_check().ok is True
    assert backend.manager.db_url == "sqlite:////tmp/main_simulation.db"
    assert backend.manager.db_path is None


def test_ghostkg_backend_explicit_opt_out_uses_db_path(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self.db_path = db_path
            self.db_url = db_url

        def create_agent(self, name, llm_service=None):
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    engine = types.SimpleNamespace(url="sqlite:////tmp/main_simulation.db")
    backend = GhostKGMemoryBackend(
        backend_config={"db_path": "/tmp/ghostkg_only.db", "use_main_db": False},
        engine=engine,
    )
    backend.initialize({"config_path": "/tmp"})

    assert backend.health_check().ok is True
    assert backend.manager.db_url is None
    assert backend.manager.db_path == "/tmp/ghostkg_only.db"


def test_ghostkg_backend_resolves_relative_sqlite_url_with_config_path(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self.db_path = db_path
            self.db_url = db_url

        def create_agent(self, name, llm_service=None):
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    engine = types.SimpleNamespace(url="sqlite:///simulation_memory_ghostkg.db")
    backend = GhostKGMemoryBackend(backend_config={}, engine=engine)
    backend.initialize({"config_path": "/tmp/experiment"})

    assert backend.health_check().ok is True
    assert backend.manager.db_url == "sqlite:////tmp/experiment/simulation_memory_ghostkg.db"


def test_ghostkg_backend_falls_back_to_direct_triplet_on_float_rating_error(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeAgent:
        def set_time(self, _time):
            return None

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self.db_path = db_path
            self.db_url = db_url
            self._agents = {}
            self.learn_calls = 0

        def create_agent(self, name, llm_service=None):
            self._agents[name] = FakeAgent()
            return self._agents[name]

        def get_agent(self, name):
            return self._agents[name]

        def absorb_content(self, *args, **kwargs):
            raise TypeError("list indices must be integers or slices, not float")

        def learn_triplet(self, *args, **kwargs):
            self.learn_calls += 1
            return None

        def get_context(self, agent_name, topic):
            return "- memory item"

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "llm", "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})
    ingest = backend.ingest_event(
        "agent-1",
        {"action_type": "POST", "topic": "ai", "content": "AI will transform healthcare"},
        {"day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert backend.manager.learn_calls == 1


def test_ghostkg_backend_external_triplets_mode_never_builds_server_llm_service(monkeypatch):
    class FakeRating:
        Good = 3
        Hard = 2

    class FakeManager:
        def __init__(self, db_path="db", db_url=None, store_log_content=False):
            self._agents = {}

        def create_agent(self, name, llm_service=None):
            self._agents[name] = object()
            return self._agents[name]

        def get_agent(self, name):
            class _Agent:
                def set_time(self, _time):
                    return None

            return _Agent()

        def learn_triplet(self, *args, **kwargs):
            return None

    fake_module = types.SimpleNamespace(AgentManager=FakeManager, Rating=FakeRating)
    monkeypatch.setitem(sys.modules, "ghost_kg", fake_module)

    backend = GhostKGMemoryBackend(
        backend_config={"extraction_mode": "llm", "external_triplets_only": True, "db_path": "fake.db"}
    )
    backend.initialize({"day": 1, "slot": 1})

    assert backend.health_check().ok is True
    assert backend._llm_service is None
