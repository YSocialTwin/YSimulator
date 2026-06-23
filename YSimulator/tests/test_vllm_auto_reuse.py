from unittest.mock import Mock

from YSimulator.YClient.llm_utils.load_balancer import (
    DEFAULT_VLLM_SHARED_NAMESPACE,
    _build_vllm_pool_prefix,
    _build_vllm_shared_group_key,
    _discover_existing_vllm_pool,
    create_llm_actors,
)


class _RemoteCall:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


def test_create_llm_actors_auto_reuses_existing_same_model_pool(monkeypatch):
    model_name = "AMead10/Llama-3.2-3B-Instruct-AWQ"
    resolved_prefix = _build_vllm_pool_prefix(model_name)
    llm_config = {"model": model_name, "client_name": "client-a", "gpu_per_actor": 1.0}
    prompts_config = {}

    actor0 = Mock(name="actor0")
    actor1 = Mock(name="actor1")
    actors = {
        f"{resolved_prefix}_vllm_0": actor0,
        f"{resolved_prefix}_vllm_1": actor1,
    }

    def fake_get_actor(name, namespace=None):
        if name in actors:
            return actors[name]
        raise ValueError(name)

    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get_actor", fake_get_actor)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.acquire_llm_pool_lease",
        lambda **kwargs: 1,
    )

    # If auto-reuse fails, constructor would try to create a new actor and hit this.
    options_mock = Mock(side_effect=AssertionError("should not create a new vLLM actor"))
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.vllm_service.VLLMService.options", options_mock
    )

    llm_handle = create_llm_actors(
        llm_config=llm_config,
        prompts_config=prompts_config,
        num_actors=4,
        backend="vllm",
        reuse_actors=False,
        actor_name_prefix="custom_prefix_should_be_ignored",
        logger=Mock(),
    )

    assert llm_handle.get_all_actors() == [actor0, actor1]
    assert llm_handle.num_actors == 2
    assert llm_config["_resolved_actor_name_prefix"] == resolved_prefix
    assert llm_config["_resolved_num_actors"] == 2
    assert llm_config["_resolved_actor_namespace"] == DEFAULT_VLLM_SHARED_NAMESPACE
    assert llm_config["_reused_existing_pool"] is True


def test_discover_existing_vllm_pool_can_use_actor_metadata(monkeypatch):
    model_name = "AMead10/Llama-3.2-3B-Instruct-AWQ"
    states = [
        {"name": "custom_pool_vllm_0", "class_name": "VLLMService", "state": "ALIVE"},
        {"name": "custom_pool_vllm_1", "class_name": "VLLMService", "state": "ALIVE"},
    ]

    actor0 = Mock()
    actor0.get_service_metadata = _RemoteCall(
        lambda: {"backend": "vllm", "model": model_name, "pool_prefix": "custom_pool"}
    )
    actor1 = Mock()
    actor1.get_service_metadata = _RemoteCall(
        lambda: {"backend": "vllm", "model": model_name, "pool_prefix": "custom_pool"}
    )
    actors = {"custom_pool_vllm_0": actor0, "custom_pool_vllm_1": actor1}

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._discover_named_actor_count",
        lambda prefix, backend, actor_namespace=None: 0,
    )
    monkeypatch.setattr("ray.util.state.list_actors", lambda: states)
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: actors[name],
    )

    prefix, count = _discover_existing_vllm_pool(model_name, actor_namespace="shared_vllm")

    assert prefix == "custom_pool"
    assert count == 2


