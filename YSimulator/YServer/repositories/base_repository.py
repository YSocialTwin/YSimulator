"""
Abstract base repository interfaces.

This module defines abstract interfaces for data access operations.
Each repository interface focuses on a specific domain entity.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple


class BaseRepository(ABC):
    """Base repository interface with common operations."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the repository backend is healthy."""


class UserRepository(BaseRepository):
    """Repository interface for user-related operations."""

    @abstractmethod
    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """Register a single user."""

    @abstractmethod
    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """Register multiple users in a batch."""

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""

    @abstractmethod
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users."""

    @abstractmethod
    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """Update user's archetype."""

    @abstractmethod
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""

    @abstractmethod
    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """Update agent's last active day."""

    @abstractmethod
    def get_churned_agents(self, day: int = None, inactivity_threshold: int = None) -> List[str]:
        """Get churned agents."""

    @abstractmethod
    def set_agent_churned(self, agent_id: str, churned: bool) -> bool:
        """Set agent churned status."""

    @abstractmethod
    def get_inactive_agents(self, current_day: int, inactivity_threshold: int) -> List[str]:
        """Get inactive agents."""


class PostRepository(BaseRepository):
    """Repository interface for post-related operations."""

    @abstractmethod
    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """Add a new post."""

    @abstractmethod
    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post by ID."""

    @abstractmethod
    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """Get recent post IDs."""

    @abstractmethod
    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """Get thread context for a post."""

    @abstractmethod
    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """Add a reaction/interaction to a post."""

    @abstractmethod
    def increment_post_reaction_count(self, post_id: str) -> bool:
        """Increment the reaction count for a post."""

    @abstractmethod
    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """Associate a topic with a post."""

    @abstractmethod
    def get_post_topics(self, post_id: str) -> List[str]:
        """Get all topics associated with a post."""

    @abstractmethod
    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """Search posts by topic."""

    @abstractmethod
    def get_active_system_messages(self, user_id: str, round_id: str) -> List[Dict[str, Any]]:
        """Get active system messages for a user at the given round."""

    # Metadata methods
    @abstractmethod
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add emotion to a post."""

    @abstractmethod
    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """Get emotion ID by name."""

    @abstractmethod
    def initialize_emotions_table(self):
        """Initialize emotions table with standard emotions."""

    @abstractmethod
    def add_post_sentiment(self, post_id: str, sentiment_score: float) -> bool:
        """Add sentiment score to a post."""

    @abstractmethod
    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """Get sentiment score for a post."""

    @abstractmethod
    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add toxicity score to a post."""

    @abstractmethod
    def add_or_get_hashtag(self, hashtag: str) -> Optional[str]:
        """Add or get hashtag ID."""

    @abstractmethod
    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add hashtag to a post."""

    # Mention methods
    @abstractmethod
    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """Add a mention to a post."""

    @abstractmethod
    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions for a user."""

    @abstractmethod
    def get_mention_by_id(self, mention_id: str) -> Optional[Dict[str, Any]]:
        """Get mention by ID."""

    @abstractmethod
    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark a mention as replied."""


class FollowRepository(BaseRepository):
    """Repository interface for follow/relationship operations."""

    @abstractmethod
    def add_follow(self, follow_data: Dict[str, Any]) -> bool:
        """Add a follow relationship."""

    @abstractmethod
    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """Add multiple follow relationships in a batch."""


class InterestRepository(BaseRepository):
    """Repository interface for interest/topic operations."""

    @abstractmethod
    def get_interest_by_id(self, interest_id: str) -> Optional[Dict[str, Any]]:
        """Get interest by ID."""

    @abstractmethod
    def add_or_get_interest(self, interest_name: str) -> Optional[str]:
        """Add a new interest or get existing one's ID."""

    @abstractmethod
    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""

    @abstractmethod
    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""

    @abstractmethod
    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add a user interest."""

    @abstractmethod
    def add_agent_opinion(
        self, agent_id: str, topic_id: str, opinion: float, round_id: str
    ) -> bool:
        """Add an agent opinion on a topic."""

    @abstractmethod
    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion on a topic."""

    @abstractmethod
    def get_user_interests_in_window(
        self, user_id: str, start_round: int, end_round: int
    ) -> List[str]:
        """Get user interests within a time window."""


class RecommendationRepository(BaseRepository):
    """Repository interface for recommendation and round operations."""

    @abstractmethod
    def get_or_create_round(self, day: int, hour: int) -> str:
        """Get or create a round ID."""

    @abstractmethod
    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """Cleanup old posts (Redis only)."""

    @abstractmethod
    def consolidate_redis_to_sqlite(self, day: int) -> Dict[str, Any]:
        """Consolidate Redis data to SQLite (Redis only)."""


class ArticleRepository(BaseRepository):
    """Repository interface for article/website operations."""

    @abstractmethod
    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """Add a website."""

    @abstractmethod
    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """Add multiple websites in a batch."""

    @abstractmethod
    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """Add an article."""

    @abstractmethod
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get an article by ID."""

    @abstractmethod
    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """Get website by RSS URL."""

    @abstractmethod
    def get_article_topics(self, article_id: str) -> List[str]:
        """Get topics associated with an article."""


class ImageRepository(BaseRepository):
    """Repository interface for image operations."""

    @abstractmethod
    def add_image(self, image_data: Dict[str, Any]) -> Optional[str]:
        """Add an image."""

    @abstractmethod
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """Get a random image."""

    @abstractmethod
    def get_image_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get an image by its URL."""
