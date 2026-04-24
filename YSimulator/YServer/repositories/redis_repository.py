"""
Redis-based repository implementations.

This module provides concrete implementations of repository interfaces
using Redis for high-performance caching operations.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from .base_repository import (
    FollowRepository,
    InterestRepository,
    PostRepository,
    RecommendationRepository,
    UserRepository,
)


class RedisUserRepository(UserRepository):
    """Redis implementation of UserRepository."""

    def __init__(
        self, redis_client, key_prefix: str = "ysim", logger: Optional[logging.Logger] = None
    ):
        """Initialize Redis user repository."""
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.logger = logger or logging.getLogger(__name__)

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key."""
        if id is not None:
            return f"{self.key_prefix}:{table}:{id}"
        return f"{self.key_prefix}:{table}"

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """Register a single user."""
        try:
            user_id = user_data["id"]
            key = self._redis_key("user_mgmt", user_id)

            # Check if user already exists
            if self.redis_client.exists(key):
                return False

            # Filter out None values for Redis
            redis_data = {k: v for k, v in user_data.items() if v is not None}

            # Store user data
            self.redis_client.hset(key, mapping=redis_data)
            # Add to user set
            self.redis_client.sadd(self._redis_key("user_mgmt", "ids"), user_id)

            # Create username index for fast lookup
            username = user_data.get("username")
            if username:
                username_key = self._redis_key("user_mgmt:by_username", username)
                self.redis_client.set(username_key, user_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error registering user in Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """Register multiple users in a batch."""
        if not users_data:
            return (0, set())

        try:
            registered_count = 0
            newly_registered_ids = set()

            for user_data in users_data:
                user_id = user_data["id"]
                key = self._redis_key("user_mgmt", user_id)

                # Check if user already exists
                if self.redis_client.exists(key):
                    continue

                # Filter out None values for Redis
                redis_data = {k: v for k, v in user_data.items() if v is not None}

                # Store user data
                self.redis_client.hset(key, mapping=redis_data)
                # Add to user set
                self.redis_client.sadd(self._redis_key("user_mgmt", "ids"), user_id)

                # Create username index for fast lookup
                username = user_data.get("username")
                if username:
                    username_key = self._redis_key("user_mgmt:by_username", username)
                    self.redis_client.set(username_key, user_id)

                registered_count += 1
                newly_registered_ids.add(user_id)

            return (registered_count, newly_registered_ids)
        except Exception as e:
            self.logger.error(
                f"Error registering users in batch (Redis): {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(users_data)}},
            )
            return (0, set())

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        try:
            key = self._redis_key("user_mgmt", user_id)
            user_data = self.redis_client.hgetall(key)

            if not user_data:
                return None

            # Decode bytes to strings
            return {
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in user_data.items()
            }
        except Exception as e:
            self.logger.error(
                f"Error getting user from Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        try:
            user_ids = self.redis_client.smembers(self._redis_key("user_mgmt", "ids"))
            users = []

            for user_id in user_ids:
                if isinstance(user_id, bytes):
                    user_id = user_id.decode()
                user_data = self.get_user(user_id)
                if user_data:
                    users.append(user_data)

            return users
        except Exception as e:
            self.logger.error(
                f"Error getting all users from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """Update user's archetype."""
        try:
            key = self._redis_key("user_mgmt", user_id)
            if not self.redis_client.exists(key):
                return False

            self.redis_client.hset(key, "archetype", new_archetype)
            return True
        except Exception as e:
            self.logger.error(
                f"Error updating user archetype in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        try:
            # Look up user ID from username index
            username_key = self._redis_key("user_mgmt:by_username", username)
            user_id = self.redis_client.get(username_key)

            if user_id:
                # Decode if bytes
                user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
                # Get user data by ID (reuse existing method)
                return self.get_user(user_id_str)
            return None
        except Exception as e:
            self.logger.error(
                f"Error getting user by username from Redis: {e}",
                extra={"extra_data": {"error": str(e), "username": username}},
            )
            return None

    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """Update agent's last active day."""
        try:
            key = self._redis_key("user_mgmt", agent_id)
            self.redis_client.hset(key, "last_active_day", str(day))
            return True
        except Exception as e:
            self.logger.error(
                f"Error updating last_active_day in Redis: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id}},
            )
            return False

    def get_churned_agents(self, day: int = None, inactivity_threshold: int = None) -> List[str]:
        """Get churned agents (agents with left_on set)."""
        try:
            churned_agents = []
            # Get all user keys
            pattern = self._redis_key("user_mgmt", "*")
            for key in self.redis_client.scan_iter(match=pattern):
                agent_data = self.redis_client.hgetall(key)
                # Decode bytes to strings
                decoded_data = {
                    k.decode() if isinstance(k, bytes) else k: (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in agent_data.items()
                }
                # Agent is churned if left_on is set
                if decoded_data.get("left_on"):
                    churned_agents.append(decoded_data.get("id"))
            return churned_agents
        except Exception as e:
            self.logger.error(
                f"Error getting churned agents from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def set_agent_churned(self, agent_id: str, churned: bool) -> bool:
        """Set agent churned status."""
        try:
            key = self._redis_key("user_mgmt", agent_id)
            if churned:
                # In db_middleware, this is set_agent_churned(agent_id, round_id)
                # For Redis, we'll just set a marker. The round_id should be passed differently.
                # Looking at the base_repository interface, it expects a bool.
                # However, db_middleware uses round_id. Let's align with db_middleware behavior.
                # Since the signature differs, we'll store "churned" as a marker
                self.redis_client.hset(key, "left_on", "churned")
            else:
                self.redis_client.hdel(key, "left_on")
            return True
        except Exception as e:
            self.logger.error(
                f"Error setting agent churned status in Redis: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id}},
            )
            return False

    def get_inactive_agents(self, current_day: int, inactivity_threshold: int) -> List[str]:
        """Get inactive agents."""
        # Note: db_middleware.get_inactive_agents requires both current_day and
        # inactivity_threshold parameters
        return self.db_middleware.get_inactive_agents(current_day, inactivity_threshold)


class RedisPostRepository(PostRepository):
    """Redis implementation of PostRepository."""

    def __init__(
        self, redis_client, key_prefix: str = "ysim", logger: Optional[logging.Logger] = None
    ):
        """Initialize Redis post repository."""
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.logger = logger or logging.getLogger(__name__)

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key."""
        if id is not None:
            return f"{self.key_prefix}:{table}:{id}"
        return f"{self.key_prefix}:{table}"

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """Add a new post."""
        try:
            post_id = post_data["id"]
            key = self._redis_key("posts", post_id)

            # Filter out None values
            redis_data = {k: str(v) if v is not None else "" for k, v in post_data.items()}

            # Store post data
            self.redis_client.hset(key, mapping=redis_data)
            # Add to posts list (no limit - will be cleaned by visibility_rounds at day end)
            # Using lpush to maintain chronological order (most recent first)
            self.redis_client.lpush(self._redis_key("posts", "recent"), post_id)

            return post_id
        except Exception as e:
            self.logger.error(
                f"Error adding post to Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post by ID."""
        try:
            key = self._redis_key("posts", post_id)
            post_data = self.redis_client.hgetall(key)

            if not post_data:
                return None

            # Decode bytes to strings
            decoded_post = {
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in post_data.items()
            }

            # Add user_id alias for backward compatibility with client code
            if "author" in decoded_post:
                decoded_post["user_id"] = decoded_post["author"]

            return decoded_post
        except Exception as e:
            self.logger.error(
                f"Error getting post from Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """Get recent post IDs."""
        try:
            # Use lrange to get posts from the list (most recent first)
            post_ids = self.redis_client.lrange(self._redis_key("posts", "recent"), 0, limit - 1)
            # Properly decode bytes
            return [pid.decode() if isinstance(pid, bytes) else str(pid) for pid in post_ids]
        except Exception as e:
            self.logger.error(
                f"Error getting recent posts from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """Get thread context for a post."""
        try:
            thread = []
            current_id = post_id

            for _ in range(max_length):
                post = self.get_post(current_id)
                if not post:
                    break

                thread.append(post)

                parent_post = post.get("parent_post")
                if not parent_post or parent_post == "":
                    break

                current_id = parent_post

            return list(reversed(thread))
        except Exception as e:
            self.logger.error(
                f"Error getting thread context from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """Add a reaction/interaction to a post."""
        try:
            interaction_id = interaction_data.get("id")
            key = self._redis_key("interactions", interaction_id)

            # Filter out None values
            redis_data = {k: str(v) if v is not None else "" for k, v in interaction_data.items()}

            # Store interaction data
            self.redis_client.hset(key, mapping=redis_data)

            # Maintain lightweight indexes used by Redis recommenders.
            # Only LIKE reactions are considered for recommendation signals.
            reaction_type = str(interaction_data.get("type", "")).upper()
            post_id = interaction_data.get("post_id")
            user_id = interaction_data.get("user_id")
            if reaction_type == "LIKE" and post_id and user_id:
                self.redis_client.sadd(self._redis_key("post", post_id) + ":reactions", user_id)
                self.redis_client.sadd(self._redis_key("user", user_id) + ":likes", post_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding interaction to Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def increment_post_reaction_count(self, post_id: str) -> bool:
        """Increment the reaction count for a post."""
        try:
            key = self._redis_key("posts", post_id)
            if not self.redis_client.exists(key):
                return False

            # Get current count, increment, and set
            # This matches the db_middleware implementation
            current_count = self.redis_client.hget(key, "reaction_count")
            new_count = int(current_count or 0) + 1
            self.redis_client.hset(key, "reaction_count", new_count)
            return True
        except Exception as e:
            self.logger.error(
                f"Error incrementing post reaction count in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """Associate a topic with a post."""
        try:
            # Store as a set of topics for the post
            key = self._redis_key("post_topics", post_id)
            self.redis_client.sadd(key, topic_id)
            return True
        except Exception as e:
            self.logger.error(
                f"Error adding post topic to Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def get_post_topics(self, post_id: str) -> List[str]:
        """Get all topics associated with a post."""
        try:
            key = self._redis_key("post_topics", post_id)
            topics = self.redis_client.smembers(key)
            return [topic.decode() if isinstance(topic, bytes) else topic for topic in topics]
        except Exception as e:
            self.logger.error(
                f"Error getting post topics from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """Search posts by topic."""
        try:
            # Get all recent post IDs from the list
            all_post_ids = self.redis_client.lrange(self._redis_key("posts", "recent"), 0, -1)
            matching_posts = []

            for post_id in all_post_ids:
                if isinstance(post_id, bytes):
                    post_id = post_id.decode()

                topics = self.get_post_topics(post_id)
                if topic_id in topics:
                    post = self.get_post(post_id)
                    if post and post.get("author") != agent_id:
                        matching_posts.append(post_id)
                        if len(matching_posts) >= limit:
                            break

            return matching_posts
        except Exception as e:
            self.logger.error(
                f"Error searching posts by topic in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def get_active_system_messages(self, user_id: str, round_id: str) -> List[Dict[str, Any]]:
        """System messages are stored in SQL-backed experiment DB, not Redis."""
        return []

    # Metadata methods
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add emotion to a post."""
        try:
            post_emotion_id = str(uuid.uuid4())
            post_emotion_data = {
                "id": post_emotion_id,
                "post_id": post_id,
                "emotion_id": emotion_id,
            }

            # Store post emotion in Redis
            key = self._redis_key("post_emotions", post_emotion_id)
            redis_data = {k: str(v) for k, v in post_emotion_data.items()}
            self.redis_client.hset(key, mapping=redis_data)

            # Index by post_id for retrieval
            post_emotions_key = self._redis_key("post_emotions", f"by_post:{post_id}")
            self.redis_client.sadd(post_emotions_key, post_emotion_id)

            # Index by emotion_id + post_id for duplicate checking
            emotion_post_key = self._redis_key("post_emotions", f"check:{post_id}:{emotion_id}")
            if self.redis_client.exists(emotion_post_key):
                return True  # Already exists
            self.redis_client.set(emotion_post_key, "1")

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding post emotion to Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False

    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """Get emotion ID by name."""
        try:
            # Look up emotion ID from name index
            emotion_name_key = self._redis_key("emotion:by_name", emotion_name)
            emotion_id = self.redis_client.get(emotion_name_key)

            if emotion_id:
                # Decode if bytes
                return emotion_id.decode() if isinstance(emotion_id, bytes) else emotion_id
            return None
        except Exception as e:
            self.logger.error(
                f"Error getting emotion by name from Redis: {e}",
                extra={"extra_data": {"error": str(e), "emotion_name": emotion_name}},
            )
            return None

    def get_emotion_by_name_full(self, emotion_name: str) -> Optional[Dict[str, str]]:
        """Get full emotion data by name (id, emotion, icon)."""
        try:
            # Look up emotion ID from name index
            emotion_name_key = self._redis_key("emotion:by_name", emotion_name)
            emotion_id = self.redis_client.get(emotion_name_key)

            if emotion_id:
                # Decode if bytes
                emotion_id_str = (
                    emotion_id.decode() if isinstance(emotion_id, bytes) else emotion_id
                )
                # Get emotion data from hash
                emotion_key = self._redis_key("emotion", emotion_id_str)
                emotion_data = self.redis_client.hgetall(emotion_key)

                if emotion_data:
                    # Decode all keys and values
                    return {
                        k.decode() if isinstance(k, bytes) else k: (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in emotion_data.items()
                    }
            return None
        except Exception as e:
            self.logger.error(
                f"Error getting emotion by name (full) from Redis: {e}",
                extra={"extra_data": {"error": str(e), "emotion_name": emotion_name}},
            )
            return None

    def initialize_emotions_table(self):
        """Initialize emotions table with standard emotions."""
        # Note: db_middleware uses SQL-only implementation for this
        # Redis repositories typically don't initialize schemas
        self.logger.warning(
            "initialize_emotions_table is typically a SQL-only operation. "
            "Redis implementation will not populate emotions."
        )

    def add_post_sentiment(self, post_id: str, sentiment_score: float) -> bool:
        """Add sentiment score to a post."""
        # Note: base repository signature is simplified compared to db_middleware
        # db_middleware uses add_post_sentiment(sentiment_data: Dict)
        # We'll create a minimal sentiment record with just the score
        try:
            sentiment_id = str(uuid.uuid4())
            sentiment_data = {
                "id": sentiment_id,
                "post_id": post_id,
                "compound": str(sentiment_score),
            }

            # Store sentiment in Redis
            key = self._redis_key("post_sentiment", sentiment_id)
            self.redis_client.hset(key, mapping=sentiment_data)

            # Index by post_id for retrieval
            post_sentiments_key = self._redis_key("post_sentiment", f"by_post:{post_id}")
            self.redis_client.sadd(post_sentiments_key, sentiment_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding post sentiment to Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False

    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """Get sentiment score for a post."""
        try:
            # Get sentiment IDs for this post
            post_sentiments_key = self._redis_key("post_sentiment", f"by_post:{post_id}")
            sentiment_ids = self.redis_client.smembers(post_sentiments_key)

            if not sentiment_ids:
                return None

            # Get the first sentiment
            sentiment_id = list(sentiment_ids)[0]
            sentiment_id_str = (
                sentiment_id.decode() if isinstance(sentiment_id, bytes) else sentiment_id
            )
            key = self._redis_key("post_sentiment", sentiment_id_str)
            sentiment_data = self.redis_client.hgetall(key)

            if sentiment_data:
                # Decode and get compound score
                compound = sentiment_data.get(b"compound") or sentiment_data.get("compound")
                if compound:
                    compound_str = compound.decode() if isinstance(compound, bytes) else compound
                    return float(compound_str) if compound_str else None

            return None
        except Exception as e:
            self.logger.error(
                f"Error getting post sentiment from Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return None

    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add toxicity score to a post."""
        # Note: base repository signature is simplified compared to db_middleware
        # db_middleware uses add_post_toxicity(toxicity_data: Dict)
        # We'll create a minimal toxicity record with just the main score
        try:
            toxicity_id = str(uuid.uuid4())
            toxicity_data = {
                "id": toxicity_id,
                "post_id": post_id,
                "toxicity": str(toxicity_score),
            }

            # Store toxicity in Redis
            key = self._redis_key("post_toxicity", toxicity_id)
            self.redis_client.hset(key, mapping=toxicity_data)

            # Index by post_id for retrieval
            post_toxicity_key = self._redis_key("post_toxicity", f"by_post:{post_id}")
            self.redis_client.set(post_toxicity_key, toxicity_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding post toxicity to Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False

    def add_or_get_hashtag(self, hashtag: str) -> Optional[str]:
        """Add or get hashtag ID."""
        try:
            # Check if hashtag exists in Redis
            hashtag_lookup_key = self._redis_key("hashtags", f"lookup:{hashtag}")
            existing_id = self.redis_client.get(hashtag_lookup_key)

            if existing_id:
                return existing_id.decode() if isinstance(existing_id, bytes) else existing_id

            # Create new hashtag
            hashtag_id = str(uuid.uuid4())
            hashtag_data = {"id": hashtag_id, "hashtag": hashtag}

            # Store hashtag
            key = self._redis_key("hashtags", hashtag_id)
            self.redis_client.hset(key, mapping=hashtag_data)

            # Store lookup index
            self.redis_client.set(hashtag_lookup_key, hashtag_id)

            return hashtag_id
        except Exception as e:
            self.logger.error(
                f"Error adding or getting hashtag from Redis: {e}",
                extra={"extra_data": {"error": str(e), "hashtag": hashtag}},
            )
            return None

    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add hashtag to a post."""
        try:
            post_hashtag_id = str(uuid.uuid4())
            post_hashtag_data = {
                "id": post_hashtag_id,
                "post_id": post_id,
                "hashtag_id": hashtag_id,
            }

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
        except Exception as e:
            self.logger.error(
                f"Error adding post hashtag to Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False

    # Mention methods
    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """Add a mention to a post."""
        try:
            mention_id = str(uuid.uuid4())
            # Note: base repository signature differs from db_middleware
            # db_middleware uses add_mention(mention_data: Dict) with round and answered fields
            # base repository uses add_mention(post_id, mentioned_user_id)
            # We'll store with minimal data and set answered=0 by default
            mention_data = {
                "id": mention_id,
                "user_id": mentioned_user_id,
                "post_id": post_id,
                "answered": "0",
                # Note: round field is missing in this signature
            }

            # Store mention in Redis
            key = self._redis_key("mentions", mention_id)
            self.redis_client.hset(key, mapping=mention_data)

            # Index by user_id for retrieval
            user_mentions_key = self._redis_key("mentions", f"by_user:{mentioned_user_id}")
            self.redis_client.sadd(user_mentions_key, mention_id)

            # Index by post_id for retrieval
            post_mentions_key = self._redis_key("mentions", f"by_post:{post_id}")
            self.redis_client.sadd(post_mentions_key, mention_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding mention to Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions for a user."""
        try:
            # Get mention IDs for this user
            user_mentions_key = self._redis_key("mentions", f"by_user:{user_id}")
            mention_ids = self.redis_client.smembers(user_mentions_key)

            if not mention_ids:
                return []

            # Filter to only unreplied mentions
            unreplied_mentions = []
            for mention_id in mention_ids:
                # Decode mention_id if it's bytes
                mention_id_str = (
                    mention_id.decode() if isinstance(mention_id, bytes) else mention_id
                )
                mention_key = self._redis_key("mentions", mention_id_str)
                mention_data = self.redis_client.hgetall(mention_key)

                if mention_data:
                    # Convert bytes to strings
                    mention_dict = {
                        k.decode() if isinstance(k, bytes) else k: (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in mention_data.items()
                    }
                    # Check if unreplied (answered is "0")
                    if mention_dict.get("answered", "0") == "0":
                        unreplied_mentions.append(mention_dict)

            return unreplied_mentions
        except Exception as e:
            self.logger.error(
                f"Error getting unreplied mentions from Redis: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id}},
            )
            return []

    def get_users_with_unreplied_mentions(self, user_ids: List[str]) -> List[str]:
        """Return user IDs that currently have at least one unreplied mention."""
        if not user_ids:
            return []
        try:
            matched_users = []
            for user_id in user_ids:
                if self.get_unreplied_mentions(user_id):
                    matched_users.append(str(user_id))
            return matched_users
        except Exception as e:
            self.logger.error(
                f"Error getting users with unreplied mentions from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def get_mention_by_id(self, mention_id: str) -> Optional[Dict[str, Any]]:
        """Get mention by ID."""
        try:
            mention_key = self._redis_key("mention", mention_id)
            mention_data = self.redis.hgetall(mention_key)

            if not mention_data:
                return None

            # Convert bytes to strings
            mention_dict = {k.decode(): v.decode() for k, v in mention_data.items()}

            # Add alias for compatibility
            mention_dict["mentioned_user_id"] = mention_dict.get("user_id", "")

            return mention_dict
        except Exception as e:
            self.logger.error(f"Error getting mention by ID from Redis: {e}")
            return None

    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark a mention as replied."""
        try:
            # Note: base repository signature differs from db_middleware
            # db_middleware uses mark_mention_replied(mention_id)
            # base repository uses mark_mention_replied(post_id, mentioned_user_id)
            # We need to find the mention by post_id and user_id

            # Get mentions for this post
            post_mentions_key = self._redis_key("mentions", f"by_post:{post_id}")
            mention_ids = self.redis_client.smembers(post_mentions_key)

            marked = False
            for mention_id in mention_ids:
                mention_id_str = (
                    mention_id.decode() if isinstance(mention_id, bytes) else mention_id
                )
                mention_key = self._redis_key("mentions", mention_id_str)
                mention_data = self.redis_client.hgetall(mention_key)

                if mention_data:
                    # Decode and check if this mention is for the specified user
                    user_id = mention_data.get(b"user_id") or mention_data.get("user_id")
                    if user_id:
                        user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
                        if user_id_str == mentioned_user_id:
                            # Mark as replied
                            self.redis_client.hset(mention_key, "answered", "1")
                            marked = True

            return marked
        except Exception as e:
            self.logger.error(
                f"Error marking mention as replied in Redis: {e}",
                extra={"extra_data": {"error": str(e), "post_id": post_id}},
            )
            return False


class RedisFollowRepository(FollowRepository):
    """Redis implementation of FollowRepository."""

    def __init__(
        self, redis_client, key_prefix: str = "ysim", logger: Optional[logging.Logger] = None
    ):
        """Initialize Redis follow repository."""
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.logger = logger or logging.getLogger(__name__)

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key."""
        if id is not None:
            return f"{self.key_prefix}:{table}:{id}"
        return f"{self.key_prefix}:{table}"

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def add_follow(self, follow_data: Dict[str, Any]) -> bool:
        """Add a follow relationship."""
        try:
            # Generate UUID for follow record
            follow_id = str(uuid.uuid4())
            mapped = dict(follow_data)
            mapped["id"] = follow_id
            mapped["user_id"] = mapped.get("followee_id") or mapped.get("user_id")
            mapped["action"] = mapped.get("action", "follow")
            mapped["round"] = mapped.get("round") or mapped.get("round_id")

            # Store follow relationship in Redis as a hash
            key = self._redis_key("follow", follow_id)
            # Filter out None values for Redis
            redis_data = {k: str(v) if v is not None else "" for k, v in mapped.items()}
            self.redis_client.hset(key, mapping=redis_data)

            # Maintain follows index used by Redis recommenders.
            follower_id = mapped.get("follower_id")
            followee_id = mapped.get("user_id")
            if follower_id and followee_id:
                follows_key = self._redis_key("user", follower_id) + ":follows"
                if mapped["action"] == "follow":
                    self.redis_client.sadd(follows_key, followee_id)
                elif mapped["action"] == "unfollow":
                    self.redis_client.srem(follows_key, followee_id)

            return True
        except Exception as e:
            self.logger.error(
                f"Error adding follow to Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """Add multiple follow relationships in a batch."""
        if not follows_data:
            return 0

        try:
            # Store follow relationships in Redis
            count = 0
            for follow_data in follows_data:
                mapped = dict(follow_data)
                mapped["id"] = mapped.get("id", str(uuid.uuid4()))
                mapped["user_id"] = mapped.get("followee_id") or mapped.get("user_id")
                mapped["action"] = mapped.get("action", "follow")
                mapped["round"] = mapped.get("round") or mapped.get("round_id")

                key = self._redis_key("follow", mapped["id"])
                # Filter out None values for Redis
                redis_data = {k: str(v) if v is not None else "" for k, v in mapped.items()}
                self.redis_client.hset(key, mapping=redis_data)

                follower_id = mapped.get("follower_id")
                followee_id = mapped.get("user_id")
                if follower_id and followee_id:
                    follows_key = self._redis_key("user", follower_id) + ":follows"
                    if mapped["action"] == "follow":
                        self.redis_client.sadd(follows_key, followee_id)
                    elif mapped["action"] == "unfollow":
                        self.redis_client.srem(follows_key, followee_id)
                count += 1

            return count
        except Exception as e:
            self.logger.error(
                f"Error adding follows in batch (Redis): {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(follows_data)}},
            )
            return 0


class RedisInterestRepository(InterestRepository):
    """Redis implementation of InterestRepository."""

    def __init__(
        self, redis_client, key_prefix: str = "ysim", logger: Optional[logging.Logger] = None
    ):
        """Initialize Redis interest repository."""
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.logger = logger or logging.getLogger(__name__)

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key."""
        if id is not None:
            return f"{self.key_prefix}:{table}:{id}"
        return f"{self.key_prefix}:{table}"

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def get_interest_by_id(self, interest_id: str) -> Optional[Dict[str, Any]]:
        """Get interest by ID."""
        try:
            key = self._redis_key("interests", interest_id)
            interest_data = self.redis_client.hgetall(key)

            if not interest_data:
                return None

            return {
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in interest_data.items()
            }
        except Exception as e:
            self.logger.error(
                f"Error getting interest from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def add_or_get_interest(self, interest_name: str) -> Optional[str]:
        """Add a new interest or get existing one's ID."""
        try:
            # Check if interest exists by name
            name_key = self._redis_key("interests:by_name", interest_name)
            existing_id = self.redis_client.get(name_key)

            if existing_id:
                return existing_id.decode() if isinstance(existing_id, bytes) else existing_id

            # Create new interest
            interest_id = str(uuid.uuid4())
            key = self._redis_key("interests", interest_id)

            # Store interest data
            self.redis_client.hset(key, mapping={"iid": interest_id, "interest": interest_name})
            # Create name index
            self.redis_client.set(name_key, interest_id)

            return interest_id
        except Exception as e:
            self.logger.error(
                f"Error adding or getting interest in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""
        try:
            name_key = self._redis_key("interests:by_name", topic_name)
            topic_id = self.redis_client.get(name_key)

            if not topic_id:
                return None

            return topic_id.decode() if isinstance(topic_id, bytes) else topic_id
        except Exception as e:
            self.logger.error(
                f"Error getting topic ID from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""
        try:
            interest = self.get_interest_by_id(topic_id)
            if not interest:
                return None
            return interest.get("interest")
        except Exception as e:
            self.logger.error(
                f"Error getting topic name from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def list_interests(self) -> List[Dict[str, Any]]:
        """Return all known interests/topics."""
        try:
            pattern = self._redis_key("interests", "*")
            records = []
            for key in self.redis_client.scan_iter(match=pattern):
                key_str = key.decode() if isinstance(key, bytes) else key
                if ":by_name:" in key_str:
                    continue
                data = self.redis_client.hgetall(key)
                if not data:
                    continue
                normalized = {
                    k.decode() if isinstance(k, bytes) else k: (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in data.items()
                }
                if normalized.get("iid") and normalized.get("interest"):
                    records.append(normalized)
            return records
        except Exception as e:
            self.logger.error(
                f"Error listing interests from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add a user interest."""
        try:
            # Store as a sorted set with a numeric score for time-based queries
            # If round_id is a UUID string, hash it to get a numeric value
            # If it's already numeric, use it directly
            key = self._redis_key("user_interests", user_id)

            try:
                # Try to use round_id as a number
                score = float(round_id)
            except (ValueError, TypeError):
                # If round_id is a UUID string, use a hash for ordering
                import hashlib

                score = int(hashlib.md5(round_id.encode()).hexdigest()[:8], 16)

            self.redis_client.zadd(key, {interest_id: score})
            return True
        except Exception as e:
            self.logger.error(
                f"Error adding user interest to Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def add_agent_opinion(
        self, agent_id: str, topic_id: str, opinion: float, round_id: str
    ) -> bool:
        """Add an agent opinion on a topic."""
        try:
            # Store as hash with topic_id as field
            key = self._redis_key("agent_opinions", f"{agent_id}:{topic_id}")
            self.redis_client.hset(key, mapping={"opinion": str(opinion), "round_id": round_id})
            return True
        except Exception as e:
            self.logger.error(
                f"Error adding agent opinion to Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion on a topic."""
        try:
            key = self._redis_key("agent_opinions", f"{agent_id}:{topic_id}")
            opinion_data = self.redis_client.hget(key, "opinion")

            if not opinion_data:
                return None

            opinion_str = opinion_data.decode() if isinstance(opinion_data, bytes) else opinion_data
            return float(opinion_str)
        except Exception as e:
            self.logger.error(
                f"Error getting latest agent opinion from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def get_user_interests_in_window(
        self, user_id: str, start_round: int, end_round: int
    ) -> List[str]:
        """Get user interests within a time window."""
        try:
            key = self._redis_key("user_interests", user_id)
            # Use ZRANGEBYSCORE to get interests within the round range
            interests = self.redis_client.zrangebyscore(key, float(start_round), float(end_round))
            return [
                interest.decode() if isinstance(interest, bytes) else interest
                for interest in interests
            ]
        except Exception as e:
            self.logger.error(
                f"Error getting user interests in window from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []


class RedisRecommendationRepository(RecommendationRepository):
    """Redis implementation of RecommendationRepository."""

    def __init__(
        self, redis_client, key_prefix: str = "ysim", logger: Optional[logging.Logger] = None
    ):
        """Initialize Redis recommendation repository."""
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.logger = logger or logging.getLogger(__name__)

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key."""
        if id is not None:
            return f"{self.key_prefix}:{table}:{id}"
        return f"{self.key_prefix}:{table}"

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def get_or_create_round(self, day: int, hour: int) -> str:
        """
        Get or create a round ID.

        Args:
            day: Day number
            hour: Hour/slot number

        Returns:
            Round ID (UUID string)

        Raises:
            RuntimeError: If unable to create or retrieve round
        """
        try:
            # Check if round exists
            key = self._redis_key("rounds", f"{day}:{hour}")
            round_id = self.redis_client.get(key)

            if round_id:
                return round_id.decode() if isinstance(round_id, bytes) else round_id

            # Create new round
            round_id = str(uuid.uuid4())
            self.redis_client.set(key, round_id)

            # Store round details
            round_key = self._redis_key("round_data", round_id)
            self.redis_client.hset(
                round_key, mapping={"id": round_id, "day": str(day), "hour": str(hour)}
            )

            return round_id
        except Exception as e:
            self.logger.error(
                f"Error getting or creating round in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            raise RuntimeError(f"Failed to get or create round for day={day}, hour={hour}: {e}")

    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """
        Cleanup old posts from Redis based on visibility window.

        This is a placeholder implementation. In a production system, you would:
        1. Store post timestamps or round information with each post
        2. Calculate the visibility window based on current_day and current_slot
        3. Only delete posts that fall outside the visibility window

        For now, this returns a status indicating the operation requires implementation.
        """
        try:
            return {
                "status": "requires_implementation",
                "message": "Cleanup logic requires post timestamp indexing. "
                "Posts should be stored with round information for time-based cleanup.",
                "current_day": current_day,
                "current_slot": current_slot,
            }
        except Exception as e:
            self.logger.error(
                f"Error cleaning up old posts from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return {"deleted": 0, "status": "error", "error": str(e)}

    def consolidate_redis_to_sqlite(self, day: int) -> Dict[str, Any]:
        """Consolidate Redis data to SQLite."""
        # This would require both Redis and SQL repositories to work together
        # It's implemented at a higher service layer
        return {"status": "not_implemented_at_repository_layer"}
