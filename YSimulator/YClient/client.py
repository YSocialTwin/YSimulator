"""
YClient - Simulation Client for YSimulator.

This module contains the Ray remote actor that runs simulation clients,
managing agent behaviors and coordinating with the orchestrator server.
"""

import gzip
import json
import logging
import os
import random
import shutil
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import ray

from YSimulator.YClient.action_executor import ActionExecutorMixin
from YSimulator.YClient.action_generators import ActionContext, ActionGeneratorFactory
from YSimulator.YClient.actions import (
    generate_image_post_async,
    generate_llm_follow_async,
    generate_llm_post_async,
    generate_llm_reaction_async,
    generate_llm_read_async,
    generate_llm_reply_to_mention_async,
    generate_llm_search_action_async,
    generate_news_post_async,
    generate_rule_based_comment,
    generate_rule_based_follow,
    generate_rule_based_image_post,
    generate_rule_based_news_post,
    generate_rule_based_post,
    generate_rule_based_reaction,
    generate_rule_based_read,
    generate_rule_based_reply_to_mention,
    generate_rule_based_share,
)
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.recsys import (
    CommonInterests,
    CommonUserInterests,
    ContentRecSys,
    RandomOrder,
    ReverseChrono,
    ReverseChronoComments,
    ReverseChronoFollowers,
    ReverseChronoFollowersPopularity,
    ReverseChronoPopularity,
    SimilarUsersPosts,
    SimilarUsersReact,
)
from YSimulator.YClient.recsys.FollowRecSysRay import (
    AdamicAdarFollowRecSys,
    CommonNeighborsFollowRecSys,
    FollowRecSysRay,
    JaccardFollowRecSys,
    PreferentialAttachmentFollowRecSys,
    RandomFollowRecSys,
)
from YSimulator.YClient.text_support.text_annotator import annotate_text

# Constants
REACTION_TYPES = ["LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"]
# Basic reactions for rule-based agents (simple positive/negative responses)
BASIC_REACTIONS = ["LIKE", "ANGRY"]

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
    "default": ReverseChrono,  # Default to reverse chronological
}

# Follow recommendation system class mapping
FOLLOW_RECSYS_CLASS_MAP = {
    "random": RandomFollowRecSys,
    "common_neighbors": CommonNeighborsFollowRecSys,
    "jaccard": JaccardFollowRecSys,
    "adamic_adar": AdamicAdarFollowRecSys,
    "preferential_attachment": PreferentialAttachmentFollowRecSys,
    "default": CommonNeighborsFollowRecSys,  # Default to common neighbors algorithm
}


def compress_rotated_log(source: str, dest: str) -> None:
    """
    Compress a rotated log file using gzip.

    Args:
        source: Path to the source log file
        dest: Path to the destination compressed file
    """
    with open(source, "rb") as f_in:
        with gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)


