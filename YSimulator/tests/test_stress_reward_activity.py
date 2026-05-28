from unittest.mock import MagicMock

from YSimulator.YClient.classes.ray_models import AgentProfile
from YSimulator.YClient.client import SimulationClient
from YSimulator.YClient.stress_reward.update_system import StressRewardSystem


def test_stress_reward_activity_effect_reduces_actions_and_can_skip():
    system = StressRewardSystem(
        {
            "activity_impact": {
                "enabled": True,
                "stress_weight": 1.2,
                "reward_weight": 0.1,
                "baseline_buffer": 0.05,
                "min_action_multiplier": 0.15,
                "max_skip_probability": 0.65,
            }
        }
    )

    calm = system.compute_activity_effect(current_stress=0.05, current_reward=0.35)
    strained = system.compute_activity_effect(current_stress=0.75, current_reward=0.05)

    assert calm["action_multiplier"] > strained["action_multiplier"]
    assert calm["skip_probability"] < strained["skip_probability"]
    assert strained["skip_probability"] > 0.4
    assert strained["action_multiplier"] < 0.35


def test_prepare_stress_reward_active_agents_suppresses_high_stress_agent(monkeypatch):
    client_cls = SimulationClient.__ray_metadata__.modified_class
    client = client_cls.__new__(client_cls)
    client.stress_reward_enabled = True
    client.stress_reward_system = StressRewardSystem(
        {
            "churn": {"enabled": False},
            "activity_impact": {
                "enabled": True,
                "stress_weight": 1.2,
                "reward_weight": 0.0,
                "baseline_buffer": 0.0,
                "min_action_multiplier": 0.2,
                "max_skip_probability": 0.65,
            },
        }
    )
    client.logger = MagicMock()
    client._stress_reward_clamp01 = SimulationClient._stress_reward_clamp01
    client.evaluate_stress_reward_churn = MagicMock(return_value=False)
    states = {
        "calm": {"stress": 0.05, "reward": 0.4},
        "strained": {"stress": 0.8, "reward": 0.0},
    }
    client.refresh_stress_reward_state = lambda agent_id, current_tid, force=False: states[agent_id]

    calm_agent = AgentProfile(id="calm", username="calm_user", daily_activity_level=3, is_page=0)
    strained_agent = AgentProfile(
        id="strained", username="strained_user", daily_activity_level=3, is_page=0
    )

    draws = iter([0.99, 0.10])
    monkeypatch.setattr("YSimulator.YClient.client.random.random", lambda: next(draws))

    filtered = client_cls.prepare_stress_reward_active_agents(
        client,
        [calm_agent, strained_agent],
        current_tid="round-10",
    )

    assert [agent.id for agent in filtered] == ["calm"]
    assert getattr(calm_agent, "stress_reward_activity_multiplier") > 0.8
    assert getattr(strained_agent, "stress_reward_activity_multiplier") < 0.3
