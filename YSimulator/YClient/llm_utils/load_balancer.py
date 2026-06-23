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
import threading
import time
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
DEFAULT_VLLM_SHARED_POOL_CAPACITY = 5
DEFAULT_VLLM_SHARED_POOL_TTL_SECONDS = 5 * 60
DEFAULT_VLLM_SHARED_POOL_REAPER_INTERVAL_SECONDS = 60
DEFAULT_BATCHING_POLICY = "auto"


def _build_vllm_pool_prefix(
    model_name: str, experiment_identity: Optional[str] = None
) -> str:
    """Create a stable actor-name prefix for a vLLM model and experiment."""
    normalized = (model_name or "unknown-model").strip().lower()
    model_hash = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    if experiment_identity:
        experiment_digest = hashlib.sha256(
            str(experiment_identity).strip().encode()
        ).hexdigest()[:12]
        return f"ysim_vllm_{model_hash}_{experiment_digest}"
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


def _resolve_vllm_shared_pool_capacity(llm_config: Optional[dict]) -> Optional[int]:
    """Return the configured shared vLLM pool capacity, or None when disabled."""
    llm_config = llm_config or {}
    shared_pool = llm_config.get("shared_pool") or {}
    if not shared_pool.get("enabled"):
        return None

    raw_capacity = shared_pool.get("max_clients_per_worker")
    if raw_capacity is None:
        raw_capacity = shared_pool.get("max_clients")
    if raw_capacity is None:
        return DEFAULT_VLLM_SHARED_POOL_CAPACITY

    try:
        capacity = int(raw_capacity)
    except (TypeError, ValueError):
        return DEFAULT_VLLM_SHARED_POOL_CAPACITY
    return capacity if capacity > 0 else DEFAULT_VLLM_SHARED_POOL_CAPACITY


def _build_vllm_shared_group_key(
    llm_config: Optional[dict],
    actor_namespace: Optional[str],
    actor_name_prefix: str,
    num_actors: int,
    actor_backend: str,
    experiment_identity: Optional[str] = None,
) -> str:
    """Build a stable allocation key for shared vLLM pool sharding."""
    llm_config = llm_config or {}
    model_name = str(llm_config.get("model", "unknown-model")).strip().lower()
    tensor_parallel_size = llm_config.get("tensor_parallel_size", 1)
    gpu_per_actor = llm_config.get("gpu_per_actor", 1.0)
    namespace = actor_namespace or DEFAULT_VLLM_SHARED_NAMESPACE
    experiment_identity = experiment_identity or _resolve_experiment_identity(llm_config)
    key_parts = [
        actor_backend.lower(),
        namespace,
        actor_name_prefix,
        str(num_actors),
        str(tensor_parallel_size),
        str(gpu_per_actor),
        model_name,
    ]
    if experiment_identity:
        experiment_digest = hashlib.sha256(experiment_identity.encode()).hexdigest()[:16]
        key_parts.extend(["exp", experiment_digest])
    return ":".join(key_parts)


def _resolve_lease_client_id(llm_config: Optional[dict]) -> Optional[str]:
    """Return a stable per-run lease holder id for shared LLM pools."""
    llm_config = llm_config or {}
    return llm_config.get("_lease_client_id") or llm_config.get("client_name")


def _resolve_experiment_identity(llm_config: Optional[dict]) -> Optional[str]:
    """Return a stable experiment identity if one was provided by the caller."""
    llm_config = llm_config or {}
    experiment_identity = llm_config.get("_experiment_identity") or llm_config.get(
        "experiment_identity"
    )
    if experiment_identity is None:
        return None
    experiment_identity = str(experiment_identity).strip()
    return experiment_identity or None


def _resolve_batching_policy(llm_config: Optional[dict]) -> str:
    """Return validated batching policy for non-vLLM providers."""
    llm_config = llm_config or {}
    policy = str(llm_config.get("batching_policy", DEFAULT_BATCHING_POLICY)).strip().lower()
    return policy if policy in {"auto", "off", "force"} else DEFAULT_BATCHING_POLICY


