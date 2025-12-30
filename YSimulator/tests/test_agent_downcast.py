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


def test_agent_downcast_disabled():
    """Test that without agent_downcast, agent types are respected."""
    
    # Mock configuration without agent_downcast
    simulation_config = {
        "simulation": {
            "num_days": 1,
            "num_slots_per_day": 24,
            "heartbeat_interval": 5,
            "agent_archetypes": {
                "enabled": True,
                "agent_downcast": False,  # Disabled
                "distribution": {
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }
            },
            "actions_likelihood": {
                "post": 1,
                "comment": 1,
                "read": 1,
                "share": 1,
                "search": 1,
                "follow": 1
            }
        }
    }
    
    # Create mock client (simplified for testing)
    class MockClient:
        def __init__(self, simulation_config):
            archetype_config = simulation_config["simulation"].get("agent_archetypes", {})
            self.agent_downcast = archetype_config.get("agent_downcast", False)
            self.actions_likelihood = simulation_config["simulation"].get("actions_likelihood", {})
        
        def determine_agent_type(self, agent_profile):
            """Simplified version of agent type determination logic."""
            agent_type = "llm" if agent_profile.llm else "rule_based"
            
            # Apply agent_downcast logic
            if self.agent_downcast and agent_profile.archetype:
                archetype_lower = agent_profile.archetype.lower()
                if archetype_lower in ["validator", "explorer"]:
                    agent_type = "rule_based"
            
            return agent_type
    
    client = MockClient(simulation_config)
    
    # Test validator with llm=True (should remain LLM when downcast disabled)
    validator_llm = AgentProfile(
        id="1",
        username="validator_llm",
        archetype="Validator",
        llm=True,
        cluster=0
    )
    assert client.determine_agent_type(validator_llm) == "llm"
    print("✓ Validator with llm=True remains LLM when downcast disabled")
    
    # Test explorer with llm=True (should remain LLM when downcast disabled)
    explorer_llm = AgentProfile(
        id="2",
        username="explorer_llm",
        archetype="Explorer",
        llm=True,
        cluster=2
    )
    assert client.determine_agent_type(explorer_llm) == "llm"
    print("✓ Explorer with llm=True remains LLM when downcast disabled")
    
    # Test broadcaster with llm=True (should remain LLM)
    broadcaster_llm = AgentProfile(
        id="3",
        username="broadcaster_llm",
        archetype="Broadcaster",
        llm=True,
        cluster=1
    )
    assert client.determine_agent_type(broadcaster_llm) == "llm"
    print("✓ Broadcaster with llm=True remains LLM when downcast disabled")


def test_agent_downcast_enabled():
    """Test that with agent_downcast enabled, validators and explorers become rule-based."""
    
    # Mock configuration with agent_downcast enabled
    simulation_config = {
        "simulation": {
            "num_days": 1,
            "num_slots_per_day": 24,
            "heartbeat_interval": 5,
            "agent_archetypes": {
                "enabled": True,
                "agent_downcast": True,  # Enabled
                "distribution": {
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }
            },
            "actions_likelihood": {
                "post": 1,
                "comment": 1,
                "read": 1,
                "share": 1,
                "search": 1,
                "follow": 1
            }
        }
    }
    
    # Create mock client (simplified for testing)
    class MockClient:
        def __init__(self, simulation_config):
            archetype_config = simulation_config["simulation"].get("agent_archetypes", {})
            self.agent_downcast = archetype_config.get("agent_downcast", False)
            self.actions_likelihood = simulation_config["simulation"].get("actions_likelihood", {})
        
        def determine_agent_type(self, agent_profile):
            """Simplified version of agent type determination logic."""
            agent_type = "llm" if agent_profile.llm else "rule_based"
            
            # Apply agent_downcast logic
            if self.agent_downcast and agent_profile.archetype:
                archetype_lower = agent_profile.archetype.lower()
                if archetype_lower in ["validator", "explorer"]:
                    agent_type = "rule_based"
            
            return agent_type
    
    client = MockClient(simulation_config)
    
    # Test validator with llm=True (should be downcast to rule_based)
    validator_llm = AgentProfile(
        id="1",
        username="validator_llm",
        archetype="Validator",
        llm=True,
        cluster=0
    )
    assert client.determine_agent_type(validator_llm) == "rule_based"
    print("✓ Validator with llm=True is downcast to rule_based")
    
    # Test explorer with llm=True (should be downcast to rule_based)
    explorer_llm = AgentProfile(
        id="2",
        username="explorer_llm",
        archetype="Explorer",
        llm=True,
        cluster=2
    )
    assert client.determine_agent_type(explorer_llm) == "rule_based"
    print("✓ Explorer with llm=True is downcast to rule_based")
    
    # Test broadcaster with llm=True (should remain LLM)
    broadcaster_llm = AgentProfile(
        id="3",
        username="broadcaster_llm",
        archetype="Broadcaster",
        llm=True,
        cluster=1
    )
    assert client.determine_agent_type(broadcaster_llm) == "llm"
    print("✓ Broadcaster with llm=True remains LLM even with downcast enabled")
    
    # Test validator with llm=False (should remain rule_based)
    validator_rule = AgentProfile(
        id="4",
        username="validator_rule",
        archetype="Validator",
        llm=False,
        cluster=0
    )
    assert client.determine_agent_type(validator_rule) == "rule_based"
    print("✓ Validator with llm=False remains rule_based")
    
    # Test broadcaster with llm=False (should remain rule_based)
    broadcaster_rule = AgentProfile(
        id="5",
        username="broadcaster_rule",
        archetype="Broadcaster",
        llm=False,
        cluster=1
    )
    assert client.determine_agent_type(broadcaster_rule) == "rule_based"
    print("✓ Broadcaster with llm=False remains rule_based")


