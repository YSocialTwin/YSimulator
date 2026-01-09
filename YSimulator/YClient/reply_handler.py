"""
Reply Handler Module for YClient.

This module handles the mention reply pipeline for simulation agents.
"""

import logging
import random
import traceback
from typing import Optional

import ray

from YSimulator.YClient.actions import (
    generate_llm_reply_to_mention_async,
    generate_rule_based_reply_to_mention,
)
from YSimulator.YClient.classes.ray_models import AgentProfile


def handle_reply_to_mention(
    agent: AgentProfile,
    agent_type: str,
    pending_llm_reactions: list,
    actions: list,
    server,
    client_id: str,
    llm_handle,
    max_length_thread_reading: int,
    logger: logging.Logger,
    extract_agent_attrs_func,
    annotate_action_content_func,
) -> Optional[str]:
    """
    Handle reply to mention for an agent.

    This method checks if the agent has unreplied mentions, randomly selects one,
    and creates a comment action (reply) using the reply-specific action functions.
    After creating the reply action, marks the mention as replied.

    Args:
        agent: AgentProfile of the agent
        agent_type: "llm" or "rule_based"
        pending_llm_reactions: List to append pending LLM comment futures
        actions: List to append immediate (rule-based) actions
        server: Ray server actor handle
        client_id: Client identifier
        llm_handle: LLM service handle
        max_length_thread_reading: Maximum thread context length
        logger: Logger instance
        extract_agent_attrs_func: Function to extract agent attributes
        annotate_action_content_func: Function to annotate action content

    Returns:
        str or None: mention_id if a reply was generated, None otherwise
    """
    # Page agents do not reply to mentions
    if agent.is_page == 1:
        logger.debug(f"[REPLY] Agent {agent.username} is a page agent - skipping reply pipeline")
        return None

    # Get unreplied mentions for this agent
    try:
        logger.debug(
            f"[REPLY] Checking unreplied mentions for agent {agent.username} (ID: {agent.id})"
        )
        unreplied_mentions = ray.get(
            server.get_unreplied_mentions.remote(agent.id, client_id=client_id)
        )

        if not unreplied_mentions:
            logger.debug(f"[REPLY] No unreplied mentions found for agent {agent.username}")
            return None  # No mentions to reply to

        logger.info(
            f"[REPLY] Agent {agent.username} has {len(unreplied_mentions)} unreplied mention(s)"
        )

        # Randomly select one mention to reply to
        selected_mention = random.choice(unreplied_mentions)
        mention_id = selected_mention["id"]
        post_id = selected_mention["post_id"]

        logger.info(
            f"[REPLY] Agent {agent.username} ({agent_type}) selected mention {mention_id} in post {post_id}"
        )

        # Get the post content to reply to
        post_data = ray.get(server.get_post.remote(post_id, client_id=client_id))
        if not post_data:
            logger.warning(
                f"[REPLY] Post {post_id} not found for mention {mention_id} - cannot reply"
            )
            return None

        post_content = post_data.get("tweet", "")
        author_id = post_data.get("user_id")

        logger.debug(
            f"[REPLY] Post content preview: '{post_content[:50]}...' (author: {author_id})"
        )

        # Get author username
        author_username = "Someone"
        if author_id:
            author_user = ray.get(server.get_user.remote(author_id, client_id=client_id))
            if author_user:
                author_username = author_user.get("username", "Someone")

        logger.info(f"[REPLY] Agent {agent.username} will reply to @{author_username}'s post")

        # Generate reply using the reply-specific action functions
        if agent_type == "llm":
            # Get thread context (preceding posts/comments in chronological order)
            thread_context = ray.get(
                server.get_thread_context.remote(
                    post_id, max_length_thread_reading, client_id=client_id
                )
            )
            logger.debug(
                f"[REPLY] Retrieved thread context: {len(thread_context)} previous posts/comments"
            )

            # Fire off async LLM call to generate reply
            agent_attrs = extract_agent_attrs_func(agent)
            future = generate_llm_reply_to_mention_async(
                llm_handle,
                agent.cluster,
                post_content,
                agent_attrs,
                author_username,
                thread_context,
            )
            # Store the mention_id with the pending reaction so we can mark it as replied later
            pending_llm_reactions.append((agent.id, agent.cluster, post_id, future, mention_id))
            logger.info(
                f"[REPLY] LLM reply request queued for agent {agent.username} (mention: {mention_id})"
            )
        else:
            # Rule-based: Generate reply with @username mention
            action = generate_rule_based_reply_to_mention(
                agent.id, agent.cluster, post_id, author_username
            )
            # Annotate rule-based comment
            annotate_action_content_func(action)
            actions.append(action)
            logger.info(
                f"[REPLY] Rule-based reply created: '{action.content}' for agent {agent.username}"
            )

            # Mark mention as replied immediately for rule-based agents
            ray.get(server.mark_mention_replied.remote(mention_id))
            logger.info(f"[REPLY] Marked mention {mention_id} as replied (rule-based)")

        return mention_id

    except Exception as e:
        logger.error(
            f"[REPLY] Error handling reply to mention for agent {agent.username}: {e}",
            extra={"extra_data": {"error": str(e), "agent_id": agent.id}},
        )
        logger.error(f"[REPLY] Traceback: {traceback.format_exc()}")
        return None
