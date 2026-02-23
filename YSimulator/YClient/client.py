"""
YClient - Simulation Client for YSimulator.

This module contains the Ray remote actor that runs simulation clients,
managing agent behaviors and coordinating with the orchestrator server.
"""

import gzip
import json
import logging
import os
import shutil
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

import ray

# Phase 5: Removed ActionExecutorMixin - dead code replaced by action generators in Phase 1
from YSimulator.YClient.action_generators import ActionContext, ActionGeneratorFactory
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.memory_runtime import ClientMemoryRuntime
from YSimulator.YClient.recsys import (
    CommonInterests,
    CommonUserInterests,
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
class SimulationClient:
    """
    Simulation client actor that manages agent behaviors and actions.

    This client handles:
    - Agent profile creation and management
    - Simulation loop execution
    - Action generation (posts and reactions)
    - Coordination with LLM service for intelligent behaviors

    Phase 5: Removed ActionExecutorMixin inheritance - action execution
    now handled by action generators (Phase 1).
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
        agent_config_file_path: str = None,
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
            agent_config_file_path: Optional path to agent_population.json file
                                    (overrides default config_path lookup)
        """
        self.client_id = client_id
        self.llm = llm_handle
        self.news_service = news_service_handle
        self.config_path = Path(config_path)
        self.agent_config_file_path = (
            Path(agent_config_file_path) if agent_config_file_path else None
        )

        # Phase 3: Initialize LLM Manager for consistent LLM interface
        # Import here to avoid circular dependencies during initial setup
        # Use a temporary logger until _setup_logging() is called
        import logging

        from YSimulator.YClient.llm_utils import LLMManager

        temp_logger = logging.getLogger(f"client_{client_id}")
        self.llm_manager = LLMManager(llm_handle, logger=temp_logger) if llm_handle else None

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

        # Load follow action decay configuration
        self.follow_action_decay_config = agents_config.get("follow_action_decay", {})
        # Add slots_per_day to decay config for proper calculation
        if self.follow_action_decay_config:
            self.follow_action_decay_config["slots_per_day"] = self.num_slots_per_day

        # Load text annotation configuration
        self.enable_sentiment = simulation_config["simulation"].get("enable_sentiment", False)
        self.enable_toxicity = simulation_config["simulation"].get("enable_toxicity", False)
        self.perspective_api_key = simulation_config["simulation"].get("perspective_api_key", None)
        self.enable_emotions = simulation_config["simulation"].get("emotion_annotation", False)

        # Cache for churned agents (refreshed after churn evaluation)
        self._churned_agents_cache = set()
        self._churned_agents_cache_valid = False

        # Connect to the Named Server Actor
        self.server = ray.get_actor("Orchestrator")
        self._memory_day = 1
        self._memory_slot = 0
        self._memory_round_id = None
        self.memory_runtime = ClientMemoryRuntime(
            simulation_config=self.simulation_config,
            config_path=self.config_path,
            logger=self.logger,
        )
        self.memory_runtime.initialize()

        # Initialize agent manager (Phase 6 refactoring - NEW)
        # Centralized agent lifecycle management
        from YSimulator.YClient.agent_management import AgentManager

        self.agent_manager = AgentManager(
            config_path=self.config_path,
            server=self.server,
            client_id=self.client_id,
            archetype_distribution=self.archetype_distribution,
            agent_downcast=self.agent_downcast,
            actions_likelihood=self.actions_likelihood,
            logger=self.logger,
            follow_action_decay_config=self.follow_action_decay_config,
            agent_config_file_path=self.agent_config_file_path,
        )

        # Create agents from configuration
        self.agent_profiles = []
        if agent_config:
            self.agent_profiles = self.agent_manager.create_agents_from_config(agent_config)

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

        # Initialize simulation orchestrator (Phase 2 refactoring)
        self._simulator = None
        self._agent_scheduler = None
        self._batch_processor = None
        self._lifecycle_manager = None
        self._round_executor = None

        # Initialize opinion manager (Phase 4 refactoring - NEW)
        # Centralized opinion dynamics management
        from YSimulator.YClient.opinion import OpinionManager

        self.opinion_manager = OpinionManager(
            simulation_config=self.simulation_config,
            server=self.server,
            llm_manager=self.llm_manager,
            agent_profiles=self.agent_profiles,
            client_id=self.client_id,
            logger=self.logger,
        )

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
        # Phase 4: Use OpinionManager for opinion dynamics operations
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
            memory_settings={
                "enabled": self.memory_runtime.active,
                "retrieval_top_k": self.simulation_config.get("agent_memory", {}).get(
                    "retrieval_top_k", 3
                ),
                "prompt_memory_char_budget": self.simulation_config.get("agent_memory", {}).get(
                    "prompt_memory_char_budget", 600
                ),
                "prompt_memory_item_char_limit": self.simulation_config.get(
                    "agent_memory", {}
                ).get("prompt_memory_item_char_limit", 140),
            },
            opinion_dynamics_config=(
                self.opinion_dynamics_config if hasattr(self, "opinion_dynamics_config") else None
            ),
            extract_agent_attrs_fn=self._extract_agent_attrs,
            annotate_action_fn=self._annotate_action_content,
            # Phase 4: Delegate opinion operations to OpinionManager
            is_opinion_dynamics_enabled_fn=self.opinion_manager.is_enabled,
            map_opinion_to_group_fn=self.opinion_manager.map_opinion_to_group,
            infer_page_agent_opinion_fn=self.opinion_manager.infer_page_agent_opinion,
            get_opinions_for_post_fn=self.opinion_manager.get_opinions_for_post,
            calculate_opinion_updates_fn=self.opinion_manager.calculate_opinion_updates,
            fetch_agent_memory_fn=self._fetch_agent_memory,
            record_memory_usage_fn=self._record_memory_usage,
        )

        return ActionGeneratorFactory(context)

    def _initialize_simulation_orchestrator(self):
        """
        Initialize the simulation orchestrator with all required components.

        This is part of Phase 2 refactoring to extract simulation orchestration logic
        into dedicated modules. Creates instances of:
        - AgentScheduler: Selects active agents for each round
        - BatchProcessor: Processes LLM calls in parallel (scatter/gather)
        - LifecycleManager: Handles agent lifecycle (churn, follows, new agents)
        - RoundExecutor: Executes simulation for a single round
        - Simulator: Main coordination of simulation loop
        """
        from YSimulator.YClient.simulation import (
            AgentScheduler,
            BatchProcessor,
            LifecycleManager,
            RoundExecutor,
            Simulator,
        )

        # Initialize AgentScheduler
        self._agent_scheduler = AgentScheduler(
            agent_profiles=self.agent_profiles,
            hourly_activity=self.hourly_activity,
            activity_profiles=self.activity_profiles,
            archetypes_enabled=self.archetypes_enabled,
            archetype_distribution=self.archetype_distribution,
            churn_enabled=self.churn_enabled,
            server=self.server,
            logger=self.logger,
        )

        # Initialize BatchProcessor
        self._batch_processor = BatchProcessor(
            server=self.server,
            client_id=self.client_id,
            llm=self.llm,
            enable_sentiment=self.enable_sentiment,
            enable_toxicity=self.enable_toxicity,
            enable_emotions=self.enable_emotions,
            perspective_api_key=self.perspective_api_key,
            logger=self.logger,
            cost_tracker=self.cost_tracker,  # Phase 3: Pass cost tracker
            ingest_memory_event_fn=self._ingest_memory_event,
        )

        # Initialize LifecycleManager
        self._lifecycle_manager = LifecycleManager(
            server=self.server,
            client_id=self.client_id,
            agent_profiles=self.agent_profiles,
            config_path=self.config_path,
            probability_of_daily_follow=self.probability_of_daily_follow,
            churn_enabled=self.churn_enabled,
            churn_probability=self.churn_probability,
            inactivity_threshold=self.inactivity_threshold,
            churn_percentage=self.churn_percentage,
            new_agents_enabled=self.new_agents_enabled,
            percentage_new_agents=self.percentage_new_agents,
            probability_new_agents=self.probability_new_agents,
            logger=self.logger,
        )

        # Initialize RoundExecutor
        self._round_executor = RoundExecutor(
            agent_profiles=self.agent_profiles,
            server=self.server,
            client_id=self.client_id,
            logger=self.logger,
            agent_downcast=self.agent_downcast,
            actions_likelihood=self.actions_likelihood,
            select_action_fn=self.__select_action,
            determine_agent_type_fn=self._determine_agent_type,
            dispatch_action_with_generator_fn=self._dispatch_action_with_generator,
        )

        # Initialize SecondaryFollowProcessor (Phase 1 alignment)
        from YSimulator.YClient.simulation.secondary_follow_processor import (
            SecondaryFollowProcessor,
        )

        self._secondary_follow_processor = SecondaryFollowProcessor(
            server=self.server,
            client_id=self.client_id,
            logger=self.logger,
            llm_manager=self.llm_manager,
            probability_of_secondary_follow=self.probability_of_secondary_follow,
        )

        # Initialize Simulator
        self._simulator = Simulator(
            server=self.server,
            client_id=self.client_id,
            agent_profiles=self.agent_profiles,
            config_path=self.config_path,
            num_days=self.num_days,
            num_slots_per_day=self.num_slots_per_day,
            heartbeat_interval=self.heartbeat_interval,
            agent_scheduler=self._agent_scheduler,
            batch_processor=self._batch_processor,
            lifecycle_manager=self._lifecycle_manager,
            round_executor=self._round_executor,
            secondary_follow_processor=self._secondary_follow_processor,
            logger=self.logger,
            parse_network_edges_fn=self._parse_network_edges,
            load_and_create_social_network_fn=self._load_and_create_social_network,
            create_action_generator_factory_fn=self._create_action_generator_factory,
            log_action_fn=self._log_action,
            log_hourly_summary_fn=self._log_hourly_summary,
            log_daily_summary_fn=self._log_daily_summary,
            update_round_info_fn=self._update_round_info,
            set_memory_context_fn=self._set_memory_context,
            ingest_actions_memory_fn=self._ingest_actions_memory,
        )

        self.logger.info("Simulation orchestrator initialized (Phase 2)")

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

        # Initialize cost tracker for LLM usage monitoring (Phase 3)
        self._setup_cost_tracker()

        # Phase 3: Update LLM Manager logger now that main logger is set up
        if self.llm_manager:
            self.llm_manager.logger = self.logger

    def _setup_cost_tracker(self):
        """Set up optional cost tracker for LLM usage monitoring."""
        from YSimulator.YClient.llm_utils import CostTracker

        # Get logging configuration
        logging_config = self.simulation_config.get("logging", {})
        enable_llm_usage_log = logging_config.get("enable_llm_usage_log", True)

        # Initialize cost tracker if enabled
        if enable_llm_usage_log:
            log_dir = self.config_path / "logs"
            llm_usage_log_file = log_dir / f"{self.client_id}_llm_usage.log"

            self.cost_tracker = CostTracker(
                token_costs=None,  # No cost estimates by default
                logger=self.logger,
                log_file_path=llm_usage_log_file,
                enable_file_logging=True,
            )
            self.logger.info(f"LLM usage logging enabled: {llm_usage_log_file}")

            # Log GPU selection information if using vLLM
            self._log_gpu_selection_info()
        else:
            self.cost_tracker = None
            self.logger.info("LLM usage logging disabled")

    def _log_gpu_selection_info(self):
        """Log GPU selection information to LLM usage log."""
        if not self.cost_tracker or not self.llm_manager:
            return

        try:
            # Check if the LLM service has GPU selection info (vLLM only)
            llm_service = self.llm_manager.llm_service

            # Check if this is a VLLMService with GPU info
            if hasattr(llm_service, "get_gpu_selection_info"):
                gpu_info = llm_service.get_gpu_selection_info()

                # Get model name from config
                llm_config = self.simulation_config.get("llm", {})
                model_name = llm_config.get("model", "unknown")
                backend = llm_config.get("backend", "vllm")

                # Log to usage file
                self.cost_tracker.log_gpu_selection(gpu_info, model_name, backend)
            # Check if it's a load balancer with multiple actors
            elif hasattr(llm_service, "get_all_actors"):
                # Load balancer - log info for first actor
                actors = llm_service.get_all_actors()
                if actors:
                    first_actor = actors[0]
                    # Get GPU info from first actor (requires remote call)
                    try:
                        gpu_info = ray.get(first_actor.get_gpu_selection_info.remote())

                        llm_config = self.simulation_config.get("llm", {})
                        model_name = llm_config.get("model", "unknown")
                        backend = llm_config.get("backend", "vllm")
                        num_actors = len(actors)

                        # Add actor count to GPU info
                        gpu_info_with_actors = gpu_info.copy()
                        gpu_info_with_actors["num_actors"] = num_actors

                        self.cost_tracker.log_gpu_selection(
                            gpu_info_with_actors, model_name, backend
                        )
                        self.logger.info(f"GPU selection logged for {num_actors} vLLM actors")
                    except Exception as e:
                        self.logger.debug(f"Could not get GPU info from actor: {e}")
        except Exception as e:
            # Don't fail if GPU logging fails
            self.logger.debug(f"Could not log GPU selection info: {e}")

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
        Delegates to agent_manager (Phase 6).
        """
        return self.agent_manager.sample_agents_by_archetype(available_agents, num_active)

    def _create_agents_from_config(self, agent_config):
        """
        Create agent profiles from configuration.
        Delegates to agent_manager (Phase 6).
        """
        return self.agent_manager.create_agents_from_config(agent_config)

    def _parse_network_edges(self, network_csv_path: Path) -> list:
        """
        Parse network.csv to extract edge tuples (follower_id, user_id).
        Delegates to agent_manager (Phase 6).

        Args:
            network_csv_path: Path to the network.csv file

        Returns:
            list: List of tuples (follower_id, user_id) representing edges
        """
        return self.agent_manager.parse_network_edges(network_csv_path, self.agent_profiles)

    def _load_and_create_social_network(self, network_csv_path: Path) -> int:
        """
        Load social network topology from CSV file and create Follow records.
        Delegates to agent_manager (Phase 6).

        Args:
            network_csv_path: Path to the network.csv file

        Returns:
            int: Number of follow relationships created
        """
        if not network_csv_path.exists():
            self.logger.info(
                f"No network.csv found at {network_csv_path}, skipping social network creation"
            )
            return 0

        self.logger.info(f"Loading social network from {network_csv_path}")

        # Delegate to agent_manager
        return self.agent_manager.load_and_create_social_network(
            network_csv_path, self.agent_profiles
        )

    def run(self) -> None:
        """
        Main simulation loop for the client.

        This method delegates to the Simulator class (Phase 2 refactoring).
        The simulator handles:
        1. Agent and client registration
        2. Network loading
        3. Main simulation loop execution
        4. Heartbeat management
        5. Lifecycle operations
        6. Completion notification
        """
        # Initialize simulation orchestrator if not already done
        if self._simulator is None:
            self._initialize_simulation_orchestrator()

        # Delegate to simulator
        self._simulator.run(calculate_opinion_updates_fn=self._calculate_opinion_updates)

    def _determine_agent_type(self, agent_profile: AgentProfile) -> str:
        """
        Determine the agent type (llm or rule_based) based on agent profile and downcast settings.
        Delegates to agent_manager (Phase 6).

        Args:
            agent_profile: Agent profile containing behavior settings

        Returns:
            str: "llm" or "rule_based"
        """
        return self.agent_manager.determine_agent_type(agent_profile)

    def __select_action(self, agent_profile: AgentProfile, recent_posts: list) -> tuple:
        """
        Determine which action an agent should perform.
        Delegates to agent_manager (Phase 6).
        """
        return self.agent_manager.select_action(agent_profile, recent_posts)

    def _update_round_info(self, current_day: int, current_hour: int):
        """
        Update the current round information for action selection (e.g., follow decay).
        Delegates to agent_manager.
        """
        self.agent_manager.update_round_info(current_day, current_hour)

    def _extract_agent_attrs(self, agent) -> dict:
        """
        Extract agent attributes for dynamic persona building.
        Delegates to agent_manager (Phase 6).
        """
        return self.agent_manager.extract_agent_attrs(
            agent,
            self._validate_and_extract_interests,
            self._is_opinion_dynamics_enabled,
            self._map_opinion_to_group,
        )

    def _fetch_agent_memory(self, agent_id: str, query: dict) -> list:
        """
        Fetch memory context for an agent.

        Args:
            agent_id: Agent UUID
            query: Retrieval query payload

        Returns:
            List of memory dictionaries (empty on error)
        """
        try:
            if self.memory_runtime.active:
                return self.memory_runtime.retrieve(
                    str(agent_id), query or {}, self._build_memory_context()
                )
            return ray.get(
                self.server.get_agent_memory.remote(
                    str(agent_id), query or {}, client_id=self.client_id
                )
            )
        except Exception as e:
            self.logger.debug(f"Memory retrieval failed for agent {agent_id}: {e}")
            return []

    def _record_memory_usage(self, agent_id: str, memory_ids: list) -> bool:
        """
        Record used memory item IDs for backend reinforcement.

        Args:
            agent_id: Agent UUID
            memory_ids: List of used memory item IDs

        Returns:
            bool: True on success, False otherwise
        """
        try:
            if self.memory_runtime.active:
                return self.memory_runtime.reinforce(
                    str(agent_id), memory_ids or [], self._build_memory_context()
                )
            return bool(
                ray.get(
                    self.server.record_memory_usage.remote(
                        str(agent_id), memory_ids or [], client_id=self.client_id
                    )
                )
            )
        except Exception as e:
            self.logger.debug(f"Memory reinforcement failed for agent {agent_id}: {e}")
            return False

    def _set_memory_context(self, day: int, slot: int) -> None:
        self._memory_day = int(day)
        self._memory_slot = int(slot)
        try:
            self._memory_round_id = ray.get(self.server.get_current_round_id.remote())
        except Exception:
            self._memory_round_id = None

    def _build_memory_context(self) -> Dict[str, Any]:
        return {
            "day": int(self._memory_day),
            "slot": int(self._memory_slot),
            "current_round_id": self._memory_round_id,
            "client_id": self.client_id,
        }

    def _ingest_memory_event(self, agent_id: str, event: Dict[str, Any]) -> bool:
        try:
            if self.memory_runtime.active:
                return self.memory_runtime.ingest_event(
                    str(agent_id), event or {}, self._build_memory_context()
                )
            return bool(
                ray.get(
                    self.server.ingest_memory_event.remote(
                        str(agent_id), event or {}, client_id=self.client_id
                    )
                )
            )
        except Exception as e:
            self.logger.debug(f"Memory ingest failed for agent {agent_id}: {e}")
            return False

    def _ingest_actions_memory(self, actions: List[ActionDTO], day: int, slot: int) -> None:
        self._set_memory_context(day, slot)
        if not self.memory_runtime.active:
            return
        for act in actions:
            event = {
                "action_type": getattr(act, "action_type", None),
                "agent_id": str(getattr(act, "agent_id", "")),
                "content": getattr(act, "content", None),
                "target_post_id": getattr(act, "target_post_id", None),
                "target_user_id": getattr(act, "target_user_id", None),
                "topic": getattr(act, "topic", None),
                "metadata": (
                    dict(getattr(act, "memory_metadata", {}))
                    if isinstance(getattr(act, "memory_metadata", None), dict)
                    else {}
                ),
            }
            self._ingest_memory_event(str(getattr(act, "agent_id", "")), event)

    def _save_updated_agent_population(self, updated_interests: dict):
        """
        Save updated agent interests to agent_population.json at end of day.
        Delegates to agent_manager (Phase 6).
        """
        self.agent_manager.save_updated_agent_population(updated_interests)

    def _validate_and_extract_interests(self, interests):
        """
        Validate interests structure and extract topics and counts.
        Delegates to agent_manager (Phase 6).
        """
        return self.agent_manager.validate_and_extract_interests(interests)

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
                f"Annotated action content: has_sentiment={bool( annotations.get('sentiment'))}, has_toxicity={bool( annotations.get('toxicity'))}, has_emotions={bool( annotations.get('emotions'))}, hashtags={len( annotations.get( 'hashtags', []))}, mentions={len( annotations.get( 'mentions', []))}"
            )

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

        # Ensure action generator factory is initialized
        # This is needed because the factory may not be created yet when called from
        # various contexts before the main simulation loop
        if self._action_generator_factory is None:
            # Create a temporary factory with minimal context
            # The actual context values (day, slot, recent_posts) may not be accurate
            # but this allows the method to work in all contexts
            self._action_generator_factory = self._create_action_generator_factory(
                day=0, slot=0, recent_posts=[]
            )

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
                f"Generator {generator.__class__.__name__}cannot generate for agent {agent.username}"
            )
            return [], [], {"skipped": True, "reason": "cannot_generate"}

        # Generate the action
        result = generator.generate(agent, agent_type)

        return result.actions, result.pending_llm_calls, result.metadata

    def _calculate_opinion_updates(
        self, agent_id: str, parent_post_id: str, parent_post_data: dict
    ) -> Optional[dict]:
        """
        Calculate opinion updates when an agent comments on a post.

        Phase 4: Delegated to OpinionManager.

        Args:
            agent_id: UUID of the agent making the comment
            parent_post_id: UUID of the post being commented on
            parent_post_data: Dictionary containing post data including user_id

        Returns:
            dict: Mapping of topic_id to new opinion value, or None if no updates
        """
        return self.opinion_manager.calculate_opinion_updates(
            agent_id, parent_post_id, parent_post_data
        )

    def _map_opinion_to_group(self, opinion_value: float) -> str:
        """
        Map a numeric opinion value to a discrete opinion group label.

        Phase 4: Delegated to OpinionManager.

        Args:
            opinion_value: Numeric opinion in [0, 1]

        Returns:
            str: Opinion group label from simulation_config opinion_groups
        """
        return self.opinion_manager.map_opinion_to_group(opinion_value)

    def _is_opinion_dynamics_enabled(self) -> bool:
        """
        Check if opinion dynamics is enabled in the simulation configuration.

        Phase 4: Delegated to OpinionManager.

        Returns:
            bool: True if opinion dynamics is enabled, False otherwise
        """
        return self.opinion_manager.is_enabled()

    def _infer_page_agent_opinion(
        self, agent_id: str, article_content: str, topic_name: str
    ) -> float:
        """
        Infer opinion for a page agent on a topic from article content.

        Phase 4: Delegated to OpinionManager.

        Args:
            agent_id: Agent UUID
            article_content: Article text to analyze
            topic_name: Topic to infer opinion about

        Returns:
            float: Opinion value in [0, 1] range
        """
        return self.opinion_manager.infer_page_agent_opinion(agent_id, article_content, topic_name)

    def _get_opinions_for_post(self, agent_id: str, post_id: str) -> dict:
        """
        Get agent's opinions on the topics discussed in a post.

        Phase 4: Delegated to OpinionManager.

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
        return self.opinion_manager.get_opinions_for_post(agent_id, post_id)

    def shutdown(self) -> None:
        ray.get(self.server.deregister_client.remote(self.client_id))
