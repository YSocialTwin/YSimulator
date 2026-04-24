"""
Share action processor.

Handles SHARE actions - creating new posts that reference original posts.
"""

import logging
from typing import Any, Optional

from YSimulator.YServer.action_processors.base_processor import (
    ActionContext,
    ActionResult,
    BaseActionProcessor,
)


class ShareProcessor(BaseActionProcessor):
    """Processor for SHARE actions."""

    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize share processor.

        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)

    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process a SHARE action.

        Creates a new post that references the original post via shared_from field.
        Handles:
        - Optional commentary content
        - Article reference copying from original post
        - Opinion dynamics updates

        Args:
            action: ActionDTO with action_type="SHARE"
            context: ActionContext with current round info

        Returns:
            ActionResult with new share post_id if successful
        """
        try:
            # Get the original post to copy metadata
            original_post = self.services.post_service.get_post(action.target_post_id)

            if not original_post:
                self.logger.warning(
                    f"Original post not found for share: {action.target_post_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_post_id": action.target_post_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="SHARE",
                    agent_id=action.agent_id,
                    error="Original post not found",
                )

            # Build share post data
            post_data = {
                "user_id": str(action.agent_id),
                "tweet": action.content if action.content else "",  # Optional commentary
                "round": context.current_round_id,
                "shared_from": action.target_post_id,
            }

            # If the original post references an article, copy the reference
            news_id = original_post.get("news_id")
            if news_id and not self._is_empty_or_default(news_id):
                post_data["news_id"] = news_id

            # Create the share post
            post_id = self.services.post_service.create_post(post_data)

            if not post_id:
                self.logger.warning(
                    f"Failed to add share for agent {action.agent_id}",
                    extra={"extra_data": {"agent_id": action.agent_id}},
                )
                return ActionResult(
                    success=False,
                    action_type="SHARE",
                    agent_id=action.agent_id,
                    error="Failed to create share post",
                )

            # Link original post topics to share (shares inherit topics from original)
            original_topic_ids = self._resolve_inherited_topic_ids(
                action.target_post_id, original_post
            )
            if original_topic_ids:
                topics_linked = 0
                for topic_id in original_topic_ids:
                    try:
                        if self.services.post_service.add_post_topic(post_id, topic_id):
                            topics_linked += 1
                        else:
                            self.logger.warning(
                                f"Failed to link topic {topic_id}from original post {action.target_post_id}to share {post_id}"
                            )
                    except Exception as e:
                        self.logger.error(f"Error linking topic {topic_id} to share {post_id}: {e}")
                if topics_linked > 0:
                    self.logger.info(
                        f"Linked {topics_linked}/{len(original_topic_ids)}topics from original post {action.target_post_id}to share {post_id}"
                    )
            else:
                self.logger.warning(
                    f"No topics found on original post {action.target_post_id} for share {post_id}"
                )

            # Store opinion updates if calculated by client
            if hasattr(action, "updated_opinions") and action.updated_opinions:
                parent_author_id = original_post.get("user_id")
                for topic_id, new_opinion in action.updated_opinions.items():
                    self.services.add_agent_opinion(
                        agent_id=str(action.agent_id),
                        topic_id=topic_id,
                        opinion=new_opinion,
                        id_interacted_with=parent_author_id,
                        id_post=action.target_post_id,
                    )
                self.logger.info(
                    f"Stored {len(action.updated_opinions)} opinion updates for share by agent {action.agent_id}"
                )

            return ActionResult(
                success=True,
                action_type="SHARE",
                agent_id=action.agent_id,
                new_ids=[post_id],
                metadata={"post_id": post_id, "shared_from": action.target_post_id},
            )

        except Exception as e:
            self.logger.error(f"Error processing SHARE action: {e}")
            return ActionResult(
                success=False, action_type="SHARE", agent_id=action.agent_id, error=str(e)
            )

    def _resolve_inherited_topic_ids(self, post_id: str, post_data: Optional[dict]) -> list[str]:
        """Resolve topics from the target post, then its upstream ancestors if needed."""
        topic_ids = self.services.post_service.get_post_topics(post_id)
        if topic_ids:
            return topic_ids

        candidate_ids = []
        if post_data:
            for field in ("shared_from", "comment_to", "thread_id"):
                candidate = post_data.get(field)
                if candidate and candidate not in candidate_ids and candidate != post_id:
                    candidate_ids.append(candidate)

        for candidate_id in candidate_ids:
            upstream_topics = self.services.post_service.get_post_topics(candidate_id)
            if upstream_topics:
                self.logger.info(
                    f"Using {len(upstream_topics)} upstream topics from {candidate_id} for share target {post_id}"
                )
                return upstream_topics
        return []

    def _is_empty_or_default(self, value: Any) -> bool:
        """
        Check if value is empty or default (delegates to services).

        Args:
            value: Value to check

        Returns:
            True if empty/default, False otherwise
        """
        if hasattr(self.services, "_is_empty_or_default"):
            return self.services._is_empty_or_default(value)
        # Fallback check
        return value is None or value == "" or value == "0"
