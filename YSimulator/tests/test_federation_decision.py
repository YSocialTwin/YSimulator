"""P14: the agent's LLM decides whether (and where) to cross-post (publish trigger), with a fake model: YSimulator."""

import json
import logging
import random
import time
from types import SimpleNamespace

import pytest

from YSimulator import prompt_store
from YSimulator.YClient import federation

DECIDE_KEY = "crosspost_decide"  # not a literal at the call: the call-site ratchet checks the real call sites only
INTERACTION_KEY = "crosspost_decide_interaction"


def _on(monkeypatch, dests, mode="agent_action", propensity=1.0, decision="llm", **kw):
    section = dict(
        enabled=True,
        seed=3,
        member="hpc",
        crosspost_mode=mode,
        crosspost_propensity=propensity,
        **kw,
    )
    if decision is not None:
        section["crosspost_decision"] = decision
    federation.install({"federation": section})
    monkeypatch.setattr(federation, "destinations", lambda server, agent_id: list(dests))


class Fake:
    def __init__(self, reply, has_model=True):
        self.reply, self.calls, self.has_model = reply, [], has_model
        federation.set_decider(self, lambda agent_id: self.has_model)

    def __call__(self, agent_id, trigger, text, lines, context=None):
        self.calls.append((agent_id, trigger, text, lines))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(agent_id, text) if callable(self.reply) else self.reply


def _acts(n=1, kind="POST"):
    return [
        SimpleNamespace(
            action_type=kind, agent_id=f"a{i}", content=f"post number {i} about the park"
        )
        for i in range(n)
    ]


def _marks(acts):
    return [(getattr(a, "crosspost", False), getattr(a, "crosspost_to", None)) for a in acts]


@pytest.fixture(autouse=True)
def _off():
    yield
    federation.install({})


def test_random_mode_is_bit_identical_and_never_asks(monkeypatch):
    out = []
    for decision in (None, "random"):
        _on(monkeypatch, ["forum"], mode="coordinator_rule", propensity=0.5, decision=decision)
        ask = Fake("{}")
        acts = _acts(40) + _acts(1, "LIKE")
        state = random.getstate()
        federation.mark_posts(acts, object(), day=1)
        assert random.getstate() == state and ask.calls == []
        out.append((_marks(acts), federation._state["rng"].getstate()))
    assert out[0] == out[1]
    ref = random.Random(3)
    assert [m[0] for m in out[0][0][:40]] == [ref.random() < 0.5 for _ in range(40)]


def test_agent_action_the_model_chooses_and_the_generator_is_untouched(monkeypatch):
    _on(monkeypatch, ["dating", "forum"], propensity=0.0)
    ask = Fake(
        json.dumps(
            {
                "crosspost": True,
                "destinations": ["forum", "myspace"],
                "text": {"forum": "Title\nBody"},
            }
        )
    )
    before = federation._state["rng"].getstate()
    acts = _acts(2)
    federation.mark_posts(acts, object(), day=2)
    assert _marks(acts) == [(True, [{"member": "forum", "text": "Title\nBody"}])] * 2
    assert len(ask.calls) == 2 and federation._state["rng"].getstate() == before
    assert "- dating (200)" in ask.calls[0][3]


def test_coordinator_rule_the_model_only_marks(monkeypatch):
    _on(monkeypatch, ["forum"], mode="coordinator_rule", propensity=0.0)
    Fake(
        lambda agent, text: '{"crosspost": %s, "destinations": ["forum"]}'
        % ("true" if agent == "a0" else "false")
    )
    acts = _acts(2)
    federation.mark_posts(acts, object(), day=2)
    assert _marks(acts) == [(True, None), (False, None)]


@pytest.mark.parametrize("reply", ["no json", '{"crosspost": "maybe"}', OSError("down")])
def test_failures_fall_back_to_the_draw_and_are_logged(monkeypatch, caplog, reply):
    _on(monkeypatch, ["forum"], mode="coordinator_rule", propensity=1.0)
    Fake(reply)
    acts = _acts(1)
    with caplog.at_level(logging.INFO, logger="YSimulator.federation"):
        federation.mark_posts(acts, object(), day=2)
    assert _marks(acts) == [(True, None)] and "source=fallback" in caplog.text


