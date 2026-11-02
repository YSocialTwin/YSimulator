"""Client side of the federation (F3.4c, opt-in): which agents may act, and the agent's choice to cross-post.

With the `federation` section of the client simulation configuration absent or `enabled: false` every function here does
nothing: no call to the server, no random draw (INV-01).

- inactive_ids(server): local ids of the agents that are not active on the platform (dormant or left); the scheduler
  treats them like churned agents, so they are not sampled and do not act.
- mark_posts(actions): sets `crosspost = True` on the POST actions whose agent chose to cross-post (D-07): a Bernoulli
  draw with `federation.crosspost_propensity` (default 0 = never) from a generator of its own (`federation.seed`)."""

from __future__ import annotations

import json
import logging
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor

_state = {"enabled": False, "propensity": 0.0, "rng": None, "inactive": set(), "attention": {},
          "mode": "coordinator_rule", "member": None, "adapt": None, "adopt": False, "decision": "random",
          "triggers": ("publish",), "max_per_day": 5, "content": frozenset(), "counts": {}, "decider": None}

# Longest text each destination accepts (characters); the rules and the parser of an LLM reply both apply them.
LIMITS = {"microblogging": 280, "forum": 2000, "photo_sharing": 300, "instant_messaging": 400, "dating": 200}


def install(config):
    """Read config["federation"]; call once when the client starts."""
    section = (config or {}).get("federation") or {}
    enabled = bool(section.get("enabled"))
    _state.update(enabled=enabled, propensity=0.0, rng=None, inactive=set(), attention={},
                  mode="coordinator_rule", member=None, adapt=None, adopt=False, decision="random",
                  triggers=("publish",), max_per_day=5, content=frozenset(), counts={}, decider=None)
    if enabled:
        _state.update(propensity=float(section.get("crosspost_propensity", 0.0)), rng=random.Random(section.get("seed", 0)),
                      mode=str(section.get("crosspost_mode") or "coordinator_rule"), member=section.get("member"),
                      adopt=bool(section.get("adopt")))
        _state.update(read_decision(section))
        _state["triggers"] = tuple(t for t in _state["triggers"] if t in SUPPORTED_TRIGGERS)
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


def adopt_provisioned(server, client_id, agent_profiles):
    """INV-19: accounts the server created because an agent of another platform decided to join this one get an agent here.

    Only with `federation.adopt` in the client configuration. The server lists the profiles of the accounts this client has to play
    (`get_federation_provisioned`, without the ids in `agent_profiles`); they are reported as adopted and appended to
    `agent_profiles` (the list the scheduler, the executor and the lifecycle manager share), so they act from the next slot like
    any other agent. They are registered on the server already. Returns the number adopted; never raises for an unreachable server
    (asked again at the next slot)."""
    if not (_state["enabled"] and _state["adopt"]):
        return 0
    try:
        import ray

        known = {str(a.id) for a in agent_profiles}
        fresh = [p for p in ray.get(server.get_federation_provisioned.remote(client_id, sorted(known))) if str(p.id) not in known]
        if not fresh:
            return 0
        ray.get(server.federation_adopted.remote(client_id, [str(p.id) for p in fresh]))  # before: a failure here is retried
        agent_profiles.extend(fresh)
        return len(fresh)
    except Exception:  # noqa: BLE001 - try again at the next slot
        return 0


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


def _draw_fields(server, agent_id, text):
    """The Bernoulli draw of the cross-post choice of one POST action (crosspost.decision = random, and the fallback of llm)."""
    if not _state["enabled"] or _state["propensity"] <= 0.0:
        return {}
    if _state["mode"] == "agent_action":
        targets = crosspost_targets(server, agent_id, text) if server is not None else []
        return {"crosspost": True, "crosspost_to": targets} if targets else {}
    return {"crosspost": True} if _state["rng"].random() < _state["propensity"] else {}


def set_decider(fn, has_model=None):
    """fn(agent_id, trigger, text, destination_lines, context) -> the raw reply of the model of that agent. `has_model(agent_id)`
    is False for an agent without a model: it keeps the Bernoulli draw and is never asked. Set by the client when
    crosspost.decision = llm."""
    _state["decider"], _state["has_model"] = fn, has_model


