"""
YServer - Orchestrator Server for YSimulator.

This module contains the Ray remote actor that orchestrates the simulation,
managing client registration, agent actions, and simulation state progression.
"""

import json
import logging
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import ray

from YSimulator.YClient.classes.ray_models import SimulationInstruction
from YSimulator.YServer.recsys import content_recsys_db, content_recsys_redis, follow_recsys_db
from YSimulator.YServer.classes.models import Recommendation
from YSimulator.YServer.interests_modeling import InterestManager


# Constants
RECOMMENDATION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds
NETWORK_EDGE_CHECK_LIMIT = 10  # Number of edges to check when verifying network load


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
        from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware

        # Server configuration
        self.min_to_start = min_to_start
        self.server_name = server_name
        self.config_path = Path(config_path)
        self.timeout_seconds = timeout_seconds

        # Archetype configuration
        if simulation_config is None:
            simulation_config = {}
        self.archetype_config = simulation_config.get("agent_archetypes", {})
        self.archetypes_enabled = self.archetype_config.get("enabled", False)
        self.archetype_distribution = self.archetype_config.get("distribution", {})
        self.archetype_transitions = self.archetype_config.get("transitions", {})
        
        # Track last archetype transition day (start at 0, so first transition at day 7)
        self.last_archetype_transition_day = 0
        
        # Simulation timing configuration
        self.num_slots_per_day = simulation_config.get("simulation", {}).get("num_slots_per_day", 24)
        
        # Store visibility_rounds for server use
        self.visibility_rounds = simulation_config.get("posts", {}).get("visibility_rounds", 36)
        
        # Store attention_window for interest decay (sliding window)
        self.attention_window = simulation_config.get("agents", {}).get("attention_window", 336)

        # Client tracking
        self.registered_clients = set()  # All registered clients
        self.completed_clients = set()  # Clients that finished their simulation
        self.submitted_clients = set()  # Clients that submitted for current slot
        self.last_heartbeat = {}  # {client_id: timestamp}
        self.registered_agents = {}  # {agent_id: username}

        # Simulation state
        self.day = 1
        self.slot = 1
        self.recent_posts_cache = []
        self.current_round_id = None  # Will be set when simulation starts

        # Set up logging first
        self._setup_logging()

        # Initialize database middleware
        self.db = DatabaseMiddleware(
            db_config=db_config,
            config_path=str(self.config_path),
            redis_config=redis_config,
            logger=self.logger,
            simulation_config=simulation_config,
        )
        
        # Initialize Interest Manager for topic/interest tracking
        self.interest_manager = InterestManager(
            db_middleware=self.db,
            attention_window=self.attention_window
        )
        
        # Initialize the first round entry
        self.current_round_id = self.db.get_or_create_round(self.day, self.slot)
        self.interest_manager.set_current_round(self.current_round_id)
        
        # Initialize emotions table with GoEmotions taxonomy
        self.db.initialize_emotions_table()

        self.logger.info(
            "Orchestrator server initialized",
            extra={
                "extra_data": {
                    "db_type": db_config.get("type", "sqlite"),
                    "min_to_start": min_to_start,
                    "redis_enabled": self.db.use_redis,
                    "timeout_seconds": timeout_seconds,
                    "archetypes_enabled": self.archetypes_enabled,
                }
            },
        )

    def _setup_logging(self):
        """Set up JSON logging for the server actor."""
        log_dir = self.config_path / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"{self.server_name}_actor.log"

        # Create logger
        self.logger = logging.getLogger(f"YSimulator.Server.{self.server_name}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Create file handler with JSON formatting
        from logging.handlers import RotatingFileHandler

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
            self.logger.info(f"Mapped reaction {reaction_type} to sentiment: compound={result['compound']}")
        else:
            self.logger.debug(f"Reaction type {reaction_type} not mapped to sentiment (e.g., IGNORE)")
        return result
    
    def _process_annotations(
        self, 
        post_id: str, 
        user_id: str, 
        annotations: dict, 
        is_post: bool = False, 
        is_comment: bool = False,
        parent_post_id: Optional[str] = None,
        parent_sentiment: Optional[float] = None
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
        self.logger.info(f"_process_annotations called for post {post_id}: has_hashtags={bool(annotations.get('hashtags'))}, has_mentions={bool(annotations.get('mentions'))}, has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}")
        
        # Process hashtags
        hashtags = annotations.get("hashtags", [])
        for hashtag_text in hashtags:
            # Get or create hashtag
            hashtag_id = self.db.add_or_get_hashtag(hashtag_text)
            if hashtag_id:
                # Link hashtag to post
                self.db.add_post_hashtag(post_id, hashtag_id)
                self.logger.info(f"Linked hashtag '{hashtag_text}' to post {post_id}")
        
        # Process mentions
        mentions = annotations.get("mentions", [])
        for username in mentions:
            # Check if user exists
            mentioned_user = self.db.get_user_by_username(username)
            if mentioned_user:
                # Add mention entry
                mention_data = {
                    "user_id": mentioned_user["id"],
                    "post_id": post_id,
                    "round": self.current_round_id,
                    "answered": 0
                }
                self.db.add_mention(mention_data)
                self.logger.info(f"Added mention of @{username} in post {post_id}")
            else:
                self.logger.warning(f"Mentioned user @{username} not found in database")
        
        # Process sentiment
        sentiment_scores = annotations.get("sentiment")
        if sentiment_scores:
            self.logger.info(f"Processing sentiment for post {post_id}: compound={sentiment_scores.get('compound', 0):.3f}")
            # Get topics associated with this post/comment
            topic_ids = self.db.get_post_topics(post_id)
            
            # If comment without topics yet, get parent's topics
            if not topic_ids and parent_post_id:
                topic_ids = self.db.get_post_topics(parent_post_id)
                if topic_ids:
                    self.logger.info(f"Using {len(topic_ids)} topics from parent post {parent_post_id} for comment {post_id}")
            
            if not topic_ids:
                self.logger.warning(f"No topics found for post {post_id}, skipping sentiment storage. Sentiment data will not be saved.")
            
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
                    "is_reaction": 0
                }
                success = self.db.add_post_sentiment(sentiment_data)
                if success:
                    self.logger.info(f"Added sentiment entry for post {post_id}, topic {topic_id}")
                else:
                    self.logger.error(f"Failed to add sentiment entry for post {post_id}, topic {topic_id}")
            
            if topic_ids:
                self.logger.info(f"Successfully added sentiment for post {post_id} across {len(topic_ids)} topics")
        else:
            self.logger.debug(f"No sentiment data in annotations for post {post_id}")
        
        # Process toxicity
        toxicity_scores = annotations.get("toxicity")
        if toxicity_scores:
            self.logger.info(f"Processing toxicity for post {post_id}: TOXICITY={toxicity_scores.get('TOXICITY', 0):.3f}")
            toxicity_data = {
                "post_id": post_id,
                "toxicity": toxicity_scores.get("TOXICITY", 0.0),
                "severe_toxicity": toxicity_scores.get("SEVERE_TOXICITY", 0.0),
                "identity_attack": toxicity_scores.get("IDENTITY_ATTACK", 0.0),
                "insult": toxicity_scores.get("INSULT", 0.0),
                "profanity": toxicity_scores.get("PROFANITY", 0.0),
                "threat": toxicity_scores.get("THREAT", 0.0),
                "sexually_explicit": toxicity_scores.get("SEXUALLY_EXPLICIT", 0.0),
                "flirtation": toxicity_scores.get("FLIRTATION", 0.0)
            }
            success = self.db.add_post_toxicity(toxicity_data)
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
                emotion = self.db.get_emotion_by_name(emotion_name)
                if emotion:
                    # Add post emotion association
                    success = self.db.add_post_emotion(post_id, emotion["id"])
                    if success:
                        self.logger.info(f"Added emotion '{emotion_name}' to post {post_id}")
                    else:
                        self.logger.error(f"Failed to add emotion '{emotion_name}' to post {post_id}")
                else:
                    self.logger.warning(f"Emotion '{emotion_name}' not found in database for post {post_id}")
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

    def register_agents(self, agents: list) -> dict:
        """
        Register agent profiles in the database if they don't already exist.
        For page agents (is_page=1), also creates a Website entry.

        Args:
            agents: List of AgentProfile dataclass instances

        Returns:
            dict: Summary of registration results with counts
        """
        start_time = time.time()
        registered_count = 0
        skipped_count = 0
        pages_registered = 0

        try:
            for agent_profile in agents:
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
                    "joined_on": self.current_round_id,  # FK to rounds table (UUID string)
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
                }

                # Try to register user
                user_registered = self.db.register_user(user_data)
                if user_registered:
                    registered_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    
                    # Initialize agent interests using InterestManager
                    if agent_profile.interests:
                        self.interest_manager.initialize_agent_interests(
                            agent_id=str(agent_profile.id),
                            interests=agent_profile.interests,
                            round_id=self.current_round_id
                        )
                    
                    # If this is a page agent, create a Website entry
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
                        if self.db.add_website(website_data):
                            pages_registered += 1
                        else:
                            self.logger.warning(
                                f"Failed to create website for page {agent_profile.username}",
                                extra={"extra_data": {"page_id": str(agent_profile.id)}}
                            )
                else:
                    skipped_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    
                    # If page already exists, ensure its Website entry also exists
                    if agent_profile.is_page == 1 and agent_profile.feed_url:
                        # Check if website exists
                        website_data = self.db.get_website_by_rss(agent_profile.feed_url)
                        if website_data:
                            pages_registered += 1
                        else:
                            # Website doesn't exist, create it now
                            self.logger.info(
                                f"Creating missing website for existing page {agent_profile.username}",
                                extra={"extra_data": {"page_id": str(agent_profile.id)}}
                            )
                            website_data = {
                                "id": str(agent_profile.id),  # Website ID = User ID
                                "name": agent_profile.username,  # Use username as website name
                                "rss": agent_profile.feed_url,
                                "category": "page",  # Mark as page
                                "language": agent_profile.language,
                                "country": agent_profile.nationality,
                                "leaning": agent_profile.leaning,
                            }
                            if self.db.add_website(website_data):
                                pages_registered += 1
                            else:
                                self.logger.warning(
                                    f"Failed to create website for existing page {agent_profile.username}",
                                    extra={"extra_data": {"page_id": str(agent_profile.id)}}
                                )

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

            print(
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
            print(f"[Server] ❌ Agent registration error: {e}")
            raise

    def add_follow_relationship(self, follow_data: dict) -> bool:
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
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success = self.db.add_follow(follow_data)
            return success
        except Exception as e:
            self.logger.error(
                f"Error adding follow relationship: {e}",
                extra={"extra_data": {"error": str(e), "follow_data": follow_data}}
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
                    exists = session.query(Follow).filter_by(
                        follower_id=follower_id,
                        user_id=user_id,
                        action="follow"
                    ).first()
                    
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
                f"Error checking network edges: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            # On error, assume network not loaded to be safe
            return False

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
            first_round_id = self.db.get_or_create_round(1, 1)
            self.logger.info(f"Retrieved first round ID: {first_round_id}")
            return first_round_id
        except Exception as e:
            self.logger.error(
                f"Error getting first round ID: {e}",
                extra={"extra_data": {"error": str(e)}}
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
                latest_follow = session.query(Follow).filter_by(
                    follower_id=follower_id,
                    user_id=user_id
                ).order_by(Follow.round.desc()).first()
                
                # Return True if latest action is "follow", False otherwise
                return latest_follow and latest_follow.action == "follow"
                
        except Exception as e:
            self.logger.error(
                f"Error checking follow relationship: {e}",
                extra={"extra_data": {"error": str(e), "follower_id": follower_id, "user_id": user_id}}
            )
            return False

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all unreplied mentions for a user.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            List[Dict]: List of mention records with keys: id, user_id, post_id, round, answered
        """
        result = self.db.get_unreplied_mentions(user_id)
        self.logger.debug(f"[REPLY_SERVER] get_unreplied_mentions for user {user_id}: found {len(result)} unreplied mentions")
        return result

    def mark_mention_replied(self, mention_id: str) -> bool:
        """
        Mark a mention as replied by setting answered=1.
        
        Args:
            mention_id: UUID of the mention
            
        Returns:
            bool: True if successful, False otherwise
        """
        result = self.db.mark_mention_replied(mention_id)
        self.logger.debug(f"[REPLY_SERVER] mark_mention_replied for mention {mention_id}: success={result}")
        return result


    def register_client(self, client_id: str, num_days: int = 0) -> dict:
        """
        Register a new client with the server.

        Provides the current server state (day and slot) as the starting point.
        The client will handle its own simulation step counting from this point.

        Args:
            client_id: Unique identifier for the client
            num_days: Number of days this client plans to simulate (informational only)

        Returns:
            dict: {"registered": bool, "start_day": int, "start_slot": int}
        """
        start_time = time.time()

        if client_id not in self.registered_clients:
            self.registered_clients.add(client_id)
            self.last_heartbeat[client_id] = time.time()
            
            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Client registered",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "start_day": self.day,
                        "start_slot": self.slot,
                        "num_days": num_days,
                        "total_clients": len(self.registered_clients),
                        "active_clients": len(self._get_active_clients()),
                        "execution_time_ms": execution_time,
                    }
                },
            )
            print(
                f"[Server] 🟢 Client {client_id} joined at day {self.day}, slot {self.slot}. "
                f"Will run for {num_days if num_days > 0 else '∞'} days. "
                f"Total: {len(self.registered_clients)}, Active: {len(self._get_active_clients())}"
            )
        
        # Return current server state as starting point for client
        return {
            "registered": True,
            "start_day": self.day,
            "start_slot": self.slot,
        }

    def complete_client(self, client_id: str) -> bool:
        """
        Mark a client as completed (finished all planned activities).

        Completed clients no longer block barrier advancement. This allows
        clients with different simulation durations to coexist without deadlocks.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if successfully marked as complete
        """
        if client_id in self.registered_clients:
            self._mark_client_as_completed(client_id)

            self.logger.info(
                "Client completed all activities",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "remaining_active": len(self._get_active_clients()),
                        "total_completed": len(self.completed_clients),
                    }
                },
            )
            print(
                f"[Server] 🏁 Client {client_id} completed. "
                f"Active: {len(self._get_active_clients())}, "
                f"Completed: {len(self.completed_clients)}"
            )

            # Check if completing this client unblocks the barrier
            self._check_barrier_and_advance()
        return True

    def heartbeat(self, client_id: str) -> bool:
        """
        Record a heartbeat from a client to indicate it's still alive.

        Prevents the server from considering the client stale and removing it.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if heartbeat recorded
        """
        if client_id in self.registered_clients:
            self.last_heartbeat[client_id] = time.time()
        return True

    def _get_active_clients(self) -> set:
        """
        Get the set of active clients (registered but not completed).

        Returns:
            set: Set of active client IDs
        """
        return self.registered_clients - self.completed_clients

    def _check_for_stale_clients(self):
        """
        Check for clients that haven't sent a heartbeat recently and remove them.

        Heartbeat-based liveness: Clients are only considered stale if they stop
        sending heartbeats. Processing time doesn't matter - if heartbeats arrive,
        the client is alive. This prevents false positives on slow/busy clients.
        """
        current_time = time.time()
        stale_clients = []
        stale_clients_info = {}  # Store time_since_heartbeat for each stale client

        for client_id in self._get_active_clients():
            # Check if heartbeat was ever received (should be set during registration)
            if client_id not in self.last_heartbeat:
                # This shouldn't happen, but log and skip to avoid crashes
                self.logger.warning(
                    f"Active client {client_id} has no heartbeat entry, initializing",
                    extra={"extra_data": {"client_id": client_id}}
                )
                self.last_heartbeat[client_id] = current_time
                continue
                
            last_hb = self.last_heartbeat[client_id]
            time_since_heartbeat = current_time - last_hb
            
            # Only mark as stale if no heartbeat received within timeout
            # Note: Clients send heartbeat every heartbeat_interval seconds,
            # so timeout_seconds should be >> heartbeat_interval to account for
            # network delays and processing variations
            if time_since_heartbeat > self.timeout_seconds:
                stale_clients.append(client_id)
                stale_clients_info[client_id] = time_since_heartbeat

        for client_id in stale_clients:
            time_since_heartbeat = stale_clients_info[client_id]
            self.logger.warning(
                "Removing stale client (no heartbeat)",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "timeout_seconds": self.timeout_seconds,
                        "last_heartbeat_ago": time_since_heartbeat,
                    }
                },
            )
            print(
                f"[Server] ⚠️  Removing stale client {client_id} "
                f"(no heartbeat for {time_since_heartbeat:.1f}s)"
            )
            self._mark_client_as_completed(client_id)

    def _mark_client_as_completed(self, client_id: str):
        """
        Mark a client as completed internally.

        Helper method to avoid code duplication between complete_client and stale detection.

        Args:
            client_id: Unique identifier for the client
        """
        self.completed_clients.add(client_id)
        self.submitted_clients.discard(client_id)

    def deregister_client(self, client_id: str) -> bool:
        """
        Remove a client from the server.

        Optional: Call this if a client shuts down gracefully.
        Otherwise, the server might hang waiting for a dead client.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if deregistration successful
        """
        if client_id in self.registered_clients:
            self.registered_clients.remove(client_id)
            # Clean up all tracking data for this client
            self.submitted_clients.discard(client_id)
            self.completed_clients.discard(client_id)
            self.last_heartbeat.pop(client_id, None)

            self.logger.info(
                "Client deregistered",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "remaining_clients": len(self.registered_clients),
                    }
                },
            )
            print(f"[Server] 🔴 Client {client_id} left. Total: {len(self.registered_clients)}")

            # Check if leaving unblocked the barrier
            self._check_barrier_and_advance()
        return True

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

    def submit_actions(self, client_id: str, actions: list) -> None:
        """
        Submit actions from a client for the current simulation slot.

        Args:
            client_id: Unique identifier for the client
            actions: List of ActionDTO objects representing agent actions
        """
        start_time = time.time()
        new_ids = []

        try:
            for act in actions:
                if act.action_type == "POST":
                    post_data = {
                        "user_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string)
                        "tweet": act.content,  # Post content field
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    # Add article_id (news_id) if this is a news post
                    article_id = None
                    if hasattr(act, 'article_id') and act.article_id:
                        post_data["news_id"] = act.article_id
                        article_id = act.article_id
                    
                    post_id = self.db.add_post(post_data)
                    if post_id:
                        new_ids.append(post_id)
                        
                        # If this is an article post, extract and store topics
                        if article_id:
                            # Get article details from database
                            article_data = self.db.get_article(article_id)
                            if article_data:
                                # Extract topics using LLM (checks if already extracted)
                                # Note: We need the LLM service handle - we'll get it from the client context
                                # For now, check if article already has topics
                                existing_topic_ids = self.db.get_article_topics(article_id)
                                
                                if existing_topic_ids:
                                    # Article already has topics, link them to the post
                                    for topic_id in existing_topic_ids:
                                        self.db.add_post_topic(post_id, topic_id)
                                    self.logger.info(f"Linked {len(existing_topic_ids)} existing article topics to post {post_id}")
                                # If no existing topics, they will need to be extracted by client before posting
                        
                        # Save post topic if provided (for non-article posts)
                        elif hasattr(act, 'topic') and act.topic:
                            # Get or create the topic in interests table
                            topic_id = self.db.add_or_get_interest(act.topic)
                            if topic_id:
                                # Save post-topic association
                                self.db.add_post_topic(post_id, topic_id)
                                
                                # Increment the agent's interest counter for this topic
                                self._update_agent_interest_counter(act.agent_id, act.topic, increment=1)
                        
                        # Process annotations AFTER topics are assigned
                        if hasattr(act, 'annotations') and act.annotations:
                            self._process_annotations(post_id, act.agent_id, act.annotations, is_post=True, is_comment=False)
                    else:
                        self.logger.warning(
                            f"Failed to add post for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id}},
                        )
                
                elif act.action_type == "COMMENT":
                    # Comments are stored as posts with comment_to set
                    # Get the parent post to inherit thread_id (which points to the root of the thread)
                    parent_post = self.db.get_post(act.target_post_id)
                    if parent_post:
                        # Get thread_id from parent - this will point to the root post
                        # because:
                        # 1. If parent is a root post, thread_id equals parent's ID
                        # 2. If parent is a comment, it already inherited root's thread_id
                        # So we recursively inherit the correct root thread_id
                        thread_id = parent_post.get("thread_id")
                        
                        # Fallback: If parent doesn't have thread_id (legacy data), 
                        # assume parent IS the root post
                        if not thread_id:
                            thread_id = act.target_post_id
                        
                        post_data = {
                            "user_id": str(act.agent_id),
                            "tweet": act.content,
                            "round": self.current_round_id,
                            "comment_to": act.target_post_id,  # Points to immediate parent
                            "thread_id": thread_id,  # Points to root post of thread
                        }
                        post_id = self.db.add_post(post_data)
                        if post_id:
                            new_ids.append(post_id)
                            
                            # Process annotations if provided
                            if hasattr(act, 'annotations') and act.annotations:
                                # Get parent post sentiment for sentiment_parent field
                                parent_sentiment = None
                                if parent_post:
                                    # Query database to get sentiment of parent post
                                    parent_sentiment_data = self.db.get_post_sentiment(act.target_post_id)
                                    if parent_sentiment_data is not None:
                                        sentiment_parent_compound = parent_sentiment_data.get("compound")
                                        if sentiment_parent_compound is not None:
                                            # Apply thresholding
                                            if sentiment_parent_compound > 0.05:
                                                parent_sentiment = "pos"
                                            elif sentiment_parent_compound < -0.05:
                                                parent_sentiment = "neg"
                                            else:
                                                parent_sentiment = "neu"
                                            self.logger.info(f"Parent sentiment for comment {post_id}: compound={sentiment_parent_compound:.3f} -> {parent_sentiment}")
                                        else:
                                            parent_sentiment = ""
                                            self.logger.debug(f"Parent sentiment compound is None for post {act.target_post_id}")
                                    else:
                                        parent_sentiment = ""
                                        self.logger.debug(f"No sentiment data found for parent post {act.target_post_id}")
                                
                                self._process_annotations(post_id, act.agent_id, act.annotations, is_post=False, is_comment=True, parent_post_id=act.target_post_id, parent_sentiment=parent_sentiment)
                            
                            # When commenting on a post, save the post's topics as user interests
                            parent_post_id = act.target_post_id
                            topic_ids = self.db.get_post_topics(parent_post_id)
                            for topic_id in topic_ids:
                                self.db.add_user_interest(
                                    user_id=str(act.agent_id),
                                    interest_id=topic_id,
                                    round_id=self.current_round_id
                                )
                                
                                # Increment the agent's interest counter for this topic
                                topic_name = self._get_topic_name_from_id(topic_id)
                                if topic_name:
                                    self._update_agent_interest_counter(act.agent_id, topic_name, increment=1)
                        else:
                            self.logger.warning(
                                f"Failed to add comment for agent {act.agent_id}",
                                extra={"extra_data": {"agent_id": act.agent_id}},
                            )
                    else:
                        self.logger.warning(
                            f"Parent post not found for comment: {act.target_post_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_post_id": act.target_post_id}},
                        )
                
                elif act.action_type == "SHARE":
                    # Share action: create a new post referencing the original
                    # Get the original post to copy news_id if present
                    original_post = self.db.get_post(act.target_post_id)
                    if original_post:
                        post_data = {
                            "user_id": str(act.agent_id),
                            "tweet": act.content if act.content else "",  # Optional commentary
                            "round": self.current_round_id,
                            "shared_from": act.target_post_id,
                        }
                        # If the original post references an article, copy the reference
                        # Use helper method for consistent empty/default value checking
                        news_id = original_post.get("news_id")
                        if not self.db._is_empty_or_default(news_id):
                            post_data["news_id"] = news_id
                        
                        post_id = self.db.add_post(post_data)
                        if post_id:
                            new_ids.append(post_id)
                        else:
                            self.logger.warning(
                                f"Failed to add share for agent {act.agent_id}",
                                extra={"extra_data": {"agent_id": act.agent_id}},
                            )
                    else:
                        self.logger.warning(
                            f"Original post not found for share: {act.target_post_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_post_id": act.target_post_id}},
                        )
                
                elif act.action_type == "FOLLOW":
                    # Follow action: create follow relationship
                    follow_data = {
                        "follower_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string) - agent who is following
                        "user_id": act.target_user_id,  # FK to user_mgmt.id (UUID string) - user being followed
                        "action": "follow",
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    success = self.db.add_follow(follow_data)
                    if not success:
                        self.logger.warning(
                            f"Failed to add follow for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_user_id": act.target_user_id}},
                        )
                
                elif act.action_type == "UNFOLLOW":
                    # Unfollow action: create unfollow relationship record
                    unfollow_data = {
                        "follower_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string) - agent who is unfollowing
                        "user_id": act.target_user_id,  # FK to user_mgmt.id (UUID string) - user being unfollowed
                        "action": "unfollow",
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    success = self.db.add_follow(unfollow_data)
                    if not success:
                        self.logger.warning(
                            f"Failed to add unfollow for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_user_id": act.target_user_id}},
                        )
                
                else:
                    # Other interactions (LIKE, LOVE, ANGRY, SAD, LAUGH, etc.)
                    interaction_data = {
                        "user_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string)
                        "post_id": act.target_post_id,  # FK to post.id (UUID string)
                        "type": act.action_type,  # Field name is 'type' not 'reaction_type'
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    self.db.add_interaction(interaction_data)
                    
                    # Save sentiment for reactions
                    # Get the post being reacted to
                    reacted_post = self.db.get_post(act.target_post_id)
                    if reacted_post:
                        # Get topics from the reacted post
                        topic_ids = self.db.get_post_topics(act.target_post_id)
                        
                        if topic_ids:
                            # Map reaction type to sentiment values
                            sentiment_values = self._reaction_to_sentiment(act.action_type)
                            
                            if sentiment_values:
                                # Get parent post sentiment for sentiment_parent field
                                parent_sentiment = None
                                parent_sentiment_data = self.db.get_post_sentiment(act.target_post_id)
                                if parent_sentiment_data is not None:
                                    sentiment_parent_compound = parent_sentiment_data.get("compound")
                                    if sentiment_parent_compound is not None:
                                        # Apply thresholding
                                        if sentiment_parent_compound > 0.05:
                                            parent_sentiment = "pos"
                                        elif sentiment_parent_compound < -0.05:
                                            parent_sentiment = "neg"
                                        else:
                                            parent_sentiment = "neu"
                                        self.logger.info(f"Parent sentiment for reaction on post {act.target_post_id}: compound={sentiment_parent_compound:.3f} -> {parent_sentiment}")
                                    else:
                                        parent_sentiment = ""
                                else:
                                    parent_sentiment = ""
                                
                                # Create sentiment entries for each topic
                                for topic_id in topic_ids:
                                    sentiment_data = {
                                        "post_id": act.target_post_id,
                                        "user_id": str(act.agent_id),
                                        "topic_id": topic_id,
                                        "round": self.current_round_id,
                                        "neg": sentiment_values["neg"],
                                        "pos": sentiment_values["pos"],
                                        "neu": sentiment_values["neu"],
                                        "compound": sentiment_values["compound"],
                                        "sentiment_parent": parent_sentiment,
                                        "is_post": 0,
                                        "is_comment": 0,
                                        "is_reaction": 1
                                    }
                                    success = self.db.add_post_sentiment(sentiment_data)
                                    if success:
                                        self.logger.info(f"Added reaction sentiment for {act.action_type} on post {act.target_post_id}, topic {topic_id}")
                                    else:
                                        self.logger.error(f"Failed to add reaction sentiment for {act.action_type} on post {act.target_post_id}, topic {topic_id}")
                        else:
                            self.logger.debug(f"No topics found for reacted post {act.target_post_id}, skipping reaction sentiment")
                    else:
                        self.logger.warning(f"Reacted post {act.target_post_id} not found")


            if new_ids:
                self.recent_posts_cache.extend(new_ids)
                self.recent_posts_cache = self.recent_posts_cache[-50:]  # Keep last 50

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
            print(f"DB Error: {e}")

        # Mark this specific client as done
        self.submitted_clients.add(client_id)

        # Check if EVERYONE is done
        self._check_barrier_and_advance()

    def add_website(self, website_data: dict) -> Optional[str]:
        """
        Add a website (news source) to the database.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            website_data: Dictionary containing website information
            
        Returns:
            str: Website ID if successful, None otherwise
        """
        return self.db.add_website(website_data)
    
    def get_website_by_rss(self, rss_url: str) -> Optional[dict]:
        """
        Get website information by RSS URL.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            rss_url: RSS feed URL
            
        Returns:
            dict: Website information if found, None otherwise
        """
        return self.db.get_website_by_rss(rss_url)
    
    def add_article(self, article_data: dict) -> Optional[str]:
        """
        Add a news article to the database.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            article_data: Dictionary containing article information
            
        Returns:
            str: Article ID if successful, None otherwise
        """
        return self.db.add_article(article_data)
    
    def add_image(self, image_data: dict) -> Optional[str]:
        """
        Add an image to the database.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            image_data: Dictionary containing image information (url, description, article_id)
            
        Returns:
            str: Image ID if successful, None otherwise
        """
        return self.db.add_image(image_data)

    def _check_barrier_and_advance(self) -> None:
        """
        Check if all active clients have submitted actions and advance simulation state.

        This implements the core dynamic barrier synchronization mechanism.
        Only waits for active clients (not completed ones).
        """
        active_clients = self._get_active_clients()
        active_count = len(active_clients)

        # Do not advance if no one is active
        if active_count == 0:
            return

        # Count how many active clients have submitted
        submitted_active_clients = self.submitted_clients & active_clients
        active_submitted_count = len(submitted_active_clients)

        # If all active clients have submitted, advance.
        if active_submitted_count >= active_count:
            execution_start = time.time()

            print(
                f"[Server] ✅ Day {self.day} Slot {self.slot} complete "
                f"(Active clients: {active_count}). Advancing..."
            )

            self.submitted_clients.clear()
            self.slot += 1

            # Check if day is complete and consolidate Redis data if needed
            day_completed = False
            if self.slot > 24:
                day_completed = True
                completed_day = self.day
                self.slot = 1
                self.day += 1

                # Consolidate Redis data to SQLite at end of day
                consolidation_result = self.db.consolidate_redis_to_sqlite(completed_day)
                if (
                    consolidation_result.get("posts", 0) > 0
                    or consolidation_result.get("interactions", 0) > 0
                    or consolidation_result.get("removed_posts", 0) > 0
                ):
                    self.logger.info(
                        f"Day {completed_day} complete - data consolidated to SQLite",
                        extra={
                            "extra_data": {
                                "completed_day": completed_day,
                                "posts_consolidated": consolidation_result.get("posts", 0),
                                "interactions_consolidated": consolidation_result.get(
                                    "interactions", 0
                                ),
                                "posts_removed_from_redis": consolidation_result.get(
                                    "removed_posts", 0
                                ),
                                "interactions_removed_from_redis": consolidation_result.get(
                                    "removed_interactions", 0
                                ),
                            }
                        },
                    )
                    print(
                        f"[Server] 💾 Day {completed_day} complete - "
                        f"Consolidated {consolidation_result.get('posts', 0)} posts, "
                        f"{consolidation_result.get('interactions', 0)} interactions to SQLite. "
                        f"Removed {consolidation_result.get('removed_posts', 0)} old posts, "
                        f"{consolidation_result.get('removed_interactions', 0)} old interactions from Redis"
                    )
                
                # Recompute all agent interests based on the sliding attention window
                # This handles the forgetting mechanism - interests decay as entries fall out of window
                self._recompute_all_agent_interests()
                
                # Note: Saving updated agent_population.json is handled by clients,
                # not the server, to respect client-specific naming conventions
                
                # Clean up old posts from Redis based on visibility_rounds (temporal sliding window)
                cleanup_result = self.db.cleanup_old_posts_from_redis(self.day, self.slot)
                if cleanup_result.get("removed_posts", 0) > 0 or cleanup_result.get("removed_interactions", 0) > 0:
                    self.logger.info(
                        f"Redis temporal cleanup complete - removed posts older than visibility_rounds",
                        extra={
                            "extra_data": {
                                "day": self.day,
                                "slot": self.slot,
                                "removed_posts": cleanup_result.get("removed_posts", 0),
                                "removed_interactions": cleanup_result.get("removed_interactions", 0),
                                "remaining_posts": cleanup_result.get("remaining_posts", 0),
                            }
                        },
                    )
                    print(
                        f"[Server] 🧹 Redis cleanup - "
                        f"Removed {cleanup_result.get('removed_posts', 0)} old posts, "
                        f"{cleanup_result.get('removed_interactions', 0)} old interactions. "
                        f"Remaining: {cleanup_result.get('remaining_posts', 0)} posts in Redis"
                    )
                
                # Check if it's time for archetype transitions (every 7 days)
                if self.archetypes_enabled and self.day - self.last_archetype_transition_day >= 7:
                    self._perform_archetype_transitions()
                    self.last_archetype_transition_day = self.day

            # Update Round table with new time
            self.current_round_id = self.db.get_or_create_round(self.day, self.slot)
            self.interest_manager.set_current_round(self.current_round_id)

            execution_time = (time.time() - execution_start) * 1000

            self.logger.info(
                "Simulation advanced",
                extra={
                    "extra_data": {
                        "new_day": self.day,
                        "new_slot": self.slot,
                        "round_id": self.current_round_id,
                        "num_active_clients": active_count,
                        "day_completed": day_completed,
                        "execution_time_ms": execution_time,
                    }
                },
            )

    def _perform_archetype_transitions(self) -> None:
        """
        Perform archetype transitions for all registered agents based on transition probabilities.
        
        Each agent has a probability of transitioning to a different archetype based on their
        current archetype and the transition matrix defined in the configuration.
        This is called every 7 days when archetypes are enabled.
        """
        import random
        
        # Tolerance for probability sum validation
        PROBABILITY_TOLERANCE = 0.01
        
        if not self.archetypes_enabled or not self.archetype_transitions:
            return
        
        transition_start = time.time()
        transitioned_count = 0
        error_count = 0
        
        # Get all registered agents from database
        try:
            # Query all users and their current archetypes
            agents = self.db.get_all_users()
            
            for agent in agents:
                agent_id = agent.get("id")
                current_archetype = agent.get("archetype")
                
                # Skip if agent has no archetype
                if not current_archetype:
                    continue
                
                # Normalize archetype to lowercase for comparison
                current_archetype_lower = current_archetype.lower()
                
                # Skip if archetype not in transitions
                if current_archetype_lower not in self.archetype_transitions:
                    continue
                
                # Get transition probabilities for current archetype
                transitions = self.archetype_transitions.get(current_archetype_lower, {})
                
                if not transitions:
                    continue
                
                # Sample new archetype based on transition probabilities
                archetypes = list(transitions.keys())
                probabilities = list(transitions.values())
                
                # Validate probabilities sum to approximately 1.0
                total_prob = sum(probabilities)
                if abs(total_prob - 1.0) > PROBABILITY_TOLERANCE:
                    self.logger.warning(
                        f"Archetype transition probabilities for '{current_archetype}' sum to {total_prob}, expected 1.0"
                    )
                    # Normalize probabilities
                    probabilities = [p / total_prob for p in probabilities]
                
                # Select new archetype using weighted random choice
                new_archetype = random.choices(archetypes, weights=probabilities)[0]
                
                # Update agent archetype in database if it changed
                if new_archetype != current_archetype_lower:
                    # Capitalize first letter to match format
                    new_archetype_formatted = new_archetype.capitalize()
                    
                    if self.db.update_user_archetype(agent_id, new_archetype_formatted):
                        transitioned_count += 1
                        self.logger.debug(
                            f"Agent {agent_id} transitioned from {current_archetype} to {new_archetype_formatted}"
                        )
                    else:
                        error_count += 1
        
        except Exception as e:
            self.logger.error(
                f"Error during archetype transitions: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            print(f"[Server] ❌ Archetype transition error: {e}")
            return
        
        transition_time = (time.time() - transition_start) * 1000
        
        self.logger.info(
            f"Archetype transitions complete at day {self.day}",
            extra={
                "extra_data": {
                    "day": self.day,
                    "transitioned_count": transitioned_count,
                    "error_count": error_count,
                    "total_agents": len(agents),
                    "execution_time_ms": transition_time,
                }
            },
        )
        
        print(
            f"[Server] 🔄 Archetype transitions complete - "
            f"{transitioned_count} agents changed archetypes (day {self.day})"
        )
    
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
        slots_per_day = getattr(self, 'num_slots_per_day', 24)
        
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
                    round=self.current_round_id
                )
                session.add(recommendation)
                session.commit()
            finally:
                session.close()
            
            # Also save to Redis if enabled
            if self.db.use_redis:
                # Store recommendation in Redis with key format: ysim:recommendations:{user_id}:{round_id}
                rec_key = self.db._redis_key("recommendations", f"{agent_id}:{self.current_round_id}")
                self.db.redis_client.set(rec_key, post_ids_str)
                # Set TTL to prevent unbounded growth
                self.db.redis_client.expire(rec_key, RECOMMENDATION_TTL_SECONDS)
                
            self.logger.debug(
                f"Saved recommendation for agent {agent_id}: {len(post_ids)} posts",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "round": self.current_round_id,
                        "post_count": len(post_ids)
                    }
                }
            )
            
        except Exception as e:
            self.logger.error(
                f"Error saving recommendation: {e}",
                extra={"extra_data": {"agent_id": agent_id, "error": str(e)}}
            )
    
    def get_recommended_posts(
        self,
        agent_id: str,
        mode: str = "random",
        limit: int = 5,
        followers_ratio: float = 0.6
    ) -> List[str]:
        """
        Get recommended posts for an agent using the specified recommendation strategy.
        
        Args:
            agent_id: UUID of the agent requesting recommendations
            mode: Recommendation mode:
                - "random": Random post ordering (default)
                - "rchrono": Reverse chronological ordering (newest first)
                - "rchrono_popularity": Reverse chronological with popularity boost
                - "rchrono_followers": Prioritizes posts from followed users
                - "rchrono_followers_popularity": Followers + popularity
                - "rchrono_comments": Prioritizes highly commented posts
                - "common_interests": Posts with common topic interests
                - "common_user_interests": Posts by users with common interests
                - "similar_users_react": Posts from similar users (by reactions)
                - "similar_users_posts": Posts from similar users (by posting)
            limit: Number of posts to recommend (default: 5)
            followers_ratio: Ratio of posts from followers vs others (default: 0.6)
            
        Returns:
            List[str]: List of post UUIDs recommended for the agent
        """
        try:
            # Use server's configured visibility_rounds
            # Calculate visibility threshold based on day/hour (not UUID arithmetic)
            visibility_day, visibility_hour = self._calculate_visibility_params(self.visibility_rounds)
            
            if self.db.use_redis:
                # Use Redis for recommendations - dispatch to modular functions
                # Get recent posts from Redis
                recent_posts_key = self.db._redis_key("posts", "recent")
                all_post_ids = self.db.redis_client.lrange(recent_posts_key, 0, -1)
                
                # Use Redis pipeline to fetch post data efficiently (avoid N+1 queries)
                if all_post_ids:
                    pipeline = self.db.redis_client.pipeline()
                    for post_id in all_post_ids:
                        post_key = self.db._redis_key("posts", post_id)
                        pipeline.hgetall(post_key)
                    
                    # Execute pipeline and get all results at once
                    posts_data = pipeline.execute()
                    
                    # Build list of valid posts with metadata
                    valid_posts_with_data = []
                    for i, post_data in enumerate(posts_data):
                        if post_data:
                            post_user_id = post_data.get("user_id")
                            # Exclude own posts
                            if post_user_id and post_user_id != agent_id:
                                valid_posts_with_data.append({
                                    'id': all_post_ids[i],
                                    'index': i,  # Preserve chronological order (lower index = newer)
                                    'reaction_count': int(post_data.get("reaction_count", 0) or 0)
                                })
                else:
                    valid_posts_with_data = []
                
                # Prepare common kwargs for all recommendation functions
                common_kwargs = {
                    'valid_posts_with_data': valid_posts_with_data,
                    'limit': limit,
                    'agent_id': agent_id,
                    'all_post_ids': all_post_ids,
                    'posts_data': posts_data,
                    'followers_ratio': followers_ratio,
                    'db_engine': self.db.engine,
                    'redis_client': self.db.redis_client,
                    'redis_key_fn': self.db._redis_key,
                    'logger': self.logger
                }
                
                # Dispatch to appropriate recommendation function
                if mode == "rchrono":
                    post_ids = content_recsys_redis.recommend_rchrono_redis(**common_kwargs)
                elif mode == "rchrono_popularity":
                    post_ids = content_recsys_redis.recommend_rchrono_popularity_redis(**common_kwargs)
                elif mode == "rchrono_followers":
                    post_ids = content_recsys_redis.recommend_rchrono_followers_redis(**common_kwargs)
                elif mode == "rchrono_followers_popularity":
                    post_ids = content_recsys_redis.recommend_rchrono_followers_popularity_redis(**common_kwargs)
                elif mode == "rchrono_comments":
                    post_ids = content_recsys_redis.recommend_rchrono_comments_redis(**common_kwargs)
                elif mode == "common_interests":
                    post_ids = content_recsys_redis.recommend_common_interests_redis(**common_kwargs)
                elif mode == "common_user_interests":
                    post_ids = content_recsys_redis.recommend_common_user_interests_redis(**common_kwargs)
                elif mode == "similar_users_react":
                    post_ids = content_recsys_redis.recommend_similar_users_react_redis(**common_kwargs)
                elif mode == "similar_users_posts":
                    post_ids = content_recsys_redis.recommend_similar_users_posts_redis(**common_kwargs)
                else:
                    # Default: random ordering
                    post_ids = content_recsys_redis.recommend_random_redis(**common_kwargs)
                
                self.logger.info(
                    f"Recommended {len(post_ids)} posts (Redis, mode={mode})",
                    extra={
                        "extra_data": {
                            "agent_id": agent_id,
                            "mode": mode,
                            "limit": limit,
                            "found": len(post_ids),
                        }
                    },
                )
                
                # Save recommendations to database (and Redis if enabled)
                self._save_recommendation(agent_id, post_ids)
                
                return post_ids
                
            else:
                # Use SQL database for recommendations
                from sqlalchemy.orm import Session
                session = Session(self.db.engine)
                try:
                    if mode == "rchrono":
                        # Reverse chronological: newest posts first
                        post_ids = content_recsys_db.recommend_rchrono(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                        
                    elif mode == "rchrono_popularity":
                        # Reverse chronological with popularity (reaction count)
                        post_ids = content_recsys_db.recommend_rchrono_popularity(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                        
                    elif mode == "rchrono_followers":
                        # Prioritize posts from followed users
                        post_ids = content_recsys_db.recommend_rchrono_followers(
                            session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                        )
                        
                    elif mode == "rchrono_followers_popularity":
                        # Followers with popularity boost
                        post_ids = content_recsys_db.recommend_rchrono_followers_popularity(
                            session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                        )
                            
                    elif mode == "rchrono_comments":
                        # Prioritize posts with more comments (thread activity)
                        post_ids = content_recsys_db.recommend_rchrono_comments(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                        
                    elif mode == "common_interests":
                        # Posts with common topic interests
                        post_ids = content_recsys_db.recommend_common_interests(
                            session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                        )
                    
                    elif mode == "common_user_interests":
                        # Posts by users with common interests (most interacted)
                        post_ids = content_recsys_db.recommend_common_user_interests(
                            session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                        )
                    
                    elif mode == "similar_users_react":
                        # Posts from similar users (based on demographics/personality)
                        post_ids = content_recsys_db.recommend_similar_users_react(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                    
                    elif mode == "similar_users_posts":
                        # Posts created by similar users
                        post_ids = content_recsys_db.recommend_similar_users_posts(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                        
                    else:
                        # Random ordering (default)
                        post_ids = content_recsys_db.recommend_random(
                            session, agent_id, visibility_day, visibility_hour, limit
                        )
                    
                    self.logger.info(
                        f"Recommended {len(post_ids)} posts (SQL, mode={mode})",
                        extra={
                            "extra_data": {
                                "agent_id": agent_id,
                                "mode": mode,
                                "limit": limit,
                                "found": len(post_ids),
                            }
                        },
                    )
                    
                    # Save recommendations to database (and Redis if enabled)
                    self._save_recommendation(agent_id, post_ids)
                    
                    return post_ids
                finally:
                    session.close()
                
        except Exception as e:
            self.logger.error(
                f"Error getting recommended posts: {e}",
                extra={"extra_data": {"agent_id": agent_id, "mode": mode, "error": str(e)}},
            )
            return []
    
    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a post by its ID.
        
        Args:
            post_id: UUID of the post to retrieve
            
        Returns:
            Dictionary with post data or None if not found
        """
        return self.db.get_post(post_id)

    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """
        Get thread context for a post - retrieve up to max_length posts/comments
        that immediately precede the target post in the discussion thread.
        
        Returns posts in chronological order (oldest first) to allow the agent
        to follow the discussion thread.
        
        Args:
            post_id: UUID of the post to get context for
            max_length: Maximum number of preceding posts/comments to return
            
        Returns:
            List of dicts with keys: id, user_id, username, tweet, round
            in chronological order (oldest first)
        """
        return self.db.get_thread_context(post_id, max_length)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their ID.
        
        Args:
            user_id: UUID of the user to retrieve
            
        Returns:
            Dictionary with user data or None if not found
        """
        return self.db.get_user(user_id)

    def get_follow_suggestions(
        self,
        agent_id: str,
        mode: str = "random",
        n_neighbors: int = 10,
        leaning_bias: int = 1
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
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using SQL queries for better scalability.
        
        Dispatcher method that delegates to modular functions in follow_recsys_db module.
        """
        try:
            from sqlalchemy.orm import Session
            from YSimulator.YServer.classes.models import User_mgmt, Follow
            from sqlalchemy import func, and_
            
            with Session(self.db.engine) as session:
                # Get agent's info
                agent = session.query(User_mgmt).filter_by(id=agent_id).first()
                if not agent:
                    self.logger.warning(f"Agent {agent_id} not found for follow suggestions")
                    return []
                
                # Get users that agent is currently following (with latest action = "follow")
                latest_follows_subq = session.query(
                    Follow.follower_id,
                    Follow.user_id,
                    func.max(Follow.round).label('max_round')
                ).filter(
                    Follow.follower_id == agent_id
                ).group_by(Follow.follower_id, Follow.user_id).subquery()
                
                following = session.query(Follow.user_id).join(
                    latest_follows_subq,
                    and_(
                        Follow.follower_id == latest_follows_subq.c.follower_id,
                        Follow.user_id == latest_follows_subq.c.user_id,
                        Follow.round == latest_follows_subq.c.max_round,
                        Follow.action == "follow"
                    )
                ).all()
                following_ids = {f.user_id for f in following}
                
                # Dispatch to appropriate recommendation function
                if mode == "random":
                    suggestions = follow_recsys_db.recommend_random_follows(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "common_neighbors":
                    suggestions = follow_recsys_db.recommend_common_neighbors(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "jaccard":
                    suggestions = follow_recsys_db.recommend_jaccard(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "adamic_adar":
                    suggestions = follow_recsys_db.recommend_adamic_adar(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "preferential_attachment":
                    suggestions = follow_recsys_db.recommend_preferential_attachment(
                        session, agent_id, following_ids, n_neighbors
                    )
                else:
                    # Unknown mode, fallback to random
                    suggestions = follow_recsys_db.recommend_random_follows(
                        session, agent_id, following_ids, n_neighbors
                    )
                
                # Apply leaning bias if requested
                suggestions = follow_recsys_db.apply_leaning_bias(
                    session, agent_id, suggestions, leaning_bias, n_neighbors
                )
                
                return suggestions[:n_neighbors]
                
        except Exception as e:
            self.logger.error(
                f"Error getting SQL follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}}
            )
            # Fallback to simple random
            try:
                from sqlalchemy.orm import Session
                from YSimulator.YServer.classes.models import User_mgmt
                with Session(self.db.engine) as session:
                    candidates = session.query(User_mgmt.id).filter(
                        User_mgmt.id != agent_id
                    ).limit(n_neighbors * 2).all()
                    candidate_ids = [c.id for c in candidates]
                    random.shuffle(candidate_ids)
                    return candidate_ids[:n_neighbors]
            except:
                return []
    
    def _get_follow_suggestions_redis(
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using Redis for better scalability with key-value storage.
        Dispatcher method that delegates to specific recommendation functions.
        """
        from YSimulator.YServer.recsys import follow_recsys_redis
        
        try:
            # Dispatch to appropriate recommendation function
            if mode == "random":
                recommendations = follow_recsys_redis.recommend_random_follows_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "preferential_attachment":
                recommendations = follow_recsys_redis.recommend_preferential_attachment_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "common_neighbors":
                recommendations = follow_recsys_redis.recommend_common_neighbors_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "jaccard":
                recommendations = follow_recsys_redis.recommend_jaccard_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "adamic_adar":
                recommendations = follow_recsys_redis.recommend_adamic_adar_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            else:
                # Unknown mode, fallback to random
                self.logger.warning(f"Unknown follow recommendation mode: {mode}, using random")
                recommendations = follow_recsys_redis.recommend_random_follows_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            
            # Apply political leaning bias if specified
            if leaning_bias > 0 and recommendations:
                recommendations = follow_recsys_redis.apply_leaning_bias_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, recommendations, leaning_bias, self.logger
                )
            
            return recommendations
                
        except Exception as e:
            self.logger.error(
                f"Error getting Redis follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}}
            )
            # Fallback to random from user_mgmt ids
            try:
                user_ids_key = self.db._redis_key("user_mgmt", "ids")
                all_user_ids = list(self.db.redis_client.smembers(user_ids_key))
                candidates = [uid for uid in all_user_ids if uid != agent_id]
                random.shuffle(candidates)
                return candidates[:n_neighbors]
            except:
                return []
