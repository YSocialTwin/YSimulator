"""
Post action processor.

Handles POST actions including article posts, image posts, and regular posts with topics.
"""

from typing import Any, Optional
import logging

from YSimulator.YServer.action_processors.base_processor import (
    BaseActionProcessor,
    ActionContext,
    ActionResult,
)


class PostProcessor(BaseActionProcessor):
    """Processor for POST actions."""

    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize post processor.

        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)

    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process a POST action.

        Creates a post and handles:
        - Article posts (with news_id)
        - Image posts (with image_id)
        - Regular posts with topics
        - Topic assignment and opinion management
        - Text annotations (hashtags, mentions, sentiment, toxicity)

        Args:
            action: ActionDTO with action_type="POST"
            context: ActionContext with current round info

        Returns:
            ActionResult with post_id if successful
        """
        try:
            # Build post data
            post_data = {
                "user_id": str(action.agent_id),
                "tweet": action.content,
                "round": context.current_round_id,
            }

            # Track article_id for topic handling
            article_id = None
            if hasattr(action, "article_id") and action.article_id:
                post_data["news_id"] = action.article_id
                article_id = action.article_id

            # Add image_id if this is an image post
            if hasattr(action, "image_id") and action.image_id:
                post_data["image_id"] = action.image_id
                self.logger.info(
                    f"Adding image post: agent={action.agent_id}, image_id={action.image_id}"
                )

            # Create the post
            post_id = self.services.post_service.create_post(post_data)

            if not post_id:
                self.logger.warning(
                    f"Failed to add post for agent {action.agent_id}",
                    extra={"extra_data": {"agent_id": action.agent_id}},
                )
                return ActionResult(
                    success=False,
                    action_type="POST",
                    agent_id=action.agent_id,
                    error="Failed to create post",
                )

            # Handle topics based on post type
            self._handle_post_topics(action, post_id, article_id)

            # Process annotations (hashtags, mentions, sentiment, toxicity)
            if hasattr(action, "annotations") and action.annotations:
                self._process_annotations(
                    post_id,
                    action.agent_id,
                    action.annotations,
                    is_post=True,
                    is_comment=False,
                )

            return ActionResult(
                success=True,
                action_type="POST",
                agent_id=action.agent_id,
                new_ids=[post_id],
                metadata={"post_id": post_id},
            )

        except Exception as e:
            self.logger.error(f"Error processing POST action: {e}")
            return ActionResult(
                success=False, action_type="POST", agent_id=action.agent_id, error=str(e)
            )

    def _handle_post_topics(self, action: Any, post_id: str, article_id: Optional[str]) -> None:
        """
        Handle topic assignment for posts.

        Supports three types:
        1. Article posts - link existing article topics
        2. Image posts - use pre-fetched topic_ids
        3. Regular posts - create/get topic from action.topic

        Args:
            action: ActionDTO with topic information
            post_id: Created post ID
            article_id: Article ID if this is an article post
        """
        # If this is an article post, extract and store topics
        if article_id:
            article_data = self.services.article_service.get_article(article_id)
            if article_data:
                existing_topic_ids = self.services.article_service.get_article_topics(article_id)

                # Get article content for opinion inference
                article_content = (
                    article_data.get("content")
                    or article_data.get("summary")
                    or article_data.get("title", "")
                )

                if existing_topic_ids:
                    # Article already has topics, link them to the post
                    for topic_id in existing_topic_ids:
                        self.services.post_service.add_post_topic(post_id, topic_id)
                        # Ensure author has opinion on each topic
                        topic_name = self.services.interest_service.get_topic_name_from_id(topic_id)
                        if topic_name:
                            self._ensure_agent_opinion_exists(
                                action.agent_id,
                                topic_id,
                                topic_name,
                                article_content=article_content,
                            )
                    self.logger.info(
                        f"Linked {len(existing_topic_ids)} existing article topics to post {post_id}"
                    )
            else:
                # Article not found in database - this shouldn't happen if website was loaded properly
                self.logger.warning(
                    f"Article {article_id} not found in database for post {post_id}. "
                    "This may indicate articles were not stored during website loading."
                )

        # Handle topic_ids for image posts
        elif hasattr(action, "topic_ids") and action.topic_ids:
            # Image posts have pre-fetched topic IDs from article
            for topic_id in action.topic_ids:
                self.services.post_service.add_post_topic(post_id, topic_id)
                # Ensure author has opinion on each topic
                topic_name = self.services.interest_service.get_topic_name_from_id(topic_id)
                if topic_name:
                    self._ensure_agent_opinion_exists(action.agent_id, topic_id, topic_name)
            self.logger.info(
                f"Linked {len(action.topic_ids)} article topics to image post {post_id}"
            )

        # Save post topic if provided (for non-article posts)
        elif hasattr(action, "topic") and action.topic:
            # Get or create the topic in interests table
            topic_id = self.services.interest_service.add_or_get_interest(action.topic)
            if topic_id:
                # Save post-topic association
                self.services.post_service.add_post_topic(post_id, topic_id)

                # Increment the agent's interest counter for this topic
                self._update_agent_interest_counter(action.agent_id, action.topic, increment=1)

                # Ensure author has an opinion on the topic they're posting about
                self._ensure_agent_opinion_exists(action.agent_id, topic_id, action.topic)

    def _ensure_agent_opinion_exists(
        self, agent_id: str, topic_id: str, topic_name: str, article_content: Optional[str] = None
    ) -> None:
        """
        Ensure agent has opinion on topic (delegates to server).

        Args:
            agent_id: Agent identifier
            topic_id: Topic identifier
            topic_name: Topic name
            article_content: Optional article content for opinion inference
        """
        # Services object is the server instance, which always has this method
        # Remove conditional check to prevent silent failures
        self.services._ensure_agent_opinion_exists(
            agent_id, topic_id, topic_name, article_content=article_content
        )

    def _update_agent_interest_counter(self, agent_id: str, topic: str, increment: int) -> None:
        """
        Update agent's interest counter (delegates to server).

        Args:
            agent_id: Agent identifier
            topic: Topic name
            increment: Amount to increment
        """
        # Services object is the server instance, which always has this method
        # Remove conditional check to prevent silent failures
        self.services._update_agent_interest_counter(agent_id, topic, increment)

    def _process_annotations(
        self, post_id: str, agent_id: str, annotations: dict, is_post: bool, is_comment: bool
    ) -> None:
        """
        Process text annotations (delegates to server).

        Args:
            post_id: Post identifier
            agent_id: Agent identifier
            annotations: Dict with hashtags, mentions, sentiment, toxicity
            is_post: Whether this is a post
            is_comment: Whether this is a comment
        """
        # Services object is the server instance, which always has this method
        # Remove conditional check to prevent silent failures
        self.services._process_annotations(post_id, agent_id, annotations, is_post, is_comment)