@ray.remote
class SimulationClient(ActionExecutorMixin):
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

        # Store simulation config for logging configuration
        self.simulation_config = simulation_config if simulation_config else {}

        # Set up logging early so it's available for initialization methods
        self._setup_logging()

        # Load simulation configuration with defaults
        if simulation_config is None:
            simulation_config = {
                "simulation": {"num_days": 0, "num_slots_per_day": 24, "heartbeat_interval": 5}
            }

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
        self.agent_downcast = archetype_config.get("agent_downcast", False)

        # Load recommendation system configuration
        recsys_config = simulation_config["simulation"].get("recsys", {})
        self.recsys_mode = recsys_config.get("mode", "random")  # "random" or "rchrono"
        self.recsys_n_posts = recsys_config.get("n_posts", 5)

        # Load agent behavior configuration
        agents_config = simulation_config.get("agents", {})
        self.probability_of_secondary_follow = agents_config.get(
            "probability_of_secondary_follow", 0.0
        )
        self.probability_of_daily_follow = agents_config.get("probability_of_daily_follow", 0.0)
        self.max_length_thread_reading = agents_config.get("max_length_thread_reading", 5)

        # Load churn configuration
        churn_config = agents_config.get("churn", {})
        self.churn_enabled = churn_config.get("enabled", False)
        self.churn_probability = churn_config.get("churn_probability", 0.01)
        self.inactivity_threshold = churn_config.get("inactivity_threshold", 5)
        self.churn_percentage = churn_config.get("churn_percentage", 0.1)

        # Load new agents configuration
        new_agents_config = agents_config.get("new_agents", {})
        self.new_agents_enabled = new_agents_config.get("enabled", False)
        self.probability_new_agents = new_agents_config.get("probability_new_agents", 0.01)
        self.percentage_new_agents = new_agents_config.get("percentage_new_agents", 0.01)

        # Load text annotation configuration
        self.enable_sentiment = simulation_config["simulation"].get("enable_sentiment", False)
        self.enable_toxicity = simulation_config["simulation"].get("enable_toxicity", False)
        self.perspective_api_key = simulation_config["simulation"].get("perspective_api_key", None)
        self.enable_emotions = simulation_config["simulation"].get("emotion_annotation", False)

        # Cache for churned agents (refreshed after churn evaluation)
        self._churned_agents_cache = set()
        self._churned_agents_cache_valid = False

        # Create agents from configuration
        self.agent_profiles = []
        if agent_config:
            self.agent_profiles = self._create_agents_from_config(agent_config)

        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")

        # Register page agent feeds with news service
        if self.news_service:
            for agent in self.agent_profiles:
                if agent.is_page == 1 and agent.feed_url:
                    try:
                        ray.get(
                            self.news_service.register_page_feed.remote(
                                agent.feed_url, str(agent.id)
                            )
                        )
                    except Exception as e:
                        # Failed to register page feed, log and continue
                        self.logger.warning(
                            f"Failed to register feed for page {agent.username}: {e}"
                        )

        # Initialize action generator factory (Phase 1 refactoring - COMPLETED)
        # The framework is now the sole implementation (legacy handlers removed)
        self._action_generator_factory = None

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

    def _create_action_generator_factory(self, day: int, slot: int, recent_posts: list):
        """
        Create action generator factory for the current simulation context.

        This is part of Phase 1 refactoring to extract action generation logic
        into pluggable generators. The factory pattern enables clean separation
        of action generation from simulation orchestration.

        Args:
            day: Current simulation day
            slot: Current time slot
            recent_posts: List of recent post UUIDs for reactions

        Returns:
            ActionGeneratorFactory: Configured factory for generating actions
        """
        # Get current round_id for opinion dynamics tracking
        round_id = ray.get(self.server.get_current_round_id.remote())

        # Build action context with all dependencies
        context = ActionContext(
            day=day,
            slot=slot,
            recent_posts=recent_posts,
            server=self.server,
            logger=self.logger,
            client_id=self.client_id,
            round_id=round_id,
            llm=self.llm,
            news_service=self.news_service,
            activity_profiles=self.activity_profiles,
            actions_likelihood=self.actions_likelihood,
            recsys_settings={
                "recsys_mode": self.recsys_mode,
                "recsys_n_posts": self.recsys_n_posts,
                "max_length_thread_reading": self.max_length_thread_reading,
            },
            opinion_dynamics_config=(
                self.opinion_dynamics_config if hasattr(self, "opinion_dynamics_config") else None
            ),
            extract_agent_attrs_fn=self._extract_agent_attrs,
            annotate_action_fn=self._annotate_action_content,
            is_opinion_dynamics_enabled_fn=self._is_opinion_dynamics_enabled,
            map_opinion_to_group_fn=(
                self._map_opinion_to_group if hasattr(self, "_map_opinion_to_group") else None
            ),
            infer_page_agent_opinion_fn=(
                self._infer_page_agent_opinion
                if hasattr(self, "_infer_page_agent_opinion")
                else None
            ),
            get_opinions_for_post_fn=self._get_opinions_for_post,
            calculate_opinion_updates_fn=self._calculate_opinion_updates,
        )

        return ActionGeneratorFactory(context)

    def _setup_logging(self):
        """Set up JSON logging for the client actor with gzip compression."""
        # Get logging configuration
        logging_config = self.simulation_config.get("logging", {})
        enable_actor_log = logging_config.get("enable_actor_log", True)
        enable_client_log = logging_config.get("enable_client_log", True)

        log_dir = self.config_path / "logs"
        log_dir.mkdir(exist_ok=True)

        # Create logger
        self.logger = logging.getLogger(f"YSimulator.Client.{self.client_id}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Create file handler with JSON formatting (actor log)
        if enable_actor_log:
            log_file = log_dir / f"{self.client_id}_actor.log"
            handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )  # 10MB

            # Add compression for rotated files
            handler.rotator = compress_rotated_log
            handler.namer = lambda name: name + ".gz"

            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
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

        # Create action logger for individual agent actions (client log)
        self.action_logger = logging.getLogger(f"YSimulator.Client.{self.client_id}.Actions")
        self.action_logger.setLevel(logging.INFO)
        self.action_logger.handlers = []
        self.action_logger.propagate = False  # Don't propagate to parent logger

        if enable_client_log:
            action_log_file = log_dir / f"{self.client_id}_client.log"
            action_handler = RotatingFileHandler(
                action_log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )

            # Add compression for rotated files
            action_handler.rotator = compress_rotated_log
            action_handler.namer = lambda name: name + ".gz"

            class ActionFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    # Simple format for action logs: one JSON object per line
                    return record.getMessage()

            action_handler.setFormatter(ActionFormatter())
            self.action_logger.addHandler(action_handler)

        # Initialize tracking variables for hourly and daily summaries
        self.hourly_actions = []  # Track actions for current hour
        self.daily_actions = []  # Track actions for current day

    def _parse_activity_profiles(self, activity_profiles_config):
        """
        Parse activity profiles from configuration.
        Delegates to activity_selector module.
        """
        from YSimulator.YClient.activity_selector import parse_activity_profiles

        return parse_activity_profiles(activity_profiles_config, self.logger)

    def _sample_agents_by_archetype(self, available_agents, num_active):
        """
        Sample agents according to archetype distribution.
        Delegates to activity_selector module.
        """
        from YSimulator.YClient.activity_selector import sample_agents_by_archetype

        return sample_agents_by_archetype(
            available_agents, num_active, self.archetype_distribution, self.logger
        )

    def _create_agents_from_config(self, agent_config):
        """
        Create agent profiles from configuration.
        Delegates to agent_manager module.
        """
        from YSimulator.YClient.agent_manager import create_agents_from_config

        return create_agents_from_config(agent_config, self.logger)

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
            with open(network_csv_path, "r", encoding="utf-8") as csvfile:
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
                f"Error parsing network CSV: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    def _load_and_create_social_network(self, network_csv_path: Path) -> int:
        """
        Load social network topology from CSV file and create Follow records.

        This method reads a network.csv file where each row represents an edge
        in the social network as "agent1_name,agent2_name" and creates Follow
        records in the database using batch insertion for optimal performance.

        Args:
            network_csv_path: Path to the network.csv file

        Returns:
            int: Number of follow relationships created
        """
        import csv

        if not network_csv_path.exists():
            self.logger.info(
                f"No network.csv found at {network_csv_path}, skipping social network creation"
            )
            return 0

        self.logger.info(f"Loading social network from {network_csv_path}")

        # Create a mapping from username to agent ID for quick lookup
        username_to_id = {agent.username: str(agent.id) for agent in self.agent_profiles}

        # Get first round UUID from server (for initial network setup)
        # This is critical - we cannot proceed without a valid round ID
        def _log_round_id_error(error_msg: str = None):
            """Helper to log and print round ID error."""
            if error_msg:
                self.logger.error(error_msg, extra={"extra_data": {"error": error_msg}})
            self.logger.error(f" Cannot load network without valid round ID")
            return 0

        try:
            first_round_id = ray.get(self.server.get_first_round_id.remote())
            if not first_round_id:
                return _log_round_id_error(
                    "Failed to get first round ID from server (empty response)"
                )
        except Exception as e:
            return _log_round_id_error(f"Failed to get first round ID from server: {e}")

        follows_to_create = []
        skipped_count = 0

        try:
            with open(network_csv_path, "r", encoding="utf-8") as csvfile:
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

                    # Prepare follow relationship data
                    follow_data = {
                        "follower_id": follower_id,
                        "user_id": user_id,
                        "action": "follow",
                        "round": first_round_id,  # First round UUID for initial network setup
                    }
                    follows_to_create.append(follow_data)

            # Batch insert all follow relationships if any were collected
            follow_count = 0
            if follows_to_create:
                expected_count = len(follows_to_create)
                self.logger.info(
                    f"Batch inserting {expected_count} follow relationships",
                    extra={"extra_data": {"batch_size": expected_count}},
                )
                try:
                    follow_count = ray.get(
                        self.server.add_follow_relationships_batch.remote(
                            follows_to_create, client_id=self.client_id
                        )
                    )
                    if follow_count != expected_count:
                        self.logger.warning(
                            f"Batch insert returned {follow_count} but expected {expected_count}",
                            extra={
                                "extra_data": {
                                    "expected": expected_count,
                                    "actual": follow_count,
                                }
                            },
                        )
                except Exception as e:
                    self.logger.error(
                        f"Error creating follow relationships in batch (attempted {expected_count} relationships): {e}",
                        extra={"extra_data": {"error": str(e), "batch_size": expected_count}},
                    )
                    return 0

            self.logger.info(
                f"Social network loaded: {follow_count} relationships created, {skipped_count} skipped",
                extra={
                    "extra_data": {"follow_count": follow_count, "skipped_count": skipped_count}
                },
            )
            self.logger.info(
                f"[{self.client_id}] Social network loaded: {follow_count} follow relationships created"
            )

            return follow_count

        except Exception as e:
            self.logger.error(
                f"Error loading social network from {network_csv_path}: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return 0

    def run(self) -> None:
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
        self.logger.info(f" Registering {len(self.agent_profiles)} agents with server...")

        registration_result = ray.get(
            self.server.register_agents.remote(self.agent_profiles, client_id=self.client_id)
        )
        reg_time = (time.time() - start_time) * 1000

        self.logger.info(
            "Agents registered with server",
            extra={"extra_data": {**registration_result, "execution_time_ms": reg_time}},
        )
        self.logger.info(f" Agent registration complete: {registration_result}")

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
            self.logger.info(
                f"[{self.client_id}] Checking if social network needs to be loaded from {network_csv_path.name}..."
            )
            edges = self._parse_network_edges(network_csv_path)

            if edges:
                # Ask server if any of these edges already exist in the database
                edges_exist = ray.get(self.server.check_network_edges_exist.remote(edges))

                if not edges_exist:
                    self.logger.info(
                        f"[{self.client_id}] Loading social network topology from {network_csv_path.name}..."
                    )
                    self._load_and_create_social_network(network_csv_path)
                else:
                    self.logger.info("Network already loaded (edges exist in database)")
                    self.logger.info(f" Social network already loaded, skipping")
            else:
                self.logger.warning(f"No valid edges found in {network_csv_path.name}")
        else:
            self.logger.info("No network.csv found, skipping social network creation")

        # Calculate our personal max_day for local tracking
        # num_days=0 means infinite simulation
        max_day = start_day + self.num_days if self.num_days > 0 else float("inf")
        max_day_str = "∞" if max_day == float("inf") else str(max_day)

        self.logger.info(
            "Client registered with server",
            extra={
                "extra_data": {
                    "start_day": start_day,
                    "start_slot": start_slot,
                    "num_days": self.num_days,
                    "max_day": max_day,
                }
            },
        )
        self.logger.info(
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
                    self.logger.info(
                        f"[{self.client_id}] Completed {self.num_days} days "
                        f"(day {start_day} to {instruction.day - 1}). Total slots: {slot_count}"
                    )
                    break

                # Process Logic
                sim_start = time.time()
                actions, active_agent_ids = self._simulate(
                    instruction.day, instruction.slot, instruction.recent_post_ids
                )
                sim_time = (time.time() - sim_start) * 1000

                # Track active agents for this day
                active_agents_today.update(active_agent_ids)

                # Check if this is the last slot of the day (end of day)
                is_last_slot = instruction.slot == self.num_slots_per_day - 1
                day_changed = instruction.day != current_day

                # Evaluate daily follows at the end of each day
                if (
                    (is_last_slot or day_changed)
                    and self.probability_of_daily_follow > 0
                    and active_agents_today
                ):
                    self.logger.info(
                        f"End of day {current_day}: Evaluating daily follows for {len(active_agents_today)} active agents, probability={self.probability_of_daily_follow}"
                    )
                    daily_follow_actions = self._evaluate_daily_follows(
                        active_agents_today, instruction.day
                    )
                    if daily_follow_actions:
                        actions.extend(daily_follow_actions)
                        self.logger.info(f"Added {len(daily_follow_actions)} daily follow actions")

                    # Reset for next day
                    active_agents_today = set()
                    current_day = instruction.day

                # Evaluate churn at the end of each day
                if (is_last_slot or day_changed) and self.churn_enabled:
                    try:
                        self.logger.info(
                            f"End of day {current_day}: Evaluating churn (enabled={self.churn_enabled})"
                        )
                        churn_stats = self._evaluate_churn()
                        self.logger.info(
                            f"Churn evaluation complete: inactive={churn_stats['inactive_agents']}, candidates={churn_stats['candidates']}, churned={churn_stats['churned']}"
                        )
                        if churn_stats["churned"] > 0:
                            self.logger.info(
                                f"Churn evaluation: {churn_stats['churned']} agents churned out of {churn_stats['candidates']} candidates ({churn_stats['inactive_agents']} inactive)"
                            )
                            # Invalidate churned agents cache after new churns
                            self._churned_agents_cache_valid = False
                    except Exception as e:
                        self.logger.error(
                            f"Error evaluating churn: {e}",
                            extra={"extra_data": {"error": str(e)}},
                        )

                # Evaluate new agents at the end of each day
                if (is_last_slot or day_changed) and self.new_agents_enabled:
                    try:
                        self.logger.info(
                            f"End of day {current_day}: Evaluating new agents (enabled={self.new_agents_enabled})"
                        )
                        # Get current round_id from server
                        current_round_id = ray.get(self.server.get_current_round_id.remote())
                        new_agents_count = self._evaluate_new_agents(current_round_id)
                        self.logger.info(
                            f"New agents evaluation complete: {new_agents_count} agents added"
                        )
                        if new_agents_count > 0:
                            self.logger.info(
                                f"New agents evaluation: {new_agents_count} agents added to population"
                            )
                    except Exception as e:
                        self.logger.error(
                            f"Error evaluating new agents: {e}",
                            extra={"extra_data": {"error": str(e)}},
                        )

                # At end of day, save updated agent interests from server
                if is_last_slot or day_changed:
                    try:
                        # Get updated interests from server
                        updated_interests = ray.get(
                            self.server.get_updated_agent_interests.remote()
                        )
                        if updated_interests:
                            self._save_updated_agent_population(updated_interests)
                    except Exception as e:
                        self.logger.error(
                            f"Error saving updated agent interests: {e}",
                            extra={"extra_data": {"error": str(e)}},
                        )

                # Log individual actions before submission
                for action in actions:
                    # Get agent username from agent_id
                    agent_profile = next(
                        (a for a in self.agent_profiles if a.id == action.agent_id), None
                    )
                    agent_name = agent_profile.username if agent_profile else str(action.agent_id)

                    # Normalize action type to method name (lowercase)
                    method_name = action.action_type.lower()

                    # Estimate execution time based on simulation time divided by number of actions
                    # This is an approximation since we don't track individual action times
                    execution_time = (sim_time / 1000.0) / len(actions) if len(actions) > 0 else 0

                    # All actions that reach this point are considered successful
                    self._log_action(
                        agent_name,
                        method_name,
                        execution_time,
                        True,
                        instruction.day,
                        instruction.slot,
                    )

                # Log hourly summary after processing all actions for this slot
                self._log_hourly_summary(instruction.day, instruction.slot)

                # Log daily summary if this is the end of a day
                if is_last_slot:
                    self._log_daily_summary(instruction.day)

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

                self.logger.info(
                    f"[{self.client_id}] Day {instruction.day} Slot {instruction.slot} -> "
                    f"Submitted {len(actions)} actions."
                )

        finally:
            # Notify server that this client has completed all activities
            try:
                ray.get(self.server.complete_client.remote(self.client_id))
                self.logger.info("Notified server of completion")
                self.logger.info(f" Simulation complete. Server notified.")
            except Exception as e:
                self.logger.warning(
                    f"Failed to notify server of completion: {e}",
                    extra={"extra_data": {"error": str(e)}},
                )

    def _determine_agent_type(self, agent_profile: AgentProfile) -> str:
        """
        Determine the agent type (llm or rule_based) based on agent profile and downcast settings.

        Args:
            agent_profile: Agent profile containing behavior settings

        Returns:
            str: "llm" or "rule_based"
        """
        # Start with the agent's configured type
        agent_type = "llm" if agent_profile.llm else "rule_based"

        # Apply agent_downcast logic: if enabled, treat validator and explorer as rule-based
        if self.agent_downcast and agent_profile.archetype:
            archetype_lower = agent_profile.archetype.lower()
            if archetype_lower in ["validator", "explorer"]:
                agent_type = "rule_based"

        return agent_type

    def __select_action(self, agent_profile: AgentProfile, recent_posts: list) -> tuple:
        """
        Determine which action an agent should perform.
        Delegates to activity_selector module.
        """
        from YSimulator.YClient.activity_selector import select_action

        return select_action(
            agent_profile,
            recent_posts,
            self.actions_likelihood,
            self.logger,
        )

    def _extract_agent_attrs(self, agent) -> dict:
        """
        Extract agent attributes for dynamic persona building.
        Delegates to agent_manager module.
        """
        from YSimulator.YClient.agent_manager import extract_agent_attrs

        return extract_agent_attrs(
            agent,
            self._validate_and_extract_interests,
            self._is_opinion_dynamics_enabled,
            self._map_opinion_to_group,
        )

    def _save_updated_agent_population(self, updated_interests: dict):
        """
        Save updated agent interests to agent_population.json at end of day.
        Delegates to agent_manager module.
        """
        from YSimulator.YClient.agent_manager import save_updated_agent_population

        save_updated_agent_population(
            updated_interests,
            self.config_path,
            self.client_id,
            self.logger,
        )

    def _validate_and_extract_interests(self, interests):
        """
        Validate interests structure and extract topics and counts.
        Delegates to agent_manager module.
        """
        from YSimulator.YClient.agent_manager import validate_and_extract_interests

        return validate_and_extract_interests(interests)

    def _log_action(
        self,
        agent_name: str,
        method_name: str,
        execution_time_seconds: float,
        success: bool,
        day: int,
        slot: int,
    ):
        """
        Log an individual agent action in the standardized format.

        Args:
            agent_name: Name of the agent performing the action
            method_name: Type of action (post, comment, read, follow, etc.)
            execution_time_seconds: Time taken to execute the action
            success: Whether the action succeeded
            day: Current simulation day
            slot: Current simulation slot (hour)
        """
        # Get current timestamp in the required format
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "time": timestamp,
            "agent_name": agent_name,
            "method_name": method_name,
            "execution_time_seconds": round(execution_time_seconds, 4),
            "success": success,
        }

        # Log to action log file
        self.action_logger.info(json.dumps(log_entry))

        # Track for hourly/daily summaries
        action_info = {
            "method_name": method_name,
            "execution_time_seconds": execution_time_seconds,
            "success": success,
            "day": day,
            "slot": slot,
        }
        self.hourly_actions.append(action_info)
        self.daily_actions.append(action_info)

    def _log_hourly_summary(self, day: int, slot: int):
        """
        Log hourly summary with execution time statistics.

        Args:
            day: Simulation day that just ended
            slot: Simulation slot (hour) that just ended
        """
        if not self.hourly_actions:
            return

        total_time = sum(a["execution_time_seconds"] for a in self.hourly_actions)
        total_actions = len(self.hourly_actions)
        successful_actions = sum(1 for a in self.hourly_actions if a["success"])

        # Count actions by method
        method_counts = {}
        for action in self.hourly_actions:
            method = action["method_name"]
            method_counts[method] = method_counts.get(method, 0) + 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = {
            "time": timestamp,
            "summary_type": "hourly",
            "day": day,
            "slot": slot,
            "total_actions": total_actions,
            "successful_actions": successful_actions,
            "total_execution_time_seconds": round(total_time, 4),
            "average_execution_time_seconds": round(
                total_time / total_actions if total_actions > 0 else 0, 4
            ),
            "actions_by_method": method_counts,
        }

        self.action_logger.info(json.dumps(summary))

        # Reset hourly tracking
        self.hourly_actions = []

    def _log_daily_summary(self, day: int):
        """
        Log daily summary with execution time statistics.

        Args:
            day: Simulation day that just ended
        """
        if not self.daily_actions:
            return

        total_time = sum(a["execution_time_seconds"] for a in self.daily_actions)
        total_actions = len(self.daily_actions)
        successful_actions = sum(1 for a in self.daily_actions if a["success"])

        # Count actions by method
        method_counts = {}
        for action in self.daily_actions:
            method = action["method_name"]
            method_counts[method] = method_counts.get(method, 0) + 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = {
            "time": timestamp,
            "summary_type": "daily",
            "day": day,
            "total_actions": total_actions,
            "successful_actions": successful_actions,
            "total_execution_time_seconds": round(total_time, 4),
            "average_execution_time_seconds": round(
                total_time / total_actions if total_actions > 0 else 0, 4
            ),
            "actions_by_method": method_counts,
        }

        self.action_logger.info(json.dumps(summary))

        # Reset daily tracking
        self.daily_actions = []

    def _annotate_action_content(self, action: ActionDTO) -> None:
        """
        Annotate the content of an action with hashtags, mentions, sentiment, toxicity, and emotions.

        This helper method avoids code duplication when annotating rule-based posts and comments.
        Modifies the action in-place by setting its annotations field.

        Args:
            action: ActionDTO instance with content to annotate
        """
        if action.content:
            annotations = annotate_text(
                action.content,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=self.enable_emotions,
                llm_handle=self.llm,
            )
            action.annotations = annotations
            self.logger.info(
                f"Annotated action content: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}, hashtags={len(annotations.get('hashtags', []))}, mentions={len(annotations.get('mentions', []))}"
            )

    def _handle_reply_to_mention(self, agent, agent_type, pending_llm_reactions, actions):
        """
        Handle reply to mention for an agent.
        Uses the reply action generator framework for consistency.
        """
        # Use the reply generator via the action generator framework
        immediate_actions, pending_calls, metadata = self._dispatch_action_with_generator(
            "reply", agent, agent_type
        )
        
        # Add immediate actions (rule-based) to the actions list
        actions.extend(immediate_actions)
        
        # Add pending LLM calls to the pending_llm_reactions list
        pending_llm_reactions.extend(pending_calls)
        
        # Return mention_id if one was processed (for tracking)
        return metadata.get("mention_id")

    def _dispatch_action_with_generator(
        self, action_type: str, agent: AgentProfile, agent_type: str, target=None
    ) -> tuple:
        """
        Dispatch action using action generator framework.

        This method is part of Phase 1 refactoring. It provides a clean interface
        to generate actions using the new generator framework. The old _handle_*
        methods are gradually being replaced by this approach.

        Args:
            action_type: Type of action to generate (e.g., "post", "comment", "read")
            agent: Agent profile
            agent_type: "llm" or "rule_based"
            target: Optional target for the action (e.g., post UUID for reactions)

        Returns:
            tuple: (immediate_actions, pending_llm_calls, metadata)
                immediate_actions: List of ActionDTO objects to submit immediately
                pending_llm_calls: List of tuples for async LLM calls to gather later
                metadata: Dict with debugging/tracking information
        """
        # Check if action_type is None (can happen from activity_selector)
        if action_type is None:
            self.logger.debug(f"Action type is None for agent {agent.username}, skipping")
            return [], [], {"skipped": True, "reason": "action_type_none"}

        # Update the generator factory's context with target if provided
        if target:
            self._action_generator_factory.context.target = target

        # Get the appropriate generator for this action type
        try:
            generator = self._action_generator_factory.get_generator(action_type)
        except ValueError as e:
            self.logger.warning(f"No generator found for action type '{action_type}': {e}")
            return [], [], {"error": str(e)}

        # Check if generator can handle this agent
        if not generator.can_generate(agent, agent_type):
            self.logger.debug(
                f"Generator {generator.__class__.__name__} cannot generate for agent {agent.username}"
            )
            return [], [], {"skipped": True, "reason": "cannot_generate"}

        # Generate the action
        result = generator.generate(agent, agent_type)

        return result.actions, result.pending_llm_calls, result.metadata

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

        # Get list of churned agents from server to filter them out
        # Use cache to avoid expensive server calls on every simulation
        churned_agent_ids = set()
        if self.churn_enabled:
            try:
                # Refresh cache if invalid or empty
                if not self._churned_agents_cache_valid:
                    churned_agent_ids = set(ray.get(self.server.get_churned_agents.remote()))
                    self._churned_agents_cache = churned_agent_ids
                    self._churned_agents_cache_valid = True
                    if churned_agent_ids:
                        self.logger.info(
                            f"Refreshed churned agents cache: {len(churned_agent_ids)} churned agents"
                        )
                else:
                    # Use cached value
                    churned_agent_ids = self._churned_agents_cache
            except Exception as e:
                self.logger.warning(
                    f"Error getting churned agents: {e}", extra={"extra_data": {"error": str(e)}}
                )

        # Get hourly activity probability for this slot (default to 0.04 if not specified)
        hourly_prob = self.hourly_activity.get(slot, 0.04)

        # Separate regular agents and page agents
        # Pages are always active during their activity profile hours
        # Filter out churned agents
        regular_agents = []
        page_agents = []

        for agent in self.agent_profiles:
            # Skip churned agents
            if agent.id in churned_agent_ids:
                continue

            profile_name = agent.activity_profile
            active_hours = self.activity_profiles.get(profile_name, list(range(24)))
            if slot in active_hours:
                if agent.is_page == 1:
                    page_agents.append(agent)
                else:
                    regular_agents.append(agent)

        self.logger.info(
            f"Activity sampling: slot={slot}, regular_agents={len(regular_agents)}, page_agents={len(page_agents)}"
        )
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
                    active_regular_agents = self._sample_agents_by_archetype(
                        regular_agents, num_active
                    )
                else:
                    # Random sampling when archetypes are disabled
                    active_regular_agents = random.sample(regular_agents, k=num_active)

        # Combine regular agents and ALL page agents that are available
        active_agents = active_regular_agents + page_agents
        self.logger.info(
            f"Total active agents for this round: {len(active_agents)} (regular: {len(active_regular_agents)}, pages: {len(page_agents)})"
        )

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

        self.logger.info(f"[REPLY] Starting simulation for {len(active_agents)} active agents")

        # Initialize action generator factory (Phase 1 refactoring - consolidated)
        self._action_generator_factory = self._create_action_generator_factory(
            day, slot, recent_posts
        )

        # --- SCATTER PHASE: Select and dispatch actions ---
        for agent in active_agents:
            # Determine agent type (llm or rule_based) with agent_downcast logic
            agent_type = self._determine_agent_type(agent)

            # REPLY PIPELINE: Check for unreplied mentions and reply to one if present
            # This happens BEFORE the agent's normal actions
            # Page agents are excluded from reply pipeline
            self.logger.debug(
                f"[REPLY] Processing agent {agent.username} (type: {agent_type}, is_page: {agent.is_page})"
            )
            self._handle_reply_to_mention(agent, agent_type, pending_llm_reactions, actions)

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
                    self.logger.info(
                        f"Page agent {agent.username} action {action_idx+1}/{num_actions}: type={action_type}, agent_type={agent_type}"
                    )

                # Dispatch action using action generator framework
                immediate_actions, pending_calls, metadata = (
                    self._dispatch_action_with_generator(action_type, agent, agent_type, target)
                )

                # Add immediate actions
                actions.extend(immediate_actions)

                # Route pending LLM calls to appropriate lists
                # The structure of pending_calls depends on action type
                if action_type in ["post", "image", "cast", "share_link"]:
                    pending_llm_posts.extend(pending_calls)
                elif action_type in ["comment", "read", "search", "share"]:
                    pending_llm_reactions.extend(pending_calls)
                elif action_type == "follow":
                    pending_llm_follows.extend(pending_calls)

                # Track rule-based interactions if metadata indicates it
                if metadata.get("rule_based_interaction"):
                    rb_interaction = metadata["rule_based_interaction"]
                    # Need to fetch post data for secondary follow
                    post_data = ray.get(
                        self.server.get_post.remote(
                            rb_interaction["target_post"], client_id=self.client_id
                        )
                    )
                    if post_data:
                        rule_based_interactions.append(
                            (
                                rb_interaction["agent_id"],
                                rb_interaction["cluster_id"],
                                post_data.get("user_id"),
                                post_data.get("tweet", ""),
                                False,
                            )
                        )

        # --- GATHER PHASE: Wait for all LLM results in parallel ---

        self.logger.info(
            f"Gather phase: pending_llm_posts={len(pending_llm_posts)}, pending_llm_reactions={len(pending_llm_reactions)}, pending_llm_follows={len(pending_llm_follows)}, actions_so_far={len(actions)}"
        )

        # Gather LLM posts
        self._gather_pending_llm_posts(pending_llm_posts, actions)

        # Gather LLM reactions and track interactions for secondary follow
        secondary_follow_candidates = self._gather_pending_llm_reactions(
            pending_llm_reactions, actions
        )

        # Gather LLM follows
        self._gather_pending_llm_follows(pending_llm_follows, actions)

        # --- SECONDARY FOLLOW PHASE: Evaluate follow/unfollow for read/comment interactions ---
        self._process_secondary_follows(
            secondary_follow_candidates, rule_based_interactions, actions
        )

        self.logger.info(
            f"Returning {len(actions)} total actions, {len(active_agents)} active agents"
        )
        return actions, {agent.id for agent in active_agents}

    def _gather_pending_llm_posts(self, pending_llm_posts: list, actions: list) -> None:
        """
        Gather and resolve all pending LLM post generation calls.

        Args:
            pending_llm_posts: List of tuples:
                - (agent_id, cluster_id, future, topic_or_article_id) for regular/news posts
                - (agent_id, cluster_id, future, None, image_id, topic_ids) for image posts
            actions: List to append resolved post actions to
        """
        if not pending_llm_posts:
            return

        # Extract futures and wait for all posts in parallel
        futures = [p[2] for p in pending_llm_posts]
        results = ray.get(futures)  # Blocks once for ALL posts

        for i, res_txt in enumerate(results):
            pending_item = pending_llm_posts[i]
            a_id = pending_item[0]
            cid = pending_item[1]

            # Check if this is an image post (has 6 elements)
            if len(pending_item) == 6:
                # Image post: (agent_id, cluster_id, future, None, image_id, topic_ids)
                _, _, _, _, image_id, topic_ids = pending_item
                action = ActionDTO(a_id, cid, "POST", content=res_txt)
                action.image_id = image_id  # Set image_id as attribute
                action.topic_ids = topic_ids  # Store for later processing
                self.logger.info(
                    f"LLM image post for agent {a_id}: image_id={image_id}, has_image_id_attr={hasattr(action, 'image_id')}, topics={len(topic_ids)}, content_len={len(res_txt)}"
                )
            else:
                # Regular/news post: (agent_id, cluster_id, future, topic_or_article_id)
                topic_or_article = pending_item[3] if len(pending_item) > 3 else None
                action = ActionDTO(a_id, cid, "POST", content=res_txt)

                # Check if the fourth element is an article_id (UUID format) or a topic (string)
                if topic_or_article:
                    # Try to parse as UUID - if successful, it's an article_id
                    try:
                        import uuid

                        uuid.UUID(topic_or_article)
                        action.article_id = topic_or_article
                        self.logger.info(
                            f"LLM post for agent {a_id}: article_id={topic_or_article}, content_len={len(res_txt)}"
                        )
                    except (ValueError, AttributeError):
                        # Not a valid UUID, treat as topic string
                        action.topic = topic_or_article
                        self.logger.info(
                            f"LLM post for agent {a_id}: topic={topic_or_article}, content_len={len(res_txt)}"
                        )
                else:
                    self.logger.info(
                        f"LLM post for agent {a_id}: NO article_id/topic, content_len={len(res_txt)}"
                    )

            # Annotate the post text
            annotations = annotate_text(
                res_txt,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=self.enable_emotions,
                llm_handle=self.llm,
            )
            action.annotations = annotations
            self.logger.info(
                f"LLM post annotated for agent {a_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}, hashtags={len(annotations.get('hashtags', []))}, mentions={len(annotations.get('mentions', []))}"
            )

            actions.append(action)

    def _gather_pending_llm_reactions(self, pending_llm_reactions: list, actions: list) -> list:
        """
        Gather and resolve all pending LLM reaction/comment/share generation calls.

        Args:
            pending_llm_reactions: List of tuples:
                - (agent_id, cluster_id, target_post_id, future) for regular reactions/comments
                - (agent_id, cluster_id, target_post_id, future, mention_id) for replies to mentions
                - (agent_id, cluster_id, target_post_id, future, "SHARE") for share with commentary
            actions: List to append resolved reaction/comment/share actions to

        Returns:
            list: Secondary follow candidates [(agent_id, cluster_id, author_id, post_content, is_llm)]
        """
        secondary_follow_candidates = []

        if not pending_llm_reactions:
            return secondary_follow_candidates

        self.logger.info(
            f"[REPLY] Gathering {len(pending_llm_reactions)} pending LLM reactions/comments"
        )

        # Count how many are mention replies
        mention_replies = sum(1 for r in pending_llm_reactions if len(r) > 4)
        if mention_replies > 0:
            self.logger.info(f"[REPLY] {mention_replies} of these are mention replies")

        # Extract futures and wait for all reactions in parallel
        futures = [r[3] for r in pending_llm_reactions]
        results = ray.get(futures)  # Blocks once for ALL reactions/comments

        for i, res_act in enumerate(results):
            # Handle tuples of varying lengths:
            # 4-element: (agent_id, cluster_id, target_post_id, future) - regular comment/reaction
            # 5-element: (agent_id, cluster_id, target_post_id, future, mention_id_or_action_type)
            #   - If 5th element is a UUID string -> mention_id (reply to mention)
            #   - If 5th element is "SHARE" -> action_type (share with commentary)
            reaction_tuple = pending_llm_reactions[i]
            a_id = reaction_tuple[0]
            cid = reaction_tuple[1]
            target = reaction_tuple[2]

            # Check 5th element: mention_id or action_type
            mention_id = None
            action_type_override = None
            if len(reaction_tuple) > 4:
                fifth_element = reaction_tuple[4]
                # Check if it's a UUID (mention_id) or action type string
                if fifth_element == "SHARE":
                    action_type_override = "SHARE"
                else:
                    # Assume it's a mention_id (UUID or other identifier)
                    mention_id = fifth_element

            # Check if result is a comment/share commentary (text) or a reaction type
            if res_act and res_act.upper() not in REACTION_TYPES:
                # This is comment/share commentary text from LLM
                # Determine action type: SHARE (with commentary) or COMMENT
                determined_action_type = action_type_override if action_type_override else "COMMENT"

                self.logger.debug(
                    f"[REPLY] LLM generated {determined_action_type} for agent {a_id}: '{res_act[:50]}...' (is_mention_reply: {mention_id is not None})"
                )

                # Annotate the text
                annotations = annotate_text(
                    res_act,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key,
                    enable_emotions=self.enable_emotions,
                    llm_handle=self.llm,
                )
                self.logger.info(
                    f"LLM {determined_action_type} annotated for agent {a_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}, hashtags={len(annotations.get('hashtags', []))}, mentions={len(annotations.get('mentions', []))}"
                )

                # Calculate opinion updates
                post_data = ray.get(self.server.get_post.remote(target, client_id=self.client_id))
                updated_opinions = None
                if post_data:
                    updated_opinions = self._calculate_opinion_updates(a_id, target, post_data)

                action = ActionDTO(
                    a_id,
                    cid,
                    determined_action_type,
                    content=res_act,
                    target_post_id=target,
                    annotations=annotations,
                    updated_opinions=updated_opinions,
                )
                actions.append(action)

                # If this was a reply to a mention, mark it as replied
                if mention_id:
                    self.logger.info(
                        f"[REPLY] Marking mention {mention_id} as replied for agent {a_id}"
                    )
                    ray.get(self.server.mark_mention_replied.remote(mention_id))
                    self.logger.info(
                        f"[REPLY] Successfully marked mention {mention_id} as replied (LLM)"
                    )

                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
            elif res_act.upper() != "IGNORE":
                # This is a reaction type (or SHARE)
                self.logger.debug(f"[REPLY] LLM generated reaction for agent {a_id}: {res_act}")

                # Special handling for SHARE - generate share commentary
                if res_act.upper() == "SHARE":
                    # For SHARE actions, use cluster-specific share content (similar to rule-based)
                    share_content = f"Sharing from cluster {cid}"
                    # Calculate opinion updates for the share
                    post_data = ray.get(
                        self.server.get_post.remote(target, client_id=self.client_id)
                    )
                    updated_opinions = None
                    if post_data:
                        updated_opinions = self._calculate_opinion_updates(a_id, target, post_data)

                    action = ActionDTO(
                        a_id,
                        cid,
                        res_act.upper(),
                        content=share_content,
                        target_post_id=target,
                        updated_opinions=updated_opinions,
                    )
                    self.logger.info(
                        f"search action: LLM agent {a_id} decided to SHARE with content",
                        extra={
                            "extra_data": {
                                "agent_id": a_id,
                                "action_type": "SHARE",
                                "target_post_id": target,
                            }
                        },
                    )
                    # Track for secondary follow (share action)
                    if post_data:
                        secondary_follow_candidates.append(
                            (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                        )
                else:
                    # Regular reaction (LIKE, LOVE, LAUGH, ANGRY, SAD)
                    action = ActionDTO(a_id, cid, res_act, target_post_id=target)
                    # Track for secondary follow (read/reaction action)
                    post_data = ray.get(
                        self.server.get_post.remote(target, client_id=self.client_id)
                    )
                    if post_data:
                        secondary_follow_candidates.append(
                            (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                        )

                actions.append(action)
            else:
                # IGNORE action - log for search action context
                self.logger.debug(
                    f"LLM agent {a_id} chose to IGNORE post {target}",
                    extra={
                        "extra_data": {
                            "agent_id": a_id,
                            "action_type": "IGNORE",
                            "target_post_id": target,
                        }
                    },
                )

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

    def _calculate_opinion_updates(
        self, agent_id: str, parent_post_id: str, parent_post_data: dict
    ) -> Optional[dict]:
        """
        Calculate opinion updates when an agent comments on a post.

        Supports two opinion dynamics models based on simulation_config:
        - "bounded_confidence": Classic bounded confidence model (all agents)
        - "llm_evaluation": LLM-based evaluation (LLM agents only)

        Args:
            agent_id: UUID of the agent making the comment
            parent_post_id: UUID of the post being commented on
            parent_post_data: Dictionary containing post data including user_id

        Returns:
            dict: Mapping of topic_id to new opinion value, or None if no updates
        """
        try:
            # Check if opinion dynamics is enabled
            if not self._is_opinion_dynamics_enabled():
                return None

            # Get opinion dynamics config
            opinion_config = self.simulation_config.get("opinion_dynamics", {})
            if not opinion_config:
                return None

            # Get model name and parameters
            model_name = opinion_config.get("model_name", "bounded_confidence")
            params = opinion_config.get("parameters", {})

            # Validate model selection
            if model_name == "llm_evaluation":
                # Check if this is an LLM agent
                agent_profile = next((a for a in self.agent_profiles if a.id == agent_id), None)
                if not agent_profile or not agent_profile.llm:
                    self.logger.error(
                        f"llm_evaluation model can only be used with LLM agents. "
                        f"Agent {agent_id} is not an LLM agent. Skipping opinion update."
                    )
                    return None

            # Get the parent post author
            parent_author_id = parent_post_data.get("user_id")
            if not parent_author_id:
                return None

            # Get the post topics from server
            topic_ids = ray.get(
                self.server.get_post_topics.remote(parent_post_id, client_id=self.client_id)
            )
            if not topic_ids:
                return None

            # Get post content (needed for LLM evaluation)
            post_content = parent_post_data.get("tweet", "")

            # Calculate updated opinions for each topic
            updated_opinions = {}
            for topic_id in topic_ids:
                # Get topic name
                topic_name = ray.get(
                    self.server.get_topic_name_from_id.remote(topic_id, client_id=self.client_id)
                )
                if not topic_name:
                    continue

                # Get agent's LATEST opinion from database (not cached profile)
                # This ensures we use the most recent opinion after interactions
                agent_opinion = ray.get(
                    self.server.get_latest_agent_opinion.remote(
                        agent_id, topic_id, client_id=self.client_id
                    )
                )

                # Get author's latest opinion from server
                author_opinion = ray.get(
                    self.server.get_latest_agent_opinion.remote(
                        parent_author_id, topic_id, client_id=self.client_id
                    )
                )

                # Check if author has opinion on topic
                # If not, this is expected - opinion will be created during interaction
                # The opinion dynamics model will handle cold_start properly
                if author_opinion is None:
                    self.logger.debug(
                        f"Author {parent_author_id} has no opinion yet on topic '{topic_name}' "
                        f"(topic_id: {topic_id}) in their post {parent_post_id}. "
                        f"Opinion will be created during this interaction with cold_start strategy. "
                        f"Skipping opinion update calculation for now."
                    )
                    continue

                # Calculate new opinion based on selected model
                if model_name == "llm_evaluation":
                    # Use LLM-based evaluation
                    from YSimulator.YClient.opinion_dynamics.llm_evaluation import llm_evaluation

                    # Get evaluation scope and prepare neighbors' opinions if needed
                    evaluation_scope = params.get("evaluation_scope", "interlocutor_only")
                    peers_opinions = None

                    if evaluation_scope == "neighbors":
                        # Get neighbors' opinions from server
                        neighbor_opinion_values = ray.get(
                            self.server.get_neighbors_opinions.remote(
                                agent_id, topic_id, client_id=self.client_id
                            )
                        )

                        if neighbor_opinion_values:
                            # Convert to opinion labels and count occurrences
                            from collections import Counter

                            from YSimulator.YClient.opinion_dynamics.utils import get_opinion_group

                            opinion_groups = opinion_config.get("opinion_groups", {})
                            neighbor_labels = [
                                get_opinion_group(val, opinion_groups)
                                for val in neighbor_opinion_values
                            ]
                            peers_opinions = list(Counter(neighbor_labels).items())

                    # Calculate new opinion using LLM evaluation
                    new_opinion = llm_evaluation(
                        x=agent_opinion,
                        y=author_opinion,
                        text=post_content,
                        topic=topic_name,
                        evaluation_scope=evaluation_scope,
                        cold_start=params.get("cold_start", "neutral"),
                        group_classes=opinion_config.get("opinion_groups", {}),
                        peers_opinions=peers_opinions,
                        llm_service=self.llm,
                    )
                else:
                    # Use bounded confidence model (default)
                    from YSimulator.YClient.opinion_dynamics.confidence_bound import (
                        bounded_confidence,
                    )

                    new_opinion = bounded_confidence(
                        x=agent_opinion,
                        y=author_opinion,
                        epsilon=params.get("epsilon", 0.25),
                        mu=params.get("mu", 0.5),
                        theta=params.get("theta", 0.0),
                        cold_start=params.get("cold_start", "neutral"),
                    )

                updated_opinions[topic_id] = new_opinion

                self.logger.info(
                    f"Opinion update calculated (model={model_name}): agent={agent_id}, "
                    f"topic={topic_name}, old={agent_opinion}, author={author_opinion}, new={new_opinion}"
                )

            return updated_opinions if updated_opinions else None

        except Exception as e:
            self.logger.error(
                f"Error calculating opinion updates for agent {agent_id}: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id}},
            )
            return None

    def _map_opinion_to_group(self, opinion_value: float) -> str:
        """
        Map a numeric opinion value to a discrete opinion group label.

        Args:
            opinion_value: Numeric opinion in [0, 1]

        Returns:
            str: Opinion group label from simulation_config opinion_groups
        """
        opinion_config = self.simulation_config.get("opinion_dynamics", {})
        opinion_groups = opinion_config.get("opinion_groups", {})

        if not opinion_groups:
            # Default mapping if not configured
            if opinion_value < 0.2:
                return "Strongly against"
            elif opinion_value < 0.4:
                return "Against"
            elif opinion_value < 0.6:
                return "Neutral"
            elif opinion_value < 0.8:
                return "In favor"
            else:
                return "Strongly in favor"

        # Find which group the opinion falls into
        for group_name, (lower, upper) in opinion_groups.items():
            if lower <= opinion_value <= upper:
                return group_name

        # Fallback
        return "Neutral"

    def _is_opinion_dynamics_enabled(self) -> bool:
        """
        Check if opinion dynamics is enabled in the simulation configuration.

        Returns:
            bool: True if opinion dynamics is enabled, False otherwise
        """
        opinion_config = self.simulation_config.get("opinion_dynamics", {})
        return opinion_config.get("enabled", False)

    def _infer_page_agent_opinion(
        self, agent_id: str, article_content: str, topic_name: str
    ) -> float:
        """
        Infer opinion for a page agent on a topic from article content.

        This method is called CLIENT-SIDE before submitting article posts.
        - LLM page agents: Use LLM service to infer opinion from article
        - Rule-based page agents: Generate random opinion

        Args:
            agent_id: Agent UUID
            article_content: Article text to analyze
            topic_name: Topic to infer opinion about

        Returns:
            float: Opinion value in [0, 1] range
        """
        try:
            # Get agent profile to determine if LLM or rule-based
            agent_profile = next((a for a in self.agent_profiles if a.id == agent_id), None)
            if not agent_profile:
                self.logger.warning(f"Agent profile not found for {agent_id}, using random opinion")
                return random.random()

            # Check if this is an LLM agent
            if agent_profile.llm:
                # LLM page agent: infer opinion from article content using LLM service
                opinion_config = self.simulation_config.get("opinion_dynamics", {})
                opinion_groups = opinion_config.get("opinion_groups", {})

                if not opinion_groups:
                    self.logger.warning("No opinion_groups configured, using random opinion")
                    return random.random()

                # Call LLM service to infer opinion
                opinion_value = ray.get(
                    self.llm.infer_article_opinion.remote(
                        article_content, topic_name, opinion_groups
                    )
                )
                self.logger.info(
                    f"LLM page agent {agent_id}: inferred opinion {opinion_value} "
                    f"on topic '{topic_name}' from article content"
                )
                return opinion_value
            else:
                # Rule-based page agent: random opinion
                opinion_value = random.random()
                self.logger.info(
                    f"Rule-based page agent {agent_id}: assigned random opinion {opinion_value} "
                    f"on topic '{topic_name}'"
                )
                return opinion_value

        except Exception as e:
            self.logger.error(
                f"Error inferring opinion for page agent {agent_id}: {e}. Using random value."
            )
            return random.random()

    def _get_opinions_for_post(self, agent_id: str, post_id: str) -> dict:
        """
        Get agent's opinions on the topics discussed in a post.

        Args:
            agent_id: UUID of the agent
            post_id: UUID of the post

        Returns:
            dict: {
                "topics": List of topic names,
                "opinions": Dict mapping topic names to opinion labels,
                "opinion_values": Dict mapping topic names to numeric values
            }
        """
        try:
            # Check if opinion dynamics is enabled
            if not self._is_opinion_dynamics_enabled():
                return {"topics": [], "opinions": {}, "opinion_values": {}}

            # Get agent profile
            agent_profile = next((a for a in self.agent_profiles if a.id == agent_id), None)
            if not agent_profile or not agent_profile.opinions:
                return {"topics": [], "opinions": {}, "opinion_values": {}}

            # Get post topics
            topic_ids = ray.get(
                self.server.get_post_topics.remote(post_id, client_id=self.client_id)
            )
            if not topic_ids:
                return {"topics": [], "opinions": {}, "opinion_values": {}}

            # For each topic, get the agent's opinion
            topics = []
            opinions = {}
            opinion_values = {}

            for topic_id in topic_ids:
                # Get topic name
                topic_name = ray.get(
                    self.server.get_topic_name_from_id.remote(topic_id, client_id=self.client_id)
                )
                if not topic_name:
                    continue

                # Get agent's opinion on this topic
                if topic_name in agent_profile.opinions:
                    opinion_value = agent_profile.opinions[topic_name]
                    opinion_label = self._map_opinion_to_group(opinion_value)

                    topics.append(topic_name)
                    opinions[topic_name] = opinion_label
                    opinion_values[topic_name] = opinion_value

            return {"topics": topics, "opinions": opinions, "opinion_values": opinion_values}
        except Exception as e:
            self.logger.error(
                f"Error getting opinions for post {post_id}: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "post_id": post_id}},
            )
            return {"topics": [], "opinions": {}, "opinion_values": {}}

    def _process_secondary_follows(
        self, secondary_follow_candidates: list, rule_based_interactions: list, actions: list
    ) -> None:
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

        self.logger.info(
            f"Secondary follow phase: {len(secondary_follow_candidates)} candidates, probability={self.probability_of_secondary_follow}"
        )

        # Process each candidate for secondary follow
        pending_secondary_follow_llm = (
            []
        )  # List of (agent_id, cluster_id, author_id, is_following, future)

        for (
            agent_id,
            cluster_id,
            author_id,
            post_content,
            is_llm_agent,
        ) in secondary_follow_candidates:
            # Skip if author is self
            if agent_id == author_id:
                continue

            # Decide whether to evaluate secondary follow based on probability
            if random.random() >= self.probability_of_secondary_follow:
                continue

            # Get current follow relationship status
            is_following = ray.get(
                self.server.check_follow_relationship.remote(agent_id, author_id)
            )

            if is_llm_agent:
                # LLM-based: Ask LLM whether to follow/unfollow based on post content
                future = self.llm.generate_secondary_follow_decision.remote(
                    cluster_id, post_content, is_following
                )
                pending_secondary_follow_llm.append(
                    (agent_id, cluster_id, author_id, is_following, future)
                )
            else:
                # Rule-based: Randomly decide to follow/unfollow
                decision = random.choice(["follow", "unfollow", "no_change"])

                if decision == "follow" and not is_following:
                    # Follow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=author_id)
                    )
                elif decision == "unfollow" and is_following:
                    # Unfollow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "UNFOLLOW", target_user_id=author_id)
                    )

        # Resolve LLM-based secondary follow decisions
        if pending_secondary_follow_llm:
            futures = [f[4] for f in pending_secondary_follow_llm]
            results = ray.get(futures)  # Blocks for all secondary follow decisions

            for i, decision in enumerate(results):
                agent_id, cluster_id, author_id, is_following, _ = pending_secondary_follow_llm[i]

                if decision == "follow" and not is_following:
                    # Follow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=author_id)
                    )
                elif decision == "unfollow" and is_following:
                    # Unfollow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "UNFOLLOW", target_user_id=author_id)
                    )

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
            agent_frecsys_mode = getattr(agent, "frecsys_type", None) or "random"
            frecsys_class = FOLLOW_RECSYS_CLASS_MAP.get(agent_frecsys_mode, RandomFollowRecSys)

            # Initialize follow recsys
            frecsys = frecsys_class(
                n_neighbors=10,  # Request top 10 suggestions
                leaning_bias=1,  # No political bias for daily follows (1 = neutral)
            )

            # Get follow suggestions from server
            try:
                follow_suggestions = frecsys.get_follow_suggestions(
                    self.server, agent.id, client_id=self.client_id
                )

                if follow_suggestions:
                    # Randomly select one candidate to follow
                    target_user_id = random.choice(follow_suggestions)

                    # Create follow action
                    action = ActionDTO(
                        agent.id, agent.cluster, "FOLLOW", target_user_id=target_user_id
                    )
                    daily_follow_actions.append(action)
                    self.logger.debug(
                        f"Daily follow: Agent {agent.id} will follow user {target_user_id}"
                    )

            except Exception as e:
                self.logger.warning(f"Failed to get follow suggestions for agent {agent.id}: {e}")

        return daily_follow_actions

    def _evaluate_churn(self) -> dict[str, int]:
        """
        Evaluate and process churn at the end of a day (client-side).
        Delegates to churn_manager module.
        """
        from YSimulator.YClient.churn_manager import evaluate_churn

        return evaluate_churn(
            self.server,
            self.client_id,
            self.agent_profiles,
            self.churn_enabled,
            self.churn_probability,
            self.inactivity_threshold,
            self.churn_percentage,
            self.logger,
        )

    def _add_agent_to_population_file(self, agent: AgentProfile):
        """
        Add a new agent to the agent_population.json file.
        Delegates to agent_manager module.
        """
        from YSimulator.YClient.agent_manager import add_agent_to_population_file

        add_agent_to_population_file(
            agent,
            self.config_path,
            self.client_id,
            self.logger,
        )

    def _evaluate_new_agents(self, current_round_id: str) -> int:
        """
        Evaluate and create new agents at end of day.

        Creates new agents by:
        1. Calculating available slots based on non-churned population
        2. For each slot, rolling probability to create agent
        3. Selecting random template from existing agents
        4. Generating realistic name with Faker
        5. Batch registering with server
        6. Updating agent_population.json

        Args:
            current_round_id: Current round UUID

        Returns:
            int: Number of new agents created
        """
        if not self.new_agents_enabled:
            return 0

        try:
            import uuid

            from faker import Faker

            # Count non-churned agents
            non_churned_agents = [a for a in self.agent_profiles if a.left_on is None]
            num_non_churned = len(non_churned_agents)

            # Calculate available slots
            num_slots = int(num_non_churned * self.percentage_new_agents)

            if num_slots == 0:
                self.logger.info("No new agent slots available")
                return 0

            # Roll probability for each slot
            new_agents = []
            fake = Faker()
            existing_usernames = {a.username for a in self.agent_profiles}

            for _ in range(num_slots):
                if random.random() < self.probability_new_agents:
                    # Select random template
                    template = random.choice(non_churned_agents)

                    # Generate name based on template gender
                    gender = getattr(template, "gender", "male")
                    max_attempts = 10
                    for attempt in range(max_attempts):
                        if gender == "female":
                            name = fake.name_female()
                        else:
                            name = fake.name_male()

                        # Convert to username format
                        username = name.replace(" ", "_").replace(".", "_")

                        if username not in existing_usernames:
                            break
                    else:
                        # Fallback with UUID if can't find unique name
                        username = f"{name.replace(' ', '_')}_{str(uuid.uuid4())[:8]}"

                    # Create new agent from template
                    new_agent = AgentProfile(
                        id=str(uuid.uuid4()),
                        username=username,
                        joined_on=current_round_id,
                        left_on=None,
                        # Copy attributes from template
                        gender=getattr(template, "gender", "male"),
                        archetype=template.archetype,
                        llm=template.llm,
                        round_actions=template.round_actions,
                        daily_activity_level=getattr(template, "daily_activity_level", 1),
                        activity_profile=getattr(template, "activity_profile", "Always On"),
                        recsys_type=getattr(template, "recsys_type", "random"),
                        frecsys_type=getattr(template, "frecsys_type", "random"),
                        # Additional attributes
                        leaning=getattr(template, "leaning", 0),
                        leaning_bias=getattr(template, "leaning_bias", 1),
                        profile=getattr(template, "profile", ""),
                        action_likelihoods=getattr(template, "action_likelihoods", {}),
                    )

                    new_agents.append(new_agent)
                    existing_usernames.add(username)
                    self.logger.info(
                        f"Created new agent: {username} (template: {template.username})"
                    )

            if not new_agents:
                self.logger.info("No new agents created this evaluation")
                return 0

            # Batch register with server
            self.logger.info(f"Batch registering {len(new_agents)} new agents")
            ray.get(self.server.register_agents.remote(new_agents))

            # Add to local agent_profiles
            self.agent_profiles.extend(new_agents)

            # Update agent_population.json for persistence
            for agent in new_agents:
                self._add_agent_to_population_file(agent)

            self.logger.info(f"Successfully created and registered {len(new_agents)} new agents")
            return len(new_agents)

        except Exception as e:
            self.logger.error(f"Error evaluating new agents: {e}", exc_info=True)
            return 0

    def shutdown(self) -> None:
        ray.get(self.server.deregister_client.remote(self.client_id))
