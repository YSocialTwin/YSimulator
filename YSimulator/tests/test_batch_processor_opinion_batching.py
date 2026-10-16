from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from YSimulator.YClient.simulation.batch_processor import BatchProcessor


class _RemoteFn:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


class _FakeServer:
    def __init__(self):
        self.get_post_topics = _RemoteFn(
            lambda target_post, client_id=None: ["topic1"] if target_post == "post1" else []
        )
        self.get_topic_name_from_id = _RemoteFn(
            lambda topic_id, client_id=None: "Politics" if topic_id == "topic1" else None
        )
        self.get_latest_agent_opinion = _RemoteFn(self._get_latest_agent_opinion)
        self.get_neighbors_opinions = _RemoteFn(lambda agent_id, topic_id, client_id=None: [])

    @staticmethod
    def _get_latest_agent_opinion(agent_id, topic_id, client_id=None):
        if topic_id != "topic1":
            return None
        if agent_id == "agent1":
            return 0.5
        if agent_id == "author1":
            return 0.9
        return None


class _FakeLLMActor:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.last_requests = None
        self.evaluate_opinion_batch = _RemoteFn(self._evaluate_batch)

    def _evaluate_batch(self, requests):
        self.call_count += 1
        self.last_requests = requests
        return self.responses


class _FakeVLLMActor:
    def __init__(self, outputs):
        self.outputs = outputs
        self.last_requests = None
        self.generate_post_batch = _RemoteFn(self._generate_post_batch)
        self.generate_post = _RemoteFn(lambda cluster_id, day, slot, attrs=None: "single text")

    def _generate_post_batch(self, requests):
        self.last_requests = requests
        return self.outputs


class _FakeOpinionManager:
    def __init__(self, model_name="llm_evaluation"):
        self.opinion_config = {
            "model_name": model_name,
            "parameters": {"evaluation_scope": "interlocutor_only", "cold_start": "neutral"},
            "opinion_groups": {
                "Strongly against": [0.0, 0.2],
                "Against": [0.2, 0.4],
                "Neutral": [0.4, 0.6],
                "In favor": [0.6, 0.8],
                "Strongly in favor": [0.8, 1.0],
            },
        }
        self.standard_calls = 0

    def calculate_opinion_updates(self, agent_id, target_post, post_data):
        self.standard_calls += 1
        return {"topic1": 0.42}


def test_batch_opinion_updates_uses_vllm_batch(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.simulation.batch_processor.ray.wait",
        lambda futures, num_returns=1, timeout=None: (futures, []),
    )

    fake_server = _FakeServer()
    fake_llm = _FakeLLMActor(["AGREE"])
    manager = _FakeOpinionManager(model_name="llm_evaluation")

    processor = BatchProcessor(
        server=fake_server,
        client_id="client-1",
        llm=fake_llm,
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )
    processor.batch_handler.gather_with_timeout = Mock(return_value=[["AGREE"]])

    actions = [SimpleNamespace(updated_opinions=None)]
    opinion_requests = [
        {
            "agent_id": "agent1",
            "target_post": "post1",
            "post_data": {"user_id": "author1", "tweet": "Some post about politics"},
            "action_index": 0,
        }
    ]

    processor._batch_evaluate_and_update_opinions(
        opinion_requests, actions, manager.calculate_opinion_updates
    )

    assert fake_llm.call_count == 1
    assert manager.standard_calls == 0
    assert fake_llm.last_requests[0]["topic"] == "Politics"
    # AGREE should move one class from Neutral toward Strongly in favor -> In favor midpoint 0.7
    assert actions[0].updated_opinions["topic1"] == 0.7


def test_batch_opinion_updates_falls_back_for_non_llm_model(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)

    fake_server = _FakeServer()
    fake_llm = _FakeLLMActor(["AGREE"])
    manager = _FakeOpinionManager(model_name="bounded_confidence")

    processor = BatchProcessor(
        server=fake_server,
        client_id="client-1",
        llm=fake_llm,
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )

    actions = [SimpleNamespace(updated_opinions=None)]
    opinion_requests = [
        {
            "agent_id": "agent1",
            "target_post": "post1",
            "post_data": {"user_id": "author1", "tweet": "Some post about politics"},
            "action_index": 0,
        }
    ]

    processor._batch_evaluate_and_update_opinions(
        opinion_requests, actions, manager.calculate_opinion_updates
    )

    assert fake_llm.call_count == 0
    assert manager.standard_calls == 1
    assert actions[0].updated_opinions == {"topic1": 0.42}


