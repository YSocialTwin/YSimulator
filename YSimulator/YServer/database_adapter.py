"""
Database Service Adapter for YSimulator.

This adapter provides a unified interface using the Repository/Service pattern.
All database operations go through this adapter with services handling the logic.
100% migration complete - no legacy middleware dependencies.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from YSimulator.YServer.services.article_service import ArticleService
from YSimulator.YServer.services.content_service import ContentService
from YSimulator.YServer.services.follow_service import FollowService
from YSimulator.YServer.services.image_service import ImageService
from YSimulator.YServer.services.interest_service import InterestService
from YSimulator.YServer.services.memory_service import MemoryService
from YSimulator.YServer.services.mention_service import MentionService
from YSimulator.YServer.services.metadata_service import MetadataService
from YSimulator.YServer.services.post_service import PostService
from YSimulator.YServer.services.simulation_service import SimulationService
from YSimulator.YServer.services.user_service import UserService


class DatabaseServiceAdapter:
    """
    Complete database adapter for YSimulator using Repository/Service pattern.

    This adapter provides all database operations through services.
    100% migration complete - all operations use modern Repository/Service architecture.
    Now includes specialized ArticleService and ImageService.
    """

    def __init__(
        self,
        user_service: UserService,
        post_service: PostService,
        follow_service: FollowService,
        interest_service: InterestService,
        article_service: ArticleService,
        image_service: ImageService,
        content_service: ContentService,
        simulation_service: SimulationService,
        metadata_service: MetadataService,
        mention_service: MentionService,
        memory_service: MemoryService = None,
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
            article_service: Article service (specialized)
            image_service: Image service (specialized)
            content_service: Content service (facade for article/image)
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
        self.article_service = article_service
        self.image_service = image_service
        self.content_service = content_service
        self.simulation_service = simulation_service
        self.metadata_service = metadata_service
        self.mention_service = mention_service
        self.memory_service = memory_service
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

    def get_churned_agents(self) -> List[str]:
        """Get churned agents - matches old middleware signature."""
        return self.user_service.get_churned_agents()

    def set_agent_churned(self, agent_id: str, round_id: str) -> bool:
        """Set agent as churned - matches old middleware signature."""
        return self.user_service.set_agent_churned(agent_id, round_id)

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

    def add_report(self, report_data: Dict[str, Any]) -> bool:
        """Add moderation report."""
        return self.post_service.add_report(report_data)

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

    def get_active_system_messages(self, user_id: str, round_id: str) -> List[Dict[str, Any]]:
        """Get active system messages for a user at a given round."""
        return self.post_service.get_active_system_messages(user_id, round_id)

    # ========================================================================
    # POST METADATA OPERATIONS - MetadataService (COMPLETE)
    # ========================================================================

    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add post emotion."""
        return self.metadata_service.add_post_emotion(post_id, emotion_id)

    def add_post_sentiment(self, sentiment_data: Dict[str, Any]) -> bool:
        """
        Add post sentiment - backwards compatible with old middleware signature.

        Args:
            sentiment_data: Dict with keys: post_id, user_id, topic_id, round,
                          neg, pos, neu, compound, sentiment_parent,
                          is_post, is_comment, is_reaction

        Returns:
            bool: True if successful, False otherwise
        """
        # Repository method will handle the full dict
        return self.metadata_service.post_repo.add_post_sentiment_full(sentiment_data)

    def add_post_toxicity(self, toxicity_data: Dict[str, Any]) -> bool:
        """
        Add post toxicity - backwards compatible with old middleware signature.

        Args:
            toxicity_data: Dict with keys: post_id, toxicity, severe_toxicity,
                          identity_attack, insult, profanity, threat,
                          sexually_explicit, flirtation

        Returns:
            bool: True if successful, False otherwise
        """
        # Repository method will handle the full dict
        return self.metadata_service.post_repo.add_post_toxicity_full(toxicity_data)

    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add post hashtag."""
        return self.metadata_service.add_post_hashtag(post_id, hashtag_id)

    def add_or_get_hashtag(self, hashtag: str) -> str:
        """Add or get hashtag."""
        return self.metadata_service.add_or_get_hashtag(hashtag)

    def get_post_sentiment(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get post sentiment - returns full dict like old middleware.

        Args:
            post_id: Post ID

        Returns:
            Dict with sentiment data or None if not found
        """
        return self.metadata_service.post_repo.get_post_sentiment_full(post_id)

    def get_emotion_by_name(self, emotion_name: str) -> Optional[Dict[str, str]]:
        """
        Get emotion by name - returns dict like old middleware.

        Args:
            emotion_name: Emotion name (e.g., "joy", "anger")

        Returns:
            Dict with emotion data (id, emotion, icon) or None if not found
        """
        return self.metadata_service.post_repo.get_emotion_by_name_full(emotion_name)

    def initialize_emotions_table(self):
        """Initialize emotions table."""
        return self.metadata_service.initialize_emotions_table()

    # ========================================================================
    # FOLLOW OPERATIONS - FollowService (COMPLETE)
    # ========================================================================

    def add_follow(self, follow_data: Dict[str, Any]) -> bool:
        """
        Add follow relationship - backwards compatible with old middleware signature.

        Args:
            follow_data: Dict with keys: user_id (being followed), follower_id, action, round

        Returns:
            bool: True if successful, False otherwise
        """
        # Extract parameters from dict - old middleware signature
        _ = follow_data.get("user_id")  # User being followed
        follow_data.get("follower_id")
        follow_data.get("action", "follow")
        follow_data.get("round")

        # Call repository directly with full data to maintain action field
        return self.follow_service.follow_repo.add_follow_full(follow_data)

    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """
        Add multiple follows - backwards compatible with old middleware signature.

        Args:
            follows_data: List of dicts with keys: user_id, follower_id, action, round

        Returns:
            int: Number of follows added successfully
        """
        return self.follow_service.follow_repo.add_follows_batch(follows_data)

    # ========================================================================
    # INTEREST/TOPIC OPERATIONS - InterestService (COMPLETE)
    # ========================================================================

    def add_or_get_interest(self, interest_name: str) -> str:
        """Add or get interest."""
        return self.interest_service.add_or_get_interest(interest_name)

    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add user interest - matches old middleware signature."""
        return self.interest_service.add_user_interest(user_id, interest_id, round_id)

    def get_interest_by_id(self, interest_ids: List[str]) -> List[str]:
        """Get interests by IDs."""
        return self.interest_service.get_interest_by_id(interest_ids)

    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""
        return self.interest_service.get_topic_id_by_name(topic_name)

    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""
        return self.interest_service.get_topic_name_from_id(topic_id)

    def add_agent_opinion(
        self,
        agent_id: str,
        round_id: str,
        topic_id: str,
        opinion: float,
        id_interacted_with: Optional[str] = None,
        id_post: Optional[str] = None,
    ) -> bool:
        """
        Add agent opinion - matches old middleware signature.

        Args:
            agent_id: Agent UUID
            round_id: Round UUID
            topic_id: Topic UUID
            opinion: Opinion value
            id_interacted_with: Optional UUID of agent interacted with
            id_post: Optional UUID of post

        Returns:
            bool: True if successful
        """
        return self.interest_service.add_agent_opinion(
            agent_id, round_id, topic_id, opinion, id_interacted_with, id_post
        )

    def add_or_get_interests_batch(self, interest_names: List[str]) -> Dict[str, str]:
        """
        Add multiple interests or get existing ones' IDs in batch.

        Args:
            interest_names: List of interest/topic names

        Returns:
            Dict mapping interest names to their IDs
        """
        return self.interest_service.add_or_get_interests_batch(interest_names)

    def add_user_interests_batch(self, user_interests_data: List[Dict[str, str]]) -> int:
        """
        Add multiple user interests in batch.

        Args:
            user_interests_data: List of dicts with user_id, interest_id, round_id

        Returns:
            Number of user interests successfully added
        """
        return self.interest_service.add_user_interests_batch(user_interests_data)

    def add_agent_opinions_batch(self, agent_opinions_data: List[Dict[str, Any]]) -> int:
        """
        Add multiple agent opinions in batch.

        Args:
            agent_opinions_data: List of dicts with agent_id, tid, topic_id, opinion, etc.

        Returns:
            Number of agent opinions successfully added
        """
        return self.interest_service.add_agent_opinions_batch(agent_opinions_data)

    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion."""
        return self.interest_service.get_latest_agent_opinion(agent_id, topic_id)

    def get_user_interests_in_window(
        self, user_id: str, current_round_id: str, attention_window: int
    ) -> List[Dict[str, str]]:
        """
        Get user interests within attention window (old middleware signature).

        Args:
            user_id: User UUID
            current_round_id: Current round UUID
            attention_window: Number of rounds to look back

        Returns:
            List[Dict]: List of user interest records with interest_id and round_id
        """
        # This method needs to query the Round table to convert round_id to day/hour
        # Then calculate the window and query UserInterest
        # For now, delegate to the interest repository directly
        return self.interest_service.interest_repo.get_user_interests_in_window_old(
            user_id, current_round_id, attention_window
        )

    def compute_interest_counts_in_window(
        self, user_id: str, current_round_id: str, attention_window: int
    ) -> Dict[str, int]:
        """
        Compute interest counts for a user within the attention window.

        Args:
            user_id: User UUID
            current_round_id: Current round UUID
            attention_window: Number of rounds to look back

        Returns:
            Dict[str, int]: Map of interest_id to count within the window
        """
        interests_in_window = self.get_user_interests_in_window(
            user_id, current_round_id, attention_window
        )

        # Count occurrences of each interest
        interest_counts = {}
        for entry in interests_in_window:
            interest_id = entry.get("interest_id")
            if interest_id:
                interest_counts[interest_id] = interest_counts.get(interest_id, 0) + 1

        return interest_counts

    # ========================================================================
    # MENTION OPERATIONS - MentionService (COMPLETE)
    # ========================================================================

    def add_mention(self, mention_data: Dict[str, Any]) -> bool:
        """
        Add mention - backwards compatible with old middleware signature.

        Args:
            mention_data: Dict with keys: user_id, post_id, round, answered (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        # Extract parameters from dict for new service signature
        mention_data.get("user_id")
        mention_data.get("post_id")
        mention_data.get("round")

        # Store the round_id and other fields for the actual repository to use
        # The service expects simplified parameters but repository needs full data
        return self.mention_service.post_repo.add_mention_full(mention_data)

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions."""
        return self.mention_service.get_unreplied_mentions(user_id)

    def mark_mention_replied(self, mention_id: str) -> bool:
        """
        Mark mention as replied - backwards compatible with old middleware signature.

        Args:
            mention_id: Mention ID (UUID string)

        Returns:
            bool: True if successful, False otherwise
        """
        # Query the mention to get post_id and mentioned_user_id
        try:
            mention_data = self.mention_service.post_repo.get_mention_by_id(mention_id)
            if not mention_data:
                self.logger.warning(f"Mention {mention_id} not found")
                return False

            post_id = mention_data.get("post_id")
            mentioned_user_id = mention_data.get("mentioned_user_id")

            if not post_id or not mentioned_user_id:
                self.logger.error(f"Invalid mention data for {mention_id}")
                return False

            # Call service with correct signature
            return self.mention_service.mark_mention_replied(post_id, mentioned_user_id)
        except Exception as e:
            self.logger.error(f"Error marking mention {mention_id} as replied: {e}")
            return False

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

    def add_article_topic(self, article_id: str, topic_id: str) -> bool:
        """
        Add article topic association (old middleware signature).

        Args:
            article_id: Article UUID
            topic_id: Topic UUID

        Returns:
            bool: True if successful, False otherwise
        """
        # Delegate to article repository directly
        return self.content_service.article_repo.add_article_topic(article_id, topic_id)

    def add_image(self, image_data: Dict[str, Any]) -> str:
        """Add image."""
        return self.content_service.add_image(image_data)

    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """Get random image."""
        return self.content_service.get_random_image()

    def get_image_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get image by URL."""
        return self.content_service.get_image_by_url(url)

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

    def get_latest_round(self) -> Optional[Dict[str, Any]]:
        """Return the most advanced persisted simulation round."""
        return self.simulation_service.get_latest_round()

    # ========================================================================
    # MEMORY OPERATIONS - MemoryService
    # ========================================================================

    def memory_reset(self, run_id: str) -> Dict[str, Any]:
        """Clear server-owned memory for a run."""
        return self.memory_service.reset(run_id) if self.memory_service else {"status": 503}

    def memory_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Record a memory event."""
        return self.memory_service.record_event(payload) if self.memory_service else {"status": 503}

    def memory_item_upsert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a searchable memory item."""
        return self.memory_service.upsert_item(payload) if self.memory_service else {"status": 503}

    def memory_search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Search server-owned memory."""
        return (
            self.memory_service.search(payload)
            if self.memory_service
            else {"status": 503, "items": []}
        )

    def memory_get_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch memory context."""
        return self.memory_service.get_context(payload) if self.memory_service else {"status": 503}

    def memory_events_recent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch recent memory events."""
        return (
            self.memory_service.events_recent(payload)
            if self.memory_service
            else {"status": 503, "events": []}
        )

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
