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
from typing import Dict, List, Optional, Tuple, Union

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO
from YSimulator.YClient.llm_utils import (
    BatchHandler,
    CostTracker,
    LLMManager,
    ResponseParser,
    RetryHandler,
)
from YSimulator.YClient.text_support.text_annotator import annotate_text

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
        self.retry_handler = RetryHandler(
            max_retries=3, initial_delay=1.0, logger=logger
        )  # Add retry logic
        self.response_parser = ResponseParser(logger=logger)
        self.cost_tracker = cost_tracker  # Optional cost tracking

    def _get_llm_actor(self, agent_id: Optional[str] = None):
        """
        Get LLM actor handle, following YClient patterns.
        
        Handles both single actor and load balancer cases safely.
        Follows the pattern from llm_manager._get_llm_actor_for_manager.
        
        Args:
            agent_id: Optional agent ID for load balancing
            
        Returns:
            LLM actor handle
        """
        # Check class name to avoid issues with Mock objects (YClient pattern)
        if self.llm.__class__.__name__ in ('LLMLoadBalancer', 'LLMActorPool'):
            if agent_id is None:
                # Fallback to first actor if no agent_id provided
                return self.llm.get_all_actors()[0]
            return self.llm.get_actor_for_agent(agent_id)
        # Direct actor handle (including Ray actors)
        return self.llm

    def _is_vllm_backend(self) -> bool:
        """
        Check if the LLM backend is vLLM by checking for generate_post_batch method.
        
        Follows YClient pattern of checking class capabilities safely.
        
        Returns:
            bool: True if using vLLM backend, False otherwise (Ollama)
        """
        try:
            # Get an LLM actor to check its capabilities (using YClient pattern)
            test_actor = self._get_llm_actor()
            
            # Check if the actor has generate_post_batch method
            # Use hasattr on the actor class to avoid remote calls
            return hasattr(test_actor, 'generate_post_batch')
        except Exception as e:
            self.logger.debug(f"Could not determine LLM backend type: {e}, defaulting to Ollama")
            return False

    def gather_pending_llm_posts(
        self, pending_llm_posts: List[Tuple], actions: List[ActionDTO], 
        day: Optional[int] = None, slot: Optional[int] = None
    ) -> None:
        """
        Gather and resolve all pending LLM post generation calls.
        
        When vLLM backend is detected, uses batch inference for improved performance.
        Otherwise, falls back to standard scatter/gather pattern (Ollama).

        Args:
            pending_llm_posts: List of tuples:
                - (agent_id, cluster_id, future, topic_or_article_id) for regular/news posts
                - (agent_id, cluster_id, future, None, image_id, topic_ids) for image posts
            actions: List to append resolved post actions to
            day: Current simulation day (optional, needed for vLLM batching)
            slot: Current time slot (optional, needed for vLLM batching)
        """
        if not pending_llm_posts:
            return

        # Check if using vLLM backend for batch inference
        use_vllm_batching = self._is_vllm_backend()
        
        if use_vllm_batching:
            self.logger.info(f"Using vLLM batch inference for {len(pending_llm_posts)} posts")
            self._gather_posts_with_vllm_batch(pending_llm_posts, actions, day, slot)
        else:
            self.logger.debug(f"Using standard scatter/gather for {len(pending_llm_posts)} posts (Ollama)")
            self._gather_posts_standard(pending_llm_posts, actions)

    def _gather_posts_standard(
        self, pending_llm_posts: List[Tuple], actions: List[ActionDTO]
    ) -> None:
        """
        Standard scatter/gather pattern for Ollama backend (default).
        
        Args:
            pending_llm_posts: List of pending post tuples (supports both old and new formats)
            actions: List to append resolved post actions to
        """
        # Phase 3: Use batch_handler with retry logic for robustness
        # Filter out None futures (used for vLLM batching placeholders)
        futures = [p[2] for p in pending_llm_posts if p[2] is not None]
        
        if not futures:
            # All futures are None - shouldn't happen in standard path
            self.logger.warning("No valid futures in standard gather, skipping")
            return
        
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures, futures, error_message="Gathering LLM post futures"
        )  # Blocks once for ALL posts with automatic retries
        
        # Create mapping from non-None futures back to pending items
        future_to_index = {}
        result_index = 0
        for i, pending_item in enumerate(pending_llm_posts):
            if pending_item[2] is not None:
                future_to_index[result_index] = i
                result_index += 1

        for result_idx, res_txt in enumerate(results):
            pending_idx = future_to_index[result_idx]
            pending_item = pending_llm_posts[pending_idx]
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
                    f"LLM image post for agent {a_id}: image_id={image_id}, has_image_id_attr={hasattr( action, 'image_id')}, topics={len(topic_ids)}, content_len={len(res_txt)}"
                )
            else:
                # Regular/news post: Old format (agent_id, cluster_id, future, topic_or_article_id)
                # Or new format: (agent_id, cluster_id, future, topic, day, slot, agent_attrs)
                # Extract topic from position 3 in both cases
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
                f"LLM post annotated for agent {a_id}: has_sentiment={bool( annotations.get('sentiment'))}, has_toxicity={bool( annotations.get('toxicity'))}, has_emotions={bool( annotations.get('emotions'))}, hashtags={len( annotations.get( 'hashtags', []))}, mentions={len( annotations.get( 'mentions', []))}"
            )

            actions.append(action)

    def _gather_posts_with_vllm_batch(
        self, pending_llm_posts: List[Tuple], actions: List[ActionDTO],
        day: Optional[int] = None, slot: Optional[int] = None
    ) -> None:
        """
        vLLM batch inference pattern for improved performance.
        
        Collects all post generation requests and processes them in a single batch
        call to vLLM's generate_post_batch method, which is significantly faster
        than individual calls.
        
        Args:
            pending_llm_posts: List of pending post tuples
            actions: List to append resolved post actions to
            day: Current simulation day (fallback if not in tuple)
            slot: Current time slot (fallback if not in tuple)
        """
        # Separate posts into batchable (with agent_attrs) and non-batchable
        batchable_posts = []
        non_batchable_posts = []
        
        for pending_item in pending_llm_posts:
            # New format: (agent_id, cluster_id, future, topic, day, slot, agent_attrs)
            # Old format: (agent_id, cluster_id, future, topic) or image posts with 6 elements
            if len(pending_item) >= 7:
                # Has all info needed for batching
                batchable_posts.append(pending_item)
            else:
                # Missing agent_attrs or other info, fall back to standard gather for these
                non_batchable_posts.append(pending_item)
        
        # Process batchable posts with vLLM batch inference
        if batchable_posts:
            self.logger.info(f"Processing {len(batchable_posts)} posts with vLLM batch inference")
            self._process_vllm_batch(batchable_posts, actions)
        
        # Process non-batchable posts with standard gather
        if non_batchable_posts:
            self.logger.info(f"Processing {len(non_batchable_posts)} posts with standard gather (missing metadata)")
            self._gather_posts_standard(non_batchable_posts, actions)
    
    def _process_vllm_batch(
        self, batchable_posts: List[Tuple], actions: List[ActionDTO]
    ) -> None:
        """
        Process posts using vLLM's generate_post_batch method.
        
        Args:
            batchable_posts: List of tuples with format (agent_id, cluster_id, future, topic, day, slot, agent_attrs)
            actions: List to append resolved post actions to
        """
        # Build batch requests
        batch_requests = []
        for item in batchable_posts:
            agent_id, cluster_id, future, topic, item_day, item_slot, agent_attrs = item
            batch_requests.append({
                "cluster_id": cluster_id,
                "day": item_day,
                "slot": item_slot,
                "agent_attrs": agent_attrs
            })
        
        # Get LLM actor for batch call (using YClient pattern)
        llm_actor = self._get_llm_actor()
        
        # Call generate_post_batch with retry logic
        self.logger.info(f"Calling generate_post_batch for {len(batch_requests)} requests")
        try:
            batch_future = llm_actor.generate_post_batch.remote(batch_requests)
            results = self.retry_handler.retry_with_backoff(
                lambda f: ray.get(f),
                batch_future,
                error_message="vLLM batch post generation"
            )
        except Exception as e:
            self.logger.error(f"vLLM batch generation failed: {e}, falling back to standard gather")
            self._gather_posts_standard(batchable_posts, actions)
            return
        
        # Process results
        # Collect texts for batch emotion extraction
        texts_for_emotions = []
        action_start_idx = len(actions)
        
        for i, res_txt in enumerate(results):
            pending_item = batchable_posts[i]
            agent_id = pending_item[0]
            cluster_id = pending_item[1]
            topic = pending_item[3]  # topic_or_article_id
            
            # Validate response
            res_txt = self.response_parser.parse_text_response(res_txt, default="")
            if not res_txt:
                self.logger.warning(f"Empty vLLM batch post response for agent {agent_id}, skipping")
                continue
            
            # Track LLM usage
            if self.cost_tracker:
                output_tokens = len(res_txt) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_post", PROMPT_TOKENS_POST, output_tokens)
            
            # Create action (same logic as standard gather)
            action = ActionDTO(agent_id, cluster_id, "POST", content=res_txt)
            
            # Handle topic/article assignment
            if topic:
                try:
                    uuid.UUID(topic)
                    action.article_id = topic
                    self.logger.info(
                        f"vLLM batch post for agent {agent_id}: article_id={topic}, content_len={len(res_txt)}"
                    )
                except ValueError:
                    action.topic = topic
                    self.logger.info(
                        f"vLLM batch post for agent {agent_id}: topic={topic}, content_len={len(res_txt)}"
                    )
            else:
                self.logger.info(
                    f"vLLM batch post for agent {agent_id}: NO article_id/topic, content_len={len(res_txt)}"
                )
            
            # Annotate the post text (without emotions for now if vLLM)
            annotations = annotate_text(
                res_txt,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=False,  # Disable for now, will batch extract later
                llm_handle=self.llm,
            )
            
            # Collect text for batch emotion extraction if needed
            if self.enable_emotions:
                texts_for_emotions.append(res_txt)
            else:
                annotations["emotions"] = None
            
            action.annotations = annotations
            self.logger.info(
                f"vLLM batch post annotated for agent {agent_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}"
            )
            
            actions.append(action)
        
        # Batch extract emotions if any texts collected
        if texts_for_emotions:
            self._batch_extract_and_update_emotions(texts_for_emotions, action_start_idx, actions)

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
                - (agent_id, cluster_id, target_post_id, future) for regular reactions/comments (old format)
                - (agent_id, cluster_id, target_post_id, future, mention_id) for replies to mentions (old format)
                - (agent_id, cluster_id, target_post_id, future, "SHARE") for share with commentary (old format)
                - (agent_id, cluster_id, target_post_id, future, metadata_dict) for batching (new format)
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

        # Check if using vLLM backend for batch inference
        use_vllm_batching = self._is_vllm_backend()
        
        if use_vllm_batching:
            self.logger.info(f"Using vLLM batch inference for reactions/comments")
            return self._gather_reactions_with_vllm_batch(
                pending_llm_reactions, actions, calculate_opinion_updates_fn
            )
        else:
            self.logger.debug(f"Using standard scatter/gather for reactions/comments (Ollama)")
            return self._gather_reactions_standard(
                pending_llm_reactions, actions, calculate_opinion_updates_fn
            )

    def _gather_reactions_standard(
        self,
        pending_llm_reactions: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Standard scatter/gather pattern for Ollama backend (default).
        
        Args:
            pending_llm_reactions: List of pending reaction tuples
            actions: List to append resolved reaction/comment/share actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []

        # Count how many are mention replies
        mention_replies = sum(1 for r in pending_llm_reactions if len(r) > 4)
        if mention_replies > 0:
            self.logger.info(f"[REPLY] {mention_replies} of these are mention replies")

        # Phase 3: Use batch_handler with retry logic for robustness
        # Filter out None futures (used for vLLM batching placeholders)
        futures = [r[3] for r in pending_llm_reactions if r[3] is not None]
        
        if not futures:
            # All futures are None - shouldn't happen in standard path
            self.logger.warning("No valid futures in standard reaction gather, skipping")
            return secondary_follow_candidates
        
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures,
            futures,
            error_message="Gathering LLM reaction futures",
        )  # Blocks once for ALL reactions/comments with automatic retries
        
        # Create mapping from non-None futures back to pending items
        future_to_index = {}
        result_index = 0
        for i, reaction_tuple in enumerate(pending_llm_reactions):
            if reaction_tuple[3] is not None:
                future_to_index[result_index] = i
                result_index += 1

        for result_idx, res_act in enumerate(results):
            i = future_to_index[result_idx]
            # Phase 3: Track LLM usage
            if self.cost_tracker and res_act:
                # Estimate tokens based on response type
                if res_act.upper() in REACTION_TYPES or res_act.upper() == "SHARE":
                    # Simple reaction - minimal tokens
                    output_tokens = REACTION_OUTPUT_TOKENS
                else:
                    # Comment/share commentary - count actual content
                    output_tokens = len(res_act) // CHARS_PER_TOKEN
                self.cost_tracker.record_call(
                    "generate_comment", PROMPT_TOKENS_COMMENT, output_tokens
                )
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
                    f"[REPLY] LLM generated {determined_action_type} for agent {a_id}: "
                    f"'{res_act[:50]}...' (is_mention_reply: {mention_id is not None})"
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
                    f"LLM {determined_action_type}annotated for agent {a_id}: has_sentiment={bool( annotations.get('sentiment'))}, has_toxicity={bool( annotations.get('toxicity'))}, has_emotions={bool( annotations.get('emotions'))}, hashtags={len( annotations.get( 'hashtags', []))}, mentions={len( annotations.get( 'mentions', []))}"
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

    def _gather_reactions_with_vllm_batch(
        self,
        pending_llm_reactions: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        vLLM batch inference pattern for reactions/comments.
        
        Separates reactions into batchable (with metadata) and non-batchable,
        then processes them accordingly.
        
        Args:
            pending_llm_reactions: List of pending reaction tuples
            actions: List to append resolved actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []
        
        # Separate into batchable and non-batchable
        batchable_comments = []
        batchable_shares = []
        batchable_reads = []
        batchable_searches = []
        non_batchable = []
        
        for reaction_tuple in pending_llm_reactions:
            # New format with metadata: (agent_id, cluster_id, target_post_id, future, metadata_dict)
            if len(reaction_tuple) >= 5 and isinstance(reaction_tuple[4], dict):
                metadata = reaction_tuple[4]
                if metadata.get("type") == "comment":
                    batchable_comments.append(reaction_tuple)
                elif metadata.get("type") == "share":
                    batchable_shares.append(reaction_tuple)
                elif metadata.get("type") == "read":
                    batchable_reads.append(reaction_tuple)
                elif "post_content" in metadata and "agent_attrs" in metadata:
                    # Search action (has post_content and agent_attrs but no type field)
                    batchable_searches.append(reaction_tuple)
                else:
                    non_batchable.append(reaction_tuple)
            else:
                # Old format - use standard gather
                non_batchable.append(reaction_tuple)
        
        # Process batchable comments with vLLM batch inference
        if batchable_comments:
            self.logger.info(f"Processing {len(batchable_comments)} comments with vLLM batch inference")
            candidates = self._process_vllm_comment_batch(
                batchable_comments, actions, calculate_opinion_updates_fn
            )
            secondary_follow_candidates.extend(candidates)
        
        # Process batchable shares with vLLM batch inference
        if batchable_shares:
            self.logger.info(f"Processing {len(batchable_shares)} shares with vLLM batch inference")
            candidates = self._process_vllm_share_batch(
                batchable_shares, actions, calculate_opinion_updates_fn
            )
            secondary_follow_candidates.extend(candidates)
        
        # Process batchable reads (reaction decisions) with vLLM batch inference
        if batchable_reads:
            self.logger.info(f"Processing {len(batchable_reads)} read reactions with vLLM batch inference")
            candidates = self._process_vllm_read_batch(
                batchable_reads, actions, calculate_opinion_updates_fn
            )
            secondary_follow_candidates.extend(candidates)
        
        # Process batchable searches (search action decisions) with vLLM batch inference
        if batchable_searches:
            self.logger.info(f"Processing {len(batchable_searches)} search actions with vLLM batch inference")
            candidates = self._process_vllm_search_batch(
                batchable_searches, actions, calculate_opinion_updates_fn
            )
            secondary_follow_candidates.extend(candidates)
        
        # Process non-batchable with standard gather
        if non_batchable:
            self.logger.info(f"Processing {len(non_batchable)} reactions with standard gather (no metadata)")
            candidates = self._gather_reactions_standard(
                non_batchable, actions, calculate_opinion_updates_fn
            )
            secondary_follow_candidates.extend(candidates)
        
        return secondary_follow_candidates
    
    def _process_vllm_comment_batch(
        self,
        batchable_comments: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Process comments using vLLM's generate_comment_batch method.
        
        Args:
            batchable_comments: List of tuples with format (agent_id, cluster_id, target_post_id, future, metadata_dict)
            actions: List to append resolved actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []
        
        # Build batch requests from metadata
        batch_requests = []
        for item in batchable_comments:
            agent_id, cluster_id, target_post, future, metadata = item
            batch_requests.append({
                "cluster_id": cluster_id,
                "post_content": metadata.get("post_content", ""),
                "agent_attrs": metadata.get("agent_attrs"),
                "author_name": metadata.get("author_name", "Someone"),
                "thread_context": metadata.get("thread_context")
            })
        
        # Get LLM actor for batch call (using YClient pattern)
        llm_actor = self._get_llm_actor()
        
        # Call generate_comment_batch with retry logic
        self.logger.info(f"Calling generate_comment_batch for {len(batch_requests)} requests")
        try:
            batch_future = llm_actor.generate_comment_batch.remote(batch_requests)
            results = self.retry_handler.retry_with_backoff(
                lambda f: ray.get(f),
                batch_future,
                error_message="vLLM batch comment generation"
            )
        except Exception as e:
            self.logger.error(f"vLLM batch comment generation failed: {e}, falling back to standard gather")
            return self._gather_reactions_standard(batchable_comments, actions, calculate_opinion_updates_fn)
        
        # Process results
        # Collect texts for batch emotion extraction
        texts_for_emotions = []
        action_start_idx = len(actions)  # Track where new actions start
        
        # Collect opinion evaluation requests for batch processing
        opinion_requests = []
        
        for i, comment_text in enumerate(results):
            item = batchable_comments[i]
            agent_id = item[0]
            cluster_id = item[1]
            target_post = item[2]
            
            # Track LLM usage
            if self.cost_tracker:
                output_tokens = len(comment_text) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_comment", PROMPT_TOKENS_COMMENT, output_tokens)
            
            # Annotate the comment text (without emotions for now if vLLM)
            annotations = annotate_text(
                comment_text,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=False,  # Disable for now, will batch extract later
                llm_handle=self.llm,
            )
            
            # Collect text for batch emotion extraction if needed
            if self.enable_emotions:
                texts_for_emotions.append(comment_text)
            else:
                annotations["emotions"] = None
            
            # Defer opinion updates for batch processing (store post data for later)
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            updated_opinions = None
            if post_data:
                # Check if we should defer opinion evaluation for batching
                # Store parameters for batch evaluation instead of calling now
                opinion_requests.append({
                    "agent_id": agent_id,
                    "target_post": target_post,
                    "post_data": post_data,
                    "action_index": len(actions),  # Track which action this belongs to
                })
            
            # Check if this was a reply to a mention (has mention_id in metadata)
            metadata = item[4]
            mention_id = metadata.get("mention_id")
            if mention_id:
                self.logger.info(f"[REPLY] Marking mention {mention_id} as replied for agent {agent_id}")
                ray.get(self.server.mark_mention_replied.remote(mention_id))
                self.logger.info(f"[REPLY] Successfully marked mention {mention_id} as replied (vLLM batch)")
            
            # Create action (opinions will be added later via batch processing)
            action = ActionDTO(
                agent_id,
                cluster_id,
                "COMMENT",
                content=comment_text,
                target_post_id=target_post,
                annotations=annotations,
                updated_opinions=None,  # Will be updated by batch processing
            )
            actions.append(action)
            
            # Track for secondary follow
            if post_data:
                secondary_follow_candidates.append(
                    (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                )
        
        # Batch extract emotions if any texts collected
        if texts_for_emotions:
            self._batch_extract_and_update_emotions(texts_for_emotions, action_start_idx, actions)
        
        # Batch evaluate opinions if any requests collected
        if opinion_requests:
            self._batch_evaluate_and_update_opinions(opinion_requests, actions, calculate_opinion_updates_fn)
        
        return secondary_follow_candidates

    def _process_vllm_share_batch(
        self,
        batchable_shares: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Process shares using vLLM's generate_share_commentary batch method.
        
        Args:
            batchable_shares: List of tuples with format (agent_id, cluster_id, target_post_id, future, metadata_dict)
            actions: List to append resolved actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []
        
        # Build batch requests from metadata (shares use similar format to comments)
        batch_requests = []
        for item in batchable_shares:
            agent_id, cluster_id, target_post, future, metadata = item
            batch_requests.append({
                "cluster_id": cluster_id,
                "post_content": metadata.get("post_content", ""),
                "agent_attrs": metadata.get("agent_attrs"),
                "author_name": metadata.get("author_name", "Someone"),
            })
        
        # Get LLM actor for batch call (using YClient pattern)
        llm_actor = self._get_llm_actor()
        
        # For shares, we can use generate_comment_batch since the format is similar
        # Or call a dedicated generate_share_commentary_batch if it exists
        # For now, let's use comment batch as they have similar structure
        self.logger.info(f"Calling generate_comment_batch for {len(batch_requests)} share requests")
        try:
            batch_future = llm_actor.generate_comment_batch.remote(batch_requests)
            results = self.retry_handler.retry_with_backoff(
                lambda f: ray.get(f),
                batch_future,
                error_message="vLLM batch share commentary generation"
            )
        except Exception as e:
            self.logger.error(f"vLLM batch share generation failed: {e}, falling back to standard gather")
            return self._gather_reactions_standard(batchable_shares, actions, calculate_opinion_updates_fn)
        
        # Process results
        # Collect texts for batch emotion extraction
        texts_for_emotions = []
        action_start_idx = len(actions)
        
        # Collect opinion evaluation requests for batch processing
        opinion_requests = []
        
        for i, share_text in enumerate(results):
            item = batchable_shares[i]
            agent_id = item[0]
            cluster_id = item[1]
            target_post = item[2]
            
            # Track LLM usage
            if self.cost_tracker:
                output_tokens = len(share_text) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_share_commentary", PROMPT_TOKENS_COMMENT, output_tokens)
            
            # Annotate the share commentary text (without emotions for now if vLLM)
            annotations = annotate_text(
                share_text,
                enable_sentiment=self.enable_sentiment,
                enable_toxicity=self.enable_toxicity,
                perspective_api_key=self.perspective_api_key,
                enable_emotions=False,  # Disable for now, will batch extract later
                llm_handle=self.llm,
            )
            
            # Collect text for batch emotion extraction if needed
            if self.enable_emotions:
                texts_for_emotions.append(share_text)
            else:
                annotations["emotions"] = None
            
            self.logger.info(
                f"vLLM batch share annotated for agent {agent_id}: has_sentiment={bool(annotations.get('sentiment'))}, has_toxicity={bool(annotations.get('toxicity'))}"
            )
            
            # Defer opinion updates for batch processing
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            updated_opinions = None
            if post_data:
                # Store parameters for batch evaluation
                opinion_requests.append({
                    "agent_id": agent_id,
                    "target_post": target_post,
                    "post_data": post_data,
                    "action_index": len(actions),
                })
            
            # Create SHARE action (opinions will be added later via batch processing)
            action = ActionDTO(
                agent_id,
                cluster_id,
                "SHARE",
                content=share_text,
                target_post_id=target_post,
                annotations=annotations,
                updated_opinions=None,  # Will be updated by batch processing
            )
            actions.append(action)
            
            # Track for secondary follow
            if post_data:
                secondary_follow_candidates.append(
                    (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                )
        
        # Batch extract emotions if any texts collected
        if texts_for_emotions:
            self._batch_extract_and_update_emotions(texts_for_emotions, action_start_idx, actions)
        
        # Batch evaluate opinions if any requests collected
        if opinion_requests:
            self._batch_evaluate_and_update_emotions(opinion_requests, actions, calculate_opinion_updates_fn)
        
        return secondary_follow_candidates

    def _process_vllm_read_batch(
        self,
        batchable_reads: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Process read reactions (LIKE, LOVE, etc.) using vLLM's decide_reaction_batch method.
        
        Args:
            batchable_reads: List of tuples with format (agent_id, cluster_id, target_post_id, future, metadata_dict)
            actions: List to append resolved actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []
        
        # Build batch requests from metadata
        batch_requests = []
        for item in batchable_reads:
            agent_id, cluster_id, target_post, future, metadata = item
            batch_requests.append({
                "cluster_id": cluster_id,
                "post_content": metadata.get("post_content", ""),
                "agent_attrs": metadata.get("agent_attrs"),
            })
        
        # Get LLM actor for batch call (using YClient pattern)
        llm_actor = self._get_llm_actor()
        
        # Call generate_read_reaction_batch (supports agent_attrs including opinions)
        self.logger.info(f"Calling generate_read_reaction_batch for {len(batch_requests)} read requests")
        try:
            batch_future = llm_actor.generate_read_reaction_batch.remote(batch_requests)
            results = self.retry_handler.retry_with_backoff(
                lambda f: ray.get(f),
                batch_future,
                error_message="vLLM batch read reaction generation"
            )
        except Exception as e:
            self.logger.error(f"vLLM batch read generation failed: {e}, falling back to standard gather")
            return self._gather_reactions_standard(batchable_reads, actions, calculate_opinion_updates_fn)
        
        # Process results
        # Collect texts for batch emotion extraction (only for comments generated by reads)
        texts_for_emotions = []
        comment_action_indices = []  # Track which actions are comments that need emotions
        
        # Collect opinion evaluation requests for batch processing
        opinion_requests = []
        
        for i, reaction_type in enumerate(results):
            item = batchable_reads[i]
            agent_id = item[0]
            cluster_id = item[1]
            target_post = item[2]
            
            # Track LLM usage
            if self.cost_tracker:
                if reaction_type.upper() in REACTION_TYPES or reaction_type.upper() == "SHARE":
                    output_tokens = REACTION_OUTPUT_TOKENS
                else:
                    # Comment text
                    output_tokens = len(reaction_type) // CHARS_PER_TOKEN
                self.cost_tracker.record_call("generate_read_reaction", PROMPT_TOKENS_COMMENT, output_tokens)
            
            # Validate response
            reaction_type = self.response_parser.parse_text_response(reaction_type, default="IGNORE")
            
            # Handle different reaction types
            if reaction_type and reaction_type.upper() not in REACTION_TYPES:
                # This is comment text from LLM - treat as COMMENT action
                self.logger.debug(f"[READ] LLM generated comment for agent {agent_id}: '{reaction_type[:50]}...'")
                
                # Annotate the comment text (without emotions for now if vLLM)
                annotations = annotate_text(
                    reaction_type,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key,
                    enable_emotions=False,  # Disable for now, will batch extract later
                    llm_handle=self.llm,
                )
                
                # Collect text for batch emotion extraction if needed
                if self.enable_emotions:
                    texts_for_emotions.append(reaction_type)
                    comment_action_indices.append(len(actions))  # Track action index
                else:
                    annotations["emotions"] = None
                
                # Defer opinion updates for batch processing
                post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
                updated_opinions = None
                if post_data:
                    # Store parameters for batch evaluation
                    opinion_requests.append({
                        "agent_id": agent_id,
                        "target_post": target_post,
                        "post_data": post_data,
                        "action_index": len(actions),
                    })
                
                action = ActionDTO(
                    agent_id,
                    cluster_id,
                    "COMMENT",
                    content=reaction_type,
                    target_post_id=target_post,
                    annotations=annotations,
                    updated_opinions=None,  # Will be updated by batch processing
                )
                actions.append(action)
                
                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
            elif reaction_type.upper() == "SHARE":
                # SHARE reaction - would need share commentary, but for now just note it
                # This is handled separately by share_generator typically
                self.logger.debug(f"[READ] LLM decided to SHARE for agent {agent_id}")
                # Note: Real share implementation would call generate_share_commentary
                # For now, skip or create simple share
                pass
            elif reaction_type.upper() in REACTION_TYPES and reaction_type.upper() != "IGNORE":
                # Simple reaction (LIKE, LOVE, etc.)
                self.logger.debug(f"[READ] LLM generated reaction for agent {agent_id}: {reaction_type}")
                
                # Defer opinion updates for batch processing
                post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
                updated_opinions = None
                if post_data:
                    # Store parameters for batch evaluation
                    opinion_requests.append({
                        "agent_id": agent_id,
                        "target_post": target_post,
                        "post_data": post_data,
                        "action_index": len(actions),
                    })
                
                action = ActionDTO(
                    agent_id,
                    cluster_id,
                    reaction_type.upper(),
                    target_post_id=target_post,
                    updated_opinions=None,  # Will be updated by batch processing
                )
                actions.append(action)
                
                # Track for secondary follow (simple reaction)
                if post_data:
                    secondary_follow_candidates.append(
                        (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
            else:
                # IGNORE or unrecognized - skip
                self.logger.debug(f"[READ] Agent {agent_id} chose to IGNORE")
        
        # Batch extract emotions if any texts collected (only for comments)
        if texts_for_emotions:
            # Call batch extraction with specific action indices
            try:
                llm_actor = self._get_llm_actor()
                if hasattr(llm_actor, 'extract_emotions_batch'):
                    self.logger.info(f"Batch extracting emotions for {len(texts_for_emotions)} read comment texts")
                    batch_future = llm_actor.extract_emotions_batch.remote(texts_for_emotions)
                    results = self.retry_handler.retry_with_backoff(
                        lambda f: ray.get(f),
                        batch_future,
                        error_message="vLLM batch emotion extraction for read comments"
                    )
                    # Update actions with extracted emotions
                    for i, emotions in enumerate(results):
                        action_idx = comment_action_indices[i]
                        if action_idx < len(actions) and hasattr(actions[action_idx], 'annotations'):
                            actions[action_idx].annotations["emotions"] = emotions if emotions else []
                else:
                    # Fallback to individual extraction
                    for i, text in enumerate(texts_for_emotions):
                        emotion_future = llm_actor.extract_emotions.remote(text)
                        emotions = ray.get(emotion_future)
                        action_idx = comment_action_indices[i]
                        if action_idx < len(actions) and hasattr(actions[action_idx], 'annotations'):
                            actions[action_idx].annotations["emotions"] = emotions if emotions else []
            except Exception as e:
                self.logger.error(f"Failed to batch extract emotions for read comments: {e}")
                for action_idx in comment_action_indices:
                    if action_idx < len(actions) and hasattr(actions[action_idx], 'annotations'):
                        actions[action_idx].annotations["emotions"] = []
        
        # Batch evaluate opinions if any requests collected
        if opinion_requests:
            self._batch_evaluate_and_update_opinions(opinion_requests, actions, calculate_opinion_updates_fn)
        
        return secondary_follow_candidates

    def _process_vllm_search_batch(
        self,
        batchable_searches: List[Tuple],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> List[Tuple]:
        """
        Process search action decisions using vLLM's generate_search_action_batch method.
        
        Converts LLM decisions (COMMENT/SHARE/LIKE/etc) into appropriate ActionDTOs.
        
        Args:
            batchable_searches: List of tuples with format (agent_id, cluster_id, target_post_id, future, metadata_dict)
            actions: List to append resolved actions to
            calculate_opinion_updates_fn: Function to calculate opinion updates
            
        Returns:
            List of secondary follow candidates
        """
        secondary_follow_candidates = []
        
        # Build batch requests from metadata
        batch_requests = []
        for item in batchable_searches:
            agent_id, cluster_id, target_post, future, metadata = item
            batch_requests.append({
                "cluster_id": cluster_id,
                "post_content": metadata.get("post_content", ""),
                "agent_attrs": metadata.get("agent_attrs"),
            })
        
        # Get LLM actor for batch call
        llm_actor = self._get_llm_actor()
        
        # Call generate_search_action_batch
        self.logger.info(f"Calling generate_search_action_batch for {len(batch_requests)} search requests")
        try:
            batch_future = llm_actor.generate_search_action_batch.remote(batch_requests)
            results = self.retry_handler.retry_with_backoff(
                lambda f: ray.get(f),
                batch_future,
                error_message="vLLM batch search action decision"
            )
        except Exception as e:
            self.logger.error(f"vLLM batch search action failed: {e}, falling back to standard gather")
            return self._gather_reactions_standard(batchable_searches, actions, calculate_opinion_updates_fn)
        
        # Process results - convert action decisions to ActionDTOs
        # Collect texts for batch emotion extraction (only for comments/shares)
        texts_for_emotions = []
        action_indices_for_emotions = []
        
        # Collect opinion evaluation requests for batch processing
        opinion_requests = []
        
        for i, action_decision in enumerate(results):
            item = batchable_searches[i]
            agent_id = item[0]
            cluster_id = item[1]
            target_post = item[2]
            metadata = item[4]
            post_data = metadata.get("post_data")
            
            action_decision = action_decision.upper()
            
            if action_decision == "COMMENT":
                # Generate comment using rule-based or simple approach
                # For search, we can use a simple comment template
                comment_text = f"Interesting post about {metadata.get('agent_attrs', {}).get('topic', 'this topic')}."
                
                # Annotate the comment
                annotations = annotate_text(
                    comment_text,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key,
                    enable_emotions=False,  # Will batch extract later
                    llm_handle=self.llm,
                )
                
                # Collect for batch emotion extraction
                if self.enable_emotions:
                    texts_for_emotions.append(comment_text)
                    action_indices_for_emotions.append(len(actions))
                else:
                    annotations["emotions"] = None
                
                # Store for batch opinion processing
                if post_data:
                    opinion_requests.append({
                        "agent_id": agent_id,
                        "target_post": target_post,
                        "post_data": post_data,
                        "action_index": len(actions),
                    })
                
                action = ActionDTO(
                    agent_id,
                    cluster_id,
                    "COMMENT",
                    content=comment_text,
                    target_post_id=target_post,
                    annotations=annotations,
                    updated_opinions=None,
                )
                actions.append(action)
                
                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
                    
            elif action_decision == "SHARE":
                # Generate share with simple commentary
                share_text = f"Check out this post about {metadata.get('agent_attrs', {}).get('topic', 'this')}!"
                
                # Annotate the share commentary
                annotations = annotate_text(
                    share_text,
                    enable_sentiment=self.enable_sentiment,
                    enable_toxicity=self.enable_toxicity,
                    perspective_api_key=self.perspective_api_key,
                    enable_emotions=False,  # Will batch extract later
                    llm_handle=self.llm,
                )
                
                # Collect for batch emotion extraction
                if self.enable_emotions:
                    texts_for_emotions.append(share_text)
                    action_indices_for_emotions.append(len(actions))
                else:
                    annotations["emotions"] = None
                
                # Store for batch opinion processing
                if post_data:
                    opinion_requests.append({
                        "agent_id": agent_id,
                        "target_post": target_post,
                        "post_data": post_data,
                        "action_index": len(actions),
                    })
                
                action = ActionDTO(
                    agent_id,
                    cluster_id,
                    "SHARE",
                    content=share_text,
                    target_post_id=target_post,
                    annotations=annotations,
                    updated_opinions=None,
                )
                actions.append(action)
                
                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
                    
            elif action_decision in ["LIKE", "LOVE", "LAUGH", "ANGRY", "SAD"]:
                # Simple reaction
                # Store for batch opinion processing
                if post_data:
                    opinion_requests.append({
                        "agent_id": agent_id,
                        "target_post": target_post,
                        "post_data": post_data,
                        "action_index": len(actions),
                    })
                
                action = ActionDTO(
                    agent_id,
                    cluster_id,
                    action_decision,
                    target_post_id=target_post,
                    updated_opinions=None,
                )
                actions.append(action)
                
                # Track for secondary follow
                if post_data:
                    secondary_follow_candidates.append(
                        (agent_id, cluster_id, post_data.get("user_id"), post_data.get("tweet", ""), True)
                    )
            else:
                # IGNORE or unrecognized - skip
                self.logger.debug(f"[SEARCH] Agent {agent_id} chose to {action_decision}")
        
        # Batch extract emotions if any texts collected
        if texts_for_emotions:
            self._batch_extract_and_update_emotions(texts_for_emotions, action_indices_for_emotions, actions)
        
        # Batch evaluate opinions if any requests collected
        if opinion_requests:
            self._batch_evaluate_and_update_opinions(opinion_requests, actions, calculate_opinion_updates_fn)
        
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
            error_message="Gathering LLM follow decision futures",
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

    def _batch_extract_and_update_emotions(
        self,
        texts: List[str],
        action_indices: Union[int, List[int]],
        actions: List[ActionDTO],
    ) -> None:
        """
        Batch extract emotions and update actions.
        
        Only used with vLLM batching to extract emotions for multiple texts at once.
        
        Args:
            texts: List of text strings to extract emotions from
            action_indices: Either an int (start index for consecutive actions) or List[int] (specific indices)
            actions: List of actions to update
        """
        if not texts:
            return
        
        try:
            # Check if vLLM backend supports batch emotion extraction
            llm_actor = self._get_llm_actor()
            if hasattr(llm_actor, 'extract_emotions_batch'):
                self.logger.info(f"Batch extracting emotions for {len(texts)} texts using extract_emotions_batch")
                
                # Call batch emotion extraction
                batch_future = llm_actor.extract_emotions_batch.remote(texts)
                results = self.retry_handler.retry_with_backoff(
                    lambda f: ray.get(f),
                    batch_future,
                    error_message="vLLM batch emotion extraction"
                )
                
                self.logger.info(f"Successfully batch extracted emotions for {len(results)} texts")
            else:
                # Fallback to individual extraction for Ollama
                self.logger.info(f"Extracting emotions individually for {len(texts)} texts (no batch support)")
                results = []
                for text in texts:
                    emotion_future = llm_actor.extract_emotions.remote(text)
                    emotions = ray.get(emotion_future)
                    results.append(emotions if emotions else [])
            
            # Update actions with extracted emotions
            for i, emotions in enumerate(results):
                # Handle both int (consecutive) and list (specific indices)
                if isinstance(action_indices, int):
                    action_idx = action_indices + i
                else:
                    action_idx = action_indices[i]
                    
                if action_idx < len(actions) and hasattr(actions[action_idx], 'annotations'):
                    actions[action_idx].annotations["emotions"] = emotions if emotions else []
                    
        except Exception as e:
            self.logger.error(f"Failed to batch extract emotions: {e}")
            # Set empty emotions on error
            for i in range(len(texts)):
                # Handle both int (consecutive) and list (specific indices)
                if isinstance(action_indices, int):
                    action_idx = action_indices + i
                else:
                    action_idx = action_indices[i]
                    
                if action_idx < len(actions) and hasattr(actions[action_idx], 'annotations'):
                    actions[action_idx].annotations["emotions"] = []
    
    def _batch_evaluate_and_update_opinions(
        self,
        opinion_requests: List[Dict],
        actions: List[ActionDTO],
        calculate_opinion_updates_fn,
    ) -> None:
        """
        Batch evaluate opinions and update actions.
        
        Only used with vLLM batching when LLM-based opinion dynamics is enabled.
        Provides parallel batching path that doesn't modify core opinion pipeline.
        
        Args:
            opinion_requests: List of dicts with agent_id, target_post, post_data, action_index
            actions: List of actions to update with evaluated opinions
            calculate_opinion_updates_fn: Function to calculate opinion updates
        """
        if not opinion_requests:
            return
        
        try:
            # For now, use standard opinion calculation (parallel path approach)
            # Future optimization: detect LLM evaluation and batch those calls
            self.logger.info(f"Calculating opinions for {len(opinion_requests)} interactions (standard path)")
            
            for req in opinion_requests:
                agent_id = req["agent_id"]
                target_post = req["target_post"]
                post_data = req["post_data"]
                action_idx = req["action_index"]
                
                # Call standard opinion calculation
                updated_opinions = calculate_opinion_updates_fn(agent_id, target_post, post_data)
                
                # Update action with calculated opinions
                if action_idx < len(actions):
                    actions[action_idx].updated_opinions = updated_opinions
                    
        except Exception as e:
            self.logger.error(f"Failed to batch evaluate opinions: {e}")
            # Opinions remain None on error (non-critical)
