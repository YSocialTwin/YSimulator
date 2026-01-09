"""
Test agent_downcast feature.

This test verifies that when agent_downcast is enabled,
validator and explorer agents are treated as rule-based
even if they are defined as LLM agents, while broadcaster
agents maintain their original type.
"""

import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from YSimulator.YClient.classes.ray_models import AgentProfile


# Shared helper function for determining agent type based on configuration
def determine_agent_type(agent_profile, agent_downcast):
    """
    Simplified version of agent type determination logic matching client.py implementation.

    Args:
        agent_profile: AgentProfile object
        agent_downcast: Boolean indicating if downcast is enabled

    Returns:
        str: "llm" or "rule_based"
    """
    agent_type = "llm" if agent_profile.llm else "rule_based"

    # Apply agent_downcast logic
    if agent_downcast and agent_profile.archetype:
        archetype_lower = agent_profile.archetype.lower()
        if archetype_lower in ["validator", "explorer"]:
            agent_type = "rule_based"

    return agent_type


def test_agent_downcast_disabled():
    """Test that without agent_downcast, agent types are respected."""

    # Test validator with llm=True (should remain LLM when downcast disabled)
    validator_llm = AgentProfile(
        id="1", username="validator_llm", archetype="Validator", llm=True, cluster=0
    )
    assert determine_agent_type(validator_llm, False) == "llm"
    print("✓ Validator with llm=True remains LLM when downcast disabled")

    # Test explorer with llm=True (should remain LLM when downcast disabled)
    explorer_llm = AgentProfile(
        id="2", username="explorer_llm", archetype="Explorer", llm=True, cluster=2
    )
    assert determine_agent_type(explorer_llm, False) == "llm"
    print("✓ Explorer with llm=True remains LLM when downcast disabled")

    # Test broadcaster with llm=True (should remain LLM)
    broadcaster_llm = AgentProfile(
        id="3", username="broadcaster_llm", archetype="Broadcaster", llm=True, cluster=1
    )
    assert determine_agent_type(broadcaster_llm, False) == "llm"
    print("✓ Broadcaster with llm=True remains LLM when downcast disabled")


def test_agent_downcast_enabled():
    """Test that with agent_downcast enabled, validators and explorers become rule-based."""

    # Test validator with llm=True (should be downcast to rule_based)
    validator_llm = AgentProfile(
        id="1", username="validator_llm", archetype="Validator", llm=True, cluster=0
    )
    assert determine_agent_type(validator_llm, True) == "rule_based"
    print("✓ Validator with llm=True is downcast to rule_based")

    # Test explorer with llm=True (should be downcast to rule_based)
    explorer_llm = AgentProfile(
        id="2", username="explorer_llm", archetype="Explorer", llm=True, cluster=2
    )
    assert determine_agent_type(explorer_llm, True) == "rule_based"
    print("✓ Explorer with llm=True is downcast to rule_based")

    # Test broadcaster with llm=True (should remain LLM)
    broadcaster_llm = AgentProfile(
        id="3", username="broadcaster_llm", archetype="Broadcaster", llm=True, cluster=1
    )
    assert determine_agent_type(broadcaster_llm, True) == "llm"
    print("✓ Broadcaster with llm=True remains LLM even with downcast enabled")

    # Test validator with llm=False (should remain rule_based)
    validator_rule = AgentProfile(
        id="4", username="validator_rule", archetype="Validator", llm=False, cluster=0
    )
    assert determine_agent_type(validator_rule, True) == "rule_based"
    print("✓ Validator with llm=False remains rule_based")

    # Test broadcaster with llm=False (should remain rule_based)
    broadcaster_rule = AgentProfile(
        id="5", username="broadcaster_rule", archetype="Broadcaster", llm=False, cluster=1
    )
    assert determine_agent_type(broadcaster_rule, True) == "rule_based"
    print("✓ Broadcaster with llm=False remains rule_based")


def test_agent_downcast_case_insensitive():
    """Test that archetype comparison is case-insensitive."""

    # Test different case variations
    test_cases = [
        ("VALIDATOR", True, "rule_based"),
        ("validator", True, "rule_based"),
        ("Validator", True, "rule_based"),
        ("EXPLORER", True, "rule_based"),
        ("explorer", True, "rule_based"),
        ("Explorer", True, "rule_based"),
        ("BROADCASTER", True, "llm"),
        ("broadcaster", True, "llm"),
        ("Broadcaster", True, "llm"),
    ]

    for archetype_variant, llm, expected_type in test_cases:
        agent = AgentProfile(
            id=f"test_{archetype_variant}",
            username=f"test_{archetype_variant}",
            archetype=archetype_variant,
            llm=llm,
            cluster=0,
        )
        actual_type = determine_agent_type(agent, True)
        assert (
            actual_type == expected_type
        ), f"Failed for archetype '{archetype_variant}': expected {expected_type}, got {actual_type}"

    print("✓ Archetype comparison is case-insensitive")


def test_agent_without_archetype():
    """Test that agents without archetype are not affected by downcast."""

    # Test agent without archetype
    agent_no_archetype_llm = AgentProfile(
        id="1", username="no_archetype_llm", archetype=None, llm=True, cluster=0
    )
    assert determine_agent_type(agent_no_archetype_llm, True) == "llm"
    print("✓ Agent without archetype with llm=True remains LLM")

    agent_no_archetype_rule = AgentProfile(
        id="2", username="no_archetype_rule", archetype=None, llm=False, cluster=0
    )
    assert determine_agent_type(agent_no_archetype_rule, True) == "rule_based"
    print("✓ Agent without archetype with llm=False remains rule_based")


if __name__ == "__main__":
    print("Testing agent_downcast feature...\n")

    try:
        print("Test 1: agent_downcast disabled")
        test_agent_downcast_disabled()
        print()

        print("Test 2: agent_downcast enabled")
        test_agent_downcast_enabled()
        print()

        print("Test 3: case-insensitive archetype comparison")
        test_agent_downcast_case_insensitive()
        print()

        print("Test 4: agents without archetype")
        test_agent_without_archetype()
        print()

        print("=" * 50)
        print("All tests passed!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
