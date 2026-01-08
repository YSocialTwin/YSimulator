"""
Batch Processor Module for YClient Simulation.

This module handles batching and processing of LLM calls in the scatter/gather pattern.
Collects pending LLM futures, resolves them in parallel, and converts to actions.

The scatter/gather pattern:
- Scatter: Fire off all LLM calls immediately without waiting
- Gather: Wait once for all LLM results simultaneously

Extracted from client.py as part of Phase 2 refactoring.
Updated in Phase 3 to use LLM service layer.
"""

import logging
import uuid
from typing import List, Optional, Tuple

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO
from YSimulator.YClient.text_support.text_annotator import annotate_text
from YSimulator.YClient.llm_utils import BatchHandler, ResponseParser, CostTracker, LLMManager, RetryHandler

# Constants
REACTION_TYPES = ["LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"]

# Token estimation constants (Phase 3: LLM usage tracking)
# Rough estimates for tracking purposes - actual tokens may vary
CHARS_PER_TOKEN = 4  # Approximate: English text averages ~4 chars per token
PROMPT_TOKENS_POST = 100  # Estimated prompt tokens for post generation
PROMPT_TOKENS_COMMENT = 120  # Estimated prompt tokens for comment/reaction generation
PROMPT_TOKENS_FOLLOW = 60  # Estimated prompt tokens for follow decision
REACTION_OUTPUT_TOKENS = 5  # Simple reaction outputs (LIKE, LOVE, etc.)


