"""
Ray actor resolution helpers for YSimulator clients.

These helpers keep named actor discovery consistent across the client and
support services, especially in batch runs where the orchestrator may not be
available the instant a client actor starts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import ray


def _resolve_runtime_namespace(namespace: Optional[str]) -> Optional[str]:
    """Return the namespace to use for actor discovery."""
    if namespace:
        return namespace

    try:
        return ray.get_runtime_context().namespace
    except Exception:
        return None


def resolve_named_actor(
    actor_name: str,
    *,
    namespace: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    wait_seconds: float = 60.0,
    poll_interval: float = 2.0,
    raise_on_timeout: bool = False,
) -> Any:
    """
    Resolve a Ray named actor, retrying for a bounded period when unavailable.

    Args:
        actor_name: Ray actor name to resolve.
        namespace: Optional Ray namespace. When omitted, the current runtime
            namespace is used.
        logger: Optional logger for wait-time diagnostics.
        wait_seconds: Maximum number of seconds to wait before giving up.
        poll_interval: Delay between retries.
        raise_on_timeout: When True, raise RuntimeError after timeout instead
            of returning None.

    Returns:
        The resolved Ray actor handle, or None on timeout when
        ``raise_on_timeout`` is False.
    """
    resolved_namespace = _resolve_runtime_namespace(namespace)
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    attempt = 0
    last_error: Optional[Exception] = None

    while True:
        attempt += 1
        try:
            if resolved_namespace:
                return ray.get_actor(actor_name, namespace=resolved_namespace)
            return ray.get_actor(actor_name)
        except ValueError as exc:
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            if logger:
                logger.debug(
                    f"Orchestrator actor '{actor_name}' not yet available "
                    f"(attempt {attempt}, namespace={resolved_namespace or 'default'})"
                )
            time.sleep(min(float(poll_interval), max(0.1, remaining)))

    message = (
        f"Unable to resolve Ray actor '{actor_name}'"
        f"{f' in namespace {resolved_namespace!r}' if resolved_namespace else ''}"
        f" after {wait_seconds:.1f}s"
    )
    if raise_on_timeout:
        raise RuntimeError(message) from last_error
    if logger:
        logger.warning(message)
    return None
