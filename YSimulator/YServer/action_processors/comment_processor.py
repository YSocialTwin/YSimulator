"""
Comment action processor.

Handles COMMENT actions on posts, including thread tracking and opinion updates.
"""

from typing import Any, Optional
import logging

from YSimulator.YServer.action_processors.base_processor import (
    BaseActionProcessor,
    ActionContext,
    ActionResult,
)


class CommentProcessor(BaseActionProcessor):
    """Processor for COMMENT actions."""
    
    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize comment processor.
        
        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)
    
    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process a COMMENT action.
        
        Creates a comment as a post with comment_to and thread_id fields.
        Handles:
        - Thread tracking (inherits root thread_id from parent)
        - Reaction count increment on parent post
        - Text annotations with parent sentiment
        - User interest tracking from parent post topics
        - Opinion dynamics updates
        
        Args:
            action: ActionDTO with action_type="COMMENT"
            context: ActionContext with current round info
            
        Returns:
            ActionResult with comment post_id if successful
        """
        try:
            # Get the parent post to inherit thread_id
            parent_post = self.services.post_service.get_post(action.target_post_id)
            
            if not parent_post or not isinstance(parent_post, dict):
                self.logger.warning(
                    f"Parent post not found or invalid for comment: {action.target_post_id}",
                    extra={
                        "extra_data": {
                            "agent_id": action.agent_id,
                            "target_post_id": action.target_post_id,
                        }
                    },
                )
                return ActionResult(
                    success=False,
                    action_type="COMMENT",
                    agent_id=action.agent_id,
                    error="Parent post not found or invalid"
                )
            
            # Get thread_id from parent - points to root post
            # If parent is root post, thread_id equals parent's ID
            # If parent is comment, it already inherited root's thread_id
            thread_id = parent_post.get("thread_id")
            
            # Fallback: If parent doesn't have thread_id (legacy data),
            # assume parent IS the root post
            if not thread_id:
                thread_id = action.target_post_id
            
            # Build comment post data
            post_data = {
                "user_id": str(action.agent_id),
                "tweet": action.content,
                "round": context.current_round_id,
                "comment_to": action.target_post_id,  # Points to immediate parent
                "thread_id": thread_id,  # Points to root post of thread
            }
            
            # Create the comment as a post
            post_id = self.services.post_service.create_post(post_data)
            
            if not post_id:
                self.logger.warning(
                    f"Failed to add comment for agent {action.agent_id}",
                    extra={"extra_data": {"agent_id": action.agent_id}},
                )
                return ActionResult(
                    success=False,
                    action_type="COMMENT",
                    agent_id=action.agent_id,
                    error="Failed to create comment"
                )
            
            # Increment reaction count for the parent post
            count_updated = self.services.post_service.increment_post_reaction_count(action.target_post_id)
            if count_updated:
                self.logger.info(
                    f"Incremented reaction count for post {action.target_post_id} after COMMENT by agent {action.agent_id}"
                )
            else:
                self.logger.warning(
                    f"Failed to increment reaction count for post {action.target_post_id}"
                )
            
            # Process annotations with parent sentiment
            if hasattr(action, "annotations") and action.annotations:
                parent_sentiment = self._get_parent_sentiment(action.target_post_id)
                self._process_annotations(
                    post_id,
                    action.agent_id,
                    action.annotations,
                    is_post=False,
                    is_comment=True,
                    parent_post_id=action.target_post_id,
                    parent_sentiment=parent_sentiment,
                )
            
            # Save parent post's topics as user interests
            self._track_user_interests(action, context.current_round_id)
            
            # Store opinion updates if calculated by client
            if hasattr(action, "updated_opinions") and action.updated_opinions:
                parent_author_id = parent_post.get("user_id")
                for topic_id, new_opinion in action.updated_opinions.items():
                    self.services.add_agent_opinion(
                        agent_id=str(action.agent_id),
                        topic_id=topic_id,
                        opinion=new_opinion,
                        id_interacted_with=parent_author_id,
                        id_post=action.target_post_id,
                    )
                self.logger.info(
                    f"Stored {len(action.updated_opinions)} opinion updates for agent {action.agent_id}"
                )
            
            return ActionResult(
                success=True,
                action_type="COMMENT",
                agent_id=action.agent_id,
                new_ids=[post_id],
                metadata={"post_id": post_id, "parent_post_id": action.target_post_id}
            )
            
        except Exception as e:
            self.logger.error(f"Error processing COMMENT action: {e}")
            return ActionResult(
                success=False,
                action_type="COMMENT",
                agent_id=action.agent_id,
                error=str(e)
            )
    
    def _get_parent_sentiment(self, parent_post_id: str) -> Optional[str]:
        """
        Get sentiment classification of parent post.
        
        Args:
            parent_post_id: Parent post identifier
            
        Returns:
            Sentiment classification: "pos", "neg", "neu", or empty string
        """
        parent_sentiment_data = self.services.metadata_service.get_post_sentiment(parent_post_id)
        if parent_sentiment_data is not None:
            sentiment_parent_compound = parent_sentiment_data.get("compound")
            if sentiment_parent_compound is not None:
                # Apply thresholding
                if sentiment_parent_compound > 0.05:
                    parent_sentiment = "pos"
                elif sentiment_parent_compound < -0.05:
                    parent_sentiment = "neg"
                else:
                    parent_sentiment = "neu"
                self.logger.info(
                    f"Parent sentiment: compound={sentiment_parent_compound:.3f} -> {parent_sentiment}"
                )
                return parent_sentiment
            else:
                self.logger.debug(f"Parent sentiment compound is None for post {parent_post_id}")
        else:
            self.logger.debug(f"No sentiment data found for parent post {parent_post_id}")
        
        return ""
    
    def _track_user_interests(self, action: Any, current_round_id: str) -> None:
        """
        Track user interests from parent post topics.
        
        Args:
            action: ActionDTO with target_post_id
            current_round_id: Current round identifier
        """
        parent_post_id = action.target_post_id
        topic_ids = self.services.post_service.get_post_topics(parent_post_id)
        
        for topic_id in topic_ids:
            self.services.interest_service.add_user_interest(
                user_id=str(action.agent_id),
                interest_id=topic_id,
                round_id=current_round_id,
            )
            
            # Increment the agent's interest counter for this topic
            topic_name = self._get_topic_name_from_id(topic_id)
            if topic_name:
                self._update_agent_interest_counter(
                    action.agent_id, topic_name, increment=1
                )
    
    def _get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID (delegates to services)."""
        # Try public method first, then private method
        if hasattr(self.services, 'get_topic_name_from_id'):
            return self.services.get_topic_name_from_id(topic_id)
        elif hasattr(self.services, '_get_topic_name_from_id'):
            return self.services._get_topic_name_from_id(topic_id)
        
        self.logger.warning(f"get_topic_name_from_id not available in services")
        return None
    
    def _update_agent_interest_counter(
        self, agent_id: str, topic_name: str, increment: int
    ) -> None:
        """Update agent's interest counter (delegates to services)."""
        if hasattr(self.services, '_update_agent_interest_counter'):
            self.services._update_agent_interest_counter(agent_id, topic_name, increment)
    
    def _process_annotations(
        self,
        post_id: str,
        agent_id: str,
        annotations: dict,
        is_post: bool,
        is_comment: bool,
        parent_post_id: Optional[str] = None,
        parent_sentiment: Optional[str] = None
    ) -> None:
        """Process text annotations (delegates to services)."""
        if hasattr(self.services, '_process_annotations'):
            self.services._process_annotations(
                post_id,
                agent_id,
                annotations,
                is_post,
                is_comment,
                parent_post_id=parent_post_id,
                parent_sentiment=parent_sentiment,
            )
