"""
Redis-based repository implementations.

This module provides concrete implementations of repository interfaces
using Redis for high-performance caching operations.
"""

import logging
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
        self,
        redis_client,
        key_prefix: str = "ysim",
        logger: Optional[logging.Logger] = None
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
                k.decode() if isinstance(k, bytes) else k: 
                v.decode() if isinstance(v, bytes) else v
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


class RedisPostRepository(PostRepository):
    """Redis implementation of PostRepository."""
    
    def __init__(
        self,
        redis_client,
        key_prefix: str = "ysim",
        logger: Optional[logging.Logger] = None
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
            # Add to post IDs set
            self.redis_client.sadd(self._redis_key("posts", "ids"), post_id)
            
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
            return {
                k.decode() if isinstance(k, bytes) else k: 
                v.decode() if isinstance(v, bytes) else v
                for k, v in post_data.items()
            }
        except Exception as e:
            self.logger.error(
                f"Error getting post from Redis: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """Get recent post IDs."""
        try:
            # Redis stores posts in sets, so we need a different approach
            # This is a simplified version - in production, use sorted sets with timestamps
            post_ids = self.redis_client.smembers(self._redis_key("posts", "ids"))
            post_ids = [
                pid.decode() if isinstance(pid, bytes) else pid
                for pid in post_ids
            ]
            return post_ids[:limit]
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
            reaction_id = interaction_data.get("id")
            key = self._redis_key("reactions", reaction_id)
            
            # Filter out None values
            redis_data = {k: str(v) if v is not None else "" for k, v in interaction_data.items()}
            
            # Store reaction data
            self.redis_client.hset(key, mapping=redis_data)
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
            
            # Increment num_reactions field
            self.redis_client.hincrby(key, "num_reactions", 1)
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
            return [
                topic.decode() if isinstance(topic, bytes) else topic
                for topic in topics
            ]
        except Exception as e:
            self.logger.error(
                f"Error getting post topics from Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []
    
    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """Search posts by topic."""
        try:
            # This is a simplified implementation
            # In production, use Redis search or maintain topic->posts index
            all_post_ids = self.redis_client.smembers(self._redis_key("posts", "ids"))
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


class RedisFollowRepository(FollowRepository):
    """Redis implementation of FollowRepository."""
    
    def __init__(
        self,
        redis_client,
        key_prefix: str = "ysim",
        logger: Optional[logging.Logger] = None
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
            follower_id = follow_data["follower_id"]
            followee_id = follow_data["followee_id"]
            
            # Store follower -> followees
            self.redis_client.sadd(
                self._redis_key("follows:following", follower_id),
                followee_id
            )
            
            # Store followee -> followers
            self.redis_client.sadd(
                self._redis_key("follows:followers", followee_id),
                follower_id
            )
            
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
            count = 0
            for follow_data in follows_data:
                if self.add_follow(follow_data):
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
        self,
        redis_client,
        key_prefix: str = "ysim",
        logger: Optional[logging.Logger] = None
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
                k.decode() if isinstance(k, bytes) else k: 
                v.decode() if isinstance(v, bytes) else v
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
            import uuid
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
    
    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add a user interest."""
        try:
            # Store as a sorted set with round_id as score for time-based queries
            key = self._redis_key("user_interests", user_id)
            self.redis_client.zadd(key, {interest_id: float(round_id)})
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
            self.redis_client.hset(
                key,
                mapping={"opinion": str(opinion), "round_id": round_id}
            )
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
            interests = self.redis_client.zrangebyscore(
                key,
                float(start_round),
                float(end_round)
            )
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
        self,
        redis_client,
        key_prefix: str = "ysim",
        logger: Optional[logging.Logger] = None
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
        """Get or create a round ID."""
        try:
            # Check if round exists
            key = self._redis_key("rounds", f"{day}:{hour}")
            round_id = self.redis_client.get(key)
            
            if round_id:
                return round_id.decode() if isinstance(round_id, bytes) else round_id
            
            # Create new round
            import uuid
            round_id = str(uuid.uuid4())
            self.redis_client.set(key, round_id)
            
            # Store round details
            round_key = self._redis_key("round_data", round_id)
            self.redis_client.hset(round_key, mapping={"id": round_id, "day": str(day), "hour": str(hour)})
            
            return round_id
        except Exception as e:
            self.logger.error(
                f"Error getting or creating round in Redis: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None
    
    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """Cleanup old posts from Redis."""
        try:
            # This is a placeholder - actual implementation would depend on
            # how posts are indexed by day/slot in Redis
            deleted_count = 0
            
            # Get all post IDs
            post_ids = self.redis_client.smembers(self._redis_key("posts", "ids"))
            
            for post_id in post_ids:
                if isinstance(post_id, bytes):
                    post_id = post_id.decode()
                
                # Get post data to check round
                post_key = self._redis_key("posts", post_id)
                post_data = self.redis_client.hgetall(post_key)
                
                # Implement cleanup logic based on your requirements
                # This is a simplified version
                if post_data:
                    # Delete old posts (example logic)
                    self.redis_client.delete(post_key)
                    self.redis_client.srem(self._redis_key("posts", "ids"), post_id)
                    deleted_count += 1
            
            return {"deleted": deleted_count, "status": "success"}
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
