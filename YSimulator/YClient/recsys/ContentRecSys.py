"""
Content Recommendation System for YSimulator Ray Client.

This module provides a recommendation system interface that communicates
with the Ray orchestrator server to fetch recommended posts for agents.

The server implements different recommendation strategies (modes):
    - "random": Random post ordering (default)
    - "rchrono": Reverse chronological ordering (newest first)
    - "rchrono_popularity": Chronological with popularity boost
    - "rchrono_followers": Prioritizes posts from followed users
    - "rchrono_followers_popularity": Followers + popularity
    - "rchrono_comments": Prioritizes highly commented posts
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
        visibility_rounds (int): How many time slots back to look for posts
        followers_ratio (float): Ratio of posts from followers vs others
    """
    
    def __init__(self, mode="random", n_posts=5, visibility_rounds=36, followers_ratio=0.6):
        """
        Initialize the content recommendation system.
        
        Args:
            mode (str, optional): Recommendation mode. Options:
                - "random": Random post ordering (default)
                - "rchrono": Reverse chronological ordering
                - "rchrono_popularity": Chronological with popularity boost
                - "rchrono_followers": Prioritizes posts from followed users
                - "rchrono_followers_popularity": Followers + popularity
                - "rchrono_comments": Prioritizes highly commented posts
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
            followers_ratio (float, optional): Ratio of posts from followers (0.0-1.0).
                                              Defaults to 0.6.
        """
        self.mode = mode
        self.n_posts = n_posts
        self.visibility_rounds = visibility_rounds
        self.followers_ratio = followers_ratio
    
    def get_recommendations(self, server_handle, agent_id: str) -> list:
        """
        Fetch recommended posts from the server for an agent.
        
        This method queries the server's recommendation system to get posts
        suitable for the specified agent using this system's configured mode.
        
        Args:
            server_handle: Ray actor handle for the OrchestratorServer
            agent_id (str): UUID of the agent requesting recommendations
        
        Returns:
            list: List of post UUIDs recommended for the agent
        """
        try:
            post_ids = ray.get(
                server_handle.get_recommended_posts.remote(
                    agent_id=agent_id,
                    mode=self.mode,
                    limit=self.n_posts,
                    visibility_rounds=self.visibility_rounds,
                    followers_ratio=self.followers_ratio
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
    
    def __init__(self, n_posts=5, visibility_rounds=36):
        """
        Initialize reverse chronological recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
        """
        super().__init__(mode="rchrono", n_posts=n_posts, visibility_rounds=visibility_rounds)


class ReverseChronoPopularity(ContentRecSys):
    """
    Reverse chronological feed with popularity boost.
    
    Orders posts by recency and reaction count for more engaging content.
    """
    
    def __init__(self, n_posts=5, visibility_rounds=36):
        """
        Initialize reverse chronological with popularity recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
        """
        super().__init__(mode="rchrono_popularity", n_posts=n_posts, visibility_rounds=visibility_rounds)


class ReverseChronoFollowers(ContentRecSys):
    """
    Chronological feed prioritizing posts from followed users.
    
    Shows a mix of posts from followed users and the general network.
    """
    
    def __init__(self, n_posts=5, visibility_rounds=36, followers_ratio=0.6):
        """
        Initialize followers-prioritizing recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(mode="rchrono_followers", n_posts=n_posts, 
                        visibility_rounds=visibility_rounds, followers_ratio=followers_ratio)


class ReverseChronoFollowersPopularity(ContentRecSys):
    """
    Followers feed with popularity boost.
    
    Prioritizes popular posts from followed users.
    """
    
    def __init__(self, n_posts=5, visibility_rounds=36, followers_ratio=0.6):
        """
        Initialize followers + popularity recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
            followers_ratio (float, optional): Proportion of posts from followed users.
                                              Defaults to 0.6.
        """
        super().__init__(mode="rchrono_followers_popularity", n_posts=n_posts,
                        visibility_rounds=visibility_rounds, followers_ratio=followers_ratio)


class ReverseChronoComments(ContentRecSys):
    """
    Feed prioritizing posts with active discussions.
    
    Surfaces posts with more comments to encourage engagement.
    """
    
    def __init__(self, n_posts=5, visibility_rounds=36):
        """
        Initialize comment-prioritizing recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
        """
        super().__init__(mode="rchrono_comments", n_posts=n_posts, visibility_rounds=visibility_rounds)


class RandomOrder(ContentRecSys):
    """
    Random post ordering recommendation system.
    
    This system recommends posts in random order to provide diverse content
    without recency or popularity bias.
    """
    
    def __init__(self, n_posts=5, visibility_rounds=36):
        """
        Initialize random ordering recommendation system.
        
        Args:
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
        """
        super().__init__(mode="random", n_posts=n_posts, visibility_rounds=visibility_rounds)
