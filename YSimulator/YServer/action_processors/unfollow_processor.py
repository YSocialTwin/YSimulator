"""
Unfollow action processor.

Handles UNFOLLOW actions between users.
"""

from typing import Any, Optional
import logging

from YSimulator.YServer.action_processors.base_processor import (
    BaseActionProcessor,
    ActionContext,
    ActionResult,
)


class UnfollowProcessor(BaseActionProcessor):
    """Processor for UNFOLLOW actions."""
    
    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize unfollow processor.
        
        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)
    
    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process an UNFOLLOW action.
        
        Creates an unfollow relationship record between follower and target user.
        
        Args:
            action: ActionDTO with action_type="UNFOLLOW"
            context: ActionContext with current round info
            
        Returns:
            ActionResult indicating success/failure
        """
        try:
            # Validate required fields
            if not action.target_user_id:
                self.logger.error(
                    f"UNFOLLOW action missing target_user_id for agent {action.agent_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_user_id": action.target_user_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="UNFOLLOW",
                    agent_id=action.agent_id,
                    error="Missing required field: target_user_id"
                )
            
            # Create the unfollow relationship
            # FollowService.add_follow expects: follower_id, followee_id, round_id
            # For unfollow, we still use add_follow but with "unfollow" semantics
            success = self.services.follow_service.add_follow(
                follower_id=str(action.agent_id),
                followee_id=str(action.target_user_id),
                round_id=context.current_round_id
            )
            
            if not success:
                self.logger.warning(
                    f"Failed to add unfollow for agent {action.agent_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_user_id": action.target_user_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="UNFOLLOW",
                    agent_id=action.agent_id,
                    error="Failed to create unfollow relationship"
                )
            
            return ActionResult(
                success=True,
                action_type="UNFOLLOW",
                agent_id=action.agent_id,
                metadata={"target_user_id": action.target_user_id}
            )
            
        except Exception as e:
            self.logger.error(f"Error processing UNFOLLOW action: {e}")
            return ActionResult(
                success=False,
                action_type="UNFOLLOW",
                agent_id=action.agent_id,
                error=str(e)
            )