def _resolve_service_backend(
    backend: str, llm_config: Optional[dict], logger: Optional[logging.Logger] = None
) -> str:
    """
    Resolve the concrete service backend to instantiate.

    `ollama` may upgrade to `remote_batch` after a startup probe succeeds.
    """
    backend_lower = (backend or "ollama").lower()
    if backend_lower == "vllm":
        return "vllm"

    policy = _resolve_batching_policy(llm_config)
    if policy == "off":
        return backend_lower

    from YSimulator.YClient.LLM_interactions.remote_batch_service import (
        resolve_remote_batch_provider,
    )

    remote_provider = resolve_remote_batch_provider(llm_config or {}, logger=logger)
    if remote_provider:
        if llm_config is not None:
            llm_config["_resolved_remote_api"] = remote_provider
        return "remote_batch"
    if policy == "force":
        raise RuntimeError(
            "Configured remote LLM endpoint does not support batch requests, "
            "but llm.batching_policy='force' was requested"
        )
    return backend_lower


def _resolve_actor_backend_tag(service_backend: str, requested_backend: str) -> str:
    """Return actor-name/lease backend tag for the resolved service backend."""
    if service_backend == "remote_batch":
        return "remote_batch"
    return (requested_backend or service_backend).lower()


def _get_service_class(service_backend: str):
    """Import and return the concrete actor class for the resolved service backend."""
    if service_backend == "vllm":
        from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService

        return VLLMService
    if service_backend == "remote_batch":
        from YSimulator.YClient.LLM_interactions.remote_batch_service import RemoteBatchLLMService

        return RemoteBatchLLMService
    from YSimulator.YClient.LLM_interactions.llm_service import LLMService

    return LLMService


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
    experiment_identity: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> tuple[str, int]:
    """
    Discover an existing local vLLM pool for a model.

    First check the deterministic model-derived prefix. If nothing is found, scan
    named VLLMService actors and ask them for metadata so we can attach to older pools too.
    """
    preferred_prefix = _build_vllm_pool_prefix(model_name, experiment_identity)
    preferred_count = _discover_named_actor_count(preferred_prefix, "vllm", actor_namespace)
    if preferred_count > 0 and experiment_identity is None:
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
        if (
            experiment_identity is not None
            and metadata.get("experiment_identity") != experiment_identity
        ):
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
        self._lock = threading.RLock()
        self._stop_reaper = threading.Event()
        self.pool_clients = {}  # pool_key -> set(client_id)
        self.pool_actor_names = {}  # pool_key -> list[str]
        self.shared_vllm_groups = {}  # group_key -> list[pool_key]
        self.shared_vllm_pool_meta = {}  # pool_key -> metadata dict
        self._reaper_thread = threading.Thread(target=self._reaper_loop, daemon=True)
        self._reaper_thread.start()

    def _now(self) -> float:
        return time.time()

    def _is_shared_vllm_pool(self, pool_key: str) -> bool:
        return pool_key in self.shared_vllm_pool_meta

    def _get_shared_pool_meta(self, pool_key: str) -> dict:
        return self.shared_vllm_pool_meta.setdefault(
            pool_key,
            {
                "group_key": None,
                "pool_prefix": None,
                "capacity": None,
                "status": "ready",
                "created_at": self._now(),
                "last_activity_at": self._now(),
                "idle_since": None,
            },
        )

    def _reap_expired_shared_vllm_pools_locked(self, now: Optional[float] = None) -> List[str]:
        now = self._now() if now is None else now
        expired_actor_names: List[str] = []
        expired_pool_keys: List[str] = []

        for pool_key, meta in list(self.shared_vllm_pool_meta.items()):
            idle_since = meta.get("idle_since")
            if meta.get("status") != "idle" or idle_since is None:
                continue
            if now - float(idle_since) < DEFAULT_VLLM_SHARED_POOL_TTL_SECONDS:
                continue
            expired_pool_keys.append(pool_key)

        for pool_key in expired_pool_keys:
            meta = self.shared_vllm_pool_meta.pop(pool_key, None)
            self.pool_clients.pop(pool_key, None)
            actor_names = self.pool_actor_names.pop(pool_key, [])
            if meta and meta.get("group_key"):
                pools = self.shared_vllm_groups.get(meta["group_key"], [])
                self.shared_vllm_groups[meta["group_key"]] = [
                    existing_pool_key
                    for existing_pool_key in pools
                    if existing_pool_key != pool_key
                ]
                if not self.shared_vllm_groups[meta["group_key"]]:
                    self.shared_vllm_groups.pop(meta["group_key"], None)
            if actor_names:
                expired_actor_names.extend(actor_names)

        return expired_actor_names

    def _reaper_loop(self) -> None:
        while not self._stop_reaper.wait(DEFAULT_VLLM_SHARED_POOL_REAPER_INTERVAL_SECONDS):
            try:
                with self._lock:
                    expired_actor_names = self._reap_expired_shared_vllm_pools_locked()
                if expired_actor_names:
                    _terminate_llm_actors(expired_actor_names)
            except Exception:
                continue

    def acquire(self, pool_key: str, client_id: str, actor_names: List[str]) -> int:
        with self._lock:
            clients = self.pool_clients.setdefault(pool_key, set())
            clients.add(client_id)
            if actor_names:
                self.pool_actor_names[pool_key] = actor_names
            if self._is_shared_vllm_pool(pool_key):
                meta = self._get_shared_pool_meta(pool_key)
                meta["last_activity_at"] = self._now()
                meta["idle_since"] = None
                meta["status"] = "ready"
            return len(clients)

    def release(self, pool_key: str, client_id: str) -> tuple[int, List[str]]:
        with self._lock:
            clients = self.pool_clients.get(pool_key, set())
            clients.discard(client_id)
            if clients:
                self.pool_clients[pool_key] = clients
                if self._is_shared_vllm_pool(pool_key):
                    meta = self._get_shared_pool_meta(pool_key)
                    meta["last_activity_at"] = self._now()
                    meta["idle_since"] = None
                    meta["status"] = "ready"
                return len(clients), []

            if self._is_shared_vllm_pool(pool_key):
                meta = self._get_shared_pool_meta(pool_key)
                meta["last_activity_at"] = self._now()
                meta["idle_since"] = self._now()
                meta["status"] = "idle"
                self.pool_clients[pool_key] = set()
                return 0, []

            self.pool_clients.pop(pool_key, None)
            actor_names = self.pool_actor_names.pop(pool_key, [])
            meta = self.shared_vllm_pool_meta.pop(pool_key, None)
            if meta and meta.get("group_key"):
                pools = self.shared_vllm_groups.get(meta["group_key"], [])
                self.shared_vllm_groups[meta["group_key"]] = [
                    existing_pool_key
                    for existing_pool_key in pools
                    if existing_pool_key != pool_key
                ]
                if not self.shared_vllm_groups[meta["group_key"]]:
                    self.shared_vllm_groups.pop(meta["group_key"], None)
            return 0, actor_names

    def reserve_shared_vllm_pool(
        self,
        group_key: str,
        client_id: str,
        actor_name_prefix: str,
        actor_backend: str,
        num_actors: int,
        capacity: int,
    ) -> dict:
        """
        Reserve a shared vLLM pool slot for a client.

        Returns metadata describing the selected pool. Existing ready pools are reused
        until they reach capacity; otherwise a new bootstrapping pool is created.
        """
        with self._lock:
            self._reap_expired_shared_vllm_pools_locked()
            pools = self.shared_vllm_groups.setdefault(group_key, [])
            for pool_key in pools:
                clients = self.pool_clients.setdefault(pool_key, set())
                meta = self._get_shared_pool_meta(pool_key)
                if client_id in clients:
                    meta["last_activity_at"] = self._now()
                    meta["idle_since"] = None
                    meta["status"] = "ready"
                    return {
                        "pool_key": pool_key,
                        "pool_prefix": meta.get("pool_prefix"),
                        "actor_names": self.pool_actor_names.get(pool_key, []),
                        "is_creator": False,
                        "status": meta.get("status", "ready"),
                        "active_clients": len(clients),
                        "capacity": meta.get("capacity", capacity),
                    }

                if len(clients) < int(meta.get("capacity") or capacity):
                    clients.add(client_id)
                    self.pool_clients[pool_key] = clients
                    meta["last_activity_at"] = self._now()
                    meta["idle_since"] = None
                    meta["status"] = "ready"
                    return {
                        "pool_key": pool_key,
                        "pool_prefix": meta.get("pool_prefix"),
                        "actor_names": self.pool_actor_names.get(pool_key, []),
                        "is_creator": False,
                        "status": meta.get("status", "ready"),
                        "active_clients": len(clients),
                        "capacity": meta.get("capacity", capacity),
                    }

            pool_index = len(pools)
            pool_prefix = f"{actor_name_prefix}_pool{pool_index}"
            pool_key = _build_pool_key(actor_backend, pool_prefix, num_actors)
            pools.append(pool_key)
            self.shared_vllm_groups[group_key] = pools
            self.pool_clients[pool_key] = {client_id}
            self.pool_actor_names[pool_key] = []
            meta = self._get_shared_pool_meta(pool_key)
            meta.update(
                {
                    "group_key": group_key,
                    "pool_prefix": pool_prefix,
                    "capacity": int(capacity),
                    "status": "bootstrapping",
                    "created_at": self._now(),
                    "last_activity_at": self._now(),
                    "idle_since": None,
                }
            )
            return {
                "pool_key": pool_key,
                "pool_prefix": pool_prefix,
                "actor_names": [],
                "is_creator": True,
                "status": "bootstrapping",
                "active_clients": 1,
                "capacity": int(capacity),
            }

    def register_shared_vllm_pool_actors(
        self, pool_key: str, actor_names: List[str]
    ) -> dict:
        with self._lock:
            meta = self._get_shared_pool_meta(pool_key)
            meta["status"] = "ready"
            meta["last_activity_at"] = self._now()
            meta["idle_since"] = None
            self.pool_actor_names[pool_key] = actor_names
            return {
                "pool_key": pool_key,
                "actor_names": actor_names,
                "status": meta["status"],
            }

    def get_shared_vllm_pool_state(self, pool_key: str) -> dict:
        with self._lock:
            meta = self._get_shared_pool_meta(pool_key)
            return {
                "pool_key": pool_key,
                "actor_names": self.pool_actor_names.get(pool_key, []),
                "status": meta.get("status", "ready"),
                "capacity": meta.get("capacity"),
                "idle_since": meta.get("idle_since"),
                "last_activity_at": meta.get("last_activity_at"),
            }

    def reap_expired_shared_vllm_pools(self, now: Optional[float] = None) -> List[str]:
        with self._lock:
            return self._reap_expired_shared_vllm_pools_locked(now)


