"""
Repository layer for YServer.

This module provides abstract interfaces and implementations for data access,
following the Repository Pattern to separate storage logic from business logic.
"""

from .base_repository import (
    BaseRepository,
    FollowRepository,
    InterestRepository,
    PostRepository,
    RecommendationRepository,
    UserRepository,
)
from .redis_repository import (
    RedisFollowRepository,
    RedisInterestRepository,
    RedisPostRepository,
    RedisRecommendationRepository,
    RedisUserRepository,
)
from .sql_repository import (
    SQLFollowRepository,
    SQLInterestRepository,
    SQLPostRepository,
    SQLRecommendationRepository,
    SQLUserRepository,
)

__all__ = [
    # Base interfaces
    "BaseRepository",
    "UserRepository",
    "PostRepository",
    "FollowRepository",
    "InterestRepository",
    "RecommendationRepository",
    # SQL implementations
    "SQLUserRepository",
    "SQLPostRepository",
    "SQLFollowRepository",
    "SQLInterestRepository",
    "SQLRecommendationRepository",
    # Redis implementations
    "RedisUserRepository",
    "RedisPostRepository",
    "RedisFollowRepository",
    "RedisInterestRepository",
    "RedisRecommendationRepository",
]
