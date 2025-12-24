"""
Database middleware for YSimulator.

This module provides a middleware layer that can use either Redis (if available)
or SQLite as the database backend. The middleware abstracts database operations
to allow seamless switching between backends.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import Base, Reaction, Post, User_mgmt, Round, Follow

# Constants
DEFAULT_USERNAME = "Someone"  # Default username when user data is not found


class DatabaseMiddleware:
    """
    Database middleware that supports multiple SQLAlchemy-compatible backends.

    Supports SQLite, PostgreSQL, and MySQL as database backends.
    If Redis is available and configured, it will be used as a high-performance cache.
    """

    def __init__(
        self,
        db_config: Dict[str, Any],
        config_path: str = ".",
        redis_config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        simulation_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the database middleware.

        Args:
            db_config: Database configuration dict with 'type' and backend-specific settings
            config_path: Path to configuration directory (for SQLite database file)
            redis_config: Redis configuration dict with keys: host, port, db, password, sliding_window_days (optional)
            logger: Logger instance for logging operations
            simulation_config: Simulation configuration dict with posts.visibility_rounds (optional)
        """
        from pathlib import Path

        self.logger = logger or logging.getLogger(__name__)
        self.use_redis = False
        self.redis_client = None
        self.redis_sliding_window_days = 2  # Default: keep last 2 days in Redis
        self.db_type = db_config.get("type", "sqlite").lower()
        self.config_path = Path(config_path)
        
        # Extract visibility_rounds from simulation_config
        if simulation_config is None:
            simulation_config = {}
        self.visibility_rounds = simulation_config.get("posts", {}).get("visibility_rounds", 36)
        self.num_slots_per_day = simulation_config.get("simulation", {}).get("num_slots_per_day", 24)

        # Try to initialize Redis if explicitly configured with enabled=true and host specified
        if redis_config and isinstance(redis_config, dict) and redis_config.get("enabled", False):
            # Get sliding window configuration (default to 2 days)
            self.redis_sliding_window_days = redis_config.get("sliding_window_days", 2)

            # Validate that Redis host is provided
            if not redis_config.get("host"):
                self.logger.info(
                    "Redis is enabled but no host specified in config, using SQL database only"
                )
            elif not REDIS_AVAILABLE:
                self.logger.warning(
                    "Redis is enabled in config but redis module is not installed. "
                    "Install with: pip install redis"
                )
            else:
                try:
                    self.redis_client = redis.Redis(
                        host=redis_config.get("host"),
                        port=redis_config.get("port", 6379),
                        db=redis_config.get("db", 0),
                        password=redis_config.get("password"),
                        decode_responses=True,
                    )
                    # Test connection
                    self.redis_client.ping()
                    self.use_redis = True
                    self.logger.info(
                        "Redis connection established",
                        extra={
                            "extra_data": {
                                "host": redis_config.get("host"),
                                "port": redis_config.get("port"),
                            }
                        },
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Redis connection failed, falling back to SQL database: {e}",
                        extra={"extra_data": {"error": str(e)}},
                    )
                    self.use_redis = False
                    self.redis_client = None

        # Build SQLAlchemy connection string based on database type
        connection_string = self._build_connection_string(db_config)

        # Initialize SQL database backend
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        
        # Initialize round cache for performance
        self.round_cache = {}  # Cache: (day, hour) -> round_id
        
        self.logger.info(
            "SQL database initialized",
            extra={
                "extra_data": {
                    "db_type": self.db_type,
                    "redis_enabled": self.use_redis,
                }
            },
        )

    @staticmethod
    def _is_empty_or_default(value) -> bool:
        """
        Check if a value is empty or a default placeholder (-1, '-1', '', None).
        
        This helper handles the database's use of -1 as a default value for foreign keys
        that can be either integers or strings depending on context.
        
        Args:
            value: The value to check
            
        Returns:
            bool: True if the value should be considered empty/default
        """
        return value is None or value == -1 or value == "-1" or value == ""

    def _build_connection_string(self, db_config: Dict[str, Any]) -> str:
        """
        Build SQLAlchemy connection string based on database configuration.

        Args:
            db_config: Database configuration dict

        Returns:
            SQLAlchemy connection string

        Raises:
            ValueError: If database type is not supported or required parameters are missing
        """
        from urllib.parse import quote_plus

        db_type = db_config.get("type", "sqlite").lower()

        if db_type == "sqlite":
            sqlite_config = db_config.get("sqlite", {})
            filename = sqlite_config.get("filename", "simulation.db")
            # Create database file in config directory
            db_path = self.config_path / filename
            return f"sqlite:///{db_path}"

        elif db_type == "postgresql":
            pg_config = db_config.get("postgresql", {})
            host = pg_config.get("host", "localhost")
            port = pg_config.get("port", 5432)
            database = pg_config.get("database")
            username = pg_config.get("username")
            password = pg_config.get("password")

            if not all([database, username]):
                raise ValueError(
                    "PostgreSQL requires 'database' and 'username' in configuration"
                )

            # URL encode password to handle special characters
            if password:
                encoded_password = quote_plus(password)
                return f"postgresql://{username}:{encoded_password}@{host}:{port}/{database}"
            else:
                return f"postgresql://{username}@{host}:{port}/{database}"

        elif db_type == "mysql":
            mysql_config = db_config.get("mysql", {})
            host = mysql_config.get("host", "localhost")
            port = mysql_config.get("port", 3306)
            database = mysql_config.get("database")
            username = mysql_config.get("username")
            password = mysql_config.get("password")

            if not all([database, username]):
                raise ValueError("MySQL requires 'database' and 'username' in configuration")

            # URL encode password to handle special characters
            if password:
                encoded_password = quote_plus(password)
                return f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{database}"
            else:
                return f"mysql+pymysql://{username}@{host}:{port}/{database}"

        else:
            raise ValueError(
                f"Unsupported database type: {db_type}. Supported types: sqlite, postgresql, mysql"
            )

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key for a table and optional ID."""
        if id is not None:
            return f"ysim:{table}:{id}"
        return f"ysim:{table}"

    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Register a user in the database.

        Args:
            user_data: Dictionary containing user data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.use_redis:
                # Store in Redis as hash
                user_id = user_data["id"]
                key = self._redis_key("user_mgmt", user_id)

                # Check if user already exists
                if self.redis_client.exists(key):
                    return False

                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in user_data.items() if v is not None}
                
                # Store user data
                self.redis_client.hset(key, mapping=redis_data)
                # Add to user set
                self.redis_client.sadd(self._redis_key("user_mgmt", "ids"), user_id)
                return True
            else:
                # Store in SQLite
                session = Session(self.engine)
                try:
                    existing = session.query(User_mgmt).filter_by(id=user_data["id"]).first()
                    if existing:
                        return False

                    user = User_mgmt(**user_data)
                    session.add(user)
                    session.commit()
                    return True
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error registering user: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            Dict with user data or None if not found
        """
        try:
            if self.use_redis:
                key = self._redis_key("user_mgmt", user_id)
                if not self.redis_client.exists(key):
                    return None
                return self.redis_client.hgetall(key)
            else:
                session = Session(self.engine)
                try:
                    user = session.query(User_mgmt).filter_by(id=user_id).first()
                    if not user:
                        return None
                    # Convert to dict with proper type handling
                    return {
                        c.name: (
                            str(getattr(user, c.name))
                            if getattr(user, c.name) is not None
                            else None
                        )
                        for c in user.__table__.columns
                    }
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(f"Error getting user: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a post to the database.

        Args:
            post_data: Dictionary containing post data

        Returns:
            str: Post UUID if successful, None otherwise
        """
        try:
            # Generate UUID for post
            post_id = str(uuid.uuid4())
            post_data["id"] = post_id
            
            # Set thread_id logic:
            # - If comment_to is set and not -1 (comment), thread_id should already be set by caller
            # - Otherwise (new post or share), set thread_id to post_id
            comment_to = post_data.get("comment_to")
            if self._is_empty_or_default(comment_to):
                # New post or share - create new thread
                post_data["thread_id"] = post_id
            # If comment_to is set to a valid value, thread_id should already be set by the caller

            if self.use_redis:
                # Store post
                key = self._redis_key("posts", post_id)
                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in post_data.items() if v is not None}
                self.redis_client.hset(key, mapping=redis_data)

                # Add to posts list (no limit - will be cleaned by visibility_rounds at day end)
                self.redis_client.lpush(self._redis_key("posts", "recent"), post_id)

                return post_id
            else:
                session = Session(self.engine)
                try:
                    post = Post(**post_data)
                    session.add(post)
                    session.commit()
                    return post_id
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(f"Error adding post: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Add an interaction to the database.

        Args:
            interaction_data: Dictionary containing interaction data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Generate UUID for interaction
            interaction_id = str(uuid.uuid4())
            interaction_data["id"] = interaction_id

            if self.use_redis:
                # Store interaction
                key = self._redis_key("interactions", interaction_id)
                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in interaction_data.items() if v is not None}
                self.redis_client.hset(key, mapping=redis_data)
                return True
            else:
                session = Session(self.engine)
                try:
                    interaction = Reaction(**interaction_data)
                    session.add(interaction)
                    session.commit()
                    return True
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding interaction: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_follow(self, follow_data: Dict[str, Any]) -> bool:
        """
        Add a follow relationship to the database.

        Args:
            follow_data: Dictionary containing follow data with keys:
                - user_id: UUID of user being followed
                - follower_id: UUID of follower
                - action: 'follow' or 'unfollow'
                - round: Round ID (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Generate UUID for follow record
            follow_id = str(uuid.uuid4())
            follow_data["id"] = follow_id

            if self.use_redis:
                # Store follow relationship in Redis
                key = self._redis_key("follow", follow_id)
                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in follow_data.items() if v is not None}
                self.redis_client.hset(key, mapping=redis_data)
                return True
            else:
                session = Session(self.engine)
                try:
                    follow = Follow(**follow_data)
                    session.add(follow)
                    session.commit()
                    return True
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding follow relationship: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get post data by ID.
        
        Args:
            post_id: Post UUID
            
        Returns:
            dict: Post data if found, None otherwise
        """
        try:
            if self.use_redis:
                key = self._redis_key("posts", post_id)
                post_data = self.redis_client.hgetall(key)
                return post_data if post_data else None
            else:
                session = Session(self.engine)
                try:
                    post = session.query(Post).filter(Post.id == post_id).first()
                    if post:
                        return {
                            "id": post.id,
                            "thread_id": post.thread_id,
                            "news_id": post.news_id,
                            "comment_to": post.comment_to,
                            "shared_from": post.shared_from,
                            "user_id": post.user_id,
                            "tweet": post.tweet,
                            "round": post.round,
                        }
                    return None
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """
        Get thread context for a post - retrieve up to max_length of the most recent
        posts/comments that precede the target post in the discussion thread.
        
        If the thread has more than max_length posts/comments before the target,
        only the most recent max_length items are returned (to provide the most
        relevant recent context).
        
        Returns posts in chronological order (oldest first) to allow the agent
        to follow the discussion thread naturally.
        
        Args:
            post_id: Post UUID to get context for
            max_length: Maximum number of preceding posts/comments to return
            
        Returns:
            List of dicts with keys: id, user_id, username, tweet, round
            in chronological order (oldest first), containing up to max_length
            of the most recent posts before the target
        """
        try:
            # First, get the target post to find its thread_id
            target_post = self.get_post(post_id)
            if not target_post:
                return []
            
            thread_id = target_post.get("thread_id")
            if not thread_id:
                return []
            
            if self.use_redis:
                # Redis implementation: get all posts in thread, filter and sort
                thread_posts = []
                
                # Get all recent post IDs to check
                all_post_ids = self.redis_client.lrange(
                    self._redis_key("posts", "recent"), 0, -1
                )
                
                for pid in all_post_ids:
                    pid_str = pid.decode('utf-8') if isinstance(pid, bytes) else str(pid)
                    if pid_str == post_id:
                        continue  # Skip the target post itself
                    
                    key = self._redis_key("posts", pid_str)
                    post_data = self.redis_client.hgetall(key)
                    
                    if not post_data:
                        continue
                    
                    # Decode bytes to strings
                    post_dict = {}
                    for k, v in post_data.items():
                        k_str = k.decode('utf-8') if isinstance(k, bytes) else k
                        v_str = v.decode('utf-8') if isinstance(v, bytes) else v
                        post_dict[k_str] = v_str
                    
                    # Check if this post is in the same thread
                    if post_dict.get("thread_id") == thread_id:
                        # Get username for this post
                        user_id = post_dict.get("user_id")
                        username = DEFAULT_USERNAME
                        if user_id:
                            user_key = self._redis_key("users", user_id)
                            user_data = self.redis_client.hgetall(user_key)
                            if user_data:
                                username_bytes = user_data.get(b"username") or user_data.get("username")
                                if username_bytes:
                                    username = username_bytes.decode('utf-8') if isinstance(username_bytes, bytes) else username_bytes
                        
                        # Get round info for sorting - need to query database for day/hour
                        round_id = post_dict.get("round")
                        round_data = None
                        if round_id:
                            # Try to get from Redis first
                            round_key = self._redis_key("rounds", round_id)
                            round_redis_data = self.redis_client.hgetall(round_key)
                            if round_redis_data:
                                day = round_redis_data.get(b"day") or round_redis_data.get("day")
                                hour = round_redis_data.get(b"hour") or round_redis_data.get("hour")
                                if day and hour:
                                    day_int = int(day.decode('utf-8') if isinstance(day, bytes) else day)
                                    hour_int = int(hour.decode('utf-8') if isinstance(hour, bytes) else hour)
                                    round_data = (day_int, hour_int)
                        
                        # If no round data, skip this post and log a warning
                        if round_data:
                            thread_posts.append({
                                "id": pid_str,
                                "user_id": post_dict.get("user_id"),
                                "username": username,
                                "tweet": post_dict.get("tweet", ""),
                                "round": post_dict.get("round"),
                                "sort_key": round_data  # Tuple of (day, hour) for sorting
                            })
                        else:
                            self.logger.warning(
                                f"Skipping post {pid_str} in thread context: missing or invalid round data",
                                extra={"extra_data": {"post_id": pid_str, "round_id": round_id}}
                            )
                
                # Sort by day and hour chronologically (oldest first)
                thread_posts.sort(key=lambda x: x.get("sort_key", (0, 0)))
                
                # Remove sort_key before returning
                for post in thread_posts:
                    post.pop("sort_key", None)
                
                # Return up to max_length posts, ending just before target post
                return thread_posts[-max_length:] if len(thread_posts) > max_length else thread_posts
                
            else:
                # Database implementation using SQLAlchemy
                session = Session(self.engine)
                try:
                    # Get all posts in the same thread except the target post
                    query = session.query(
                        Post.id,
                        Post.user_id,
                        User_mgmt.username,
                        Post.tweet,
                        Post.round
                    ).join(
                        User_mgmt, Post.user_id == User_mgmt.id
                    ).join(
                        Round, Post.round == Round.id
                    ).filter(
                        Post.thread_id == thread_id,
                        Post.id != post_id
                    ).order_by(
                        Round.day.asc(),
                        Round.hour.asc()
                    ).all()
                    
                    thread_posts = [
                        {
                            "id": row[0],
                            "user_id": row[1],
                            "username": row[2] or DEFAULT_USERNAME,
                            "tweet": row[3],
                            "round": row[4]
                        }
                        for row in query
                    ]
                    
                    # Return up to max_length posts (already in chronological order)
                    return thread_posts[-max_length:] if len(thread_posts) > max_length else thread_posts
                    
                finally:
                    session.close()
                    
        except Exception as e:
            self.logger.error(
                f"Error getting thread context: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}}
            )
            return []

    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """
        Get recent post IDs.

        Args:
            limit: Maximum number of posts to return

        Returns:
            List of post UUIDs (as strings)
        """
        try:
            if self.use_redis:
                post_ids = self.redis_client.lrange(
                    self._redis_key("posts", "recent"), 0, limit - 1
                )
                return [str(pid) for pid in post_ids]
            else:
                session = Session(self.engine)
                try:
                    posts = (
                        session.query(Post).order_by(Post.id.desc()).limit(limit).all()
                    )
                    return [post.id for post in posts]
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting recent posts: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    def consolidate_redis_to_sqlite(self, day: int) -> dict:
        """
        Consolidate Redis data to SQLite at the end of a simulation day.

        This method transfers all posts and interactions from Redis to SQLite.
        It then removes data older than the sliding window from Redis to manage memory.

        Args:
            day: The simulation day being consolidated

        Returns:
            dict: Summary with counts of posts and interactions transferred and removed
        """
        if not self.use_redis:
            return {
                "posts": 0,
                "interactions": 0,
                "follows": 0,
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": "Not using Redis",
            }

        try:
            session = Session(self.engine)
            posts_count = 0
            interactions_count = 0
            removed_posts_count = 0
            removed_interactions_count = 0

            try:
                # Get all post keys
                post_pattern = self._redis_key("posts", "*")
                post_keys = [
                    k
                    for k in self.redis_client.keys(post_pattern)
                    if not k.endswith(":recent") and not k.endswith(":counter")
                ]

                # Transfer all posts to SQL
                for key in post_keys:
                    post_data = self.redis_client.hgetall(key)
                    if post_data and "id" in post_data:
                        # Check if post already exists in SQLite
                        existing = session.query(Post).filter_by(id=post_data["id"]).first()
                        if not existing:
                            post = Post(
                                id=post_data["id"],
                                tweet=post_data.get("tweet", ""),
                                user_id=str(post_data.get("user_id", "")),
                                round=str(post_data.get("round", "")),
                            )
                            session.add(post)
                            posts_count += 1

                # Get all interaction keys
                interaction_pattern = self._redis_key("interactions", "*")
                interaction_keys = [
                    k
                    for k in self.redis_client.keys(interaction_pattern)
                    if not k.endswith(":counter")
                ]

                # Transfer all interactions to SQL
                for key in interaction_keys:
                    interaction_data = self.redis_client.hgetall(key)
                    if interaction_data and "id" in interaction_data:
                        # Check if interaction already exists in SQLite
                        existing = (
                            session.query(Reaction)
                            .filter_by(id=interaction_data["id"])
                            .first()
                        )
                        if not existing:
                            interaction = Reaction(
                                id=interaction_data["id"],
                                user_id=str(interaction_data.get("user_id", "")),
                                post_id=interaction_data.get("post_id", ""),
                                type=interaction_data.get("type", ""),
                                round=str(interaction_data.get("round", "")),
                            )
                            session.add(interaction)
                            interactions_count += 1

                # Get all follow keys
                follow_pattern = self._redis_key("follow", "*")
                follow_keys = [
                    k
                    for k in self.redis_client.keys(follow_pattern)
                    if not k.endswith(":counter")
                ]

                # Transfer all follow relationships to SQL
                follows_count = 0
                for key in follow_keys:
                    follow_data = self.redis_client.hgetall(key)
                    if follow_data and "id" in follow_data:
                        # Check if follow relationship already exists in SQLite
                        existing = (
                            session.query(Follow)
                            .filter_by(id=follow_data["id"])
                            .first()
                        )
                        if not existing:
                            follow = Follow(
                                id=follow_data["id"],
                                user_id=str(follow_data.get("user_id", "")),
                                follower_id=str(follow_data.get("follower_id", "")),
                                action=follow_data.get("action", "follow"),
                                round=str(follow_data.get("round", "")),
                            )
                            session.add(follow)
                            follows_count += 1

                # Commit all to SQLite
                session.commit()

                # Keep data in Redis for fast queries during simulation
                # SQL serves as permanent storage, Redis as hot cache
                removed_posts_count = 0
                removed_interactions_count = 0

                self.logger.info(
                    f"Consolidated Redis data for day {day}",
                    extra={
                        "extra_data": {
                            "day": day,
                            "posts_saved": posts_count,
                            "interactions_saved": interactions_count,
                            "follows_saved": follows_count,
                        }
                    },
                )

                return {
                    "posts": posts_count,
                    "interactions": interactions_count,
                    "follows": follows_count,
                    "removed_posts": removed_posts_count,
                    "removed_interactions": removed_interactions_count,
                    "message": "Consolidation successful",
                }

            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        except Exception as e:
            self.logger.error(
                f"Error consolidating Redis to SQLite: {e}",
                extra={"extra_data": {"error": str(e), "day": day}},
            )
            return {
                "posts": 0,
                "interactions": 0,
                "follows": 0,
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": f"Consolidation failed: {str(e)}",
            }

    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """
        Remove posts older than visibility_rounds from Redis storage.
        
        This implements a temporal sliding window: at the end of each simulation day,
        posts whose round is older than visibility_rounds are removed from Redis cache.
        This ensures Redis only contains posts within the visibility window.
        
        Args:
            current_day: Current simulation day
            current_slot: Current simulation slot/hour
            
        Returns:
            dict: Summary with counts of posts and interactions removed
        """
        if not self.use_redis:
            return {
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": "Not using Redis"
            }
        
        try:
            # Calculate the visibility threshold (oldest round to keep)
            total_slots = (current_day - 1) * self.num_slots_per_day + current_slot
            visibility_slots = max(1, total_slots - self.visibility_rounds)
            visibility_day = (visibility_slots - 1) // self.num_slots_per_day + 1
            visibility_hour = (visibility_slots - 1) % self.num_slots_per_day + 1
            
            self.logger.info(
                f"Cleaning Redis posts older than visibility window",
                extra={
                    "extra_data": {
                        "current_day": current_day,
                        "current_slot": current_slot,
                        "visibility_rounds": self.visibility_rounds,
                        "visibility_day": visibility_day,
                        "visibility_hour": visibility_hour,
                    }
                }
            )
            
            # Get all post IDs from recent list
            recent_posts_key = self._redis_key("posts", "recent")
            all_post_ids = self.redis_client.lrange(recent_posts_key, 0, -1)
            
            removed_posts_count = 0
            removed_interactions_count = 0
            posts_to_keep = []
            
            # Query database to get round info for each post
            session = Session(self.engine)
            try:
                for post_id in all_post_ids:
                    # Get post data from Redis
                    post_key = self._redis_key("posts", post_id)
                    post_data = self.redis_client.hgetall(post_key)
                    
                    if post_data and "round" in post_data:
                        round_id = post_data["round"]
                        
                        # Get round day/hour from database
                        round_obj = session.query(Round).filter_by(id=round_id).first()
                        
                        if round_obj:
                            # Check if post is within visibility window
                            if (round_obj.day > visibility_day or 
                                (round_obj.day == visibility_day and round_obj.hour >= visibility_hour)):
                                # Keep this post
                                posts_to_keep.append(post_id)
                            else:
                                # Remove this post (too old)
                                self.redis_client.delete(post_key)
                                removed_posts_count += 1
                                
                                # Also remove associated interactions
                                interaction_pattern = self._redis_key("interactions", f"*{post_id}*")
                                interaction_keys = self.redis_client.keys(interaction_pattern)
                                for int_key in interaction_keys:
                                    self.redis_client.delete(int_key)
                                    removed_interactions_count += 1
                        else:
                            # Round not found in DB, keep the post for safety
                            posts_to_keep.append(post_id)
                    else:
                        # Missing round data, keep the post for safety
                        posts_to_keep.append(post_id)
                
                # Rebuild the recent posts list with only posts to keep
                self.redis_client.delete(recent_posts_key)
                if posts_to_keep:
                    # Use rpush to maintain the order (oldest first in list)
                    # Then reverse to get newest first
                    for post_id in reversed(posts_to_keep):
                        self.redis_client.lpush(recent_posts_key, post_id)
                
                self.logger.info(
                    f"Redis cleanup complete",
                    extra={
                        "extra_data": {
                            "removed_posts": removed_posts_count,
                            "removed_interactions": removed_interactions_count,
                            "remaining_posts": len(posts_to_keep),
                        }
                    }
                )
                
                return {
                    "removed_posts": removed_posts_count,
                    "removed_interactions": removed_interactions_count,
                    "remaining_posts": len(posts_to_keep),
                    "message": "Cleanup successful"
                }
                
            finally:
                session.close()
                
        except Exception as e:
            self.logger.error(
                f"Error cleaning old posts from Redis: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return {
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": f"Cleanup failed: {str(e)}"
            }

    def get_or_create_round(self, day: int, hour: int) -> str:
        """
        Get or create a Round entry for the given day and hour.
        
        This method ensures that each (day, hour) combination has exactly one Round
        record in the database, which is used as a foreign key reference by posts,
        reactions, and other temporal entities.
        
        Args:
            day: Simulation day number
            hour: Hour/slot within the day (typically 1-24)
            
        Returns:
            str: UUID of the Round record
        """
        # Check cache first for performance
        cache_key = (day, hour)
        if cache_key in self.round_cache:
            return self.round_cache[cache_key]
        
        # Query or create in database
        session = Session(self.engine)
        try:
            # Try to find existing round
            round_obj = session.query(Round).filter_by(day=day, hour=hour).first()
            
            if not round_obj:
                # Create new round
                round_id = str(uuid.uuid4())
                round_obj = Round(id=round_id, day=day, hour=hour)
                session.add(round_obj)
                session.commit()
                
                self.logger.debug(
                    f"Created new Round entry",
                    extra={
                        "extra_data": {
                            "round_id": round_id,
                            "day": day,
                            "hour": hour,
                        }
                    },
                )
            
            # Cache the result
            self.round_cache[cache_key] = round_obj.id
            return round_obj.id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error getting/creating round: {e}",
                extra={"extra_data": {"error": str(e), "day": day, "hour": hour}},
            )
            raise
        finally:
            session.close()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all registered users from the database.
        
        Returns:
            List[Dict]: List of user dictionaries with id, username, and archetype
        """
        from YSimulator.YServer.classes.models import User_mgmt
        
        session = Session(self.engine)
        try:
            users = session.query(User_mgmt).all()
            
            result = []
            for user in users:
                result.append({
                    "id": user.id,
                    "username": user.username,
                    "archetype": user.archetype,
                })
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Error getting all users: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return []
        finally:
            session.close()

    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """
        Update the archetype of a user in the database.
        
        Args:
            user_id: User ID (UUID string)
            new_archetype: New archetype value
            
        Returns:
            bool: True if update successful, False otherwise
        """
        from YSimulator.YServer.classes.models import User_mgmt
        
        session = Session(self.engine)
        try:
            user = session.query(User_mgmt).filter(User_mgmt.id == user_id).first()
            
            if user:
                user.archetype = new_archetype
                session.commit()
                return True
            else:
                self.logger.warning(
                    f"User {user_id} not found for archetype update"
                )
                return False
                
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error updating user archetype: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id, "new_archetype": new_archetype}}
            )
            return False
        finally:
            session.close()

    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a website (news source) to the database.
        
        Args:
            website_data (dict): Website information with keys:
                - id: Website UUID
                - name: Website name
                - rss: RSS feed URL
                - leaning: Political leaning (optional)
                - category: Content category (optional)
                - country: Country code (optional)
                - language: Language code (optional)
                - last_fetched: Last fetch timestamp (optional)
                
        Returns:
            str: Website ID if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Website
        import uuid
        
        session = Session(self.engine)
        try:
            # Generate UUID if not provided
            website_id = website_data.get("id", str(uuid.uuid4()))
            
            # Check if website already exists by RSS URL
            existing = session.query(Website).filter(Website.rss == website_data.get("rss")).first()
            if existing:
                return existing.id
            
            # Create new website
            website = Website(
                id=website_id,
                name=website_data.get("name"),
                rss=website_data.get("rss"),
                leaning=website_data.get("leaning"),
                category=website_data.get("category"),
                country=website_data.get("country"),
                language=website_data.get("language"),
                last_fetched=website_data.get("last_fetched", str(uuid.uuid4()))
            )
            
            session.add(website)
            session.commit()
            
            # Also cache in Redis if enabled
            if self.use_redis:
                redis_key = self._redis_key("websites", website_id)
                self.redis_client.hset(redis_key, mapping={
                    "id": website_id,
                    "name": website_data.get("name", ""),
                    "rss": website_data.get("rss", ""),
                    "category": website_data.get("category", ""),
                    "language": website_data.get("language", "")
                })
            
            return website_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding website: {e}",
                extra={"extra_data": {"error": str(e), "website_data": website_data}}
            )
            return None
        finally:
            session.close()

    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a news article to the database.
        
        Ensures the related website exists before creating the article.
        If website_id is provided but doesn't exist, returns None.
        If rss_url is provided instead of website_id, looks up or creates the website.
        
        Args:
            article_data (dict): Article information with keys:
                - id: Article UUID (optional, will be generated)
                - title: Article title
                - summary: Article summary/description
                - website_id: Reference to website (UUID) - required if rss_url not provided
                - rss_url: RSS feed URL - used to lookup/create website if website_id not provided
                - website_name: Website name - used when creating website from rss_url
                - link: Article URL
                - fetched_on: Fetch timestamp (UUID format)
                
        Returns:
            str: Article ID if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Article, Website
        import uuid
        
        session = Session(self.engine)
        try:
            # Get or ensure website exists
            website_id = article_data.get("website_id")
            
            # If no website_id provided, try to get it from rss_url
            if not website_id:
                rss_url = article_data.get("rss_url")
                if rss_url:
                    # Look up website by RSS URL
                    website = session.query(Website).filter(Website.rss == rss_url).first()
                    if website:
                        website_id = website.id
                    else:
                        # Create new website
                        website_id = str(uuid.uuid4())
                        new_website = Website(
                            id=website_id,
                            name=article_data.get("website_name", "Unknown"),
                            rss=rss_url,
                            category=article_data.get("category"),
                            language=article_data.get("language"),
                            country=article_data.get("country"),
                            leaning=article_data.get("leaning"),
                            last_fetched=str(uuid.uuid4())
                        )
                        session.add(new_website)
                        session.flush()  # Ensure website is created before article
            
            # Verify website exists
            if not website_id:
                self.logger.error("Cannot add article: no website_id or rss_url provided")
                return None
                
            website_exists = session.query(Website).filter(Website.id == website_id).first()
            if not website_exists:
                self.logger.error(
                    f"Cannot add article: website {website_id} does not exist",
                    extra={"extra_data": {"website_id": website_id}}
                )
                return None
            
            # Generate UUID if not provided
            article_id = article_data.get("id", str(uuid.uuid4()))
            
            # Check if article already exists by link
            existing = session.query(Article).filter(Article.link == article_data.get("link")).first()
            if existing:
                return existing.id
            
            # Create new article
            article = Article(
                id=article_id,
                title=article_data.get("title"),
                summary=article_data.get("summary"),
                website_id=website_id,
                link=article_data.get("link"),
                fetched_on=article_data.get("fetched_on", str(uuid.uuid4()))
            )
            
            session.add(article)
            session.commit()
            
            # Also cache in Redis if enabled
            if self.use_redis:
                redis_key = self._redis_key("articles", article_id)
                self.redis_client.hset(redis_key, mapping={
                    "id": article_id,
                    "title": article_data.get("title", ""),
                    "summary": article_data.get("summary", "")[:200],  # Truncate for Redis
                    "website_id": website_id,
                    "link": article_data.get("link", "")
                })
            
            return article_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding article: {e}",
                extra={"extra_data": {"error": str(e), "article_data": article_data}}
            )
            return None
        finally:
            session.close()
    
    def add_image(self, image_data: Dict[str, Any]) -> Optional[str]:
        """
        Add an image to the database.
        
        Args:
            image_data (dict): Image information with keys:
                - id: Image UUID (optional, will be generated)
                - url: Image URL
                - description: Image description (from LLM)
                - article_id: Reference to article (UUID)
                
        Returns:
            str: Image ID if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Image, Article
        import uuid
        
        session = Session(self.engine)
        try:
            # Verify article exists
            article_id = image_data.get("article_id")
            if not article_id:
                self.logger.error("Cannot add image: no article_id provided")
                return None
            
            article_exists = session.query(Article).filter(Article.id == article_id).first()
            if not article_exists:
                self.logger.error(
                    f"Cannot add image: article {article_id} does not exist",
                    extra={"extra_data": {"article_id": article_id}}
                )
                return None
            
            # Generate UUID if not provided
            image_id = image_data.get("id", str(uuid.uuid4()))
            
            # Check if image with same URL already exists for this article
            existing = session.query(Image).filter(
                Image.url == image_data.get("url"),
                Image.article_id == article_id
            ).first()
            if existing:
                self.logger.info(
                    f"Image already exists for article, returning existing ID: {existing.id}",
                    extra={"extra_data": {"image_id": existing.id, "article_id": article_id, "url": image_data.get("url")[:80]}}
                )
                return existing.id
            
            # Create new image
            image = Image(
                id=image_id,
                url=image_data.get("url"),
                description=image_data.get("description"),
                article_id=article_id
            )
            
            session.add(image)
            session.commit()
            
            self.logger.info(
                f"Image added successfully: {image_id}",
                extra={"extra_data": {"image_id": image_id, "article_id": article_id, "url": image_data.get("url")[:80], "description_length": len(image_data.get("description", ""))}}
            )
            
            return image_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding image: {e}",
                extra={"extra_data": {"error": str(e), "image_data": image_data}}
            )
            return None
        finally:
            session.close()
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """
        Get a random image from the database.
        
        Returns:
            dict: Image data with keys: id, url, description, article_id
                 Returns None if no images available
        """
        from YSimulator.YServer.classes.models import Image
        import random
        
        session = Session(self.engine)
        try:
            # Get all images
            images = session.query(Image).all()
            
            if not images:
                self.logger.info("No images available in database")
                return None
            
            # Select random image
            image = random.choice(images)
            
            return {
                "id": image.id,
                "url": image.url,
                "description": image.description,
                "article_id": image.article_id
            }
            
        except Exception as e:
            self.logger.error(
                f"Error getting random image: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return None
        finally:
            session.close()

    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """
        Get website by RSS URL.
        
        Args:
            rss_url (str): RSS feed URL
            
        Returns:
            dict: Website data if found, None otherwise
        """
        from YSimulator.YServer.classes.models import Website
        
        session = Session(self.engine)
        try:
            website = session.query(Website).filter(Website.rss == rss_url).first()
            
            if website:
                return {
                    "id": website.id,
                    "name": website.name,
                    "rss": website.rss,
                    "category": website.category,
                    "language": website.language
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting website by RSS: {e}",
                extra={"extra_data": {"error": str(e), "rss_url": rss_url}}
            )
            return None
        finally:
            session.close()
    
    def get_interest_by_id(self, interest_id: str) -> Optional[dict]:
        """
        Get interest details by ID.
        
        Args:
            interest_id: Interest UUID (iid)
            
        Returns:
            dict: Interest data with 'iid' and 'interest' keys, or None if not found
        """
        from YSimulator.YServer.classes.models import Interest
        
        session = Session(self.engine)
        try:
            interest = session.query(Interest).filter(Interest.iid == interest_id).first()
            
            if interest:
                return {
                    "iid": interest.iid,
                    "interest": interest.interest
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting interest by ID: {e}",
                extra={"extra_data": {"error": str(e), "interest_id": interest_id}}
            )
            return None
        finally:
            session.close()

    def add_or_get_interest(self, interest_name: str) -> Optional[str]:
        """
        Add an interest to the database or get its ID if it already exists.
        
        Args:
            interest_name: Name of the interest/topic
            
        Returns:
            str: Interest UUID (iid) if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Interest
        import uuid
        
        session = Session(self.engine)
        try:
            # Check if interest already exists
            existing = session.query(Interest).filter(Interest.interest == interest_name).first()
            if existing:
                return existing.iid
            
            # Create new interest
            interest_id = str(uuid.uuid4())
            interest = Interest(iid=interest_id, interest=interest_name)
            session.add(interest)
            session.commit()
            return interest_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding interest: {e}",
                extra={"extra_data": {"error": str(e), "interest_name": interest_name}}
            )
            return None
        finally:
            session.close()

    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """
        Add a user interest association to the database.
        
        Args:
            user_id: User UUID
            interest_id: Interest UUID (iid)
            round_id: Round UUID
            
        Returns:
            bool: True if successful, False otherwise
        """
        from YSimulator.YServer.classes.models import UserInterest
        import uuid
        
        session = Session(self.engine)
        try:
            # Create user interest record
            user_interest_id = str(uuid.uuid4())
            user_interest = UserInterest(
                id=user_interest_id,
                user_id=user_id,
                interest_id=interest_id,
                round_id=round_id
            )
            session.add(user_interest)
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding user interest: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id, "interest_id": interest_id}}
            )
            return False
        finally:
            session.close()

    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """
        Add a post topic association to the database.
        
        Args:
            post_id: Post UUID
            topic_id: Topic UUID (from interests table)
            
        Returns:
            bool: True if successful, False otherwise
        """
        from YSimulator.YServer.classes.models import PostTopic
        import uuid
        
        session = Session(self.engine)
        try:
            # Create post topic record
            post_topic_id = str(uuid.uuid4())
            post_topic = PostTopic(
                id=post_topic_id,
                post_id=post_id,
                topic_id=topic_id
            )
            session.add(post_topic)
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding post topic: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id, "topic_id": topic_id}}
            )
            return False
        finally:
            session.close()

    def get_post_topics(self, post_id: str) -> List[str]:
        """
        Get all topic IDs associated with a post.
        
        Args:
            post_id: Post UUID
            
        Returns:
            List[str]: List of topic UUIDs
        """
        from YSimulator.YServer.classes.models import PostTopic
        
        session = Session(self.engine)
        try:
            post_topics = session.query(PostTopic).filter(PostTopic.post_id == post_id).all()
            return [pt.topic_id for pt in post_topics]
            
        except Exception as e:
            self.logger.error(
                f"Error getting post topics: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}}
            )
            return []
        finally:
            session.close()
    
    def get_user_interests_in_window(self, user_id: str, current_round_id: str, attention_window: int) -> List[Dict[str, str]]:
        """
        Get user interests within the attention window (sliding window for forgetting).
        
        Args:
            user_id: User UUID
            current_round_id: Current round UUID
            attention_window: Number of rounds to look back
            
        Returns:
            List[Dict]: List of user interest records with interest_id and round_id
        """
        from YSimulator.YServer.classes.models import UserInterest, Round
        
        session = Session(self.engine)
        try:
            # Get current round details
            current_round = session.query(Round).filter(Round.id == current_round_id).first()
            if not current_round:
                return []
            
            current_day = current_round.day
            current_hour = current_round.hour
            
            # Calculate the round number (day * 24 + hour)
            current_round_num = (current_day - 1) * 24 + current_hour
            cutoff_round_num = max(0, current_round_num - attention_window)
            
            # Calculate cutoff day and hour
            cutoff_day = (cutoff_round_num // 24) + 1
            cutoff_hour = cutoff_round_num % 24
            
            # Query user interests within the window
            user_interests = session.query(UserInterest, Round).join(
                Round, UserInterest.round_id == Round.id
            ).filter(
                UserInterest.user_id == user_id
            ).filter(
                (Round.day > cutoff_day) | 
                ((Round.day == cutoff_day) & (Round.hour >= cutoff_hour))
            ).all()
            
            return [
                {"interest_id": ui.interest_id, "round_id": ui.round_id}
                for ui, _ in user_interests
            ]
            
        except Exception as e:
            self.logger.error(
                f"Error getting user interests in window: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id}}
            )
            return []
        finally:
            session.close()
    
    def compute_interest_counts_in_window(self, user_id: str, current_round_id: str, attention_window: int) -> Dict[str, int]:
        """
        Compute interest counts for a user within the attention window.
        
        Args:
            user_id: User UUID
            current_round_id: Current round UUID
            attention_window: Number of rounds to look back
            
        Returns:
            Dict[str, int]: Map of interest_id to count within the window
        """
        interests_in_window = self.get_user_interests_in_window(user_id, current_round_id, attention_window)
        
        # Count occurrences of each interest
        interest_counts = {}
        for entry in interests_in_window:
            interest_id = entry["interest_id"]
            interest_counts[interest_id] = interest_counts.get(interest_id, 0) + 1
        
        return interest_counts
    
    def get_article_topics(self, article_id: str) -> List[str]:
        """
        Get all topic IDs associated with an article.
        
        Args:
            article_id: Article UUID
            
        Returns:
            List[str]: List of topic UUIDs
        """
        from YSimulator.YServer.classes.models import ArticleTopic
        
        session = Session(self.engine)
        try:
            article_topics = session.query(ArticleTopic).filter(ArticleTopic.article_id == article_id).all()
            return [at.topic_id for at in article_topics]
            
        except Exception as e:
            self.logger.error(
                f"Error getting article topics: {e}",
                extra={"extra_data": {"error": str(e), "article_id": article_id}}
            )
            return []
        finally:
            session.close()
    
    def get_article(self, article_id: str) -> Optional[dict]:
        """
        Get article details by ID.
        
        Args:
            article_id: Article UUID
            
        Returns:
            dict: Article data or None if not found
        """
        from YSimulator.YServer.classes.models import Article
        
        session = Session(self.engine)
        try:
            article = session.query(Article).filter(Article.id == article_id).first()
            if article:
                return {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "website_id": article.website_id,
                    "link": article.link,
                    "fetched_on": article.fetched_on
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting article: {e}",
                extra={"extra_data": {"error": str(e), "article_id": article_id}}
            )
            return None
        finally:
            session.close()
    
    def add_article_topic(self, article_id: str, topic_id: str) -> bool:
        """
        Add an article topic association to the database.
        
        Args:
            article_id: Article UUID
            topic_id: Topic UUID (from interests table)
            
        Returns:
            bool: True if successful, False otherwise
        """
        from YSimulator.YServer.classes.models import ArticleTopic
        import uuid
        
        self.logger.info(f"add_article_topic called: article_id={article_id}, topic_id={topic_id}")
        
        session = Session(self.engine)
        try:
            # Check if already exists
            existing = session.query(ArticleTopic).filter(
                ArticleTopic.article_id == article_id,
                ArticleTopic.topic_id == topic_id
            ).first()
            
            if existing:
                self.logger.info(f"Article-topic association already exists: {article_id} - {topic_id}")
                return True  # Already exists, no need to add
            
            # Create article topic record
            article_topic_id = str(uuid.uuid4())
            article_topic = ArticleTopic(
                id=article_topic_id,
                article_id=article_id,
                topic_id=topic_id
            )
            session.add(article_topic)
            session.commit()
            self.logger.info(f"Successfully created article_topic entry: id={article_topic_id}, article_id={article_id}, topic_id={topic_id}")
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding article topic: {e}",
                extra={"extra_data": {"error": str(e), "article_id": article_id, "topic_id": topic_id}}
            )
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            session.close()

    def add_or_get_hashtag(self, hashtag_text: str) -> Optional[str]:
        """
        Add a hashtag to the database or get its UUID if it already exists.
        
        Args:
            hashtag_text: Hashtag text (without # prefix)
            
        Returns:
            str: Hashtag UUID, or None if error
        """
        import uuid
        
        try:
            if self.use_redis:
                # Check if hashtag exists in Redis
                hashtag_lookup_key = self._redis_key("hashtags", f"lookup:{hashtag_text}")
                existing_id = self.redis_client.get(hashtag_lookup_key)
                
                if existing_id:
                    return existing_id
                
                # Create new hashtag
                hashtag_id = str(uuid.uuid4())
                hashtag_data = {
                    "id": hashtag_id,
                    "hashtag": hashtag_text
                }
                
                # Store hashtag
                key = self._redis_key("hashtags", hashtag_id)
                self.redis_client.hset(key, mapping=hashtag_data)
                
                # Store lookup index
                self.redis_client.set(hashtag_lookup_key, hashtag_id)
                
                self.logger.info(f"Created new hashtag: id={hashtag_id}, hashtag={hashtag_text}")
                return hashtag_id
            else:
                from YSimulator.YServer.classes.models import Hashtag
                session = Session(self.engine)
                try:
                    # Check if hashtag already exists
                    existing = session.query(Hashtag).filter(Hashtag.hashtag == hashtag_text).first()
                    
                    if existing:
                        return existing.id
                    
                    # Create new hashtag
                    hashtag_id = str(uuid.uuid4())
                    hashtag = Hashtag(
                        id=hashtag_id,
                        hashtag=hashtag_text
                    )
                    session.add(hashtag)
                    session.commit()
                    self.logger.info(f"Created new hashtag: id={hashtag_id}, hashtag={hashtag_text}")
                    return hashtag_id
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding/getting hashtag: {e}",
                extra={"extra_data": {"error": str(e), "hashtag": hashtag_text}}
            )
            return None

    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """
        Add a post-hashtag association to the database.
        
        Args:
            post_id: Post UUID
            hashtag_id: Hashtag UUID
            
        Returns:
            bool: True if successful, False otherwise
        """
        import uuid
        
        try:
            post_hashtag_id = str(uuid.uuid4())
            post_hashtag_data = {
                "id": post_hashtag_id,
                "post_id": post_id,
                "hashtag_id": hashtag_id
            }
            
            if self.use_redis:
                # Store post hashtag in Redis
                key = self._redis_key("post_hashtags", post_hashtag_id)
                redis_data = {k: str(v) for k, v in post_hashtag_data.items()}
                self.redis_client.hset(key, mapping=redis_data)
                
                # Index by post_id for retrieval
                post_hashtags_key = self._redis_key("post_hashtags", f"by_post:{post_id}")
                self.redis_client.sadd(post_hashtags_key, post_hashtag_id)
                
                # Check for duplicates
                hashtag_post_key = self._redis_key("post_hashtags", f"check:{post_id}:{hashtag_id}")
                if self.redis_client.exists(hashtag_post_key):
                    return True  # Already exists
                self.redis_client.set(hashtag_post_key, "1")
                
                return True
            else:
                from YSimulator.YServer.classes.models import PostHashtag
                session = Session(self.engine)
                try:
                    # Check if already exists
                    existing = session.query(PostHashtag).filter(
                        PostHashtag.post_id == post_id,
                        PostHashtag.hashtag_id == hashtag_id
                    ).first()
                    
                    if existing:
                        return True  # Already exists
                    
                    # Create post hashtag record
                    post_hashtag = PostHashtag(**post_hashtag_data)
                    session.add(post_hashtag)
                    session.commit()
                    return True
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding post hashtag: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id, "hashtag_id": hashtag_id}}
            )
            return False

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their username.
        
        Args:
            username: Username to search for
            
        Returns:
            dict: User data dict with 'id' and other fields, or None if not found
        """
        from YSimulator.YServer.classes.models import User_mgmt
        
        session = Session(self.engine)
        try:
            user = session.query(User_mgmt).filter(User_mgmt.username == username).first()
            
            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting user by username: {e}",
                extra={"extra_data": {"error": str(e), "username": username}}
            )
            return None
        finally:
            session.close()

    def add_mention(self, mention_data: Dict[str, Any]) -> bool:
        """
        Add a mention to the database.
        
        Args:
            mention_data: Dict with keys: user_id, post_id, round, answered (default 0)
            
        Returns:
            bool: True if successful, False otherwise
        """
        import uuid
        
        try:
            mention_id = str(uuid.uuid4())
            mention_data_with_id = {
                "id": mention_id,
                "user_id": mention_data["user_id"],
                "post_id": mention_data["post_id"],
                "round": mention_data["round"],
                "answered": mention_data.get("answered", 0)
            }
            
            if self.use_redis:
                # Store mention in Redis
                key = self._redis_key("mentions", mention_id)
                redis_data = {k: str(v) for k, v in mention_data_with_id.items()}
                self.redis_client.hset(key, mapping=redis_data)
                
                # Index by user_id for retrieval
                user_mentions_key = self._redis_key("mentions", f"by_user:{mention_data['user_id']}")
                self.redis_client.sadd(user_mentions_key, mention_id)
                
                # Index by post_id for retrieval
                post_mentions_key = self._redis_key("mentions", f"by_post:{mention_data['post_id']}")
                self.redis_client.sadd(post_mentions_key, mention_id)
                
                self.logger.info(f"Created mention: id={mention_id}, user_id={mention_data['user_id']}, post_id={mention_data['post_id']}")
                return True
            else:
                from YSimulator.YServer.classes.models import Mention
                session = Session(self.engine)
                try:
                    mention = Mention(**mention_data_with_id)
                    session.add(mention)
                    session.commit()
                    self.logger.info(f"Created mention: id={mention_id}, user_id={mention_data['user_id']}, post_id={mention_data['post_id']}")
                    return True
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding mention: {e}",
                extra={"extra_data": {"error": str(e), "mention_data": mention_data}}
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
        try:
            if self.use_redis:
                self.logger.debug(f"[REPLY_DB] Getting unreplied mentions for user {user_id} (Redis mode)")
                # Get mention IDs for this user
                user_mentions_key = self._redis_key("mentions", f"by_user:{user_id}")
                mention_ids = self.redis_client.smembers(user_mentions_key)
                
                self.logger.debug(f"[REPLY_DB] Found {len(mention_ids) if mention_ids else 0} total mentions for user {user_id}")
                
                if not mention_ids:
                    return []
                
                # Filter to only unreplied mentions
                unreplied_mentions = []
                for mention_id in mention_ids:
                    # Decode mention_id if it's bytes (Redis returns bytes)
                    mention_id_str = mention_id.decode() if isinstance(mention_id, bytes) else mention_id
                    mention_key = self._redis_key("mentions", mention_id_str)
                    mention_data = self.redis_client.hgetall(mention_key)
                    
                    if mention_data:
                        # Convert bytes to strings and handle answered field properly
                        mention_dict = {
                            k.decode() if isinstance(k, bytes) else k: 
                            v.decode() if isinstance(v, bytes) else v 
                            for k, v in mention_data.items()
                        }
                        # Check if unreplied (answered is "0")
                        answered_value = mention_dict.get("answered", "0")
                        self.logger.debug(f"[REPLY_DB] Mention {mention_id_str}: answered={answered_value}")
                        if answered_value == "0":
                            unreplied_mentions.append(mention_dict)
                
                self.logger.info(f"[REPLY_DB] Returning {len(unreplied_mentions)} unreplied mentions for user {user_id}")
                return unreplied_mentions
            else:
                self.logger.debug(f"[REPLY_DB] Getting unreplied mentions for user {user_id} (SQL mode)")
                from YSimulator.YServer.classes.models import Mention
                session = Session(self.engine)
                try:
                    mentions = session.query(Mention).filter(
                        Mention.user_id == user_id,
                        Mention.answered == 0
                    ).all()
                    
                    result = [
                        {
                            "id": m.id,
                            "user_id": m.user_id,
                            "post_id": m.post_id,
                            "round": m.round,
                            "answered": m.answered
                        }
                        for m in mentions
                    ]
                    self.logger.info(f"[REPLY_DB] Returning {len(result)} unreplied mentions for user {user_id} (SQL)")
                    return result
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"[REPLY_DB] Error getting unreplied mentions for user {user_id}: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id}}
            )
            import traceback
            self.logger.error(f"[REPLY_DB] Traceback: {traceback.format_exc()}")
            return []

    def mark_mention_replied(self, mention_id: str) -> bool:
        """
        Mark a mention as replied by setting answered=1.
        
        Args:
            mention_id: UUID of the mention
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.use_redis:
                mention_key = self._redis_key("mentions", mention_id)
                self.redis_client.hset(mention_key, "answered", "1")
                self.logger.info(f"[REPLY_DB] Marked mention {mention_id} as replied (Redis)")
                return True
            else:
                from YSimulator.YServer.classes.models import Mention
                session = Session(self.engine)
                try:
                    mention = session.query(Mention).filter(Mention.id == mention_id).first()
                    if mention:
                        mention.answered = 1
                        session.commit()
                        self.logger.info(f"[REPLY_DB] Marked mention {mention_id} as replied (DB)")
                        return True
                    else:
                        self.logger.warning(f"[REPLY_DB] Mention {mention_id} not found - cannot mark as replied")
                        return False
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"[REPLY_DB] Error marking mention {mention_id} as replied: {e}",
                extra={"extra_data": {"error": str(e), "mention_id": mention_id}}
            )
            import traceback
            self.logger.error(f"[REPLY_DB] Traceback: {traceback.format_exc()}")
            return False

    def get_post_sentiment(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get sentiment data for a post/comment.
        
        Returns the first sentiment entry found for the post.
        Since posts can have multiple sentiment entries (one per topic),
        this returns the first one found.
        
        Args:
            post_id: UUID of the post/comment
            
        Returns:
            dict: Sentiment data with keys: id, post_id, neg, pos, neu, compound, etc.
                  or None if no sentiment found
        """
        try:
            if self.use_redis:
                # Get sentiment IDs for this post
                post_sentiments_key = self._redis_key("post_sentiment", f"by_post:{post_id}")
                sentiment_ids = self.redis_client.smembers(post_sentiments_key)
                
                if not sentiment_ids:
                    return None
                
                # Get the first sentiment
                sentiment_id = list(sentiment_ids)[0]
                key = self._redis_key("post_sentiment", sentiment_id)
                sentiment_data = self.redis_client.hgetall(key)
                
                if sentiment_data:
                    # Convert string values back to appropriate types
                    return {
                        "id": sentiment_data.get("id"),
                        "post_id": sentiment_data.get("post_id"),
                        "user_id": sentiment_data.get("user_id"),
                        "topic_id": sentiment_data.get("topic_id"),
                        "round": int(sentiment_data.get("round", 0)),
                        "neg": float(sentiment_data.get("neg", 0.0)) if sentiment_data.get("neg") else None,
                        "pos": float(sentiment_data.get("pos", 0.0)) if sentiment_data.get("pos") else None,
                        "neu": float(sentiment_data.get("neu", 0.0)) if sentiment_data.get("neu") else None,
                        "compound": float(sentiment_data.get("compound", 0.0)) if sentiment_data.get("compound") else None,
                        "sentiment_parent": sentiment_data.get("sentiment_parent", ""),
                        "is_post": int(sentiment_data.get("is_post", 0)),
                        "is_comment": int(sentiment_data.get("is_comment", 0)),
                        "is_reaction": int(sentiment_data.get("is_reaction", 0))
                    }
                return None
            else:
                from YSimulator.YServer.classes.models import PostSentiment
                session = Session(self.engine)
                try:
                    sentiment = session.query(PostSentiment).filter(
                        PostSentiment.post_id == post_id
                    ).first()
                    
                    if sentiment:
                        return {
                            "id": sentiment.id,
                            "post_id": sentiment.post_id,
                            "user_id": sentiment.user_id,
                            "topic_id": sentiment.topic_id,
                            "round": sentiment.round,
                            "neg": sentiment.neg,
                            "pos": sentiment.pos,
                            "neu": sentiment.neu,
                            "compound": sentiment.compound,
                            "sentiment_parent": sentiment.sentiment_parent,
                            "is_post": sentiment.is_post,
                            "is_comment": sentiment.is_comment,
                            "is_reaction": sentiment.is_reaction
                        }
                    return None
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error getting post sentiment: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}}
            )
            return None

    def add_post_sentiment(self, sentiment_data: Dict[str, Any]) -> bool:
        """
        Add sentiment analysis data for a post/comment.
        
        Args:
            sentiment_data: Dict with keys: post_id, user_id, topic_id, round,
                          neg, pos, neu, compound, sentiment_parent,
                          is_post, is_comment, is_reaction
            
        Returns:
            bool: True if successful, False otherwise
        """
        import uuid
        
        try:
            sentiment_id = str(uuid.uuid4())
            sentiment_data_with_id = {
                "id": sentiment_id,
                "post_id": sentiment_data["post_id"],
                "user_id": sentiment_data["user_id"],
                "topic_id": sentiment_data["topic_id"],
                "round": sentiment_data["round"],
                "neg": sentiment_data.get("neg"),
                "pos": sentiment_data.get("pos"),
                "neu": sentiment_data.get("neu"),
                "compound": sentiment_data.get("compound"),
                "sentiment_parent": sentiment_data.get("sentiment_parent"),
                "is_post": sentiment_data.get("is_post", 0),
                "is_comment": sentiment_data.get("is_comment", 0),
                "is_reaction": sentiment_data.get("is_reaction", 0)
            }
            
            if self.use_redis:
                # Store sentiment in Redis
                key = self._redis_key("post_sentiment", sentiment_id)
                # Filter out None values for Redis
                redis_data = {k: str(v) if v is not None else "" for k, v in sentiment_data_with_id.items()}
                self.redis_client.hset(key, mapping=redis_data)
                
                # Index by post_id for retrieval
                post_sentiments_key = self._redis_key("post_sentiment", f"by_post:{sentiment_data['post_id']}")
                self.redis_client.sadd(post_sentiments_key, sentiment_id)
                
                return True
            else:
                from YSimulator.YServer.classes.models import PostSentiment
                session = Session(self.engine)
                try:
                    sentiment = PostSentiment(**sentiment_data_with_id)
                    session.add(sentiment)
                    session.commit()
                    return True
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding post sentiment: {e}",
                extra={"extra_data": {"error": str(e), "sentiment_data": sentiment_data}}
            )
            return False

    def add_post_toxicity(self, toxicity_data: Dict[str, Any]) -> bool:
        """
        Add toxicity analysis data for a post/comment.
        
        Args:
            toxicity_data: Dict with keys: post_id, toxicity, severe_toxicity,
                          identity_attack, insult, profanity, threat,
                          sexually_explicit, flirtation
            
        Returns:
            bool: True if successful, False otherwise
        """
        import uuid
        
        try:
            toxicity_id = str(uuid.uuid4())
            toxicity_data_with_id = {
                "id": toxicity_id,
                "post_id": toxicity_data["post_id"],
                "toxicity": toxicity_data.get("toxicity", 0.0),
                "severe_toxicity": toxicity_data.get("severe_toxicity", 0.0),
                "identity_attack": toxicity_data.get("identity_attack", 0.0),
                "insult": toxicity_data.get("insult", 0.0),
                "profanity": toxicity_data.get("profanity", 0.0),
                "threat": toxicity_data.get("threat", 0.0),
                "sexually_explicit": toxicity_data.get("sexually_explicit", 0.0),
                "flirtation": toxicity_data.get("flirtation", 0.0)
            }
            
            if self.use_redis:
                # Store toxicity in Redis
                key = self._redis_key("post_toxicity", toxicity_id)
                # Convert all values to strings for Redis
                redis_data = {k: str(v) for k, v in toxicity_data_with_id.items()}
                self.redis_client.hset(key, mapping=redis_data)
                
                # Index by post_id for retrieval
                post_toxicity_key = self._redis_key("post_toxicity", f"by_post:{toxicity_data['post_id']}")
                self.redis_client.set(post_toxicity_key, toxicity_id)
                
                return True
            else:
                from YSimulator.YServer.classes.models import PostToxicity
                session = Session(self.engine)
                try:
                    toxicity = PostToxicity(**toxicity_data_with_id)
                    session.add(toxicity)
                    session.commit()
                    return True
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding post toxicity: {e}",
                extra={"extra_data": {"error": str(e), "toxicity_data": toxicity_data}}
            )
            return False

    def get_emotion_by_name(self, emotion_name: str) -> Optional[Dict[str, Any]]:
        """
        Get an emotion by its name.
        
        Args:
            emotion_name: Name of the emotion (e.g., "joy", "anger")
            
        Returns:
            dict: Emotion data with 'id', 'emotion', 'icon' fields, or None if not found
        """
        from YSimulator.YServer.classes.models import Emotion
        
        session = Session(self.engine)
        try:
            emotion = session.query(Emotion).filter(Emotion.emotion == emotion_name).first()
            
            if emotion:
                return {
                    "id": emotion.id,
                    "emotion": emotion.emotion,
                    "icon": emotion.icon
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting emotion by name: {e}",
                extra={"extra_data": {"error": str(e), "emotion_name": emotion_name}}
            )
            return None
        finally:
            session.close()

    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """
        Add an emotion association to a post.
        
        Args:
            post_id: UUID of the post/comment
            emotion_id: UUID of the emotion
            
        Returns:
            bool: True if successful, False otherwise
        """
        import uuid
        
        try:
            post_emotion_id = str(uuid.uuid4())
            post_emotion_data = {
                "id": post_emotion_id,
                "post_id": post_id,
                "emotion_id": emotion_id
            }
            
            if self.use_redis:
                # Store post emotion in Redis
                key = self._redis_key("post_emotions", post_emotion_id)
                redis_data = {k: str(v) for k, v in post_emotion_data.items()}
                self.redis_client.hset(key, mapping=redis_data)
                
                # Index by post_id for retrieval
                post_emotions_key = self._redis_key("post_emotions", f"by_post:{post_id}")
                self.redis_client.sadd(post_emotions_key, post_emotion_id)
                
                # Index by emotion_id + post_id for duplicate checking (store as set)
                emotion_post_key = self._redis_key("post_emotions", f"check:{post_id}:{emotion_id}")
                if self.redis_client.exists(emotion_post_key):
                    return True  # Already exists
                self.redis_client.set(emotion_post_key, "1")
                
                return True
            else:
                from YSimulator.YServer.classes.models import PostEmotion
                session = Session(self.engine)
                try:
                    # Check if already exists
                    existing = session.query(PostEmotion).filter(
                        PostEmotion.post_id == post_id,
                        PostEmotion.emotion_id == emotion_id
                    ).first()
                    
                    if existing:
                        return True  # Already exists
                    
                    # Create post emotion record
                    post_emotion = PostEmotion(**post_emotion_data)
                    session.add(post_emotion)
                    session.commit()
                    return True
                finally:
                    session.close()
            
        except Exception as e:
            self.logger.error(
                f"Error adding post emotion: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id, "emotion_id": emotion_id}}
            )
            return False

    def initialize_emotions_table(self) -> bool:
        """
        Initialize the emotions table with the GoEmotions taxonomy.
        
        This creates all 28 emotions from the taxonomy if they don't already exist.
        
        Returns:
            bool: True if successful, False otherwise
        """
        from YSimulator.YServer.classes.models import Emotion
        import uuid
        
        # GoEmotions taxonomy with icon mappings
        emotions_data = [
            ("amusement", "mdi-emoticon-happy"),
            ("admiration", "mdi-weather-sunny"),
            ("anger", "mdi-emoticon-devil"),
            ("annoyance", "mdi-emoticon-tongue"),
            ("approval", "mdi-thumb-up-outline"),
            ("caring", "mdi-cake"),
            ("confusion", "mdi-emoticon-neutral"),
            ("curiosity", "mdi-beaker-outline"),
            ("desire", "mdi-cash-multiple"),
            ("disappointment", "mdi-close-circle"),
            ("disapproval", "mdi-thumb-down-outline"),
            ("disgust", "mdi-emoticon-poop"),
            ("embarrassment", "mdi-minus-circle"),
            ("excitement", "mdi-rocket"),
            ("fear", "mdi-weather-lightning"),
            ("gratitude", "mdi-panda"),
            ("grief", "mdi-weather-pouring"),
            ("joy", "mdi-emoticon"),
            ("love", "mdi-heart"),
            ("nervousness", "mdi-alert"),
            ("optimism", "mdi-leaf"),
            ("pride", "mdi-emoticon-cool"),
            ("realization", "mdi-lightbulb-outline"),
            ("relief", "mdi-weather-sunset-up"),
            ("remorse", "mdi-ambulance"),
            ("sadness", "mdi-emoticon-sad"),
            ("surprise", "mdi-wallet-giftcard"),
            ("trust", "mdi-brightness-5"),
        ]
        
        session = Session(self.engine)
        try:
            created_count = 0
            for emotion_name, icon in emotions_data:
                # Check if emotion already exists
                existing = session.query(Emotion).filter(Emotion.emotion == emotion_name).first()
                
                if not existing:
                    # Create new emotion
                    emotion_id = str(uuid.uuid4())
                    emotion = Emotion(
                        id=emotion_id,
                        emotion=emotion_name,
                        icon=icon
                    )
                    session.add(emotion)
                    created_count += 1
            
            session.commit()
            self.logger.info(f"Initialized emotions table: {created_count} new emotions added, {len(emotions_data) - created_count} already existed")
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error initializing emotions table: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return False
        finally:
            session.close()
