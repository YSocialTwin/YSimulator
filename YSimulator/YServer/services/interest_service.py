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
    
    def add_user_interest(self, user_id: str, interest_id: str, count: int = 1) -> bool:
        """
        Add a user interest.
        
        Args:
            user_id: User ID
            interest_id: Interest ID
            count: Count/weight of interest
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Note: count parameter needs to be handled - for now using round_id as placeholder
            return self.interest_repo.add_user_interest(user_id, interest_id, str(count))
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
            return [
                self.interest_repo.get_topic_name_from_id(iid) or ""
                for iid in interest_ids
            ]
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
    
    def add_agent_opinion(
        self, agent_id: str, topic_id: str, opinion_value: float, round_id: str
    ) -> bool:
        """
        Add an agent opinion on a topic.
        
        Args:
            agent_id: Agent ID
            topic_id: Topic ID
            opinion_value: Opinion value
            round_id: Round ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.interest_repo.add_agent_opinion(
                agent_id, topic_id, opinion_value, round_id
            )
        except Exception as e:
            self.logger.error(f"Error adding agent opinion: {e}")
            return False
    
    def get_latest_agent_opinion(
        self, agent_id: str, topic_id: str
    ) -> Optional[float]:
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
