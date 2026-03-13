from unittest.mock import Mock

from YSimulator.YClient.llm_utils.load_balancer import _build_vllm_pool_prefix, create_llm_actors


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

    def fake_get_actor(name):
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
    assert llm_config["_reused_existing_pool"] is True
