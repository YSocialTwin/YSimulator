"""Bus and membership of the YSimulator server (F3.4c): export, ingest, membership, invisibility. No coordinator, no network."""

import inspect
import uuid
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ysocial_federation.envelope import Envelope  # noqa: E402
from ysocial_federation.schemas import MembershipChange  # noqa: E402

from YSimulator.YServer.classes.models import Base, Interest, Post, PostTopic, Round, User_mgmt  # noqa: E402
from YSimulator.YServer.federation.adapter import YSimulatorAdapter  # noqa: E402
from YSimulator.YServer.federation.tables import FederationMembership, FederationRef  # noqa: E402
from YSimulator.YServer.server import OrchestratorServer  # noqa: E402

CLASS = getattr(OrchestratorServer, "__ray_actor_class__", OrchestratorServer)
U = {n: f"user-{n}" for n in (1, 2, 3)}
ROUND = "round-1"


def _unwrap(name):
    return inspect.unwrap(getattr(CLASS, name))


class Host(SimpleNamespace):
    pass


@pytest.fixture()
def host(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Round(id=ROUND, day=1, hour=1))
        for n, uid in U.items():
            s.add(User_mgmt(id=uid, username=f"u{n}", password="x", language="it" if n == 2 else "en"))
        for name in ("sport", "music"):
            s.add(Interest(iid=f"i-{name}", interest=name))
        s.commit()

    def topic_by_name(name):
        with Session(engine) as s:
            return s.scalar(select(Interest.iid).where(Interest.interest == name))

    return Host(engine=engine, current_round_id=ROUND, recent_posts_cache=[],
                post_service=SimpleNamespace(get_topic_by_name=topic_by_name))


def adapter_for(host, **kw):
    return YSimulatorAdapter("hpc", 1, host=host, accounts={f"g{n}": u for n, u in U.items()}, **kw)


def new_post(host, n, text, comment_to="-1", topics=()):
    pid = str(uuid.uuid4())
    with Session(host.engine) as s:
        s.add(Post(id=pid, tweet=text, user_id=U[n], comment_to=comment_to, thread_id=pid, round=ROUND))
        for t in topics:
            s.add(PostTopic(id=str(uuid.uuid4()), post_id=pid, topic_id=f"i-{t}"))
        s.commit()
    return pid


def crosspost(seq, target, text="hello", topics=(), tick=4):
    return Envelope.create(1, "forum", "hpc", tick, seq, "crosspost.v1",
                           {"global_agent_id": "g9", "source_ref": f"ysocial://1/forum/post/{seq}", "kind": "post",
                            "text_excerpt": text, "image_ref": None, "topics": list(topics), "lang": "en",
                            "target_account_id": target})


def test_export_only_marked_root_posts_with_a_stable_retry(host):
    a = adapter_for(host)
    new_post(host, 1, "not marked")
    p2 = new_post(host, 2, "marked two", topics=("sport",))
    p1 = new_post(host, 1, "marked one")
    new_post(host, 1, "a reply", comment_to=p2)
    a.mark_for_export(p2)
    a.mark_for_export(p1)
    out = a.export_outbox(3)
    assert [(e.seq, e.payload["text_excerpt"], e.payload["global_agent_id"]) for e in out] == [
        (0, "marked one", "g1"), (1, "marked two", "g2")]
    assert out[1].payload["lang"] == "it" and out[1].payload["topics"] == ["sport"]
    assert out[0].payload["source_ref"] == f"ysocial://1/hpc/post/{p1}" and out[0].target_member == "coordinator"
    assert [e.fed_msg_id for e in a.export_outbox(3)] == [e.fed_msg_id for e in out]  # retry of the same tick
    assert a.export_outbox(4) == []  # exported once


def test_export_all_policy_takes_the_posts_of_the_current_round_but_not_replies_dormant_or_federated(host):
    a = adapter_for(host, export_policy="all")
    new_post(host, 1, "new root")
    new_post(host, 3, "dormant author")
    new_post(host, 1, "reply", comment_to="some-post")
    a.apply_membership([MembershipChange("g3", "dormant", 0, "initial")])
    assert a.ingest_inbox(2, [crosspost(0, U[2])]).materialized == 1  # a federated post is never sent back
    assert [e.payload["text_excerpt"] for e in a.export_outbox(5)] == ["new root"]


