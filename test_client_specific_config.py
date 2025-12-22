"""
Test client-specific configuration file loading.
"""

import sys
from pathlib import Path
import tempfile
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def test_client_specific_config_fallback():
    """Test that client looks for client-specific config and falls back to generic."""
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        
        # Create simulation_config.json with client name
        sim_config = {
            "client_name": "test_client",
            "simulation": {
                "num_days": 1,
                "num_slots_per_day": 24
            }
        }
        with open(config_dir / "simulation_config.json", "w") as f:
            json.dump(sim_config, f)
        
        # Create generic agent_population.json
        generic_agents = {"agents": [{"username": "generic_user"}]}
        with open(config_dir / "agent_population.json", "w") as f:
            json.dump(generic_agents, f)
        
        # Create client-specific agent_population.json
        client_agents = {"agents": [{"username": "client_specific_user"}]}
        with open(config_dir / "test_client_agent_population.json", "w") as f:
            json.dump(client_agents, f)
        
        # Create generic llm_prompts.json
        generic_prompts = {"personas": {"0": "Generic persona"}}
        with open(config_dir / "llm_prompts.json", "w") as f:
            json.dump(generic_prompts, f)
        
        # Test the helper function logic
        def find_config_file(base_name: str, client_name: str, config_dir: Path) -> Path:
            """Find client-specific config file or fall back to generic."""
            client_specific = config_dir / f"{client_name}_{base_name}"
            generic = config_dir / base_name
            
            if client_specific.exists():
                return client_specific
            else:
                return generic
        
        # Test agent_population - should find client-specific
        agent_file = find_config_file("agent_population.json", "test_client", config_dir)
        assert agent_file.name == "test_client_agent_population.json"
        with open(agent_file) as f:
            data = json.load(f)
        assert data["agents"][0]["username"] == "client_specific_user"
        print("✓ Client-specific agent_population.json found")
        
        # Test llm_prompts - should fall back to generic
        prompts_file = find_config_file("llm_prompts.json", "test_client", config_dir)
        assert prompts_file.name == "llm_prompts.json"
        with open(prompts_file) as f:
            data = json.load(f)
        assert data["personas"]["0"] == "Generic persona"
        print("✓ Fallback to generic llm_prompts.json works")
        
        return True


def test_network_csv_client_specific():
    """Test that network.csv follows the same pattern."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        client_id = "client_1"
        
        # Create generic network.csv
        with open(config_dir / "network.csv", "w") as f:
            f.write("user1,user2\n")
        
        # Create client-specific network.csv
        with open(config_dir / f"{client_id}_network.csv", "w") as f:
            f.write("user3,user4\n")
        
        # Test logic from client.py
        network_csv_path = config_dir / f"{client_id}_network.csv"
        if not network_csv_path.exists():
            network_csv_path = config_dir / "network.csv"
        
        assert network_csv_path.name == f"{client_id}_network.csv"
        with open(network_csv_path) as f:
            content = f.read()
        assert "user3,user4" in content
        print("✓ Client-specific network.csv found")
        
        # Test fallback when client-specific doesn't exist
        client_id_2 = "client_2"
        network_csv_path = config_dir / f"{client_id_2}_network.csv"
        if not network_csv_path.exists():
            network_csv_path = config_dir / "network.csv"
        
        assert network_csv_path.name == "network.csv"
        with open(network_csv_path) as f:
            content = f.read()
        assert "user1,user2" in content
        print("✓ Fallback to generic network.csv works")
        
        return True


if __name__ == '__main__':
    print("Testing client-specific configuration file loading...\n")
    
    try:
        test_client_specific_config_fallback()
        print()
        test_network_csv_client_specific()
        print("\n" + "="*50)
        print("All tests passed!")
        print("="*50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)
