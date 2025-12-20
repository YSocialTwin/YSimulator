"""
Rule-based agent action implementations.

This module contains deterministic behaviors for rule-based (non-LLM) agents.
These actions follow simple, predictable patterns based on cluster membership
and probability distributions.
"""

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
    The behavior is deterministic - rule-based agents create cluster-specific comments.
    
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
        'Cluster 1 comment'
    """
    content = f"Cluster {cluster_id} comment"
    return ActionDTO(agent_id, cluster_id, "COMMENT", content=content, target_post_id=target_post_id)


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
