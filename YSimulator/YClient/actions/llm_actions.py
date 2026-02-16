"""
LLM-powered agent action implementations.

This module contains intelligent behaviors for LLM-powered agents.
These actions use language models to generate contextual, varied content
and make nuanced decisions about social interactions.

All functions return Ray ObjectRefs (futures) to enable parallel execution
of multiple LLM calls using the scatter/gather pattern.
"""

from typing import Any, Dict, List, Optional

import ray


def _get_llm_actor(llm_handle: Any, agent_id: Optional[str] = None) -> Any:
    """
    Get the appropriate LLM actor from handle.

    If llm_handle is a LLMLoadBalancer, uses agent_id to route to the correct actor.
    Otherwise returns llm_handle directly (single actor case).

    Args:
        llm_handle: Either a Ray actor handle or a LLMLoadBalancer instance
        agent_id: Optional agent ID for load balancing

    Returns:
        Ray actor handle for LLM service
    """
    # Check if llm_handle is a load balancer by checking its class name
    # This avoids issues with Mock objects that auto-create attributes
    if llm_handle.__class__.__name__ in ("LLMLoadBalancer", "LLMActorPool"):
        if agent_id is None:
            # Fallback to first actor if no agent_id provided
            return llm_handle.get_all_actors()[0]
        return llm_handle.get_actor_for_agent(agent_id)
    # Direct actor handle (including Ray actors)
    return llm_handle


def _should_use_vllm_batching(llm_handle: Any) -> bool:
    """
    Check if vLLM batching should be used for this LLM handle.

    vLLM batching defers individual .remote() calls and instead collects
    request parameters to make a single batch call during the gather phase.

    Args:
        llm_handle: LLM handle (actor or load balancer)

    Returns:
        bool: True if vLLM batching should be used, False for standard scatter/gather
    """
    try:
        # Get an actor to check capabilities
        actor = _get_llm_actor(llm_handle)
        # Check if actor has batch methods (indicates vLLM backend)
        return hasattr(actor, "generate_post_batch")
    except Exception:
        # Default to standard scatter/gather on error
        return False


def generate_llm_post_async(
    llm_handle: Any,
    cluster_id: int,
    day: int,
    slot: int,
    agent_attrs: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> ray.ObjectRef:
    """
    Initiate async LLM post generation.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls using the scatter/gather pattern.

    The LLM service will generate contextual content based on:
    - Cluster ID (determines persona/behavior)
    - Current simulation time (day and slot)
    - Agent attributes for dynamic persona building
    - Any additional context from the LLM service

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        day: Current simulation day
        slot: Current time slot within the day
        agent_attrs: Optional dict with agent attributes (name, age, gender, etc.)
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to generated post content (str)

    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent in agents:
            attrs = {"name": agent.username, "age": agent.age, ...}
            future = generate_llm_post_async(llm, agent.cluster, day, slot, attrs, agent.id)
            futures.append((agent.id, agent.cluster, future))

        # Gather phase - wait for all results at once
        results = ray.get([f[2] for f in futures])

        # Create actions from results
        for i, content in enumerate(results):
            agent_id, cluster_id, _ = futures[i]
            actions.append(ActionDTO(agent_id, cluster_id, "POST", content=content))
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)

    # For vLLM batching: Don't create individual futures, return None as placeholder
    # The batch processor will create a single batch call instead
    if _should_use_vllm_batching(llm_handle):
        return None  # Placeholder - batch processor will handle this

    # For Ollama/standard: Create individual future (standard scatter/gather)
    return llm_actor.generate_post.remote(cluster_id, day, slot, agent_attrs)


def generate_llm_reaction_async(
    llm_handle: Any, cluster_id: int, content: str, agent_id: Optional[str] = None
) -> ray.ObjectRef:
    """
    Initiate async LLM reaction decision.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.

    The LLM service will decide how to react to a post based on:
    - Cluster ID (determines persona/behavior)
    - Post content (what the agent is reacting to)

    Possible return values from LLM:
    - "LIKE": Positive reaction
    - "LOVE": Strong positive reaction
    - "LAUGH": Humorous reaction
    - "ANGRY": Negative reaction
    - "SAD": Emotional negative reaction
    - "IGNORE": Choose not to react

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        content: Content of the post being reacted to
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to reaction type (str)

    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent, target_post in agent_post_pairs:
            future = generate_llm_reaction_async(llm, agent.cluster, "post content", agent.id)
            futures.append((agent.id, agent.cluster, target_post, future))

        # Gather phase - wait for all results at once
        results = ray.get([f[3] for f in futures])

        # Create actions from results (skip IGNORE)
        for i, reaction_type in enumerate(results):
            agent_id, cluster_id, target, _ = futures[i]
            if reaction_type != "IGNORE":
                actions.append(ActionDTO(agent_id, cluster_id, reaction_type, target_post_id=target))
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)
    return llm_actor.decide_reaction.remote(cluster_id, content)