def _asker(agent_id):
    decider, has_model = _state["decider"], _state.get("has_model")
    if decider is None or (has_model is not None and not has_model(agent_id)):
        return None
    return lambda trigger, text, lines, context: decider(agent_id, trigger, text, lines, context)


def mark_posts(actions, server=None, day=None):
    """Flag the POST actions the agents chose to cross-post (agent_action: with the destinations and the texts).

    With crosspost.decision = llm (trigger `publish`; the `interaction` trigger is not supported by this client: its
    shares are never exported) the model of each agent decides, one call per POST in parallel and each bounded by
    DECISION_TIMEOUT; any failure falls back to the Bernoulli draw. `day` is the simulated day (cap per agent per day)."""
    if not _state["enabled"]:
        return actions
    llm = decision_for("publish") and _state["decider"] is not None
    if not llm and _state["propensity"] <= 0.0:
        return actions
    posts = [a for a in actions if getattr(a, "action_type", None) == "POST"]
    decided = {}
    if llm and posts:
        def one(act):
            agent_id = getattr(act, "agent_id", None)
            return decide(agent_id, getattr(act, "content", None), "publish", _asker(agent_id), day=day,
                          dests=(lambda: destinations(server, agent_id)) if server is not None else [])
        with ThreadPoolExecutor(max_workers=min(8, len(posts))) as pool:
            decided = dict(zip((id(a) for a in posts), pool.map(one, posts)))
    for act in posts:
        agent_id, text = getattr(act, "agent_id", None), getattr(act, "content", None)
        verdict = decided.get(id(act))
        if verdict is not None and verdict["source"] != "fallback":
            adapt = _state["adapt"]
            fields = decision_fields(verdict, agent_id, text, (lambda d, t, a=agent_id: adapt(a, d, t)) if adapt else None)
        else:
            fields = _draw_fields(server, agent_id, text)
            if verdict is not None:
                note_fallback(agent_id, "publish", fields, verdict["reason"])
        if fields:
            act.crosspost = True
            if "crosspost_to" in fields:
                act.crosspost_to = fields["crosspost_to"]
    return actions


# --- P14: the agent decides whether to cross-post (crosspost.decision = llm) --------------------------------------------
# `random` (default) is the Bernoulli draw above, unchanged. With `llm` an LLM agent is asked, ONCE per event, whether to
# cross-post the content it just published (trigger `publish`) or interacted with (trigger `interaction`) and, with
# crosspost.mode = agent_action, towards which platforms. Any failure falls back to the draw, so a run never stalls.
DECISIONS = ("random", "llm")
TRIGGERS = ("publish", "interaction")
SUPPORTED_TRIGGERS = ("publish",)  # this client exports no share: only the publish trigger is decided
DEFAULT_MAX_PER_DAY = 5  # model calls per agent per simulated day (0 = no limit)
DECISION_TIMEOUT = 60.0  # seconds a decision may take before the draw is used instead
ROUNDS_PER_DAY = 24  # World Simulation: simulated clock with hourly slots
URL_RE = re.compile(r"https?://\S+", re.I)
_CONTENT_ALIASES = {"own_posts": "own_content"}
_TRUE = {"true", "yes", "si", "sì", "1"}
_FALSE = {"false", "no", "0"}
log = logging.getLogger("YSimulator.federation")
_lock = threading.Lock()
_stats = {"llm": 0, "fallback": 0, "skipped": 0, "crossposts_llm": 0}


def decision_stats():
    """Counters of this process: decisions taken by the model, fallbacks to the draw, skipped events and cross-posts the model chose."""
    return dict(_stats)


def _content_options(content):
    names = {_CONTENT_ALIASES.get(str(c), str(c)) for c in (content or ())}
    return frozenset() if (not names or "all" in names) else frozenset(names)


