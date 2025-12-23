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
    generate_llm_follow_async,
    generate_rule_based_post,
    generate_rule_based_reaction,
    generate_rule_based_comment,
    generate_rule_based_share,
    generate_rule_based_read,
    generate_rule_based_follow,
    generate_news_post_async,
    generate_rule_based_news_post,
)
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.text_support.text_annotator import annotate_text
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
from YSimulator.YClient.recsys.FollowRecSysRay import (
    FollowRecSysRay,
    RandomFollowRecSys,
    CommonNeighborsFollowRecSys,
    JaccardFollowRecSys,
    AdamicAdarFollowRecSys,
    PreferentialAttachmentFollowRecSys
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

# Follow recommendation system class mapping
FOLLOW_RECSYS_CLASS_MAP = {
    "random": RandomFollowRecSys,
    "common_neighbors": CommonNeighborsFollowRecSys,
    "jaccard": JaccardFollowRecSys,
    "adamic_adar": AdamicAdarFollowRecSys,
    "preferential_attachment": PreferentialAttachmentFollowRecSys,
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
        
        # Load agent behavior configuration
        agents_config = simulation_config.get("agents", {})
        self.probability_of_secondary_follow = agents_config.get("probability_of_secondary_follow", 0.0)
        self.probability_of_daily_follow = agents_config.get("probability_of_daily_follow", 0.0)
        self.max_length_thread_reading = agents_config.get("max_length_thread_reading", 5)

        # Load text annotation configuration
        self.enable_sentiment = simulation_config["simulation"].get("enable_sentiment", False)
        self.enable_toxicity = simulation_config["simulation"].get("enable_toxicity", False)
        self.perspective_api_key = simulation_config["simulation"].get("perspective_api_key", None)

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
                    interests=agent_data.get("interests"),  # Interest topics and counts
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

    def _parse_network_edges(self, network_csv_path: Path) -> list:
        """
        Parse network.csv to extract edge tuples (follower_id, user_id).
        
        This is a lightweight parser used to check if the network has been loaded.
        It only extracts valid edges without creating database records or logging details.
        For the full loading process with detailed logging, see _load_and_create_social_network().
        
        Args:
            network_csv_path: Path to the network.csv file
            
        Returns:
            list: List of tuples (follower_id, user_id) representing edges
        """
        import csv
        
        if not network_csv_path.exists():
            return []
        
        # Create a mapping from username to agent ID for quick lookup
        username_to_id = {agent.username: str(agent.id) for agent in self.agent_profiles}
        
        edges = []
        
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
                    if follower_name not in username_to_id or user_name not in username_to_id:
                        continue
                    
                    # Get agent IDs
                    follower_id = username_to_id[follower_name]
                    user_id = username_to_id[user_name]
                    
                    edges.append((follower_id, user_id))
            
            return edges
            
        except Exception as e:
            self.logger.error(
                f"Error parsing network CSV: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return []

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
                    
                    # Get first round UUID from server (for initial network setup)
                    # We only need to fetch this once for all edges
                    if follow_count == 0:
                        try:
                            first_round_id = ray.get(self.server.get_first_round_id.remote())
                        except Exception as e:
                            self.logger.error(f"Error getting first round ID: {e}")
                            first_round_id = ""
                    
                    # Create follow relationship via server
                    # We use the server's method to insert follow data
                    # The round is set to first round UUID for initial network setup
                    follow_data = {
                        "follower_id": follower_id,
                        "user_id": user_id,
                        "action": "follow",
                        "round": first_round_id,  # First round UUID for initial network setup
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
        
        # Check if we should load the social network topology from network.csv
        # This works regardless of when the client joins (multi-client scenarios)
        # Try client-specific network file first, then fall back to generic
        network_csv_path = self.config_path / f"{self.client_id}_network.csv"
        if not network_csv_path.exists():
            network_csv_path = self.config_path / "network.csv"
        
        if network_csv_path.exists():
            # First, parse the network edges from CSV
            print(f"[{self.client_id}] Checking if social network needs to be loaded from {network_csv_path.name}...")
            edges = self._parse_network_edges(network_csv_path)
            
            if edges:
                # Ask server if any of these edges already exist in the database
                edges_exist = ray.get(self.server.check_network_edges_exist.remote(edges))
                
                if not edges_exist:
                    print(f"[{self.client_id}] Loading social network topology from {network_csv_path.name}...")
                    self._load_and_create_social_network(network_csv_path)
                else:
                    self.logger.info("Network already loaded (edges exist in database)")
                    print(f"[{self.client_id}] Social network already loaded, skipping")
            else:
                self.logger.warning(f"No valid edges found in {network_csv_path.name}")
        else:
            self.logger.info("No network.csv found, skipping social network creation")
        
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
        
        # Track active agents per day for daily follow evaluation
        current_day = start_day
        active_agents_today = set()  # Set of agent IDs active during current day

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
                actions, active_agent_ids = self._simulate(instruction.day, instruction.slot, instruction.recent_post_ids)
                sim_time = (time.time() - sim_start) * 1000
                
                # Track active agents for this day
                active_agents_today.update(active_agent_ids)
                
                # Check if this is the last slot of the day (end of day)
                is_last_slot = (instruction.slot == self.num_slots_per_day - 1)
                day_changed = (instruction.day != current_day)
                
                # Evaluate daily follows at the end of each day
                if (is_last_slot or day_changed) and self.probability_of_daily_follow > 0 and active_agents_today:
                    self.logger.info(f"End of day {current_day}: Evaluating daily follows for {len(active_agents_today)} active agents, probability={self.probability_of_daily_follow}")
                    daily_follow_actions = self._evaluate_daily_follows(active_agents_today, instruction.day)
                    if daily_follow_actions:
                        actions.extend(daily_follow_actions)
                        self.logger.info(f"Added {len(daily_follow_actions)} daily follow actions")
                    
                    # Reset for next day
                    active_agents_today = set()
                    current_day = instruction.day
                
                # At end of day, save updated agent interests from server
                if is_last_slot or day_changed:
                    try:
                        # Get updated interests from server
                        updated_interests = ray.get(self.server.get_updated_agent_interests.remote())
                        if updated_interests:
                            self._save_updated_agent_population(updated_interests)
                    except Exception as e:
                        self.logger.error(
                            f"Error saving updated agent interests: {e}",
                            extra={"extra_data": {"error": str(e)}}
                        )

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

    def _extract_agent_attrs(self, agent) -> dict:
        """
        Extract agent attributes for dynamic persona building.
        
        Args:
            agent: AgentProfile object
            
        Returns:
            dict: Agent attributes for persona template
        """
        # Sample a topic from agent's interests if available
        selected_topic = None
        topics, counts = self._validate_and_extract_interests(agent.interests)
        if topics and counts:
            # Weight topics by their interaction counts
            import random
            selected_topic = random.choices(topics, weights=counts, k=1)[0]
        
        return {
            "name": agent.username,
            "age": agent.age if agent.age else "unknown",
            "gender": agent.gender if agent.gender else "person",
            "nationality": agent.nationality if agent.nationality else "citizen",
            "profession": agent.profession if agent.profession else "individual",
            "political_leaning": agent.leaning if agent.leaning else "neutral",
            "oe": agent.oe if agent.oe else "average in openness",
            "co": agent.co if agent.co else "average in conscientiousness",
            "ex": agent.ex if agent.ex else "average in extraversion",
            "ag": agent.ag if agent.ag else "average in agreeableness",
            "ne": agent.ne if agent.ne else "average in neuroticism",
            "toxicity": agent.toxicity if agent.toxicity and agent.toxicity != "" else "no",
            "topic": selected_topic  # Include the sampled topic
        }
    
    def _save_updated_agent_population(self, updated_interests: dict):
        """
        Save updated agent interests to agent_population.json at end of day.
        Respects client-specific naming convention (e.g., client_1_agent_population.json).
        
        Args:
            updated_interests: Dict of {agent_id: {"topics": [...], "counts": [...]}}
        """
        # Find agent_population.json file using client-specific naming convention
        # Try client-specific file first, then fall back to generic
        client_specific_file = self.config_path / f"{self.client_id}_agent_population.json"
        generic_file = self.config_path / "agent_population.json"
        
        if client_specific_file.exists():
            agent_config_file = client_specific_file
        else:
            agent_config_file = generic_file
        
        if not agent_config_file.exists():
            self.logger.warning(
                f"Agent config file not found at {agent_config_file}, skipping interests update"
            )
            return
        
        try:
            # Load current agent_population.json
            with open(agent_config_file, 'r') as f:
                agent_data = json.load(f)
            
            # Update interests for each agent
            if "agents" in agent_data:
                for agent in agent_data["agents"]:
                    agent_id = agent.get("id")
                    if agent_id and str(agent_id) in updated_interests:
                        interests_data = updated_interests[str(agent_id)]
                        # Update the interests field with current topics and counts
                        agent["interests"] = [
                            interests_data["topics"],
                            interests_data["counts"]
                        ]
            
            # Write updated data back to file
            with open(agent_config_file, 'w') as f:
                json.dump(agent_data, f, indent=2)
            
            self.logger.info(
                f"Updated {agent_config_file.name} with current interests for {len(updated_interests)} agents"
            )
            
        except Exception as e:
            self.logger.error(
                f"Error updating agent population file: {e}",
                extra={"extra_data": {"error": str(e), "file": str(agent_config_file)}}
            )
    
    def _validate_and_extract_interests(self, interests):
        """
        Validate interests structure and extract topics and counts.
        
        Args:
            interests: Interest data in format [["Topic1", "Topic2"], [1, 2]]
            
        Returns:
            tuple: (topics, counts) or (None, None) if invalid
        """
        if not interests or not isinstance(interests, (list, tuple)) or len(interests) != 2:
            return None, None
        
        topics = interests[0]
        counts = interests[1]
        
        if not topics or not counts or not isinstance(topics, list) or not isinstance(counts, list):
            return None, None
        
        if len(topics) == 0:
            return None, None
        
        return topics, counts

    def _handle_post_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle post action for an agent."""
        if agent_type == "llm":
            # LLM: Fire off async call (don't wait for result yet)
            agent_attrs = self._extract_agent_attrs(agent)
            selected_topic = agent_attrs.get("topic")  # Get the sampled topic
            future = generate_llm_post_async(self.llm, agent.cluster, day, slot, agent_attrs)
            pending_llm_posts.append((agent.id, agent.cluster, future, selected_topic))
        else:
            # Rule-based: Execute immediately
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Annotate rule-based post
            if action.content:
                annotations = annotate_text(
                    action.content,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key
                )
                action.annotations = annotations
            actions.append(action)
    
    def _handle_comment_action(self, agent, agent_type, pending_llm_reactions, actions, rule_based_interactions):
        """Handle comment action for an agent."""
        # Use recsys to get recommended posts to comment on
        agent_recsys_mode = getattr(agent, 'recsys_type', None) or self.recsys_mode
        recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
        recsys = recsys_class(
            n_posts=self.recsys_n_posts
        )
        
        # Get recommended posts from server
        recommended_posts = recsys.get_recommendations(self.server, agent.id)
        
        if not recommended_posts:
            return  # No posts available to comment on
        
        # Select one post randomly from recommendations
        target_post = random.choice(recommended_posts)
        
        if agent_type == "llm":
            # LLM: Get the post content and ask for a comment
            post_data = ray.get(self.server.get_post.remote(target_post))
            if post_data:
                post_content = post_data.get("tweet", "")
                author_id = post_data.get("user_id")
                # Get author username
                author_name = "Someone"
                if author_id:
                    author_user = ray.get(self.server.get_user.remote(author_id))
                    if author_user:
                        author_name = author_user.get("username", "Someone")
                
                # Get thread context (preceding posts/comments in chronological order)
                thread_context = ray.get(self.server.get_thread_context.remote(target_post, self.max_length_thread_reading))
                
                # Fire off async LLM call to generate comment with agent attributes, author name, and thread context
                agent_attrs = self._extract_agent_attrs(agent)
                future = self.llm.generate_comment.remote(agent.cluster, post_content, agent_attrs, author_name, thread_context)
                pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Just comment "COMMENT"
            action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
            # Annotate rule-based comment
            if action.content:
                annotations = annotate_text(
                    action.content,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key
                )
                action.annotations = annotations
            actions.append(action)
            # Track for secondary follow (rule-based comment)
            post_data = ray.get(self.server.get_post.remote(target_post))
            if post_data:
                rule_based_interactions.append((agent.id, agent.cluster, post_data.get("user_id"), post_data.get("tweet", ""), False))
    
    def _handle_read_action(self, agent, agent_type, pending_llm_reactions, actions, rule_based_interactions):
        """Handle read action for an agent."""
        # Use recsys to get recommended posts
        agent_recsys_mode = getattr(agent, 'recsys_type', None) or self.recsys_mode
        recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
        recsys = recsys_class(
            n_posts=self.recsys_n_posts
        )
        
        # Get recommended posts from server
        recommended_posts = recsys.get_recommendations(self.server, agent.id)
        
        if not recommended_posts:
            return  # No posts available to read
        
        # Select one post randomly from recommendations
        target_post = random.choice(recommended_posts)
        
        if agent_type == "llm":
            # LLM: Get the post content and ask for a reaction decision
            post_data = ray.get(self.server.get_post.remote(target_post))
            if post_data:
                post_content = post_data.get("tweet", "")
                # Fire off async LLM call to decide reaction with agent attributes
                agent_attrs = self._extract_agent_attrs(agent)
                future = generate_llm_read_async(self.llm, agent.cluster, post_content, agent_attrs)
                pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Randomly choose LIKE, DISLIKE (ANGRY), or IGNORE
            action = generate_rule_based_read(agent.id, agent.cluster, target_post)
            if action:  # Only add if not IGNORE
                actions.append(action)
                # Track for secondary follow (rule-based read)
                post_data = ray.get(self.server.get_post.remote(target_post))
                if post_data:
                    rule_based_interactions.append((agent.id, agent.cluster, post_data.get("user_id"), post_data.get("tweet", ""), False))
    
    def _handle_follow_action(self, agent, agent_type, pending_llm_follows, actions):
        """Handle follow action for an agent."""
        # Use follow recsys to get suggested users
        agent_frecsys_mode = getattr(agent, 'frecsys_type', None) or "random"
        frecsys_class = FOLLOW_RECSYS_CLASS_MAP.get(agent_frecsys_mode, RandomFollowRecSys)
        frecsys = frecsys_class(n_neighbors=10, leaning_bias=1)
        
        # Get follow suggestions from server
        suggested_users = frecsys.get_follow_suggestions(self.server, agent.id)
        
        if not suggested_users:
            return  # No users available to follow
        
        if agent_type == "llm":
            # LLM: Ask to decide which user to follow
            future = generate_llm_follow_async(self.llm, agent.cluster, suggested_users)
            pending_llm_follows.append((agent.id, agent.cluster, future))
        else:
            # Rule-based: Randomly select one user to follow
            target_user = random.choice(suggested_users)
            action = generate_rule_based_follow(agent.id, agent.cluster, target_user)
            actions.append(action)
    
    def _handle_share_link_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle share_link action for page agents (news sharing)."""
        self.logger.info(f"share_link action: agent={agent.username}, is_page={agent.is_page}, feed_url={agent.feed_url[:50] if agent.feed_url else None}, news_service={self.news_service is not None}")
        
        if agent.is_page != 1:
            self.logger.warning(f"share_link skipped: {agent.username} is not a page agent")
            return
        
        if not agent.feed_url:
            self.logger.warning(f"share_link skipped: {agent.username} has no feed_url")
            return
        
        if not self.news_service:
            self.logger.warning(f"share_link skipped: {agent.username} - news_service is None")
            return
        
        # Get an article from this page's specific feed
        try:
            self.logger.info(f"Page {agent.username} fetching article from {agent.feed_url[:50]}")
            article_future = self.news_service.get_article_from_feed.remote(agent.feed_url)
            article = ray.get(article_future)
            
            if article:
                self.logger.info(f"Page {agent.username} got article: {article.get('title', 'NO TITLE')[:50]}")
                
                # Verify the article's website_id matches the page's user_id
                article_website_id = article.get("website_id")
                if article_website_id:
                    normalized_article_id = str(article_website_id).lower()
                    normalized_agent_id = str(agent.id).lower()
                    if normalized_article_id != normalized_agent_id:
                        self.logger.warning(
                            f"Page {agent.username} attempted to share from wrong feed. "
                            f"Page ID: {agent.id}, Article Website ID: {article_website_id}"
                        )
                        return
                
                if agent_type == "llm":
                    # LLM page posts news with commentary
                    self.logger.info(f"LLM Page {agent.username} generating news post async")
                    future, article_id = generate_news_post_async(
                        self.news_service, self.llm, agent.cluster, article, agent.username
                    )
                    self.logger.info(f"LLM Page {agent.username} got article_id: {article_id}")
                    
                    # Extract and store article topics after article is saved
                    if article_id:
                        try:
                            # Check if article already has topics (avoid duplicate extraction)
                            existing_topics = ray.get(self.server.get_article_topics.remote(article_id))
                            
                            if not existing_topics:
                                # Extract topics using LLM (client-side)
                                self.logger.info(f"Extracting topics for article {article_id}: {article.get('title', '')[:50]}...")
                                topics_future = self.llm.extract_topics_from_article.remote(
                                    article.get("title", ""),
                                    article.get("summary", "")
                                )
                                topic_names = ray.get(topics_future)
                                self.logger.info(f"LLM extracted topics: {topic_names}")
                                
                                if topic_names:
                                    # Store topics in database (server-side)
                                    topic_ids = ray.get(
                                        self.server.store_article_topics.remote(
                                            article_id,
                                            topic_names[:2]  # Up to 2 topics
                                        )
                                    )
                                    if topic_ids:
                                        self.logger.info(f"Stored {len(topic_ids)} topics for article {article_id}")
                            else:
                                self.logger.info(f"Article {article_id} already has {len(existing_topics)} topics")
                        except Exception as e:
                            self.logger.warning(f"Failed to extract/store topics for article {article_id}: {e}")
                            import traceback
                            self.logger.warning(f"Traceback: {traceback.format_exc()}")
                    
                    pending_llm_posts.append((agent.id, agent.cluster, future, article_id))
                else:
                    # Rule-based page posts news directly
                    self.logger.info(f"Rule-based Page {agent.username} generating news post")
                    action, article_id = generate_rule_based_news_post(
                        agent.id, agent.cluster, article, self.news_service
                    )
                    self.logger.info(f"Rule-based Page {agent.username} got article_id: {article_id}")
                    
                    # Extract and store article topics after article is saved
                    if article_id:
                        try:
                            # Check if article already has topics (avoid duplicate extraction)
                            existing_topics = ray.get(self.server.get_article_topics.remote(article_id))
                            
                            if not existing_topics:
                                # Extract topics using LLM (client-side)
                                self.logger.info(f"Extracting topics for article {article_id}: {article.get('title', '')[:50]}...")
                                topics_future = self.llm.extract_topics_from_article.remote(
                                    article.get("title", ""),
                                    article.get("summary", "")
                                )
                                topic_names = ray.get(topics_future)
                                self.logger.info(f"LLM extracted topics: {topic_names}")
                                
                                if topic_names:
                                    # Store topics in database (server-side)
                                    topic_ids = ray.get(
                                        self.server.store_article_topics.remote(
                                            article_id,
                                            topic_names[:2]  # Up to 2 topics
                                        )
                                    )
                                    if topic_ids:
                                        self.logger.info(f"Stored {len(topic_ids)} topics for article {article_id}")
                            else:
                                self.logger.info(f"Article {article_id} already has {len(existing_topics)} topics")
                        except Exception as e:
                            self.logger.warning(f"Failed to extract/store topics for article {article_id}: {e}")
                            import traceback
                            self.logger.warning(f"Traceback: {traceback.format_exc()}")
                    
                    action.article_id = article_id
                    # Annotate rule-based news post
                    if action.content:
                        annotations = annotate_text(
                            action.content,
                            enable_sentiment=self.enable_sentiment,
                            enable_toxicity=self.enable_toxicity,
                            perspective_api_key=self.perspective_api_key
                        )
                        action.annotations = annotations
                    actions.append(action)
            else:
                self.logger.warning(f"Page {agent.username} got no article from feed")
        except Exception as e:
            self.logger.warning(f"Share link action failed for page {agent.username}: {e}")
            import traceback
            self.logger.warning(f"Traceback: {traceback.format_exc()}")
    
    def _handle_share_action(self, agent, agent_type, target, actions):
        """Handle share action (reshare existing post)."""
        # For now, only rule-based agents share
        if agent_type == "rule_based" and target:
            action = generate_rule_based_share(agent.id, agent.cluster, target)
            actions.append(action)
    
    def _handle_image_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle image post action (stub for future image generation)."""
        if agent_type == "llm":
            future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
            pending_llm_posts.append((agent.id, agent.cluster, future, None))
        else:
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Annotate rule-based post
            if action.content:
                annotations = annotate_text(
                    action.content,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key
                )
                action.annotations = annotations
            actions.append(action)
    
    def _handle_cast_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle cast/broadcast action (stub for future broadcast mechanism)."""
        if agent_type == "llm":
            future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
            pending_llm_posts.append((agent.id, agent.cluster, future, None))
        else:
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Annotate rule-based post
            if action.content:
                annotations = annotate_text(
                    action.content,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key
                )
                action.annotations = annotations
            actions.append(action)
    
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
        # Each entry: (agent_id, cluster_id, future) for follows
        pending_llm_posts = []
        pending_llm_reactions = []
        pending_llm_follows = []
        
        # Track rule-based read/comment actions for secondary follow
        # Each entry: (agent_id, cluster_id, post_author_id, post_content, is_llm=False)
        rule_based_interactions = []
        
        # --- SCATTER PHASE: Select and dispatch actions ---
        for agent in active_agents:
            # Sample number of actions for this agent based on daily_activity_level
            # Page agents can perform at most 1 action (0 or 1)
            # Regular agents: Random from 1 to daily_activity_level (minimum 1)
            if agent.daily_activity_level <= 0:
                # Skip agents with 0 or negative activity level
                continue
            
            if agent.is_page == 1:
                # Page agents perform at most 1 action (0 or 1)
                # Use a probability-based decision: 50% chance to act
                num_actions = 1 if random.random() < 0.5 else 0
                if num_actions > 0:
                    self.logger.info(f"Page agent {agent.username} will perform 1 action")
                else:
                    self.logger.debug(f"Page agent {agent.username} will skip this round")
            else:
                # Regular agents perform 1 to daily_activity_level actions
                num_actions = random.randint(1, agent.daily_activity_level)
            
            for action_idx in range(num_actions):
                action_type, agent_type, target = self.__select_action(agent, recent_posts)
                
                if agent.is_page == 1:
                    self.logger.info(f"Page agent {agent.username} action {action_idx+1}/{num_actions}: type={action_type}, agent_type={agent_type}")
                
                # Dispatch to appropriate action handler
                if action_type == "post":
                    self._handle_post_action(agent, agent_type, day, slot, pending_llm_posts, actions)
                elif action_type == "comment":
                    self._handle_comment_action(agent, agent_type, pending_llm_reactions, actions, rule_based_interactions)
                elif action_type == "read":
                    self._handle_read_action(agent, agent_type, pending_llm_reactions, actions, rule_based_interactions)
                elif action_type == "follow":
                    self._handle_follow_action(agent, agent_type, pending_llm_follows, actions)
                elif action_type == "image":
                    self._handle_image_action(agent, agent_type, day, slot, pending_llm_posts, actions)
                elif action_type == "share_link":
                    self._handle_share_link_action(agent, agent_type, day, slot, pending_llm_posts, actions)
                elif action_type == "share":
                    self._handle_share_action(agent, agent_type, target, actions)
                elif action_type == "search":
                    # Stub: Search action - future implementation
                    pass
                elif action_type == "cast":
                    self._handle_cast_action(agent, agent_type, day, slot, pending_llm_posts, actions)
        
        # --- GATHER PHASE: Wait for all LLM results in parallel ---
        
        self.logger.info(f"Gather phase: pending_llm_posts={len(pending_llm_posts)}, pending_llm_reactions={len(pending_llm_reactions)}, pending_llm_follows={len(pending_llm_follows)}, actions_so_far={len(actions)}")
        
        # Gather LLM posts
        self._gather_pending_llm_posts(pending_llm_posts, actions)
        
        # Gather LLM reactions and track interactions for secondary follow
        secondary_follow_candidates = self._gather_pending_llm_reactions(pending_llm_reactions, actions)
        
        # Gather LLM follows
        self._gather_pending_llm_follows(pending_llm_follows, actions)
        
        # --- SECONDARY FOLLOW PHASE: Evaluate follow/unfollow for read/comment interactions ---
        self._process_secondary_follows(secondary_follow_candidates, rule_based_interactions, actions)
        
        self.logger.info(f"Returning {len(actions)} total actions, {len(active_agents)} active agents")
        return actions, {agent.id for agent in active_agents}
    
    def _gather_pending_llm_posts(self, pending_llm_posts: list, actions: list) -> None:
        """
        Gather and resolve all pending LLM post generation calls.
        
        Args:
            pending_llm_posts: List of (agent_id, cluster_id, future, topic_or_article_id) tuples
            actions: List to append resolved post actions to
        """
        if not pending_llm_posts:
            return
        
        # Extract futures and wait for all posts in parallel
        futures = [p[2] for p in pending_llm_posts]
        results = ray.get(futures)  # Blocks once for ALL posts
        
        for i, res_txt in enumerate(results):
            a_id, cid, _, topic_or_article = pending_llm_posts[i]
            action = ActionDTO(a_id, cid, "POST", content=res_txt)
            
            # Annotate the post text
            annotations = annotate_text(
                res_txt,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key
            )
            action.annotations = annotations
            
            # Check if the fourth element is an article_id (UUID format) or a topic (string)
            if topic_or_article:
                # Try to parse as UUID - if successful, it's an article_id
                try:
                    import uuid
                    uuid.UUID(topic_or_article)
                    action.article_id = topic_or_article
                    self.logger.info(f"LLM post for agent {a_id}: article_id={topic_or_article}, content_len={len(res_txt)}")
                except (ValueError, AttributeError):
                    # Not a valid UUID, treat as topic string
                    action.topic = topic_or_article
                    self.logger.info(f"LLM post for agent {a_id}: topic={topic_or_article}, content_len={len(res_txt)}")
            else:
                self.logger.info(f"LLM post for agent {a_id}: NO article_id/topic, content_len={len(res_txt)}")
            actions.append(action)
    
    def _gather_pending_llm_reactions(self, pending_llm_reactions: list, actions: list) -> list:
        """
        Gather and resolve all pending LLM reaction/comment generation calls.
        
        Args:
            pending_llm_reactions: List of (agent_id, cluster_id, target_post_id, future) tuples
            actions: List to append resolved reaction/comment actions to
            
        Returns:
            list: Secondary follow candidates [(agent_id, cluster_id, author_id, post_content, is_llm)]
        """
        secondary_follow_candidates = []
        
        if not pending_llm_reactions:
            return secondary_follow_candidates
        
        # Extract futures and wait for all reactions in parallel
        futures = [r[3] for r in pending_llm_reactions]
        results = ray.get(futures)  # Blocks once for ALL reactions/comments
        
        for i, res_act in enumerate(results):
            a_id, cid, target, _ = pending_llm_reactions[i]
            # Check if result is a comment (text) or a reaction type
            if res_act and res_act.upper() not in REACTION_TYPES:
                # This is a comment text from LLM
                # Annotate the comment text
                annotations = annotate_text(
                    res_act,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key
                )
                action = ActionDTO(a_id, cid, "COMMENT", content=res_act, target_post_id=target, annotations=annotations)
                actions.append(action)
                # Track for secondary follow (comment action)
                post_data = ray.get(self.server.get_post.remote(target))
                if post_data:
                    secondary_follow_candidates.append((a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True))
            elif res_act.upper() != "IGNORE":
                # This is a reaction type
                actions.append(ActionDTO(a_id, cid, res_act, target_post_id=target))
                # Track for secondary follow (read/reaction action)
                post_data = ray.get(self.server.get_post.remote(target))
                if post_data:
                    secondary_follow_candidates.append((a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True))
        
        return secondary_follow_candidates
    
    def _gather_pending_llm_follows(self, pending_llm_follows: list, actions: list) -> None:
        """
        Gather and resolve all pending LLM follow decision calls.
        
        Args:
            pending_llm_follows: List of (agent_id, cluster_id, future) tuples
            actions: List to append resolved follow actions to
        """
        if not pending_llm_follows:
            return
        
        # Extract futures and wait for all follow decisions in parallel
        futures = [f[2] for f in pending_llm_follows]
        results = ray.get(futures)  # Blocks once for ALL follow decisions
        
        for i, target_user in enumerate(results):
            a_id, cid, _ = pending_llm_follows[i]
            # LLM returns user_id to follow or None to skip
            if target_user:
                actions.append(ActionDTO(a_id, cid, "FOLLOW", target_user_id=target_user))
    
    def _process_secondary_follows(self, secondary_follow_candidates: list, rule_based_interactions: list, actions: list) -> None:
        """
        Process secondary follow/unfollow decisions for agents who interacted with content.
        
        This method handles the secondary follow pipeline where agents may decide to follow
        or unfollow content authors after reading or commenting on their posts.
        
        Args:
            secondary_follow_candidates: List of LLM agent interactions [(agent_id, cluster_id, author_id, post_content, is_llm)]
            rule_based_interactions: List of rule-based agent interactions (same format)
            actions: List to append follow/unfollow actions to
        """
        # Merge rule-based interactions into secondary follow candidates
        secondary_follow_candidates.extend(rule_based_interactions)
        
        if self.probability_of_secondary_follow <= 0 or not secondary_follow_candidates:
            return
        
        self.logger.info(f"Secondary follow phase: {len(secondary_follow_candidates)} candidates, probability={self.probability_of_secondary_follow}")
        
        # Process each candidate for secondary follow
        pending_secondary_follow_llm = []  # List of (agent_id, cluster_id, author_id, is_following, future)
        
        for agent_id, cluster_id, author_id, post_content, is_llm_agent in secondary_follow_candidates:
            # Skip if author is self
            if agent_id == author_id:
                continue
            
            # Decide whether to evaluate secondary follow based on probability
            if random.random() >= self.probability_of_secondary_follow:
                continue
            
            # Get current follow relationship status
            is_following = ray.get(self.server.check_follow_relationship.remote(agent_id, author_id))
            
            if is_llm_agent:
                # LLM-based: Ask LLM whether to follow/unfollow based on post content
                future = self.llm.generate_secondary_follow_decision.remote(
                    cluster_id, post_content, is_following
                )
                pending_secondary_follow_llm.append((agent_id, cluster_id, author_id, is_following, future))
            else:
                # Rule-based: Randomly decide to follow/unfollow
                decision = random.choice(["follow", "unfollow", "no_change"])
                
                if decision == "follow" and not is_following:
                    # Follow the author
                    actions.append(ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=author_id))
                elif decision == "unfollow" and is_following:
                    # Unfollow the author
                    actions.append(ActionDTO(agent_id, cluster_id, "UNFOLLOW", target_user_id=author_id))
        
        # Resolve LLM-based secondary follow decisions
        if pending_secondary_follow_llm:
            futures = [f[4] for f in pending_secondary_follow_llm]
            results = ray.get(futures)  # Blocks for all secondary follow decisions
            
            for i, decision in enumerate(results):
                agent_id, cluster_id, author_id, is_following, _ = pending_secondary_follow_llm[i]
                
                if decision == "follow" and not is_following:
                    # Follow the author
                    actions.append(ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=author_id))
                elif decision == "unfollow" and is_following:
                    # Unfollow the author
                    actions.append(ActionDTO(agent_id, cluster_id, "UNFOLLOW", target_user_id=author_id))
    
    def _evaluate_daily_follows(self, active_agent_ids: set, current_day: int) -> list:
        """
        Evaluate daily follow actions for agents that were active during the day.
        
        For each active agent, with probability_of_daily_follow, use the agent's
        follow recommendation system to suggest users and create a follow action.
        
        Args:
            active_agent_ids: Set of agent IDs that were active during the day
            current_day: Current simulation day
            
        Returns:
            list: List of ActionDTO objects for follow actions
        """
        daily_follow_actions = []
        
        # Get agent profiles for active agents
        active_agents = [agent for agent in self.agent_profiles if agent.id in active_agent_ids]
        
        for agent in active_agents:
            # With probability, evaluate follow action for this agent
            if random.random() > self.probability_of_daily_follow:
                continue
            
            # Get agent's follow recommendation strategy
            agent_frecsys_mode = getattr(agent, 'frecsys_type', None) or 'random'
            frecsys_class = FOLLOW_RECSYS_CLASS_MAP.get(agent_frecsys_mode, RandomFollowRecSys)
            
            # Initialize follow recsys
            frecsys = frecsys_class(
                n_neighbors=10,  # Request top 10 suggestions
                leaning_bias=1  # No political bias for daily follows (1 = neutral)
            )
            
            # Get follow suggestions from server
            try:
                follow_suggestions = frecsys.get_follow_suggestions(self.server, agent.id)
                
                if follow_suggestions:
                    # Randomly select one candidate to follow
                    target_user_id = random.choice(follow_suggestions)
                    
                    # Create follow action
                    action = ActionDTO(
                        agent.id,
                        agent.cluster,
                        "FOLLOW",
                        target_user_id=target_user_id
                    )
                    daily_follow_actions.append(action)
                    self.logger.debug(f"Daily follow: Agent {agent.id} will follow user {target_user_id}")
                    
            except Exception as e:
                self.logger.warning(f"Failed to get follow suggestions for agent {agent.id}: {e}")
        
        return daily_follow_actions

    def shutdown(self):
        ray.get(self.server.deregister_client.remote(self.client_id))
