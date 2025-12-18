import argparse
import ray
import os
import sys
from LLM_interactions.llm_service import LLMService
from YClient.client import SimulationClient

# --- Execution Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default="client_1")
    args = parser.parse_args()

    if not os.path.exists("ray_config.temp"):
        print("❌ Error: 'ray_config.temp' not found. Start run_server.py first.")
        sys.exit(1)

    with open("ray_config.temp", "r") as f:
        server_address = f.read().strip()

    print(f"--- Connecting to Cluster at {server_address} ---")

    # Initialize with namespace matching the server
    ray.init(address=server_address, namespace="social_sim", ignore_reinit_error=True)

    print(f"--- Launching Client {args.id} ---")

    llm_service = LLMService.remote()
    client = SimulationClient.remote(args.id, llm_service, num_agents=50)

    try:
        ray.get(client.run.remote())
    except KeyboardInterrupt:
        print("Client stopping...")