"""
Image service for business logic related to image management.

This service encapsulates all image-related business operations.
"""

import logging
from typing import Any, Dict, Optional

from YSimulator.YServer.repositories.base_repository import ImageRepository


class ImageService:
    """Service for image management business logic."""
    
    def __init__(
        self,
        image_repository: ImageRepository,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize image service.
        
        Args:
            image_repository: Repository for image data access
            logger: Logger instance
        """
        self.image_repo = image_repository
        self.logger = logger or logging.getLogger(__name__)
    
    def add_image(self, image_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a new image.
        
        Args:
            image_data: Image information dictionary containing:
                - url: Image URL (required)
                - description: Image description (optional)
                - id: Image ID (optional, will be generated if not provided)
            
        Returns:
            Image ID if successful, None otherwise
        """
        try:
            return self.image_repo.add_image(image_data)
        except Exception as e:
            self.logger.error(f"Error in image service add_image: {e}")
            return None
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """
        Get a random image from the repository.
        
        Returns:
            Image data dictionary or None if no images available
        """
        try:
            return self.image_repo.get_random_image()
        except Exception as e:
            self.logger.error(f"Error in image service get_random_image: {e}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if the image service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.image_repo.health_check()
        except Exception as e:
            self.logger.error(f"Error in image service health_check: {e}")
            return False
