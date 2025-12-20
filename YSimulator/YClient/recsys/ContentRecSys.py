"""
Content Recommendation System for YSimulator Ray Client.

This module provides a recommendation system interface that communicates
with the Ray orchestrator server to fetch recommended posts for agents.

The server implements different recommendation strategies (modes):
    - "random": Random post ordering (default)
    - "rchrono": Reverse chronological ordering (newest first)
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
    """
    
    def __init__(self, mode="random", n_posts=5, visibility_rounds=36):
        """
        Initialize the content recommendation system.
        
        Args:
            mode (str, optional): Recommendation mode. Options:
                - "random": Random post ordering (default)
                - "rchrono": Reverse chronological ordering
            n_posts (int, optional): Number of posts to recommend. Defaults to 5.
            visibility_rounds (int, optional): Number of time slots posts remain visible.
                                               Defaults to 36.
        """
        self.mode = mode
        self.n_posts = n_posts
        self.visibility_rounds = visibility_rounds
    
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
                    visibility_rounds=self.visibility_rounds
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
