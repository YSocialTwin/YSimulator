"""
Follow Recommendation System for YSimulator Ray Client.

This module provides a follow recommendation system interface that communicates
with the Ray orchestrator server to fetch follow suggestions for agents.

The server implements different recommendation strategies (modes):
    - "FollowRecSys": Random user suggestions (default)
    - "CommonNeighbors": Users with mutual connections
    - "Jaccard": Jaccard coefficient-based similarity
    - "AdamicAdar": Adamic/Adar index for link prediction
    - "PreferentialAttachment": Rich-get-richer recommendation
    - "ResourceAllocation": Resource allocation index
    - "CosineSimilarity": Cosine similarity on profile vectors
    - "CoEngagement": Users who interact with same content
    - "RandomWalkRestart": Random walk with restart
    - "ReactionsOnContent": Users who react to agent's content
    - "TwoHopEgoSampling": 2-hop ego sampling with community detection
"""

import logging

import ray

logger = logging.getLogger(__name__)


class FollowRecSysRay:
    """
    Follow recommendation system for Ray-based simulation.

    This class provides an interface for agents to request follow suggestions
    from the orchestrator server using Ray actor calls.

    Attributes:
        mode (str): Recommendation strategy mode
        n_neighbors (int): Number of users to suggest
        leaning_bias (int): Political leaning bias factor
    """

    def __init__(self, mode="FollowRecSys", n_neighbors=10, leaning_bias=1):
        """
        Initialize the follow recommendation system.

        Args:
            mode (str, optional): Recommendation mode. Options:
                - "FollowRecSys": Random user suggestions (default)
                - "CommonNeighbors": Users with mutual connections
                - "Jaccard": Jaccard coefficient-based similarity
                - "AdamicAdar": Adamic/Adar index for link prediction
                - "PreferentialAttachment": Rich-get-richer recommendation
                - "ResourceAllocation": Resource allocation index
                - "CosineSimilarity": Cosine similarity on profile vectors
                - "CoEngagement": Users who interact with same content
                - "RandomWalkRestart": Random walk with restart
                - "ReactionsOnContent": Users who react to agent's content
                - "TwoHopEgoSampling": 2-hop ego sampling with community detection
            n_neighbors (int, optional): Number of users to suggest. Defaults to 10.
            leaning_bias (int, optional): Political leaning bias factor.
                                         1 = no bias, higher values increase homophily.
                                         Defaults to 1.
        """
        self.mode = mode
        self.n_neighbors = n_neighbors
        self.leaning_bias = leaning_bias

    def get_follow_suggestions(self, server_handle, agent_id: str, client_id: str = None) -> list:
        """
        Fetch follow suggestions from the server for an agent.

        This method queries the server's follow recommendation system to get users
        suggested for the specified agent using this system's configured mode.

        Args:
            server_handle: Ray actor handle for the OrchestratorServer
            agent_id (str): UUID of the agent requesting follow suggestions
            client_id (str, optional): Client identifier for logging purposes

        Returns:
            list: List of user UUIDs recommended for the agent to follow
        """
        try:
            user_ids = ray.get(
                server_handle.get_follow_suggestions.remote(
                    agent_id=agent_id,
                    mode=self.mode,
                    n_neighbors=self.n_neighbors,
                    leaning_bias=self.leaning_bias,
                    client_id=client_id,
                )
            )
            return user_ids if user_ids else []
        except Exception as e:
            logger.error(f"Error fetching follow suggestions for agent {agent_id}: {e}")
            return []


class RandomFollowRecSys(FollowRecSysRay):
    """Random follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="FollowRecSys", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class CommonNeighborsFollowRecSys(FollowRecSysRay):
    """Common neighbors follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="CommonNeighbors", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class JaccardFollowRecSys(FollowRecSysRay):
    """Jaccard similarity follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="Jaccard", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class AdamicAdarFollowRecSys(FollowRecSysRay):
    """Adamic/Adar follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="AdamicAdar", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class PreferentialAttachmentFollowRecSys(FollowRecSysRay):
    """Preferential attachment follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="PreferentialAttachment", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class ResourceAllocationFollowRecSys(FollowRecSysRay):
    """Resource allocation index follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="ResourceAllocation", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class CosineSimilarityFollowRecSys(FollowRecSysRay):
    """Cosine similarity on profile vectors follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="CosineSimilarity", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class CoEngagementFollowRecSys(FollowRecSysRay):
    """Co-engagement based follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="CoEngagement", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class RandomWalkRestartFollowRecSys(FollowRecSysRay):
    """Random walk with restart follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="RandomWalkRestart", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class ReactionsOnContentFollowRecSys(FollowRecSysRay):
    """Reactions on agent content follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="ReactionsOnContent", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class TwoHopEgoSamplingFollowRecSys(FollowRecSysRay):
    """2-hop ego sampling with community detection follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="TwoHopEgoSampling", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )
