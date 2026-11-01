"""Human gateway of YSimulator: account, actions, cross-post marks, identity and exclusion from the group mechanisms."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from YSimulator.YServer.classes.models import Follow, Hashtag, Post, PostTopic, Reaction, User_mgmt  # noqa: E402
from YSimulator.YServer.federation.humans import HumanGateway, dispatch  # noqa: E402
from YSimulator.YServer.federation.tables import FederationCrosspost, FederationExport  # noqa: E402
from tests.test_federation_bus import U, adapter_for, host, new_post  # noqa: E402,F401

REPO = Path(__file__).resolve().parents[2]


def gateway(host, mode="agent_action"):  # noqa: F811
    return HumanGateway(host.engine, mode, "hpc")


def person(host, **kw):  # noqa: F811
    gw = gateway(host, **kw)
    status, body = gw.ensure("u7", "ann", "en", "human:7")
    assert status == 200 and body["created"]
    return gw, body["account_id"]


def test_ensure_creates_one_account_and_is_idempotent(host):  # noqa: F811
    gw, acc = person(host)
    assert gw.ensure("u7", "ann", "en", "human:7")[1] == {"ok": True, "account_id": acc, "username": "ann", "human_id": "human:7", "created": False}
    assert gw.ensure("u7", "ann", "en", "human:8")[0] == 409  # one person, one identity
    assert gw.ensure("u9", "u1", "en", "human:9") == (409, {"ok": False, "code": "username_taken"})
    with Session(host.engine) as s:
        assert s.get(User_mgmt, acc).user_type == "human"


def test_a_person_never_takes_the_identity_of_an_agent(host):  # noqa: F811
    gw, acc = person(host)
    a = adapter_for(host)
    assert a.agent_of(acc) == "human:7" and a.user_of("human:7") == acc
    assert a.agent_of(U[1]) == "g1"
    assert a.agent_of("unknown-account") == "unknown-account"  # not a person: no identity invented


def test_actions_are_stored_like_the_ones_of_an_agent(host):  # noqa: F811
    gw, acc = person(host)
    pid = new_post(host, 1, "their post")
    status, body = gw.actions(acc, [
        {"type": "post", "text": "hello #sport @u1", "topics": ["sport", "chess"]},
        {"type": "comment", "post_id": pid, "text": "nice"},
        {"type": "share", "post_id": pid, "text": "look"},
        {"type": "reaction", "post_id": pid, "reaction": "like"},
        {"type": "follow", "target": U[1]},
    ])
    assert status == 200 and body["ok"], body
    with Session(host.engine) as s:
        mine = {p.tweet: p for p in s.scalars(select(Post).where(Post.user_id == acc)).all()}
        assert mine["hello #sport @u1"].thread_id == mine["hello #sport @u1"].id
        assert mine["nice"].comment_to == pid and mine["look"].shared_from == pid
        assert len(s.scalars(select(PostTopic).where(PostTopic.post_id == mine["hello #sport @u1"].id)).all()) == 2
        assert s.scalars(select(Hashtag).where(Hashtag.hashtag == "#sport")).first() is not None
        assert s.scalars(select(Reaction).where(Reaction.user_id == acc)).one().type == "like"
        f = s.scalars(select(Follow).where(Follow.follower_id == acc)).one()
        assert f.user_id == U[1] and f.action == "follow"


def test_invalid_requests_are_refused_without_writing(host):  # noqa: F811
    gw, acc = person(host)
    assert gw.actions("someone-else", [{"type": "post", "text": "x"}])[0] == 403
    status, body = gw.actions(acc, [{"type": "post", "text": ""}, {"type": "reaction", "post_id": "nope", "reaction": "like"},
                                    {"type": "dance"}])
    assert status == 200 and not body["ok"]
    assert [r["code"] for r in body["results"]] == ["invalid_text", "unknown_post", "invalid_type"]
    assert dispatch(gw, "actions", {"account_id": acc, "actions": []})[0] == 400
    assert dispatch(gw, "nothing", {})[0] == 400
    with Session(host.engine) as s:
        assert s.scalars(select(Post).where(Post.user_id == acc)).first() is None


def test_a_crosspost_is_marked_and_exported_exactly_like_an_agents(host):  # noqa: F811
    gw, acc = person(host)
    _, body = gw.actions(acc, [{"type": "post", "text": "from a person",
                                "crosspost_to": [{"member": "forum", "text": "Title\nbody"}]}])
    pid = body["results"][0]["post_id"]
    with Session(host.engine) as s:
        assert s.get(FederationExport, pid) is not None
        assert s.get(FederationCrosspost, (pid, "forum")).text == "Title\nbody"
    a = adapter_for(host, crosspost_mode="agent_action")
    a.set_destinations({"human:7": [{"member": "forum", "local_account_id": "201"}]})
    out = a.export_outbox(3)
    assert [(e.payload_type, e.target_member) for e in out] == [("crosspost.v1", "forum")]
    assert out[0].payload["global_agent_id"] == "human:7" and out[0].payload["text_excerpt"] == "Title\nbody"


def test_in_rule_mode_only_the_post_is_marked(host):  # noqa: F811
    gw, acc = person(host, mode="coordinator_rule")
    _, body = gw.actions(acc, [{"type": "post", "text": "p", "crosspost_to": [{"member": "forum", "text": "t"}]}])
    pid = body["results"][0]["post_id"]
    with Session(host.engine) as s:
        assert s.get(FederationExport, pid) is not None
        assert s.get(FederationCrosspost, (pid, "forum")) is None


def test_people_are_outside_exposures_affective_reports_churn_and_attention(host):  # noqa: F811
    from YSimulator.YServer.classes.models import Recommendation
    from YSimulator.YServer.federation.tables import FederationMembership, FederationRef
    from ysocial_federation.schemas import MembershipChange

    gw, acc = person(host)
    a = adapter_for(host, emit_exposures=True)
    a.apply_membership([MembershipChange(global_agent_id="human:7", state="active", tick=0, reason="initial"),
                        MembershipChange(global_agent_id="g1", state="active", tick=0, reason="initial")])
    assert [s.global_agent_id for s in a.affective_report(1)] == ["g1"]
    assert a.churned_agents(1) == []
    a.apply_attention(1, {"human:7": 0.5, "g1": 0.5})
    assert set(a.attention_multipliers()) == {U[1]}
    pid = new_post(host, 2, "foreign")
    with Session(host.engine) as s:
        s.add(FederationRef(local_kind="post", local_id=pid, source_ref="ysocial://1/forum/post/1", fed_msg_id="m1"))
        s.add(Recommendation(id="r1", user_id=acc, round="round-1", post_ids=json.dumps([pid])))
        s.add(Recommendation(id="r2", user_id=U[1], round="round-1", post_ids=json.dumps([pid])))
        s.commit()
    viewers = {e.payload["viewer_global_agent_id"] for e in a.export_outbox(0) if e.payload_type == "exposure.v1"}
    assert viewers == {"g1"}


def test_the_script_serves_a_request_on_the_experiment_database(tmp_path):
    from sqlalchemy import create_engine

    from YSimulator.YServer.classes.models import Base, Round

    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "server_config.json").write_text(json.dumps({"server_name": "s", "database": {"type": "sqlite", "sqlite": {"filename": "x.db"}},
                                                           "federation": {"member": "hpc", "crosspost_mode": "agent_action"}}))
    engine = create_engine(f"sqlite:///{folder / 'database_server.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Round(id="r1", day=1, hour=1))
        s.commit()
    run = subprocess.run([sys.executable, str(REPO / "run_human_gateway.py"), str(folder)], cwd=REPO, capture_output=True, text=True,
                         input=json.dumps({"op": "ensure", "body": {"human_key": "u1", "username": "bob", "human_id": "human:1"}}))
    answer = json.loads(run.stdout.strip().splitlines()[-1])
    assert answer["status"] == 200 and answer["ok"] and answer["created"], run.stderr
    acc = answer["account_id"]
    run = subprocess.run([sys.executable, str(REPO / "run_human_gateway.py"), str(folder)], cwd=REPO, capture_output=True, text=True,
                         input=json.dumps({"op": "actions", "body": {"account_id": acc, "actions": [{"type": "post", "text": "hi"}]}}))
    assert json.loads(run.stdout.strip().splitlines()[-1])["ok"] is True, run.stderr
