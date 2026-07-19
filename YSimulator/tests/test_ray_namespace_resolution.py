from pathlib import Path

import run_server
import run_client
from YSimulator.YClient import ray_utils
from run_client import resolve_client_namespace
from run_server import build_isolated_namespace


def test_build_isolated_namespace_is_stable(tmp_path):
    namespace_a = build_isolated_namespace("social_sim", tmp_path)
    namespace_b = build_isolated_namespace("social_sim", tmp_path)

    assert namespace_a == namespace_b
    assert namespace_a.startswith("social_sim_")


def test_build_isolated_namespace_differs_per_config_dir(tmp_path):
    namespace_a = build_isolated_namespace("social_sim", tmp_path / "exp_a")
    namespace_b = build_isolated_namespace("social_sim", tmp_path / "exp_b")

    assert namespace_a != namespace_b


def test_resolve_client_namespace_prefers_server_override(tmp_path):
    config_dir = Path(tmp_path)
    (config_dir / "ray_namespace.temp").write_text("social_sim_exp")

    namespace = resolve_client_namespace(config_dir, {"namespace": "social_sim"})

    assert namespace == "social_sim_exp"


def test_resolve_client_namespace_falls_back_to_simulation_config(tmp_path):
    config_dir = Path(tmp_path)

    namespace = resolve_client_namespace(config_dir, {"namespace": "social_sim"})

    assert namespace == "social_sim"


def test_llm_agents_disabled_config_is_detected():
    assert run_client._llm_agents_enabled_from_config(
        {"agents": {"llm_agents": [None]}}
    ) is False
    assert run_client._llm_agents_enabled_from_config(
        {"agents": {"llm_agents": []}}
    ) is True
    assert run_client._llm_agents_enabled_from_config(
        {"agents": {"llm_agents": ["llama3.2"]}}
    ) is True


def test_llm_agents_enabled_accepts_bare_agent_lists():
    assert run_client._llm_agents_enabled_from_config(
        [{"username": "alice", "llm": False}, {"username": "bob", "llm": True}]
    ) is True
    assert run_client._llm_agents_enabled_from_config(
        [{"username": "alice", "llm": False}, {"username": "bob", "llm": False}]
    ) is False
    assert run_client._llm_agents_enabled_from_config([]) is False


def test_resolve_named_actor_retries_with_namespace(monkeypatch):
    actor = object()
    calls = []

    def fake_get_actor(name, namespace=None):
        calls.append((name, namespace))
        if len(calls) < 3:
            raise ValueError("Orchestrator not ready")
        return actor

    monkeypatch.setattr(ray_utils.ray, "get_actor", fake_get_actor)
    monkeypatch.setattr(ray_utils.time, "sleep", lambda *_: None)

    resolved = ray_utils.resolve_named_actor(
        "Orchestrator",
        namespace="social_sim_exp",
        wait_seconds=1.0,
        poll_interval=0.1,
    )

    assert resolved is actor
    assert calls[0] == ("Orchestrator", "social_sim_exp")


def test_wait_for_orchestrator_ready_retries_until_ping(monkeypatch):
    class ReadyProbe:
        def __init__(self):
            self.calls = 0

        def remote(self):
            self.calls += 1
            return f"probe-{self.calls}"

    class FakeServerHandle:
        def __init__(self):
            self.is_ready = ReadyProbe()

    probe_calls = []

    def fake_ray_get(value):
        probe_calls.append(value)
        if len(probe_calls) < 3:
            raise ValueError("actor not ready yet")
        return True

    monkeypatch.setattr(run_server.ray, "get", fake_ray_get)
    monkeypatch.setattr(run_server.time, "sleep", lambda *_: None)

    assert run_server.wait_for_orchestrator_ready(
        FakeServerHandle(), timeout_seconds=1
    ) is True
    assert len(probe_calls) == 3


def test_cleanup_stale_client_actor_kills_existing_named_actor(monkeypatch):
    class FakeActor:
        pass

    killed = []

    def fake_get_actor(name, namespace=None):
        assert name == "exp_1:client_1"
        assert namespace == "social_sim_exp"
        return FakeActor()

    def fake_kill(actor, no_restart=True):
        killed.append((actor, no_restart))

    monkeypatch.setattr(run_client.ray, "get_actor", fake_get_actor)
    monkeypatch.setattr(run_client.ray, "kill", fake_kill)

    run_client.cleanup_stale_client_actor(
        "exp_1:client_1", "social_sim_exp", run_client.logging.getLogger("test")
    )

    assert killed and killed[0][1] is True


def test_intentional_actor_termination_detection(monkeypatch):
    class FakeActorDiedError(Exception):
        pass

    monkeypatch.setattr(run_client.ray.exceptions, "ActorDiedError", FakeActorDiedError, raising=False)

    assert run_client._is_intentional_actor_termination(
        FakeActorDiedError("The actor is dead because it was killed by `ray.kill`.")
    )
    assert not run_client._is_intentional_actor_termination(
        FakeActorDiedError("The actor died unexpectedly before finishing this task.")
    )