def _eligible(text, own=True, has_image=False):
    """Client-side view of crosspost.content (the coordinator stays the authority): False only when the agent's OWN content
    can certainly not be eligible. The content of others is left to the coordinator (it knows the link and the image)."""
    opts = _state["content"]
    if not opts or not own or "own_content" in opts:
        return True
    return ("news" in opts and bool(URL_RE.search(str(text or "")))) or ("images" in opts and bool(has_image))


def parse_decision(reply, allowed):
    """The decision in a model reply: {"crosspost": bool, "destinations": [allowed names, in the order of `allowed`],
    "text": {destination: cleaned text}}, or None when there is no valid JSON object with a boolean `crosspost`.
    Unknown destinations are ignored; texts are cleaned and cut like an adaptation (`parse_reply`)."""
    raw = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.S | re.I)
    decoder, obj = json.JSONDecoder(), None
    for match in re.finditer(r"\{", raw):
        try:
            found, _ = decoder.raw_decode(raw[match.start():])
        except ValueError:
            continue
        if isinstance(found, dict) and "crosspost" in found:
            obj = found
            break
    if obj is None:
        return None
    flag = obj["crosspost"]
    if isinstance(flag, str):
        flag = True if flag.strip().lower() in _TRUE else False if flag.strip().lower() in _FALSE else None
    if not isinstance(flag, bool):
        return None
    asked = obj.get("destinations")
    asked = [str(d).strip().lower() for d in asked] if isinstance(asked, list) else []
    dests = [d for d in allowed if d in asked]
    texts = obj.get("text") if isinstance(obj.get("text"), dict) else {}
    out = {}
    for dest in dests:
        value = next((v for k, v in texts.items() if str(k).strip().lower() == dest), None)
        cleaned = parse_reply(dest, value) if isinstance(value, str) else None
        if cleaned:
            out[dest] = cleaned
    return {"crosspost": flag, "destinations": dests, "text": out}


def destination_lines(dests):
    """The destinations as lines for the prompt: `- forum (2000)`, the number being the longest text in characters."""
    return "\n".join(f"- {d} ({LIMITS.get(d, 280)})" for d in dests)


def _ask_with_timeout(ask, args, timeout):
    box = {}

    def run():
        try:
            box["reply"] = ask(*args)
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"no decision within {timeout}s")
    if "error" in box:
        raise box["error"]
    return box.get("reply")


def _note(user_id, trigger, source, crosspost, dests, reason=""):
    """One log line per decision, the record YWeb analytics read: `federation_decision agent=.. trigger=.. source=llm|fallback
    crosspost=0|1 destinations=a,b [reason=..]`. For `fallback` the crosspost value is the outcome of the Bernoulli draw."""
    _stats[source] += 1
    if crosspost and source == "llm":
        _stats["crossposts_llm"] += 1
    log.info("federation_decision agent=%s trigger=%s source=%s crosspost=%d destinations=%s%s", user_id, trigger, source,
             1 if crosspost else 0, ",".join(dests), f" reason={reason}" if reason else "")


def note_fallback(user_id, trigger, fields, reason):
    """Log a decision that fell back to the Bernoulli draw (`fields` are the ones the draw produced) and say why."""
    to = [t["member"] for t in fields.get("crosspost_to", [])]
    _note(user_id, trigger, "fallback", bool(fields.get("crosspost")), to, reason)


def decision_for(trigger):
    """True when this event is decided by the model: crosspost.decision = llm and the trigger is selected."""
    return bool(_state["enabled"]) and _state["decision"] == "llm" and trigger in _state["triggers"]


