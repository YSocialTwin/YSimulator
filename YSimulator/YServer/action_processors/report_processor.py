"""
Report action processor.

Handles REPORT actions emitted by LLM-capable agents after reading content.
"""

import logging
from typing import Any, Optional

from YSimulator.YServer.action_processors.base_processor import (
    ActionContext,
    ActionResult,
    BaseActionProcessor,
)


class ReportProcessor(BaseActionProcessor):
    """Processor for REPORT actions."""

    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        super().__init__(services, logger)

    def validate(self, action: Any) -> bool:
        report_type = str(getattr(action, "report_type", "") or "").lower()
        return bool(getattr(action, "target_post_id", None)) and report_type in {
            "toxic",
            "offensive",
        }

    def process(self, action: Any, context: ActionContext) -> ActionResult:
        try:
            target_post = self.services.post_service.get_post(action.target_post_id)
            if not target_post or not isinstance(target_post, dict):
                return ActionResult(
                    success=False,
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                    error="Target post not found",
                )

            success = self.services.post_service.add_report(
                {
                    "type": str(action.report_type).lower(),
                    "to_uid": target_post.get("user_id"),
                    "to_post": action.target_post_id,
                    "from_uid": str(action.agent_id),
                    "tid": context.current_round_id,
                }
            )
            if not success:
                return ActionResult(
                    success=False,
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                    error="Failed to create report",
                )

            return ActionResult(
                success=True,
                action_type=action.action_type,
                agent_id=action.agent_id,
                metadata={
                    "target_post_id": action.target_post_id,
                    "report_type": str(action.report_type).lower(),
                },
            )
        except Exception as e:
            self.logger.error(f"Error processing REPORT action: {e}")
            return ActionResult(
                success=False,
                action_type=action.action_type,
                agent_id=action.agent_id,
                error=str(e),
            )
