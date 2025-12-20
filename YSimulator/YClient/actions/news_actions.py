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
        cluster_id: Agent cluster/persona ID
        article: Article dictionary with 'title' and 'summary' keys
        website_name: Name of the website/page sharing the article
        
    Returns:
        str: Generated commentary/perspective on the news article (not including article details)
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    # Extract article information
    article_title = article.get('title', 'News Article')
    article_text = article.get('summary', article.get('description', ''))
    
    # Truncate article text if too long (keep first 500 chars)
    if len(article_text) > 500:
        article_text = article_text[:500] + "..."
    
    # Default website name if not provided
    if not website_name:
        website_name = "this website"
    
    # Create a prompt asking LLM to act as social media manager
    system_msg = f"You are the social media manager for {website_name}. Your job is to present news articles to your audience in an engaging way."
    user_msg = f"""Here's a news article to share:

Title: {article_title}

Content: {article_text}

Write a brief, engaging tweet (max 280 characters) to present this article to your followers. Be professional but engaging. Do NOT include hashtags or links - just your commentary."""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("user", user_msg)
    ])
    
    # Get commentary from LLM
    try:
        chain = prompt | llm_service | StrOutputParser()
        # Invoke chain with the formatted prompt (no variables needed since we used f-strings)
        commentary = ray.get(chain.invoke.remote({}))
        
        # Ensure commentary doesn't exceed tweet length
        if len(commentary) > 280:
            commentary = commentary[:277] + "..."
            
        return commentary
    except Exception as e:
        # Fallback if LLM fails - truncate title if too long
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
