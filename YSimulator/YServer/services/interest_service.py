"""
Interest service for business logic related to topics and interests.

This service encapsulates all interest/topic-related business operations.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import InterestRepository


class InterestService:
    """Service for interest/topic business logic."""

    def __init__(
        self,
        interest_repository: InterestRepository,
        logger: logging.Logger = None,
    ):
        """
        Initialize interest service.

        Args:
            interest_repository: Repository for interest data access
            logger: Logger instance
        """
        self.interest_repo = interest_repository
        self.logger = logger or logging.getLogger(__name__)

    def add_or_get_interest(self, interest_name: str) -> Optional[str]:
        """
        Add a new interest or get existing one's ID.

        Args:
            interest_name: Name of the interest/topic

        Returns:
            Interest ID or None if error
        """
        try:
            return self.interest_repo.add_or_get_interest(interest_name)
        except Exception as e:
            self.logger.error(f"Error adding/getting interest: {e}")
            return None

    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """
        Add a user interest.

        Args:
            user_id: User ID
            interest_id: Interest ID
            round_id: Round ID (UUID string)

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.interest_repo.add_user_interest(user_id, interest_id, round_id)
        except Exception as e:
            self.logger.error(f"Error adding user interest: {e}")
            return False

    def get_interest_by_id(self, interest_ids: List[str]) -> List[str]:
        """
        Get interest names by IDs.

        Args:
            interest_ids: List of interest IDs

        Returns:
            List of interest names
        """
        try:
            return [self.interest_repo.get_topic_name_from_id(iid) or "" for iid in interest_ids]
        except Exception as e:
            self.logger.error(f"Error getting interests by ID: {e}")
            return []

    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """
        Get topic ID by name.

        Args:
            topic_name: Topic name

        Returns:
            Topic ID or None
        """
        try:
            return self.interest_repo.get_topic_id_by_name(topic_name)
        except Exception as e:
            self.logger.error(f"Error getting topic ID: {e}")
            return None

    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """
        Get topic name from ID.

        Args:
            topic_id: Topic ID

        Returns:
            Topic name or None
        """
        try:
            return self.interest_repo.get_topic_name_from_id(topic_id)
        except Exception as e:
            self.logger.error(f"Error getting topic name: {e}")
            return None

    def list_interests(self) -> List[Dict[str, Any]]:
        """
        Return all known interests/topics.

        Returns:
            List of dicts with ``iid`` and ``interest``
        """
        try:
            return self.interest_repo.list_interests()
        except Exception as e:
            self.logger.error(f"Error listing interests: {e}")
            return []

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
        Add an agent opinion on a topic.

        Args:
            agent_id: Agent ID
            round_id: Round ID
            topic_id: Topic ID
            opinion: Opinion value
            id_interacted_with: Optional UUID of agent interacted with
            id_post: Optional UUID of post

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.interest_repo.add_agent_opinion(
                agent_id, round_id, topic_id, opinion, id_interacted_with, id_post
            )
        except Exception as e:
            self.logger.error(f"Error adding agent opinion: {e}")
            return False

    def add_or_get_interests_batch(self, interest_names: List[str]) -> dict:
        """
        Add multiple interests or get existing ones' IDs in batch.

        Args:
            interest_names: List of interest/topic names

        Returns:
            Dict mapping interest names to their IDs
        """
        try:
            return self.interest_repo.add_or_get_interests_batch(interest_names)
        except Exception as e:
            self.logger.error(f"Error batch adding/getting interests: {e}")
            return {}

    def add_user_interests_batch(self, user_interests_data: List[dict]) -> int:
        """
        Add multiple user interests in batch.

        Args:
            user_interests_data: List of dicts with user_id, interest_id, round_id

        Returns:
            Number of user interests successfully added
        """
        try:
            return self.interest_repo.add_user_interests_batch(user_interests_data)
        except Exception as e:
            self.logger.error(f"Error batch adding user interests: {e}")
            return 0

    def add_agent_opinions_batch(self, agent_opinions_data: List[dict]) -> int:
        """
        Add multiple agent opinions in batch.

        Args:
            agent_opinions_data: List of dicts with agent_id, tid, topic_id, opinion, etc.

        Returns:
            Number of agent opinions successfully added
        """
        try:
            return self.interest_repo.add_agent_opinions_batch(agent_opinions_data)
        except Exception as e:
            self.logger.error(f"Error batch adding agent opinions: {e}")
            return 0

    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """
        Get latest agent opinion on a topic.

        Args:
            agent_id: Agent ID
            topic_id: Topic ID

        Returns:
            Opinion value or None
        """
        try:
            return self.interest_repo.get_latest_agent_opinion(agent_id, topic_id)
        except Exception as e:
            self.logger.error(f"Error getting agent opinion: {e}")
            return None
