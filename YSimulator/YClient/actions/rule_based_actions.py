"""
Rule-based agent action implementations.

This module contains deterministic behaviors for rule-based (non-LLM) agents.
These actions follow simple, predictable patterns based on cluster membership
and probability distributions.
"""

import random
from typing import Any, Dict, List, Optional

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO


def generate_rule_based_post(agent_id: int, cluster_id: int) -> ActionDTO:
    """
    Generate a simple rule-based post action.

    Rule-based agents create straightforward posts based on their cluster ID.
    The content is deterministic and follows a simple template.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to

    Returns:
        ActionDTO: Post action with simple cluster-based content

    Example:
        >>> action = generate_rule_based_post(42, 1)
        >>> action.action_type
        'POST'
        >>> action.content
        'Cluster 1 post'
    """
    content = f"Cluster {cluster_id} post"
    return ActionDTO(agent_id, cluster_id, "POST", content=content)


def generate_rule_based_reaction(agent_id: int, cluster_id: int, target_post_id: str) -> ActionDTO:
    """
    Generate a simple rule-based reaction action.

    Rule-based agents react to posts with a simple LIKE action.
    The behavior is deterministic - rule-based agents always LIKE posts
    they choose to react to.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_post_id: UUID of the post to react to

    Returns:
        ActionDTO: LIKE reaction action targeting the specified post

    Example:
        >>> action = generate_rule_based_reaction(42, 1, "post-uuid-123")
        >>> action.action_type
        'LIKE'
        >>> action.target_post_id
        'post-uuid-123'
    """
    return ActionDTO(agent_id, cluster_id, "LIKE", target_post_id=target_post_id)


def generate_rule_based_comment(agent_id: int, cluster_id: int, target_post_id: str) -> ActionDTO:
    """
    Generate a simple rule-based comment action.

    Rule-based agents create simple comments on posts.
    The behavior is deterministic - rule-based agents just comment "COMMENT".

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_post_id: UUID of the post to comment on

    Returns:
        ActionDTO: COMMENT action targeting the specified post

    Example:
        >>> action = generate_rule_based_comment(42, 1, "post-uuid-123")
        >>> action.action_type
        'COMMENT'
        >>> action.content
        'COMMENT'
    """
    content = "COMMENT"
    return ActionDTO(
        agent_id, cluster_id, "COMMENT", content=content, target_post_id=target_post_id
    )


def generate_rule_based_reply_to_mention(
    agent_id: int, cluster_id: int, target_post_id: str, author_username: str
) -> ActionDTO:
    """
    Generate a rule-based reply to a mention.

    Rule-based agents create simple replies that include a mention of the original author.
    This ensures the reply is contextually linked to the person who mentioned them.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_post_id: UUID of the post to comment on
        author_username: Username of the person who mentioned this agent

    Returns:
        ActionDTO: COMMENT action with @mention targeting the specified post

    Example:
        >>> action = generate_rule_based_reply_to_mention(42, 1, "post-uuid-123", "alice")
        >>> action.action_type
        'COMMENT'
        >>> action.content
        '@alice COMMENT'
    """
    content = f"@{author_username} COMMENT"
    return ActionDTO(
        agent_id, cluster_id, "COMMENT", content=content, target_post_id=target_post_id
    )


def generate_rule_based_share(agent_id: int, cluster_id: int, target_post_id: str) -> ActionDTO:
    """
    Generate a simple rule-based share action.

    Rule-based agents share posts with optional simple commentary.
    The behavior is deterministic - rule-based agents create cluster-specific share commentary.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_post_id: UUID of the post to share

    Returns:
        ActionDTO: SHARE action targeting the specified post

    Example:
        >>> action = generate_rule_based_share(42, 1, "post-uuid-123")
        >>> action.action_type
        'SHARE'
        >>> action.target_post_id
        'post-uuid-123'
    """
    content = f"Sharing from cluster {cluster_id}"
    return ActionDTO(agent_id, cluster_id, "SHARE", content=content, target_post_id=target_post_id)


def generate_rule_based_news_post(
    agent_id: int,
    cluster_id: int,
    article: Dict[str, Any],
    news_service: Any,
    article_id: Optional[str] = None,
) -> tuple:
    """
    Generate a simple rule-based news post.

    Rule-based agents share news without commentary - the post just references
    the article via news_id, with an empty or minimal tweet field.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        article: Article dictionary with keys: title, summary, link, source
        news_service: Ray actor reference for NewsFeedService
        article_id: Article ID if already saved (optional)

    Returns:
        tuple: (ActionDTO with POST action and empty/minimal content, article_id)
    """
    # Save article to database if not already saved
    if not article_id and news_service:
        article_id = ray.get(news_service.save_article_to_db.remote(article))

    # Rule-based agents share news without commentary
    # The article details are in the Article table, referenced by news_id
    content = ""  # Empty for rule-based agents

    action = ActionDTO(agent_id, cluster_id, "POST", content=content)

    return action, article_id


def generate_rule_based_read(agent_id: int, cluster_id: int, target_post_id: str) -> ActionDTO:
    """
    Generate a simple rule-based read action (reaction to discovered post).

    Rule-based agents randomly decide to LIKE, DISLIKE (ANGRY), or IGNORE posts
    they discover via the recommendation system.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_post_id: UUID of the post to react to

    Returns:
        ActionDTO or None: Reaction action (LIKE or ANGRY), or None if IGNORE

    Example:
        >>> action = generate_rule_based_read(42, 1, "post-uuid-123")
        >>> action.action_type in ["LIKE", "ANGRY"]
        True
        >>> # Or action could be None (IGNORE)
    """
    # Rule-based: randomly choose reaction
    reactions = ["LIKE", "ANGRY", "IGNORE"]  # ANGRY represents DISLIKE
    reaction_type = random.choice(reactions)

    if reaction_type == "IGNORE":
        return None  # No action for IGNORE

    return ActionDTO(agent_id, cluster_id, reaction_type, target_post_id=target_post_id)


def generate_rule_based_follow(agent_id: int, cluster_id: int, target_user_id: str) -> ActionDTO:
    """
    Generate a follow action for a rule-based agent.

    Rule-based agents always follow suggested users (no decision making).

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        target_user_id: UUID of the user to follow

    Returns:
        ActionDTO: Follow action targeting the specified user

    Example:
        >>> action = generate_rule_based_follow(42, 1, "user-uuid-123")
        >>> action.action_type
        'FOLLOW'
        >>> action.target_user_id
        'user-uuid-123'
    """
    return ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=target_user_id)


def generate_rule_based_image_post(agent_id: int, cluster_id: int, image_id: str) -> ActionDTO:
    """
    Generate a simple rule-based image post action.

    Rule-based agents share images with a simple "IMAGE" text.
    The image_id references the image in the database.

    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        image_id: UUID of the image to share

    Returns:
        ActionDTO: POST action with "IMAGE" content and image_id

    Example:
        >>> action = generate_rule_based_image_post(42, 1, "image-uuid-123")
        >>> action.action_type
        'POST'
        >>> action.content
        'IMAGE'
        >>> action.image_id
        'image-uuid-123'
    """
    action = ActionDTO(agent_id, cluster_id, "POST", content="IMAGE")
    action.image_id = image_id  # Set image_id as attribute
    return action
