"""
User service for business logic related to users.

This service encapsulates all user-related business operations,
coordinating between repositories to perform complex tasks.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from YSimulator.YServer.repositories.base_repository import (
    UserRepository,
    InterestRepository,
)


class UserService:
    """Service for user-related business logic."""
    
    def __init__(
        self,
        user_repository: UserRepository,
        interest_repository: Optional[InterestRepository] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize user service.
        
        Args:
            user_repository: Repository for user data access
            interest_repository: Repository for interest/topic operations (optional)
            logger: Logger instance
        """
        self.user_repo = user_repository
        self.interest_repo = interest_repository
        self.logger = logger or logging.getLogger(__name__)
    
    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Register a new user.
        
        Args:
            user_data: User information dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.user_repo.register_user(user_data)
        except Exception as e:
            self.logger.error(f"Error in user service register_user: {e}")
            return False
    
    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """
        Register multiple users in a batch.
        
        Args:
            users_data: List of user information dictionaries
            
        Returns:
            Tuple of (count of registered users, set of newly registered user IDs)
        """
        try:
            return self.user_repo.register_users_batch(users_data)
        except Exception as e:
            self.logger.error(f"Error in user service register_users_batch: {e}")
            return (0, set())
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.
        
        Args:
            user_id: User identifier
            
        Returns:
            User data dictionary or None if not found
        """
        try:
            return self.user_repo.get_user(user_id)
        except Exception as e:
            self.logger.error(f"Error in user service get_user: {e}")
            return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all users.
        
        Returns:
            List of user data dictionaries
        """
        try:
            return self.user_repo.get_all_users()
        except Exception as e:
            self.logger.error(f"Error in user service get_all_users: {e}")
            return []
    
    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """
        Update user's archetype.
        
        Args:
            user_id: User identifier
            new_archetype: New archetype value
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.user_repo.update_user_archetype(user_id, new_archetype)
        except Exception as e:
            self.logger.error(f"Error in user service update_user_archetype: {e}")
            return False
    
    def get_user_interests(
        self, user_id: str, start_round: int, end_round: int
    ) -> List[str]:
        """
        Get user interests within a time window.
        
        Args:
            user_id: User identifier
            start_round: Start round ID
            end_round: End round ID
            
        Returns:
            List of interest IDs
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return []
        
        try:
            return self.interest_repo.get_user_interests_in_window(
                user_id, start_round, end_round
            )
        except Exception as e:
            self.logger.error(f"Error in user service get_user_interests: {e}")
            return []
    
    def add_user_interest(
        self, user_id: str, interest_id: str, round_id: str
    ) -> bool:
        """
        Add an interest for a user.
        
        Args:
            user_id: User identifier
            interest_id: Interest identifier
            round_id: Round identifier
            
        Returns:
            True if successful, False otherwise
        """
        if not self.interest_repo:
            self.logger.warning("Interest repository not configured")
            return False
        
        try:
            return self.interest_repo.add_user_interest(user_id, interest_id, round_id)
        except Exception as e:
            self.logger.error(f"Error in user service add_user_interest: {e}")
            return False
    
    def health_check(self) -> bool:
        """
        Check if the service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.user_repo.health_check()
        except Exception as e:
            self.logger.error(f"Error in user service health_check: {e}")
            return False
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.
        
        Args:
            username: Username
            
        Returns:
            User data dict or None if not found
        """
        try:
            return self.user_repo.get_user_by_username(username)
        except Exception as e:
            self.logger.error(f"Error getting user by username {username}: {e}")
            return None
    
    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """
        Update agent's last active day.
        
        Args:
            agent_id: Agent ID
            day: Simulation day
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.user_repo.update_agent_last_active_day(agent_id, day)
        except Exception as e:
            self.logger.error(f"Error updating last active day for agent {agent_id}: {e}")
            return False
    
    def get_churned_agents(self) -> List[str]:
        """
        Get list of churned agents - matches old middleware signature.
        
        Returns:
            List of churned agent IDs
        """
        try:
            return self.user_repo.get_churned_agents()
        except Exception as e:
            self.logger.error(f"Error getting churned agents: {e}")
            return []
    
    def set_agent_churned(self, agent_id: str, round_id: str) -> bool:
        """
        Mark an agent as churned by setting left_on field - matches old middleware signature.
        
        Args:
            agent_id: Agent ID (UUID string)
            round_id: Round ID when agent churned (UUID string)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.user_repo.set_agent_churned(agent_id, round_id)
        except Exception as e:
            self.logger.error(f"Error setting agent {agent_id} as churned: {e}")
            return False
    
    def get_inactive_agents(self, current_day: int, inactivity_days: int = 7) -> List[str]:
        """
        Get list of inactive agents.
        
        Args:
            current_day: Current simulation day
            inactivity_days: Number of days of inactivity to consider
            
        Returns:
            List of inactive agent IDs
        """
        try:
            return self.user_repo.get_inactive_agents(current_day, inactivity_days)
        except Exception as e:
            self.logger.error(f"Error getting inactive agents: {e}")
            return []
