"""
Retry Handler for LLM service error handling and retry logic.

This module provides retry logic with exponential backoff for LLM calls,
handling transient errors, rate limits, and service unavailability.
"""

import logging
import time
from typing import Any, Callable, Optional

import ray


class RetryHandler:
    """
    Handles retry logic for LLM service calls.
    
    Implements:
    - Exponential backoff
    - Maximum retry attempts
    - Rate limit handling
    - Circuit breaker pattern (future enhancement)
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the RetryHandler.
        
        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before first retry
            backoff_factor: Multiplier for exponential backoff
            max_delay: Maximum delay between retries
            logger: Logger instance for debugging
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.logger = logger or logging.getLogger(__name__)
    
    def retry_with_backoff(
        self, func: Callable, *args, error_message: str = "LLM call", **kwargs
    ) -> Any:
        """
        Execute a function with retry and exponential backoff.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            error_message: Description for logging
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func if successful
            
        Raises:
            Exception: If all retries exhausted
        """
        delay = self.initial_delay
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    self.logger.warning(
                        f"{error_message} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    self.logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    delay = min(delay * self.backoff_factor, self.max_delay)
                else:
                    self.logger.error(
                        f"{error_message} failed after {self.max_retries + 1} attempts: {e}"
                    )
        
        raise last_exception
    
    def retry_ray_get(
        self, futures: list, error_message: str = "Ray get"
    ) -> list:
        """
        Execute ray.get with retry logic.
        
        Useful for handling transient Ray errors.
        
        Args:
            futures: List of Ray ObjectRef futures
            error_message: Description for logging
            
        Returns:
            List of results from ray.get
        """
        return self.retry_with_backoff(
            ray.get, futures, error_message=error_message
        )
    
    def is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Args:
            error: Exception to check
            
        Returns:
            True if error is retryable, False otherwise
        """
        # Common retryable errors
        retryable_error_types = [
            ConnectionError,
            TimeoutError,
        ]
        
        # Add Ray-specific errors if available and valid
        try:
            if hasattr(ray, 'exceptions') and hasattr(ray.exceptions, 'RayTaskError'):
                ray_error = ray.exceptions.RayTaskError
                # Only add if it's actually a type (not a mock)
                if isinstance(ray_error, type):
                    retryable_error_types.append(ray_error)
        except (AttributeError, ImportError, TypeError):
            pass
        
        # Check error type
        try:
            if isinstance(error, tuple(retryable_error_types)):
                return True
        except TypeError:
            # If tuple conversion fails, check individually
            for error_type in retryable_error_types:
                try:
                    if isinstance(error, error_type):
                        return True
                except TypeError:
                    continue
        
        # Check error message for rate limits
        error_message = str(error).lower()
        if any(
            keyword in error_message
            for keyword in ["rate limit", "timeout", "connection", "unavailable"]
        ):
            return True
        
        return False
    
    def retry_if_retryable(
        self, func: Callable, *args, **kwargs
    ) -> Any:
        """
        Retry function only if error is retryable.
        
        Non-retryable errors are raised immediately without retry.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from func if successful
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if self.is_retryable_error(e):
                self.logger.info(f"Retryable error detected: {e}")
                return self.retry_with_backoff(func, *args, **kwargs)
            else:
                self.logger.error(f"Non-retryable error: {e}")
                raise
