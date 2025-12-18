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
    with open("simulation_config.json", "r") as f:
        sim_config = json.load(f)
    
    with open("agent_population.json", "r") as f:
        agent_config = json.load(f)
    
    with open("llm_prompts.json", "r") as f:
        prompts_config = json.load(f)

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
    print(f"--- Number of Agents: {agent_config['num_agents']} ---")

    # Create LLM service with configuration
    llm_service = LLMService.remote(sim_config["llm"], prompts_config)
    
    # Create client with all configurations
    client = SimulationClient.remote(args.id, llm_service, agent_config, sim_config)

    try:
        ray.get(client.run.remote())
    except KeyboardInterrupt:
        print("Client stopping...")