"""INV-17 in YSimulator: accounts are reported by username and the global id comes from the coordinator, never from the local id."""

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from sqlalchemy.orm import Session  # noqa: E402
from tests.test_federation_bus import U, host, new_post  # noqa: E402,F401
from ysocial_federation.schemas import MembershipChange  # noqa: E402

from YSimulator.YServer.classes.models import User_mgmt  # noqa: E402
from YSimulator.YServer.federation.adapter import YSimulatorAdapter  # noqa: E402


def bound_adapter(host, tmp_path, **kw):
    return YSimulatorAdapter("hpc", 1, host=host, bindings_file=str(tmp_path / "bindings.db"), **kw)


def test_accounts_are_offered_by_username_once(host, tmp_path):
    a = bound_adapter(host, tmp_path)
    offered = a.account_bindings()
    assert offered == [{"username": f"u{n}", "local_account_id": U[n]} for n in (1, 2, 3)]
    a.bindings_reported(
        offered,
        [
            {"global_agent_id": "12", "local_account_id": U[1]},
            {"global_agent_id": "30", "local_account_id": U[3]},
        ],
    )
    assert a.account_bindings() == []
    with Session(host.engine) as s:
        s.add(User_mgmt(id="user-4", username="u4", password="x"))
        s.commit()
    offered = a.account_bindings()
    assert offered == [{"username": "u4", "local_account_id": "user-4"}]
    a.bindings_reported(offered, [])
    assert a.account_bindings() == []
    assert {"username": "u4", "local_account_id": "user-4"} in a.account_bindings(retry=True)


def test_the_global_id_is_the_bound_one_and_never_the_local_id(host, tmp_path):
    a = bound_adapter(host, tmp_path)
    a.bindings_reported(a.account_bindings(), [{"global_agent_id": "12", "local_account_id": U[1]}])
    assert a.agent_of(U[1]) == "12" and a.user_of("12") == U[1]
    assert a.agent_of(U[2]) == f"unbound:{U[2]}"
    assert a.user_of("g2") is None and a.user_of(U[2]) is None


def test_membership_reaches_only_bound_accounts(host, tmp_path):
    a = bound_adapter(host, tmp_path)
    a.bindings_reported(a.account_bindings(), [{"global_agent_id": "12", "local_account_id": U[1]}])
    a.apply_membership(
        [
            MembershipChange("12", "dormant", 0, "initial"),
            MembershipChange("77", "dormant", 0, "initial"),
        ]
    )
    assert a.inactive_agent_ids() == {U[1]}  # "77" is nobody's: ignored, not stored as a local id


def test_only_bound_accounts_are_exported(host, tmp_path):
    a = bound_adapter(host, tmp_path, export_policy="all")
    a.bindings_reported(a.account_bindings(), [{"global_agent_id": "12", "local_account_id": U[1]}])
    new_post(host, 1, "from a federation agent")
    new_post(host, 2, "from an account the federation does not know")
    out = a.export_outbox(3)
    assert [e.payload["global_agent_id"] for e in out] == ["12"]


def test_a_restart_keeps_the_bindings(host, tmp_path):
    first = bound_adapter(host, tmp_path)
    first.bindings_reported(
        first.account_bindings(), [{"global_agent_id": "12", "local_account_id": U[2]}]
    )
    second = bound_adapter(host, tmp_path)
    assert second.agent_of(U[2]) == "12" and second.account_bindings() == []


def test_without_a_bindings_file_nothing_changes(host):
    a = YSimulatorAdapter("hpc", 1, host=host)
    assert a.account_bindings() == [] and a.agent_of(U[2]) == U[2] and a.user_of(U[2]) == U[2]


# -- INV-19: accounts created on the coordinator's request ------------------------------------------------------------
@pytest.fixture()
def server(tmp_path):
    """A real OrchestratorServer on an in-memory database (what the adapter runs in) with the bound adapter attached."""
    from YSimulator.YServer.server import OrchestratorServer

    cls = getattr(OrchestratorServer, "__ray_actor_class__", OrchestratorServer)
    srv = cls(
        db_config={"type": "sqlite", "sqlite": {"filename": ":memory:"}},
        config_path=str(tmp_path),
        min_to_start=1,
    )
    srv._federation_adapter = YSimulatorAdapter(
        "hpc", 1, host=srv, bindings_file=str(tmp_path / "bindings.db")
    )
    return srv


