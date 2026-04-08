"""
Action router for dispatching actions to appropriate processors.

Uses the Strategy pattern to route each action type to its dedicated processor.
"""

import logging
from typing import Any, Dict, Optional

from YSimulator.YServer.action_processors.base_processor import (
    ActionContext,
    ActionResult,
    BaseActionProcessor,
)
from YSimulator.YServer.action_processors.comment_processor import CommentProcessor
from YSimulator.YServer.action_processors.follow_processor import FollowProcessor
from YSimulator.YServer.action_processors.post_processor import PostProcessor
from YSimulator.YServer.action_processors.reaction_processor import ReactionProcessor
from YSimulator.YServer.action_processors.report_processor import ReportProcessor
from YSimulator.YServer.action_processors.share_processor import ShareProcessor
from YSimulator.YServer.action_processors.unfollow_processor import UnfollowProcessor


class ActionRouter:
    """
    Routes actions to appropriate processors.

    Maintains a registry of action processors and dispatches actions based on type.
    """

    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize action router with processors.

        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        self.services = services
        self.logger = logger or logging.getLogger(__name__)

        # Initialize processors
        self.processors: Dict[str, BaseActionProcessor] = {
            "POST": PostProcessor(services, logger),
            "COMMENT": CommentProcessor(services, logger),
            "SHARE": ShareProcessor(services, logger),
            "FOLLOW": FollowProcessor(services, logger),
            "UNFOLLOW": UnfollowProcessor(services, logger),
            "REPORT": ReportProcessor(services, logger),
        }

        # Reaction processor handles all other action types (LIKE, LOVE, ANGRY, etc.)
        self.reaction_processor = ReactionProcessor(services, logger)

    def route(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Route action to appropriate processor.

        Args:
            action: ActionDTO with action_type field
            context: ActionContext with simulation state

        Returns:
            ActionResult from the processor
        """
        action_type = action.action_type

        # Get specific processor or use reaction processor for other types
        processor = self.processors.get(action_type, self.reaction_processor)

        # Validate action
        if not processor.validate(action):
            self.logger.warning(f"Action validation failed for {action_type}")
            return ActionResult(
                success=False,
                action_type=action_type,
                agent_id=action.agent_id,
                error="Action validation failed",
            )

        # Process action
        return processor.process(action, context)

    def register_processor(self, action_type: str, processor: BaseActionProcessor) -> None:
        """
        Register a custom processor for an action type.

        Args:
            action_type: Action type identifier
            processor: Processor instance
        """
        self.processors[action_type] = processor
        self.logger.info(f"Registered processor for action type: {action_type}")