def generate_news_post_async(
    news_service, llm_service, agent_cluster: int, article: dict, website_name: str = None
):
    """
    Generate a news post with LLM commentary asynchronously.

    This function creates a news post where an LLM agent reads a news article
    and generates a comment or perspective on it based on their persona.
    Also saves the article to the database.

    Args:
        news_service: Ray actor reference for NewsFeedService
        llm_service: Ray actor reference for LLMService
        agent_cluster: Cluster ID of the agent (determines persona)
        article: Article dictionary with keys: title, summary, link, source, website_id
        website_name: Name of the website/page sharing the article (for LLM context)

    Returns:
        tuple: (Ray ObjectRef for commentary, article_id)
    """
    # Save article to database first
    article_id_future = news_service.save_article_to_db.remote(article)
    article_id = ray.get(article_id_future)

    # Use LLM to generate commentary (just the comment, not the full article)
    commentary_future = generate_llm_news_commentary.remote(
        llm_service, agent_cluster, article, website_name
    )

    # Return article content along with article_id to avoid re-fetching from DB
    return commentary_future, article_id, article


def generate_llm_read_async(
    llm_handle: Any,
    cluster_id: int,
    content: str,
    agent_attrs: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> ray.ObjectRef:
    """
    Initiate async LLM read reaction decision.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.

    The LLM service will decide how to react to a post discovered via read/recommendation.

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        content: Content of the post being reacted to
        agent_attrs: Optional dict with agent attributes for dynamic persona building
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to reaction type (str)

    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent, target_post, post_content in agent_post_pairs:
            attrs = {"name": agent.username, "age": agent.age, ...}
            future = generate_llm_read_async(llm, agent.cluster, post_content, attrs, agent.id)
            futures.append((agent.id, agent.cluster, target_post, future))

        # Gather phase - wait for all results at once
        results = ray.get([f[3] for f in futures])

        # Create actions from results (skip IGNORE)
        for i, reaction_type in enumerate(results):
            agent_id, cluster_id, target, _ = futures[i]
            if reaction_type != "IGNORE":
                actions.append(ActionDTO(agent_id, cluster_id, reaction_type, target_post_id=target))
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)

    # For vLLM batching: Don't create individual futures, return None as placeholder
    if _should_use_vllm_batching(llm_handle):
        return None  # Placeholder - batch processor will handle this

    # For Ollama/standard: Create individual future
    return llm_actor.generate_read_reaction.remote(cluster_id, content, agent_attrs)


def generate_llm_follow_async(
    llm_handle: Any,
    cluster_id: int,
    candidate_users: List[Dict[str, Any]],
    agent_id: Optional[str] = None,
) -> ray.ObjectRef:
    """
    Initiate async LLM follow decision.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.

    The LLM service will decide whether to follow one of the suggested users.

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        candidate_users: List of user IDs that could be followed
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to user ID to follow (str) or None

    Usage:
        # Fire off LLM call to decide which user to follow
        future = generate_llm_follow_async(llm, agent.cluster, candidates, agent.id)
        # Later, resolve the future to get the decision
        target_user = ray.get(future)
        if target_user:
            actions.append(ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=target_user))
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)
    return llm_actor.generate_follow_decision.remote(cluster_id, candidate_users)


def generate_llm_search_action_async(
    llm_handle,
    cluster_id: int,
    content: str,
    agent_attrs: dict = None,
    agent_id: Optional[str] = None,
):
    """
    Initiate async LLM search action decision.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.

    The LLM service will decide how to engage with a searched post based on:
    - Cluster ID (determines persona/behavior)
    - Post content (what the agent found via search)
    - Agent attributes for dynamic persona building

    Possible return values from LLM:
    - "COMMENT": Engage by commenting
    - "SHARE": Reshare the post
    - "LIKE", "LOVE", "LAUGH", "ANGRY", "SAD": React to the post
    - "IGNORE": Choose not to engage

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        content: Content of the post found via search
        agent_attrs: Optional dict with agent attributes for dynamic persona building
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to action type (str)

    Usage:
        # Fire off LLM call to decide action on searched post
        future = generate_llm_search_action_async(llm, agent.cluster, post_content, attrs, agent.id)
        # Later, resolve the future to get the decision
        action_type = ray.get(future)
        if action_type == "COMMENT":
            # Generate comment
        elif action_type == "SHARE":
            # Create share action
        elif action_type != "IGNORE":
            # Create reaction action
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)
    return llm_actor.decide_search_action.remote(cluster_id, content, agent_attrs)


def generate_llm_reply_to_mention_async(
    llm_handle,
    cluster_id: int,
    post_content: str,
    agent_attrs: dict,
    author_name: str,
    thread_context: list,
    agent_id: Optional[str] = None,
):
    """
    Initiate async LLM reply to mention generation.

    This function generates a comment reply when an agent is mentioned in a post.
    It's similar to generate_comment but specifically for replying to mentions.

    The LLM service will generate a contextual reply based on:
    - Cluster ID (determines persona/behavior)
    - Post content (the post that mentioned the agent)
    - Agent attributes for dynamic persona building
    - Author name (who mentioned the agent)
    - Thread context (preceding posts/comments)

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        post_content: Content of the post that mentioned the agent
        agent_attrs: Dict with agent attributes (name, age, gender, etc.)
        author_name: Username of the person who mentioned the agent
        thread_context: List of previous posts/comments in chronological order
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to generated comment content (str)

    Usage:
        # Scatter phase - fire off LLM call for reply
        future = generate_llm_reply_to_mention_async(
            llm, agent.cluster, post_content, agent_attrs, author_name, thread_context, agent.id
        )
        pending_llm_reactions.append((agent.id, agent.cluster, post_id, future, mention_id))

        # Gather phase - wait for result
        comment_text = ray.get(future)
        action = ActionDTO(agent_id, cluster_id, "COMMENT", content=comment_text, target_post_id=post_id)
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)

    # For vLLM batching: Don't create individual futures, return None as placeholder
    if _should_use_vllm_batching(llm_handle):
        return None  # Placeholder - batch processor will handle this

    # For Ollama/standard: Create individual future
    return llm_actor.generate_comment.remote(
        cluster_id, post_content, agent_attrs, author_name, thread_context
    )