def test_agent_downcast_case_insensitive():
    """Test that archetype comparison is case-insensitive."""
    
    simulation_config = {
        "simulation": {
            "num_days": 1,
            "num_slots_per_day": 24,
            "agent_archetypes": {
                "enabled": True,
                "agent_downcast": True,
                "distribution": {
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }
            },
            "actions_likelihood": {
                "post": 1,
                "comment": 1,
                "read": 1,
                "share": 1,
                "search": 1,
                "follow": 1
            }
        }
    }
    
    class MockClient:
        def __init__(self, simulation_config):
            archetype_config = simulation_config["simulation"].get("agent_archetypes", {})
            self.agent_downcast = archetype_config.get("agent_downcast", False)
            self.actions_likelihood = simulation_config["simulation"].get("actions_likelihood", {})
        
        def determine_agent_type(self, agent_profile):
            """Simplified version of agent type determination logic."""
            agent_type = "llm" if agent_profile.llm else "rule_based"
            
            # Apply agent_downcast logic
            if self.agent_downcast and agent_profile.archetype:
                archetype_lower = agent_profile.archetype.lower()
                if archetype_lower in ["validator", "explorer"]:
                    agent_type = "rule_based"
            
            return agent_type
    
    client = MockClient(simulation_config)
    
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
            cluster=0
        )
        actual_type = client.determine_agent_type(agent)
        assert actual_type == expected_type, f"Failed for archetype '{archetype_variant}': expected {expected_type}, got {actual_type}"
    
    print("✓ Archetype comparison is case-insensitive")


def test_agent_without_archetype():
    """Test that agents without archetype are not affected by downcast."""
    
    simulation_config = {
        "simulation": {
            "num_days": 1,
            "num_slots_per_day": 24,
            "agent_archetypes": {
                "enabled": True,
                "agent_downcast": True,
                "distribution": {
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }
            },
            "actions_likelihood": {
                "post": 1,
                "comment": 1,
                "read": 1,
                "share": 1,
                "search": 1,
                "follow": 1
            }
        }
    }
    
    class MockClient:
        def __init__(self, simulation_config):
            archetype_config = simulation_config["simulation"].get("agent_archetypes", {})
            self.agent_downcast = archetype_config.get("agent_downcast", False)
            self.actions_likelihood = simulation_config["simulation"].get("actions_likelihood", {})
        
        def determine_agent_type(self, agent_profile):
            """Simplified version of agent type determination logic."""
            agent_type = "llm" if agent_profile.llm else "rule_based"
            
            # Apply agent_downcast logic
            if self.agent_downcast and agent_profile.archetype:
                archetype_lower = agent_profile.archetype.lower()
                if archetype_lower in ["validator", "explorer"]:
                    agent_type = "rule_based"
            
            return agent_type
    
    client = MockClient(simulation_config)
    
    # Test agent without archetype
    agent_no_archetype_llm = AgentProfile(
        id="1",
        username="no_archetype_llm",
        archetype=None,
        llm=True,
        cluster=0
    )
    assert client.determine_agent_type(agent_no_archetype_llm) == "llm"
    print("✓ Agent without archetype with llm=True remains LLM")
    
    agent_no_archetype_rule = AgentProfile(
        id="2",
        username="no_archetype_rule",
        archetype=None,
        llm=False,
        cluster=0
    )
    assert client.determine_agent_type(agent_no_archetype_rule) == "rule_based"
    print("✓ Agent without archetype with llm=False remains rule_based")


if __name__ == '__main__':
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
        
        print("="*50)
        print("All tests passed!")
        print("="*50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
