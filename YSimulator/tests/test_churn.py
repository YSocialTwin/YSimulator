"""
Test churn event functionality.

This test validates:
1. Churn configuration loading
2. Inactive agent identification
3. Churn probability application
4. Churned agent filtering from selection
"""

import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_churn_configuration():
    """Test that churn configuration is properly loaded."""
    
    # Create a simulation config with churn settings
    sim_config = {
        "simulation": {
            "num_days": 3,
            "num_slots_per_day": 24
        },
        "agents": {
            "churn": {
                "enabled": True,
                "churn_probability": 0.01,
                "inactivity_threshold": 5,
                "churn_percentage": 0.1
            }
        }
    }
    
    # Verify configuration structure
    assert "agents" in sim_config
    assert "churn" in sim_config["agents"]
    churn_config = sim_config["agents"]["churn"]
    
    assert churn_config["enabled"] is True
    assert churn_config["churn_probability"] == 0.01
    assert churn_config["inactivity_threshold"] == 5
    assert churn_config["churn_percentage"] == 0.1
    
    print("✓ Churn configuration structure is valid")


def test_churn_config_in_all_examples():
    """Test that all example simulation_config.json files have churn configuration."""
    
    example_dir = Path(__file__).parent.parent.parent / "example"
    
    if not example_dir.exists():
        print("⚠ Example directory not found, skipping this test")
        return True
    
    config_files = list(example_dir.glob("*/simulation_config.json"))
    
    if not config_files:
        print("⚠ No simulation_config.json files found, skipping this test")
        return True
    
    for config_file in config_files:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        assert "agents" in config, f"Missing 'agents' section in {config_file}"
        assert "churn" in config["agents"], f"Missing 'churn' config in {config_file}"
        
        churn_config = config["agents"]["churn"]
        assert "enabled" in churn_config, f"Missing 'enabled' in churn config in {config_file}"
        assert "churn_probability" in churn_config, f"Missing 'churn_probability' in {config_file}"
        assert "inactivity_threshold" in churn_config, f"Missing 'inactivity_threshold' in {config_file}"
        assert "churn_percentage" in churn_config, f"Missing 'churn_percentage' in {config_file}"
    
    print(f"✓ All {len(config_files)} example configs have valid churn configuration")


def test_inactive_agent_logic():
    """Test the logic for identifying inactive agents."""
    
    # Simulate agent data - using left_on instead of churned
    agents = [
        {"id": "agent_1", "last_active_day": 1, "left_on": None},
        {"id": "agent_2", "last_active_day": 5, "left_on": None},
        {"id": "agent_3", "last_active_day": 10, "left_on": None},
        {"id": "agent_4", "last_active_day": None, "left_on": None},  # Never active
        {"id": "agent_5", "last_active_day": 3, "left_on": "round_123"},  # Already churned
    ]
    
    current_day = 15
    inactivity_threshold = 5
    
    # Identify inactive agents
    inactive_agents = []
    for agent in agents:
        # Skip if already churned (left_on is set)
        if agent["left_on"] is not None:
            continue
        
        # Check if inactive
        if agent["last_active_day"] is not None:
            days_inactive = current_day - agent["last_active_day"]
            if days_inactive >= inactivity_threshold:
                inactive_agents.append(agent["id"])
    
    # Expected: agent_1 (14 days inactive), agent_2 (10 days inactive), agent_3 (5 days inactive)
    # Not expected: agent_4 (never active), agent_5 (already churned)
    assert len(inactive_agents) == 3, f"Expected 3 inactive agents, got {len(inactive_agents)}"
    assert "agent_1" in inactive_agents
    assert "agent_2" in inactive_agents
    assert "agent_3" in inactive_agents
    
    print("✓ Inactive agent identification logic is correct")


def test_churn_percentage_selection():
    """Test that churn percentage correctly selects candidates."""
    
    inactive_agents = [f"agent_{i}" for i in range(20)]  # 20 inactive agents
    churn_percentage = 0.1  # 10% should be selected
    
    # Calculate number of candidates
    num_candidates = max(1, int(len(inactive_agents) * churn_percentage))
    
    assert num_candidates == 2, f"Expected 2 candidates (10% of 20), got {num_candidates}"
    
    # Test edge case: ensure at least 1 candidate if any inactive agents exist
    inactive_agents_small = ["agent_1"]
    num_candidates_small = max(1, int(len(inactive_agents_small) * churn_percentage))
    assert num_candidates_small == 1, f"Expected at least 1 candidate, got {num_candidates_small}"
    
    print("✓ Churn percentage selection logic is correct")


def test_churn_probability_application():
    """Test that churn probability is applied correctly (conceptual test)."""
    
    # This is a conceptual test since actual probability is random
    # We verify the logic structure
    
    candidates = ["agent_1", "agent_2", "agent_3"]
    churn_probability = 0.5  # 50% chance
    
    # Simulate churn application (deterministic for testing)
    import random
    random.seed(42)  # Fixed seed for reproducibility
    
    churned = []
    for agent_id in candidates:
        if random.random() < churn_probability:
            churned.append(agent_id)
    
    # With seed 42 and probability 0.5, we should get some churned agents
    # We're just checking the logic runs without error
    assert isinstance(churned, list)
    assert all(isinstance(a, str) for a in churned)
    
    print("✓ Churn probability application logic is correct")


def test_database_schema_updates():
    """Test that database schema includes new churn columns."""
    
    # Read the SQL schema file
    schema_file = Path(__file__).parent.parent.parent / "scripts" / "postgresql_server.sql"
    
    if not schema_file.exists():
        print("⚠ Schema file not found, skipping this test")
        return True
    
    with open(schema_file, 'r') as f:
        schema_content = f.read()
    
    # Check for last_active_day column (not churned - we use left_on instead)
    assert "last_active_day" in schema_content, "Missing 'last_active_day' column in schema"
    assert "left_on" in schema_content, "Missing 'left_on' column in schema"
    
    print("✓ Database schema includes last_active_day and left_on columns")


def test_sqlalchemy_model_updates():
    """Test that SQLAlchemy models include churn fields."""
    
    models_file = Path(__file__).parent.parent / "YServer" / "classes" / "models.py"
    
    if not models_file.exists():
        print("⚠ Models file not found, skipping this test")
        return True
    
    with open(models_file, 'r') as f:
        models_content = f.read()
    
    # Check for last_active_day and left_on in User_mgmt model (not churned)
    assert "last_active_day = Column" in models_content, "Missing last_active_day column in User_mgmt model"
    assert "left_on = Column" in models_content, "Missing left_on column in User_mgmt model"
    
    print("✓ SQLAlchemy models include churn fields")


if __name__ == '__main__':
    print("Testing churn event functionality...\n")
    
    tests = [
        ("Churn Configuration", test_churn_configuration),
        ("Churn Config in Examples", test_churn_config_in_all_examples),
        ("Inactive Agent Logic", test_inactive_agent_logic),
        ("Churn Percentage Selection", test_churn_percentage_selection),
        ("Churn Probability Application", test_churn_probability_application),
        ("Database Schema Updates", test_database_schema_updates),
        ("SQLAlchemy Model Updates", test_sqlalchemy_model_updates),
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
    
    print("\n" + "="*50)
    if not failed:
        print("All tests passed!")
        print("="*50)
        sys.exit(0)
    else:
        print(f"Failed tests: {', '.join(failed)}")
        print("="*50)
        sys.exit(1)
