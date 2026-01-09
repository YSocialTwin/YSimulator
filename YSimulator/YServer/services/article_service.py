"""
Article service for business logic related to articles and websites.

This service encapsulates all article/website-related business operations,
coordinating between repositories to perform complex tasks.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import (
    ArticleRepository,
    InterestRepository,
)


class ArticleService:
    """Service for article and website business logic."""

    def __init__(
        self,
        article_repository: ArticleRepository,
        interest_repository: Optional[InterestRepository] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize article service.

        Args:
            article_repository: Repository for article/website data access
            interest_repository: Repository for interest/topic operations (optional)
            logger: Logger instance
        """
        self.article_repo = article_repository
        self.interest_repo = interest_repository
        self.logger = logger or logging.getLogger(__name__)

    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a new website.

        Args:
            website_data: Website information dictionary

        Returns:
            Website ID if successful, None otherwise
        """
        try:
            return self.article_repo.add_website(website_data)
        except Exception as e:
            self.logger.error(f"Error in article service add_website: {e}")
            return None

    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """
        Add multiple websites in a batch.

        Args:
            websites_data: List of website information dictionaries

        Returns:
            Number of websites successfully added
        """
        try:
            return self.article_repo.add_websites_batch(websites_data)
        except Exception as e:
            self.logger.error(f"Error in article service add_websites_batch: {e}")
            return 0

    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a new article.

        Args:
            article_data: Article information dictionary

        Returns:
            Article ID if successful, None otherwise
        """
        try:
            return self.article_repo.add_article(article_data)
        except Exception as e:
            self.logger.error(f"Error in article service add_article: {e}")
            return None

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get article by ID.

        Args:
            article_id: Article identifier

        Returns:
            Article data dictionary or None if not found
        """
        try:
            return self.article_repo.get_article(article_id)
        except Exception as e:
            self.logger.error(f"Error in article service get_article: {e}")
            return None

    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """
        Get website by RSS URL.

        Args:
            rss_url: RSS feed URL

        Returns:
            Website data dictionary or None if not found
        """
        try:
            return self.article_repo.get_website_by_rss(rss_url)
        except Exception as e:
            self.logger.error(f"Error in article service get_website_by_rss: {e}")
            return None

    def get_article_topics(self, article_id: str) -> List[str]:
        """
        Get topics associated with an article.

        Args:
            article_id: Article identifier

        Returns:
            List of topic IDs associated with the article
        """
        try:
            return self.article_repo.get_article_topics(article_id)
        except Exception as e:
            self.logger.error(f"Error in article service get_article_topics: {e}")
            return []

    def get_article_with_topics(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get article with its associated topic names.

        This is a coordinated operation that retrieves the article
        and enriches it with topic information if interest_repository is available.

        Args:
            article_id: Article identifier

        Returns:
            Article data dictionary with topic names, or None if not found
        """
        try:
            article = self.article_repo.get_article(article_id)
            if not article:
                return None

            # If we have interest repository, enrich with topic names
            if self.interest_repo:
                topic_ids = self.article_repo.get_article_topics(article_id)
                topic_names = []
                for topic_id in topic_ids:
                    topic_name = self.interest_repo.get_topic_name_from_id(topic_id)
                    if topic_name:
                        topic_names.append(topic_name)
                article["topics"] = topic_names

            return article
        except Exception as e:
            self.logger.error(f"Error in article service get_article_with_topics: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if the article service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.article_repo.health_check()
        except Exception as e:
            self.logger.error(f"Error in article service health_check: {e}")
            return False
