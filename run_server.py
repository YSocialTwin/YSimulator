import ray
import time
import os
import json
from YServer.server import OrchestratorServer

if __name__ == "__main__":
    # Load server configuration
    with open("server_config.json", "r") as f:
        config = json.load(f)
    
    namespace = config.get("namespace", "social_sim")
    address = config.get("address", "auto")
    port = config.get("port")
    db_name = config.get("database_file", "simulation.db")
    
    # Build ray.init() arguments
    init_kwargs = {
        "include_dashboard": False,
        "namespace": namespace
    }
    
    # Add address if not 'auto'
    if address and address != "auto":
        init_kwargs["address"] = address
    
    # Note: Port configuration is handled by Ray's internal mechanisms
    # Use RAY_ADDRESS environment variable or ray start --port for custom ports
    
    # Start Cluster
    context = ray.init(**init_kwargs)

    ray_address = context.address_info["address"]

    # Save address for clients
    with open("ray_config.temp", "w") as f:
        f.write(ray_address)

    print(f"--- 🚀 Server Running on {ray_address} ---")
    print(f"--- 📝 Namespace: {namespace} ---")
    print(f"--- 💾 Database: {db_name} ---")
    print(f"--- 💾 Waiting for clients... ---")

    # Start Actor
    server = OrchestratorServer.options(name="Orchestrator").remote(
        db_name=db_name,
        min_to_start=1  # Starts as soon as 1 person joins
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        if os.path.exists("ray_config.temp"):
            os.remove("ray_config.temp")
        ray.shutdown()