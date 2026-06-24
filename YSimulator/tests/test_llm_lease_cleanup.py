from unittest.mock import ANY, Mock

from YSimulator.YClient.llm_utils.load_balancer import (
    acquire_llm_pool_lease,
    cleanup_expired_shared_vllm_pools,
    release_llm_pool_lease,
)


class _RemoteCall:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


class _FakeRegistry:
    def __init__(self, release_result):
        self._release_result = release_result
        self.acquire = _RemoteCall(self._acquire)
        self.release = _RemoteCall(self._release)
        self.reap_expired_shared_vllm_pools = _RemoteCall(self._reap)
        self.acquire_calls = []
        self.release_calls = []
        self.reap_calls = []

    def _acquire(self, pool_key, client_id, actor_names):
        self.acquire_calls.append((pool_key, client_id, actor_names))
        return 2

    def _release(self, pool_key, client_id):
        self.release_calls.append((pool_key, client_id))
        return self._release_result

    def _reap(self, now):
        self.reap_calls.append(now)
        return []


class _FakeActor:
    def __init__(self, name, shutdown_error=None, shutdown_result=None):
        self.name = name
        self.shutdown_calls = 0
        self._shutdown_error = shutdown_error
        self._shutdown_result = shutdown_result or {
            "actor_pid": 111,
            "child_pids": [222],
            "terminated_children": 0,
            "errors": [],
        }
        self.shutdown = _RemoteCall(self._shutdown)

    def _shutdown(self):
        self.shutdown_calls += 1
        if self._shutdown_error:
            raise self._shutdown_error
        return self._shutdown_result


def test_acquire_lease_calls_registry(monkeypatch):
    fake_registry = _FakeRegistry(release_result=(1, []))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    active = acquire_llm_pool_lease(
        backend="vllm",
        actor_name_prefix="ysim_llm",
        num_actors=2,
        client_id="client1",
        actor_names=["ysim_llm_vllm_0", "ysim_llm_vllm_1"],
    )

    assert active == 2
    assert fake_registry.acquire_calls == [
        ("vllm:ysim_llm:2", "client1", ["ysim_llm_vllm_0", "ysim_llm_vllm_1"])
    ]


def test_release_lease_can_use_explicit_pool_key(monkeypatch):
    fake_registry = _FakeRegistry(release_result=(0, ["legacy_vllm_0"]))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    kill_mock = Mock()
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.kill", kill_mock)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: Mock(name=f"actor-{name}"),
    )
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._force_kill_local_processes",
        lambda *args, **kwargs: 0,
    )

    active = release_llm_pool_lease(
        backend="vllm",
        actor_name_prefix="ysim_vllm_newprefix",
        num_actors=1,
        client_id="client1",
        pool_key="vllm:legacy_pool:1",
    )

    assert active == 0
    assert fake_registry.release_calls == [("vllm:legacy_pool:1", "client1")]


def test_release_lease_no_kill_when_clients_still_active(monkeypatch):
    fake_registry = _FakeRegistry(release_result=(1, ["ysim_llm_vllm_0"]))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    kill_mock = Mock()
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.kill", kill_mock)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: Mock(name=f"actor-{name}"),
    )

    active = release_llm_pool_lease(
        backend="vllm",
        actor_name_prefix="ysim_llm",
        num_actors=2,
        client_id="client1",
    )

    assert active == 1
    kill_mock.assert_not_called()


def test_release_lease_kills_actors_when_last_client_leaves(monkeypatch):
    actor_names = ["ysim_llm_vllm_0", "ysim_llm_vllm_1"]
    fake_registry = _FakeRegistry(release_result=(0, actor_names))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    actors = {name: _FakeActor(name) for name in actor_names}
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: actors[name],
    )
    kill_mock = Mock()
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.kill", kill_mock)
    force_kill_mock = Mock(return_value=2)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._force_kill_local_processes",
        force_kill_mock,
    )

    active = release_llm_pool_lease(
        backend="vllm",
        actor_name_prefix="ysim_llm",
        num_actors=2,
        client_id="client2",
    )

    assert active == 0
    assert kill_mock.call_count == 2
    assert [actors[name].shutdown_calls for name in actor_names] == [1, 1]
    assert force_kill_mock.call_count == 2


def test_release_lease_kills_even_if_shutdown_fails(monkeypatch):
    actor_names = ["ysim_llm_vllm_0"]
    fake_registry = _FakeRegistry(release_result=(0, actor_names))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    failing_actor = _FakeActor(actor_names[0], shutdown_error=RuntimeError("cleanup failed"))
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: failing_actor,
    )
    kill_mock = Mock()
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.kill", kill_mock)
    force_kill_mock = Mock(return_value=0)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._force_kill_local_processes",
        force_kill_mock,
    )

    active = release_llm_pool_lease(
        backend="vllm",
        actor_name_prefix="ysim_llm",
        num_actors=1,
        client_id="client2",
        logger=Mock(),
    )

    assert active == 0
    assert failing_actor.shutdown_calls == 1
    kill_mock.assert_called_once()
    force_kill_mock.assert_called_once_with([], ANY)


def test_cleanup_expired_shared_vllm_pools_terminates_expired_actors(monkeypatch):
    fake_registry = _FakeRegistry(release_result=(1, []))
    fake_registry._reap = lambda now: ["ysim_llm_vllm_0", "ysim_llm_vllm_1"]
    fake_registry.reap_expired_shared_vllm_pools = _RemoteCall(fake_registry._reap)

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: fake_registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)

    actors = {
        "ysim_llm_vllm_0": _FakeActor("ysim_llm_vllm_0"),
        "ysim_llm_vllm_1": _FakeActor("ysim_llm_vllm_1"),
    }
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: actors[name],
    )
    kill_mock = Mock()
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.kill", kill_mock)
    force_kill_mock = Mock(return_value=2)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._force_kill_local_processes",
        force_kill_mock,
    )

    expired = cleanup_expired_shared_vllm_pools(logger=Mock())

    assert expired == ["ysim_llm_vllm_0", "ysim_llm_vllm_1"]
    assert [actors[name].shutdown_calls for name in actors] == [1, 1]
    assert kill_mock.call_count == 2
