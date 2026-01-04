"""
Database Service Adapter for YSimulator.

This adapter provides a unified interface using the Repository/Service pattern.
All database operations go through this adapter with services handling the logic.
100% migration complete - no legacy middleware dependencies.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from YSimulator.YServer.services.user_service import UserService
from YSimulator.YServer.services.post_service import PostService
from YSimulator.YServer.services.follow_service import FollowService
from YSimulator.YServer.services.interest_service import InterestService
from YSimulator.YServer.services.content_service import ContentService
from YSimulator.YServer.services.simulation_service import SimulationService
from YSimulator.YServer.services.metadata_service import MetadataService
from YSimulator.YServer.services.mention_service import MentionService


class DatabaseServiceAdapter:
    """
    Complete database adapter for YSimulator using Repository/Service pattern.
    
    This adapter provides all database operations through services.
    100% migration complete - all operations use modern Repository/Service architecture.
    """
    
    def __init__(
        self,
        user_service: UserService,
        post_service: PostService,
        follow_service: FollowService,
        interest_service: InterestService,
        content_service: ContentService,
        simulation_service: SimulationService,
        metadata_service: MetadataService,
        mention_service: MentionService,
        redis_client=None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the complete database adapter.
        
        Args:
            user_service: User service
            post_service: Post service
            follow_service: Follow service
            interest_service: Interest service
            content_service: Content service
            simulation_service: Simulation service
            metadata_service: Metadata service
            mention_service: Mention service
            redis_client: Optional Redis client for caching
            logger: Optional logger instance
        """
        self.user_service = user_service
        self.post_service = post_service
        self.follow_service = follow_service
        self.interest_service = interest_service
        self.content_service = content_service
        self.simulation_service = simulation_service
        self.metadata_service = metadata_service
        self.mention_service = mention_service
        self.redis_client = redis_client
        self.logger = logger or logging.getLogger(__name__)
        
        # Expose necessary attributes for compatibility
        self.use_redis = redis_client is not None
    
    @property
    def engine(self):
        """
        Provide access to the database engine for compatibility with server code.
        Returns the engine from the user service's repository.
        """
        return self.user_service.user_repo.engine
    
    # ========================================================================
    # USER OPERATIONS - UserService (COMPLETE)
    # ========================================================================
    
    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """Register multiple users."""
        return self.user_service.register_users_batch(users_data)
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return self.user_service.get_user(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        return self.user_service.get_user_by_username(username)
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        return self.user_service.get_all_users()
    
    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """Update user archetype."""
        return self.user_service.update_user_archetype(user_id, new_archetype)
    
    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """Update agent last active day."""
        return self.user_service.update_agent_last_active_day(agent_id, day)
    
    def get_churned_agents(self, day: int = None, inactivity_threshold: int = None) -> List[str]:
        """Get churned agents."""
        return self.user_service.get_churned_agents(day, inactivity_threshold)
    
    def set_agent_churned(self, agent_id: str, churn_day: int) -> bool:
        """Set agent as churned."""
        return self.user_service.set_agent_churned(agent_id, churn_day)
    
    def get_inactive_agents(self, current_day: int, inactivity_days: int = 7) -> List[str]:
        """Get inactive agents."""
        return self.user_service.get_inactive_agents(current_day, inactivity_days)
    
    # ========================================================================
    # POST OPERATIONS - PostService (COMPLETE)
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
    
    # ========================================================================
    # POST METADATA OPERATIONS - MetadataService (COMPLETE)
    # ========================================================================
    
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add post emotion."""
        return self.metadata_service.add_post_emotion(post_id, emotion_id)
    
    def add_post_sentiment(self, post_id: str, sentiment_score: float) -> bool:
        """Add post sentiment."""
        return self.metadata_service.add_post_sentiment(post_id, sentiment_score)
    
    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add post toxicity."""
        return self.metadata_service.add_post_toxicity(post_id, toxicity_score)
    
    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add post hashtag."""
        return self.metadata_service.add_post_hashtag(post_id, hashtag_id)
    
    def add_or_get_hashtag(self, hashtag: str) -> str:
        """Add or get hashtag."""
        return self.metadata_service.add_or_get_hashtag(hashtag)
    
    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """Get post sentiment."""
        return self.metadata_service.get_post_sentiment(post_id)
    
    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """Get emotion by name."""
        return self.metadata_service.get_emotion_by_name(emotion_name)
    
    def initialize_emotions_table(self):
        """Initialize emotions table."""
        return self.metadata_service.initialize_emotions_table()
    
    # ========================================================================
    # FOLLOW OPERATIONS - FollowService (COMPLETE)
    # ========================================================================
    
    def add_follow(self, follower_id: str, followee_id: str, round_id: str) -> bool:
        """Add follow relationship."""
        return self.follow_service.add_follow(follower_id, followee_id, round_id)
    
    def add_follows_batch(self, follows_data: List[Tuple[str, str, str]]) -> int:
        """Add multiple follows."""
        return self.follow_service.add_follows_batch(follows_data)
    
    # ========================================================================
    # INTEREST/TOPIC OPERATIONS - InterestService (COMPLETE)
    # ========================================================================
    
    def add_or_get_interest(self, interest_name: str) -> str:
        """Add or get interest."""
        return self.interest_service.add_or_get_interest(interest_name)
    
    def add_user_interest(self, user_id: str, interest_id: str, count: int = 1) -> bool:
        """Add user interest."""
        return self.interest_service.add_user_interest(user_id, interest_id, count)
    
    def get_interest_by_id(self, interest_ids: List[str]) -> List[str]:
        """Get interests by IDs."""
        return self.interest_service.get_interest_by_id(interest_ids)
    
    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""
        return self.interest_service.get_topic_id_by_name(topic_name)
    
    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""
        return self.interest_service.get_topic_name_from_id(topic_id)
    
    def add_agent_opinion(self, agent_id: str, topic_id: str, opinion_value: float, round_id: str) -> bool:
        """Add agent opinion."""
        return self.interest_service.add_agent_opinion(agent_id, topic_id, opinion_value, round_id)
    
    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion."""
        return self.interest_service.get_latest_agent_opinion(agent_id, topic_id)
    
    # ========================================================================
    # MENTION OPERATIONS - MentionService (COMPLETE)
    # ========================================================================
    
    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """Add mention."""
        return self.mention_service.add_mention(post_id, mentioned_user_id)
    
    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions."""
        return self.mention_service.get_unreplied_mentions(user_id)
    
    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark mention as replied."""
        return self.mention_service.mark_mention_replied(post_id, mentioned_user_id)
    
    # ========================================================================
    # CONTENT OPERATIONS - ContentService (COMPLETE)
    # ========================================================================
    
    def add_article(self, article_data: Dict[str, Any]) -> str:
        """Add article."""
        return self.content_service.add_article(article_data)
    
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get article."""
        return self.content_service.get_article(article_id)
    
    def get_article_topics(self, article_id: str) -> List[str]:
        """Get article topics."""
        return self.content_service.get_article_topics(article_id)
    
    def add_image(self, image_data: Dict[str, Any]) -> str:
        """Add image."""
        return self.content_service.add_image(image_data)
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """Get random image."""
        return self.content_service.get_random_image()
    
    def add_website(self, website_data: Dict[str, Any]) -> str:
        """Add website."""
        return self.content_service.add_website(website_data)
    
    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """Add multiple websites."""
        return self.content_service.add_websites_batch(websites_data)
    
    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """Get website by RSS URL."""
        return self.content_service.get_website_by_rss(rss_url)
    
    # ========================================================================
    # SIMULATION STATE OPERATIONS - SimulationService (COMPLETE)
    # ========================================================================
    
    def get_or_create_round(self, day: int, slot: int) -> str:
        """Get or create simulation round."""
        return self.simulation_service.get_or_create_round(day, slot)
    
    def consolidate_redis_to_sqlite(self, current_day: int):
        """Consolidate Redis to SQL."""
        return self.simulation_service.consolidate_redis_to_sqlite(current_day)
    
    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """
        Cleanup old posts from Redis.
        
        Args:
            current_day: Current simulation day
            current_slot: Current time slot
            
        Returns:
            Dict with cleanup statistics
        """
        return self.simulation_service.cleanup_old_posts_from_redis(current_day, current_slot)
    
    # ========================================================================
    # UTILITY METHODS - Complete migration (no legacy dependencies)
    # ========================================================================
    
    def get_redis_key_pattern(self, table: str, pattern: str = "*") -> str:
        """
        Generate a Redis key pattern for scanning.
        
        Args:
            table: Table name (e.g., "follow", "post")
            pattern: Pattern to match (default: "*")
            
        Returns:
            str: Redis key pattern (e.g., "ysim:follow:*")
        """
        return f"ysim:{table}:{pattern}"
    
    def _redis_key(self, table: str, id: Any = None) -> str:
        """
        Generate Redis key for a table and optional ID.
        
        Args:
            table: Table name
            id: Optional ID
            
        Returns:
            str: Redis key (e.g., "ysim:table:id")
        """
        if id is not None:
            return f"ysim:{table}:{id}"
        return f"ysim:{table}"
    
    @staticmethod
    def _is_empty_or_default(value: Any) -> bool:
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
