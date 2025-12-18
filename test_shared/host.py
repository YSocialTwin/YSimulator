import ray
from shared import DbWriter, TimeKeeper, LLMService, AgentBatch

# CONFIG
TOTAL_AGENTS = 5000
BATCH_SIZE = 100
NAMESPACE = "CitySimV1"


def setup_world():
    # Connect to the terminal-started cluster
    ray.init(address="auto", namespace=NAMESPACE)

    print(f"--- 🌍 Initializing World ({TOTAL_AGENTS} Agents) ---")

    # 1. Create Singleton Actors (Detached)
    try:
        db = DbWriter.options(name="GlobalDB", lifetime="detached").remote()
        clock = TimeKeeper.options(name="Clock", lifetime="detached").remote()
        print("✅ DB and Clock created.")
    except:
        print("⚠️ DB/Clock already exist.")

    # 2. Create LLM Pool (Detached)
    llm_names = []
    for i in range(4):
        name = f"LLM_{i}"
        try:
            LLMService.options(name=name, lifetime="detached").remote()
            llm_names.append(name)
        except:
            llm_names.append(name)  # Already exists
    print(f"✅ LLM Pool Ready: {llm_names}")

    # 3. Create Agent Batches (Detached)
    # We name them "Batch_0", "Batch_1" so Client can find them
    num_batches = TOTAL_AGENTS // BATCH_SIZE
    for i in range(num_batches):
        b_name = f"Batch_{i}"
        try:
            AgentBatch.options(name=b_name, lifetime="detached").remote(
                start_id=i * BATCH_SIZE,
                size=BATCH_SIZE,
                llm_names=llm_names,
                db_name="GlobalDB"
            )
        except:
            pass  # Already exists

    print(f"✅ {num_batches} Agent Batches Deployed.")
    print("--- Host Setup Complete. You may now run client.py ---")


if __name__ == "__main__":
    setup_world()