def test_discover_existing_vllm_pool_filters_by_experiment_identity(monkeypatch):
    model_name = "AMead10/Llama-3.2-3B-Instruct-AWQ"
    states = [
        {"name": "exp_a_pool_vllm_0", "class_name": "VLLMService", "state": "ALIVE"},
        {"name": "exp_b_pool_vllm_0", "class_name": "VLLMService", "state": "ALIVE"},
    ]

    actor_a = Mock()
    actor_a.get_service_metadata = _RemoteCall(
        lambda: {
            "backend": "vllm",
            "model": model_name,
            "pool_prefix": "exp_a_pool",
            "experiment_identity": "/tmp/experiment-a",
        }
    )
    actor_b = Mock()
    actor_b.get_service_metadata = _RemoteCall(
        lambda: {
            "backend": "vllm",
            "model": model_name,
            "pool_prefix": "exp_b_pool",
            "experiment_identity": "/tmp/experiment-b",
        }
    )
    actors = {"exp_a_pool_vllm_0": actor_a, "exp_b_pool_vllm_0": actor_b}

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._discover_named_actor_count",
        lambda prefix, backend, actor_namespace=None: 0,
    )
    monkeypatch.setattr("ray.util.state.list_actors", lambda: states)
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: actors[name],
    )

    prefix, count = _discover_existing_vllm_pool(
        model_name,
        actor_namespace="shared_vllm",
        experiment_identity="/tmp/experiment-a",
    )

    assert prefix == "exp_a_pool"
    assert count == 1


def test_discover_existing_vllm_pool_ignores_state_api_failures(monkeypatch):
    model_name = "AMead10/Llama-3.2-3B-Instruct-AWQ"
    resolved_prefix = _build_vllm_pool_prefix(model_name)

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._discover_named_actor_count",
        lambda prefix, backend, actor_namespace=None: 0,
    )
    monkeypatch.setattr(
        "ray.util.state.list_actors", Mock(side_effect=RuntimeError("state api unavailable"))
    )

    prefix, count = _discover_existing_vllm_pool(model_name, logger=Mock())

    assert prefix == resolved_prefix
    assert count == 0


def test_build_vllm_shared_group_key_includes_experiment_identity():
    llm_config = {
        "model": "AMead10/Llama-3.2-3B-Instruct-AWQ",
        "tensor_parallel_size": 1,
        "gpu_per_actor": 1.0,
    }

    key_a = _build_vllm_shared_group_key(
        llm_config=llm_config,
        actor_namespace="shared_vllm",
        actor_name_prefix="ysim_vllm",
        num_actors=2,
        actor_backend="vllm",
        experiment_identity="/tmp/experiment-a",
    )
    key_b = _build_vllm_shared_group_key(
        llm_config=llm_config,
        actor_namespace="shared_vllm",
        actor_name_prefix="ysim_vllm",
        num_actors=2,
        actor_backend="vllm",
        experiment_identity="/tmp/experiment-b",
    )

    assert key_a != key_b
    assert "exp" in key_a
    assert "exp" in key_b


def test_create_llm_actors_creates_vllm_in_shared_namespace(monkeypatch):
    llm_config = {
        "model": "AMead10/Llama-3.2-3B-Instruct-AWQ",
        "client_name": "client-a",
        "_lease_client_id": "client-a:pid:run1",
        "gpu_per_actor": 1.0,
    }
    prompts_config = {}
    created_options = {}
    actor_handle = Mock(name="new-vllm-actor")

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._discover_existing_vllm_pool",
        lambda model_name, actor_namespace=None, experiment_identity=None, logger=None: (
            _build_vllm_pool_prefix(model_name),
            0,
        ),
    )
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.acquire_llm_pool_lease",
        lambda **kwargs: 1,
    )

    class _OptionsProxy:
        def __init__(self, opts):
            self._opts = opts

        def remote(self, **kwargs):
            created_options.update(self._opts)
            return actor_handle

    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.vllm_service.VLLMService.options",
        lambda **kwargs: _OptionsProxy(kwargs),
    )

    actor = create_llm_actors(
        llm_config=llm_config,
        prompts_config=prompts_config,
        num_actors=1,
        backend="vllm",
        logger=Mock(),
    )

    assert actor is actor_handle
    assert created_options["namespace"] == DEFAULT_VLLM_SHARED_NAMESPACE
    assert llm_config["_resolved_actor_namespace"] == DEFAULT_VLLM_SHARED_NAMESPACE


