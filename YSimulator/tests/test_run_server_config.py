from run_server import build_server_simulation_config


def test_build_server_simulation_config_preserves_top_level_stress_reward():
    config = {
        "simulation": {"num_slots_per_day": 24},
        "posts": {"visibility_rounds": 36},
        "stress_reward": {
            "enabled": True,
            "backward_rounds": 18,
            "system": {"churn": {"enabled": True}},
        },
    }

    simulation_config = build_server_simulation_config(config)

    assert simulation_config["num_slots_per_day"] == 24
    assert simulation_config["posts"]["visibility_rounds"] == 36
    assert simulation_config["stress_reward"]["enabled"] is True
    assert simulation_config["stress_reward"]["backward_rounds"] == 18
    assert simulation_config["stress_reward"]["system"]["churn"]["enabled"] is True


def test_build_server_simulation_config_supports_legacy_flat_stress_reward_enable():
    config = {
        "simulation": {},
        "stress_reward_enabled": True,
    }

    simulation_config = build_server_simulation_config(config)

    assert simulation_config["stress_reward"]["enabled"] is True
    assert simulation_config["stress_reward"]["backward_rounds"] == 24