def test_process_vllm_batch_accepts_image_post_tuple(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.simulation.batch_processor.ray.wait",
        lambda futures, num_returns=1, timeout=None: (futures, []),
    )
    monkeypatch.setattr(
        "YSimulator.YClient.simulation.batch_processor.annotate_text",
        lambda *args, **kwargs: {"hashtags": [], "mentions": []},
    )

    processor = BatchProcessor(
        server=Mock(),
        client_id="client-1",
        llm=_FakeVLLMActor(["caption text"]),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )
    processor.batch_handler.gather_with_timeout = Mock(return_value=[["caption text"]])

    actions = []
    processor._process_vllm_batch(
        [
            (
                "agent-1",
                3,
                None,
                None,
                1,
                2,
                {"name": "Agent One"},
                "image-77",
            )
        ],
        actions,
    )

    assert len(actions) == 1
    assert actions[0].action_type == "POST"
    assert actions[0].image_id == "image-77"
    assert actions[0].content == "caption text"


def test_process_vllm_batch_falls_back_to_single_request_when_batch_call_times_out(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)
    monkeypatch.setattr(
        "YSimulator.YClient.simulation.batch_processor.ray.wait",
        lambda futures, num_returns=1, timeout=None: (list(futures), []),
    )

    processor = BatchProcessor(
        server=Mock(),
        client_id="client-1",
        llm=_FakeVLLMActor(["unused"]),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )

    resolved = []

    def fake_resolve_batch_future(future, error_message, timeout_seconds=45):
        resolved.append(error_message)
        if len(resolved) == 1:  # the batch call times out ...
            raise TimeoutError("slow")
        return future  # ... and the single-request fallback answers

    processor._resolve_batch_future = fake_resolve_batch_future
    actions = []

    processor._process_vllm_batch(
        [("agent-1", 3, "future-1", None, 1, 2, {"name": "Agent One"})],
        actions,
    )

    assert resolved[1].endswith("single-request fallback")
    assert len(actions) == 1
    assert actions[0].action_type == "POST"
    assert actions[0].content == "single text"


def _processor_with_failing_batches():
    processor = BatchProcessor(
        server=Mock(),
        client_id="client-1",
        llm=Mock(),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )
    calls = []

    def batch_call_fn(requests):
        calls.append(("batch", [req["id"] for req in requests]))
        raise TimeoutError("slow batch")

    def single_call_fn(request):
        calls.append(("single", request["id"]))
        return ("single", request["id"])

    def fake_resolve_batch_future(future, error_message, timeout_seconds=45):
        kind, value = future
        return [f"resolved-{value}"]

    processor._resolve_batch_future = fake_resolve_batch_future
    return processor, calls, batch_call_fn, single_call_fn


def test_vllm_batch_request_helper_retries_a_failing_chunk_with_backoff_then_raises(monkeypatch):
    sleeps = []
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.time.sleep", sleeps.append)
    processor, calls, batch_call_fn, single_call_fn = _processor_with_failing_batches()

    with pytest.raises(TimeoutError):
        processor._resolve_vllm_request_batches(
            batch_requests=[{"id": 1}, {"id": 2}],
            batch_call_fn=batch_call_fn,
            single_call_fn=single_call_fn,
            error_message="test batch",
            timeout_seconds=45,
        )

    assert calls == [("batch", [1, 2])] * 3  # a multi-request chunk is retried, never split
    assert sleeps == [1.5, 3.0]  # exponential backoff between the attempts


def test_vllm_batch_request_helper_uses_the_single_path_for_a_one_request_chunk(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.time.sleep", lambda s: None)
    processor, calls, batch_call_fn, single_call_fn = _processor_with_failing_batches()

    results = processor._resolve_vllm_request_batches(
        batch_requests=[{"id": 1}, {"id": 2}],
        batch_call_fn=batch_call_fn,
        single_call_fn=single_call_fn,
        error_message="test batch",
        timeout_seconds=45,
        max_chunk_size=1,
    )

    assert results == ["resolved-1", "resolved-2"]
    assert calls == [("batch", [1]), ("single", 1), ("batch", [2]), ("single", 2)]
