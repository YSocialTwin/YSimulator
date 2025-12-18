"""
Database middleware for YSimulator.

This module provides a middleware layer that can use either Redis (if available)
or SQLite as the database backend. The middleware abstracts database operations
to allow seamless switching between backends.
"""

import json
import logging
from typing import Any, Dict, List, Optional

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classes.models import Base, InteractionModel, PostModel, User_mgmt


class DatabaseMiddleware:
    """
    Database middleware that supports both Redis and SQLite backends.

    If Redis is available and configured, it will be used as the primary storage.
    Otherwise, SQLite will be used as a fallback.
    """

    def __init__(
        self,
        sqlite_db_path: str,
        redis_config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the database middleware.

        Args:
            sqlite_db_path: Path to SQLite database file (always required as fallback)
            redis_config: Redis configuration dict with keys: host, port, db, password (optional)
            logger: Logger instance for logging operations
        """
        self.logger = logger or logging.getLogger(__name__)
        self.use_redis = False
        self.redis_client = None

        # Try to initialize Redis if explicitly configured with enabled=true and host specified
        if redis_config and isinstance(redis_config, dict) and redis_config.get("enabled", False):
            # Validate that Redis host is provided
            if not redis_config.get("host"):
                self.logger.info(
                    "Redis is enabled but no host specified in config, using SQLite only"
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
                        f"Redis connection failed, falling back to SQLite: {e}",
                        extra={"extra_data": {"error": str(e)}},
                    )
                    self.use_redis = False
                    self.redis_client = None

        # Always initialize SQLite as fallback
        self.engine = create_engine(f"sqlite:///{sqlite_db_path}")
        Base.metadata.create_all(self.engine)
        self.logger.info(
            "SQLite database initialized",
            extra={"extra_data": {"db_path": sqlite_db_path, "redis_enabled": self.use_redis}},
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

    def add_post(self, post_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a post to the database.

        Args:
            post_data: Dictionary containing post data

        Returns:
            int: Post ID if successful, None otherwise
        """
        try:
            if self.use_redis:
                # Generate post ID
                post_id = self.redis_client.incr(self._redis_key("posts", "counter"))
                post_data["id"] = post_id

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
                    post = PostModel(**post_data)
                    session.add(post)
                    session.flush()
                    post_id = post.id
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
            if self.use_redis:
                # Generate interaction ID
                interaction_id = self.redis_client.incr(self._redis_key("interactions", "counter"))
                interaction_data["id"] = interaction_id

                # Store interaction
                key = self._redis_key("interactions", interaction_id)
                self.redis_client.hset(key, mapping=interaction_data)
                return True
            else:
                session = Session(self.engine)
                try:
                    interaction = InteractionModel(**interaction_data)
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

    def get_recent_posts(self, limit: int = 50) -> List[int]:
        """
        Get recent post IDs.

        Args:
            limit: Maximum number of posts to return

        Returns:
            List of post IDs
        """
        try:
            if self.use_redis:
                post_ids = self.redis_client.lrange(
                    self._redis_key("posts", "recent"), 0, limit - 1
                )
                return [int(pid) for pid in post_ids]
            else:
                session = Session(self.engine)
                try:
                    posts = (
                        session.query(PostModel).order_by(PostModel.id.desc()).limit(limit).all()
                    )
                    return [post.id for post in posts]
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting recent posts: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
