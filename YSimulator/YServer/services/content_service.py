"""
Content service for business logic related to articles, images, and websites.

This service encapsulates all content-related business operations.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import (
    ArticleRepository,
    ImageRepository,
)


class ContentService:
    """Service for content (articles, images, websites) business logic."""
    
    def __init__(
        self,
        article_repository: ArticleRepository,
        image_repository: ImageRepository = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize content service.
        
        Args:
            article_repository: Repository for article/website data access
            image_repository: Repository for image data access (optional)
            logger: Logger instance
        """
        self.article_repo = article_repository
        self.image_repo = image_repository
        self.logger = logger or logging.getLogger(__name__)
    
    # Article operations
    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """
        Add an article.
        
        Args:
            article_data: Article information
            
        Returns:
            Article ID or None
        """
        try:
            return self.article_repo.add_article(article_data)
        except Exception as e:
            self.logger.error(f"Error adding article: {e}")
            return None
    
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get article by ID.
        
        Args:
            article_id: Article ID
            
        Returns:
            Article data or None
        """
        try:
            return self.article_repo.get_article(article_id)
        except Exception as e:
            self.logger.error(f"Error getting article: {e}")
            return None
    
    def get_article_topics(self, article_id: str) -> List[str]:
        """
        Get topics associated with an article.
        
        Args:
            article_id: Article ID
            
        Returns:
            List of topic IDs
        """
        try:
            return self.article_repo.get_article_topics(article_id)
        except Exception as e:
            self.logger.error(f"Error getting article topics: {e}")
            return []
    
    # Website operations
    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a website.
        
        Args:
            website_data: Website information
            
        Returns:
            Website ID or None
        """
        try:
            return self.article_repo.add_website(website_data)
        except Exception as e:
            self.logger.error(f"Error adding website: {e}")
            return None
    
    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """
        Add multiple websites in a batch.
        
        Args:
            websites_data: List of website information dicts
            
        Returns:
            Number of websites added
        """
        try:
            return self.article_repo.add_websites_batch(websites_data)
        except Exception as e:
            self.logger.error(f"Error adding websites batch: {e}")
            return 0
    
    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """
        Get website by RSS URL.
        
        Args:
            rss_url: RSS feed URL
            
        Returns:
            Website data or None
        """
        try:
            return self.article_repo.get_website_by_rss(rss_url)
        except Exception as e:
            self.logger.error(f"Error getting website by RSS: {e}")
            return None
    
    # Image operations
    def add_image(self, image_data: Dict[str, Any]) -> Optional[str]:
        """
        Add an image.
        
        Args:
            image_data: Image information
            
        Returns:
            Image ID or None
        """
        if not self.image_repo:
            self.logger.warning("Image repository not available")
            return None
        
        try:
            return self.image_repo.add_image(image_data)
        except Exception as e:
            self.logger.error(f"Error adding image: {e}")
            return None
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """
        Get a random image.
        
        Returns:
            Image data or None
        """
        if not self.image_repo:
            self.logger.warning("Image repository not available")
            return None
        
        try:
            return self.image_repo.get_random_image()
        except Exception as e:
            self.logger.error(f"Error getting random image: {e}")
            return None
