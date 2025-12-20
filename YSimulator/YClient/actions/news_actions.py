"""
News Action Implementations

This module provides functions for generating news-based actions in the simulation.
Agents can post news articles, optionally with LLM-generated commentary.
"""

import ray
from YSimulator.YClient.classes.ray_models import ActionDTO


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


def generate_rule_based_news_post(agent_id: int, cluster_id: int, article: dict, 
                                   news_service, article_id: str = None) -> tuple:
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
