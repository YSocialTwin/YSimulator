from pathlib import Path

from YSimulator.YClient.memory_runtime import ClientMemoryRuntime


def test_sqlite_url_relative_path_is_resolved_under_config_path(tmp_path):
    runtime = ClientMemoryRuntime(
        simulation_config={"agent_memory": {"enabled": True, "backend": "native"}},
        config_path=tmp_path,
    )
    out = runtime._sqlite_url_from_path("sqlite:///database_server.db")
    assert out == f"sqlite:///{(tmp_path / 'database_server.db').resolve()}"


def test_sqlite_path_without_scheme_is_resolved_under_config_path(tmp_path):
    runtime = ClientMemoryRuntime(
        simulation_config={"agent_memory": {"enabled": True, "backend": "native"}},
        config_path=tmp_path,
    )
    out = runtime._sqlite_url_from_path("database_server.db")
    assert out == f"sqlite:///{(tmp_path / 'database_server.db').resolve()}"
