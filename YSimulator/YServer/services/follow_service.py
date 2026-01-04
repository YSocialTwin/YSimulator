"""
Follow service for business logic related to social relationships.

This service encapsulates all follow-related business operations.
"""

import logging
from typing import Any, Dict, List, Tuple

from YSimulator.YServer.repositories.base_repository import FollowRepository


class FollowService:
    """Service for follow relationship business logic."""
    
    def __init__(
        self,
        follow_repository: FollowRepository,
        logger: logging.Logger = None,
    ):
        """
        Initialize follow service.
        
        Args:
            follow_repository: Repository for follow data access
            logger: Logger instance
        """
        self.follow_repo = follow_repository
        self.logger = logger or logging.getLogger(__name__)
    
    def add_follow(self, follower_id: str, followee_id: str, round_id: str) -> bool:
        """
        Add a follow relationship.
        
        Args:
            follower_id: ID of the user following
            followee_id: ID of the user being followed
            round_id: Round ID when follow occurred
            
        Returns:
            True if successful, False otherwise
        """
        try:
            follow_data = {
                "follower_id": follower_id,
                "followee_id": followee_id,
                "round_id": round_id,
            }
            return self.follow_repo.add_follow(follow_data)
        except Exception as e:
            self.logger.error(f"Error adding follow: {e}")
            return False
    
    def add_follows_batch(self, follows_data: List[Tuple[str, str, str]]) -> int:
        """
        Add multiple follow relationships in a batch.
        
        Args:
            follows_data: List of (follower_id, followee_id, round_id) tuples
            
        Returns:
            Number of follows added
        """
        try:
            # Convert tuples or lists to dicts
            follow_dicts = []
            for item in follows_data:
                if isinstance(item, dict):
                    # Already a dict
                    follow_dicts.append(item)
                elif isinstance(item, (tuple, list)):
                    # Convert tuple/list to dict
                    if len(item) == 2:
                        # (follower_id, followee_id)
                        follow_dicts.append({
                            "follower_id": item[0],
                            "followee_id": item[1],
                            "round_id": None,
                        })
                    elif len(item) == 3:
                        # (follower_id, followee_id, round_id)
                        follow_dicts.append({
                            "follower_id": item[0],
                            "followee_id": item[1],
                            "round_id": item[2],
                        })
                    else:
                        self.logger.warning(f"Unexpected follow data format: {item}")
                        continue
                else:
                    self.logger.warning(f"Unexpected follow data type: {type(item)}")
                    continue
                    
            return self.follow_repo.add_follows_batch(follow_dicts)
        except Exception as e:
            self.logger.error(f"Error adding follows batch: {e}")
            return 0