def test_provisioned_accounts_are_created_bound_and_able_to_act(server):
    import uuid

    from sqlalchemy import func, select

    from YSimulator.YClient.classes.ray_models import ActionDTO
    from YSimulator.YServer.classes.models import Post

    a = server._federation_adapter
    done = a.provision_accounts(
        [
            {
                "global_agent_id": "40",
                "username": "newcomer",
                "interests": ["jazz", "sport"],
                "age": 41,
                "gender": "female",
            },
            {"global_agent_id": "42", "username": "x" * 51, "interests": []},  # not a username
            {"global_agent_id": "43", "username": "plain", "interests": []},
        ]
    )
    by = {d["global_agent_id"]: d["local_account_id"] for d in done}
    assert set(by) == {"40", "43"} and str(uuid.UUID(by["40"])) == by["40"]  # a UUID id
    assert (
        a.agent_of(by["40"]) == "40" and a.user_of("40") == by["40"] and a.user_of("43") == by["43"]
    )
    with Session(server.engine) as s:
        user = s.get(User_mgmt, by["40"])
        assert (
            user.username,
            user.age,
            user.gender,
            user.leaning,
            user.language,
            user.toxicity,
        ) == ("newcomer", 41, "female", "neutral", "en", "no")
        assert (user.oe, user.co, user.ex, user.ag, user.ne) == (
            "medium",
        ) * 5 and user.joined_on == server.current_round_id
        plain = s.get(User_mgmt, by["43"])
        assert (plain.age, plain.gender, plain.profession, plain.nationality) == (
            30,
            "non-binary",
            "",
            "",
        )  # harmless defaults
    assert server.registered_agents[by["40"]] == "newcomer"
    assert server.interest_manager.get_agent_interests()[by["40"]]["topics"] == ["jazz", "sport"]
    # idempotent: the same name gives the same account, nothing is duplicated
    assert a.provision_accounts(
        [{"global_agent_id": "40", "username": "newcomer", "interests": ["jazz"]}]
    ) == [{"global_agent_id": "40", "local_account_id": by["40"]}]
    with Session(server.engine) as s:
        assert (
            s.scalar(
                select(func.count()).select_from(User_mgmt).where(User_mgmt.username == "newcomer")
            )
            == 1
        )
    # known to the federation: not offered for binding again, active (multiplier not reduced)
    assert all(o["username"] not in ("newcomer", "plain") for o in a.account_bindings(retry=True))
    assert (
        by["40"] not in a.inactive_agent_ids()
        and by["40"] not in server.get_federation_inactive_agents()
    )
    assert server.get_federation_attention().get(by["40"], 1.0) == 1.0
    # it acts through the normal action endpoint, and its post is exported with the global id of its agent
    act = ActionDTO(
        agent_id=by["40"], cluster_id=0, action_type="POST", content="hello from the newcomer"
    )
    act.crosspost = True  # what the client's mark_posts does
    server.submit_actions("c1", [act])
    with Session(server.engine) as s:
        assert s.scalar(select(func.count()).select_from(Post).where(Post.user_id == by["40"])) == 1
    assert [e.payload["global_agent_id"] for e in a.export_outbox(3)] == ["40"]


def test_provisioning_an_existing_name_binds_it_without_creating_it(server):
    from sqlalchemy import func, select

    from YSimulator.YClient.classes.ray_models import AgentProfile

    server.register_agents(
        [AgentProfile(id="11111111-1111-1111-1111-111111111111", username="veteran")]
    )
    done = server._federation_adapter.provision_accounts(
        [{"global_agent_id": "41", "username": "veteran", "interests": []}]
    )
    assert done == [
        {"global_agent_id": "41", "local_account_id": "11111111-1111-1111-1111-111111111111"}
    ]
    assert server._federation_adapter.user_of("41") == "11111111-1111-1111-1111-111111111111"
    with Session(server.engine) as s:
        assert s.scalar(select(func.count()).select_from(User_mgmt)) == 1
    assert (
        server.get_federation_provisioned("c1") == []
    )  # nobody has to adopt an account that was not created for the federation


