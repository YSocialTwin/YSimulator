"""F6.2: cross-post as an agent action in YSimulator: adapter (server) and client choice. No coordinator, no real LLM."""

import json
import random
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from sqlalchemy.orm import Session  # noqa: E402

from YSimulator import prompt_store  # noqa: E402
from YSimulator.YClient import federation  # noqa: E402
from YSimulator.YServer.classes.models import Post  # noqa: E402
from YSimulator.YServer.federation.adapter import YSimulatorAdapter  # noqa: E402
from tests.test_federation_bus import ROUND, U, adapter_for, host, new_post  # noqa: E402,F401

DEST = {"g1": [{"member": "forum", "local_account_id": "201"}, {"member": "dating", "local_account_id": "301"}],
        "g2": [{"member": "forum", "local_account_id": "202"}]}


def agent_adapter(host, **kw):  # noqa: F811
    a = adapter_for(host, crosspost_mode="agent_action", **kw)
    a.set_destinations(DEST)
    return a


def test_the_agent_sends_a_crosspost_with_its_own_text_to_each_chosen_destination(host):  # noqa: F811
    a = agent_adapter(host)
    pid = new_post(host, 1, "original")
    a.mark_for_export(pid, [{"member": "forum", "text": "Title\nbody"}, {"member": "dating", "text": "hi there"}])
    out = a.export_outbox(3)
    assert [(e.payload_type, e.target_member, e.payload["target_account_id"], e.payload["text_excerpt"]) for e in out] == [
        ("crosspost.v1", "dating", "301", "hi there"), ("crosspost.v1", "forum", "201", "Title\nbody")]
    assert [e.seq for e in out] == [1, 2]  # seq 0 belongs to the post itself: no content.v1 is sent for it
    assert all(e.source_member == "hpc" and e.tick_emitted == 3 for e in out)
    assert out[0].payload["global_agent_id"] == "g1" and out[0].payload["source_ref"].startswith("ysocial://1/hpc/post/")
    a.set_destinations({})  # a retry keeps the account fixed at the first export
    assert [e.to_dict() for e in a.export_outbox(3)] == [e.to_dict() for e in out]
    assert a.export_outbox(4) == []


def test_a_destination_without_an_active_account_is_dropped_and_a_plain_mark_still_sends_content(host):  # noqa: F811
    a = agent_adapter(host)
    p2 = new_post(host, 2, "two")
    a.mark_for_export(p2, [{"member": "forum", "text": "ok"}, {"member": "dating", "text": "no account"}])
    p1 = new_post(host, 1, "nowhere")
    a.mark_for_export(p1, [])
    out = a.export_outbox(3)
    assert sorted((e.payload_type, e.target_member) for e in out) == [("content.v1", "coordinator"), ("crosspost.v1", "forum")]
    assert len({e.seq for e in out}) == len(out)


def test_exposure_numbers_never_reuse_a_sequence_number(host):  # noqa: F811
    a = agent_adapter(host, emit_exposures=True, export_policy="all")
    a.mark_for_export(new_post(host, 1, "with xp"), [{"member": "forum", "text": "t"}])
    new_post(host, 2, "plain")
    out = a.export_outbox(3)
    assert len({e.seq for e in out}) == len(out)


def test_targets_are_ignored_in_coordinator_rule_mode(host):  # noqa: F811
    a = adapter_for(host)
    a.mark_for_export(new_post(host, 1, "x"), [{"member": "forum", "text": "t"}])
    assert [(e.payload_type, e.target_member) for e in a.export_outbox(3)] == [("content.v1", "coordinator")]


def test_destination_members_and_an_unknown_mode(host):  # noqa: F811
    a = agent_adapter(host)
    assert a.destination_members(U[1]) == ["dating", "forum"] and a.destination_members(U[3]) == []
    with pytest.raises(ValueError):
        YSimulatorAdapter("hpc", 1, host=host, crosspost_mode="nope")


# -- client -----------------------------------------------------------------------------------------------------
def _server(dests):
    return SimpleNamespace(get_federation_destinations=SimpleNamespace(remote=lambda agent_id: dests))


