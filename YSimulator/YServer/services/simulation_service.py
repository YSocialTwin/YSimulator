"""
Simulation service for simulation state and round management.

This service encapsulates simulation-related operations.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import RecommendationRepository


class SimulationService:
    """Service for simulation state management."""

    def __init__(
        self,
        recommendation_repository: RecommendationRepository,
        logger: logging.Logger = None,
    ):
        """
        Initialize simulation service.

        Args:
            recommendation_repository: Repository for round/simulation operations
            logger: Logger instance
        """
        self.recommendation_repo = recommendation_repository
        self.logger = logger or logging.getLogger(__name__)

    def get_or_create_round(self, day: int, slot: int) -> str:
        """
        Get or create a simulation round.

        Args:
            day: Simulation day
            slot: Time slot

        Returns:
            Round ID
        """
        try:
            return self.recommendation_repo.get_or_create_round(day, slot)
        except Exception as e:
            self.logger.error(f"Error getting/creating round: {e}")
            raise

    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """
        Cleanup old posts from Redis (Redis-only operation).

        Args:
            current_day: Current simulation day
            current_slot: Current time slot

        Returns:
            Dict with cleanup statistics
        """
        try:
            return self.recommendation_repo.cleanup_old_posts_from_redis(current_day, current_slot)
        except Exception as e:
            self.logger.error(f"Error cleaning up old posts: {e}")
            return {}

    def consolidate_redis_to_sqlite(self, day: int) -> Dict[str, Any]:
        """
        Consolidate Redis data to SQLite (Redis-only operation).

        Args:
            day: Day to consolidate

        Returns:
            Dict with consolidation statistics
        """
        try:
            return self.recommendation_repo.consolidate_redis_to_sqlite(day)
        except Exception as e:
            self.logger.error(f"Error consolidating Redis data: {e}")
            return {}
