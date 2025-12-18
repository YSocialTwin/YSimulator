# run_client.py
import ray
import time
import random
from classes.ray_models import ActionDTO, AgentProfile


# --- Client Actor ---
@ray.remote
class SimulationClient:
    def __init__(self, client_id, llm_handle, agent_config=None, simulation_config=None):
        self.client_id = client_id
        self.llm = llm_handle
        
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
        
        # Create agents from configuration
        self.agent_profiles = []
        if agent_config:
            self.agent_profiles = self._create_agents_from_config(agent_config)
        
        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")
    
    def _create_agents_from_config(self, agent_config):
        """
        Create agent profiles from configuration.
        Combines predefined agents with generated agents.
        """
        import time
        
        agents = []
        current_time = int(time.time())
        
        # Load predefined agents
        if "agents" in agent_config:
            for agent_data in agent_config["agents"]:
                profile = AgentProfile(
                    id=agent_data.get("id"),
                    username=agent_data.get("username"),
                    email=agent_data.get("email", ""),
                    password=agent_data.get("password", "simulation_agent"),
                    leaning=agent_data.get("leaning", "neutral"),
                    user_type=agent_data.get("user_type", "agent"),
                    age=agent_data.get("age", 0),
                    oe=agent_data.get("oe"),
                    co=agent_data.get("co"),
                    ex=agent_data.get("ex"),
                    ag=agent_data.get("ag"),
                    ne=agent_data.get("ne"),
                    language=agent_data.get("language", "en"),
                    education_level=agent_data.get("education_level"),
                    joined_on=agent_data.get("joined_on", current_time),
                    gender=agent_data.get("gender"),
                    nationality=agent_data.get("nationality"),
                    profession=agent_data.get("profession", ""),
                    activity_profile=agent_data.get("activity_profile", "Always On"),
                    archetype=agent_data.get("archetype"),
                    cluster=agent_data.get("cluster", 0),
                    llm=agent_data.get("llm", False),
                    toxicity=agent_data.get("toxicity", "no"),
                    daily_activity_level=agent_data.get("daily_activity_level", 1),
                    round_actions=agent_data.get("round_actions", 3),
                    is_page=agent_data.get("is_page", 0)
                )
                agents.append(profile)
        
        # Generate additional agents if specified
        if "generation_config" in agent_config:
            gen_config = agent_config["generation_config"]
            num_additional = gen_config.get("num_additional_agents", 0)
            cluster_weights = gen_config["cluster_distribution"]["weights"]
            llm_prob = gen_config.get("llm_enabled_probability", 0.1)
            defaults = gen_config.get("default_settings", {})
            age_range = gen_config.get("age_range", [18, 65])
            
            start_id = (max((a.id for a in agents), default=0) + 1) if agents else 1
            
            archetypes = ["Validator", "Broadcaster", "Explorer"]
            activity_profiles = ["Always On", "Morning Active", "Evening Active", "Weekend Warrior"]
            professions = ["Engineer", "Teacher", "Designer", "Writer", "Analyst", "Manager"]
            genders = ["male", "female", "non-binary"]
            nationalities = ["US", "UK", "CA", "AU", "EU"]
            education_levels = ["high_school", "college", "graduate", "phd"]
            
            for i in range(num_additional):
                agent_id = start_id + i
                cluster = random.choices([0, 1, 2], weights=cluster_weights)[0]
                
                profile = AgentProfile(
                    id=agent_id,
                    username=f"agent_{agent_id:04d}",
                    email=f"agent{agent_id}@simulation.local",
                    password=defaults.get("password", "simulation_agent"),
                    leaning=defaults.get("leaning", "neutral"),
                    user_type=defaults.get("user_type", "agent"),
                    age=random.randint(age_range[0], age_range[1]),
                    oe=random.choice(["low", "medium", "high"]),
                    co=random.choice(["low", "medium", "high"]),
                    ex=random.choice(["low", "medium", "high"]),
                    ag=random.choice(["low", "medium", "high"]),
                    ne=random.choice(["low", "medium", "high"]),
                    language=defaults.get("language", "en"),
                    education_level=random.choice(education_levels),
                    joined_on=current_time,
                    gender=random.choice(genders),
                    nationality=random.choice(nationalities),
                    profession=random.choice(professions),
                    activity_profile=random.choice(activity_profiles),
                    archetype=archetypes[cluster],
                    cluster=cluster,
                    llm=random.random() < llm_prob,
                    toxicity=defaults.get("toxicity", "no"),
                    daily_activity_level=random.randint(1, 4),
                    round_actions=defaults.get("round_actions", 3),
                    is_page=defaults.get("is_page", 0)
                )
                agents.append(profile)
        
        return agents

    def run(self):
        # Register agents with the server
        print(f"[{self.client_id}] Registering {len(self.agent_profiles)} agents with server...")
        registration_result = ray.get(self.server.register_agents.remote(self.agent_profiles))
        print(f"[{self.client_id}] Agent registration complete: {registration_result}")
        
        # Register client
        ray.get(self.server.register_client.remote(self.client_id))
        print(f"[{self.client_id}] Client registered. Waiting for sync...")

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
        # Select active agents based on daily_activity_level
        active = random.sample(self.agent_profiles, k=int(len(self.agent_profiles) * 0.2))

        # --- 1. SCATTER: Fire off all tasks ---
        # We store tuples of (agent_data, object_handle, type)
        pending_llm_posts = []
        pending_llm_reactions = []

        for agent_profile in active:
            cid = agent_profile.cluster
            p_post = 0.7 if cid == 1 else 0.1
            p_react = 0.8 if cid == 0 else 0.3

            # --- Post Logic ---
            if random.random() < p_post:
                if agent_profile.llm:
                    # Don't call ray.get() here! Just get the handle (future).
                    future = self.llm.generate_post.remote(cid, day, slot)
                    pending_llm_posts.append((agent_profile.id, cid, future))
                else:
                    # Rule-based is instant
                    txt = f"Cluster {cid} post"
                    actions.append(ActionDTO(agent_profile.id, cid, 'POST', content=txt))

            # --- Reaction Logic ---
            if recent_posts and random.random() < p_react:
                target = random.choice(recent_posts)
                if agent_profile.llm:
                    future = self.llm.decide_reaction.remote(cid, "content")
                    pending_llm_reactions.append((agent_profile.id, cid, target, future))
                else:
                    # Rule-based
                    actions.append(ActionDTO(agent_profile.id, cid, 'LIKE', target_post_id=target))

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