def test_provisioned_accounts_are_offered_to_one_client_until_adopted_and_again_after_a_restart(
    server,
):
    a = server._federation_adapter
    by = a.provision_accounts(
        [{"global_agent_id": "40", "username": "newcomer", "interests": ["jazz"], "llm": True}]
    )[0]["local_account_id"]
    (profile,) = server.get_federation_provisioned("c1")
    assert (profile.id, profile.username, profile.interests, profile.llm, profile.oe) == (
        by,
        "newcomer",
        (["jazz"], [1]),
        True,
        "medium",
    )
    assert server.get_federation_provisioned("c2") == []  # claimed by the first client that asked
    assert server.get_federation_provisioned("c1", [by]) == []  # the client plays it already
    assert server.federation_adopted("c2", [by]) is True  # not its account: ignored
    assert [p.id for p in server.get_federation_provisioned("c1")] == [by]
    assert server.federation_adopted("c1", [by]) is True
    assert [p.id for p in server.get_federation_provisioned("c1")] == [
        by
    ] and server.get_federation_provisioned(
        "c2"
    ) == []  # a restarted client gets it back


def test_a_restarted_adapter_does_not_provision_again(server, tmp_path):
    a = server._federation_adapter
    by = a.provision_accounts([{"global_agent_id": "40", "username": "newcomer", "interests": []}])[
        0
    ]["local_account_id"]
    b = YSimulatorAdapter("hpc", 1, host=server, bindings_file=str(tmp_path / "bindings.db"))
    assert b.agent_of(by) == "40" and all(
        o["username"] != "newcomer" for o in b.account_bindings(retry=True)
    )
    assert (
        b.provision_accounts([{"global_agent_id": "40", "username": "newcomer", "interests": []}])[
            0
        ]["local_account_id"]
        == by
    )


def test_a_client_adopts_the_accounts_only_when_configured(server, monkeypatch):
    from types import SimpleNamespace

    import ray

    from YSimulator.YClient import federation as client_fed

    by = server._federation_adapter.provision_accounts(
        [{"global_agent_id": "40", "username": "newcomer", "interests": ["jazz"]}]
    )[0]["local_account_id"]
    monkeypatch.setattr(ray, "get", lambda x: x, raising=False)
    remote = SimpleNamespace(
        **{
            n: SimpleNamespace(remote=getattr(server, n))
            for n in ("get_federation_provisioned", "federation_adopted")
        }
    )
    population = []  # the list the scheduler, the executor and the lifecycle manager share
    try:
        client_fed.install({"federation": {"enabled": True}})
        assert (
            client_fed.adopt_provisioned(remote, "c1", population) == 0 and population == []
        )  # no `adopt`: nothing asked
        client_fed.install({})
        assert client_fed.adopt_provisioned(remote, "c1", population) == 0
        client_fed.install({"federation": {"enabled": True, "adopt": True}})
        assert client_fed.adopt_provisioned(remote, "c1", population) == 1
        assert [p.username for p in population] == ["newcomer"] and population[0].id == by
        assert (
            client_fed.adopt_provisioned(remote, "c1", population) == 0 and len(population) == 1
        )  # once
        assert client_fed.adopt_provisioned(remote, "c2", []) == 0  # another client does not get it
        population.clear()  # a restart: the server offers the account again to the client that adopted it
        assert client_fed.adopt_provisioned(remote, "c1", population) == 1
        # an unreachable server never raises
        assert (
            client_fed.adopt_provisioned(
                SimpleNamespace(get_federation_provisioned=None), "c1", population
            )
            == 0
        )
    finally:
        client_fed.install({})


def test_federation_off_provisioning_calls_are_empty(server):
    server._federation_adapter = None
    assert (
        server.get_federation_provisioned("c1") == []
        and server.federation_adopted("c1", ["x"]) is False
    )
