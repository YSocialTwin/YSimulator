"""
Recommendation service layer for YSimulator.

Provides content and follow recommendation engines with pluggable strategies.
"""

from YSimulator.YServer.recommendation.content_recommender import ContentRecommender
from YSimulator.YServer.recommendation.follow_recommender import FollowRecommender

__all__ = [
    "ContentRecommender",
    "FollowRecommender",
]
