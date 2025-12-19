"""
LLM-powered agent action implementations.

This module contains intelligent behaviors for LLM-powered agents.
These actions use language models to generate contextual, varied content
and make nuanced decisions about social interactions.

All functions return Ray ObjectRefs (futures) to enable parallel execution
of multiple LLM calls using the scatter/gather pattern.
"""


def generate_llm_post_async(llm_handle, cluster_id: int, day: int, slot: int):
    """
    Initiate async LLM post generation.
    
    This function doesn't wait for the LLM response - it immediately returns
    a Ray ObjectRef (future) that can be resolved later. This enables parallel
    execution of multiple LLM calls using the scatter/gather pattern.
    
    The LLM service will generate contextual content based on:
    - Cluster ID (determines persona/behavior)
    - Current simulation time (day and slot)
    - Any additional context from the LLM service
    
    Args:
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to (determines persona)
        day: Current simulation day
        slot: Current time slot within the day
        
    Returns:
        Ray ObjectRef: Future that will resolve to generated post content (str)
        
    Usage:
        # Scatter phase - fire off multiple LLM calls in parallel
        futures = []
        for agent in agents:
            future = generate_llm_post_async(llm, agent.cluster, day, slot)
            futures.append((agent.id, agent.cluster, future))
        
        # Gather phase - wait for all results at once
        results = ray.get([f[2] for f in futures])
        
        # Create actions from results
        for i, content in enumerate(results):
            agent_id, cluster_id, _ = futures[i]
            actions.append(ActionDTO(agent_id, cluster_id, "POST", content=content))
    """
    return llm_handle.generate_post.remote(cluster_id, day, slot)


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
