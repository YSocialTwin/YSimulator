# run_client.py
import ray
import time
import random
from classes.models import ActionDTO


# --- Client Actor ---
@ray.remote
class SimulationClient:
    def __init__(self, client_id, llm_handle, agent_config=None, simulation_config=None):
        self.client_id = client_id
        self.llm = llm_handle
        
        # Load agent configuration with defaults
        if agent_config is None:
            agent_config = {
                "num_agents": 50,
                "cluster_distribution": {
                    "weights": [0.4, 0.3, 0.3],
                    "llm_enabled_probability": 0.1
                }
            }
        
        # Load simulation configuration with defaults
        if simulation_config is None:
            simulation_config = {
                "simulation": {
                    "num_days": 0,
                    "num_slots_per_day": 24
                }
            }
        
        self.num_days = simulation_config["simulation"]["num_days"]
        self.num_slots_per_day = simulation_config["simulation"]["num_slots_per_day"]
        
        # Create agents based on configuration
        num_agents = agent_config["num_agents"]
        cluster_weights = agent_config["cluster_distribution"]["weights"]
        llm_prob = agent_config["cluster_distribution"]["llm_enabled_probability"]
        
        self.agents = []
        for i in range(num_agents):
            cluster = random.choices([0, 1, 2], weights=cluster_weights)[0]
            self.agents.append({'id': i, 'cluster': cluster, 'llm': random.random() < llm_prob})

        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")

    def run(self):
        ray.get(self.server.register_client.remote(self.client_id))
        print(f"[{self.client_id}] Registered. Waiting for sync...")

        # Determine stopping condition
        max_days = self.num_days if self.num_days > 0 else float('inf')
        current_day = 0

        while current_day < max_days:
            instruction = ray.get(self.server.get_instruction.remote(self.client_id))

            if instruction.status == 'WAIT':
                time.sleep(1)
                continue

            # Check if we've reached the day limit
            if instruction.day >= max_days:
                print(f"[{self.client_id}] Reached max days ({max_days}). Stopping.")
                break
            
            current_day = instruction.day

            # Process Logic
            actions = self._simulate(instruction.day, instruction.slot, instruction.recent_post_ids)

            # Submit
            ray.get(self.server.submit_actions.remote(self.client_id, actions))
            print(
                f"[{self.client_id}] Day {instruction.day} Slot {instruction.slot} -> Submitted {len(actions)} actions.")

    def _simulate(self, day, slot, recent_posts):
        actions = []
        active = random.sample(self.agents, k=int(len(self.agents) * 0.2))

        # --- 1. SCATTER: Fire off all tasks ---
        # We store tuples of (agent_data, object_handle, type)
        pending_llm_posts = []
        pending_llm_reactions = []

        for ag in active:
            cid = ag['cluster']
            p_post = 0.7 if cid == 1 else 0.1
            p_react = 0.8 if cid == 0 else 0.3

            # --- Post Logic ---
            if random.random() < p_post:
                if ag['llm']:
                    # Don't call ray.get() here! Just get the handle (future).
                    future = self.llm.generate_post.remote(cid, day, slot)
                    pending_llm_posts.append((ag['id'], cid, future))
                else:
                    # Rule-based is instant
                    txt = f"Cluster {cid} post"
                    actions.append(ActionDTO(ag['id'], cid, 'POST', content=txt))

            # --- Reaction Logic ---
            if recent_posts and random.random() < p_react:
                target = random.choice(recent_posts)
                if ag['llm']:
                    future = self.llm.decide_reaction.remote(cid, "content")
                    pending_llm_reactions.append((ag['id'], cid, target, future))
                else:
                    # Rule-based
                    actions.append(ActionDTO(ag['id'], cid, 'LIKE', target_post_id=target))

        # --- 2. GATHER: Wait for all LLM results in parallel ---

        # Resolve Posts
        if pending_llm_posts:
            # Extract just the futures list to pass to ray.get
            futures = [p[2] for p in pending_llm_posts]
            results = ray.get(futures)  # Blocks once for ALL posts

            for i, res_txt in enumerate(results):
                a_id, cid, _ = pending_llm_posts[i]
                actions.append(ActionDTO(a_id, cid, 'POST', content=res_txt))

        # Resolve Reactions
        if pending_llm_reactions:
            futures = [r[3] for r in pending_llm_reactions]
            results = ray.get(futures)  # Blocks once for ALL reactions

            for i, res_act in enumerate(results):
                a_id, cid, target, _ = pending_llm_reactions[i]
                if res_act != 'IGNORE':
                    actions.append(ActionDTO(a_id, cid, res_act, target_post_id=target))

        return actions
    def shutdown(self):
        ray.get(self.server.deregister_client.remote(self.client_id))


