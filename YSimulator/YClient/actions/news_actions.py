"""
News Action Implementations

This module provides functions for generating news-based actions in the simulation.
Agents can post news articles, optionally with LLM-generated commentary.
"""

import ray
from YSimulator.YClient.classes.ray_models import ActionDTO


def generate_news_post_async(news_service, llm_service, agent_cluster: int, article: dict):
    """
    Generate a news post with LLM commentary asynchronously.
    
    This function creates a news post where an LLM agent reads a news article
    and generates a comment or perspective on it based on their persona.
    
    Args:
        news_service: Ray actor reference for NewsFeedService
        llm_service: Ray actor reference for LLMService
        agent_cluster: Cluster ID of the agent (determines persona)
        article: Article dictionary with keys: title, summary, link, source
        
    Returns:
        Ray ObjectRef: Future that will resolve to the generated post content
    """
    # Get LLM to comment on the news article
    prompt_data = {
        "cluster_id": agent_cluster,
        "title": article.get("title", ""),
        "summary": article.get("summary", ""),
        "source": article.get("source", "")
    }
    
    # Use LLM to generate commentary
    return generate_llm_news_commentary.remote(llm_service, agent_cluster, article)


@ray.remote
def generate_llm_news_commentary(llm_service, cluster_id: int, article: dict) -> str:
    """
    Generate LLM commentary on a news article.
    
    Args:
        llm_service: Ray actor reference for LLMService
        cluster_id: Agent cluster/persona ID
        article: Article dictionary
        
    Returns:
        str: Generated post content with news link and commentary
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    # Get the LLM instance from the service
    llm = ray.get(llm_service.llm.remote()) if hasattr(llm_service, 'llm') else None
    
    # For now, create a simple format with the article
    # In a full implementation, this would use the LLM to generate commentary
    title = article.get("title", "")
    summary = article.get("summary", "")[:150]  # Truncate summary
    link = article.get("link", "")
    source = article.get("source", "")
    
    # Simple format for news post
    content = f"📰 {title}\n\n{summary}...\n\nSource: {source}\n{link}"
    
    return content


def generate_rule_based_news_post(agent_id: int, cluster_id: int, article: dict) -> ActionDTO:
    """
    Generate a simple rule-based news post.
    
    Rule-based agents create straightforward news posts that include the article
    title, a snippet of the summary, and the link.
    
    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        article: Article dictionary with keys: title, summary, link, source
        
    Returns:
        ActionDTO: POST action with news content
    """
    title = article.get("title", "Interesting article")
    summary = article.get("summary", "")[:100]  # Truncate to 100 chars
    link = article.get("link", "")
    source = article.get("source", "News")
    
    # Format the news post
    content = f"📰 {title}\n\n{summary}...\n\nVia {source}: {link}"
    
    return ActionDTO(agent_id, cluster_id, "POST", content=content)
