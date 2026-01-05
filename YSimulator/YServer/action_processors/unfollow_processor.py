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
            # Build unfollow relationship data
            unfollow_data = {
                "follower_id": str(action.agent_id),  # Agent who is unfollowing
                "user_id": action.target_user_id,  # User being unfollowed
                "action": "unfollow",
                "round": context.current_round_id,
            }
            
            # Create the unfollow relationship
            success = self.services.add_follow(unfollow_data)
            
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
