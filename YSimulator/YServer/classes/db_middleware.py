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

from YSimulator.YServer.classes.models import Base, Reaction, Post, User_mgmt, Round


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
    ):
        """
        Initialize the database middleware.

        Args:
            db_config: Database configuration dict with 'type' and backend-specific settings
            config_path: Path to configuration directory (for SQLite database file)
            redis_config: Redis configuration dict with keys: host, port, db, password, sliding_window_days (optional)
            logger: Logger instance for logging operations
        """
        from pathlib import Path

        self.logger = logger or logging.getLogger(__name__)
        self.use_redis = False
        self.redis_client = None
        self.redis_sliding_window_days = 2  # Default: keep last 2 days in Redis
        self.db_type = db_config.get("type", "sqlite").lower()
        self.config_path = Path(config_path)

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

                # Store user data
                self.redis_client.hset(key, mapping=user_data)
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

            if self.use_redis:
                # Store post
                key = self._redis_key("posts", post_id)
                self.redis_client.hset(key, mapping=post_data)

                # Add to posts list
                self.redis_client.lpush(self._redis_key("posts", "recent"), post_id)
                # Keep only last 50
                self.redis_client.ltrim(self._redis_key("posts", "recent"), 0, 49)

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
                self.redis_client.hset(key, mapping=interaction_data)
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

                # Transfer posts and track old ones for removal
                posts_to_remove = []
                old_post_ids = set()  # Collect old post IDs during first pass
                cutoff_day = day - self.redis_sliding_window_days

                for key in post_keys:
                    post_data = self.redis_client.hgetall(key)
                    if post_data and "id" in post_data:
                        post_day = int(post_data.get("day", 0))

                        # Check if post already exists in SQLite
                        existing = session.query(Post).filter_by(id=post_data["id"]).first()
                        if not existing:
                            post = Post(
                                id=post_data["id"],
                                tweet=post_data.get("content", ""),
                                user_id=int(post_data.get("agent_id", 0)),
                                round=int(post_data.get("round", 0)),
                            )
                            session.add(post)
                            posts_count += 1

                        # Mark for removal if outside sliding window (strictly less than cutoff)
                        # Keep posts from cutoff_day onwards (inclusive)
                        if post_day < cutoff_day:
                            posts_to_remove.append(key)
                            old_post_ids.add(post_data["id"])

                # Get all interaction keys
                interaction_pattern = self._redis_key("interactions", "*")
                interaction_keys = [
                    k
                    for k in self.redis_client.keys(interaction_pattern)
                    if not k.endswith(":counter")
                ]

                # Transfer interactions and mark old ones for removal
                interactions_to_remove = []

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
                                user_id=int(interaction_data.get("agent_id", 0)),
                                post_id=interaction_data.get("post_id", ""),
                                type=interaction_data.get("type", ""),
                                round=int(interaction_data.get("round", 0)),
                            )
                            session.add(interaction)
                            interactions_count += 1

                        # Mark for removal if it references an old post
                        if interaction_data.get("post_id") in old_post_ids:
                            interactions_to_remove.append(key)

                # Commit all to SQLite
                session.commit()

                # Remove old data from Redis (outside sliding window)
                if posts_to_remove:
                    self.redis_client.delete(*posts_to_remove)
                    removed_posts_count = len(posts_to_remove)

                if interactions_to_remove:
                    self.redis_client.delete(*interactions_to_remove)
                    removed_interactions_count = len(interactions_to_remove)

                # Clean up recent posts list - remove references to deleted posts
                if old_post_ids:
                    recent_key = self._redis_key("posts", "recent")
                    for old_post_id in old_post_ids:
                        self.redis_client.lrem(recent_key, 0, old_post_id)

                self.logger.info(
                    f"Consolidated Redis data for day {day}",
                    extra={
                        "extra_data": {
                            "day": day,
                            "posts_saved": posts_count,
                            "interactions_saved": interactions_count,
                            "posts_removed": removed_posts_count,
                            "interactions_removed": removed_interactions_count,
                            "sliding_window_days": self.redis_sliding_window_days,
                            "cutoff_day": cutoff_day,
                        }
                    },
                )

                return {
                    "posts": posts_count,
                    "interactions": interactions_count,
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
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": f"Consolidation failed: {str(e)}",
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
