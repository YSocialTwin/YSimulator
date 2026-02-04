"""
Content Recommendation System for YSimulator Ray Client.

This module provides a recommendation system interface that communicates
with the Ray orchestrator server to fetch recommended posts for agents.

The server implements different recommendation strategies (modes):
    - "random": Random post ordering (default)
    - "ReverseChrono": Reverse chronological ordering (newest first)
    - "ReverseChronoPopularity": Chronological with popularity boost
    - "ReverseChronoFollowers": Prioritizes posts from followed users
    - "ReverseChronoFollowersPopularity": Followers + popularity
    - "ReverseChronoComments": Prioritizes highly commented posts
    - "CommonInterests": Posts with common topic interests
    - "CommonUserInterests": Posts by users with common interests
    - "SimilarUsersReactions": Posts from similar users (by reactions)
    - "SimilarUsersPosts": Posts from similar users (by posting)
    - "CollaborativeUserUser": Collaborative filtering - user similarity
    - "CollaborativeItemItem": Collaborative filtering - item co-occurrence
    - "ContentBasedFeatures": Content-based filtering - feature extraction
    - "ContentBasedVector": Content-based filtering - vector space similarity
"""

import logging

import ray

logger = logging.getLogger(__name__)


class ContentRecSys:
    """
    Content recommendation system for Ray-based simulation.

    This class provides an interface for agents to request recommended
    posts from the orchestrator server using Ray actor calls.

    Attributes:
        mode (str): Recommendation strategy mode
        n_posts (int): Number of posts to recommend
        followers_ratio (float): Ratio of posts from followers vs others
    """

    def __init__(self, mode="ContentRecSys", n_posts=5, followers_ratio=0.6):
        """
        Initialize the content recommendation system.

        Args:
            mode (str, optional): Recommendation mode. Options:
                - "random": Random post ordering (default)
                - "ReverseChrono": Reverse chronological ordering
                - "ReverseChronoPopularity": Chronological with popularity boost
                - "ReverseChronoFollowers": Prioritizes posts from followed users
                - "ReverseChronoFollowersPopularity": Followers + popularity
                - "ReverseChronoComments": Prioritizes highly commented posts
                - "CommonInterests": Posts with common topic interests
                - "CommonUserInterests": Posts by users with common interests
                - "SimilarUsersReactions": Posts from similar users (by reactions)
                - "SimilarUsersPosts": Posts from similar users (by posting)
                - "CollaborativeUserUser": Collaborative filtering - user similarity
                - "CollaborativeItemItem": Collaborative filtering - item co-occurrence
                - "ContentBasedFeatures": Content-based filtering - feature extraction
                - "ContentBasedVector": Content-based filtering - vector space similarity
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            followers_ratio (float, optional): Ratio of posts from followers (0.0-1.0).
                                              Defaults to 0.6.
        """
        self.mode = mode
        self.n_posts = n_posts
        self.followers_ratio = followers_ratio

    def get_recommendations(self, server_handle, agent_id: str, client_id: str = None) -> list:
        """
        Fetch recommended posts from the server for an agent.

        This method queries the server's recommendation system to get posts
        suitable for the specified agent using this system's configured mode.

        Args:
            server_handle: Ray actor handle for the OrchestratorServer
            agent_id (str): UUID of the agent requesting recommendations
            client_id (str, optional): Client identifier for logging purposes

        Returns:
            list: List of post UUIDs recommended for the agent
        """
        try:
            post_ids = ray.get(
                server_handle.get_recommended_posts.remote(
                    agent_id=agent_id,
                    mode=self.mode,
                    limit=self.n_posts,
                    followers_ratio=self.followers_ratio,
                    client_id=client_id,
                )
            )
            return post_ids if post_ids else []
        except Exception as e:
            logger.error(f"Error getting recommendations for agent {agent_id}: {e}")
            return []


class ReverseChrono(ContentRecSys):
    """
    Reverse chronological feed (newest posts first).

    This recommendation system orders posts by recency without any
    personalization or filtering.
    """

    def __init__(self, n_posts=5):
        """
        Initialize reverse chronological recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ReverseChrono", n_posts=n_posts)


class ReverseChronoPopularity(ContentRecSys):
    """
    Reverse chronological feed with popularity boost.

    Orders posts by recency and reaction count for more engaging content.
    """

    def __init__(self, n_posts=5):
        """
        Initialize reverse chronological with popularity recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ReverseChronoPopularity", n_posts=n_posts)


