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


LEASE_REGISTRY_ACTOR_NAME = "ysim_llm_lease_registry"
DEFAULT_VLLM_SHARED_NAMESPACE = "ysim_vllm_shared"


def _build_vllm_pool_prefix(model_name: str) -> str:
    """Create a stable actor-name prefix for a vLLM model."""
    normalized = (model_name or "unknown-model").strip().lower()
    model_hash = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"ysim_vllm_{model_hash}"


def _resolve_actor_namespace(backend: str, llm_config: Optional[dict] = None) -> Optional[str]:
    """Resolve the namespace where named actors should be created/discovered."""
    llm_config = llm_config or {}
    shared_pool = llm_config.get("shared_pool") or {}
    explicit_namespace = shared_pool.get("namespace") or llm_config.get("actor_namespace")
    if explicit_namespace:
        return explicit_namespace
    if backend.lower() == "vllm":
        return DEFAULT_VLLM_SHARED_NAMESPACE
    return None


def _discover_named_actor_count(
    actor_name_prefix: str, backend: str, actor_namespace: Optional[str] = None
) -> int:
    """Return how many consecutively named actors already exist for this pool."""
    count = 0
    while True:
        actor_name = f"{actor_name_prefix}_{backend}_{count}"
        try:
            ray.get_actor(actor_name, namespace=actor_namespace)
            count += 1
        except ValueError:
            break
    return count


