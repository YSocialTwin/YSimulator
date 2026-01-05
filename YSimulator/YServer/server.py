"""
YServer - Orchestrator Server for YSimulator.

This module contains the Ray remote actor that orchestrates the simulation,
managing client registration, agent actions, and simulation state progression.
"""

import functools
import gzip
import inspect
import json
import logging
import os
import random
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import ray

from YSimulator.YClient.classes.ray_models import SimulationInstruction
from YSimulator.YServer.classes.models import Recommendation
from YSimulator.YServer.interests_modeling import InterestManager
from YSimulator.YServer.recsys import content_recsys_db, content_recsys_redis, follow_recsys_db

# Constants
RECOMMENDATION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds
NETWORK_EDGE_CHECK_LIMIT = 10  # Number of edges to check when verifying network load
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_FILE_BACKUP_COUNT = 5  # Keep 5 backup files


def log_server_request(func: callable) -> callable:
    """
    Decorator to log server requests to _server.log with detailed information.

    Logs each method call with:
    - request_id: unique request identifier
    - client_name: client making the request (if available)
    - path: method name
    - status_code: 200 for success, 500 for error
    - duration: execution time in seconds
    - time: current datetime
    - tid: current round id
    - day: current simulation day
    - hour: current simulation slot/hour
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Generate request ID with better uniqueness using UUID hex
        request_id = f"{time.time()}-{uuid.uuid4().hex[:10]}"

        # Extract client_name from arguments
        # Only look for explicit client_id parameter - this represents the actual client making the request
        client_name = kwargs.get("client_id")

        # If not in kwargs, check if first positional arg is client_id by checking parameter name
        if not client_name and args:
            # Get the function signature to check parameter names
            import inspect

            try:
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                # First param after 'self' (index 0 is 'self', index 1 is first real param)
                if len(param_names) > 1 and len(args) > 0:
                    first_param_name = param_names[1]
                    # Only use first arg as client_name if the parameter is named 'client_id'
                    if first_param_name == "client_id" and isinstance(args[0], str):
                        client_name = args[0]
            except (ValueError, TypeError, AttributeError) as e:
                # Signature inspection can fail for various reasons, fallback to "unknown"
                pass

        # Default to "unknown" if still not found
        if not client_name:
            client_name = "unknown"

        # Start timing
        start_time = time.time()
        status_code = 200
        error = None

        try:
            # Execute the method
            result = func(self, *args, **kwargs)
            return result
        except Exception as e:
            status_code = 500
            error = str(e)
            raise
        finally:
            # Calculate duration
            duration = time.time() - start_time

            # Get current simulation state (getattr with defaults never raises exceptions)
            tid = getattr(self, "current_round_id", None)
            day = getattr(self, "day", None)
            hour = getattr(self, "slot", None)

            # Log the request
            try:
                server_logger = getattr(self, "server_request_logger", None)
                if server_logger:
                    log_entry = {
                        "request_id": request_id,
                        "client_name": client_name,
                        "path": func.__name__,
                        "status_code": status_code,
                        "duration": duration,
                        "time": datetime.now(timezone.utc).isoformat(),
                        "tid": tid,
                        "day": day,
                        "hour": hour,
                    }
                    if error:
                        log_entry["error"] = error

                    server_logger.info(json.dumps(log_entry))
            except Exception as log_error:
                # Don't let logging errors break the application
                # Log to stderr as fallback for debugging
                self.logger.error(f"Server request logging failed: {log_error}")

    return wrapper


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
class OrchestratorServer:
    """
    Orchestrator server actor that manages simulation state and coordinates clients.

    This server handles:
    - Client registration and deregistration
    - Agent profile registration in the database
    - Simulation state progression (days and slots)
    - Action submission and processing
    - Barrier synchronization between clients
    """

    def __init__(
        self,
        db_config: dict,
        config_path: str = ".",
        min_to_start: int = 1,
        server_name: str = "orchestrator",
        redis_config: dict = None,
        timeout_seconds: int = 60,
        simulation_config: dict = None,
    ):
        """
        Initialize the orchestrator server.

        Args:
            db_config: Database configuration dict with type and connection details
            config_path: Path to configuration directory for logs
            min_to_start: Minimum number of clients before simulation starts
            server_name: Name of this server instance (str)
            redis_config: Redis configuration dict (optional)
            timeout_seconds: Seconds before considering a client stale (default: 60)
            simulation_config: Simulation configuration dict (optional)
        """
        # Server configuration
        self.min_to_start = min_to_start
        self.server_name = server_name
        self.config_path = Path(config_path)
        self.timeout_seconds = timeout_seconds

        # Store simulation config for logging configuration
        if simulation_config is None:
            simulation_config = {}
        self.simulation_config = simulation_config

        # Archetype configuration
        self.archetype_config = simulation_config.get("agent_archetypes", {})
        self.archetypes_enabled = self.archetype_config.get("enabled", False)
        self.archetype_distribution = self.archetype_config.get("distribution", {})
        self.archetype_transitions = self.archetype_config.get("transitions", {})

        # Track last archetype transition day (start at 0, so first transition at day 7)
        self.last_archetype_transition_day = 0

        # Cache agent profiles for opinion lookup (only when opinion dynamics enabled)
        self.agent_profiles_cache = {}

        # Simulation timing configuration
        self.num_slots_per_day = simulation_config.get("simulation", {}).get(
            "num_slots_per_day", 24
        )

        # Store visibility_rounds for server use
        self.visibility_rounds = simulation_config.get("posts", {}).get("visibility_rounds", 36)

        # Store attention_window for interest decay (sliding window)
        self.attention_window = simulation_config.get("agents", {}).get("attention_window", 336)

        # Registered agents mapping
        self.registered_agents = {}  # {agent_id: username}

        # Simulation state (will be managed by RoundManager)
        self.recent_posts_cache = []

        # Set up logging first
        self._setup_logging()

        # Initialize Redis client if configured
        redis_client = None
        if redis_config and isinstance(redis_config, dict) and redis_config.get("enabled", False):
            redis_client = self._create_redis_client(redis_config)
        
        # Initialize services using Repository/Service pattern
        use_new_pattern = False
        try:
            from YSimulator.YServer.service_factory import create_all_services, SERVICES_AVAILABLE
            from YSimulator.YServer.database_adapter import DatabaseServiceAdapter
            
            if not SERVICES_AVAILABLE:
                raise ImportError("Repository/Service pattern dependencies not available")
            
            (user_service, post_service, follow_service, interest_service, 
             article_service, image_service, content_service, simulation_service, 
             metadata_service, mention_service) = create_all_services(
                db_config, 
                str(self.config_path),
                self.logger
            )
            
            # Phase 5: Expose services directly for explicit usage
            self.user_service = user_service
            self.post_service = post_service
            self.follow_service = follow_service
            self.interest_service = interest_service
            self.article_service = article_service
            self.image_service = image_service
            self.content_service = content_service
            self.simulation_service = simulation_service
            self.metadata_service = metadata_service
            self.mention_service = mention_service
            self.redis_client = redis_client
            self.use_redis = redis_client is not None
            
            # Create database adapter for backwards compatibility (will be phased out)
            self.db = DatabaseServiceAdapter(
                user_service=user_service,
                post_service=post_service,
                follow_service=follow_service,
                interest_service=interest_service,
                article_service=article_service,
                image_service=image_service,
                content_service=content_service,
                simulation_service=simulation_service,
                metadata_service=metadata_service,
                mention_service=mention_service,
                redis_client=redis_client,
                logger=self.logger,
            )
            use_new_pattern = True
            self.logger.info(
                "Orchestrator server initialized - Repository/Service pattern 100% with direct service access!",
                extra={
                    "migration_status": "PHASE_5_COMPLETE",
                    "services": "User, Post, Follow, Interest, Article, Image, Content, Simulation, Metadata, Mention",
                    "service_access": "Direct - no adapter facade",
                    "legacy_middleware": "None - fully eliminated"
                }
            )
        except Exception as e:
            self.logger.error(
                f"Failed to create services: {e}. "
                "Unable to start server without service layer."
            )
            raise RuntimeError(
                f"Service layer initialization failed: {e}. "
                "Please ensure all dependencies are installed: pip install sqlalchemy>=2.0.0"
            )

        # Initialize Interest Manager using the database adapter
        self.interest_manager = InterestManager(
            db_service=self.db, attention_window=self.attention_window
        )

        # Initialize emotions table
        self.metadata_service.initialize_emotions_table()

        # Initialize action router for modular action processing
        # Pass self (the server) so processors can access server methods like _process_annotations
        from YSimulator.YServer.action_processors.action_router import ActionRouter
        self.action_router = ActionRouter(self, self.logger)
        self.logger.info("Action router initialized with processors for POST, COMMENT, SHARE, FOLLOW, UNFOLLOW, and reactions")

        # Initialize recommendation engines
        from YSimulator.YServer.recommendation import ContentRecommender, FollowRecommender
        self.content_recommender = ContentRecommender(self.db, self.visibility_rounds, self.logger)
        self.follow_recommender = FollowRecommender(self.db, self.logger)
        self.logger.info("Recommendation engines initialized (ContentRecommender, FollowRecommender)")

        # Initialize opinion dynamics handler
        from YSimulator.YServer.opinion_dynamics import OpinionHandler
        self.opinion_handler = OpinionHandler(
            db_adapter=self.db,
            simulation_config=self.simulation_config,
            agent_profiles_cache=self.agent_profiles_cache,
            current_round_id_getter=lambda: self.current_round_id,
            logger=self.logger
        )
        self.logger.info("Opinion dynamics handler initialized")

        # Initialize coordination layer
        from YSimulator.YServer.coordination import (
            ClientManager, BarrierHandler, RoundManager, ArchetypeManager
        )
        self.client_manager = ClientManager(timeout_seconds=self.timeout_seconds, logger=self.logger)
        self.barrier_handler = BarrierHandler(logger=self.logger)
        self.round_manager = RoundManager(
            db_adapter=self.db,
            interest_manager=self.interest_manager,
            visibility_rounds=self.visibility_rounds,
            num_slots_per_day=self.num_slots_per_day,
            logger=self.logger
        )
        self.archetype_manager = ArchetypeManager(
            db_adapter=self.db,
            archetypes_enabled=self.archetypes_enabled,
            archetype_transitions=self.archetype_transitions,
            logger=self.logger
        )
        self.logger.info("Coordination layer initialized (ClientManager, BarrierHandler, RoundManager, ArchetypeManager)")
        
        # Initialize first round using RoundManager (no need to store, accessed via property)
        self.round_manager.initialize_first_round()
        
        # Expose properties for backward compatibility
        self.registered_clients = self.client_manager.registered_clients
        self.completed_clients = self.client_manager.completed_clients
        self.submitted_clients = self.client_manager.submitted_clients
        self.last_heartbeat = self.client_manager.last_heartbeat

        self.logger.info(
            "Orchestrator server fully initialized - 100% modern architecture!",
            extra={
                "extra_data": {
                    "db_type": db_config.get("type", "sqlite"),
                    "min_to_start": min_to_start,
                    "redis_enabled": self.db.use_redis,
                    "timeout_seconds": timeout_seconds,
                    "archetypes_enabled": self.archetypes_enabled,
                    "migration_status": "100_PERCENT_COMPLETE",
                    "services_integrated": [
                        "UserService",
                        "PostService",
                        "FollowService",
                        "InterestService",
                        "ArticleService",
                        "ImageService",
                        "ContentService",
                        "SimulationService",
                        "MetadataService",
                        "MentionService",
                    ],
                    "legacy_middleware": "None - fully removed",
                }
            },
        )

    @property
    def day(self) -> int:
        """Get current simulation day from RoundManager."""
        return self.round_manager.day
    
    @property
    def slot(self) -> int:
        """Get current simulation slot from RoundManager."""
        return self.round_manager.slot
    
    @property
    def current_round_id(self) -> str:
        """Get current round ID from RoundManager."""
        return self.round_manager.current_round_id

    def _create_redis_client(self, redis_config: dict):
        """
        Create and initialize a Redis client.
        
        Args:
            redis_config: Redis configuration dict with host, port, db, password, enabled
            
        Returns:
            Redis client instance or None if connection fails
        """
        try:
            import redis
        except ImportError:
            self.logger.warning(
                "Redis is enabled but redis module is not installed. "
                "Install with: pip install redis"
            )
            return None
        
        if not redis_config.get("host"):
            self.logger.info(
                "Redis is enabled but no host specified in config, skipping Redis initialization"
            )
            return None
        
        try:
            redis_client = redis.Redis(
                host=redis_config.get("host"),
                port=redis_config.get("port", 6379),
                db=redis_config.get("db", 0),
                password=redis_config.get("password"),
                decode_responses=True,
            )
            # Test connection
            redis_client.ping()
            self.logger.info(
                "Redis connection established",
                extra={
                    "extra_data": {
                        "host": redis_config.get("host"),
                        "port": redis_config.get("port", 6379),
                    }
                },
            )
            return redis_client
        except Exception as e:
            self.logger.warning(
                f"Redis connection failed: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def _setup_logging(self):
        """Set up JSON logging for the server actor with gzip compression."""
        # Get logging configuration
        logging_config = self.simulation_config.get("logging", {})
        enable_actor_log = logging_config.get("enable_actor_log", True)
        enable_request_log = logging_config.get("enable_request_log", True)

        log_dir = self.config_path / "logs"
        log_dir.mkdir(exist_ok=True)

        # Create logger
        self.logger = logging.getLogger(f"YSimulator.Server.{self.server_name}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Create file handler with JSON formatting (actor log)
        if enable_actor_log:
            log_file = log_dir / f"{self.server_name}_actor.log"

            from logging.handlers import RotatingFileHandler

            handler = RotatingFileHandler(
                log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT
            )

            # Add compression for rotated files
            handler.rotator = compress_rotated_log
            handler.namer = lambda name: name + ".gz"

            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    log_data = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
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

        # Set up server request logger for _server.log
        self.server_request_logger = logging.getLogger(
            f"YSimulator.Server.{self.server_name}.Requests"
        )
        self.server_request_logger.setLevel(logging.INFO)
        self.server_request_logger.handlers = []

        if enable_request_log:
            from logging.handlers import RotatingFileHandler

            server_log_file = log_dir / "_server.log"

            # Create handler for server requests (raw JSON, one per line)
            server_handler = RotatingFileHandler(
                server_log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT
            )

            # Add compression for rotated files
            server_handler.rotator = compress_rotated_log
            server_handler.namer = lambda name: name + ".gz"

            # Simple formatter that just outputs the message (already JSON)
            class RawFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    return record.getMessage()

            server_handler.setFormatter(RawFormatter())
            self.server_request_logger.addHandler(server_handler)

        # Prevent propagation to avoid duplicate logs
        self.server_request_logger.propagate = False

    def _validate_and_extract_interests(self, interests):
        """
        Validate interests structure and extract topics and counts.
        Delegates to InterestManager.

        Args:
            interests: Interest data in format [["Topic1", "Topic2"], [1, 2]]

        Returns:
            tuple: (topics, counts) or (None, None) if invalid
        """
        return self.interest_manager.validate_and_extract_interests(interests)

    def _recompute_agent_interests_from_window(self, agent_id: str):
        """
        Recompute agent interests based on the sliding attention window.
        Delegates to InterestManager.

        Args:
            agent_id: Agent UUID
        """
        self.interest_manager.recompute_agent_interests_from_window(agent_id)

    def _update_agent_interest_counter(self, agent_id: str, topic_name: str, increment: int = 1):
        """
        DEPRECATED: This method is replaced by _recompute_agent_interests_from_window.
        Delegates to InterestManager.

        Args:
            agent_id: Agent UUID
            topic_name: Name of the topic
            increment: Amount to increment the counter (default: 1)
        """
        self.interest_manager.update_agent_interest_counter(agent_id, topic_name, increment)

    def _get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """
        Get topic name from topic UUID.
        Delegates to InterestManager.

        Args:
            topic_id: Topic UUID (iid)

        Returns:
            str: Topic name or None if not found
        """
        return self.interest_manager.get_topic_name_from_id(topic_id)

    def _ensure_agent_opinion_exists(
        self, agent_id: str, topic_id: str, topic_name: str, article_content: str = None
    ):
        """
        Ensure an agent has an opinion recorded for a topic.
        
        Delegates to OpinionHandler for opinion management logic.
        
        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID (from interests table)
            topic_name: Topic name for looking up in cached profile
            article_content: Unused (kept for backwards compatibility)
        """
        self.opinion_handler.ensure_agent_opinion_exists(
            agent_id, topic_id, topic_name, article_content
        )

    def _reaction_to_sentiment(self, reaction_type: str) -> Optional[Dict[str, float]]:
        """
        Map a reaction type to sentiment values.

        Converts reaction types (LIKE, LOVE, ANGRY, SAD, LAUGH) to sentiment scores
        that can be stored in the post_sentiment table.

        Args:
            reaction_type: Type of reaction (LIKE, LOVE, ANGRY, SAD, LAUGH, etc.)

        Returns:
            dict: Sentiment values with keys: neg, pos, neu, compound
                  Returns None if reaction type doesn't map to sentiment
        """
        # Map reaction types to sentiment
        # pos=1 for positive reactions, neg=1 for negative, neu=1 for neutral
        # compound: 1 if pos=1, -1 if neg=1, 0 otherwise
        reaction_map = {
            "LIKE": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "LOVE": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "LAUGH": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "ANGRY": {"pos": 0.0, "neg": 1.0, "neu": 0.0, "compound": -1.0},
            "SAD": {"pos": 0.0, "neg": 1.0, "neu": 0.0, "compound": -1.0},
        }

        result = reaction_map.get(reaction_type.upper())
        if result:
            self.logger.info(
                f"Mapped reaction {reaction_type} to sentiment: compound={result['compound']}"
            )
        else:
            self.logger.debug(
                f"Reaction type {reaction_type} not mapped to sentiment (e.g., IGNORE)"
            )
        return result

    def _process_annotations(
        self,
        post_id: str,
        user_id: str,
        annotations: dict,
        is_post: bool = False,
        is_comment: bool = False,
        parent_post_id: Optional[str] = None,
        parent_sentiment: Optional[float] = None,
    ):
        """
        Process text annotations for a post or comment.

        Handles:
        - Hashtags: Add to hashtags table and link to post
        - Mentions: Validate users and add to mentions table
        - Sentiment: Compute and store sentiment data per topic
        - Toxicity: Store toxicity scores

        Args:
            post_id: UUID of the post/comment
            user_id: UUID of the user who created the post/comment
            annotations: Dict with annotation data:
                - 'hashtags': List[str] - Hashtag text without # prefix
                - 'mentions': List[str] - Usernames without @ prefix
                - 'sentiment': Dict[str, float] or None - VADER sentiment scores
                  with keys: 'neg', 'pos', 'neu', 'compound'
                - 'toxicity': Dict[str, float] or None - Perspective API scores
                  with keys: 'TOXICITY', 'SEVERE_TOXICITY', 'IDENTITY_ATTACK',
                  'INSULT', 'PROFANITY', 'THREAT', 'SEXUALLY_EXPLICIT', 'FLIRTATION'
            is_post: Whether this is a post (not a comment)
            is_comment: Whether this is a comment
            parent_post_id: UUID of parent post (for comments)
            parent_sentiment: Compound sentiment of parent post (for comments)
        """
        self.logger.info(
            f"_process_annotations called for post {post_id}: has_hashtags={bool(annotations.get('hashtags'))}, has_mentions={bool(annotations.get('mentions'))}, has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}"
        )

        # Process hashtags
        hashtags = annotations.get("hashtags", [])
        for hashtag_text in hashtags:
            # Get or create hashtag
            hashtag_id = self.metadata_service.add_or_get_hashtag(hashtag_text)
            if hashtag_id:
                # Link hashtag to post
                self.metadata_service.add_post_hashtag(post_id, hashtag_id)
                self.logger.info(f"Linked hashtag '{hashtag_text}' to post {post_id}")

        # Process mentions
        mentions = annotations.get("mentions", [])
        for username in mentions:
            # Check if user exists
            mentioned_user = self.user_service.get_user_by_username(username)
            if mentioned_user:
                # Add mention entry
                self.mention_service.add_mention(post_id, mentioned_user["id"])
                self.logger.info(f"Added mention of @{username} in post {post_id}")
            else:
                self.logger.warning(f"Mentioned user @{username} not found in database")

        # Process sentiment
        sentiment_scores = annotations.get("sentiment")
        if sentiment_scores:
            self.logger.info(
                f"Processing sentiment for post {post_id}: compound={sentiment_scores.get('compound', 0):.3f}"
            )
            # Get topics associated with this post/comment
            topic_ids = self.post_service.get_post_topics(post_id)

            # If comment without topics yet, get parent's topics
            if not topic_ids and parent_post_id:
                topic_ids = self.post_service.get_post_topics(parent_post_id)
                if topic_ids:
                    self.logger.info(
                        f"Using {len(topic_ids)} topics from parent post {parent_post_id} for comment {post_id}"
                    )

            if not topic_ids:
                self.logger.warning(
                    f"No topics found for post {post_id}, skipping sentiment storage. Sentiment data will not be saved."
                )

            # Create sentiment entry for each topic
            for topic_id in topic_ids:
                sentiment_data = {
                    "post_id": post_id,
                    "user_id": user_id,
                    "topic_id": topic_id,
                    "round": self.current_round_id,
                    "neg": sentiment_scores.get("neg"),
                    "pos": sentiment_scores.get("pos"),
                    "neu": sentiment_scores.get("neu"),
                    "compound": sentiment_scores.get("compound"),
                    "sentiment_parent": parent_sentiment,
                    "is_post": 1 if is_post else 0,
                    "is_comment": 1 if is_comment else 0,
                    "is_reaction": 0,
                }
                success = self.metadata_service.add_post_sentiment(sentiment_data)
                if success:
                    self.logger.info(f"Added sentiment entry for post {post_id}, topic {topic_id}")
                else:
                    self.logger.error(
                        f"Failed to add sentiment entry for post {post_id}, topic {topic_id}"
                    )

            if topic_ids:
                self.logger.info(
                    f"Successfully added sentiment for post {post_id} across {len(topic_ids)} topics"
                )
        else:
            self.logger.debug(f"No sentiment data in annotations for post {post_id}")

        # Process toxicity
        toxicity_scores = annotations.get("toxicity")
        if toxicity_scores:
            self.logger.info(
                f"Processing toxicity for post {post_id}: TOXICITY={toxicity_scores.get('TOXICITY', 0):.3f}"
            )
            toxicity_data = {
                "post_id": post_id,
                "toxicity": toxicity_scores.get("TOXICITY", 0.0),
                "severe_toxicity": toxicity_scores.get("SEVERE_TOXICITY", 0.0),
                "identity_attack": toxicity_scores.get("IDENTITY_ATTACK", 0.0),
                "insult": toxicity_scores.get("INSULT", 0.0),
                "profanity": toxicity_scores.get("PROFANITY", 0.0),
                "threat": toxicity_scores.get("THREAT", 0.0),
                "sexually_explicit": toxicity_scores.get("SEXUALLY_EXPLICIT", 0.0),
                "flirtation": toxicity_scores.get("FLIRTATION", 0.0),
            }
            success = self.metadata_service.add_post_toxicity(toxicity_data)
            if success:
                self.logger.info(f"Successfully added toxicity data for post {post_id}")
            else:
                self.logger.error(f"Failed to add toxicity data for post {post_id}")
        else:
            self.logger.debug(f"No toxicity data in annotations for post {post_id}")

        # Process emotions
        emotions = annotations.get("emotions")
        if emotions:
            self.logger.info(f"Processing emotions for post {post_id}: {emotions}")
            for emotion_name in emotions:
                # Get emotion from database
                emotion = self.metadata_service.get_emotion_by_name(emotion_name)
                if emotion:
                    # Add post emotion association
                    success = self.metadata_service.add_post_emotion(post_id, emotion["id"])
                    if success:
                        self.logger.info(f"Added emotion '{emotion_name}' to post {post_id}")
                    else:
                        self.logger.error(
                            f"Failed to add emotion '{emotion_name}' to post {post_id}"
                        )
                else:
                    self.logger.warning(
                        f"Emotion '{emotion_name}' not found in database for post {post_id}"
                    )
        else:
            self.logger.debug(f"No emotion data in annotations for post {post_id}")

    def _recompute_all_agent_interests(self):
        """
        Recompute interests for all registered agents based on the sliding attention window.
        Delegates to InterestManager.
        """
        agent_ids = list(self.registered_agents.keys())
        self.interest_manager.recompute_all_agent_interests(agent_ids)

    def get_updated_agent_interests(self) -> Dict[str, Dict[str, list]]:
        """
        Get the current agent interests dictionary for clients to save.
        Delegates to InterestManager.

        Returns:
            Dict: agent_interests dictionary with format {agent_id: {"topics": [...], "counts": [...]}}
        """
        return self.interest_manager.get_agent_interests()

    def get_article_topics(self, article_id: str) -> List[str]:
        """
        Get topic IDs for an article.
        Delegates to InterestManager.

        Args:
            article_id: Article UUID

        Returns:
            List[str]: List of topic IDs (uuids)
        """
        return self.interest_manager.get_article_topics(article_id)

    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """
        Get topic ID by topic name.

        Args:
            topic_name: Name of the topic/interest

        Returns:
            str: Topic UUID or None if not found
        """
        return self.interest_service.get_topic_id_by_name(topic_name)

    def store_article_topics(self, article_id: str, topic_names: List[str]) -> List[str]:
        """
        Store topics for an article in the database.
        Delegates to InterestManager.

        Args:
            article_id: Article UUID
            topic_names: List of topic names to store

        Returns:
            List[str]: List of topic IDs (uuids) that were stored
        """
        return self.interest_manager.store_article_topics(article_id, topic_names)

    @log_server_request
    def register_agents(self, agents: list, client_id: str = None) -> dict:
        """
        Register agent profiles in the database if they don't already exist.
        For page agents (is_page=1), also creates a Website entry.

        This method uses batch insertion for improved performance with large agent populations.

        Args:
            agents: List of AgentProfile dataclass instances
            client_id: Optional client identifier for logging purposes

        Returns:
            dict: Summary of registration results with counts
        """
        start_time = time.time()

        # Prepare all user data for batch insertion
        users_data = []
        websites_data = []
        agent_id_to_profile = {}

        for agent_profile in agents:
            # Store agent profile for later lookup
            agent_id_to_profile[str(agent_profile.id)] = agent_profile

            # Prepare user data
            user_data = {
                "id": str(agent_profile.id),  # Convert to UUID string
                "username": agent_profile.username,
                "email": agent_profile.email,
                "password": agent_profile.password,
                "leaning": agent_profile.leaning,
                "user_type": agent_profile.user_type,
                "age": agent_profile.age,
                "oe": agent_profile.oe,
                "co": agent_profile.co,
                "ex": agent_profile.ex,
                "ag": agent_profile.ag,
                "ne": agent_profile.ne,
                "recsys_type": agent_profile.recsys_type,
                "frecsys_type": agent_profile.frecsys_type,
                "language": agent_profile.language,
                "owner": agent_profile.owner,
                "education_level": agent_profile.education_level,
                "joined_on": (
                    agent_profile.joined_on if agent_profile.joined_on else self.current_round_id
                ),  # Use agent's joined_on or current round
                "gender": agent_profile.gender,
                "nationality": agent_profile.nationality,
                "round_actions": agent_profile.round_actions,
                "toxicity": agent_profile.toxicity,
                "is_page": agent_profile.is_page,
                "left_on": agent_profile.left_on,
                "daily_activity_level": agent_profile.daily_activity_level,
                "profession": agent_profile.profession,
                "activity_profile": agent_profile.activity_profile,
                "archetype": agent_profile.archetype,
                "last_active_day": self.day,  # Initialize last_active_day to current day
            }
            users_data.append(user_data)

            # Prepare website data for page agents
            if agent_profile.is_page == 1 and agent_profile.feed_url:
                website_data = {
                    "id": str(agent_profile.id),  # Website ID = User ID
                    "name": agent_profile.username,  # Use username as website name
                    "rss": agent_profile.feed_url,
                    "category": "page",  # Mark as page
                    "language": agent_profile.language,
                    "country": agent_profile.nationality,
                    "leaning": agent_profile.leaning,
                }
                websites_data.append(website_data)

        try:
            # Batch register users - returns (count, set of newly registered IDs)
            registered_count, newly_registered_ids = self.user_service.register_users_batch(users_data)

            # All agents (new and existing) should be in registered_agents dict
            # Also cache agent profiles for opinion lookups (when opinion dynamics enabled)
            opinion_config = self.simulation_config.get("opinion_dynamics", {})
            if opinion_config.get("enabled", False):
                for agent_profile in agents:
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    # Cache full profile for opinion lookups
                    self.agent_profiles_cache[agent_profile.id] = agent_profile
            else:
                for agent_profile in agents:
                    self.registered_agents[agent_profile.id] = agent_profile.username

            skipped_count = len(agents) - registered_count

            # Initialize interests ONLY for newly registered agents
            # This prevents duplicate interest entries for already-existing agents
            for agent_id in newly_registered_ids:
                agent_profile = agent_id_to_profile.get(agent_id)
                if agent_profile and agent_profile.interests:
                    self.interest_manager.initialize_agent_interests(
                        agent_id=agent_id,
                        interests=agent_profile.interests,
                        round_id=self.current_round_id,
                    )

                # Initialize opinions for newly registered agents
                if agent_profile and agent_profile.opinions:
                    # Get interest IDs for the agent's topics
                    for topic_name, opinion_value in agent_profile.opinions.items():
                        # Get or create the interest/topic in the database
                        topic_id = self.interest_service.add_or_get_interest(topic_name)
                        if topic_id:
                            # Store initial opinion with no interaction references
                            self.interest_service.add_agent_opinion(
                                agent_id=agent_id,
                                round_id=self.current_round_id,
                                topic_id=topic_id,
                                opinion=opinion_value,
                                id_interacted_with=None,
                                id_post=None,
                            )

            # Batch register websites for page agents
            pages_registered = 0
            if websites_data:
                pages_registered = self.content_service.add_websites_batch(websites_data)

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Agent registration complete",
                extra={
                    "extra_data": {
                        "registered": registered_count,
                        "skipped": skipped_count,
                        "pages": pages_registered,
                        "total": len(self.registered_agents),
                        "execution_time_ms": execution_time,
                    }
                },
            )

            self.logger.info(
                f"[Server] 👥 Agent Registration: {registered_count} new, {skipped_count} existing, {pages_registered} pages"
            )

            return {
                "registered": registered_count,
                "skipped": skipped_count,
                "pages": pages_registered,
                "total": len(self.registered_agents),
            }

        except Exception as e:
            self.logger.error(
                f"Agent registration error: {e}", extra={"extra_data": {"error": str(e)}}
            )
            self.logger.error(f"Agent registration error: {e}")
            raise

    @log_server_request
    def add_follow_relationship(self, follow_data: dict, client_id: str = None) -> bool:
        """
        Add a follow relationship to the database.

        This method is called by clients to create follow relationships,
        typically during initial social network setup from network.csv.

        Args:
            follow_data: Dictionary containing:
                - user_id: UUID of user being followed
                - follower_id: UUID of follower
                - action: 'follow' or 'unfollow'
                - round: Round ID (can be empty for initial setup)
            client_id: Optional client identifier for logging purposes

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success = self.follow_service.add_follow(follow_data)
            return success
        except Exception as e:
            self.logger.error(
                f"Error adding follow relationship: {e}",
                extra={"extra_data": {"error": str(e), "follow_data": follow_data}},
            )
            return False

    def check_network_edges_exist(self, edges: list) -> bool:
        """
        Check if any of the network edges already exist in the Follow table.

        This method checks if the social network from network.csv has already been loaded
        by verifying if any of the specified edges exist in the database.

        Args:
            edges: List of tuples (follower_id, user_id) representing network edges

        Returns:
            bool: True if any edge exists, False if none exist
        """
        if not edges:
            return False

        try:
            from sqlalchemy.orm import Session

            from YSimulator.YServer.classes.models import Follow

            with Session(self.db.engine) as session:
                # Check if any of the edges exist
                # We only need to find one to know the network was loaded
                for follower_id, user_id in edges[:NETWORK_EDGE_CHECK_LIMIT]:
                    exists = (
                        session.query(Follow)
                        .filter_by(follower_id=follower_id, user_id=user_id, action="follow")
                        .first()
                    )

                    if exists:
                        self.logger.info(
                            f"Network already loaded (found edge: {follower_id} -> {user_id})"
                        )
                        return True

                # None of the checked edges exist
                self.logger.info("Network not yet loaded (no edges found in database)")
                return False

        except Exception as e:
            self.logger.error(
                f"Error checking network edges: {e}", extra={"extra_data": {"error": str(e)}}
            )
            # On error, assume network not loaded to be safe
            return False

    @log_server_request
    def add_follow_relationships_batch(self, follows_data: list, client_id: str = None) -> int:
        """
        Add multiple follow relationships to the database in batch.

        This method is optimized for bulk insertion of follow relationships
        (e.g., loading initial social network from network.csv). It uses a single
        database transaction to insert all relationships, which is much faster than
        individual inserts.

        Args:
            follows_data: List of dictionaries, each containing:
                - user_id: UUID of user being followed
                - follower_id: UUID of follower
                - action: 'follow' or 'unfollow'
                - round: Round ID (can be empty for initial setup)
            client_id: Optional client identifier for logging purposes

        Returns:
            int: Number of follow relationships successfully added
        """
        try:
            count = self.follow_service.add_follows_batch(follows_data)
            self.logger.info(
                f"Batch added {count} follow relationships",
                extra={"extra_data": {"count": count, "batch_size": len(follows_data)}},
            )
            return count
        except Exception as e:
            self.logger.error(
                f"Error batch adding follow relationships: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(follows_data)}},
            )
            return 0

    def get_first_round_id(self) -> str:
        """
        Get the UUID of the first round (day 1, slot 1).

        This method retrieves or creates the first round entry in the database,
        which is used as the Round reference for initial network edges loaded
        from network.csv.

        Returns:
            str: UUID of the first round (day 1, slot 1)
        """
        try:
            # Get or create the first round (day 1, slot 1)
            first_round_id = self.simulation_service.get_or_create_round(1, 1)
            self.logger.info(f"Retrieved first round ID: {first_round_id}")
            return first_round_id
        except Exception as e:
            self.logger.error(
                f"Error getting first round ID: {e}", extra={"extra_data": {"error": str(e)}}
            )
            # Return empty string as fallback (better than crashing)
            return ""

    def check_follow_relationship(self, follower_id: str, user_id: str) -> bool:
        """
        Check if a follow relationship exists between two users.

        Args:
            follower_id: UUID of the follower
            user_id: UUID of the user being followed

        Returns:
            bool: True if follower follows user with action="follow", False otherwise
        """
        try:
            from sqlalchemy.orm import Session

            from YSimulator.YServer.classes.models import Follow

            with Session(self.db.engine) as session:
                # Check for active follow relationship
                # Get the most recent follow action between these users
                latest_follow = (
                    session.query(Follow)
                    .filter_by(follower_id=follower_id, user_id=user_id)
                    .order_by(Follow.round.desc())
                    .first()
                )

                # Return True if latest action is "follow", False otherwise
                return bool(latest_follow and latest_follow.action == "follow")

        except Exception as e:
            self.logger.error(
                f"Error checking follow relationship: {e}",
                extra={
                    "extra_data": {"error": str(e), "follower_id": follower_id, "user_id": user_id}
                },
            )
            return False

    @log_server_request
    def get_unreplied_mentions(self, user_id: str, client_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all unreplied mentions for a user.

        Args:
            user_id: UUID of the user
            client_id: Optional client identifier for logging purposes

        Returns:
            List[Dict]: List of mention records with keys: id, user_id, post_id, round, answered
        """
        result = self.mention_service.get_unreplied_mentions(user_id)
        self.logger.debug(
            f"[REPLY_SERVER] get_unreplied_mentions for user {user_id}: found {len(result)} unreplied mentions"
        )
        return result

    def mark_mention_replied(self, mention_id: str) -> bool:
        """
        Mark a mention as replied by setting answered=1.

        Args:
            mention_id: UUID of the mention

        Returns:
            bool: True if successful, False otherwise
        """
        # Use database adapter which has the correct signature for mention_id
        result = self.db.mark_mention_replied(mention_id)
        self.logger.debug(
            f"[REPLY_SERVER] mark_mention_replied for mention {mention_id}: success={result}"
        )
        return result

    @log_server_request
    def register_client(self, client_id: str, num_days: int = 0) -> dict:
        """
        Register a new client with the server.
        
        Delegates to ClientManager for client lifecycle management.

        Args:
            client_id: Unique identifier for the client
            num_days: Number of days this client plans to simulate (informational only)

        Returns:
            dict: {"registered": bool, "start_day": int, "start_slot": int}
        """
        return self.client_manager.register_client(
            client_id, num_days, self.day, self.slot
        )

    @log_server_request
    def complete_client(self, client_id: str) -> bool:
        """
        Mark a client as completed (finished all planned activities).
        
        Delegates to ClientManager for client lifecycle management.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if successfully marked as complete
        """
        result = self.client_manager.complete_client(client_id)
        
        # Check if completing this client unblocks the barrier
        self._check_barrier_and_advance()
        
        return result

    @log_server_request
    def heartbeat(self, client_id: str) -> bool:
        """
        Record a heartbeat from a client to indicate it's still alive.
        
        Delegates to ClientManager for heartbeat tracking.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if heartbeat recorded
        """
        return self.client_manager.heartbeat(client_id)

    def _get_active_clients(self) -> set:
        """
        Get the set of active clients (registered but not completed).
        
        Delegates to ClientManager.

        Returns:
            set: Set of active client IDs
        """
        return self.client_manager.get_active_clients()

    def _check_for_stale_clients(self):
        """
        Check for clients that haven't sent a heartbeat recently and remove them.
        
        Delegates to ClientManager for stale client detection.
        """
        self.client_manager.check_for_stale_clients()

    def _mark_client_as_completed(self, client_id: str):
        """
        Mark a client as completed internally.
        
        Delegates to ClientManager.

        Args:
            client_id: Unique identifier for the client
        """
        self.client_manager.mark_as_completed(client_id)

    @log_server_request
    def deregister_client(self, client_id: str) -> bool:
        """
        Remove a client from the server.
        
        Delegates to ClientManager for client deregistration.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if deregistration successful
        """
        result = self.client_manager.deregister_client(client_id)
        
        # Check if leaving unblocked the barrier
        self._check_barrier_and_advance()
        
        return result

    @log_server_request
    def get_instruction(self, client_id: str) -> SimulationInstruction:
        """
        Get the next simulation instruction for a client.

        The server provides the current day/slot. The client is responsible for
        tracking its own progress and deciding when to stop based on its start point
        and configured duration.

        Args:
            client_id: Unique identifier for the client

        Returns:
            SimulationInstruction: Instruction with status (WAIT/PROCEED) and current simulation state
        """
        # Check for stale clients before processing
        self._check_for_stale_clients()

        # 1. Pause if not enough players
        active_clients = self._get_active_clients()
        if len(active_clients) < self.min_to_start:
            return SimulationInstruction(status="WAIT")

        # 2. Wait if this client already finished the current slot
        if client_id in self.submitted_clients:
            return SimulationInstruction(status="WAIT")

        # 3. Proceed with current server state
        return SimulationInstruction(
            status="PROCEED", day=self.day, slot=self.slot, recent_post_ids=self.recent_posts_cache
        )

    @log_server_request
    def submit_actions(self, client_id: str, actions: list) -> None:
        """
        Submit actions from a client for the current simulation slot.

        Uses ActionRouter to dispatch actions to dedicated processors.

        Args:
            client_id: Unique identifier for the client
            actions: List of ActionDTO objects representing agent actions
        """
        start_time = time.time()
        new_ids = []

        try:
            # Create action context with current simulation state
            from YSimulator.YServer.action_processors.base_processor import ActionContext
            context = ActionContext(
                current_round_id=self.current_round_id,
                day=self.day,
                slot=self.slot
            )

            # Process each action through the router
            for act in actions:
                result = self.action_router.route(act, context)
                
                # Collect new post IDs from successful results
                if result.success and result.new_ids:
                    new_ids.extend(result.new_ids)

            # Update recent posts cache
            if new_ids:
                self.recent_posts_cache.extend(new_ids)
                self.recent_posts_cache = self.recent_posts_cache[-50:]  # Keep last 50

            # Update last_active_day for agents who performed actions
            if actions:
                active_agent_ids = set(act.agent_id for act in actions)
                for agent_id in active_agent_ids:
                    self.user_service.update_agent_last_active_day(agent_id, self.day)

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Actions submitted",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "day": self.day,
                        "slot": self.slot,
                        "num_actions": len(actions),
                        "num_posts": len(new_ids),
                        "execution_time_ms": execution_time,
                    }
                },
            )

        except Exception as e:
            self.logger.error(
                f"DB Error during action submission: {e}",
                extra={"extra_data": {"client_id": client_id, "error": str(e)}},
            )
            self.logger.error(f"DB Error: {e}")

        # Mark this specific client as done
        self.client_manager.mark_client_submitted(client_id)

        # Check if EVERYONE is done
        self._check_barrier_and_advance()


    def get_current_day(self) -> int:
        """
        Get the current simulation day.

        Returns:
            int: Current day number
        """
        return self.day

    def get_current_round_id(self) -> str:
        """
        Get the current round ID.

        Returns:
            str: Current round ID (UUID)
        """
        return self.current_round_id

    def get_inactive_agents(self, current_day: int, inactivity_threshold: int) -> List[str]:
        """
        Get list of inactive agents from database (simple database wrapper for client use).

        Args:
            current_day: Current simulation day
            inactivity_threshold: Number of days of inactivity to consider

        Returns:
            List of agent IDs (strings) that are inactive
        """
        return self.user_service.get_inactive_agents(current_day, inactivity_threshold)

    def set_agent_churned(self, agent_id: str, round_id: str) -> bool:
        """
        Mark an agent as churned (simple database wrapper for client use).

        Args:
            agent_id: Agent ID to churn
            round_id: Round ID when agent churned

        Returns:
            bool: True if successful
        """
        return self.user_service.set_agent_churned(agent_id, round_id)

    def set_agents_churned_batch(self, agent_ids: List[str], round_id: str) -> int:
        """
        Mark multiple agents as churned in a batch operation (simple database wrapper for client use).

        Args:
            agent_ids: List of agent IDs to churn
            round_id: Round ID when agents churned

        Returns:
            int: Number of agents successfully churned
        """
        churned_count = 0
        for agent_id in agent_ids:
            if self.user_service.set_agent_churned(agent_id, round_id):
                churned_count += 1
        return churned_count

    def get_churned_agents(self) -> List[str]:
        """
        Get list of all churned agents (simple database wrapper for client use).

        Returns:
            List of agent IDs (UUID strings) that are churned
        """
        return self.user_service.get_churned_agents()

    def add_website(self, website_data: dict) -> Optional[str]:
        """
        Add a website (news source) to the database.

        This is a wrapper method that can be called remotely from Ray actors.

        Args:
            website_data: Dictionary containing website information

        Returns:
            str: Website ID if successful, None otherwise
        """
        return self.content_service.add_website(website_data)

    def get_website_by_rss(self, rss_url: str) -> Optional[dict]:
        """
        Get website information by RSS URL.

        This is a wrapper method that can be called remotely from Ray actors.

        Args:
            rss_url: RSS feed URL

        Returns:
            dict: Website information if found, None otherwise
        """
        return self.content_service.get_website_by_rss(rss_url)

    def add_article(self, article_data: dict) -> Optional[str]:
        """
        Add a news article to the database.

        This is a wrapper method that can be called remotely from Ray actors.

        Args:
            article_data: Dictionary containing article information

        Returns:
            str: Article ID if successful, None otherwise
        """
        return self.article_service.add_article(article_data)

    def add_image(self, image_data: dict) -> Optional[str]:
        """
        Add an image to the database.

        This is a wrapper method that can be called remotely from Ray actors.

        Args:
            image_data: Dictionary containing image information (url, description, article_id)

        Returns:
            str: Image ID if successful, None otherwise
        """
        return self.image_service.add_image(image_data)

    def get_random_image(self) -> Optional[dict]:
        """
        Get a random image from the database.

        This is a wrapper method that can be called remotely from Ray actors.

        Returns:
            dict: Image data or None if no images available
        """
        return self.image_service.get_random_image()

    def get_interest_by_id(self, interest_id: str) -> Optional[dict]:
        """
        Get interest details by ID.

        This is a wrapper method that can be called remotely from Ray actors.

        Args:
            interest_id: Interest UUID

        Returns:
            dict: Interest data or None if not found
        """
        return self.interest_service.get_interest_by_id(interest_id)

    def _check_barrier_and_advance(self) -> None:
        """
        Check if all active clients have submitted actions and advance simulation state.
        
        Delegates to BarrierHandler and RoundManager for coordination logic.
        """
        active_clients = self._get_active_clients()
        
        # Check if barrier should be released
        should_advance = self.barrier_handler.check_barrier_and_should_advance(
            active_clients, self.submitted_clients
        )
        
        if should_advance:
            # Clear submitted clients for next round
            self.client_manager.clear_submitted_clients()
            
            # Advance simulation using RoundManager
            result = self.round_manager.advance_simulation(
                recompute_interests_callback=self._recompute_all_agent_interests
            )
            
            # Check if it's time for archetype transitions (every 7 days)
            if result["day_completed"] and self.archetype_manager.should_perform_transitions(self.day):
                self.archetype_manager.perform_transitions(self.day)

    def _perform_archetype_transitions(self) -> None:
        """
        Perform archetype transitions for all registered agents.
        
        Delegates to ArchetypeManager for transition logic.
        """
        self.archetype_manager.perform_transitions(self.day)

    def _calculate_visibility_params(self, visibility_rounds: int) -> tuple:
        """
        Calculate visibility day/hour parameters for filtering posts.

        Since Round IDs are UUIDs (not sequential integers), we calculate
        the day/hour threshold instead of trying to do arithmetic on UUIDs.

        Args:
            visibility_rounds: Number of time slots to look back

        Returns:
            tuple: (visibility_day, visibility_hour) representing the oldest round to show
        """
        # Use num_slots_per_day from config, with fallback to 24
        slots_per_day = getattr(self, "num_slots_per_day", 24)

        total_hours = (self.day - 1) * slots_per_day + self.slot
        visibility_hours = max(1, total_hours - visibility_rounds)
        visibility_day = (visibility_hours - 1) // slots_per_day + 1
        visibility_hour = (visibility_hours - 1) % slots_per_day + 1
        return visibility_day, visibility_hour

    def _save_recommendation(self, agent_id: str, post_ids: List[str]) -> None:
        """
        Save recommendations to the database (and Redis if enabled).

        Stores the list of recommended posts for an agent in the current round,
        formatted as a pipe-separated string (e.g., "post_id1|post_id2|post_id3").

        Args:
            agent_id: UUID of the agent receiving recommendations
            post_ids: List of post UUIDs recommended to the agent
        """
        if not post_ids:
            return

        try:
            from sqlalchemy.orm import Session

            # Format post IDs as pipe-separated string (original implementation format)
            post_ids_str = "|".join(post_ids)
            recommendation_id = str(uuid.uuid4())

            # Save to SQL database using SQLAlchemy ORM
            session = Session(self.db.engine)
            try:
                recommendation = Recommendation(
                    id=recommendation_id,
                    user_id=agent_id,
                    post_ids=post_ids_str,
                    round=self.current_round_id,
                )
                session.add(recommendation)
                session.commit()
            finally:
                session.close()

            # Also save to Redis if enabled
            if self.use_redis:
                # Store recommendation in Redis with key format: ysim:recommendations:{user_id}:{round_id}
                rec_key = f"ysim:recommendations:{agent_id}:{self.current_round_id}"
                self.redis_client.set(rec_key, post_ids_str)
                # Set TTL to prevent unbounded growth
                self.redis_client.expire(rec_key, RECOMMENDATION_TTL_SECONDS)

            self.logger.debug(
                f"Saved recommendation for agent {agent_id}: {len(post_ids)} posts",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "round": self.current_round_id,
                        "post_count": len(post_ids),
                    }
                },
            )

        except Exception as e:
            self.logger.error(
                f"Error saving recommendation: {e}",
                extra={"extra_data": {"agent_id": agent_id, "error": str(e)}},
            )

    @log_server_request
    def get_recommended_posts(
        self,
        agent_id: str,
        mode: str = "random",
        limit: int = 5,
        followers_ratio: float = 0.6,
        client_id: str = None,
    ) -> List[str]:
        """
        Get recommended posts for an agent using the specified recommendation strategy.
        
        Delegates to ContentRecommender for recommendation logic.

        Args:
            agent_id: UUID of the agent requesting recommendations
            mode: Recommendation mode (random, rchrono, rchrono_popularity, etc.)
            limit: Number of posts to recommend (default: 5)
            followers_ratio: Ratio of posts from followers vs others (default: 0.6)
            client_id: Client ID (for logging)

        Returns:
            List[str]: List of post UUIDs recommended for the agent
        """
        # Delegate to ContentRecommender
        post_ids = self.content_recommender.get_recommended_posts(
            agent_id=agent_id,
            mode=mode,
            limit=limit,
            followers_ratio=followers_ratio,
            day=self.day,
            slot=self.slot,
        )
        
        # Save recommendations to database (and Redis if enabled)
        if post_ids:
            self._save_recommendation(agent_id, post_ids)
        
        return post_ids

    @log_server_request
    def get_post(self, post_id: str, client_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get a post by its ID.

        Args:
            post_id: UUID of the post to retrieve
            client_id: Optional client identifier for logging purposes

        Returns:
            Dictionary with post data or None if not found
        """
        return self.post_service.get_post(post_id)

    @log_server_request
    def get_thread_context(
        self, post_id: str, max_length: int = 5, client_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get thread context for a post - retrieve up to max_length posts/comments
        that immediately precede the target post in the discussion thread.

        Returns posts in chronological order (oldest first) to allow the agent
        to follow the discussion thread.

        Args:
            post_id: UUID of the post to get context for
            max_length: Maximum number of preceding posts/comments to return
            client_id: Optional client identifier for logging purposes

        Returns:
            List of dicts with keys: id, user_id, username, tweet, round
            in chronological order (oldest first)
        """
        return self.post_service.get_thread_context(post_id, max_length)

    @log_server_request
    def get_user(self, user_id: str, client_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get a user by their ID.

        Args:
            user_id: UUID of the user to retrieve
            client_id: Optional client identifier for logging purposes

        Returns:
            Dictionary with user data or None if not found
        """
        return self.user_service.get_user(user_id)

    @log_server_request
    def search_posts_by_topic(
        self, topic_id: str, agent_id: str, limit: int = 10, client_id: str = None
    ) -> List[str]:
        """
        Search for recent posts on a specific topic from other users.

        Args:
            topic_id: Topic/interest UUID to search for
            agent_id: Agent UUID (to exclude agent's own posts)
            limit: Maximum number of posts to return (default: 10)

        Returns:
            List[str]: List of post UUIDs from other users on this topic
        """
        return self.post_service.search_posts_by_topic(topic_id, agent_id, limit)

    @log_server_request
    def get_post_topics(self, post_id: str, client_id: str = None) -> List[str]:
        """
        Get topic IDs associated with a post.

        Args:
            post_id: UUID of the post
            client_id: Optional client identifier for logging

        Returns:
            List of topic UUIDs
        """
        return self.post_service.get_post_topics(post_id)

    @log_server_request
    def get_topic_name_from_id(self, topic_id: str, client_id: str = None) -> Optional[str]:
        """
        Get topic name from topic UUID.

        Args:
            topic_id: Topic UUID (iid)
            client_id: Optional client identifier for logging

        Returns:
            Topic name or None if not found
        """
        return self._get_topic_name_from_id(topic_id)

    @log_server_request
    def get_latest_agent_opinion(
        self, agent_id: str, topic_id: str, client_id: str = None
    ) -> Optional[float]:
        """
        Get the latest opinion value for an agent on a topic.
        
        Delegates to OpinionHandler for opinion retrieval.

        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            client_id: Optional client identifier for logging

        Returns:
            Latest opinion value or None if not found
        """
        return self.opinion_handler.get_latest_opinion(agent_id, topic_id)

    @log_server_request
    def add_agent_opinion(
        self,
        agent_id: str,
        topic_id: str,
        opinion: float,
        id_interacted_with: Optional[str] = None,
        id_post: Optional[str] = None,
        client_id: str = None,
    ) -> bool:
        """
        Add an agent opinion record to the database.
        
        Delegates to OpinionHandler for opinion storage.

        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            opinion: Opinion value in [0, 1]
            id_interacted_with: Optional UUID of agent interacted with
            id_post: Optional UUID of post interacted with
            client_id: Optional client identifier for logging

        Returns:
            True if successful, False otherwise
        """
        return self.opinion_handler.add_opinion(
            agent_id, topic_id, opinion, id_interacted_with, id_post
        )

    @log_server_request
    def get_neighbors_opinions(
        self, agent_id: str, topic_id: str, client_id: str = None
    ) -> List[float]:
        """
        Get the opinions of an agent's neighbors (followees) on a specific topic.
        
        Delegates to OpinionHandler for neighbor opinion retrieval.

        This method retrieves the latest opinions of all users that the agent follows
        on the specified topic. Used for LLM-based opinion dynamics with evaluation_scope="neighbors".

        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            client_id: Optional client identifier for logging

        Returns:
            List of opinion values (floats in [0, 1]) from the agent's neighbors
        """
        return self.opinion_handler.get_neighbors_opinions(agent_id, topic_id)

    @log_server_request
    def get_follow_suggestions(
        self,
        agent_id: str,
        mode: str = "random",
        n_neighbors: int = 10,
        leaning_bias: int = 1,
        client_id: str = None,
    ) -> List[str]:
        """
        Get follow suggestions for an agent using the specified recommendation strategy.

        This method implements various link prediction and recommendation algorithms
        using efficient query-based approaches for scalability.

        Args:
            agent_id: UUID of the agent requesting follow suggestions
            mode: Recommendation mode:
                - "random": Random user suggestions (default)
                - "common_neighbors": Users with mutual connections
                - "jaccard": Jaccard coefficient-based similarity
                - "adamic_adar": Adamic/Adar index for link prediction
                - "preferential_attachment": Rich-get-richer recommendation
            n_neighbors: Number of users to suggest (default: 10)
            leaning_bias: Political leaning bias factor (1 = no bias, higher = more homophily)

        Returns:
            List[str]: List of user UUIDs recommended for the agent to follow
        """
        if self.db.use_redis:
            return self._get_follow_suggestions_redis(agent_id, mode, n_neighbors, leaning_bias)
        else:
            return self._get_follow_suggestions_sql(agent_id, mode, n_neighbors, leaning_bias)

    def _get_follow_suggestions_sql(
        self, agent_id: str, mode: str, n_neighbors: int, leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using SQL queries.
        
        Delegates to FollowRecommender for recommendation logic.
        """
        return self.follow_recommender.get_follow_suggestions(
            agent_id=agent_id,
            mode=mode,
            n_neighbors=n_neighbors,
            leaning_bias=leaning_bias,
        )

    def _get_follow_suggestions_redis(
        self, agent_id: str, mode: str, n_neighbors: int, leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using Redis.
        
        Delegates to FollowRecommender for recommendation logic.
        """
        return self.follow_recommender.get_follow_suggestions(
            agent_id=agent_id,
            mode=mode,
            n_neighbors=n_neighbors,
            leaning_bias=leaning_bias,
        )
