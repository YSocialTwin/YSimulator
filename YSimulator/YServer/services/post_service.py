"""
Post service for business logic related to posts and interactions.

This service encapsulates all post-related business operations,
coordinating between repositories to perform complex tasks.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import InterestRepository, PostRepository


class PostService:
    """Service for post-related business logic."""

    def __init__(
        self,
        post_repository: PostRepository,
        interest_repository: Optional[InterestRepository] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize post service.

        Args:
            post_repository: Repository for post data access
            interest_repository: Repository for interest/topic operations (optional)
            logger: Logger instance
        """
        self.post_repo = post_repository
        self.interest_repo = interest_repository
        self.logger = logger or logging.getLogger(__name__)

    def create_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new post.

        Args:
            post_data: Post information dictionary

        Returns:
            Post ID if successful, None otherwise
        """
        try:
            return self.post_repo.add_post(post_data)
        except Exception as e:
            self.logger.error(f"Error in post service create_post: {e}")
            return None

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get post by ID.

        Args:
            post_id: Post identifier

        Returns:
            Post data dictionary or None if not found
        """
        try:
            return self.post_repo.get_post(post_id)
        except Exception as e:
            self.logger.error(f"Error in post service get_post: {e}")
            return None

    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """
        Get recent post IDs.

        Args:
            limit: Maximum number of posts to return

        Returns:
            List of post IDs
        """
        try:
            return self.post_repo.get_recent_posts(limit)
        except Exception as e:
            self.logger.error(f"Error in post service get_recent_posts: {e}")
            return []

    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """
        Get the conversation thread context for a post.

        Args:
            post_id: Post identifier
            max_length: Maximum number of posts in thread

        Returns:
            List of post dictionaries in thread order
        """
        try:
            return self.post_repo.get_thread_context(post_id, max_length)
        except Exception as e:
            self.logger.error(f"Error in post service get_thread_context: {e}")
            return []

    def add_reaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Add a reaction to a post.

        Args:
            interaction_data: Reaction information dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Add the interaction
            success = self.post_repo.add_interaction(interaction_data)

            # If successful, increment the post's reaction count
            if success and "post_id" in interaction_data:
                self.post_repo.increment_post_reaction_count(interaction_data["post_id"])

            return success
        except Exception as e:
            self.logger.error(f"Error in post service add_reaction: {e}")
            return False

    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Add an interaction - alias for add_reaction for backwards compatibility.

        Args:
            interaction_data: Interaction information dictionary

        Returns:
            True if successful, False otherwise
        """
        return self.add_reaction(interaction_data)

    def increment_post_reaction_count(self, post_id: str) -> bool:
        """
        Increment the reaction count for a post.

        Args:
            post_id: Post identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.increment_post_reaction_count(post_id)
        except Exception as e:
            self.logger.error(f"Error incrementing post reaction count: {e}")
            return False

    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """
        Associate a topic with a post.

        Args:
            post_id: Post identifier
            topic_id: Topic identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_post_topic(post_id, topic_id)
        except Exception as e:
            self.logger.error(f"Error in post service add_post_topic: {e}")
            return False

    def get_post_topics(self, post_id: str) -> List[str]:
        """
        Get all topics associated with a post.

        Args:
            post_id: Post identifier

        Returns:
            List of topic IDs
        """
        try:
            return self.post_repo.get_post_topics(post_id)
        except Exception as e:
            self.logger.error(f"Error in post service get_post_topics: {e}")
            return []

    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """
        Search for posts by topic, excluding posts by the given agent.

        Args:
            topic_id: Topic identifier
            agent_id: Agent identifier to exclude
            limit: Maximum number of posts to return

        Returns:
            List of post IDs
        """
        try:
            return self.post_repo.search_posts_by_topic(topic_id, agent_id, limit)
        except Exception as e:
            self.logger.error(f"Error in post service search_posts_by_topic: {e}")
            return []

    def get_topic_by_name(self, topic_name: str) -> Optional[str]:
        """
        Get topic ID by name.

        Args:
            topic_name: Topic name

        Returns:
            Topic ID or None if not found
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return None

        try:
            return self.interest_repo.get_topic_id_by_name(topic_name)
        except Exception as e:
            self.logger.error(f"Error in post service get_topic_by_name: {e}")
            return None

    def add_or_get_topic(self, topic_name: str) -> Optional[str]:
        """
        Add a new topic or get existing topic ID.

        Args:
            topic_name: Topic name

        Returns:
            Topic ID or None if error
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return None

        try:
            return self.interest_repo.add_or_get_interest(topic_name)
        except Exception as e:
            self.logger.error(f"Error in post service add_or_get_topic: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if the service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.post_repo.health_check()
        except Exception as e:
            self.logger.error(f"Error in post service health_check: {e}")
            return False
