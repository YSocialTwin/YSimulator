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

from YSimulator.YClient.actions import (
    generate_llm_post_async,
    generate_llm_reaction_async,
    generate_llm_read_async,
    generate_rule_based_post,
    generate_rule_based_reaction,
    generate_rule_based_comment,
    generate_rule_based_share,
    generate_rule_based_read,
    generate_news_post_async,
    generate_rule_based_news_post,
)
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.recsys import (
    ContentRecSys,
    ReverseChrono,
    ReverseChronoPopularity,
    ReverseChronoFollowers,
    ReverseChronoFollowersPopularity,
    ReverseChronoComments,
    CommonInterests,
    CommonUserInterests,
    SimilarUsersReact,
    SimilarUsersPosts,
    RandomOrder
)

# Constants
REACTION_TYPES = ["LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"]

# Recommendation system class mapping
RECSYS_CLASS_MAP = {
    "random": RandomOrder,
    "rchrono": ReverseChrono,
    "rchrono_popularity": ReverseChronoPopularity,
    "rchrono_followers": ReverseChronoFollowers,
    "rchrono_followers_popularity": ReverseChronoFollowersPopularity,
    "rchrono_comments": ReverseChronoComments,
    "common_interests": CommonInterests,
    "common_user_interests": CommonUserInterests,
    "similar_users_react": SimilarUsersReact,
    "similar_users_posts": SimilarUsersPosts,
}


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
        news_service_handle=None,
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
            news_service_handle: Ray actor handle for NewsFeedService (optional)
        """
        self.client_id = client_id
        self.llm = llm_handle
        self.news_service = news_service_handle
        self.config_path = Path(config_path)

        # Load simulation configuration with defaults
        if simulation_config is None:
            simulation_config = {"simulation": {"num_days": 0, "num_slots_per_day": 24, "heartbeat_interval": 5}}

        self.num_days = simulation_config["simulation"]["num_days"]
        self.num_slots_per_day = simulation_config["simulation"]["num_slots_per_day"]
        self.heartbeat_interval = simulation_config["simulation"].get("heartbeat_interval", 5)

        # Load activity profiles (maps profile name to list of active hours)
        self.activity_profiles = self._parse_activity_profiles(
            simulation_config["simulation"].get("activity_profiles", {})
        )
        
        # Load hourly activity distribution (probability of activity per hour)
        self.hourly_activity = {
            int(k): float(v) 
            for k, v in simulation_config["simulation"].get("hourly_activity", {}).items()
        }
        
        # Load actions likelihood (weights for action selection)
        self.actions_likelihood = simulation_config["simulation"].get("actions_likelihood", {})
        
        # Load archetype configuration for agent sampling
        archetype_config = simulation_config["simulation"].get("agent_archetypes", {})
        self.archetypes_enabled = archetype_config.get("enabled", False)
        self.archetype_distribution = archetype_config.get("distribution", {})
        
        # Load recommendation system configuration
        recsys_config = simulation_config["simulation"].get("recsys", {})
        self.recsys_mode = recsys_config.get("mode", "random")  # "random" or "rchrono"
        self.recsys_n_posts = recsys_config.get("n_posts", 5)
        self.recsys_visibility_rounds = recsys_config.get("visibility_rounds", 36)

        # Create agents from configuration
        self.agent_profiles = []
        if agent_config:
            self.agent_profiles = self._create_agents_from_config(agent_config)

        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")
        
        # Set up logging first (before any logging attempts)
        self._setup_logging()
        
        # Register page agent feeds with news service
        if self.news_service:
            for agent in self.agent_profiles:
                if agent.is_page == 1 and agent.feed_url:
                    try:
                        ray.get(self.news_service.register_page_feed.remote(agent.feed_url, str(agent.id)))
                    except Exception as e:
                        # Failed to register page feed, log and continue
                        self.logger.warning(f"Failed to register feed for page {agent.username}: {e}")

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

    def _parse_activity_profiles(self, activity_profiles_config):
        """
        Parse activity profiles from configuration.
        
        Converts string representations like "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23"
        into lists of integers representing active hours.
        
        Args:
            activity_profiles_config: Dictionary mapping profile names to hour strings
            
        Returns:
            dict: Dictionary mapping profile names to lists of active hours (0-23)
        """
        parsed_profiles = {}
        for profile_name, hours_str in activity_profiles_config.items():
            if isinstance(hours_str, str):
                hours = [int(h.strip()) for h in hours_str.split(",")]
                # Validate that all hours are in valid range 0-23
                valid_hours = [h for h in hours if 0 <= h <= 23]
                if len(valid_hours) != len(hours):
                    self.logger.warning(
                        f"Invalid hours found in activity profile '{profile_name}', filtered to valid range 0-23"
                    )
                parsed_profiles[profile_name] = valid_hours
            elif isinstance(hours_str, list):
                # Validate list hours as well
                valid_hours = [h for h in hours_str if isinstance(h, int) and 0 <= h <= 23]
                parsed_profiles[profile_name] = valid_hours
            else:
                self.logger.warning(
                    f"Invalid activity profile format for '{profile_name}': {hours_str}"
                )
                parsed_profiles[profile_name] = list(range(24))  # Default to always active
        return parsed_profiles

    def _sample_agents_by_archetype(self, available_agents, num_active):
        """
        Sample agents according to archetype distribution.
        
        Ensures that active agents are composed using the archetype distribution 
        from the configuration. If a percentage is > 0, at least one agent of that 
        archetype is always selected (if available).
        
        Args:
            available_agents: List of agents available for selection
            num_active: Total number of agents to activate
            
        Returns:
            list: List of selected agents respecting archetype distribution
        """
        # Group agents by archetype
        agents_by_archetype = {}
        agents_without_archetype = []
        
        for agent in available_agents:
            archetype = agent.archetype
            # Normalize archetype to lowercase for comparison
            if archetype:
                archetype_key = archetype.lower()
                if archetype_key not in agents_by_archetype:
                    agents_by_archetype[archetype_key] = []
                agents_by_archetype[archetype_key].append(agent)
            else:
                # Track agents without archetype separately
                agents_without_archetype.append(agent)
        
        selected_agents = []
        remaining_slots = num_active
        
        # Count how many archetypes have distribution > 0 and are available
        available_archetypes = [
            arch for arch, pct in self.archetype_distribution.items()
            if pct > 0 and arch in agents_by_archetype
        ]
        
        # First pass: ensure at least 1 agent per archetype if distribution > 0
        if num_active >= len(available_archetypes):
            # We have enough slots to give at least 1 to each archetype
            for archetype in available_archetypes:
                if remaining_slots > 0:
                    available_for_archetype = agents_by_archetype[archetype]
                    if available_for_archetype:
                        selected = random.choice(available_for_archetype)
                        selected_agents.append(selected)
                        agents_by_archetype[archetype].remove(selected)
                        remaining_slots -= 1
            
            # Second pass: distribute remaining slots according to distribution
            if remaining_slots > 0:
                for archetype, percentage in self.archetype_distribution.items():
                    if archetype in agents_by_archetype and remaining_slots > 0:
                        available_for_archetype = agents_by_archetype[archetype]
                        # Calculate additional agents for this archetype (beyond the guaranteed 1)
                        additional = round(remaining_slots * percentage)
                        num_to_select = min(additional, len(available_for_archetype), remaining_slots)
                        
                        if num_to_select > 0:
                            selected = random.sample(available_for_archetype, k=num_to_select)
                            selected_agents.extend(selected)
                            remaining_slots -= num_to_select
                            for agent in selected:
                                agents_by_archetype[archetype].remove(agent)
        else:
            # Not enough slots for all archetypes, use strict proportional distribution
            for archetype, percentage in self.archetype_distribution.items():
                if archetype in agents_by_archetype and remaining_slots > 0:
                    available_for_archetype = agents_by_archetype[archetype]
                    target = round(num_active * percentage)
                    num_to_select = min(target, len(available_for_archetype), remaining_slots)
                    
                    if num_to_select > 0:
                        selected = random.sample(available_for_archetype, k=num_to_select)
                        selected_agents.extend(selected)
                        remaining_slots -= num_to_select
                        for agent in selected:
                            agents_by_archetype[archetype].remove(agent)
        
        # Fill any remaining slots with any available agents (including those without archetype)
        if remaining_slots > 0:
            all_remaining = agents_without_archetype.copy()
            for agents_list in agents_by_archetype.values():
                all_remaining.extend(agents_list)
            
            if all_remaining:
                additional_needed = min(remaining_slots, len(all_remaining))
                if additional_needed > 0:
                    additional = random.sample(all_remaining, k=additional_needed)
                    selected_agents.extend(additional)
        
        return selected_agents

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
                    feed_url=agent_data.get("feed_url"),  # RSS feed for page agents
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

            # Generate UUIDs for additional agents using the same namespace
            import uuid
            AGENT_UUID_NAMESPACE = uuid.UUID('12345678-1234-5678-1234-567812345678')
            
            # Find the starting index for generated agents
            # If we have predefined agents, start after them; otherwise start at 1
            if agents:
                # Try to extract numeric part from existing IDs for indexing
                # For UUIDs, we'll just start from a high number to avoid conflicts
                start_index = 10000
            else:
                start_index = 1

            archetypes = ["Validator", "Broadcaster", "Explorer"]
            activity_profiles = ["Always On", "Morning Active", "Evening Active", "Weekend Warrior"]
            professions = ["Engineer", "Teacher", "Designer", "Writer", "Analyst", "Manager"]
            genders = ["male", "female", "non-binary"]
            nationalities = ["US", "UK", "CA", "AU", "EU"]
            education_levels = ["high_school", "college", "graduate", "phd"]

            for i in range(num_additional):
                agent_index = start_index + i
                # Generate deterministic UUID for generated agents
                agent_id = str(uuid.uuid5(AGENT_UUID_NAMESPACE, f"generated_agent_{agent_index}"))
                cluster = random.choices([0, 1, 2], weights=cluster_weights)[0]

                profile = AgentProfile(
                    id=agent_id,
                    username=f"agent_{agent_index:04d}",
                    email=f"agent{agent_index}@simulation.local",
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

    def _load_and_create_social_network(self, network_csv_path: Path) -> int:
        """
        Load social network topology from CSV file and create Follow records.
        
        This method reads a network.csv file where each row represents an edge
        in the social network as "agent1_name,agent2_name" and creates Follow
        records in the database for each edge.
        
        Args:
            network_csv_path: Path to the network.csv file
            
        Returns:
            int: Number of follow relationships created
        """
        import csv
        
        if not network_csv_path.exists():
            self.logger.info(f"No network.csv found at {network_csv_path}, skipping social network creation")
            return 0
        
        self.logger.info(f"Loading social network from {network_csv_path}")
        
        # Create a mapping from username to agent ID for quick lookup
        username_to_id = {agent.username: str(agent.id) for agent in self.agent_profiles}
        
        follow_count = 0
        skipped_count = 0
        
        try:
            with open(network_csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                for row_num, row in enumerate(reader, start=1):
                    # Skip empty rows
                    if not row or len(row) < 2:
                        continue
                    
                    # Parse the edge: follower follows user
                    follower_name = row[0].strip()
                    user_name = row[1].strip()
                    
                    # Skip if either username is not in our agent population
                    if follower_name not in username_to_id:
                        self.logger.warning(
                            f"Skipping row {row_num}: follower '{follower_name}' not found in agent population"
                        )
                        skipped_count += 1
                        continue
                    
                    if user_name not in username_to_id:
                        self.logger.warning(
                            f"Skipping row {row_num}: user '{user_name}' not found in agent population"
                        )
                        skipped_count += 1
                        continue
                    
                    # Get agent IDs
                    follower_id = username_to_id[follower_name]
                    user_id = username_to_id[user_name]
                    
                    # Create follow relationship via server
                    # We use the server's method to insert follow data
                    # The round is set to None/empty for initial network setup
                    follow_data = {
                        "follower_id": follower_id,
                        "user_id": user_id,
                        "action": "follow",
                        "round": "",  # Empty round for initial network setup
                    }
                    
                    # Call server to add the follow relationship
                    try:
                        success = ray.get(self.server.add_follow_relationship.remote(follow_data))
                        if success:
                            follow_count += 1
                        else:
                            self.logger.warning(
                                f"Failed to create follow relationship: {follower_name} -> {user_name}"
                            )
                            skipped_count += 1
                    except Exception as e:
                        self.logger.error(
                            f"Error creating follow relationship: {follower_name} -> {user_name}: {e}",
                            extra={"extra_data": {"error": str(e)}}
                        )
                        skipped_count += 1
            
            self.logger.info(
                f"Social network loaded: {follow_count} relationships created, {skipped_count} skipped",
                extra={"extra_data": {"follow_count": follow_count, "skipped_count": skipped_count}}
            )
            print(f"[{self.client_id}] Social network loaded: {follow_count} follow relationships created")
            
            return follow_count
            
        except Exception as e:
            self.logger.error(
                f"Error loading social network from {network_csv_path}: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return 0

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
        
        # Load social network topology if this is the first run (day 0, slot 0)
        # and if network.csv exists in the config directory
        if start_day == 0 and start_slot == 0:
            network_csv_path = self.config_path / "network.csv"
            if network_csv_path.exists():
                print(f"[{self.client_id}] First run detected, loading social network topology...")
                self._load_and_create_social_network(network_csv_path)
            else:
                self.logger.info("First run but no network.csv found, skipping social network creation")
        
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

    def __select_action(self, agent_profile: AgentProfile, recent_posts: list) -> tuple:
        """
        Determine which action an agent should perform.
        
        This method implements the action selection logic based on:
        - actions_likelihood from simulation config (weighted action selection)
        - Agent's archetype (filters available actions)
        - Availability of recent posts (for comment/reaction actions)
        - Agent type (LLM vs rule-based)
        - Page agents can ONLY perform share_link action
        
        Args:
            agent_profile: Agent profile containing behavior settings
            recent_posts: List of recent post UUIDs available for reactions
            
        Returns:
            tuple: (action_type, agent_type, target_post_id) where:
                - action_type: "post", "comment", "read", "image", "share_link", "share", "search", "cast", or None
                - agent_type: "llm" or "rule_based"
                - target_post_id: UUID string for comment/read/share actions, None for posts/no-action
                
        Example:
            >>> action_type, agent_type, target = self.__select_action(profile, posts)
            >>> if action_type == "post":
            ...     # Generate post action
            >>> elif action_type == "comment":
            ...     # Generate comment to target post
        """
        # Page agents can ONLY perform share_link action
        if agent_profile.is_page == 1:
            agent_type = "llm" if agent_profile.llm else "rule_based"
            return "share_link", agent_type, None
        
        # Define archetype-to-action mappings
        # This filters which actions are available based on archetype
        # NOTE: Future enhancement - these mappings could be moved to simulation_config.json
        # for easier customization without code changes
        archetype_actions = {
            "Validator": ["share", "read", "share_link"],  # Validators react and share content: they are active content consumers
            "Broadcaster": ["post", "image", "share", "comment"],  # Broadcasters post, comment and share contents and images: they are content producers
            "Explorer": ["search", "follow"],  # Explorers follow and search to grow network: they are lurkers
        }
        
        # Get archetype-specific action weights with safe fallback
        archetype = agent_profile.archetype
        
        # If agent has no archetype (archetypes disabled), all actions are available
        if not archetype:
            # Get all action types from actions_likelihood
            available_actions = list(self.actions_likelihood.keys())
        elif archetype in archetype_actions:
            # Use archetype-specific actions
            available_actions = archetype_actions[archetype]
        else:
            # Unknown archetype - use all available actions as fallback
            available_actions = list(self.actions_likelihood.keys())
        
        # Filter actions_likelihood to only include available actions
        filtered_likelihood = {
            action: weight 
            for action, weight in self.actions_likelihood.items() 
            if action in available_actions and weight > 0
        }
        
        # If no valid actions, return no action
        if not filtered_likelihood:
            return None, None, None
            
        # Select action based on weighted probabilities
        actions = list(filtered_likelihood.keys())
        weights = list(filtered_likelihood.values())
        
        # random.choices can work directly with unnormalized weights
        selected_action = random.choices(actions, weights=weights)[0]
        
        # Determine agent type
        agent_type = "llm" if agent_profile.llm else "rule_based"
        
        # Actions that require a target post
        target_required_actions = ["comment", "read", "share"]
        
        # If action requires a target but no posts available, return no action
        if selected_action in target_required_actions and not recent_posts:
            return None, None, None
            
        # Select target post if needed
        target = random.choice(recent_posts) if selected_action in target_required_actions else None
        
        return selected_action, agent_type, target

    def _simulate(self, day: int, slot: int, recent_posts: list) -> list:
        """
        Simulate agent behaviors for a given time slot using modular action implementations.
        
        This method orchestrates the simulation by:
        1. Using hourly_activity to determine how many agents should be active
        2. Filtering agents by their activity_profile (are they available at this hour?)
        3. Selecting active agents based on hourly activity probability
        4. For each active agent: sampling number of actions from daily_activity_level
        5. For each action: calling select_action() to determine what to do
        6. Dispatching actions based on agent type (rule_based vs llm)
        7. Gathering async LLM results in parallel (scatter/gather pattern)
        
        The scatter/gather pattern is preserved for performance:
        - Scatter: Fire off all LLM calls immediately without waiting
        - Gather: Wait once for all LLM results simultaneously
        
        Args:
            day: Current simulation day
            slot: Current time slot (0-23, representing hour of day)
            recent_posts: List of recent post UUIDs for reactions
            
        Returns:
            list: List of ActionDTO objects representing agent actions
        """
        actions = []
        
        # Get hourly activity probability for this slot (default to 0.04 if not specified)
        hourly_prob = self.hourly_activity.get(slot, 0.04)
        
        # Separate regular agents and page agents
        # Pages are always active during their activity profile hours
        regular_agents = []
        page_agents = []
        
        for agent in self.agent_profiles:
            profile_name = agent.activity_profile
            active_hours = self.activity_profiles.get(profile_name, list(range(24)))
            if slot in active_hours:
                if agent.is_page == 1:
                    page_agents.append(agent)
                else:
                    regular_agents.append(agent)
        
        self.logger.info(f"Activity sampling: slot={slot}, regular_agents={len(regular_agents)}, page_agents={len(page_agents)}")
        if page_agents:
            self.logger.info(f"Active page agents: {[p.username for p in page_agents]}")
        
        # Calculate number of regular agents to activate based on hourly_activity
        # Page agents don't count toward the hourly percentage
        active_regular_agents = []
        if regular_agents:
            num_active = max(1, int(len(regular_agents) * hourly_prob))
            num_active = min(num_active, len(regular_agents))  # Can't exceed available agents
            
            # Sample active agents from regular agents
            if num_active > 0:
                # If archetypes are enabled, sample according to distribution
                if self.archetypes_enabled and self.archetype_distribution:
                    active_regular_agents = self._sample_agents_by_archetype(regular_agents, num_active)
                else:
                    # Random sampling when archetypes are disabled
                    active_regular_agents = random.sample(regular_agents, k=num_active)
        
        # Combine regular agents and ALL page agents that are available
        active_agents = active_regular_agents + page_agents
        self.logger.info(f"Total active agents for this round: {len(active_agents)} (regular: {len(active_regular_agents)}, pages: {len(page_agents)})")
        
        # Track pending LLM calls for parallel execution
        # Each entry: (agent_id, cluster_id, future) for posts
        # Each entry: (agent_id, cluster_id, target_post_id, future) for reactions/comments
        pending_llm_posts = []
        pending_llm_reactions = []
        
        # --- SCATTER PHASE: Select and dispatch actions ---
        for agent in active_agents:
            # Sample number of actions for this agent based on daily_activity_level
            # Random from 1 to daily_activity_level (minimum 1)
            if agent.daily_activity_level <= 0:
                # Skip agents with 0 or negative activity level
                continue
            num_actions = random.randint(1, agent.daily_activity_level)
            
            if agent.is_page == 1:
                self.logger.info(f"Page agent {agent.username} will perform {num_actions} actions")
            
            for action_idx in range(num_actions):
                action_type, agent_type, target = self.__select_action(agent, recent_posts)
                
                if agent.is_page == 1:
                    self.logger.info(f"Page agent {agent.username} action {action_idx+1}/{num_actions}: type={action_type}, agent_type={agent_type}")
                
                if action_type == "post":
                    if agent_type == "llm":
                        # LLM: Fire off async call (don't wait for result yet)
                        future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
                        pending_llm_posts.append((agent.id, agent.cluster, future, None))
                    else:
                        # Rule-based: Execute immediately
                        action = generate_rule_based_post(agent.id, agent.cluster)
                        actions.append(action)
                
                elif action_type == "comment":
                    # Use recsys to get recommended posts to comment on
                    # Initialize recsys based on agent's recsys_type preference
                    # Fall back to global config if agent doesn't specify
                    agent_recsys_mode = getattr(agent, 'recsys_type', None) or self.recsys_mode
                    
                    # Get the appropriate recsys class, default to RandomOrder if unknown
                    recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
                    
                    # Initialize the recsys with configuration parameters
                    recsys = recsys_class(
                        n_posts=self.recsys_n_posts,
                        visibility_rounds=self.recsys_visibility_rounds
                    )
                    
                    # Get recommended posts from server
                    recommended_posts = recsys.get_recommendations(self.server, agent.id)
                    
                    if not recommended_posts:
                        # No posts available to comment on, skip this action
                        continue
                    
                    # Select one post randomly from recommendations
                    target_post = random.choice(recommended_posts)
                    
                    if agent_type == "llm":
                        # LLM: Get the post content and ask for a comment
                        # First, fetch the post content
                        post_data = ray.get(self.server.get_post.remote(target_post))
                        if post_data:
                            post_content = post_data.get("tweet", "")
                            # Fire off async LLM call to generate comment
                            future = self.llm.generate_comment.remote(agent.cluster, post_content)
                            pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
                        else:
                            # Post not found, skip
                            continue
                    else:
                        # Rule-based: Just comment "COMMENT"
                        action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
                        actions.append(action)
                
                elif action_type == "read":
                    # Read action: Get recommended posts, save recommendations, randomly select one, and decide reaction
                    # Use recsys to get recommended posts
                    # Initialize recsys based on agent's recsys_type preference
                    # Fall back to global config if agent doesn't specify
                    agent_recsys_mode = getattr(agent, 'recsys_type', None) or self.recsys_mode
                    
                    # Get the appropriate recsys class, default to RandomOrder if unknown
                    recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
                    
                    # Initialize the recsys with configuration parameters
                    recsys = recsys_class(
                        n_posts=self.recsys_n_posts,
                        visibility_rounds=self.recsys_visibility_rounds
                    )
                    
                    # Get recommended posts from server
                    # Note: _save_recommendation is already called inside get_recommendations via server
                    recommended_posts = recsys.get_recommendations(self.server, agent.id)
                    
                    if not recommended_posts:
                        # No posts available to read, skip this action
                        continue
                    
                    # Select one post randomly from recommendations
                    target_post = random.choice(recommended_posts)
                    
                    if agent_type == "llm":
                        # LLM: Get the post content and ask for a reaction decision
                        # First, fetch the post content
                        post_data = ray.get(self.server.get_post.remote(target_post))
                        if post_data:
                            post_content = post_data.get("tweet", "")
                            # Fire off async LLM call to decide reaction
                            future = generate_llm_read_async(self.llm, agent.cluster, post_content)
                            pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
                        else:
                            # Post not found, skip
                            continue
                    else:
                        # Rule-based: Randomly choose LIKE, DISLIKE (ANGRY), or IGNORE
                        action = generate_rule_based_read(agent.id, agent.cluster, target_post)
                        if action:  # Only add if not IGNORE
                            actions.append(action)
                
                elif action_type == "image":
                    # Stub: Image post action - agent creates a post with an image
                    # Future implementation: integrate with image generation
                    if agent_type == "llm":
                        future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
                        pending_llm_posts.append((agent.id, agent.cluster, future, None))
                    else:
                        action = generate_rule_based_post(agent.id, agent.cluster)
                        actions.append(action)
                
                elif action_type == "share_link":
                    # News sharing action - ONLY page agents can perform this action
                    # Page agents share news articles from their assigned RSS feed
                    # The feed must be associated with a Website that has the same ID as the page
                    self.logger.info(f"share_link action: agent={agent.username}, is_page={agent.is_page}, feed_url={agent.feed_url[:50] if agent.feed_url else None}, news_service={self.news_service is not None}")
                    
                    if agent.is_page != 1:
                        # Non-page agents cannot perform share_link action, skip
                        self.logger.warning(f"share_link skipped: {agent.username} is not a page agent")
                        continue
                    
                    if not agent.feed_url:
                        # Page without feed URL, skip
                        self.logger.warning(f"share_link skipped: {agent.username} has no feed_url")
                        continue
                    
                    if self.news_service:
                        # Get an article from this page's specific feed
                        # The feed is already registered with the page's ID as website_id
                        try:
                            self.logger.info(f"Page {agent.username} fetching article from {agent.feed_url[:50]}")
                            article_future = self.news_service.get_article_from_feed.remote(
                                agent.feed_url
                            )
                            article = ray.get(article_future)
                            
                            if article:
                                self.logger.info(f"Page {agent.username} got article: {article.get('title', 'NO TITLE')[:50]}")
                                
                                # Verify the article's website_id matches the page's user_id
                                # This ensures pages can only share from their own feeds
                                article_website_id = article.get("website_id")
                                # Both IDs should be UUID strings - normalize for comparison
                                if article_website_id:
                                    # Normalize both IDs to lowercase strings for comparison
                                    normalized_article_id = str(article_website_id).lower()
                                    normalized_agent_id = str(agent.id).lower()
                                    if normalized_article_id != normalized_agent_id:
                                        # Article is from a different website, skip
                                        self.logger.warning(
                                            f"Page {agent.username} attempted to share from wrong feed. "
                                            f"Page ID: {agent.id}, Article Website ID: {article_website_id}"
                                        )
                                        continue
                                
                                if agent_type == "llm":
                                    # LLM page posts news with commentary
                                    self.logger.info(f"LLM Page {agent.username} generating news post async")
                                    future, article_id = generate_news_post_async(
                                        self.news_service, self.llm, agent.cluster, article, agent.username
                                    )
                                    self.logger.info(f"LLM Page {agent.username} got article_id: {article_id}")
                                    pending_llm_posts.append((agent.id, agent.cluster, future, article_id))
                                else:
                                    # Rule-based page posts news directly
                                    self.logger.info(f"Rule-based Page {agent.username} generating news post")
                                    action, article_id = generate_rule_based_news_post(
                                        agent.id, agent.cluster, article, self.news_service
                                    )
                                    self.logger.info(f"Rule-based Page {agent.username} got article_id: {article_id}")
                                    # Store article_id with the action for later use when submitting
                                    action.article_id = article_id
                                    actions.append(action)
                            else:
                                # No article available from this feed, skip
                                self.logger.warning(f"Page {agent.username} got no article from feed")
                        except Exception as e:
                            # News service unavailable or error, skip action
                            self.logger.warning(f"Share link action failed for page {agent.username}: {e}")
                            import traceback
                            self.logger.warning(f"Traceback: {traceback.format_exc()}")
                    else:
                        # News service not configured, skip (pages can only share links)
                        self.logger.warning(f"share_link skipped: {agent.username} - news_service is None")
                        pass
                
                elif action_type == "share":
                    # Share action - agent shares an existing post
                    # Select a post from recent_posts to share
                    if recent_posts:
                        # For now, only rule-based agents share (LLM share can be added later)
                        if agent_type == "rule_based":
                            action = generate_rule_based_share(agent.id, agent.cluster, target)
                            actions.append(action)
                        # LLM share could generate commentary using LLM in the future
                    # If no posts available, skip
                
                elif action_type == "search":
                    # Stub: Search action - agent searches for content
                    # Future implementation: integrate with search functionality
                    pass
                
                elif action_type == "cast":
                    # Stub: Cast/broadcast action - agent broadcasts to wider audience
                    # Future implementation: special broadcast mechanism
                    if agent_type == "llm":
                        future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
                        pending_llm_posts.append((agent.id, agent.cluster, future, None))
                    else:
                        action = generate_rule_based_post(agent.id, agent.cluster)
                        actions.append(action)
        
        # --- GATHER PHASE: Wait for all LLM results in parallel ---
        
        self.logger.info(f"Gather phase: pending_llm_posts={len(pending_llm_posts)}, pending_llm_reactions={len(pending_llm_reactions)}, actions_so_far={len(actions)}")
        
        # Resolve Posts
        if pending_llm_posts:
            # Extract just the futures list to pass to ray.get
            futures = [p[2] for p in pending_llm_posts]
            results = ray.get(futures)  # Blocks once for ALL posts
            
            for i, res_txt in enumerate(results):
                a_id, cid, _, article_id = pending_llm_posts[i]
                action = ActionDTO(a_id, cid, "POST", content=res_txt)
                # Add article_id as attribute if present (for news posts)
                if article_id:
                    action.article_id = article_id
                    self.logger.info(f"LLM post for agent {a_id}: article_id={article_id}, content_len={len(res_txt)}")
                else:
                    self.logger.info(f"LLM post for agent {a_id}: NO article_id, content_len={len(res_txt)}")
                actions.append(action)
        
        # Resolve Reactions and Comments
        if pending_llm_reactions:
            futures = [r[3] for r in pending_llm_reactions]
            results = ray.get(futures)  # Blocks once for ALL reactions/comments
            
            for i, res_act in enumerate(results):
                a_id, cid, target, _ = pending_llm_reactions[i]
                # Check if result is a comment (text) or a reaction type
                if res_act and res_act.upper() not in REACTION_TYPES:
                    # This is a comment text from LLM
                    actions.append(ActionDTO(a_id, cid, "COMMENT", content=res_act, target_post_id=target))
                elif res_act.upper() != "IGNORE":
                    # This is a reaction type
                    actions.append(ActionDTO(a_id, cid, res_act, target_post_id=target))
        
        self.logger.info(f"Returning {len(actions)} total actions")
        return actions

    def shutdown(self):
        ray.get(self.server.deregister_client.remote(self.client_id))
