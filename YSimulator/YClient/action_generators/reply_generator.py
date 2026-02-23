"""
Reply action generator for YSimulator agents.

This module generates reply-to-mention actions where agents respond to mentions.
Replaces the legacy reply_handler pattern with the action generator framework.
"""

import random
import traceback

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import (
    generate_llm_reply_to_mention_async,
    generate_rule_based_reply_to_mention,
)
from YSimulator.YClient.classes.ray_models import AgentProfile


class ReplyGenerator(BaseActionGenerator):
    """
    Generator for reply-to-mention actions.

    Handles both LLM and rule-based agents replying to mentions.
    - Checks for unreplied mentions
    - Randomly selects one mention to reply to
    - For LLM agents: fetches thread context and fires async reply generation
    - For rule-based agents: creates simple @mention reply immediately
    - Marks mention as replied after action creation
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a reply-to-mention action for the agent.

        This method:
        1. Checks if the agent has unreplied mentions
        2. Randomly selects one mention to reply to
        3. Fetches post content and context
        4. For LLM agents: fires async comment generation with thread context
        5. For rule-based agents: creates simple @mention reply immediately
        6. Stores mention_id for marking as replied later

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Page agents do not reply to mentions
        if agent.is_page == 1:
            self.context.logger.debug(
                f"[REPLY] Agent {agent.username} is a page agent - skipping reply pipeline"
            )
            return result

        try:
            # Get unreplied mentions for this agent
            self.context.logger.debug(
                f"[REPLY] Checking unreplied mentions for agent {agent.username} (ID: {agent.id})"
            )
            unreplied_mentions = ray.get(
                self.context.server.get_unreplied_mentions.remote(
                    agent.id, client_id=self.context.client_id
                )
            )

            if not unreplied_mentions:
                self.context.logger.debug(
                    f"[REPLY] No unreplied mentions found for agent {agent.username}"
                )
                return result  # No mentions to reply to

            self.context.logger.info(
                f"[REPLY] Agent {agent.username} has {len(unreplied_mentions)} unreplied mention(s)"
            )

            # Randomly select one mention to reply to
            selected_mention = random.choice(unreplied_mentions)
            mention_id = selected_mention["id"]
            post_id = selected_mention["post_id"]

            self.context.logger.info(
                f"[REPLY] Agent {agent.username}({agent_type}) selected mention {mention_id}in post {post_id}"
            )

            # Get the post content to reply to
            post_data = ray.get(
                self.context.server.get_post.remote(post_id, client_id=self.context.client_id)
            )
            if not post_data:
                self.context.logger.warning(
                    f"[REPLY] Post {post_id} not found for mention {mention_id} - cannot reply"
                )
                return result

            post_content = post_data.get("tweet") or post_data.get("text") or ""
            author_id = post_data.get("user_id")

            self.context.logger.debug(
                f"[REPLY] Post content preview: '{post_content[:50]}...' (author: {author_id})"
            )

            # Get author username
            author_username = "Someone"
            if author_id:
                author_user = ray.get(
                    self.context.server.get_user.remote(author_id, client_id=self.context.client_id)
                )
                if author_user:
                    author_username = author_user.get("username", "Someone")

            self.context.logger.info(
                f"[REPLY] Agent {agent.username} will reply to @{author_username}'s post"
            )

            # Generate reply
            if agent_type == "llm":
                # Get thread context (preceding posts/comments in chronological order)
                # Use max_length_thread_reading from actions_likelihood config
                max_thread_length = self.context.actions_likelihood.get(
                    "max_length_thread_reading", 10
                )
                thread_context = ray.get(
                    self.context.server.get_thread_context.remote(
                        post_id, max_thread_length, client_id=self.context.client_id
                    )
                )
                self.context.logger.debug(
                    f"[REPLY] Retrieved thread context: {len(thread_context)}previous posts/comments"
                )

                # Fire off async LLM call to generate reply
                agent_attrs = self._extract_agent_attrs(agent)

                # Get opinions for the topics in this post
                opinion_info = self._get_opinions_for_post(agent.id, post_id)
                if opinion_info["topics"]:
                    # Add opinion information to agent attrs
                    agent_attrs["post_topics"] = opinion_info["topics"]
                    agent_attrs["post_opinions"] = opinion_info["opinions"]
                    agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

                # Inject bounded memory context for this reply thread/author.
                self._inject_memory_context(
                    str(agent.id),
                    agent_attrs,
                    {
                        "topic": opinion_info["topics"][0] if opinion_info["topics"] else None,
                        "target_user_id": str(author_id) if author_id else None,
                        "thread_id": post_data.get("thread_id"),
                        "action_type": "REPLY",
                    },
                    metadata=result.metadata,
                )

                future = generate_llm_reply_to_mention_async(
                    self.context.llm,
                    agent.cluster,
                    post_content,
                    agent_attrs,
                    author_username,
                    thread_context,
                    agent.id,
                )
                # Store the mention_id with the pending reaction so we can mark it as replied later
                # Extended format for vLLM batching: (agent_id, cluster_id, post_id, future, metadata_dict)
                metadata = {
                    "type": "comment",  # Reply is also a comment
                    "post_content": post_content,
                    "agent_attrs": agent_attrs,
                    "author_name": author_username,
                    "thread_context": thread_context,
                    "mention_id": mention_id,  # Keep mention_id for marking as replied
                }
                result.pending_llm_calls.append(
                    (agent.id, agent.cluster, post_id, future, metadata)
                )
                self.context.logger.info(
                    f"[REPLY] LLM reply request queued for agent {agent.username}(mention: {mention_id})"
                )
            else:
                # Rule-based: Generate reply with @username mention
                action = generate_rule_based_reply_to_mention(
                    agent.id, agent.cluster, post_id, author_username
                )
                # Annotate rule-based comment
                self.context.annotate_action_fn(action)
                result.actions.append(action)
                self.context.logger.info(
                    f"[REPLY] Rule-based reply created: '{action.content}' for agent {agent.username}"
                )

                # Mark mention as replied immediately for rule-based agents
                ray.get(self.context.server.mark_mention_replied.remote(mention_id))
                self.context.logger.info(
                    f"[REPLY] Marked mention {mention_id} as replied (rule-based)"
                )

            # Store mention_id in metadata for tracking
            result.metadata["mention_id"] = mention_id
            result.metadata["post_id"] = post_id

        except Exception as e:
            self.context.logger.error(
                f"[REPLY] Error handling reply to mention for agent {agent.username}: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent.id}},
            )
            self.context.logger.error(f"[REPLY] Traceback: {traceback.format_exc()}")

        return result