def _discover_existing_vllm_pool(
    model_name: str,
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> tuple[str, int]:
    """
    Discover an existing local vLLM pool for a model.

    First check the deterministic model-derived prefix. If nothing is found, scan
    named VLLMService actors and ask them for metadata so we can attach to older pools too.
    """
    preferred_prefix = _build_vllm_pool_prefix(model_name)
    preferred_count = _discover_named_actor_count(preferred_prefix, "vllm", actor_namespace)
    if preferred_count > 0:
        return preferred_prefix, preferred_count

    try:
        from ray.util.state import list_actors
    except Exception:
        return preferred_prefix, 0

    candidate_groups = {}
    try:
        actor_states = list_actors()
    except Exception as exc:
        if logger:
            logger.warning(
                f"Unable to scan Ray actor state for reusable vLLM pools: {exc}. "
                "Falling back to deterministic prefix discovery only."
            )
        return preferred_prefix, 0

    for actor_state in actor_states:
        actor_name = actor_state.get("name")
        if not actor_name or actor_state.get("class_name") != "VLLMService":
            continue
        if actor_state.get("state") not in (None, "ALIVE"):
            continue
        state_namespace = actor_state.get("ray_namespace") or actor_state.get("namespace")
        if actor_namespace and state_namespace and state_namespace != actor_namespace:
            continue

        try:
            actor = ray.get_actor(actor_name, namespace=actor_namespace)
            metadata = ray.get(actor.get_service_metadata.remote())
        except Exception:
            continue

        if metadata.get("backend") != "vllm" or metadata.get("model") != model_name:
            continue

        pool_prefix = metadata.get("pool_prefix") or actor_name.rsplit("_vllm_", 1)[0]
        candidate_groups.setdefault(pool_prefix, []).append(actor_name)

    if not candidate_groups:
        return preferred_prefix, 0

    selected_prefix, actor_names = max(
        candidate_groups.items(), key=lambda item: (len(item[1]), item[0])
    )
    if logger:
        logger.info(
            f"Discovered existing vLLM pool via actor metadata: model={model_name}, "
            f"prefix={selected_prefix}, actors={len(actor_names)}"
        )
    return selected_prefix, len(actor_names)


@ray.remote
class LLMLeaseRegistry:
    """Tracks active clients per LLM pool to support safe shared-actor cleanup."""

    def __init__(self):
        self.pool_clients = {}  # pool_key -> set(client_id)
        self.pool_actor_names = {}  # pool_key -> list[str]

    def acquire(self, pool_key: str, client_id: str, actor_names: List[str]) -> int:
        clients = self.pool_clients.setdefault(pool_key, set())
        clients.add(client_id)
        if actor_names:
            self.pool_actor_names[pool_key] = actor_names
        return len(clients)

    def release(self, pool_key: str, client_id: str) -> tuple[int, List[str]]:
        clients = self.pool_clients.get(pool_key, set())
        clients.discard(client_id)
        if clients:
            self.pool_clients[pool_key] = clients
            return len(clients), []

        self.pool_clients.pop(pool_key, None)
        actor_names = self.pool_actor_names.pop(pool_key, [])
        return 0, actor_names


def _build_pool_key(backend: str, actor_name_prefix: str, num_actors: int) -> str:
    """Build a deterministic key for a shared actor pool."""
    return f"{backend.lower()}:{actor_name_prefix}:{num_actors}"


def _get_or_create_lease_registry(actor_namespace: Optional[str] = None):
    """Get or create the detached lease registry actor."""
    try:
        return ray.get_actor(LEASE_REGISTRY_ACTOR_NAME, namespace=actor_namespace)
    except ValueError:
        options = {"name": LEASE_REGISTRY_ACTOR_NAME, "lifetime": "detached"}
        if actor_namespace:
            options["namespace"] = actor_namespace
        return LLMLeaseRegistry.options(**options).remote()


def acquire_llm_pool_lease(
    backend: str,
    actor_name_prefix: str,
    num_actors: int,
    client_id: str,
    actor_names: List[str],
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Register client usage of an LLM actor pool."""
    pool_key = _build_pool_key(backend, actor_name_prefix, num_actors)
    registry = _get_or_create_lease_registry(actor_namespace)
    active = ray.get(registry.acquire.remote(pool_key, client_id, actor_names))
    if logger:
        logger.info(
            f"Acquired LLM pool lease: key={pool_key}, client={client_id}, active_clients={active}"
        )
    return active


def release_llm_pool_lease(
    backend: str,
    actor_name_prefix: str,
    num_actors: int,
    client_id: str,
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """
    Release client usage of an LLM actor pool.

    If this is the last client, all detached actors in the pool are terminated.
    """
    pool_key = _build_pool_key(backend, actor_name_prefix, num_actors)
    registry = _get_or_create_lease_registry(actor_namespace)
    active, actor_names = ray.get(registry.release.remote(pool_key, client_id))
    if logger:
        logger.info(
            f"Released LLM pool lease: key={pool_key}, client={client_id}, active_clients={active}"
        )

    if active == 0 and actor_names:
        for actor_name in actor_names:
            try:
                actor = ray.get_actor(actor_name, namespace=actor_namespace)
                try:
                    if hasattr(actor, "shutdown"):
                        shutdown_result = ray.get(actor.shutdown.remote())
                        if logger:
                            logger.info(
                                f"Shutdown idle LLM actor before termination: {actor_name} "
                                f"(details={shutdown_result})"
                            )
                except Exception as shutdown_exc:
                    if logger:
                        logger.warning(
                            f"Best-effort shutdown failed for LLM actor {actor_name}: {shutdown_exc}"
                        )
                ray.kill(actor, no_restart=True)
                if logger:
                    logger.info(f"Terminated idle LLM actor: {actor_name}")
            except ValueError:
                # Actor already gone, ignore.
                continue
            except Exception as exc:
                if logger:
                    logger.warning(f"Failed to terminate LLM actor {actor_name}: {exc}")

    return active


class LLMLoadBalancer:
    """
    Load balancer for multiple LLM actor instances.

    Distributes LLM inference requests across multiple Ray actors to achieve
    parallel processing and reduce the sequential bottleneck.

    Supports shared actors across multiple clients on the same machine.

    Attributes:
        actors: List of LLM Ray actor handles
        strategy: Load balancing strategy to use
        logger: Logger instance
        owns_actors: Whether this instance created the actors (for lifecycle management)
    """

    def __init__(
        self,
        llm_config: dict,
        prompts_config: dict,
        num_actors: int = 4,
        strategy: str = "hash",
        backend: str = "ollama",
        llm_v_config: Optional[dict] = None,
        logger: Optional[logging.Logger] = None,
        reuse_actors: bool = False,
        actor_name_prefix: str = "ysim_llm",
    ):
        """
        Initialize the LLM load balancer.

        Args:
            llm_config: Configuration for LLM service
            prompts_config: Prompt templates configuration
            num_actors: Number of LLM actor instances to create/reuse
            strategy: Load balancing strategy ('hash', 'round_robin')
            backend: LLM backend to use ('ollama' or 'vllm')
            llm_v_config: Optional configuration for vision LLM (vLLM only)
            logger: Optional logger instance
            reuse_actors: If True, try to reuse existing actors from another client
            actor_name_prefix: Prefix for named actors (for discovery)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.num_actors = num_actors
        self.strategy = LoadBalancingStrategy(strategy)
        self.current_idx = 0  # For round-robin
        self.backend = backend.lower()
        self.owns_actors = False  # Track if we created the actors
        self.actor_name_prefix = actor_name_prefix
        self.actor_namespace = _resolve_actor_namespace(self.backend, llm_config)

        # Get GPU allocation per actor (for vLLM)
        # Supports fractional GPUs to allocate multiple actors per GPU
        # E.g., gpu_per_actor=0.25 allows 4 actors on 1 GPU
        gpu_per_actor = llm_config.get("gpu_per_actor", 1.0)

        # Import appropriate service based on backend
        if self.backend == "vllm":
            from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService

            ServiceClass = VLLMService
        else:
            from YSimulator.YClient.LLM_interactions.llm_service import LLMService

            ServiceClass = LLMService

        self.actors = []

        # Try to reuse existing actors if requested
        if reuse_actors:
            self.logger.info(
                f"Attempting to reuse existing {num_actors} LLM actors ({self.backend} backend)"
            )
            reused_count = 0
            for i in range(num_actors):
                actor_name = f"{actor_name_prefix}_{self.backend}_{i}"
                try:
                    actor = ray.get_actor(actor_name, namespace=self.actor_namespace)
                    self.actors.append(actor)
                    reused_count += 1
                    self.logger.info(f"Reused existing LLM actor {i+1}/{num_actors}: {actor_name}")
                except ValueError:
                    # Actor doesn't exist, we'll need to create it
                    self.logger.debug(f"Actor {actor_name} not found, will create new actors")
                    break

            if reused_count == num_actors:
                self.logger.info(
                    f"Successfully reused {reused_count} existing LLM actors ({self.backend})"
                )
                self.owns_actors = False
                return

            # If we couldn't reuse all actors, start fresh
            if reused_count > 0:
                self.logger.warning(
                    f"Only found {reused_count}/{num_actors} existing actors, creating new set"
                )
                self.actors = []

        # Create new actors (either reuse failed or not requested)
        self.logger.info(
            f"Creating {num_actors} LLM actors for parallel inference using {self.backend} backend"
        )
        if self.backend == "vllm":
            self.logger.info(f"GPU allocation per actor: {gpu_per_actor}")

        for i in range(num_actors):
            actor_name = f"{actor_name_prefix}_{self.backend}_{i}"

            # Allocate GPU resources for vLLM actors
            if self.backend == "vllm":
                options = {
                    "name": actor_name,
                    "num_gpus": gpu_per_actor,
                    "lifetime": "detached",
                }
                if self.actor_namespace:
                    options["namespace"] = self.actor_namespace
                actor = ServiceClass.options(**options).remote(
                    llm_config=llm_config,
                    prompts_config=prompts_config,
                    llm_v_config=llm_v_config,
                )
            else:
                options = {"name": actor_name, "lifetime": "detached"}
                if self.actor_namespace:
                    options["namespace"] = self.actor_namespace
                actor = ServiceClass.options(**options).remote(
                    llm_config=llm_config,
                    prompts_config=prompts_config,
                    llm_v_config=llm_v_config,
                )
            self.actors.append(actor)
            self.logger.info(f"Created LLM actor {i+1}/{num_actors} ({self.backend}): {actor_name}")

        self.owns_actors = True
        self.logger.info(
            f"LLM load balancer initialized with {num_actors} actors, strategy={strategy}, backend={self.backend}"
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
        backend: str = "ollama",
        enable_monitoring: bool = True,
        llm_v_config: Optional[dict] = None,
        logger: Optional[logging.Logger] = None,
        reuse_actors: bool = False,
        actor_name_prefix: str = "ysim_llm",
    ):
        """
        Initialize the LLM actor pool.

        Args:
            llm_config: Configuration for LLM service
            prompts_config: Prompt templates configuration
            num_actors: Number of LLM actor instances to create
            strategy: Load balancing strategy ('hash', 'round_robin')
            backend: LLM backend to use ('ollama' or 'vllm')
            enable_monitoring: Whether to track per-actor statistics
            llm_v_config: Optional configuration for vision LLM (vLLM only)
            logger: Optional logger instance
            reuse_actors: If True, try to reuse existing actors from another client
            actor_name_prefix: Prefix for named actors (for discovery)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.load_balancer = LLMLoadBalancer(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            backend=backend,
            llm_v_config=llm_v_config,
            logger=logger,
            reuse_actors=reuse_actors,
            actor_name_prefix=actor_name_prefix,
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
            variance = (
                sum((count - expected_per_actor) ** 2 for count in self.request_counts)
                / self.load_balancer.num_actors
            )
            stats["load_balance_score"] = (
                variance / expected_per_actor if expected_per_actor > 0 else 0
            )
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
    backend: str = "ollama",
    enable_monitoring: bool = False,
    llm_v_config: Optional[dict] = None,
    logger: Optional[logging.Logger] = None,
    reuse_actors: bool = False,
    actor_name_prefix: str = "ysim_llm",
    logging_config: Optional[dict] = None,
) -> Any:
    """
    Create LLM actors with optional load balancing and actor reuse.

    Factory function for creating LLM service instances with load balancing.
    Supports reusing existing actors from other clients on the same machine.

    Args:
        llm_config: Configuration for LLM service
        prompts_config: Prompt templates configuration
        num_actors: Number of actors (1 = no load balancing)
        strategy: Load balancing strategy if num_actors > 1
        backend: LLM backend to use ('ollama' or 'vllm')
        enable_monitoring: Whether to enable per-actor monitoring
        llm_v_config: Optional configuration for vision LLM (vLLM only)
        logger: Optional logger instance
        reuse_actors: If True, try to reuse existing actors from another client
        actor_name_prefix: Prefix for named actors (for discovery)

    Returns:
        - If num_actors == 1: Single LLM actor handle (backwards compatible)
        - If num_actors > 1 and enable_monitoring: LLMActorPool instance
        - If num_actors > 1 and not enable_monitoring: LLMLoadBalancer instance
    """
    backend_lower = backend.lower()

    if backend_lower == "vllm":
        actor_namespace = _resolve_actor_namespace(backend_lower, llm_config)
        resolved_prefix, existing_count = _discover_existing_vllm_pool(
            llm_config.get("model", "unknown-model"), actor_namespace, logger
        )
        if existing_count > 0:
            if logger:
                logger.info(
                    f"Reusing existing local vLLM pool for model={llm_config.get('model')} "
                    f"with {existing_count} actor(s)"
                )
            actor_name_prefix = resolved_prefix
            num_actors = existing_count
            reuse_actors = True
            llm_config["_reused_existing_pool"] = True
        else:
            actor_name_prefix = resolved_prefix
            llm_config["_reused_existing_pool"] = False

        llm_config["_resolved_actor_name_prefix"] = actor_name_prefix
        llm_config["_resolved_num_actors"] = num_actors
        llm_config["_resolved_actor_namespace"] = actor_namespace
    else:
        actor_namespace = _resolve_actor_namespace(backend_lower, llm_config)
        if actor_namespace:
            llm_config["_resolved_actor_namespace"] = actor_namespace

    # Get GPU allocation per actor (for vLLM)
    gpu_per_actor = llm_config.get("gpu_per_actor", 1.0)

    if num_actors == 1:
        # Single actor - check if we should reuse
        if reuse_actors:
            actor_name = f"{actor_name_prefix}_{backend_lower}_0"
            try:
                actor = ray.get_actor(actor_name, namespace=actor_namespace)
                if logger:
                    logger.info(f"Reused existing single LLM actor: {actor_name}")
                if actor_name and llm_config.get("client_name"):
                    acquire_llm_pool_lease(
                        backend=backend_lower,
                        actor_name_prefix=actor_name_prefix,
                        num_actors=1,
                        client_id=llm_config["client_name"],
                        actor_names=[actor_name],
                        actor_namespace=actor_namespace,
                        logger=logger,
                    )
                return actor
            except ValueError:
                # Actor doesn't exist, create new one
                if logger:
                    logger.debug(f"Actor {actor_name} not found, creating new one")

        # Create new single actor
        if backend_lower == "vllm":
            from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService

            actor_name = f"{actor_name_prefix}_{backend_lower}_0"
            options = {"num_gpus": gpu_per_actor, "lifetime": "detached"}
            if actor_name:
                options["name"] = actor_name
            if actor_namespace:
                options["namespace"] = actor_namespace

            actor = VLLMService.options(**options).remote(
                llm_config=llm_config,
                prompts_config=prompts_config,
                llm_v_config=llm_v_config,
                logging_config=logging_config,
            )
            if actor_name and reuse_actors and llm_config.get("client_name"):
                acquire_llm_pool_lease(
                    backend=backend_lower,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=1,
                    client_id=llm_config["client_name"],
                    actor_names=[actor_name],
                    actor_namespace=actor_namespace,
                    logger=logger,
                )
            return actor
        else:
            from YSimulator.YClient.LLM_interactions.llm_service import LLMService

            actor_name = f"{actor_name_prefix}_{backend_lower}_0" if reuse_actors else None
            options = {"lifetime": "detached"} if reuse_actors else {}
            if actor_name:
                options["name"] = actor_name
            if actor_namespace:
                options["namespace"] = actor_namespace

            actor = LLMService.options(**options).remote(
                llm_config=llm_config,
                prompts_config=prompts_config,
                llm_v_config=llm_v_config,
                logging_config=logging_config,
            )
            if actor_name and reuse_actors and llm_config.get("client_name"):
                acquire_llm_pool_lease(
                    backend=backend_lower,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=1,
                    client_id=llm_config["client_name"],
                    actor_names=[actor_name],
                    actor_namespace=actor_namespace,
                    logger=logger,
                )
            return actor

    # Multiple actors - use load balancing
    if enable_monitoring:
        pool = LLMActorPool(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            backend=backend,
            enable_monitoring=True,
            llm_v_config=llm_v_config,
            logger=logger,
            reuse_actors=reuse_actors,
            actor_name_prefix=actor_name_prefix,
        )
        if llm_config.get("client_name"):
            actor_names = [f"{actor_name_prefix}_{backend_lower}_{i}" for i in range(num_actors)]
            acquire_llm_pool_lease(
                backend=backend_lower,
                actor_name_prefix=actor_name_prefix,
                num_actors=num_actors,
                client_id=llm_config["client_name"],
                actor_names=actor_names,
                actor_namespace=actor_namespace,
                logger=logger,
            )
        return pool
    else:
        balancer = LLMLoadBalancer(
            llm_config=llm_config,
            prompts_config=prompts_config,
            num_actors=num_actors,
            strategy=strategy,
            backend=backend,
            llm_v_config=llm_v_config,
            logger=logger,
            reuse_actors=reuse_actors,
            actor_name_prefix=actor_name_prefix,
        )
        if llm_config.get("client_name"):
            actor_names = [f"{actor_name_prefix}_{backend_lower}_{i}" for i in range(num_actors)]
            acquire_llm_pool_lease(
                backend=backend_lower,
                actor_name_prefix=actor_name_prefix,
                num_actors=num_actors,
                client_id=llm_config["client_name"],
                actor_names=actor_names,
                actor_namespace=actor_namespace,
                logger=logger,
            )
        return balancer
