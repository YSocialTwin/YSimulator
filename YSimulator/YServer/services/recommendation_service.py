"""
Recommendation service for business logic related to recommendations.

This service encapsulates recommendation-related business operations,
coordinating between repositories to perform complex tasks.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import (
    FollowRepository,
    InterestRepository,
    PostRepository,
    RecommendationRepository,
    UserRepository,
)


class RecommendationService:
    """Service for recommendation-related business logic."""

    def __init__(
        self,
        recommendation_repository: RecommendationRepository,
        follow_repository: Optional[FollowRepository] = None,
        interest_repository: Optional[InterestRepository] = None,
        post_repository: Optional[PostRepository] = None,
        user_repository: Optional[UserRepository] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize recommendation service.

        Args:
            recommendation_repository: Repository for recommendation operations
            follow_repository: Repository for follow relationships (optional)
            interest_repository: Repository for interests/topics (optional)
            post_repository: Repository for posts (optional)
            user_repository: Repository for users (optional)
            logger: Logger instance
        """
        self.rec_repo = recommendation_repository
        self.follow_repo = follow_repository
        self.interest_repo = interest_repository
        self.post_repo = post_repository
        self.user_repo = user_repository
        self.logger = logger or logging.getLogger(__name__)

    def get_or_create_round(self, day: int, hour: int) -> str:
        """
        Get or create a simulation round.

        Args:
            day: Day number
            hour: Hour/slot number

        Returns:
            Round ID

        Raises:
            RuntimeError: If unable to create or retrieve round from repository
        """
        try:
            return self.rec_repo.get_or_create_round(day, hour)
        except Exception as e:
            self.logger.error(f"Error in recommendation service get_or_create_round: {e}")
            raise

    def add_follow_relationship(self, follower_id: str, followee_id: str) -> bool:
        """
        Add a follow relationship between users.

        Args:
            follower_id: ID of the user who follows
            followee_id: ID of the user being followed

        Returns:
            True if successful, False otherwise
        """
        if not self.follow_repo:
            self.logger.warning("Follow repository not configured")
            return False

        try:
            follow_data = {
                "follower_id": follower_id,
                "followee_id": followee_id,
            }
            return self.follow_repo.add_follow(follow_data)
        except Exception as e:
            self.logger.error(f"Error in recommendation service add_follow_relationship: {e}")
            return False

    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """
        Add multiple follow relationships in a batch.

        Args:
            follows_data: List of follow relationship dictionaries

        Returns:
            Number of successfully added relationships
        """
        if not self.follow_repo:
            self.logger.warning("Follow repository not configured")
            return 0

        try:
            return self.follow_repo.add_follows_batch(follows_data)
        except Exception as e:
            self.logger.error(f"Error in recommendation service add_follows_batch: {e}")
            return 0

    def add_agent_opinion(
        self, agent_id: str, topic_id: str, opinion: float, round_id: str
    ) -> bool:
        """
        Record an agent's opinion on a topic.

        Args:
            agent_id: Agent identifier
            topic_id: Topic identifier
            opinion: Opinion value (typically -1.0 to 1.0)
            round_id: Round identifier

        Returns:
            True if successful, False otherwise
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return False

        try:
            return self.interest_repo.add_agent_opinion(agent_id, topic_id, opinion, round_id)
        except Exception as e:
            self.logger.error(f"Error in recommendation service add_agent_opinion: {e}")
            return False

    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """
        Get the latest opinion of an agent on a topic.

        Args:
            agent_id: Agent identifier
            topic_id: Topic identifier

        Returns:
            Opinion value or None if not found
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return None

        try:
            return self.interest_repo.get_latest_agent_opinion(agent_id, topic_id)
        except Exception as e:
            self.logger.error(f"Error in recommendation service get_latest_agent_opinion: {e}")
            return None

    def cleanup_old_data(self, current_day: int, current_slot: int) -> Dict[str, Any]:
        """
        Cleanup old data from storage (primarily for Redis).

        Args:
            current_day: Current simulation day
            current_slot: Current simulation slot/hour

        Returns:
            Dictionary with cleanup results
        """
        try:
            return self.rec_repo.cleanup_old_posts_from_redis(current_day, current_slot)
        except Exception as e:
            self.logger.error(f"Error in recommendation service cleanup_old_data: {e}")
            return {"status": "error", "error": str(e)}

    def consolidate_data(self, day: int) -> Dict[str, Any]:
        """
        Consolidate data from cache to persistent storage.

        Args:
            day: Day to consolidate

        Returns:
            Dictionary with consolidation results
        """
        try:
            return self.rec_repo.consolidate_redis_to_sqlite(day)
        except Exception as e:
            self.logger.error(f"Error in recommendation service consolidate_data: {e}")
            return {"status": "error", "error": str(e)}

    def health_check(self) -> Dict[str, bool]:
        """
        Check health of all repositories.

        Returns:
            Dictionary with health status of each repository
        """
        health_status = {
            "recommendation": False,
            "follow": False,
            "interest": False,
            "post": False,
            "user": False,
        }

        try:
            health_status["recommendation"] = self.rec_repo.health_check()

            if self.follow_repo:
                health_status["follow"] = self.follow_repo.health_check()

            if self.interest_repo:
                health_status["interest"] = self.interest_repo.health_check()

            if self.post_repo:
                health_status["post"] = self.post_repo.health_check()

            if self.user_repo:
                health_status["user"] = self.user_repo.health_check()

        except Exception as e:
            self.logger.error(f"Error in recommendation service health_check: {e}")

        return health_status
