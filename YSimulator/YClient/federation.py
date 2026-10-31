"""Client side of the federation (F3.4c, opt-in): which agents may act, and the agent's choice to cross-post.

With the `federation` section of the client simulation configuration absent or `enabled: false` every function here does
nothing: no call to the server, no random draw (INV-01).

- inactive_ids(server): local ids of the agents that are not active on the platform (dormant or left); the scheduler
  treats them like churned agents, so they are not sampled and do not act.
- mark_posts(actions): sets `crosspost = True` on the POST actions whose agent chose to cross-post (D-07): a Bernoulli
  draw with `federation.crosspost_propensity` (default 0 = never) from a generator of its own (`federation.seed`)."""

from __future__ import annotations

import random

_state = {"enabled": False, "propensity": 0.0, "rng": None, "inactive": set(), "attention": {}}


def install(config):
    """Read config["federation"]; call once when the client starts."""
    section = (config or {}).get("federation") or {}
    enabled = bool(section.get("enabled"))
    _state.update(enabled=enabled, propensity=0.0, rng=None, inactive=set(), attention={})
    if enabled:
        _state.update(propensity=float(section.get("crosspost_propensity", 0.0)), rng=random.Random(section.get("seed", 0)))
    return enabled


def enabled():
    return bool(_state["enabled"])


def inactive_ids(server):
    """Ids that must not act now (the last known list when the server cannot be reached)."""
    if not _state["enabled"]:
        return set()
    try:
        import ray

        _state["inactive"] = set(ray.get(server.get_federation_inactive_agents.remote()))
    except Exception:  # noqa: BLE001 - keep the last known list
        pass
    return set(_state["inactive"])


def refresh_attention(server):
    """Read the attention multipliers of the day from the server (the last known ones when it cannot be reached)."""
    if not _state["enabled"]:
        return
    try:
        import ray

        _state["attention"] = {str(k): float(v) for k, v in ray.get(server.get_federation_attention.remote()).items()}
    except Exception:  # noqa: BLE001 - keep the last known multipliers
        pass


def scale_actions(n, agent_id):
    """Number of actions of the agent in the slot after the attention multiplier of the federation (F4.3).

    Exactly `n` when the federation is off or the multiplier is 1 (nothing is drawn); otherwise `n * m` rounded at random
    with the generator of this module, so the global one is untouched. A multiplier below 1 can bring it to 0 (the agent
    does not act in the slot), one above 1 never below `n`."""
    m = _state["attention"].get(str(agent_id), 1.0) if _state["enabled"] else 1.0
    if m == 1.0:
        return n
    x = n * m
    whole = int(x)
    k = whole if x == whole else whole + (1 if _state["rng"].random() < x - whole else 0)  # an exact count draws nothing
    return max(n if m > 1.0 else 0, k)


def mark_posts(actions):
    """Flag the POST actions the agents chose to cross-post."""
    if not _state["enabled"] or _state["propensity"] <= 0.0:
        return actions
    for act in actions:
        if getattr(act, "action_type", None) == "POST" and _state["rng"].random() < _state["propensity"]:
            act.crosspost = True
    return actions
