from unittest.mock import Mock

from YSimulator.YClient.simulation.batch_processor import BatchProcessor


class _RemoteFn:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


class _FakeLLM:
    def __init__(self, outputs):
        self.generate_read_reaction_batch = _RemoteFn(lambda requests: outputs)


def test_process_vllm_read_batch_creates_report_action(monkeypatch):
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)

    processor = BatchProcessor(
        server=Mock(),
        client_id="client-1",
        llm=_FakeLLM(["REPORT_TOXIC"]),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=Mock(),
    )

    actions = []
    secondary_follows = processor._process_vllm_read_batch(
        [
            (
                "agent-1",
                1,
                "post-9",
                None,
                {"post_content": "awful text", "agent_attrs": {"name": "A"}},
            )
        ],
        actions,
        lambda agent_id, target_post, post_data: None,
    )

    assert secondary_follows == []
    assert len(actions) == 1
    assert actions[0].action_type == "REPORT"
    assert actions[0].target_post_id == "post-9"
    assert actions[0].report_type == "toxic"
