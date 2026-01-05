"""
Reaction action processor.

Handles reaction actions (LIKE, LOVE, ANGRY, SAD, LAUGH, etc.) on posts.
"""

from typing import Any, Optional
import logging

from YSimulator.YServer.action_processors.base_processor import (
    BaseActionProcessor,
    ActionContext,
    ActionResult,
)


class ReactionProcessor(BaseActionProcessor):
    """Processor for reaction actions (LIKE, LOVE, ANGRY, SAD, LAUGH, etc.)."""
    
    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize reaction processor.
        
        Args:
            services: Database adapter or service container
            logger: Logger instance
        """
        super().__init__(services, logger)
    
    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process a reaction action.
        
        Creates a reaction/interaction record and handles:
        - Reaction count increment on target post
        - Sentiment mapping from reaction type
        - Sentiment storage for each topic in the reacted post
        
        Args:
            action: ActionDTO with reaction type (LIKE, LOVE, ANGRY, etc.)
            context: ActionContext with current round info
            
        Returns:
            ActionResult indicating success/failure
        """
        try:
            # Build interaction data
            interaction_data = {
                "user_id": str(action.agent_id),
                "post_id": action.target_post_id,
                "type": action.action_type,
                "round": context.current_round_id,
            }
            
            # Create the reaction/interaction
            success = self.services.post_service.add_interaction(interaction_data)
            
            # Increment reaction count for the post
            if success:
                count_updated = self.services.post_service.increment_post_reaction_count(action.target_post_id)
                if count_updated:
                    self.logger.info(
                        f"Incremented reaction count for post {action.target_post_id} after {action.action_type} by agent {action.agent_id}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to increment reaction count for post {action.target_post_id}"
                    )
            
            # Save sentiment for reactions
            self._save_reaction_sentiment(action, context)
            
            if not success:
                return ActionResult(
                    success=False,
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                    error="Failed to create reaction"
                )
            
            return ActionResult(
                success=True,
                action_type=action.action_type,
                agent_id=action.agent_id,
                metadata={"target_post_id": action.target_post_id}
            )
            
        except Exception as e:
            self.logger.error(f"Error processing {action.action_type} action: {e}")
            return ActionResult(
                success=False,
                action_type=action.action_type,
                agent_id=action.agent_id,
                error=str(e)
            )
    
    def _save_reaction_sentiment(self, action: Any, context: ActionContext) -> None:
        """
        Save sentiment data for reaction on each topic in the post.
        
        Args:
            action: ActionDTO with reaction information
            context: ActionContext with current round info
        """
        # Get the post being reacted to
        reacted_post = self.services.post_service.get_post(action.target_post_id)
        
        if not reacted_post or not isinstance(reacted_post, dict):
            self.logger.warning(f"Reacted post {action.target_post_id} not found or invalid")
            return
        
        # Get topics from the reacted post
        topic_ids = self.services.post_service.get_post_topics(action.target_post_id)
        
        if not topic_ids:
            self.logger.debug(
                f"No topics found for reacted post {action.target_post_id}, skipping reaction sentiment"
            )
            return
        
        # Map reaction type to sentiment values
        sentiment_values = self._reaction_to_sentiment(action.action_type)
        
        if not sentiment_values:
            return
        
        # Get parent post sentiment for sentiment_parent field
        parent_sentiment = self._get_parent_sentiment(action.target_post_id)
        
        # Create sentiment entries for each topic
        for topic_id in topic_ids:
            sentiment_data = {
                "post_id": action.target_post_id,
                "user_id": str(action.agent_id),
                "topic_id": topic_id,
                "round": context.current_round_id,
                "neg": sentiment_values["neg"],
                "pos": sentiment_values["pos"],
                "neu": sentiment_values["neu"],
                "compound": sentiment_values["compound"],
                "sentiment_parent": parent_sentiment,
                "is_post": 0,
                "is_comment": 0,
                "is_reaction": 1,
            }
            # MetadataService.add_post_sentiment expects sentiment_data dict
            success = self.services.metadata_service.add_post_sentiment(sentiment_data)
            if success:
                self.logger.info(
                    f"Added reaction sentiment for {action.action_type} on post {action.target_post_id}, topic {topic_id}"
                )
            else:
                self.logger.error(
                    f"Failed to add reaction sentiment for {action.action_type} on post {action.target_post_id}, topic {topic_id}"
                )
    
    def _get_parent_sentiment(self, post_id: str) -> str:
        """
        Get sentiment classification of post.
        
        Args:
            post_id: Post identifier
            
        Returns:
            Sentiment classification: "pos", "neg", "neu", or empty string
        """
        parent_sentiment_data = self.services.metadata_service.get_post_sentiment(post_id)
        if parent_sentiment_data is not None:
            # Handle both dict and float return types
            if isinstance(parent_sentiment_data, (int, float)):
                sentiment_parent_compound = parent_sentiment_data
            else:
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
                    f"Parent sentiment for reaction on post {post_id}: compound={sentiment_parent_compound:.3f} -> {parent_sentiment}"
                )
                return parent_sentiment
            else:
                return ""
        else:
            return ""
    
    def _reaction_to_sentiment(self, reaction_type: str) -> Optional[dict]:
        """
        Map reaction type to sentiment values.
        
        Converts reaction types (LIKE, LOVE, ANGRY, SAD, LAUGH) to sentiment scores.
        
        Args:
            reaction_type: Reaction type (LIKE, LOVE, ANGRY, etc.)
            
        Returns:
            Dict with neg, pos, neu, compound values or None
        """
        # Map reaction types to sentiment
        # pos=1 for positive reactions, neg=1 for negative, neu=1 for neutral
        # compound: 1 if pos=1, -1 if neg=1, 0 otherwise
        reaction_map = {
            "LIKE": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "LOVE": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "LAUGH": {"pos": 1.0, "neg": 0.0, "neu": 0.0, "compound": 1.0},
            "ANGRY": {"pos": 0.0, "neg": 1.0, "neu": 0.0, "compound": -1.0},
            "SAD": {"pos": 0.0, "neg": 1.0, "neu": 0.0, "compound": -1.0},
        }
        
        return reaction_map.get(reaction_type, None)
