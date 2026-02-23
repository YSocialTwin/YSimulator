"""Tests for memory prompt budget handling in action generators."""

from YSimulator.YClient.action_generators.base_generator import (
    ActionContext,
    ActionGeneratorResult,
    BaseActionGenerator,
)


class _DummyGenerator(BaseActionGenerator):
    def generate(self, agent, agent_type):  # pragma: no cover - unused in this test module
        return ActionGeneratorResult()


def test_inject_memory_context_respects_char_budget():
    fetched = {
        "items": [
            {"memory_id": "m1", "memory_text": "A" * 120},
            {"memory_id": "m2", "memory_text": "B" * 120},
            {"memory_id": "m3", "memory_text": "C" * 120},
        ],
        "last_query": None,
    }
    reinforced = {"ids": []}

    def _fetch(agent_id, query):
        fetched["last_query"] = query
        return fetched["items"]

    def _reinforce(agent_id, ids):
        reinforced["ids"] = ids
        return True

    context = ActionContext(
        day=1,
        slot=1,
        recent_posts=[],
        server=None,
        logger=None,
        client_id="c1",
        round_id="r1",
        memory_settings={
            "retrieval_top_k": 5,
            "prompt_memory_char_budget": 200,
            "prompt_memory_item_char_limit": 100,
        },
        fetch_agent_memory_fn=_fetch,
        record_memory_usage_fn=_reinforce,
    )
    generator = _DummyGenerator(context)
    agent_attrs = {}
    metadata = {}

    generator._inject_memory_context(
        "agent-1",
        agent_attrs,
        {"topic": "ai", "action_type": "POST"},
        metadata=metadata,
    )

    # Each item truncated to 100 chars; total budget 200 -> exactly 2 items.
    assert "memory_context" in agent_attrs
    assert len(agent_attrs["memory_context"]) == 2
    assert metadata["memory_items_used"] == 2
    assert metadata["memory_chars_used"] == 200
    assert reinforced["ids"] == ["m1", "m2"]
    assert fetched["last_query"]["max_items"] == 5


def test_inject_memory_context_noop_when_backend_returns_none():
    def _fetch(agent_id, query):
        return []

    context = ActionContext(
        day=1,
        slot=1,
        recent_posts=[],
        server=None,
        logger=None,
        client_id="c1",
        round_id="r1",
        memory_settings={
            "retrieval_top_k": 3,
            "prompt_memory_char_budget": 120,
            "prompt_memory_item_char_limit": 80,
        },
        fetch_agent_memory_fn=_fetch,
        record_memory_usage_fn=lambda _a, _ids: True,
    )
    generator = _DummyGenerator(context)
    agent_attrs = {"existing": "value"}
    metadata = {}

    generator._inject_memory_context(
        "agent-1",
        agent_attrs,
        {"topic": "policy", "action_type": "COMMENT"},
        metadata=metadata,
    )

    assert "memory_context" not in agent_attrs
    assert metadata == {}
