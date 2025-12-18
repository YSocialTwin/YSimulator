"""
YClient - Simulation Client for YSimulator.

This module contains the Ray remote actor that runs simulation clients,
managing agent behaviors and coordinating with the orchestrator server.
"""

import json
import logging
import random
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile


@ray.remote
class SimulationClient:
    """
    Simulation client actor that manages agent behaviors and actions.

    This client handles:
    - Agent profile creation and management
    - Simulation loop execution
    - Action generation (posts and reactions)
    - Coordination with LLM service for intelligent behaviors
    """

    def __init__(
        self,
        client_id: str,
        llm_handle,
        agent_config: dict = None,
        simulation_config: dict = None,
        config_path: str = ".",
        parent_logger=None,
    ):
        """
        Initialize the simulation client.

        Args:
            client_id: Unique identifier for this client
            llm_handle: Ray actor handle for LLM service
            agent_config: Agent population configuration
            simulation_config: Simulation parameters
            config_path: Path to configuration directory for logs
            parent_logger: Parent logger (not used in Ray actor, we create our own)
        """
        self.client_id = client_id
        self.llm = llm_handle
        self.config_path = Path(config_path)

        # Load simulation configuration with defaults
        if simulation_config is None:
            simulation_config = {"simulation": {"num_days": 0, "num_slots_per_day": 24, "heartbeat_interval": 5}}

        self.num_days = simulation_config["simulation"]["num_days"]
        self.num_slots_per_day = simulation_config["simulation"]["num_slots_per_day"]
        self.heartbeat_interval = simulation_config["simulation"].get("heartbeat_interval", 5)

        # Create agents from configuration
        self.agent_profiles = []
        if agent_config:
            self.agent_profiles = self._create_agents_from_config(agent_config)

        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")

        # Set up logging
        self._setup_logging()
        self.logger.info(
            "Simulation client initialized",
            extra={
                "extra_data": {
                    "client_id": client_id,
                    "num_agents": len(self.agent_profiles),
                    "num_days": self.num_days,
                }
            },
        )

    def _setup_logging(self):
        """Set up JSON logging for the client actor."""
        log_dir = self.config_path / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"{self.client_id}_actor.log"

        # Create logger
        self.logger = logging.getLogger(f"YSimulator.Client.{self.client_id}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Create file handler with JSON formatting
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                if hasattr(record, "execution_time"):
                    log_data["execution_time_ms"] = record.execution_time
                if hasattr(record, "extra_data"):
                    log_data.update(record.extra_data)
                return json.dumps(log_data)

        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

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
                    is_page=agent_data.get("is_page", 0),
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
                    is_page=defaults.get("is_page", 0),
                )
                agents.append(profile)

        return agents

    def run(self):
        """
        Main simulation loop for the client.

        This method:
        1. Registers agents with the server
        2. Registers the client
        3. Runs the simulation loop until completion or max days reached
        4. Sends periodic heartbeats to prevent being marked as stale
        5. Notifies server on completion
        """
        # Register agents with the server
        start_time = time.time()
        print(f"[{self.client_id}] Registering {len(self.agent_profiles)} agents with server...")

        registration_result = ray.get(self.server.register_agents.remote(self.agent_profiles))
        reg_time = (time.time() - start_time) * 1000

        self.logger.info(
            "Agents registered with server",
            extra={"extra_data": {**registration_result, "execution_time_ms": reg_time}},
        )
        print(f"[{self.client_id}] Agent registration complete: {registration_result}")

        # Register client with the server, passing num_days for informational purposes
        client_reg = ray.get(self.server.register_client.remote(self.client_id, self.num_days))
        
        # Validate registration response has all required fields
        required_fields = ["registered", "start_day", "start_slot"]
        if not isinstance(client_reg, dict):
            raise RuntimeError(f"Client registration failed: expected dict, got {type(client_reg)}")
        
        missing_fields = [f for f in required_fields if f not in client_reg]
        if missing_fields:
            raise RuntimeError(f"Client registration response missing fields: {missing_fields}")
        
        if not client_reg["registered"]:
            raise RuntimeError(f"Client registration failed: {client_reg}")
        
        # Server tells us where to start - we count from here
        start_day = client_reg["start_day"]
        start_slot = client_reg["start_slot"]
        
        # Calculate our personal max_day for local tracking
        # num_days=0 means infinite simulation
        max_day = start_day + self.num_days if self.num_days > 0 else float('inf')
        max_day_str = "∞" if max_day == float('inf') else str(max_day)
        
        self.logger.info(
            "Client registered with server",
            extra={"extra_data": {
                "start_day": start_day,
                "start_slot": start_slot,
                "num_days": self.num_days,
                "max_day": max_day,
            }},
        )
        print(
            f"[{self.client_id}] Client registered. Starting at day {start_day}, slot {start_slot}. "
            f"Will run for {self.num_days if self.num_days > 0 else '∞'} days (until day {max_day_str})."
        )

        slot_count = 0
        last_heartbeat_time = time.time()

        try:
            while True:
                # Send heartbeat periodically (configurable interval, default: 5 seconds)
                if time.time() - last_heartbeat_time > self.heartbeat_interval:
                    ray.get(self.server.heartbeat.remote(self.client_id))
                    last_heartbeat_time = time.time()

                instruction = ray.get(self.server.get_instruction.remote(self.client_id))

                if instruction.status == "WAIT":
                    time.sleep(1)
                    continue

                # Check if we've reached our personal maximum day (client-side tracking)
                if self.num_days > 0 and instruction.day >= max_day:
                    self.logger.info(
                        "Reached maximum days (client-side check)",
                        extra={
                            "extra_data": {
                                "final_day": instruction.day,
                                "start_day": start_day,
                                "num_days": self.num_days,
                                "total_slots": slot_count,
                            }
                        },
                    )
                    print(
                        f"[{self.client_id}] Completed {self.num_days} days "
                        f"(day {start_day} to {instruction.day - 1}). Total slots: {slot_count}"
                    )
                    break

                # Process Logic
                sim_start = time.time()
                actions = self._simulate(instruction.day, instruction.slot, instruction.recent_post_ids)
                sim_time = (time.time() - sim_start) * 1000

                # Submit
                submit_start = time.time()
                ray.get(self.server.submit_actions.remote(self.client_id, actions))
                submit_time = (time.time() - submit_start) * 1000

                slot_count += 1

                self.logger.info(
                    "Slot completed",
                    extra={
                        "extra_data": {
                            "day": instruction.day,
                            "slot": instruction.slot,
                            "num_actions": len(actions),
                            "simulation_time_ms": sim_time,
                            "submit_time_ms": submit_time,
                        }
                    },
                )

                print(
                    f"[{self.client_id}] Day {instruction.day} Slot {instruction.slot} -> "
                    f"Submitted {len(actions)} actions."
                )

        finally:
            # Notify server that this client has completed all activities
            try:
                ray.get(self.server.complete_client.remote(self.client_id))
                self.logger.info("Notified server of completion")
                print(f"[{self.client_id}] ✅ Simulation complete. Server notified.")
            except Exception as e:
                self.logger.warning(
                    f"Failed to notify server of completion: {e}",
                    extra={"extra_data": {"error": str(e)}},
                )

    def _simulate(self, day: int, slot: int, recent_posts: list) -> list:
        """
        Simulate agent behaviors for a given time slot.

        Args:
            day: Current simulation day
            slot: Current time slot
            recent_posts: List of recent post IDs for reactions

        Returns:
            list: List of ActionDTO objects representing agent actions
        """
        actions = []
        # Select active agents based on daily_activity_level
        active = random.sample(self.agent_profiles, k=int(len(self.agent_profiles) * 0.2))

        # --- 1. SCATTER: Fire off all LLM tasks in parallel ---
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
                    actions.append(ActionDTO(agent_profile.id, cid, "POST", content=txt))

            # --- Reaction Logic ---
            if recent_posts and random.random() < p_react:
                target = random.choice(recent_posts)
                if agent_profile.llm:
                    future = self.llm.decide_reaction.remote(cid, "content")
                    pending_llm_reactions.append((agent_profile.id, cid, target, future))
                else:
                    # Rule-based
                    actions.append(ActionDTO(agent_profile.id, cid, "LIKE", target_post_id=target))

        # --- 2. GATHER: Wait for all LLM results in parallel ---

        # Resolve Posts
        if pending_llm_posts:
            # Extract just the futures list to pass to ray.get
            futures = [p[2] for p in pending_llm_posts]
            results = ray.get(futures)  # Blocks once for ALL posts

            for i, res_txt in enumerate(results):
                a_id, cid, _ = pending_llm_posts[i]
                actions.append(ActionDTO(a_id, cid, "POST", content=res_txt))

        # Resolve Reactions
        if pending_llm_reactions:
            futures = [r[3] for r in pending_llm_reactions]
            results = ray.get(futures)  # Blocks once for ALL reactions

            for i, res_act in enumerate(results):
                a_id, cid, target, _ = pending_llm_reactions[i]
                if res_act != "IGNORE":
                    actions.append(ActionDTO(a_id, cid, res_act, target_post_id=target))

        return actions

    def shutdown(self):
        ray.get(self.server.deregister_client.remote(self.client_id))