def test_timeout_falls_back(monkeypatch):
    monkeypatch.setattr(federation, "DECISION_TIMEOUT", 0.05)
    _on(monkeypatch, ["forum"], mode="coordinator_rule", propensity=1.0)
    Fake(lambda a, t: time.sleep(1) or "{}")
    acts = _acts(1)
    started = time.monotonic()
    federation.mark_posts(acts, object(), day=2)
    assert _marks(acts) == [(True, None)] and time.monotonic() - started < 0.8


def test_all_destinations_unknown_means_no_cross_post(monkeypatch):
    _on(monkeypatch, ["forum"])
    Fake('{"crosspost": true, "destinations": ["myspace"]}')
    acts = _acts(1)
    federation.mark_posts(acts, object(), day=2)
    assert _marks(acts) == [(False, None)]


def test_cap_per_agent_per_day(monkeypatch):
    _on(
        monkeypatch,
        ["forum"],
        mode="coordinator_rule",
        propensity=1.0,
        crosspost_decision_max_per_day=2,
    )
    ask = Fake('{"crosspost": false}')
    for day, expected in ((1, 2), (1, 2), (2, 3)):
        acts = [
            SimpleNamespace(action_type="POST", agent_id="a0", content="some text")
            for _ in range(1 if day == 2 else 3)
        ]
        federation.mark_posts(acts, object(), day=day)
        if day == 1 and expected == 2 and len(ask.calls) == 2:
            assert (
                _marks(acts)[2][0] is True
            )  # the third post of the day: cap reached, the Bernoulli draw (propensity 1)
    assert len(ask.calls) == 3


def test_rule_based_agent_keeps_the_draw_and_is_not_asked(monkeypatch):
    _on(monkeypatch, ["forum"], mode="coordinator_rule", propensity=0.5)
    ask = Fake('{"crosspost": false}', has_model=False)
    acts = _acts(30)
    federation.mark_posts(acts, object(), day=1)
    ref = random.Random(3)
    assert [m[0] for m in _marks(acts)] == [
        ref.random() < 0.5 for _ in range(30)
    ] and ask.calls == []


def test_no_destination_and_content_not_eligible_are_not_asked(monkeypatch):
    _on(monkeypatch, [])
    ask = Fake('{"crosspost": true, "destinations": ["forum"]}')
    acts = _acts(1)
    federation.mark_posts(acts, object(), day=1)
    assert _marks(acts) == [(False, None)] and ask.calls == []
    _on(monkeypatch, ["forum"], crosspost_content=["news"])
    ask = Fake('{"crosspost": true, "destinations": ["forum"]}')
    federation.mark_posts(_acts(1), object(), day=1)
    assert ask.calls == []


def test_only_the_publish_trigger_is_supported_by_this_client(monkeypatch):
    _on(monkeypatch, ["forum"], crosspost_decision_triggers=["interaction"])
    assert federation._state["triggers"] == () and not federation.decision_for("publish")
    _on(monkeypatch, ["forum"], crosspost_decision_triggers=["publish", "interaction"])
    assert federation._state["triggers"] == ("publish",)


def test_the_prompts_exist_and_the_agent_side(monkeypatch):
    for lang in ("en", "it"):
        text = prompt_store.prompt(
            DECIDE_KEY,
            language=lang,
            name="Ann",
            profile="34",
            text="SAMPLE",
            trigger=prompt_store.get("crosspost_decide_publish", lang),
            destinations="- forum (2000)",
        )
        assert "SAMPLE" in text and '"crosspost"' in text and "{name}" not in text
    from YSimulator.YClient.client import SimulationClient

    cls = (
        getattr(SimulationClient, "__ray_metadata__").modified_class
        if hasattr(SimulationClient, "__ray_metadata__")
        else SimulationClient
    )
    client = object.__new__(cls)
    client.llm = object()
    client.agent_profiles = [
        SimpleNamespace(
            id="a0",
            llm=True,
            username="Ann",
            age=30,
            gender="f",
            nationality="it",
            profession="nurse",
            leaning="center",
            education_level="bsc",
        ),
        SimpleNamespace(id="a1", llm=False, username="Bob"),
    ]
    assert (
        client._crosspost_has_model("a0")
        and not client._crosspost_has_model("a1")
        and not client._crosspost_has_model("zz")
    )
    client.llm = None
    assert not client._crosspost_has_model("a0")