class ReverseChronoFollowers(ContentRecSys):
    """
    Chronological feed prioritizing posts from followed users.

    Shows a mix of posts from followed users and the general network.
    """

    def __init__(self, n_posts=5, followers_ratio=0.6):
        """
        Initialize followers-prioritizing recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(
            mode="ReverseChronoFollowers", n_posts=n_posts, followers_ratio=followers_ratio
        )


class ReverseChronoFollowersPopularity(ContentRecSys):
    """
    Followers feed with popularity boost.

    Prioritizes popular posts from followed users.
    """

    def __init__(self, n_posts=5, followers_ratio=0.6):
        """
        Initialize followers + popularity recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(
            mode="ReverseChronoFollowersPopularity",
            n_posts=n_posts,
            followers_ratio=followers_ratio,
        )


class ReverseChronoComments(ContentRecSys):
    """
    Feed prioritizing posts with active discussions.

    Surfaces posts with more comments to encourage engagement.
    """

    def __init__(self, n_posts=5):
        """
        Initialize comment-prioritizing recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ReverseChronoComments", n_posts=n_posts)


class RandomOrder(ContentRecSys):
    """
    Random post ordering recommendation system.

    This system recommends posts in random order to provide diverse content
    without recency or popularity bias.
    """

    def __init__(self, n_posts=5):
        """
        Initialize random ordering recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ContentRecSys", n_posts=n_posts)


class CommonInterests(ContentRecSys):
    """
    Recommendation based on common topic interests.

    Recommends posts that match topics the agent is interested in.
    """

    def __init__(self, n_posts=5, followers_ratio=0.6):
        """
        Initialize common interests recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(mode="CommonInterests", n_posts=n_posts, followers_ratio=followers_ratio)


class CommonUserInterests(ContentRecSys):
    """
    Recommendation based on users with common interests.

    Recommends posts that were interacted with by users who share interests with the agent.
    """

    def __init__(self, n_posts=5, followers_ratio=0.6):
        """
        Initialize common user interests recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(
            mode="CommonUserInterests", n_posts=n_posts, followers_ratio=followers_ratio
        )


class SimilarUsersReact(ContentRecSys):
    """
    Recommendation based on similar users' reactions.

    Recommends posts that similar users (based on demographics/personality) have liked.
    """

    def __init__(self, n_posts=5):
        """
        Initialize similar users reactions recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="SimilarUsersReactions", n_posts=n_posts)


class SimilarUsersPosts(ContentRecSys):
    """
    Recommendation based on similar users' posts.

    Recommends posts created by users similar to the agent (based on demographics/personality).
    """

    def __init__(self, n_posts=5):
        """
        Initialize similar users posts recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="SimilarUsersPosts", n_posts=n_posts)


class CollaborativeUserUser(ContentRecSys):
    """
    Collaborative Filtering - User-User.

    Finds users with a high overlap in liked posts and recommends posts they liked.
    Uses behavioral similarity (actual likes) to find similar users.
    """

    def __init__(self, n_posts=5):
        """
        Initialize collaborative user-user filtering recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="CollaborativeUserUser", n_posts=n_posts)


class CollaborativeItemItem(ContentRecSys):
    """
    Collaborative Filtering - Item-Item.

    Finds posts that are often liked together by the same groups of users.
    Uses co-occurrence patterns to recommend related content.
    """

    def __init__(self, n_posts=5):
        """
        Initialize collaborative item-item filtering recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="CollaborativeItemItem", n_posts=n_posts)


class ContentBasedFeatures(ContentRecSys):
    """
    Content-Based Filtering - Feature Extraction.

    Analyzes attributes of content the user has interacted with (topics, hashtags)
    and recommends posts with similar features. Learns preferences from behavior.
    """

    def __init__(self, n_posts=5):
        """
        Initialize content-based feature extraction recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ContentBasedFeatures", n_posts=n_posts)


class ContentBasedVector(ContentRecSys):
    """
    Content-Based Filtering - Vector Space Similarity.

    Recommends posts mathematically close to the user's "preference vector"
    using weighted topic distributions. Uses frequency-based similarity scoring.
    """

    def __init__(self, n_posts=5):
        """
        Initialize content-based vector space recommendation system.

        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
        """
        super().__init__(mode="ContentBasedVector", n_posts=n_posts)
