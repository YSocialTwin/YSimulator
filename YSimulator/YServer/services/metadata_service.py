"""
Metadata service for post metadata operations (emotions, sentiment, toxicity, hashtags).

This service encapsulates all post metadata-related business operations.
"""

import logging
from typing import Any, Dict, List, Optional

from YSimulator.YServer.repositories.base_repository import PostRepository


class MetadataService:
    """Service for post metadata business logic."""
    
    def __init__(
        self,
        post_repository: PostRepository,
        logger: logging.Logger = None,
    ):
        """
        Initialize metadata service.
        
        Args:
            post_repository: Repository for post metadata operations
            logger: Logger instance
        """
        self.post_repo = post_repository
        self.logger = logger or logging.getLogger(__name__)
    
    # Emotion operations
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """
        Add emotion to a post.
        
        Args:
            post_id: Post ID
            emotion_id: Emotion ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_post_emotion(post_id, emotion_id)
        except Exception as e:
            self.logger.error(f"Error adding post emotion: {e}")
            return False
    
    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """
        Get emotion ID by name.
        
        Args:
            emotion_name: Emotion name
            
        Returns:
            Emotion ID or None
        """
        try:
            return self.post_repo.get_emotion_by_name(emotion_name)
        except Exception as e:
            self.logger.error(f"Error getting emotion by name: {e}")
            return None
    
    def initialize_emotions_table(self):
        """Initialize emotions table with standard emotions."""
        try:
            return self.post_repo.initialize_emotions_table()
        except Exception as e:
            self.logger.error(f"Error initializing emotions table: {e}")
            return None
    
    # Sentiment operations
    def add_post_sentiment(self, sentiment_data: Dict[str, Any]) -> bool:
        """
        Add sentiment data to a post.
        
        Args:
            sentiment_data: Dictionary containing sentiment scores and metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_post_sentiment_full(sentiment_data)
        except Exception as e:
            self.logger.error(f"Error adding post sentiment: {e}")
            return False
    
    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """
        Get sentiment score for a post.
        
        Args:
            post_id: Post ID
            
        Returns:
            Sentiment score or None
        """
        try:
            return self.post_repo.get_post_sentiment(post_id)
        except Exception as e:
            self.logger.error(f"Error getting post sentiment: {e}")
            return None
    
    # Toxicity operations
    def add_post_toxicity(self, toxicity_data: Dict[str, Any]) -> bool:
        """
        Add toxicity data to a post.
        
        Args:
            toxicity_data: Dictionary containing toxicity scores and metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_post_toxicity_full(toxicity_data)
        except Exception as e:
            self.logger.error(f"Error adding post toxicity: {e}")
            return False
    
    # Hashtag operations
    def add_or_get_hashtag(self, hashtag: str) -> Optional[str]:
        """
        Add or get hashtag ID.
        
        Args:
            hashtag: Hashtag text
            
        Returns:
            Hashtag ID or None
        """
        try:
            return self.post_repo.add_or_get_hashtag(hashtag)
        except Exception as e:
            self.logger.error(f"Error adding/getting hashtag: {e}")
            return None
    
    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """
        Add hashtag to a post.
        
        Args:
            post_id: Post ID
            hashtag_id: Hashtag ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_post_hashtag(post_id, hashtag_id)
        except Exception as e:
            self.logger.error(f"Error adding post hashtag: {e}")
            return False