def _precheck(user_id, text, trigger, own, has_image, dests, round_id, day):
    """What can be said before asking the model: {"source": "skip"} (no destination, content not eligible: nothing to do),
    {"source": "fallback", "reason": "cap"} (the agent used its calls of the day) or None (ask the model)."""
    if not dests or not _eligible(text, own, has_image):
        _stats["skipped"] += 1
        return {"source": "skip", "crosspost": False, "destinations": [], "text": {}}
    cap = int(_state["max_per_day"])
    try:  # the simulated day: given (clients that know it) or derived from the round id (hourly slots)
        which = int(day) if day is not None else (int(round_id) // ROUNDS_PER_DAY if round_id is not None else None)
    except (TypeError, ValueError):
        which = None
    if cap > 0 and which is not None:
        with _lock:
            if _state["counts"].get((user_id, which), 0) >= cap:
                return {"source": "fallback", "reason": "cap"}
            _state["counts"] = {k: v for k, v in _state["counts"].items() if k[1] >= which - 1}  # keep today and yesterday
            _state["counts"][(user_id, which)] = _state["counts"].get((user_id, which), 0) + 1
    return None


def _failed(exc):
    return {"source": "fallback", "reason": "timeout" if isinstance(exc, TimeoutError) else f"error:{type(exc).__name__}"}


def _conclude(user_id, trigger, reply, dests):
    """The decision in the reply of the model (see `decide`); a reply that cannot be read is a fallback."""
    parsed = parse_decision(reply, dests)
    if parsed is None:
        return {"source": "fallback", "reason": "invalid"}
    if _state["mode"] == "agent_action":  # the model chooses the destinations; none valid means no cross-post
        parsed["crosspost"] = bool(parsed["crosspost"] and parsed["destinations"])
    else:  # coordinator_rule: the model only marks the content, the coordinator's probabilities choose where it goes
        parsed["destinations"], parsed["text"] = [], {}
    _note(user_id, trigger, "llm", parsed["crosspost"], parsed["destinations"])
    return dict(parsed, source="llm")


def decide(user_id, text, trigger, ask, round_id=None, own=True, has_image=False, context=None, dests=None, day=None):
    """The model's decision for one event, or None when this event is not decided by a model (random mode, trigger not
    selected, rule-based agent: `ask` is None, nothing to say): the caller keeps the Bernoulli draw as before.

    Otherwise {"source": "skip"} (no destination, content not eligible: no call, nothing to do), {"source": "fallback",
    "reason": ..} (cap reached, timeout, model error, invalid JSON: the caller makes the draw and calls `note_fallback`) or
    {"source": "llm", "crosspost": bool, "destinations": [...], "text": {...}}. At most ONE call to `ask(trigger, text,
    destination_lines, context)` per event and `decision_max_per_day` per agent per day; the Bernoulli generator is not used."""
    if not decision_for(trigger) or ask is None or user_id is None or not str(text or "").strip():
        return None
    dests = destinations(user_id) if dests is None else (dests() if callable(dests) else list(dests))
    early = _precheck(user_id, text, trigger, own, has_image, dests, round_id, day)
    if early is not None:
        return early
    try:
        reply = _ask_with_timeout(ask, (trigger, text, destination_lines(dests), context), DECISION_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - a failing or slow model must not stop the agent
        return _failed(exc)
    return _conclude(user_id, trigger, reply, dests)


def decision_fields(decided, user_id, text, adapt=None):
    """The /post or /share fields for a model decision (`decide` returned source `llm` or `skip`)."""
    if not decided.get("crosspost"):
        return {}
    if _state["mode"] != "agent_action":
        return {"crosspost": True}
    targets = []
    for dest in decided["destinations"]:
        version = decided["text"].get(dest) or (adapt(dest, text) if adapt is not None else None)
        targets.append({"member": dest, "text": version or rule_text(dest, text)})
    return {"crosspost": True, "crosspost_to": targets}


def read_decision(section):
    """The decision settings of a member `federation` section (invalid values are logged and mean the default)."""
    decision = str(section.get("crosspost_decision") or "random")
    if decision not in DECISIONS:
        log.warning("federation: unknown crosspost_decision %r, using 'random'", decision)
        decision = "random"
    asked = section.get("crosspost_decision_triggers")
    triggers = tuple(t for t in TRIGGERS if t in asked) if isinstance(asked, (list, tuple)) else TRIGGERS
    try:
        cap = max(0, int(section.get("crosspost_decision_max_per_day", DEFAULT_MAX_PER_DAY)))
    except (TypeError, ValueError):
        cap = DEFAULT_MAX_PER_DAY
    return {"decision": decision, "triggers": triggers, "max_per_day": cap,
            "content": _content_options(section.get("crosspost_content")), "counts": {}}
