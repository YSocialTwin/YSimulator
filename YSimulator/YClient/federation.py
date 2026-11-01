"""Client side of the federation (F3.4c, opt-in): which agents may act, and the agent's choice to cross-post.

With the `federation` section of the client simulation configuration absent or `enabled: false` every function here does
nothing: no call to the server, no random draw (INV-01).

- inactive_ids(server): local ids of the agents that are not active on the platform (dormant or left); the scheduler
  treats them like churned agents, so they are not sampled and do not act.
- mark_posts(actions): sets `crosspost = True` on the POST actions whose agent chose to cross-post (D-07): a Bernoulli
  draw with `federation.crosspost_propensity` (default 0 = never) from a generator of its own (`federation.seed`)."""

from __future__ import annotations

import random
import re

_state = {"enabled": False, "propensity": 0.0, "rng": None, "inactive": set(), "attention": {},
          "mode": "coordinator_rule", "member": None, "adapt": None}

# Longest text each destination accepts (characters); the rules and the parser of an LLM reply both apply them.
LIMITS = {"microblogging": 280, "forum": 2000, "photo_sharing": 300, "instant_messaging": 400, "dating": 200}


def install(config):
    """Read config["federation"]; call once when the client starts."""
    section = (config or {}).get("federation") or {}
    enabled = bool(section.get("enabled"))
    _state.update(enabled=enabled, propensity=0.0, rng=None, inactive=set(), attention={},
                  mode="coordinator_rule", member=None, adapt=None)
    if enabled:
        _state.update(propensity=float(section.get("crosspost_propensity", 0.0)), rng=random.Random(section.get("seed", 0)),
                      mode=str(section.get("crosspost_mode") or "coordinator_rule"), member=section.get("member"))
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


def agent_action():
    """True when the agent itself chooses where to cross-post and with which text (crosspost.mode = agent_action)."""
    return bool(_state["enabled"]) and _state["mode"] == "agent_action"


def set_adapt(fn):
    """fn(agent_id, dest, text) -> the model's version of the text for the destination (None: use the rule text)."""
    _state["adapt"] = fn


def destinations(server, agent_id):
    """Platforms where this agent can post now (the server tells; empty when it cannot be reached)."""
    try:
        import ray

        return sorted(str(m) for m in ray.get(server.get_federation_destinations.remote(str(agent_id))))
    except Exception:  # noqa: BLE001 - no destination known: no cross-post this time
        return []


def source_platform():
    return _state["member"] or "another platform"


def adapt_prompt_key(dest):
    """Prompt-store key that adapts a text for the destination platform (None for a platform without one)."""
    return f"crosspost_adapt_{dest}" if dest in LIMITS else None


def _cut(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    return (cut.rsplit(" ", 1)[0] if " " in cut[-30:] else cut).rstrip(",;:- ")


def rule_text(dest, text):
    """The text for the destination without an LLM: the same words, shaped and cut for the platform."""
    text = " ".join(str(text or "").split()) if dest != "forum" else str(text or "").strip()
    if dest == "forum" and "\n" not in text:
        title = _cut(re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0], 80)
        return f"{title}\n{text}"[:LIMITS["forum"]]
    return _cut(text, LIMITS.get(dest, 280))


def parse_reply(dest, reply, fallback=None):
    """Clean the reply of a model asked to adapt a text: no reasoning block, fences, labels or quotes; at most the
    platform limit; for a forum a title line then a body. The fallback (default: nothing) when little is left."""
    text = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.S | re.I)
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.M).strip()
    text = re.sub(r"^(post|caption|message|text|testo|didascalia|messaggio|frase)\s*:\s*", "", text, flags=re.I).strip()
    if len(text) >= 2 and (text[0], text[-1]) in {('"', '"'), ("'", "'"), ("\u201c", "\u201d"), ("\u00ab", "\u00bb")}:
        text = text[1:-1].strip()
    if dest == "forum":
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return fallback
        title = re.sub(r"^(title|titolo)\s*:\s*|^#+\s*", "", lines[0], flags=re.I).strip()
        body = " ".join(re.sub(r"^(body|corpo)\s*:\s*", "", ln, flags=re.I) for ln in lines[1:]).strip()
        if not title:
            return fallback
        return _cut(f"{_cut(title, 120)}\n{body or title}", LIMITS["forum"])
    text = " ".join(text.split())
    if len(text) < 3:
        return fallback
    return _cut(text, LIMITS.get(dest, 280))


def crosspost_targets(server, agent_id, text):
    """[{"member", "text"}]: where this agent decided to post its text. One draw per destination (sorted) with
    `federation.crosspost_propensity`, from the generator of this module."""
    if not agent_action() or _state["propensity"] <= 0.0 or not str(text or "").strip():
        return []
    out = []
    for dest in destinations(server, agent_id):
        if _state["rng"].random() >= _state["propensity"]:
            continue
        adapt = _state["adapt"]
        version = adapt(agent_id, dest, text) if adapt is not None else None
        out.append({"member": dest, "text": version or rule_text(dest, text)})
    return out


def mark_posts(actions, server=None):
    """Flag the POST actions the agents chose to cross-post (agent_action: with the destinations and the texts)."""
    if not _state["enabled"] or _state["propensity"] <= 0.0:
        return actions
    for act in actions:
        if getattr(act, "action_type", None) != "POST":
            continue
        if _state["mode"] == "agent_action":
            targets = crosspost_targets(server, getattr(act, "agent_id", None), getattr(act, "content", None)) if server is not None else []
            if targets:
                act.crosspost, act.crosspost_to = True, targets
        elif _state["rng"].random() < _state["propensity"]:
            act.crosspost = True
    return actions
