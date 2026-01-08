"""
Response Parser for validating and processing LLM responses.

This module provides validation and sanitization for LLM responses,
ensuring they meet expected formats and handling malformed responses gracefully.
"""

import logging
from typing import Any, Dict, List, Optional, Union


class ResponseParser:
    """
    Validates and processes LLM responses.
    
    Handles:
    - Type validation
    - Format checking
    - Sanitization
    - Default value provision for malformed responses
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the ResponseParser.
        
        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def parse_text_response(
        self, response: Any, default: str = "", max_length: Optional[int] = None
    ) -> str:
        """
        Parse a text response from LLM.
        
        Args:
            response: Response from LLM (should be string)
            default: Default value if response is invalid
            max_length: Optional maximum length (truncate if exceeded)
            
        Returns:
            Validated text string
        """
        if response is None:
            self.logger.warning("LLM returned None, using default")
            return default
        
        # Convert to string
        text = str(response).strip()
        
        if not text:
            self.logger.warning("LLM returned empty text, using default")
            return default
        
        # Truncate if needed
        if max_length and len(text) > max_length:
            self.logger.warning(f"Text exceeds max length ({len(text)} > {max_length}), truncating")
            text = text[:max_length]
        
        return text
    
    def parse_boolean_response(self, response: Any, default: bool = False) -> bool:
        """
        Parse a boolean response from LLM.
        
        Args:
            response: Response from LLM (should be bool or string)
            default: Default value if response is invalid
            
        Returns:
            Boolean value
        """
        if response is None:
            self.logger.warning("LLM returned None for boolean, using default")
            return default
        
        # Handle boolean
        if isinstance(response, bool):
            return response
        
        # Handle string representation
        if isinstance(response, str):
            response_lower = response.lower().strip()
            if response_lower in ("true", "yes", "1", "follow"):
                return True
            elif response_lower in ("false", "no", "0", "unfollow", "ignore"):
                return False
        
        # Handle numeric
        if isinstance(response, (int, float)):
            return bool(response)
        
        self.logger.warning(f"Could not parse boolean from: {response}, using default")
        return default
    
    def parse_list_response(
        self, response: Any, default: Optional[List] = None, expected_type: Optional[type] = None
    ) -> List:
        """
        Parse a list response from LLM.
        
        Args:
            response: Response from LLM (should be list)
            default: Default value if response is invalid
            expected_type: Optional type to validate list elements
            
        Returns:
            Validated list
        """
        if default is None:
            default = []
        
        if response is None:
            self.logger.warning("LLM returned None for list, using default")
            return default
        
        # Ensure it's a list
        if not isinstance(response, list):
            self.logger.warning(f"Response is not a list: {type(response)}, using default")
            return default
        
        # Validate element types if specified
        if expected_type:
            validated = []
            for item in response:
                if isinstance(item, expected_type):
                    validated.append(item)
                else:
                    self.logger.warning(
                        f"List element has wrong type: {type(item)} (expected {expected_type})"
                    )
            return validated
        
        return response
    
    def parse_dict_response(
        self, response: Any, default: Optional[Dict] = None, required_keys: Optional[List[str]] = None
    ) -> Dict:
        """
        Parse a dictionary response from LLM.
        
        Args:
            response: Response from LLM (should be dict)
            default: Default value if response is invalid
            required_keys: Optional list of required keys
            
        Returns:
            Validated dictionary
        """
        if default is None:
            default = {}
        
        if response is None:
            self.logger.warning("LLM returned None for dict, using default")
            return default
        
        # Ensure it's a dict
        if not isinstance(response, dict):
            self.logger.warning(f"Response is not a dict: {type(response)}, using default")
            return default
        
        # Check required keys
        if required_keys:
            missing_keys = [key for key in required_keys if key not in response]
            if missing_keys:
                self.logger.warning(f"Dict missing required keys: {missing_keys}")
                # Add missing keys with None values
                for key in missing_keys:
                    response[key] = None
        
        return response
    
    def parse_emotion_response(self, response: Any) -> Optional[str]:
        """
        Parse an emotion response from LLM.
        
        Validates that the emotion is one of the expected GoEmotions categories.
        
        Args:
            response: Response from LLM (should be emotion string)
            
        Returns:
            Validated emotion string or None if invalid
        """
        # GoEmotions taxonomy (28 emotions + neutral)
        valid_emotions = {
            "admiration",
            "amusement",
            "anger",
            "annoyance",
            "approval",
            "caring",
            "confusion",
            "curiosity",
            "desire",
            "disappointment",
            "disapproval",
            "disgust",
            "embarrassment",
            "excitement",
            "fear",
            "gratitude",
            "grief",
            "joy",
            "love",
            "nervousness",
            "neutral",
            "optimism",
            "pride",
            "realization",
            "relief",
            "remorse",
            "sadness",
            "surprise",
        }
        
        if response is None:
            return None
        
        emotion = str(response).lower().strip()
        
        if emotion in valid_emotions:
            return emotion
        
        self.logger.warning(f"Invalid emotion: {response}")
        return None
    
    def sanitize_text(self, text: str, remove_html: bool = True) -> str:
        """
        Sanitize text by removing unwanted characters.
        
        Args:
            text: Text to sanitize
            remove_html: Whether to remove HTML tags
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Remove HTML tags if requested
        if remove_html:
            import re
            text = re.sub(r"<[^>]+>", "", text)
        
        # Remove excessive whitespace
        text = " ".join(text.split())
        
        return text.strip()
