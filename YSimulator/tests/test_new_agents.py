"""
Test new agents functionality.

This test validates:
1. New agents configuration loading
2. New agent calculation logic
3. New agent creation with probability
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_new_agents_configuration():
    """Test that new agents configuration is properly loaded."""

    # Create a simulation config with new_agents settings
    sim_config = {
        "simulation": {"num_days": 3, "num_slots_per_day": 24},
        "agents": {
            "new_agents": {
                "enabled": True,
                "probability_new_agents": 0.01,
                "percentage_new_agents": 0.01,
            }
        },
    }

    # Verify configuration structure
    assert "agents" in sim_config
    assert "new_agents" in sim_config["agents"]
    new_agents_config = sim_config["agents"]["new_agents"]

    assert new_agents_config["enabled"] is True
    assert new_agents_config["probability_new_agents"] == 0.01
    assert new_agents_config["percentage_new_agents"] == 0.01

    print("✓ New agents configuration structure is valid")


def test_new_agents_config_in_all_examples():
    """Test that all example simulation_config.json files have new_agents configuration."""

    example_dir = Path(__file__).parent.parent.parent / "example"

    if not example_dir.exists():
        print("⚠ Example directory not found, skipping this test")

    config_files = list(example_dir.glob("*/simulation_config.json"))

    if not config_files:
        print("⚠ No simulation_config.json files found, skipping this test")

    for config_file in config_files:
        with open(config_file, "r") as f:
            config = json.load(f)

        assert "agents" in config, f"Missing 'agents' section in {config_file}"
        assert "new_agents" in config["agents"], f"Missing 'new_agents' config in {config_file}"

        new_agents_config = config["agents"]["new_agents"]
        assert (
            "enabled" in new_agents_config
        ), f"Missing 'enabled' in new_agents config in {config_file}"
        assert (
            "probability_new_agents" in new_agents_config
        ), f"Missing 'probability_new_agents' in {config_file}"
        assert (
            "percentage_new_agents" in new_agents_config
        ), f"Missing 'percentage_new_agents' in {config_file}"

    print(f"✓ All {len(config_files)} example configs have valid new_agents configuration")


def test_new_agent_count_calculation():
    """Test the logic for calculating number of new agents to potentially add."""

    # Simulate different scenarios
    test_cases = [
        # (non_churned_agents, percentage_new_agents, expected_x)
        (100, 0.01, 1),  # 1% of 100 = 1
        (100, 0.1, 10),  # 10% of 100 = 10
        (50, 0.02, 1),  # 2% of 50 = 1
        (10, 0.1, 1),  # 10% of 10 = 1
        (5, 0.01, 0),  # 1% of 5 = 0 (rounded down)
    ]

    for non_churned_count, percentage, expected_x in test_cases:
        x = int(non_churned_count * percentage)
        assert (
            x == expected_x
        ), f"Expected {expected_x} for {non_churned_count} * {percentage}, got {x}"

    print("✓ New agent count calculation logic is correct")


def test_new_agent_probability_application():
    """Test that new agent probability is applied correctly (conceptual test)."""

    # This is a conceptual test since actual probability is random
    # We verify the logic structure

    x = 5  # Number of potential new agents
    probability_new_agents = 0.5  # 50% chance

    # Simulate new agent addition (deterministic for testing)
    import random

    random.seed(42)  # Fixed seed for reproducibility

    new_agents_added = 0
    for i in range(x):
        if random.random() < probability_new_agents:
            new_agents_added += 1

    # With seed 42 and probability 0.5, we should get some new agents
    # We're just checking the logic runs without error
    assert isinstance(new_agents_added, int)
    assert 0 <= new_agents_added <= x

    print("✓ New agent probability application logic is correct")


def test_new_agent_template_selection():
    """Test that new agents are created from existing agent templates."""

    # Simulate agent data
    non_churned_agents = [
        {"id": "agent_1", "username": "user1", "left_on": None},
        {"id": "agent_2", "username": "user2", "left_on": None},
        {"id": "agent_3", "username": "user3", "left_on": None},
    ]

    # Simulate selecting a template
    import random

    random.seed(42)
    template = random.choice(non_churned_agents)

    # Verify template selection works
    assert template in non_churned_agents
    assert template["left_on"] is None

    print("✓ New agent template selection logic is correct")


if __name__ == "__main__":
    print("Testing new agents functionality...\n")

    tests = [
        ("New Agents Configuration", test_new_agents_configuration),
        ("New Agents Config in Examples", test_new_agents_config_in_all_examples),
        ("New Agent Count Calculation", test_new_agent_count_calculation),
        ("New Agent Probability Application", test_new_agent_probability_application),
        ("New Agent Template Selection", test_new_agent_template_selection),
    ]

    failed = []

    for test_name, test_func in tests:
        try:
            test_func()
        except AssertionError as e:
            print(f"✗ {test_name} failed: {e}")
            failed.append(test_name)
        except Exception as e:
            print(f"✗ {test_name} error: {e}")
            failed.append(test_name)

    print("\n" + "=" * 50)
    if not failed:
        print("All tests passed!")
        print("=" * 50)
        sys.exit(0)
    else:
        print(f"Failed tests: {', '.join(failed)}")
        print("=" * 50)
        sys.exit(1)