def test_ingest_materialises_once_with_topics_and_a_reference(host):
    a = adapter_for(host)
    inbox = [crosspost(0, U[1], "from the forum", topics=["music", "chess"]), crosspost(1, U[2], "second")]
    r1 = a.ingest_inbox(5, inbox)
    assert (r1.materialized, r1.duplicates, r1.skipped_total) == (2, 0, 0)
    r2 = a.ingest_inbox(5, inbox)  # INV-05
    assert (r2.materialized, r2.duplicates) == (0, 2)
    with Session(host.engine) as s:
        posts = {p.tweet: p for p in s.scalars(select(Post)).all()}
        assert posts["from the forum"].user_id == U[1] and posts["from the forum"].comment_to == "-1"
        assert posts["from the forum"].thread_id == posts["from the forum"].id and posts["from the forum"].round == ROUND
        assert [t.topic_id for t in s.scalars(select(PostTopic).where(PostTopic.post_id == posts["from the forum"].id)).all()] == ["i-music"]
        refs = {r.fed_msg_id: r.source_ref for r in s.scalars(select(FederationRef)).all()}
        assert refs == {inbox[0].fed_msg_id: "ysocial://1/forum/post/0", inbox[1].fed_msg_id: "ysocial://1/forum/post/1"}
    assert len(host.recent_posts_cache) == 2


def test_ingest_skips_unknown_and_dormant_accounts_and_unsupported_messages(host):
    a = adapter_for(host)
    a.apply_membership([MembershipChange("g2", "dormant", 0, "initial")])
    content = Envelope.create(1, "forum", "hpc", 4, 9, "content.v1",
                              {"global_agent_id": "g1", "source_ref": "ysocial://1/forum/post/9", "kind": "post",
                               "text_excerpt": "x", "image_ref": None, "topics": [], "lang": "en"})
    r = a.ingest_inbox(5, [crosspost(0, U[2]), crosspost(1, "nobody"), content, crosspost(2, U[3])])
    assert r.materialized == 1 and r.skipped == {"skipped_ineligible": 2, "skipped_unsupported": 1}


def test_membership_is_stored_and_updated(host):
    a = adapter_for(host)
    a.apply_membership([MembershipChange("g1", "dormant", 0, "initial"), MembershipChange("g2", "active", 0, "initial")])
    a.apply_membership([MembershipChange("g1", "active", 24, "join")])
    with Session(host.engine) as s:
        rows = {r.user_id: (r.state, r.since_tick, r.reason) for r in s.scalars(select(FederationMembership)).all()}
    assert rows == {U[1]: ("active", 24, "join"), U[2]: ("active", 0, "initial")}
    a.apply_membership([MembershipChange("g2", "left", 48, "churn")])
    assert a.inactive_agent_ids() == {U[2]}
    assert adapter_for(host).inactive_agent_ids() == {U[2]}  # a new adapter (server restart) reads the table


def test_dormant_accounts_are_invisible_in_the_server_answers(host):
    a = adapter_for(host)
    p1, p2 = new_post(host, 1, "visible"), new_post(host, 2, "hidden")
    a.apply_membership([MembershipChange("g2", "dormant", 0, "initial")])
    assert a.filter_posts([p2, p1]) == [p1] and a.filter_users([U[1], U[2], U[3]]) == [U[1], U[3]]

    seen = {}

    def recommend(**kw):
        seen["limit"] = kw["limit"]
        return [p2, p1]

    srv = SimpleNamespace(
        _federation_adapter=a, default_recommendation_limit=5, day=1, slot=1, _save_recommendation=lambda *x: None,
        content_recommender=SimpleNamespace(get_recommended_posts=recommend),
        post_service=SimpleNamespace(search_posts_by_topic=lambda t, ag, lim: [p2, p1]),
        db=SimpleNamespace(use_redis=False), _get_follow_suggestions_sql=lambda *x: [U[2], U[3]])
    assert _unwrap("get_recommended_posts")(srv, U[3], limit=2) == [p1] and seen["limit"] == 4  # asked for more, then cut
    assert _unwrap("search_posts_by_topic")(srv, "t", U[3]) == [p1]
    assert _unwrap("get_follow_suggestions")(srv, U[3]) == [U[3]]
    assert _unwrap("get_federation_inactive_agents")(srv) == [U[2]]
    srv._federation_adapter = None  # standalone: untouched
    assert _unwrap("get_recommended_posts")(srv, U[3], limit=2) == [p2, p1] and _unwrap("get_federation_inactive_agents")(srv) == []