def _build_pool_key(backend: str, actor_name_prefix: str, num_actors: int) -> str:
    """Build a deterministic key for a shared actor pool."""
    return f"{backend.lower()}:{actor_name_prefix}:{num_actors}"


def _force_kill_local_processes(
    process_ids: List[int], logger: Optional[logging.Logger] = None
) -> int:
    """Best-effort kill for leaked local processes that survived actor shutdown."""
    if not process_ids:
        return 0

    try:
        import psutil
    except Exception as exc:
        if logger:
            logger.warning(f"psutil unavailable for leaked process cleanup: {exc}")
        return 0

    killed = 0
    unique_pids = []
    seen = set()
    for pid in process_ids:
        if pid and pid not in seen:
            unique_pids.append(pid)
            seen.add(pid)

    for pid in unique_pids:
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue

        try:
            process.kill()
            process.wait(timeout=3)
            killed += 1
            if logger:
                logger.info(f"Force-killed leaked local process pid={pid}")
        except psutil.NoSuchProcess:
            continue
        except Exception as exc:
            if logger:
                logger.warning(f"Failed to force-kill leaked process pid={pid}: {exc}")

    return killed


def _terminate_llm_actor(
    actor_name: str,
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Best-effort terminate a single detached LLM actor and its leaked processes."""
    shutdown_result = {}
    try:
        actor = ray.get_actor(actor_name, namespace=actor_namespace)
        try:
            if hasattr(actor, "shutdown"):
                shutdown_result = ray.get(actor.shutdown.remote()) or {}
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
        leaked_pids = []
        actor_pid = shutdown_result.get("actor_pid")
        if actor_pid:
            leaked_pids.append(actor_pid)
        leaked_pids.extend(shutdown_result.get("child_pids", []))
        force_killed = _force_kill_local_processes(leaked_pids, logger)
        if force_killed and logger:
            logger.info(
                f"Force-killed {force_killed} leaked process(es) after terminating {actor_name}"
            )
    except ValueError:
        # Actor already gone, ignore.
        return
    except Exception as exc:
        if logger:
            logger.warning(f"Failed to terminate LLM actor {actor_name}: {exc}")


def _terminate_llm_actors(
    actor_names: List[str],
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Terminate a list of detached LLM actors."""
    for actor_name in actor_names:
        _terminate_llm_actor(actor_name, actor_namespace=actor_namespace, logger=logger)


def _get_or_create_lease_registry(actor_namespace: Optional[str] = None):
    """Get or create the detached lease registry actor."""
    try:
        return ray.get_actor(LEASE_REGISTRY_ACTOR_NAME, namespace=actor_namespace)
    except ValueError:
        options = {"name": LEASE_REGISTRY_ACTOR_NAME, "lifetime": "detached"}
        if actor_namespace:
            options["namespace"] = actor_namespace
        try:
            return LLMLeaseRegistry.options(**options).remote()
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    return ray.get_actor(LEASE_REGISTRY_ACTOR_NAME, namespace=actor_namespace)
                except ValueError:
                    time.sleep(0.1)
            raise


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

    if backend.lower() == "vllm":
        try:
            cleanup_expired_shared_vllm_pools(actor_namespace=actor_namespace, logger=logger)
        except Exception as exc:
            if logger:
                logger.warning(f"Shared vLLM cleanup pass failed after lease release: {exc}")

    if active == 0 and actor_names:
        _terminate_llm_actors(actor_names, actor_namespace=actor_namespace, logger=logger)

    return active


def cleanup_expired_shared_vllm_pools(
    actor_namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> List[str]:
    """
    Sweep idle shared vLLM pools whose TTL has elapsed and terminate their actors.
    """
    try:
        registry = _get_or_create_lease_registry(actor_namespace)
        expired_actor_names = ray.get(
            registry.reap_expired_shared_vllm_pools.remote(time.time())
        )
    except Exception as exc:
        if logger:
            logger.warning(f"Unable to sweep expired shared vLLM pools: {exc}")
        return []

    if expired_actor_names:
        _terminate_llm_actors(expired_actor_names, actor_namespace=actor_namespace, logger=logger)
        if logger:
            logger.info(
                f"Reaped {len(expired_actor_names)} expired shared vLLM actor(s)"
            )
    return expired_actor_names


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
        self.service_backend = llm_config.get("_resolved_service_backend", self.backend)
        self.actor_backend = llm_config.get(
            "_resolved_pool_backend",
            _resolve_actor_backend_tag(self.service_backend, self.backend),
        )
        self.owns_actors = False  # Track if we created the actors
        self.actor_name_prefix = actor_name_prefix
        self.actor_namespace = _resolve_actor_namespace(self.backend, llm_config)

        # Get GPU allocation per actor (for vLLM)
        # Supports fractional GPUs to allocate multiple actors per GPU
        # E.g., gpu_per_actor=0.25 allows 4 actors on 1 GPU
        gpu_per_actor = llm_config.get("gpu_per_actor", 1.0)

        # Resolved actor class may be VLLMService, RemoteBatchLLMService, or LLMService.
        ServiceClass = _get_service_class(self.service_backend)

        self.actors = []

        # Try to reuse existing actors if requested
        if reuse_actors:
            self.logger.info(
                f"Attempting to reuse existing {num_actors} LLM actors ({self.actor_backend} backend)"
            )
            reused_count = 0
            for i in range(num_actors):
                actor_name = f"{actor_name_prefix}_{self.actor_backend}_{i}"
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
                    f"Successfully reused {reused_count} existing LLM actors ({self.actor_backend})"
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
            f"Creating {num_actors} LLM actors for parallel inference using {self.service_backend} backend"
        )
        if self.service_backend == "vllm":
            self.logger.info(f"GPU allocation per actor: {gpu_per_actor}")

        for i in range(num_actors):
            actor_name = f"{actor_name_prefix}_{self.actor_backend}_{i}"

            # Allocate GPU resources for vLLM actors
            if self.service_backend == "vllm":
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
            self.logger.info(
                f"Created LLM actor {i+1}/{num_actors} ({self.service_backend}): {actor_name}"
            )

        self.owns_actors = True
        self.logger.info(
            f"LLM load balancer initialized with {num_actors} actors, strategy={strategy}, "
            f"backend={self.service_backend}"
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
    service_backend = _resolve_service_backend(backend_lower, llm_config, logger=logger)
    actor_backend = _resolve_actor_backend_tag(service_backend, backend_lower)
    llm_config["_resolved_service_backend"] = service_backend
    llm_config["_resolved_pool_backend"] = actor_backend

    actor_namespace = _resolve_actor_namespace(backend_lower, llm_config)
    experiment_identity = _resolve_experiment_identity(llm_config)
    if experiment_identity:
        llm_config["_resolved_experiment_identity"] = experiment_identity
    shared_pool_capacity = _resolve_vllm_shared_pool_capacity(llm_config)

    if backend_lower == "vllm" and shared_pool_capacity is not None:
        shared_pool_prefix = _build_vllm_pool_prefix(
            llm_config.get("model", "unknown-model"), experiment_identity
        )
        if actor_name_prefix == "ysim_llm":
            actor_name_prefix = shared_pool_prefix

        cleanup_expired_shared_vllm_pools(actor_namespace=actor_namespace, logger=logger)
        registry = _get_or_create_lease_registry(actor_namespace)
        shared_pool_group_key = _build_vllm_shared_group_key(
            llm_config=llm_config,
            actor_namespace=actor_namespace,
            actor_name_prefix=actor_name_prefix,
            num_actors=num_actors,
            actor_backend=actor_backend,
            experiment_identity=experiment_identity,
        )
        reservation = ray.get(
            registry.reserve_shared_vllm_pool.remote(
                shared_pool_group_key,
                _resolve_lease_client_id(llm_config) or llm_config.get("client_name", "unknown"),
                actor_name_prefix,
                actor_backend,
                num_actors,
                shared_pool_capacity,
            )
        )

        actor_name_prefix = reservation["pool_prefix"] or actor_name_prefix
        shared_pool_key = reservation["pool_key"]
        shared_pool_actor_names = list(reservation.get("actor_names") or [])
        shared_pool_is_creator = bool(reservation.get("is_creator"))

        if not shared_pool_is_creator and not shared_pool_actor_names:
            deadline = time.time() + 60
            while time.time() < deadline:
                state = ray.get(
                    registry.get_shared_vllm_pool_state.remote(shared_pool_key)
                )
                shared_pool_actor_names = list(state.get("actor_names") or [])
                if shared_pool_actor_names:
                    break
                time.sleep(0.25)

        if not shared_pool_is_creator and not shared_pool_actor_names:
            try:
                release_llm_pool_lease(
                    backend=actor_backend,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=num_actors,
                    client_id=_resolve_lease_client_id(llm_config)
                    or llm_config.get("client_name", "unknown"),
                    actor_namespace=actor_namespace,
                    logger=logger,
                )
            finally:
                raise RuntimeError(
                    "Timed out waiting for shared vLLM pool initialization"
                )

        if shared_pool_actor_names:
            if len(shared_pool_actor_names) != num_actors and logger:
                logger.warning(
                    f"Shared vLLM pool actor count mismatch for prefix={actor_name_prefix}: "
                    f"expected {num_actors}, found {len(shared_pool_actor_names)}"
                )
            num_actors = len(shared_pool_actor_names)
            reuse_actors = True
            llm_config["_reused_existing_pool"] = not shared_pool_is_creator
        else:
            llm_config["_reused_existing_pool"] = False

        llm_config["_resolved_actor_name_prefix"] = actor_name_prefix
        llm_config["_resolved_num_actors"] = num_actors
        llm_config["_resolved_actor_namespace"] = actor_namespace
        llm_config["_resolved_shared_pool_key"] = shared_pool_key
        llm_config["_resolved_shared_pool_capacity"] = shared_pool_capacity

        try:
            if num_actors == 1:
                if reuse_actors:
                    actor_name = f"{actor_name_prefix}_{actor_backend}_0"
                    actor = ray.get_actor(actor_name, namespace=actor_namespace)
                else:
                    ServiceClass = _get_service_class(service_backend)
                    actor_name = f"{actor_name_prefix}_{actor_backend}_0"
                    options = {"num_gpus": llm_config.get("gpu_per_actor", 1.0), "lifetime": "detached"}
                    options["name"] = actor_name
                    if actor_namespace:
                        options["namespace"] = actor_namespace
                    actor = ServiceClass.options(**options).remote(
                        llm_config=llm_config,
                        prompts_config=prompts_config,
                        llm_v_config=llm_v_config,
                        logging_config=logging_config,
                    )
                    if not shared_pool_actor_names:
                        ray.get(
                            registry.register_shared_vllm_pool_actors.remote(
                                shared_pool_key, [actor_name]
                            )
                        )
                return actor

            if enable_monitoring:
                pool = LLMActorPool(
                    llm_config=llm_config,
                    prompts_config=prompts_config,
                    num_actors=num_actors,
                    strategy=strategy,
                    backend=service_backend,
                    enable_monitoring=True,
                    llm_v_config=llm_v_config,
                    logger=logger,
                    reuse_actors=reuse_actors,
                    actor_name_prefix=actor_name_prefix,
                )
                if not shared_pool_actor_names:
                    actor_names = [
                        f"{actor_name_prefix}_{actor_backend}_{i}"
                        for i in range(num_actors)
                    ]
                    ray.get(
                        registry.register_shared_vllm_pool_actors.remote(
                            shared_pool_key, actor_names
                        )
                    )
                return pool

            balancer = LLMLoadBalancer(
                llm_config=llm_config,
                prompts_config=prompts_config,
                num_actors=num_actors,
                strategy=strategy,
                backend=service_backend,
                llm_v_config=llm_v_config,
                logger=logger,
                reuse_actors=reuse_actors,
                actor_name_prefix=actor_name_prefix,
            )
            if not shared_pool_actor_names:
                actor_names = [
                    f"{actor_name_prefix}_{actor_backend}_{i}" for i in range(num_actors)
                ]
                ray.get(
                    registry.register_shared_vllm_pool_actors.remote(
                        shared_pool_key, actor_names
                    )
                )
            return balancer
        except Exception:
            try:
                actor_names = [
                    f"{actor_name_prefix}_{actor_backend}_{i}" for i in range(num_actors)
                ]
                ray.get(
                    registry.register_shared_vllm_pool_actors.remote(
                        shared_pool_key, actor_names
                    )
                )
            except Exception:
                pass
            try:
                release_llm_pool_lease(
                    backend=actor_backend,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=num_actors,
                    client_id=_resolve_lease_client_id(llm_config)
                    or llm_config.get("client_name", "unknown"),
                    actor_namespace=actor_namespace,
                    logger=logger,
                )
            except Exception:
                pass
            raise

    if backend_lower == "vllm":
        resolved_prefix, existing_count = _discover_existing_vllm_pool(
            llm_config.get("model", "unknown-model"),
            actor_namespace,
            experiment_identity,
            logger,
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
        if actor_namespace:
            llm_config["_resolved_actor_namespace"] = actor_namespace

    # Get GPU allocation per actor (for vLLM)
    gpu_per_actor = llm_config.get("gpu_per_actor", 1.0)

    if num_actors == 1:
        # Single actor - check if we should reuse
        if reuse_actors:
            actor_name = f"{actor_name_prefix}_{actor_backend}_0"
            try:
                actor = ray.get_actor(actor_name, namespace=actor_namespace)
                if logger:
                    logger.info(f"Reused existing single LLM actor: {actor_name}")
                lease_client_id = _resolve_lease_client_id(llm_config)
                if actor_name and lease_client_id:
                    acquire_llm_pool_lease(
                        backend=actor_backend,
                        actor_name_prefix=actor_name_prefix,
                        num_actors=1,
                        client_id=lease_client_id,
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
        if service_backend == "vllm":
            ServiceClass = _get_service_class(service_backend)
            actor_name = f"{actor_name_prefix}_{actor_backend}_0"
            options = {"num_gpus": gpu_per_actor, "lifetime": "detached"}
            if actor_name:
                options["name"] = actor_name
            if actor_namespace:
                options["namespace"] = actor_namespace

            actor = ServiceClass.options(**options).remote(
                llm_config=llm_config,
                prompts_config=prompts_config,
                llm_v_config=llm_v_config,
                logging_config=logging_config,
            )
            lease_client_id = _resolve_lease_client_id(llm_config)
            if actor_name and lease_client_id:
                acquire_llm_pool_lease(
                    backend=actor_backend,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=1,
                    client_id=lease_client_id,
                    actor_names=[actor_name],
                    actor_namespace=actor_namespace,
                    logger=logger,
                )
            return actor
        else:
            ServiceClass = _get_service_class(service_backend)
            actor_name = f"{actor_name_prefix}_{actor_backend}_0" if reuse_actors else None
            options = {"lifetime": "detached"} if reuse_actors else {}
            if actor_name:
                options["name"] = actor_name
            if actor_namespace:
                options["namespace"] = actor_namespace

            actor = ServiceClass.options(**options).remote(
                llm_config=llm_config,
                prompts_config=prompts_config,
                llm_v_config=llm_v_config,
                logging_config=logging_config,
            )
            lease_client_id = _resolve_lease_client_id(llm_config)
            if actor_name and reuse_actors and lease_client_id:
                acquire_llm_pool_lease(
                    backend=actor_backend,
                    actor_name_prefix=actor_name_prefix,
                    num_actors=1,
                    client_id=lease_client_id,
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
            backend=service_backend,
            enable_monitoring=True,
            llm_v_config=llm_v_config,
            logger=logger,
            reuse_actors=reuse_actors,
            actor_name_prefix=actor_name_prefix,
        )
        lease_client_id = _resolve_lease_client_id(llm_config)
        if lease_client_id:
            actor_names = [f"{actor_name_prefix}_{actor_backend}_{i}" for i in range(num_actors)]
            acquire_llm_pool_lease(
                backend=actor_backend,
                actor_name_prefix=actor_name_prefix,
                num_actors=num_actors,
                client_id=lease_client_id,
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
            backend=service_backend,
            llm_v_config=llm_v_config,
            logger=logger,
            reuse_actors=reuse_actors,
            actor_name_prefix=actor_name_prefix,
        )
        lease_client_id = _resolve_lease_client_id(llm_config)
        if lease_client_id:
            actor_names = [f"{actor_name_prefix}_{actor_backend}_{i}" for i in range(num_actors)]
            acquire_llm_pool_lease(
                backend=actor_backend,
                actor_name_prefix=actor_name_prefix,
                num_actors=num_actors,
                client_id=lease_client_id,
                actor_names=actor_names,
                actor_namespace=actor_namespace,
                logger=logger,
            )
        return balancer
