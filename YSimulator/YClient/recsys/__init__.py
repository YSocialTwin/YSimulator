"""
Recommendation Systems Module

This module provides recommendation system implementations for the Y social network.
It includes content-based recommendation for posts and follow recommendation for users
using Ray actor communication.

Content Recommendation Exports:
    - ContentRecSys: Base content recommendation system
    - ReverseChrono: Reverse chronological ordering
    - ReverseChronoPopularity: Chronological with popularity boost
    - ReverseChronoFollowers: Prioritizes posts from followed users
    - ReverseChronoFollowersPopularity: Followers + popularity
    - ReverseChronoComments: Prioritizes highly commented posts
    - CommonInterests: Posts with common topic interests
    - CommonUserInterests: Posts by users with common interests
    - SimilarUsersReact: Posts from similar users (by reactions)
    - SimilarUsersPosts: Posts from similar users (by posting)
    - CollaborativeUserUser: Collaborative filtering based on user similarity
    - CollaborativeItemItem: Collaborative filtering based on item co-occurrence
    - ContentBasedFeatures: Content-based filtering using feature extraction
    - ContentBasedVector: Content-based filtering using vector space similarity
    - HybridLinearRanker: Two-stage hybrid system with multi-signal ranking
    - RandomOrder: Random post ordering

Follow Recommendation Exports:
    - FollowRecSysRay: Base follow recommendation system
    - RandomFollowRecSys: Random follow suggestions
    - CommonNeighborsFollowRecSys: Common neighbors (friend-of-friend)
    - JaccardFollowRecSys: Jaccard similarity coefficient
    - AdamicAdarFollowRecSys: Adamic/Adar index
    - PreferentialAttachmentFollowRecSys: Popularity-based (rich-get-richer)
    - ActivityFollowRecSys: Recently active users by post count
    - ResourceAllocationFollowRecSys: Resource allocation index
    - CosineSimilarityFollowRecSys: Cosine similarity on profile vectors
    - CoEngagementFollowRecSys: Co-engagement based recommendations
    - RandomWalkRestartFollowRecSys: Random walk with restart
    - ReactionsOnContentFollowRecSys: Users who react to agent's content
    - TwoHopEgoSamplingFollowRecSys: 2-hop ego sampling with community detection
"""

from .ContentRecSys import (
    CollaborativeItemItem,
    CollaborativeUserUser,
    CommonInterests,
    CommonUserInterests,
    ContentBasedFeatures,
    ContentBasedVector,
    ContentRecSys,
    HybridLinearRanker,
    RandomOrder,
    ReverseChrono,
    ReverseChronoComments,
    ReverseChronoFollowers,
    ReverseChronoFollowersPopularity,
    ReverseChronoPopularity,
    SimilarUsersPosts,
    SimilarUsersReact,
)
from .FollowRecSysRay import (
    ActivityFollowRecSys,
    AdamicAdarFollowRecSys,
    CoEngagementFollowRecSys,
    CommonNeighborsFollowRecSys,
    CosineSimilarityFollowRecSys,
    FollowRecSysRay,
    JaccardFollowRecSys,
    PreferentialAttachmentFollowRecSys,
    RandomFollowRecSys,
    RandomWalkRestartFollowRecSys,
    ReactionsOnContentFollowRecSys,
    ResourceAllocationFollowRecSys,
    TwoHopEgoSamplingFollowRecSys,
)

__all__ = [
    # Content recommendation systems
    "ContentRecSys",
    "ReverseChrono",
    "ReverseChronoPopularity",
    "ReverseChronoFollowers",
    "ReverseChronoFollowersPopularity",
    "ReverseChronoComments",
    "CommonInterests",
    "CommonUserInterests",
    "SimilarUsersReact",
    "SimilarUsersPosts",
    "CollaborativeUserUser",
    "CollaborativeItemItem",
    "ContentBasedFeatures",
    "ContentBasedVector",
    "HybridLinearRanker",
    "RandomOrder",
    # Follow recommendation systems
    "FollowRecSysRay",
    "RandomFollowRecSys",
    "CommonNeighborsFollowRecSys",
    "JaccardFollowRecSys",
    "AdamicAdarFollowRecSys",
    "PreferentialAttachmentFollowRecSys",
    "ActivityFollowRecSys",
    "ResourceAllocationFollowRecSys",
    "CosineSimilarityFollowRecSys",
    "CoEngagementFollowRecSys",
    "RandomWalkRestartFollowRecSys",
    "ReactionsOnContentFollowRecSys",
    "TwoHopEgoSamplingFollowRecSys",
]
