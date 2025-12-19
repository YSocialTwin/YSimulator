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
    Also saves the article to the database.
    
    Args:
        news_service: Ray actor reference for NewsFeedService
        llm_service: Ray actor reference for LLMService
        agent_cluster: Cluster ID of the agent (determines persona)
        article: Article dictionary with keys: title, summary, link, source, website_id
        
    Returns:
        tuple: (Ray ObjectRef for content, article_id)
    """
    # Save article to database first
    article_id_future = news_service.save_article_to_db.remote(article)
    article_id = ray.get(article_id_future)
    
    # Use LLM to generate commentary
    content_future = generate_llm_news_commentary.remote(llm_service, agent_cluster, article)
    
    return content_future, article_id


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


def generate_rule_based_news_post(agent_id: int, cluster_id: int, article: dict, 
                                   news_service, article_id: str = None) -> ActionDTO:
    """
    Generate a simple rule-based news post.
    
    Rule-based agents create straightforward news posts that include the article
    title, a snippet of the summary, and the link.
    
    Args:
        agent_id: Unique identifier for the agent
        cluster_id: Cluster/group the agent belongs to
        article: Article dictionary with keys: title, summary, link, source
        news_service: Ray actor reference for NewsFeedService
        article_id: Article ID if already saved (optional)
        
    Returns:
        tuple: (ActionDTO with POST action and news content, article_id)
    """
    # Save article to database if not already saved
    if not article_id and news_service:
        article_id = ray.get(news_service.save_article_to_db.remote(article))
    
    title = article.get("title", "Interesting article")
    summary = article.get("summary", "")[:100]  # Truncate to 100 chars
    link = article.get("link", "")
    source = article.get("source", "News")
    
    # Format the news post
    content = f"📰 {title}\n\n{summary}...\n\nVia {source}: {link}"
    
    action = ActionDTO(agent_id, cluster_id, "POST", content=content)
    
    return action, article_id
