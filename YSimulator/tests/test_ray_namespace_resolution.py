from pathlib import Path

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
