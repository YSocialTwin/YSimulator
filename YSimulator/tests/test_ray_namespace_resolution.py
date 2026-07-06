from pathlib import Path

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
