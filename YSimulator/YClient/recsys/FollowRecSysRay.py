"""
Follow Recommendation System for YSimulator Ray Client.

This module provides a follow recommendation system interface that communicates
with the Ray orchestrator server to fetch follow suggestions for agents.

The server implements different recommendation strategies (modes):
    - "random": Random user suggestions (default)
    - "common_neighbors": Users with mutual connections
    - "jaccard": Jaccard coefficient-based similarity
    - "adamic_adar": Adamic/Adar index for link prediction
    - "preferential_attachment": Rich-get-richer recommendation
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

    def __init__(self, mode="random", n_neighbors=10, leaning_bias=1):
        """
        Initialize the follow recommendation system.

        Args:
            mode (str, optional): Recommendation mode. Options:
                - "random": Random user suggestions (default)
                - "common_neighbors": Users with mutual connections
                - "jaccard": Jaccard coefficient-based similarity
                - "adamic_adar": Adamic/Adar index for link prediction
                - "preferential_attachment": Rich-get-richer recommendation
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
        super().__init__(mode="random", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class CommonNeighborsFollowRecSys(FollowRecSysRay):
    """Common neighbors follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="common_neighbors", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )


class JaccardFollowRecSys(FollowRecSysRay):
    """Jaccard similarity follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="jaccard", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class AdamicAdarFollowRecSys(FollowRecSysRay):
    """Adamic/Adar follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(mode="adamic_adar", n_neighbors=n_neighbors, leaning_bias=leaning_bias)


class PreferentialAttachmentFollowRecSys(FollowRecSysRay):
    """Preferential attachment follow recommendation system."""

    def __init__(self, n_neighbors=10, leaning_bias=1):
        super().__init__(
            mode="preferential_attachment", n_neighbors=n_neighbors, leaning_bias=leaning_bias
        )
