"""
Follow action processor.

Handles FOLLOW actions between users.
"""

from typing import Any, Optional
import logging

from YSimulator.YServer.action_processors.base_processor import (
    BaseActionProcessor,
    ActionContext,
    ActionResult,
)


class FollowProcessor(BaseActionProcessor):
    """Processor for FOLLOW actions."""
    
    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize follow processor.
        
        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)
    
    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process a FOLLOW action.
        
        Creates a follow relationship record between follower and target user.
        
        Args:
            action: ActionDTO with action_type="FOLLOW"
            context: ActionContext with current round info
            
        Returns:
            ActionResult indicating success/failure
        """
        try:
            # Validate required fields
            if not action.target_user_id:
                self.logger.error(
                    f"FOLLOW action missing target_user_id for agent {action.agent_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_user_id": action.target_user_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="FOLLOW",
                    agent_id=action.agent_id,
                    error="Missing required field: target_user_id"
                )
            
            # Build follow relationship data
            follow_data = {
                "follower_id": str(action.agent_id),  # Agent who is following
                "user_id": str(action.target_user_id),  # User being followed (ensure string)
                "action": "follow",
                "round": context.current_round_id,
            }
            
            # Create the follow relationship
            success = self.services.follow_service.add_follow(follow_data)
            
            if not success:
                self.logger.warning(
                    f"Failed to add follow for agent {action.agent_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_user_id": action.target_user_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="FOLLOW",
                    agent_id=action.agent_id,
                    error="Failed to create follow relationship"
                )
            
            return ActionResult(
                success=True,
                action_type="FOLLOW",
                agent_id=action.agent_id,
                metadata={"target_user_id": action.target_user_id}
            )
            
        except Exception as e:
            self.logger.error(f"Error processing FOLLOW action: {e}")
            return ActionResult(
                success=False,
                action_type="FOLLOW",
                agent_id=action.agent_id,
                error=str(e)
            )
