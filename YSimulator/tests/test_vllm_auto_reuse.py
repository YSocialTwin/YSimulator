from unittest.mock import Mock

from YSimulator.YClient.llm_utils.load_balancer import (
    DEFAULT_VLLM_SHARED_NAMESPACE,
    _build_vllm_pool_prefix,
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
        lambda model_name, actor_namespace=None, logger=None: (
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
        lambda model_name, actor_namespace=None, logger=None: (
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
