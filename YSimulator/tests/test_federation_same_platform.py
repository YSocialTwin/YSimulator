"""P15: two members of the same platform type next to a forum: the adapter keeps one account per member and tells the platform and the
name of each destination; the client keys the prompt and the text limit by the platform. No coordinator, no real LLM.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from tests.test_federation_bus import U, adapter_for, host, new_post  # noqa: E402,F401

from YSimulator.YClient import federation  # noqa: E402

DEST = {
    "g1": [
        {"member": "forum", "local_account_id": "201", "platform": "forum", "name": "Agora"},
        {
            "member": "microblogging-4",
            "local_account_id": "401",
            "platform": "microblogging",
            "name": "Beta",
        },
        {
            "member": "microblogging-7",
            "local_account_id": "701",
            "platform": "microblogging",
            "name": "Gamma",
        },
    ]
}
INFO = [
    {"member": "forum", "platform": "forum", "name": "Agora"},
    {"member": "microblogging-4", "platform": "microblogging", "name": "Beta"},
    {"member": "microblogging-7", "platform": "microblogging", "name": "Gamma"},
]


def test_the_adapter_posts_to_two_members_of_one_platform_type_and_tells_their_platforms(
    host,
):  # noqa: F811
    a = adapter_for(host, crosspost_mode="agent_action")
    a.set_destinations(DEST)
    a.mark_for_export(
        new_post(host, 1, "original"),
        [{"member": "microblogging-7", "text": "b"}, {"member": "microblogging-4", "text": "a"}],
    )
    out = a.export_outbox(3)
    assert [
        (e.target_member, e.payload["target_account_id"], e.payload["text_excerpt"]) for e in out
    ] == [
        ("microblogging-4", "401", "a"),
        ("microblogging-7", "701", "b"),
    ]  # one account per member
    assert a.destination_members(U[1]) == ["forum", "microblogging-4", "microblogging-7"]
    assert a.destination_info(U[1]) == INFO and a.destination_info(U[3]) == []


def test_a_destination_without_platform_or_name_is_answered_with_the_member_name(
    host,
):  # noqa: F811
    a = adapter_for(host, crosspost_mode="agent_action")
    a.set_destinations(
        {"g1": [{"member": "forum", "local_account_id": "201"}]}
    )  # a coordinator before P15
    assert a.destination_info(U[1]) == [{"member": "forum", "platform": "forum", "name": "forum"}]


def _server(info):
    return SimpleNamespace(
        get_federation_destination_info=SimpleNamespace(remote=lambda agent_id: info),
        get_federation_destinations=SimpleNamespace(
            remote=lambda agent_id: [i["member"] for i in info]
        ),
    )


def _on(monkeypatch):
    import ray

    monkeypatch.setattr(ray, "get", lambda ref: ref)
    federation.install(
        {
            "federation": dict(
                enabled=True,
                seed=3,
                member="microblogging-1",
                name="Alpha",
                crosspost_mode="agent_action",
                crosspost_propensity=1.0,
            )
        }
    )


def test_the_client_keys_the_text_and_the_prompt_by_the_platform_of_the_member(monkeypatch):
    _on(monkeypatch)
    try:
        acts = [SimpleNamespace(action_type="POST", agent_id="a1", content="word " * 90)]
        federation.mark_posts(acts, _server(INFO))
        by = {t["member"]: t["text"] for t in acts[0].crosspost_to}
        assert sorted(by) == ["forum", "microblogging-4", "microblogging-7"]
        assert (
            len(by["microblogging-4"]) <= 280
            and len(by["microblogging-7"]) <= 280
            and len(by["forum"]) > 280
        )
        assert federation.adapt_prompt_key("microblogging-4") == "crosspost_adapt_microblogging"
        assert (
            federation.platform_of("forum") == "forum" and federation.source_platform() == "Alpha"
        )
    finally:
        federation.install({})


def test_a_server_without_the_info_method_still_gives_the_member_names(monkeypatch):
    _on(monkeypatch)
    try:
        server = SimpleNamespace(
            get_federation_destinations=SimpleNamespace(
                remote=lambda agent_id: ["forum", "microblogging"]
            )
        )
        assert federation.destinations(server, "a1") == ["forum", "microblogging"]
        assert federation.adapt_prompt_key("microblogging") == "crosspost_adapt_microblogging"
    finally:
        federation.install({})
