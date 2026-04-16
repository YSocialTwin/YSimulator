from unittest.mock import MagicMock

from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.simulation import secondary_follow_processor as processor_module
from YSimulator.YClient.simulation.secondary_follow_processor import (
    SecondaryFollowProcessor,
)


class _RemoteMethod:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def remote(self, *args):
        self.calls.append(args)
        return self.values.pop(0)


class _ServerStub:
    def __init__(self, values):
        self.check_follow_relationship = _RemoteMethod(values)


def test_process_reciprocal_follows_adds_rule_based_follow(monkeypatch):
    monkeypatch.setattr(processor_module.random, "random", lambda: 0.0)
    monkeypatch.setattr(processor_module.ray, "get", lambda value: value)

    server = _ServerStub([False])
    processor = SecondaryFollowProcessor(
        server=server,
        client_id="client-1",
        logger=MagicMock(),
        llm_manager=MagicMock(),
        probability_of_secondary_follow=0.0,
        probability_of_follow_back=1.0,
    )
    actions = [ActionDTO("actor", 1, "FOLLOW", target_user_id="target")]
    profiles = [
        AgentProfile(id="actor", username="actor", cluster=1, llm=False),
        AgentProfile(id="target", username="target", cluster=2, llm=False),
    ]

    processor.process_reciprocal_follows(actions, profiles)

    assert [(a.agent_id, a.action_type, a.target_user_id) for a in actions] == [
        ("actor", "FOLLOW", "target"),
        ("target", "FOLLOW", "actor"),
    ]
    assert server.check_follow_relationship.calls == [("target", "actor")]


def test_process_reciprocal_follows_uses_llm_decision(monkeypatch):
    monkeypatch.setattr(processor_module.random, "random", lambda: 0.0)

    def _fake_ray_get(value):
        if value == "reverse-exists":
            return False
        if value == ["llm-future"]:
            return ["follow"]
        return value

    monkeypatch.setattr(processor_module.ray, "get", _fake_ray_get)

    llm_manager = MagicMock()
    llm_manager.generate_reciprocal_follow_decision.return_value = "llm-future"
    server = _ServerStub(["reverse-exists"])
    processor = SecondaryFollowProcessor(
        server=server,
        client_id="client-1",
        logger=MagicMock(),
        llm_manager=llm_manager,
        probability_of_secondary_follow=0.0,
        probability_of_follow_back=1.0,
    )
    actions = [ActionDTO("actor", 1, "FOLLOW", target_user_id="target")]
    profiles = [
        AgentProfile(id="actor", username="actor", cluster=1, llm=False, age=42),
        AgentProfile(id="target", username="target", cluster=2, llm=True),
    ]

    processor.process_reciprocal_follows(actions, profiles)

    assert [(a.agent_id, a.action_type, a.target_user_id) for a in actions] == [
        ("actor", "FOLLOW", "target"),
        ("target", "FOLLOW", "actor"),
    ]
    llm_manager.generate_reciprocal_follow_decision.assert_called_once()


def test_secondary_follow_actions_are_also_eligible_for_reciprocal_follow(monkeypatch):
    monkeypatch.setattr(processor_module.random, "random", lambda: 0.0)
    monkeypatch.setattr(processor_module.random, "choice", lambda options: "follow")
    monkeypatch.setattr(processor_module.ray, "get", lambda value: value)

    server = _ServerStub([False, False])
    processor = SecondaryFollowProcessor(
        server=server,
        client_id="client-1",
        logger=MagicMock(),
        llm_manager=MagicMock(),
        probability_of_secondary_follow=1.0,
        probability_of_follow_back=1.0,
    )
    actions = []
    profiles = [
        AgentProfile(id="actor", username="actor", cluster=1, llm=False),
        AgentProfile(id="target", username="target", cluster=2, llm=False),
    ]

    processor.process_secondary_follows(
        secondary_follow_candidates=[],
        rule_based_interactions=[("actor", 1, "target", "post text", False)],
        actions=actions,
    )
    processor.process_reciprocal_follows(actions, profiles)

    assert [(a.agent_id, a.action_type, a.target_user_id) for a in actions] == [
        ("actor", "FOLLOW", "target"),
        ("target", "FOLLOW", "actor"),
    ]
