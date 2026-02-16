"""
Content service for business logic related to articles, images, and websites.

This service encapsulates all content-related business operations.
It can optionally use specialized ArticleService and ImageService instances,
or work directly with repositories for backward compatibility.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import ArticleRepository, ImageRepository

if TYPE_CHECKING:
    from YSimulator.YServer.services.article_service import ArticleService
    from YSimulator.YServer.services.image_service import ImageService


class ContentService:
    """
    Service for content (articles, images, websites) business logic.

    This service acts as a facade that can either:
    1. Use specialized ArticleService and ImageService (recommended)
    2. Work directly with repositories (backward compatible)
    """

    def __init__(
        self,
        article_repository: Optional[ArticleRepository] = None,
        image_repository: Optional[ImageRepository] = None,
        article_service: Optional["ArticleService"] = None,
        image_service: Optional["ImageService"] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize content service.

        Args:
            article_repository: Repository for article/website data access
                (for backward compatibility)
            image_repository: Repository for image data access
                (for backward compatibility)
            article_service: Specialized article service (preferred)
            image_service: Specialized image service (preferred)
            logger: Logger instance

        Raises:
            ValueError: If neither repositories nor services are
                provided for articles
        """
        # Validate that we have at least one way to handle articles
        if not article_repository and not article_service:
            raise ValueError(
                "ContentService requires either article_repository "
                "or article_service to be provided"
            )

        # Support both new pattern (with services) and
        # old pattern (direct repositories)
        self.article_service = article_service
        self.image_service = image_service

        # Keep repository references for backward compatibility
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
        if self.article_service:
            return self.article_service.add_article(article_data)

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
        if self.article_service:
            return self.article_service.get_article(article_id)

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
        if self.article_service:
            return self.article_service.get_article_topics(article_id)

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
        if self.article_service:
            return self.article_service.add_website(website_data)

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
        if self.article_service:
            return self.article_service.add_websites_batch(websites_data)

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
        if self.article_service:
            return self.article_service.get_website_by_rss(rss_url)

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
        if self.image_service:
            return self.image_service.add_image(image_data)

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
        if self.image_service:
            return self.image_service.get_random_image()

        if not self.image_repo:
            self.logger.warning("Image repository not available")
            return None

        try:
            return self.image_repo.get_random_image()
        except Exception as e:
            self.logger.error(f"Error getting random image: {e}")
            return None

    def get_image_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get an image by its URL.

        Args:
            url: Image URL to search for

        Returns:
            Image data or None
        """
        if self.image_service:
            return self.image_service.get_image_by_url(url)

        if not self.image_repo:
            self.logger.warning("Image repository not available")
            return None

        try:
            return self.image_repo.get_image_by_url(url)
        except Exception as e:
            self.logger.error(f"Error getting image by URL: {e}")
            return None
