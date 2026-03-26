from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from YSimulator.YClient.LLM_interactions.remote_batch_service import (
    RemoteBatchLLMService,
    probe_remote_batch_support,
)
from YSimulator.YClient.llm_utils.load_balancer import create_llm_actors


class _FakeChatResponse:
    def __init__(self, content):
        self.content = content


class _FakeChatOllama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.batch_calls = []
        self.invoke_calls = []

    def batch(self, prompts):
        self.batch_calls.append(list(prompts))
        return [_FakeChatResponse(f"batch:{idx}") for idx, _ in enumerate(prompts)]

    def invoke(self, prompt):
        self.invoke_calls.append(prompt)
        return _FakeChatResponse("single:0")


def test_probe_remote_batch_support_success(monkeypatch):
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.ChatOllama", _FakeChatOllama
    )

    supported = probe_remote_batch_support(
        {"address": "localhost", "port": 11434, "model": "llama3.2"}, logger=Mock()
    )

    assert supported is True


def test_probe_remote_batch_support_failure(monkeypatch):
    class _FailingChatOllama:
        def __init__(self, **kwargs):
            pass

        def batch(self, prompts):
            raise RuntimeError("no batch")

    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.ChatOllama",
        _FailingChatOllama,
    )

    supported = probe_remote_batch_support(
        {"address": "localhost", "port": 11434, "model": "llama3.2"}, logger=Mock()
    )

    assert supported is False


def test_create_llm_actors_uses_remote_batch_service_when_probe_succeeds(monkeypatch):
    llm_config = {"address": "localhost", "port": 11434, "model": "llama3.2"}
    prompts_config = {}
    actor_handle = Mock(name="remote-batch-actor")

    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.probe_remote_batch_support",
        lambda llm_config, logger=None: True,
    )

    class _OptionsProxy:
        def __init__(self, opts):
            self.opts = opts

        def remote(self, **kwargs):
            return actor_handle

    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.RemoteBatchLLMService.options",
        lambda **kwargs: _OptionsProxy(kwargs),
    )
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.llm_service.LLMService.options",
        Mock(side_effect=AssertionError("standard service should not be created")),
    )

    actor = create_llm_actors(
        llm_config=llm_config,
        prompts_config=prompts_config,
        num_actors=1,
        backend="ollama",
        logger=Mock(),
    )

    assert actor is actor_handle
    assert llm_config["_resolved_service_backend"] == "remote_batch"
    assert llm_config["_resolved_pool_backend"] == "remote_batch"


def test_create_llm_actors_respects_batching_policy_off(monkeypatch):
    llm_config = {
        "address": "localhost",
        "port": 11434,
        "model": "llama3.2",
        "batching_policy": "off",
    }
    prompts_config = {}
    actor_handle = Mock(name="standard-actor")

    class _OptionsProxy:
        def __init__(self, opts):
            self.opts = opts

        def remote(self, **kwargs):
            return actor_handle

    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.llm_service.LLMService.options",
        lambda **kwargs: _OptionsProxy(kwargs),
    )
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.probe_remote_batch_support",
        Mock(side_effect=AssertionError("probe should not run when batching_policy=off")),
    )

    actor = create_llm_actors(
        llm_config=llm_config,
        prompts_config=prompts_config,
        num_actors=1,
        backend="ollama",
        logger=Mock(),
    )

    assert actor is actor_handle
    assert llm_config["_resolved_service_backend"] == "ollama"
    assert llm_config["_resolved_pool_backend"] == "ollama"


def test_create_llm_actors_force_requires_batch_support(monkeypatch):
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.probe_remote_batch_support",
        lambda llm_config, logger=None: False,
    )

    with pytest.raises(RuntimeError, match="does not support batch requests"):
        create_llm_actors(
            llm_config={
                "address": "localhost",
                "port": 11434,
                "model": "llama3.2",
                "batching_policy": "force",
            },
            prompts_config={},
            num_actors=1,
            backend="ollama",
            logger=Mock(),
        )


def test_remote_batch_service_generate_post_batch_matches_vllm_contract(monkeypatch):
    monkeypatch.setattr(
        "YSimulator.YClient.LLM_interactions.remote_batch_service.ChatOllama", _FakeChatOllama
    )

    service_cls = RemoteBatchLLMService.__ray_metadata__.modified_class
    service = service_cls(
        llm_config={
            "address": "localhost",
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.7,
            "max_tokens": 64,
        },
        prompts_config={
            "personas": {"1": "Persona one"},
            "generate_post": {
                "system_template": "{persona}",
                "user_template": "Day {day} slot {slot}.{topic_instruction}",
            },
        },
        logging_config={"enable_actor_log": False},
    )

    results = service.generate_post_batch(
        [
            {"cluster_id": 1, "day": 1, "slot": 1, "agent_attrs": {"topic": "AI"}},
            {"cluster_id": 1, "day": 1, "slot": 2, "agent_attrs": {"topic": "ML"}},
        ]
    )

    assert results == ["batch:0", "batch:1"]
    assert service.get_capabilities()["supports_batch_posts"] is True
    assert service.get_service_metadata()["backend"] == "remote_batch"