class BatchProcessor:
    """
    Processes batches of LLM calls using scatter/gather pattern.

    Handles three types of LLM calls:
    - Posts (content generation)
    - Reactions (comments, reactions, shares)
    - Follows (follow decisions)
    
    Now uses LLM service layer (Phase 3) for improved error handling and validation.
    """

    def __init__(
        self,
        server,
        client_id: str,
        llm,
        enable_sentiment: bool,
        enable_toxicity: bool,
        enable_emotions: bool,
        perspective_api_key: Optional[str],
        logger: logging.Logger,
        cost_tracker: Optional[CostTracker] = None,
    ):
        """
        Initialize the BatchProcessor.

        Args:
            server: Ray server actor handle
            client_id: Client identifier
            llm: LLM handle for text annotation
            enable_sentiment: Whether sentiment analysis is enabled
            enable_toxicity: Whether toxicity detection is enabled
            enable_emotions: Whether emotion detection is enabled
            perspective_api_key: API key for Perspective API
            logger: Logger instance
            cost_tracker: Optional CostTracker for monitoring LLM usage
        """
        self.server = server
        self.client_id = client_id
        self.llm = llm  # Keep raw LLM handle for text_annotator compatibility
        self.enable_sentiment = enable_sentiment
        self.enable_toxicity = enable_toxicity
        self.enable_emotions = enable_emotions
        self.perspective_api_key = perspective_api_key
        self.logger = logger
        
        # Phase 3: Initialize all LLM utilities modules
        self.llm_manager = LLMManager(llm, logger=logger)  # Wrap LLM for consistent interface
        self.batch_handler = BatchHandler(logger=logger)
        self.retry_handler = RetryHandler(max_retries=3, initial_delay=1.0, logger=logger)  # Add retry logic
        self.response_parser = ResponseParser(logger=logger)
        self.cost_tracker = cost_tracker  # Optional cost tracking

    def gather_pending_llm_posts(
        self, pending_llm_posts: List[Tuple], actions: List[ActionDTO]
    ) -> None:
        """
        Gather and resolve all pending LLM post generation calls.

        Args:
            pending_llm_posts: List of tuples:
                - (agent_id, cluster_id, future, topic_or_article_id) for regular/news posts
                - (agent_id, cluster_id, future, None, image_id, topic_ids) for image posts
            actions: List to append resolved post actions to
        """
        if not pending_llm_posts:
            return

        # Phase 3: Use batch_handler with retry logic for robustness
        futures = [p[2] for p in pending_llm_posts]
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures,
            futures,
            error_message="Gathering LLM post futures"
        )  # Blocks once for ALL posts with automatic retries

        for i, res_txt in enumerate(results):
            pending_item = pending_llm_posts[i]
            a_id = pending_item[0]
            cid = pending_item[1]
            
            # Phase 3: Validate response
            res_txt = self.response_parser.parse_text_response(res_txt, default="")
            if not res_txt:
                self.logger.warning(f"Empty LLM post response for agent {a_id}, skipping")
                continue
            
            # Phase 3: Track LLM usage (estimate tokens from content length)
            if self.cost_tracker:
                output_tokens = len(res_txt) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_post", PROMPT_TOKENS_POST, output_tokens)

            # Check if this is an image post (has 6 elements)
            if len(pending_item) == 6:
                # Image post: (agent_id, cluster_id, future, None, image_id, topic_ids)
                _, _, _, _, image_id, topic_ids = pending_item
                action = ActionDTO(a_id, cid, "POST", content=res_txt)
                action.image_id = image_id  # Set image_id as attribute
                action.topic_ids = topic_ids  # Store for later processing
                self.logger.info(
                    f"LLM image post for agent {a_id}: image_id={image_id}, has_image_id_attr={hasattr(action, 'image_id')}, topics={len(topic_ids)}, content_len={len(res_txt)}"
                )
            else:
                # Regular/news post: (agent_id, cluster_id, future, topic_or_article_id)
                topic_or_article = pending_item[3] if len(pending_item) > 3 else None
                action = ActionDTO(a_id, cid, "POST", content=res_txt)

                # Check if the fourth element is an article_id (UUID format) or a topic (string)
                if topic_or_article:
                    # Try to parse as UUID - if successful, it's an article_id
                    try:
                        uuid.UUID(topic_or_article)
                        action.article_id = topic_or_article
                        self.logger.info(
                            f"LLM post for agent {a_id}: article_id={topic_or_article}, content_len={len(res_txt)}"
                        )
                    except ValueError:
                        # Not a valid UUID, treat as topic string
                        action.topic = topic_or_article
                        self.logger.info(
                            f"LLM post for agent {a_id}: topic={topic_or_article}, content_len={len(res_txt)}"
                        )
                else:
                    self.logger.info(
                        f"LLM post for agent {a_id}: NO article_id/topic, content_len={len(res_txt)}"
                    )

            # Annotate the post text
            annotations = annotate_text(
                res_txt,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=self.enable_emotions,
                llm_handle=self.llm,
            )
            action.annotations = annotations
            self.logger.info(
                f"LLM post annotated for agent {a_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}, hashtags={len(annotations.get('hashtags', []))}, mentions={len(annotations.get('mentions', []))}"
            )

            actions.append(action)

    def gather_pending_llm_reactions(
        self,
        pending_llm_reactions: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Gather and resolve all pending LLM reaction/comment/share generation calls.

        Args:
            pending_llm_reactions: List of tuples:
                - (agent_id, cluster_id, target_post_id, future) for regular reactions/comments
                - (agent_id, cluster_id, target_post_id, future, mention_id) for replies to mentions
                - (agent_id, cluster_id, target_post_id, future, "SHARE") for share with commentary
            actions: List to append resolved reaction/comment/share actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates

        Returns:
            List of secondary follow candidates [(agent_id, cluster_id, author_id, post_content, is_llm)]
        """
        secondary_follow_candidates = []

        if not pending_llm_reactions:
            return secondary_follow_candidates

        self.logger.info(
            f"[REPLY] Gathering {len(pending_llm_reactions)} pending LLM reactions/comments"
        )

        # Count how many are mention replies
        mention_replies = sum(1 for r in pending_llm_reactions if len(r) > 4)
        if mention_replies > 0:
            self.logger.info(f"[REPLY] {mention_replies} of these are mention replies")

        # Phase 3: Use batch_handler with retry logic for robustness
        futures = [r[3] for r in pending_llm_reactions]
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures,
            futures,
            error_message="Gathering LLM reaction futures"
        )  # Blocks once for ALL reactions/comments with automatic retries

        for i, res_act in enumerate(results):
            # Phase 3: Track LLM usage
            if self.cost_tracker and res_act:
                # Estimate tokens based on response type
                if res_act.upper() in REACTION_TYPES or res_act.upper() == "SHARE":
                    # Simple reaction - minimal tokens
                    output_tokens = REACTION_OUTPUT_TOKENS
                else:
                    # Comment/share commentary - count actual content
                    output_tokens = len(res_act) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_comment", PROMPT_TOKENS_COMMENT, output_tokens)
            # Handle tuples of varying lengths:
            # 4-element: (agent_id, cluster_id, target_post_id, future) - regular comment/reaction
            # 5-element: (agent_id, cluster_id, target_post_id, future, mention_id_or_action_type)
            #   - If 5th element is a UUID string -> mention_id (reply to mention)
            #   - If 5th element is "SHARE" -> action_type (share with commentary)
            reaction_tuple = pending_llm_reactions[i]
            a_id = reaction_tuple[0]
            cid = reaction_tuple[1]
            target = reaction_tuple[2]

            # Check 5th element: mention_id or action_type
            mention_id = None
            action_type_override = None
            if len(reaction_tuple) > 4:
                fifth_element = reaction_tuple[4]
                # Check if it's a UUID (mention_id) or action type string
                if fifth_element == "SHARE":
                    action_type_override = "SHARE"
                else:
                    # Assume it's a mention_id (UUID or other identifier)
                    mention_id = fifth_element

            # Check if result is a comment/share commentary (text) or a reaction type
            if res_act and res_act.upper() not in REACTION_TYPES:
                # This is comment/share commentary text from LLM
                # Determine action type: SHARE (with commentary) or COMMENT
                determined_action_type = action_type_override if action_type_override else "COMMENT"

                self.logger.debug(
                    f"[REPLY] LLM generated {determined_action_type} for agent {a_id}: '{res_act[:50]}...' (is_mention_reply: {mention_id is not None})"
                )

                # Annotate the text
                annotations = annotate_text(
                    res_act,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key,
                    enable_emotions=self.enable_emotions,
                    llm_handle=self.llm,
                )
                self.logger.info(
                    f"LLM {determined_action_type} annotated for agent {a_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}, has_emotions={bool(annotations.get('emotions'))}, hashtags={len(annotations.get('hashtags', []))}, mentions={len(annotations.get('mentions', []))}"
                )

                # Calculate opinion updates
                post_data = ray.get(self.server.get_post.remote(target, client_id=self.client_id))
                updated_opinions = None
                if post_data:
                    updated_opinions = calculate_opinion_updates_fn(a_id, target, post_data)

                action = ActionDTO(
                    a_id,
                    cid,
                    determined_action_type,
                    content=res_act,
                    target_post_id=target,
                    annotations=annotations,
                    updated_opinions=updated_opinions,
                )
                actions.append(action)

                # If this was a reply to a mention, mark it as replied
                if mention_id:
                    self.logger.info(
                        f"[REPLY] Marking mention {mention_id} as replied for agent {a_id}"
                    )
                    ray.get(self.server.mark_mention_replied.remote(mention_id))
                    self.logger.info(
                        f"[REPLY] Successfully marked mention {mention_id} as replied (LLM)"
                    )

                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
            elif res_act.upper() != "IGNORE":
                # This is a reaction type (or SHARE)
                self.logger.debug(f"[REPLY] LLM generated reaction for agent {a_id}: {res_act}")

                # Special handling for SHARE - generate share commentary
                if res_act.upper() == "SHARE":
                    # For SHARE actions, use cluster-specific share content (similar to rule-based)
                    share_content = f"Sharing from cluster {cid}"
                    # Calculate opinion updates for the share
                    post_data = ray.get(
                        self.server.get_post.remote(target, client_id=self.client_id)
                    )
                    updated_opinions = None
                    if post_data:
                        updated_opinions = calculate_opinion_updates_fn(a_id, target, post_data)

                    action = ActionDTO(
                        a_id,
                        cid,
                        res_act.upper(),
                        content=share_content,
                        target_post_id=target,
                        updated_opinions=updated_opinions,
                    )
                    self.logger.info(
                        f"search action: LLM agent {a_id} decided to SHARE with content",
                        extra={
                            "extra_data": {
                                "agent_id": a_id,
                                "action_type": "SHARE",
                                "target_post_id": target,
                            }
                        },
                    )
                    # Track for secondary follow (share action)
                    if post_data:
                        secondary_follow_candidates.append(
                            (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                        )
                else:
                    # Regular reaction (LIKE, LOVE, LAUGH, ANGRY, SAD)
                    action = ActionDTO(a_id, cid, res_act, target_post_id=target)
                    # Track for secondary follow (read/reaction action)
                    post_data = ray.get(
                        self.server.get_post.remote(target, client_id=self.client_id)
                    )
                    if post_data:
                        secondary_follow_candidates.append(
                            (a_id, cid, post_data.get("user_id"), post_data.get("tweet", ""), True)
                        )

                actions.append(action)
            else:
                # IGNORE action - log for search action context
                self.logger.debug(
                    f"LLM agent {a_id} chose to IGNORE post {target}",
                    extra={
                        "extra_data": {
                            "agent_id": a_id,
                            "action_type": "IGNORE",
                            "target_post_id": target,
                        }
                    },
                )

        return secondary_follow_candidates

    def gather_pending_llm_follows(
        self, pending_llm_follows: List[Tuple], actions: List[ActionDTO]
    ) -> None:
        """
        Gather and resolve all pending LLM follow decision calls.

        Args:
            pending_llm_follows: List of (agent_id, cluster_id, future) tuples
            actions: List to append resolved follow actions to
        """
        if not pending_llm_follows:
            return

        # Phase 3: Use batch_handler with retry logic for robustness
        futures = [f[2] for f in pending_llm_follows]
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures,
            futures,
            error_message="Gathering LLM follow decision futures"
        )  # Blocks once for ALL follow decisions with automatic retries

        for i, target_user in enumerate(results):
            a_id, cid, _ = pending_llm_follows[i]
            
            # Phase 3: Track LLM usage
            if self.cost_tracker:
                # Follow decision - minimal output (user_id or None)
                output_tokens = 10
                self.cost_tracker.record_call("decide_follow", PROMPT_TOKENS_FOLLOW, output_tokens)
            
            # LLM returns user_id to follow or None to skip
            # Phase 3: validate response (target_user should be a user_id string or None)
            if target_user and isinstance(target_user, str):
                actions.append(ActionDTO(a_id, cid, "FOLLOW", target_user_id=target_user))
