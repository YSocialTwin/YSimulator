"""
LLM Manager for centralized LLM interaction.

This module provides a unified interface for all LLM calls, wrapping the Ray LLM actor
and providing consistent error handling, logging, and retry logic.
"""

import logging
from typing import Any, Optional

import ray


class LLMManager:
    """
    Central manager for LLM interactions.
    
    Provides a clean interface to the underlying LLM service (Ray actor),
    with consistent error handling and logging.
    """
    
    def __init__(self, llm_handle: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize the LLM Manager.
        
        Args:
            llm_handle: Ray actor handle for LLM service
            logger: Logger instance for debugging
        """
        self.llm = llm_handle
        self.logger = logger or logging.getLogger(__name__)
    
    def generate_post(self, cluster_id: int, agent_attrs: dict, topic: str) -> Any:
        """
        Generate a post using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            topic: Topic for the post
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM generate_post: cluster={cluster_id}, topic={topic}")
        return self.llm.generate_post.remote(cluster_id, agent_attrs, topic)
    
    def generate_news_post(
        self, 
        cluster_id: int, 
        agent_attrs: dict, 
        article_title: str, 
        article_summary: str
    ) -> Any:
        """
        Generate a news-based post using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            article_title: Title of the news article
            article_summary: Summary of the news article
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_news_post: cluster={cluster_id}, title={article_title[:50]}..."
        )
        return self.llm.generate_news_post.remote(
            cluster_id, agent_attrs, article_title, article_summary
        )
    
    def generate_image_post(
        self, cluster_id: int, agent_attrs: dict, topic: str, image_id: str
    ) -> Any:
        """
        Generate an image post caption using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            topic: Topic for the image
            image_id: ID of the image
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_image_post: cluster={cluster_id}, topic={topic}, image={image_id}"
        )
        return self.llm.generate_image_post.remote(cluster_id, agent_attrs, topic, image_id)
    
    def generate_comment(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict,
        author_name: str,
        thread_context: str,
    ) -> Any:
        """
        Generate a comment on a post using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            post_content: Content of the post being commented on
            agent_attrs: Agent attributes for personalization
            author_name: Name of the post author
            thread_context: Context from the comment thread
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_comment: cluster={cluster_id}, post_len={len(post_content)}, author={author_name}"
        )
        return self.llm.generate_comment.remote(
            cluster_id, post_content, agent_attrs, author_name, thread_context
        )
    
    def generate_share_comment(
        self, cluster_id: int, agent_attrs: dict, post_content: str, author_name: str
    ) -> Any:
        """
        Generate a personalized comment for sharing a post.
        
        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            post_content: Content being shared
            author_name: Name of original post author
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_share_comment: cluster={cluster_id}, post_len={len(post_content)}"
        )
        return self.llm.generate_share_comment.remote(
            cluster_id, agent_attrs, post_content, author_name
        )
    
    def decide_follow(
        self, cluster_id: int, agent_attrs: dict, target_user: dict, recent_posts: list
    ) -> Any:
        """
        Decide whether to follow a user using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            target_user: Target user information
            recent_posts: Recent posts from the target user
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM decide_follow: cluster={cluster_id}, target={target_user.get('username', 'unknown')}"
        )
        return self.llm.decide_follow.remote(cluster_id, agent_attrs, target_user, recent_posts)
    
    def extract_topics_from_article(self, title: str, summary: str) -> Any:
        """
        Extract topics from a news article using the LLM.
        
        Args:
            title: Article title
            summary: Article summary
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM extract_topics: title={title[:50]}...")
        return self.llm.extract_topics_from_article.remote(title, summary)
    
    def infer_emotion(self, text: str) -> Any:
        """
        Infer emotion from text using the LLM.
        
        Args:
            text: Text to analyze
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM infer_emotion: text_len={len(text)}")
        return self.llm.infer_emotion.remote(text)
    
    def is_available(self) -> bool:
        """
        Check if LLM service is available.
        
        Returns:
            True if LLM handle is not None, False otherwise
        """
        return self.llm is not None
    
    def infer_article_opinion(
        self, article_content: str, topic_name: str, opinion_groups: dict
    ) -> Any:
        """
        Infer agent's opinion on an article topic using the LLM.
        
        Args:
            article_content: Article text to analyze
            topic_name: Topic to infer opinion about
            opinion_groups: Opinion group configuration
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM infer_article_opinion: topic={topic_name}, content_len={len(article_content)}"
        )
        return self.llm.infer_article_opinion.remote(
            article_content, topic_name, opinion_groups
        )
    
    def generate_secondary_follow_decision(
        self, cluster_id: int, post_content: str, is_currently_following: bool
    ) -> Any:
        """
        Decide whether to follow/unfollow post author as secondary follow using the LLM.
        
        Args:
            cluster_id: Agent's cluster ID
            post_content: Content of the post
            is_currently_following: Whether agent currently follows the author
            
        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_secondary_follow_decision: cluster={cluster_id}, following={is_currently_following}"
        )
        return self.llm.generate_secondary_follow_decision.remote(
            cluster_id, post_content, is_currently_following
        )
