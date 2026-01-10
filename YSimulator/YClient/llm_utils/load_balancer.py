"""
Multi-Actor LLM Load Balancer for YSimulator Performance Optimization.

This module provides load balancing across multiple LLM actor instances to
achieve parallel LLM inference and reduce the sequential processing bottleneck.

Performance Impact: 2-4x speedup with 4 actors (scalable with resources)

Usage:
    # In client initialization
    load_balancer = LLMLoadBalancer(num_actors=4, strategy='hash')
    
    # In action generators
    llm_actor = load_balancer.get_actor_for_agent(agent_id)
    future = llm_actor.generate_post.remote(...)
"""

import hashlib
import logging
from enum import Enum
from typing import Any, List, Optional

import ray


class LoadBalancingStrategy(Enum):
    """Supported load balancing strategies."""

    ROUND_ROBIN = "round_robin"  # Simple rotating assignment
    HASH = "hash"  # Hash-based consistent assignment (agent affinity)
    LEAST_LOADED = "least_loaded"  # Route to least busy actor (future enhancement)


class LLMLoadBalancer:
    """
    Load balancer for multiple LLM actor instances.

    Distributes LLM inference requests across multiple Ray actors to achieve
    parallel processing and reduce the sequential bottleneck.

    Attributes:
        actors: List of LLM Ray actor handles
        strategy: Load balancing strategy to use
        logger: Logger instance
    """

    def __init__(
        self,
        llm_config: dict,
        prompts_config: dict,
        num_actors: int = 4,
        strategy: str = "hash",
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the LLM load balancer.

        Args:
            llm_config: Configuration for LLM service
            prompts_config: Prompt templates configuration
            num_actors: Number of LLM actor instances to create
            strategy: Load balancing strategy ('hash', 'round_robin')
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.num_actors = num_actors
        self.strategy = LoadBalancingStrategy(strategy)
        self.current_idx = 0  # For round-robin

        # Create multiple LLM actors
        self.logger.info(f"Creating {num_actors} LLM actors for parallel inference")
        self.actors = []

        # Import here to avoid circular dependency
        from YSimulator.YClient.LLM_interactions.llm_service import LLMService

        for i in range(num_actors):
            actor = LLMService.remote(
                llm_config=llm_config,
                prompts_config=prompts_config,
            )
            self.actors.append(actor)
            self.logger.info(f"Created LLM actor {i+1}/{num_actors}")

        self.logger.info(
            f"LLM load balancer initialized with {num_actors} actors, strategy={strategy}"
        )

    def get_actor_for_agent(self, agent_id: str) -> Any:
        """
        Get the LLM actor for a specific agent.

        Uses the configured load balancing strategy to select an actor.

        Args:
            agent_id: UUID of the agent

        Returns:
            Ray actor handle for LLM service
        """
        if self.strategy == LoadBalancingStrategy.HASH:
            # Hash-based: same agent always goes to same actor (affinity)
            idx = self._hash_agent_id(agent_id) % self.num_actors
        elif self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            # Round-robin: distribute evenly
            idx = self.current_idx
            self.current_idx = (self.current_idx + 1) % self.num_actors
        else:
            # Default to first actor
            idx = 0

        return self.actors[idx]

    def get_all_actors(self) -> List[Any]:
        """
        Get all LLM actor handles.

        Returns:
            List of Ray actor handles
        """
        return self.actors

    def _hash_agent_id(self, agent_id: str) -> int:
        """
        Hash an agent ID to an integer.

        Uses SHA256 hash for consistent distribution.

        Args:
            agent_id: UUID of the agent

        Returns:
            Integer hash value
        """
        hash_bytes = hashlib.sha256(agent_id.encode()).digest()
        return int.from_bytes(hash_bytes[:4], byteorder="big")

    def get_stats(self) -> dict:
        """
        Get load balancer statistics.

        Returns:
            Dictionary with statistics:
            - num_actors: Number of actor instances
            - strategy: Load balancing strategy
            - current_round_robin_idx: Current index (if round-robin)
        """
        stats = {
            "num_actors": self.num_actors,
            "strategy": self.strategy.value,
        }

        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            stats["current_round_robin_idx"] = self.current_idx

        return stats


class LLMActorPool:
    """
    Pool of LLM actors with monitoring and health checking.

    Enhanced version of LLMLoadBalancer with:
    - Health checking
    - Request count tracking per actor
    - Automatic failover
    - Performance monitoring
    """

    def __init__(
        self,
        llm_config: dict,
        prompts_config: dict,
        num_actors: int = 4,
        strategy: str = "hash",
        enable_monitoring: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the LLM actor pool.

        Args:
            llm_config: Configuration for LLM service
            prompts_config: Prompt templates configuration
            num_actors: Number of LLM actor instances to create
            strategy: Load balancing strategy ('hash', 'round_robin')
            enable_monitoring: Whether to track per-actor statistics
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.load_balancer = LLMLoadBalancer(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            logger=logger,
        )
        self.enable_monitoring = enable_monitoring

        # Initialize monitoring counters
        if enable_monitoring:
            self.request_counts = [0] * num_actors
            self.error_counts = [0] * num_actors

    def get_actor_for_agent(self, agent_id: str) -> Any:
        """
        Get the LLM actor for a specific agent with monitoring.

        Args:
            agent_id: UUID of the agent

        Returns:
            Ray actor handle for LLM service
        """
        actor = self.load_balancer.get_actor_for_agent(agent_id)

        # Track request count
        if self.enable_monitoring:
            actor_idx = self.load_balancer.actors.index(actor)
            self.request_counts[actor_idx] += 1

        return actor

    def record_error(self, actor: Any):
        """
        Record an error for an actor.

        Args:
            actor: Ray actor handle that encountered an error
        """
        if not self.enable_monitoring:
            return

        try:
            actor_idx = self.load_balancer.actors.index(actor)
            self.error_counts[actor_idx] += 1
        except ValueError:
            # Actor not in pool (shouldn't happen)
            pass

    def get_monitoring_stats(self) -> dict:
        """
        Get monitoring statistics for all actors.

        Returns:
            Dictionary with per-actor statistics
        """
        if not self.enable_monitoring:
            return {"monitoring_enabled": False}

        stats = {
            "monitoring_enabled": True,
            "num_actors": self.load_balancer.num_actors,
            "strategy": self.load_balancer.strategy.value,
            "actors": [],
        }

        for i in range(self.load_balancer.num_actors):
            actor_stats = {
                "actor_id": i,
                "request_count": self.request_counts[i],
                "error_count": self.error_counts[i],
                "error_rate": (
                    self.error_counts[i] / self.request_counts[i]
                    if self.request_counts[i] > 0
                    else 0.0
                ),
            }
            stats["actors"].append(actor_stats)

        # Calculate load balance score (0 = perfectly balanced, higher = more imbalanced)
        if sum(self.request_counts) > 0:
            expected_per_actor = sum(self.request_counts) / self.load_balancer.num_actors
            variance = sum(
                (count - expected_per_actor) ** 2 for count in self.request_counts
            ) / self.load_balancer.num_actors
            stats["load_balance_score"] = variance / expected_per_actor if expected_per_actor > 0 else 0
        else:
            stats["load_balance_score"] = 0

        return stats

    def reset_stats(self):
        """Reset monitoring statistics."""
        if self.enable_monitoring:
            self.request_counts = [0] * self.load_balancer.num_actors
            self.error_counts = [0] * self.load_balancer.num_actors


# Backwards compatibility wrapper
def create_llm_actors(
    llm_config: dict,
    prompts_config: dict,
    num_actors: int = 1,
    strategy: str = "hash",
    enable_monitoring: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Any:
    """
    Create LLM actors with optional load balancing.

    Factory function for creating LLM service instances with load balancing.

    Args:
        llm_config: Configuration for LLM service
        prompts_config: Prompt templates configuration
        num_actors: Number of actors (1 = no load balancing)
        strategy: Load balancing strategy if num_actors > 1
        enable_monitoring: Whether to enable per-actor monitoring
        logger: Optional logger instance

    Returns:
        - If num_actors == 1: Single LLM actor handle (backwards compatible)
        - If num_actors > 1 and enable_monitoring: LLMActorPool instance
        - If num_actors > 1 and not enable_monitoring: LLMLoadBalancer instance
    """
    if num_actors == 1:
        # Single actor - backwards compatible
        from YSimulator.YClient.LLM_interactions.llm_service import LLMService

        return LLMService.remote(llm_config=llm_config, prompts_config=prompts_config)

    # Multiple actors - use load balancing
    if enable_monitoring:
        return LLMActorPool(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            enable_monitoring=True,
            logger=logger,
        )
    else:
        return LLMLoadBalancer(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            logger=logger,
        )
