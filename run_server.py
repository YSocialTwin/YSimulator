import ray
import time
import os
from YServer.server import OrchestratorServer

if __name__ == "__main__":
    # Start Cluster
    context = ray.init(include_dashboard=False, namespace="social_sim")

    ray_address = context.address_info["address"]

    # Save address for clients
    with open("ray_config.temp", "w") as f:
        f.write(ray_address)

    print(f"--- 🚀 Server Running on {ray_address} ---")
    print(f"--- 💾 Waiting for clients... ---")

    # Start Actor
    server = OrchestratorServer.options(name="Orchestrator").remote(
        db_name="simulation.db",
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