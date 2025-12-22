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