def test_conformance_suite(host):
    from ysocial_federation.testing.conformance import ConformanceCase, run_all

    def factory():
        return adapter_for(host)

    def sample_inbox(a, tick):
        return [Envelope.create(1, "forum", "hpc", tick - 1, seq, "crosspost.v1",
                                {"global_agent_id": "g1", "source_ref": f"ysocial://1/forum/post/{tick}-{seq}", "kind": "post",
                                 "text_excerpt": "x", "image_ref": None, "topics": [], "lang": "en", "target_account_id": U[1]})
                for seq in range(3)]

    case = ConformanceCase(factory, (1, 1), lambda r: (r[0], r[1] + 1) if r[1] < 24 else (r[0] + 1, 1), "hpc", 1,
                           agent_ids=["g1", "g2"], sample_inbox=sample_inbox)
    assert "ingest_is_idempotent" in run_all(case)


def test_affective_report_equals_what_the_runtime_computes(host):
    import logging

    from YSimulator.YServer.classes.models import Reaction, Recommendation, StressReward

    a = adapter_for(host)
    a.apply_membership([MembershipChange("g1", "active", 0, "initial"), MembershipChange("g2", "active", 0, "initial"),
                        MembershipChange("g3", "dormant", 0, "initial")])
    new_post(host, 1, "one")
    with Session(host.engine) as s:
        s.add(Round(id="r1-2", day=1, hour=2))
        s.add(Round(id="r2-1", day=2, hour=1))
        rows = [("stress", 0.4, "aggregate", ROUND), ("stress", 0.3, "variation", "r1-2"), ("stress", -0.1, "variation", "r1-2"),
                ("reward", 0.9, "variation", "r1-2"), ("reward", 0.5, "variation", "r1-2"), ("stress", 0.7, "variation", "r2-1")]
        for i, (var, val, typ, tid) in enumerate(rows):
            s.add(StressReward(id=f"s{i}", uid=U[1], variable=var, value=val, type=typ, tid=tid))
        s.add(Reaction(id="x1", post_id="p", user_id=U[1], type="like", round=ROUND))
        s.add(Recommendation(id="c1", user_id=U[1], post_ids="a,b,c", round=ROUND))
        s.commit()
        before = s.query(StressReward).count()
    samples = {x.global_agent_id: x for x in a.affective_report(1)}
    with Session(host.engine) as s:
        assert s.query(StressReward).count() == before  # read only
    assert set(samples) == {"g1", "g2"}
    server = SimpleNamespace(db=SimpleNamespace(engine=host.engine), simulation_config={"stress_reward": {"enabled": True}},
                             logger=logging.getLogger("t"))
    native = _unwrap("get_stress_reward")(server, U[1], "r1-2")  # the runtime's own computation at the last round of the day
    assert (samples["g1"].stress, samples["g1"].reward) == (pytest.approx(native["stress"]), pytest.approx(native["reward"]))
    assert (samples["g1"].stress, samples["g1"].reward) == (pytest.approx(0.6), 1.0)
    assert samples["g1"].actions == 2 and samples["g1"].exposures == 3
    assert (samples["g2"].stress, samples["g2"].reward, samples["g2"].actions) == (0.0, 0.0, 0)
    assert a.affective_report(9) == []
