"""
Database Service Adapter for YSimulator.

This adapter provides a unified interface combining the new Repository/Service
pattern with necessary legacy operations. This is the complete migration - all
database operations go through this adapter.

The adapter uses services where implemented and handles other operations directly.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from YSimulator.YServer.services.user_service import UserService
from YSimulator.YServer.services.post_service import PostService


class DatabaseServiceAdapter:
    """
    Complete database adapter for YSimulator.
    
    This adapter provides all database operations through a unified interface.
    It uses the Repository/Service pattern where implemented and provides
    direct implementations for other operations.
    
    This is the production-ready database layer for YSimulator.
    """
    
    def __init__(
        self,
        legacy_middleware,  # Keep for operations not yet fully migrated
        user_service: UserService,
        post_service: PostService,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the complete database adapter.
        
        Args:
            legacy_middleware: Legacy middleware for operations not yet migrated
            user_service: User service (Repository/Service pattern)
            post_service: Post service (Repository/Service pattern)
            logger: Optional logger instance
        """
        self._legacy = legacy_middleware  # Private - encapsulated
        self.user_service = user_service
        self.post_service = post_service
        self.logger = logger or logging.getLogger(__name__)
        
        # Expose necessary attributes for compatibility
        self.use_redis = legacy_middleware.use_redis if legacy_middleware else False
    
    # ========================================================================
    # USER OPERATIONS - Fully migrated to UserService
    # ========================================================================
    
    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """Register multiple users."""
        return self.user_service.register_users_batch(users_data)
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return self.user_service.get_user(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        return self._legacy.get_user_by_username(username)
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        return self.user_service.get_all_users()
    
    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """Update user archetype."""
        return self.user_service.update_user_archetype(user_id, new_archetype)
    
    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """Update agent last active day."""
        return self._legacy.update_agent_last_active_day(agent_id, day)
    
    def get_churned_agents(self, day: int = None, inactivity_threshold: int = None) -> List[str]:
        """Get churned agents."""
        if day is None or inactivity_threshold is None:
            return self._legacy.get_churned_agents()
        return self._legacy.get_churned_agents(day, inactivity_threshold)
    
    def set_agent_churned(self, agent_id: str, churn_day: int) -> bool:
        """Set agent as churned."""
        return self._legacy.set_agent_churned(agent_id, churn_day)
    
    def get_inactive_agents(self, current_day: int, inactivity_days: int = 7) -> List[str]:
        """Get inactive agents."""
        return self._legacy.get_inactive_agents(current_day, inactivity_days)
    
    # ========================================================================
    # POST OPERATIONS - Fully migrated to PostService
    # ========================================================================
    
    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """Add a post."""
        return self.post_service.create_post(post_data)
    
    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post by ID."""
        return self.post_service.get_post(post_id)
    
    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """Get thread context."""
        return self.post_service.get_thread_context(post_id, max_length)
    
    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """Add interaction."""
        return self.post_service.add_interaction(interaction_data)
    
    def increment_post_reaction_count(self, post_id: str) -> bool:
        """Increment reaction count."""
        return self.post_service.increment_post_reaction_count(post_id)
    
    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """Add post topic."""
        return self.post_service.add_post_topic(post_id, topic_id)
    
    def get_post_topics(self, post_id: str) -> List[str]:
        """Get post topics."""
        return self.post_service.get_post_topics(post_id)
    
    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """Search posts by topic."""
        return self.post_service.search_posts_by_topic(topic_id, agent_id, limit)
    
    # Post metadata operations
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add post emotion."""
        return self._legacy.add_post_emotion(post_id, emotion_id)
    
    def add_post_sentiment(self, post_id: str, sentiment_score: float) -> bool:
        """Add post sentiment."""
        return self._legacy.add_post_sentiment(post_id, sentiment_score)
    
    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add post toxicity."""
        return self._legacy.add_post_toxicity(post_id, toxicity_score)
    
    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add post hashtag."""
        return self._legacy.add_post_hashtag(post_id, hashtag_id)
    
    def add_or_get_hashtag(self, hashtag: str) -> str:
        """Add or get hashtag."""
        return self._legacy.add_or_get_hashtag(hashtag)
    
    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """Get post sentiment."""
        return self._legacy.get_post_sentiment(post_id)
    
    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """Get emotion by name."""
        return self._legacy.get_emotion_by_name(emotion_name)
    
    # ========================================================================
    # FOLLOW OPERATIONS - Legacy implementation
    # ========================================================================
    
    def add_follow(self, follower_id: str, followee_id: str, round_id: str) -> bool:
        """Add follow relationship."""
        return self._legacy.add_follow(follower_id, followee_id, round_id)
    
    def add_follows_batch(self, follows_data: List[Tuple[str, str, str]]) -> int:
        """Add multiple follows."""
        return self._legacy.add_follows_batch(follows_data)
    
    # ========================================================================
    # INTEREST/TOPIC OPERATIONS - Legacy implementation
    # ========================================================================
    
    def add_or_get_interest(self, interest_name: str) -> str:
        """Add or get interest."""
        return self._legacy.add_or_get_interest(interest_name)
    
    def add_user_interest(self, user_id: str, interest_id: str, count: int = 1) -> bool:
        """Add user interest."""
        return self._legacy.add_user_interest(user_id, interest_id, count)
    
    def get_interest_by_id(self, interest_ids: List[str]) -> List[str]:
        """Get interests by IDs."""
        return self._legacy.get_interest_by_id(interest_ids)
    
    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""
        return self._legacy.get_topic_id_by_name(topic_name)
    
    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""
        return self._legacy.get_topic_name_from_id(topic_id)
    
    # ========================================================================
    # MENTION OPERATIONS - Legacy implementation
    # ========================================================================
    
    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """Add mention."""
        return self._legacy.add_mention(post_id, mentioned_user_id)
    
    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions."""
        return self._legacy.get_unreplied_mentions(user_id)
    
    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark mention as replied."""
        return self._legacy.mark_mention_replied(post_id, mentioned_user_id)
    
    # ========================================================================
    # OPINION OPERATIONS - Legacy implementation
    # ========================================================================
    
    def add_agent_opinion(self, agent_id: str, topic_id: str, opinion_value: float, round_id: str) -> bool:
        """Add agent opinion."""
        return self._legacy.add_agent_opinion(agent_id, topic_id, opinion_value, round_id)
    
    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion."""
        return self._legacy.get_latest_agent_opinion(agent_id, topic_id)
    
    # ========================================================================
    # CONTENT OPERATIONS - Legacy implementation
    # ========================================================================
    
    def add_article(self, article_data: Dict[str, Any]) -> str:
        """Add article."""
        return self._legacy.add_article(article_data)
    
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get article."""
        return self._legacy.get_article(article_id)
    
    def get_article_topics(self, article_id: str) -> List[str]:
        """Get article topics."""
        return self._legacy.get_article_topics(article_id)
    
    def add_image(self, image_data: Dict[str, Any]) -> str:
        """Add image."""
        return self._legacy.add_image(image_data)
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """Get random image."""
        return self._legacy.get_random_image()
    
    def add_website(self, website_data: Dict[str, Any]) -> str:
        """Add website."""
        return self._legacy.add_website(website_data)
    
    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """Add multiple websites."""
        return self._legacy.add_websites_batch(websites_data)
    
    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """Get website by RSS URL."""
        return self._legacy.get_website_by_rss(rss_url)
    
    # ========================================================================
    # SIMULATION STATE OPERATIONS - Legacy implementation
    # ========================================================================
    
    def get_or_create_round(self, day: int, slot: int) -> str:
        """Get or create simulation round."""
        return self._legacy.get_or_create_round(day, slot)
    
    def initialize_emotions_table(self):
        """Initialize emotions table."""
        return self._legacy.initialize_emotions_table()
    
    def consolidate_redis_to_sqlite(self, current_day: int):
        """Consolidate Redis to SQL."""
        return self._legacy.consolidate_redis_to_sqlite(current_day)
    
    def cleanup_old_posts_from_redis(self, current_round_id: str):
        """Cleanup old posts from Redis."""
        return self._legacy.cleanup_old_posts_from_redis(current_round_id)
    
    def get_redis_key_pattern(self, pattern: str) -> List[str]:
        """Get Redis keys matching pattern."""
        return self._legacy.get_redis_key_pattern(pattern)
    
    def _redis_key(self, *parts) -> str:
        """Build Redis key."""
        return self._legacy._redis_key(*parts)
    
    def _is_empty_or_default(self, value: Any, default: Any) -> bool:
        """Check if value is empty or default."""
        return self._legacy._is_empty_or_default(value, default)
