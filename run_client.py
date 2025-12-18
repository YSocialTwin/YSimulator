import argparse
import ray
import os
import sys
import json
from LLM_interactions.llm_service import LLMService
from YClient.client import SimulationClient

# --- Execution Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default="client_1")
    args = parser.parse_args()

    # Load configuration files
    config_files = {
        "simulation_config.json": "simulation configuration",
        "agent_population.json": "agent population",
        "llm_prompts.json": "LLM prompts"
    }
    
    configs = {}
    for filename, description in config_files.items():
        try:
            with open(filename, "r") as f:
                configs[filename] = json.load(f)
        except FileNotFoundError:
            print(f"❌ Error: '{filename}' not found. Please create the {description} file.")
            print("See CONFIG.md for configuration details.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in '{filename}': {e}")
            sys.exit(1)
    
    sim_config = configs["simulation_config.json"]
    agent_config = configs["agent_population.json"]
    prompts_config = configs["llm_prompts.json"]

    # Get server address from temp file or config
    server_address = sim_config["server"].get("address")
    if not server_address:
        # Fallback to temp file
        if not os.path.exists("ray_config.temp"):
            print("❌ Error: 'ray_config.temp' not found and no server address in config. Start run_server.py first.")
            sys.exit(1)
        with open("ray_config.temp", "r") as f:
            server_address = f.read().strip()

    print(f"--- Connecting to Cluster at {server_address} ---")

    # Initialize with namespace from config
    namespace = sim_config.get("namespace", "social_sim")
    ray.init(address=server_address, namespace=namespace, ignore_reinit_error=True)

    print(f"--- Launching Client {args.id} ---")
    print(f"--- Namespace: {namespace} ---")
    print(f"--- LLM Model: {sim_config['llm']['model']} ---")
    
    # Calculate total number of agents
    num_predefined = len(agent_config.get('agents', []))
    num_generated = agent_config.get('generation_config', {}).get('num_additional_agents', 0)
    total_agents = num_predefined + num_generated
    print(f"--- Number of Agents: {total_agents} ({num_predefined} predefined + {num_generated} generated) ---")

    # Create LLM service with configuration
    llm_service = LLMService.remote(sim_config["llm"], prompts_config)
    
    # Create client with all configurations
    client = SimulationClient.remote(args.id, llm_service, agent_config, sim_config)

    try:
        ray.get(client.run.remote())
    except KeyboardInterrupt:
        print("Client stopping...")