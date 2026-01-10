#!/usr/bin/env python3
"""
Manual verification script for agent_downcast feature.

This script demonstrates the behavior of the agent_downcast feature
by showing how different agent types are handled.
"""

import json
from pathlib import Path


def verify_configs():
    """Verify all simulation_config.json files have agent_downcast field."""
    print("=" * 70)
    print("VERIFYING SIMULATION CONFIGURATIONS")
    print("=" * 70)

    base_path = Path(__file__).parent.parent / "example"
    config_files = list(base_path.glob("*/simulation_config.json"))

    all_valid = True
    for config_file in sorted(config_files):
        with open(config_file, "r") as f:
            config = json.load(f)

        archetypes_config = config.get("simulation", {}).get("agent_archetypes", {})
        has_downcast = "agent_downcast" in archetypes_config
        downcast_value = archetypes_config.get("agent_downcast", None)

        status = "✓" if has_downcast else "✗"
        print(f"{status} {config_file.parent.name:30s} - agent_downcast: {downcast_value}")

        if not has_downcast:
            all_valid = False

    print()
    if all_valid:
        print("✓ All configuration files have agent_downcast field")
    else:
        print("✗ Some configuration files are missing agent_downcast field")

    return all_valid


def demonstrate_behavior():
    """Demonstrate the agent_downcast behavior."""
    print()
    print("=" * 70)
    print("DEMONSTRATING AGENT_DOWNCAST BEHAVIOR")
    print("=" * 70)

    # Simulate the logic
    def get_agent_type(llm, archetype, agent_downcast):
        """Simulate the agent type determination logic."""
        agent_type = "llm" if llm else "rule_based"

        if agent_downcast and archetype:
            archetype_lower = archetype.lower()
            if archetype_lower in ["validator", "explorer"]:
                agent_type = "rule_based"

        return agent_type

    print()
    print("Scenario 1: agent_downcast = False")
    print("-" * 70)
    scenarios = [
        ("Validator", True),
        ("Explorer", True),
        ("Broadcaster", True),
    ]
    for archetype, llm in scenarios:
        result = get_agent_type(llm, archetype, False)
        print(f"  {archetype:15s} with llm={str(llm):5s} → {result:12s}")

    print()
    print("Scenario 2: agent_downcast = True")
    print("-" * 70)
    for archetype, llm in scenarios:
        result = get_agent_type(llm, archetype, True)
        print(f"  {archetype:15s} with llm={str(llm):5s} → {result:12s}")

    print()
    print("Key Points:")
    print("  • When agent_downcast=True:")
    print("    - Validator agents with llm=True are treated as rule_based")
    print("    - Explorer agents with llm=True are treated as rule_based")
    print("    - Broadcaster agents maintain their original type (llm)")
    print("  • When agent_downcast=False:")
    print("    - All agents maintain their original type")
    print()


def main():
    """Main verification function."""
    configs_valid = verify_configs()
    demonstrate_behavior()

    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    if configs_valid:
        print("✓ All configuration files are valid")
        print("✓ agent_downcast feature is properly configured")
        print()
        print("The feature is ready to use. When agent_downcast is enabled:")
        print("  • Validator and Explorer agents will use rule-based behavior")
        print("  • Broadcaster agents will use their configured behavior (LLM or rule-based)")
    else:
        print("✗ Some configuration files need to be updated")
    print("=" * 70)


if __name__ == "__main__":
    main()
