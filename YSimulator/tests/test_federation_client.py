"""Client side of the federation in YSimulator: off by default, the scheduler skips inactive agents, the cross-post choice."""

import random
from types import SimpleNamespace

from YSimulator.YClient import federation


def test_off_by_default_changes_nothing_and_draws_nothing():
    federation.install({})
    acts = [SimpleNamespace(action_type="POST")]
    state = random.getstate()
    assert federation.mark_posts(acts) is acts and not hasattr(acts[0], "crosspost")
    assert federation.inactive_ids(object()) == set() and not federation.enabled() and random.getstate() == state
    federation.install({"federation": {"enabled": False, "crosspost_propensity": 1.0}})
    federation.mark_posts(acts)
    assert not hasattr(acts[0], "crosspost")


def test_inactive_ids_come_from_the_server_and_the_last_list_is_kept(monkeypatch):
    import ray

    federation.install({"federation": {"enabled": True}})
    calls = {"n": 0}

    def get(ref):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("down")
        return ref

    monkeypatch.setattr(ray, "get", get)
    server = SimpleNamespace(get_federation_inactive_agents=SimpleNamespace(remote=lambda: ["a", "b"]))
    assert federation.inactive_ids(server) == {"a", "b"}
    assert federation.inactive_ids(server) == {"a", "b"}  # the server is unreachable now: the last known list
    federation.install({})


def test_scheduler_skips_inactive_agents(monkeypatch):
    from YSimulator.YClient.simulation.agent_scheduler import AgentScheduler

    federation.install({"federation": {"enabled": True}})
    monkeypatch.setattr(federation, "inactive_ids", lambda server: {"b"})
    agents = [SimpleNamespace(id=i, activity_profile="p", is_page=0, username=i) for i in "abc"]
    sch = AgentScheduler.__new__(AgentScheduler)
    sch.agent_profiles, sch.hourly_activity, sch.activity_profiles = agents, {1: 1.0}, {"p": list(range(24))}
    sch.archetypes_enabled, sch.archetype_distribution, sch.churn_enabled = False, None, False
    sch.server, sch.logger = None, SimpleNamespace(info=lambda *a, **k: None, debug=lambda *a, **k: None, warning=lambda *a, **k: None)
    sch._get_churned_agents = lambda: set()
    sch._promote_agents_with_pending_mentions = lambda active, churned: active
    regular, pages = AgentScheduler.select_active_agents(sch, 1)
    assert sorted(a.id for a in regular) == ["a", "c"] and pages == []
    federation.install({})


def test_crosspost_choice_is_a_seeded_draw_with_its_own_generator():
    def run():
        federation.install({"federation": {"enabled": True, "crosspost_propensity": 0.5, "seed": 3}})
        acts = [SimpleNamespace(action_type="POST") for _ in range(40)] + [SimpleNamespace(action_type="LIKE")]
        state = random.getstate()
        federation.mark_posts(acts)
        assert random.getstate() == state and not hasattr(acts[-1], "crosspost")
        return [hasattr(a, "crosspost") for a in acts[:-1]]

    first = run()
    assert first == run() and 0 < sum(first) < 40
    federation.install({"federation": {"enabled": True, "crosspost_propensity": 0.0}})
    acts = [SimpleNamespace(action_type="POST")]
    federation.mark_posts(acts)
    assert not hasattr(acts[0], "crosspost")
    federation.install({})
