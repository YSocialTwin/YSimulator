"""
Repository layer for YServer.

This module provides abstract interfaces and implementations for data access,
following the Repository Pattern to separate storage logic from business logic.
"""

from .base_repository import (
    BaseRepository,
    UserRepository,
    PostRepository,
    FollowRepository,
    InterestRepository,
    RecommendationRepository,
)
from .sql_repository import (
    SQLUserRepository,
    SQLPostRepository,
    SQLFollowRepository,
    SQLInterestRepository,
    SQLRecommendationRepository,
)
from .redis_repository import (
    RedisUserRepository,
    RedisPostRepository,
    RedisFollowRepository,
    RedisInterestRepository,
    RedisRecommendationRepository,
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
