from types import SimpleNamespace
from unittest.mock import Mock

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