def generate_llm_share_async(
    llm_handle,
    cluster_id: int,
    post_content: str,
    agent_attrs: dict = None,
    author_name: str = "Someone",
    agent_id: Optional[str] = None,
):
    """
    Initiate async LLM share commentary generation.

    This function generates a commentary/perspective when an LLM agent reshares
    a post. Unlike rule-based sharing (which just reshares without comment),
    LLM agents add their own perspective based on their persona and opinions.

    The LLM service will generate contextual commentary based on:
    - Cluster ID (determines persona/behavior)
    - Post content (what is being reshared)
    - Agent attributes for dynamic persona building (including opinions if available)
    - Author name (who wrote the original post)

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        post_content: Content of the post being reshared
        agent_attrs: Dict with agent attributes (name, age, opinions, etc.)
        author_name: Username of the original post author
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to share commentary (str)

    Usage:
        # Scatter phase - fire off LLM call
        attrs = {"name": agent.username, "post_topics": [...], "post_opinions": [...]}
        future = generate_llm_share_async(llm, agent.cluster, post_content, attrs, author, agent.id)

        # Gather phase - wait for result
        commentary = ray.get(future)
        action = ActionDTO(agent_id, cluster_id, "SHARE", content=commentary, target_post_id=post_id)
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)

    # For vLLM batching: Don't create individual futures, return None as placeholder
    if _should_use_vllm_batching(llm_handle):
        return None  # Placeholder - batch processor will handle this

    # For Ollama/standard: Create individual future
    return llm_actor.generate_share_commentary.remote(
        cluster_id, post_content, agent_attrs, author_name
    )


@ray.remote
def generate_llm_news_commentary(
    llm_service, cluster_id: int, article: dict, website_name: str = None
) -> str:
    """
    Generate LLM commentary on a news article as a social media manager.

    Args:
        llm_service: Ray actor reference for LLMService
        cluster_id: Agent cluster/persona ID (not currently used, reserved for future persona-based customization)
        article: Article dictionary with 'title' and 'summary' keys
        website_name: Name of the website/page sharing the article

    Returns:
        str: Generated commentary/perspective on the news article (not including article details)
    """
    # Call the LLMService method to generate commentary
    # Use ray.get to await the result from the Ray actor
    try:
        commentary = ray.get(llm_service.generate_news_commentary.remote(article, website_name))
        return commentary
    except Exception:
        # Fallback if LLM fails - truncate title if too long
        article_title = article.get("title", "News Article")
        title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
        return f"Check out this article: {title}"


def generate_image_post_async(
    llm_handle: Any,
    cluster_id: int,
    day: int,
    slot: int,
    agent_attrs: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> ray.ObjectRef:
    """
    Initiate async LLM-based image post generation.

    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later for batching.

    The LLM service will generate post content for an image. The actual image
    selection happens later in the action processing pipeline, not during this
    async call. This matches the pattern of other async generators where
    content generation is separated from resource attachment.

    Args:
        llm_handle: Ray actor handle for the LLM service or LLMLoadBalancer
        cluster_id: Cluster/group the agent belongs to (determines persona)
        day: Current simulation day (used by caller for context/tracking)
        slot: Current time slot within the day (used by caller for context/tracking)
        agent_attrs: Optional dict with agent attributes (name, age, gender, etc.)
        agent_id: Optional agent ID for load balancing (required when using LLMLoadBalancer)

    Returns:
        Ray ObjectRef: Future that will resolve to generated post content (str)

    Note:
        Image selection/attachment happens in the action processor when the future
        is resolved, not during this async generation call. The day/slot parameters
        are included for signature consistency with other async generators and are
        used by the caller for context tracking.
    """
    llm_actor = _get_llm_actor(llm_handle, agent_id)

    # For vLLM batching: Don't create individual futures, return None as placeholder
    # The batch processor will create a single batch call instead
    if _should_use_vllm_batching(llm_handle):
        return None  # Placeholder - batch processor will handle this

    # For Ollama/standard: Create individual future (standard scatter/gather)
    # Generate post content (image will be attached later during action processing)
    future = llm_actor.generate_post.remote(cluster_id, day, slot, agent_attrs)

    return future
