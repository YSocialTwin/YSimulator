"""
LLM-powered agent action implementations.

This module contains intelligent behaviors for LLM-powered agents.
These actions use language models to generate contextual, varied content
and make nuanced decisions about social interactions.

All functions return Ray ObjectRefs (futures) to enable parallel execution
of multiple LLM calls using the scatter/gather pattern.
"""

import ray


def generate_llm_post_async(llm_handle, cluster_id: int, day: int, slot: int, agent_attrs: dict = None):
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
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        day: Current simulation day
        slot: Current time slot within the day
        agent_attrs: Optional dict with agent attributes (name, age, gender, etc.)
        
    Returns:
        Ray ObjectRef: Future that will resolve to generated post content (str)
        
    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent in agents:
            attrs = {"name": agent.username, "age": agent.age, ...}
            future = generate_llm_post_async(llm, agent.cluster, day, slot, attrs)
            futures.append((agent.id, agent.cluster, future))
        
        # Gather phase - wait for all results at once
        results = ray.get([f[2] for f in futures])
        
        # Create actions from results
        for i, content in enumerate(results):
            agent_id, cluster_id, _ = futures[i]
            actions.append(ActionDTO(agent_id, cluster_id, "POST", content=content))
    """
    return llm_handle.generate_post.remote(cluster_id, day, slot, agent_attrs)


def generate_llm_reaction_async(llm_handle, cluster_id: int, content: str):
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
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        content: Content of the post being reacted to
        
    Returns:
        Ray ObjectRef: Future that will resolve to reaction type (str)
        
    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent, target_post in agent_post_pairs:
            future = generate_llm_reaction_async(llm, agent.cluster, "post content")
            futures.append((agent.id, agent.cluster, target_post, future))
        
        # Gather phase - wait for all results at once
        results = ray.get([f[3] for f in futures])
        
        # Create actions from results (skip IGNORE)
        for i, reaction_type in enumerate(results):
            agent_id, cluster_id, target, _ = futures[i]
            if reaction_type != "IGNORE":
                actions.append(ActionDTO(agent_id, cluster_id, reaction_type, target_post_id=target))
    """
    return llm_handle.decide_reaction.remote(cluster_id, content)


def generate_news_post_async(news_service, llm_service, agent_cluster: int, article: dict, website_name: str = None):
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
    commentary_future = generate_llm_news_commentary.remote(llm_service, agent_cluster, article, website_name)
    
    return commentary_future, article_id


def generate_llm_read_async(llm_handle, cluster_id: int, content: str, agent_attrs: dict = None):
    """
    Initiate async LLM read reaction decision.
    
    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.
    
    The LLM service will decide how to react to a post discovered via read/recommendation.
    
    Args:
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        content: Content of the post being reacted to
        agent_attrs: Optional dict with agent attributes for dynamic persona building
        
    Returns:
        Ray ObjectRef: Future that will resolve to reaction type (str)
        
    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent, target_post, post_content in agent_post_pairs:
            attrs = {"name": agent.username, "age": agent.age, ...}
            future = generate_llm_read_async(llm, agent.cluster, post_content, attrs)
            futures.append((agent.id, agent.cluster, target_post, future))
        
        # Gather phase - wait for all results at once
        results = ray.get([f[3] for f in futures])
        
        # Create actions from results (skip IGNORE)
        for i, reaction_type in enumerate(results):
            agent_id, cluster_id, target, _ = futures[i]
            if reaction_type != "IGNORE":
                actions.append(ActionDTO(agent_id, cluster_id, reaction_type, target_post_id=target))
    """
    return llm_handle.generate_read_reaction.remote(cluster_id, content, agent_attrs)


def generate_llm_follow_async(llm_handle, cluster_id: int, candidate_users: list):
    """
    Initiate async LLM follow decision.
    
    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls.
    
    The LLM service will decide whether to follow one of the suggested users.
    
    Args:
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        candidate_users: List of user IDs that could be followed
        
    Returns:
        Ray ObjectRef: Future that will resolve to user ID to follow (str) or None
        
    Usage:
        # Fire off LLM call to decide which user to follow
        future = generate_llm_follow_async(llm, agent.cluster, candidates)
        # Later, resolve the future to get the decision
        target_user = ray.get(future)
        if target_user:
            actions.append(ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=target_user))
    """
    return llm_handle.generate_follow_decision.remote(cluster_id, candidate_users)


def generate_llm_reply_to_mention_async(llm_handle, cluster_id: int, post_content: str, 
                                         agent_attrs: dict, author_name: str, thread_context: list):
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
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        post_content: Content of the post that mentioned the agent
        agent_attrs: Dict with agent attributes (name, age, gender, etc.)
        author_name: Username of the person who mentioned the agent
        thread_context: List of previous posts/comments in chronological order
        
    Returns:
        Ray ObjectRef: Future that will resolve to generated comment content (str)
        
    Usage:
        # Scatter phase - fire off LLM call for reply
        future = generate_llm_reply_to_mention_async(
            llm, agent.cluster, post_content, agent_attrs, author_name, thread_context
        )
        pending_llm_reactions.append((agent.id, agent.cluster, post_id, future, mention_id))
        
        # Gather phase - wait for result
        comment_text = ray.get(future)
        action = ActionDTO(agent_id, cluster_id, "COMMENT", content=comment_text, target_post_id=post_id)
    """
    return llm_handle.generate_comment.remote(cluster_id, post_content, agent_attrs, author_name, thread_context)


@ray.remote
def generate_llm_news_commentary(llm_service, cluster_id: int, article: dict, website_name: str = None) -> str:
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
    except Exception as e:
        # Fallback if LLM fails - truncate title if too long
        article_title = article.get('title', 'News Article')
        title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
        return f"Check out this article: {title}"