def _on(monkeypatch, propensity=1.0, mode="agent_action"):
    import ray

    monkeypatch.setattr(ray, "get", lambda ref: ref)
    federation.install({"federation": dict(enabled=True, seed=3, member="hpc", crosspost_mode=mode, crosspost_propensity=propensity)})


def post_action(text="I love the new park downtown. Everyone should go."):
    return SimpleNamespace(action_type="POST", agent_id="a1", content=text)


def test_client_off_or_other_mode_changes_nothing(monkeypatch):
    federation.install({})
    acts = [post_action()]
    state = random.getstate()
    federation.mark_posts(acts, _server(["forum"]))
    assert not hasattr(acts[0], "crosspost") and random.getstate() == state
    _on(monkeypatch, mode="coordinator_rule")
    federation.mark_posts(acts, _server(["forum"]))
    assert acts[0].crosspost is True and not hasattr(acts[0], "crosspost_to")  # the old behaviour
    federation.install({})


def test_client_agent_action_chooses_destinations_and_texts(monkeypatch):
    _on(monkeypatch)
    acts = [post_action(), SimpleNamespace(action_type="LIKE", agent_id="a1")]
    federation.set_adapt(lambda agent, dest, text: "from the model" if dest == "dating" else None)
    federation.mark_posts(acts, _server(["forum", "dating"]))
    assert acts[0].crosspost is True
    assert acts[0].crosspost_to == [{"member": "dating", "text": "from the model"},
                                    {"member": "forum", "text": "I love the new park downtown.\nI love the new park downtown. Everyone should go."}]
    assert not hasattr(acts[1], "crosspost")
    federation.install({})


def test_client_no_destination_zero_propensity_or_unreachable_server(monkeypatch):
    _on(monkeypatch)
    for server in (_server([]), SimpleNamespace()):
        acts = [post_action()]
        federation.mark_posts(acts, server)
        assert not hasattr(acts[0], "crosspost")
    _on(monkeypatch, propensity=0.0)
    acts = [post_action()]
    federation.mark_posts(acts, _server(["forum"]))
    assert not hasattr(acts[0], "crosspost")
    federation.install({})


def test_client_one_draw_per_destination_from_its_own_generator(monkeypatch):
    _on(monkeypatch, propensity=0.5)
    state = random.getstate()
    acts = [post_action()]
    federation.mark_posts(acts, _server(["forum", "dating", "photo_sharing"]))
    assert random.getstate() == state
    expected = random.Random(3)
    want = [d for d in ["dating", "forum", "photo_sharing"] if expected.random() < 0.5]
    assert [t["member"] for t in getattr(acts[0], "crosspost_to", [])] == want
    federation.install({})


@pytest.mark.parametrize("dest,reply,expected", [
    ("microblogging", '"Great park! #city"', "Great park! #city"),
    ("microblogging", "<think>hm</think>\nPost: nice day out", "nice day out"),
    ("microblogging", "x" * 400, "x" * 280),
    ("microblogging", "  ", None),
    ("forum", "Title: The new park\nIt opened last week. Has anyone been?", "The new park\nIt opened last week. Has anyone been?"),
    ("forum", "", None),
    ("photo_sharing", "```\nGolden hour ✨\n```", "Golden hour ✨"),
    ("instant_messaging", "«hey, did you see it?»", "hey, did you see it?"),
    ("dating", "y" * 250, "y" * 200),
])
def test_recorded_model_replies_are_parsed(dest, reply, expected):
    assert federation.parse_reply(dest, reply) == expected


def test_the_five_prompts_exist_in_both_languages_and_render():
    root = Path(prompt_store.__file__).parent
    for suffix in ("", ".it"):
        pack = json.loads((root / f"prompts_internal{suffix}.json").read_text(encoding="utf-8"))
        for dest in federation.LIMITS:
            assert f"crosspost_adapt_{dest}" in pack
    for dest in federation.LIMITS:
        for lang in ("en", "it"):
            text = prompt_store.prompt(federation.adapt_prompt_key(dest), language=lang, source_platform="forum", text="SAMPLE")
            assert "SAMPLE" in text and "{" not in text