def test_create_llm_actors_uses_unique_lease_client_id(monkeypatch):
    llm_config = {
        "model": "AMead10/Llama-3.2-3B-Instruct-AWQ",
        "client_name": "client-a",
        "_lease_client_id": "client-a:pid:run42",
        "gpu_per_actor": 1.0,
    }
    prompts_config = {}
    acquired = {}

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._discover_existing_vllm_pool",
        lambda model_name, actor_namespace=None, experiment_identity=None, logger=None: (
            _build_vllm_pool_prefix(model_name),
            1,
        ),
    )

    actor = Mock(name="reused-vllm-actor")
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor",
        lambda name, namespace=None: actor,
    )
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.acquire_llm_pool_lease",
        lambda **kwargs: acquired.update(kwargs) or 1,
    )

    reused = create_llm_actors(
        llm_config=llm_config,
        prompts_config=prompts_config,
        num_actors=1,
        backend="vllm",
        logger=Mock(),
    )

    assert reused is actor
    assert acquired["client_id"] == "client-a:pid:run42"


def test_get_or_create_lease_registry_retries_on_name_collision(monkeypatch):
    from YSimulator.YClient.llm_utils import load_balancer

    registry = Mock(name="registry")
    create_calls = {"count": 0}

    def fake_get_actor(name, namespace=None):
        if create_calls["count"] == 0:
            raise ValueError(name)
        return registry

    class _OptionsProxy:
        def remote(self):
            create_calls["count"] += 1
            raise RuntimeError("Actor with name 'ysim_llm_lease_registry' already exists")

    monkeypatch.setattr(load_balancer.ray, "get_actor", fake_get_actor)
    monkeypatch.setattr(
        load_balancer.LLMLeaseRegistry,
        "options",
        lambda **kwargs: _OptionsProxy(),
    )
    monkeypatch.setattr(load_balancer.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(load_balancer.time, "time", lambda: 0)

    # Second get_actor call should succeed after the collision retry path.
    call_count = {"count": 0}

    def fake_get_actor_retry(name, namespace=None):
        call_count["count"] += 1
        if call_count["count"] < 2:
            raise ValueError(name)
        return registry

    monkeypatch.setattr(load_balancer.ray, "get_actor", fake_get_actor_retry)

    result = load_balancer._get_or_create_lease_registry("shared_vllm")

    assert result is registry


def test_create_llm_actors_shared_pool_respects_capacity_and_reuses_pool(monkeypatch):
    class _RemoteCall:
        def __init__(self, fn):
            self._fn = fn

        def remote(self, *args, **kwargs):
            return self._fn(*args, **kwargs)

    class _FakeRegistry:
        def __init__(self):
            self.groups = {}
            self.meta = {}
            self.reserve_shared_vllm_pool = _RemoteCall(self._reserve)
            self.register_shared_vllm_pool_actors = _RemoteCall(self._register)
            self.get_shared_vllm_pool_state = _RemoteCall(self._state)
            self.reap_expired_shared_vllm_pools = _RemoteCall(self._reap)

        def _reserve(
            self,
            group_key,
            client_id,
            actor_name_prefix,
            actor_backend,
            num_actors,
            capacity,
        ):
            pools = self.groups.setdefault(group_key, [])
            for pool_key in pools:
                meta = self.meta[pool_key]
                clients = meta["clients"]
                if client_id in clients:
                    return {
                        "pool_key": pool_key,
                        "pool_prefix": meta["pool_prefix"],
                        "actor_names": meta["actor_names"],
                        "is_creator": False,
                        "status": meta["status"],
                        "active_clients": len(clients),
                        "capacity": meta["capacity"],
                    }
                if len(clients) < meta["capacity"]:
                    clients.add(client_id)
                    return {
                        "pool_key": pool_key,
                        "pool_prefix": meta["pool_prefix"],
                        "actor_names": meta["actor_names"],
                        "is_creator": False,
                        "status": meta["status"],
                        "active_clients": len(clients),
                        "capacity": meta["capacity"],
                    }

            pool_index = len(pools)
            pool_prefix = f"{actor_name_prefix}_pool{pool_index}"
            pool_key = f"{actor_backend}:{pool_prefix}:{num_actors}"
            pools.append(pool_key)
            self.meta[pool_key] = {
                "pool_prefix": pool_prefix,
                "actor_names": [],
                "clients": {client_id},
                "capacity": capacity,
                "status": "bootstrapping",
            }
            return {
                "pool_key": pool_key,
                "pool_prefix": pool_prefix,
                "actor_names": [],
                "is_creator": True,
                "status": "bootstrapping",
                "active_clients": 1,
                "capacity": capacity,
            }

        def _register(self, pool_key, actor_names):
            meta = self.meta[pool_key]
            meta["actor_names"] = actor_names
            meta["status"] = "ready"
            return {"pool_key": pool_key, "actor_names": actor_names, "status": "ready"}

        def _state(self, pool_key):
            meta = self.meta[pool_key]
            return {
                "pool_key": pool_key,
                "actor_names": meta["actor_names"],
                "status": meta["status"],
                "capacity": meta["capacity"],
            }

        def _reap(self, now):
            return []

    registry = _FakeRegistry()
    actor_handles = {}
    created_actor_names = []

    def fake_get_actor(name, namespace=None):
        return actor_handles[name]

    class _OptionsProxy:
        def __init__(self, opts):
            self.opts = opts

        def remote(self, **kwargs):
            name = self.opts["name"]
            handle = Mock(name=name)
            actor_handles[name] = handle
            created_actor_names.append(name)
            return handle

    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer._get_or_create_lease_registry",
        lambda actor_namespace=None: registry,
    )
    monkeypatch.setattr("YSimulator.YClient.llm_utils.load_balancer.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.llm_utils.load_balancer.ray.get_actor", fake_get_actor
    )
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.vllm_service.VLLMService.options",
        lambda **kwargs: _OptionsProxy(kwargs),
    )

    base_config = {
        "model": "AMead10/Llama-3.2-3B-Instruct-AWQ",
        "client_name": "client-a",
        "_lease_client_id": "client-a:pid:run1",
        "gpu_per_actor": 1.0,
        "shared_pool": {"enabled": True, "max_clients_per_worker": 2},
    }

    first = create_llm_actors(
        llm_config=base_config.copy(),
        prompts_config={},
        num_actors=2,
        backend="vllm",
        logger=Mock(),
    )

    assert first.get_all_actors() == [actor_handles[created_actor_names[0]], actor_handles[created_actor_names[1]]]
    assert created_actor_names[:2] == [
        f"{_build_vllm_pool_prefix(base_config['model'])}_pool0_vllm_0",
        f"{_build_vllm_pool_prefix(base_config['model'])}_pool0_vllm_1",
    ]

    second_config = base_config.copy()
    second_config["_lease_client_id"] = "client-b:pid:run2"
    second = create_llm_actors(
        llm_config=second_config,
        prompts_config={},
        num_actors=2,
        backend="vllm",
        logger=Mock(),
    )
    assert second.get_all_actors() == first.get_all_actors()
    assert len(created_actor_names) == 2

    third_config = base_config.copy()
    third_config["_lease_client_id"] = "client-c:pid:run3"
    third = create_llm_actors(
        llm_config=third_config,
        prompts_config={},
        num_actors=2,
        backend="vllm",
        logger=Mock(),
    )
    assert len(created_actor_names) == 4
    assert created_actor_names[2:] == [
        f"{_build_vllm_pool_prefix(base_config['model'])}_pool1_vllm_0",
        f"{_build_vllm_pool_prefix(base_config['model'])}_pool1_vllm_1",
    ]
    assert third.get_all_actors() == [actor_handles[created_actor_names[2]], actor_handles[created_actor_names[3]]]
