import ray
import time
import sys
from shared import DbWriter, TimeKeeper, AgentBatch

NAMESPACE = "CitySimV1"
TOTAL_AGENTS = 10000
BATCH_SIZE = 1000


def run_simulation_client(days=10):
    # Connect to existing cluster
    ray.init(address="auto", namespace=NAMESPACE)
    print("--- 🎮 Client Connected ---")

    # 1. Find Actors
    try:
        clock = ray.get_actor("Clock")
        db = ray.get_actor("GlobalDB")

        # Find all batches
        batches = []
        for i in range(TOTAL_AGENTS // BATCH_SIZE):
            batches.append(ray.get_actor(f"Batch_{i}"))

        print(f"✅ Connected to World. Found {len(batches)} batches.")
    except Exception as e:
        print(f"❌ Error finding actors: {e}")
        print("Did you run host.py?")
        return

    # 2. Simulation Loop
    current_hour = ray.get(clock.get_time.remote())

    for d in range(days):

        print(f"Starting day {d}")

        # Let's simulate a full day from the current point
        print(f"Starting at Hour: {current_hour}")
        for _ in range(24):
            st = time.time()

            # Advance Global Clock
            hour = ray.get(clock.advance.remote())

            # Trigger All Batches
            print(f"Processing Hour {hour:02d}...", end=" ", flush=True)

            futures = [b.run_hour.remote(hour) for b in batches]
            results = ray.get(futures)

            # Aggregation
            posts = sum(r[0] for r in results)
            likes = sum(r[1] for r in results)

            duration = time.time() - st

            # Log to DB
            db.log.remote(f"Hour {hour} complete. Posts: {posts}, Likes: {likes}", hour)

            print(f"Done ({duration:.2f}s) | 📝 {posts} | ❤️ {likes}")

            # Optional: Read stats
            # stats = ray.get(db.get_stats.remote())
            # print(f"   [Total DB]: Posts {stats[0]}, Likes {stats[1]}")

    print("\n--- Cycle Complete ---")


if __name__ == "__main__":
    run_simulation_client(days=10)