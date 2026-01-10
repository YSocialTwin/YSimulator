"""
Mention service for mention and reply tracking operations.

This service encapsulates all mention-related business operations.
"""

import logging
from typing import Any, Dict, List

from YSimulator.YServer.repositories.base_repository import PostRepository


class MentionService:
    """Service for mention and reply business logic."""

    def __init__(
        self,
        post_repository: PostRepository,
        logger: logging.Logger = None,
    ):
        """
        Initialize mention service.

        Args:
            post_repository: Repository for mention operations
            logger: Logger instance
        """
        self.post_repo = post_repository
        self.logger = logger or logging.getLogger(__name__)

    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """
        Add a mention to a post.

        Args:
            post_id: Post ID
            mentioned_user_id: ID of mentioned user

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_mention(post_id, mentioned_user_id)
        except Exception as e:
            self.logger.error(f"Error adding mention: {e}")
            return False

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get unreplied mentions for a user.

        Args:
            user_id: User ID

        Returns:
            List of unreplied mention dicts
        """
        try:
            return self.post_repo.get_unreplied_mentions(user_id)
        except Exception as e:
            self.logger.error(f"Error getting unreplied mentions: {e}")
            return []

    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """
        Mark a mention as replied.

        Args:
            post_id: Post ID
            mentioned_user_id: ID of mentioned user

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.mark_mention_replied(post_id, mentioned_user_id)
        except Exception as e:
            self.logger.error(f"Error marking mention as replied: {e}")
            return False
