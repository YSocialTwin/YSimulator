"""
Client-side memory integration for YSimulator.

The memory engine runs entirely in the client actor. Database access still goes
through the server actor, and no server-side LLM or embedding calls are added.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

import ray


def _load_memory_package():
    try:
        from yclient_memory import (
            BrowseMemoryRequest,
            CommentMemoryEvent,
            MaintenanceTickRequest,
            PostMemoryEvent,
            PostStyleRequest,
            ReplyMemoryRequest,
            VoteMemoryEvent,
            build_memory_engine,
        )
        from yclient_memory.config import MemoryConfig
    except ImportError as exc:
        raise RuntimeError(
            "The external memory integration requires the pip package "
            "'yclient-memory'. Install it before enabling agent memory."
        ) from exc
    return {
        "BrowseMemoryRequest": BrowseMemoryRequest,
        "CommentMemoryEvent": CommentMemoryEvent,
        "MaintenanceTickRequest": MaintenanceTickRequest,
        "PostMemoryEvent": PostMemoryEvent,
        "PostStyleRequest": PostStyleRequest,
        "ReplyMemoryRequest": ReplyMemoryRequest,
        "VoteMemoryEvent": VoteMemoryEvent,
        "MemoryConfig": MemoryConfig,
        "build_memory_engine": build_memory_engine,
    }


class YSimulatorMemoryRuntime:
    """
    Runtime bridge exposed to yclient-memory engines.

    yclient-memory expects integer IDs. YSimulator uses UUID strings, so this
    runtime keeps reversible surrogate mappings for posts and users.

    Contract:
    - DB access: all persistence is routed through the server actor via
      ``YSimulatorMemoryManager._server_memory_call``; this class never opens
      a direct database connection.
    - LLM access: ``llm_text`` and ``llm_json`` delegate to the client-side
      LLM manager via the ``_llm_provider`` callback.  The server never
      performs LLM calls for memory operations.
    """

    def __init__(self, client, logger: Optional[logging.Logger] = None):
        self.client = client
        self.server = client.server
        self.logger = logger or logging.getLogger(__name__)
        self._user_str_to_int: Dict[str, int] = {}
        self._user_int_to_str: Dict[int, str] = {}
        self._post_str_to_int: Dict[str, int] = {}
        self._post_int_to_str: Dict[int, str] = {}
        self._post_cache: Dict[str, dict] = {}
        self._user_cache: Dict[str, dict] = {}
        self._round_cache: Dict[str, dict] = {}
        # Optional client-side LLM provider.  Set by YSimulatorMemoryManager
        # so that llm_text / llm_json calls stay on the client, never on the
        # server.  Signature: (prompt_key: str, variables: dict, as_json: bool)
        # -> str | dict
        self._llm_provider = None

    def _stable_int(self, value: str, namespace: str) -> int:
        digest = hashlib.sha1(f"{namespace}:{value}".encode("utf-8")).hexdigest()
        return int(digest[:15], 16)

    def intern_user_id(self, user_id: Optional[str]) -> Optional[int]:
        if not user_id:
            return None
        user_id = str(user_id)
        if user_id not in self._user_str_to_int:
            surrogate = self._stable_int(user_id, "user")
            self._user_str_to_int[user_id] = surrogate
            self._user_int_to_str[surrogate] = user_id
        return self._user_str_to_int[user_id]

    def intern_post_id(self, post_id: Optional[str]) -> Optional[int]:
        if not post_id:
            return None
        post_id = str(post_id)
        if post_id not in self._post_str_to_int:
            surrogate = self._stable_int(post_id, "post")
            self._post_str_to_int[post_id] = surrogate
            self._post_int_to_str[surrogate] = post_id
        return self._post_str_to_int[post_id]

    def _resolve_post_id(self, post_id: Optional[int]) -> Optional[str]:
        if post_id is None:
            return None
        return self._post_int_to_str.get(int(post_id))

    def _fetch_post(self, post_id: str) -> Optional[dict]:
        if post_id in self._post_cache:
            return self._post_cache[post_id]
        post = ray.get(self.server.get_post.remote(post_id, client_id=self.client.client_id))
        if isinstance(post, dict):
            self._post_cache[post_id] = post
            self.intern_post_id(post_id)
            self.intern_user_id(post.get("user_id"))
            return post
        return None

    def _fetch_user(self, user_id: str) -> Optional[dict]:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        user = ray.get(self.server.get_user.remote(user_id, client_id=self.client.client_id))
        if isinstance(user, dict):
            self._user_cache[user_id] = user
            self.intern_user_id(user_id)
            return user
        return None

    def _fetch_round_info(self, round_uuid: Optional[str]) -> Optional[dict]:
        if not round_uuid:
            return None
        if round_uuid in self._round_cache:
            return self._round_cache[round_uuid]
        info = ray.get(self.server.get_round_info.remote(round_uuid))
        if isinstance(info, dict):
            self._round_cache[round_uuid] = info
            return info
        return None

    def get_author_id_and_username(self, post_id: int):
        original_post_id = self._resolve_post_id(post_id)
        if not original_post_id:
            return None, None
        post = self._fetch_post(original_post_id)
        if not post:
            return None, None
        author_id = str(post.get("user_id") or "")
        author = self._fetch_user(author_id) if author_id else None
        return self.intern_user_id(author_id), (author or {}).get("username")

    def get_thread_root_id(self, post_id: int):
        original_post_id = self._resolve_post_id(post_id)
        if not original_post_id:
            return None
        post = self._fetch_post(original_post_id)
        if not post:
            return None
        root_id = str(post.get("thread_id") or original_post_id)
        return self.intern_post_id(root_id)

    def get_recent_root_posts(self, round_id: int, limit: int = 24, rounds_back: int = 18):
        current_round = int(round_id)
        rows: List[dict] = []
        for post_id in reversed(self.client.get_recent_post_ids() or []):
            post = self._fetch_post(str(post_id))
            if not post or post.get("comment_to"):
                continue
            round_info = self._fetch_round_info(post.get("round"))
            post_round = current_round
            if round_info:
                post_round = self.client.round_number(
                    round_info.get("day", 0), round_info.get("hour", 0)
                )
            if current_round - int(post_round) > int(rounds_back):
                continue
            rows.append(
                {
                    "id": self.intern_post_id(str(post.get("id") or post_id)),
                    "round": int(post_round),
                    "user_id": self.intern_user_id(str(post.get("user_id") or "")),
                    "tweet": post.get("tweet") or post.get("text") or "",
                    "news_id": post.get("news_id"),
                    "image_post_id": post.get("image_post_id"),
                    "image_id": post.get("image_id"),
                }
            )
            if len(rows) >= int(limit):
                break
        return list(reversed(rows))

    def get_post_text(self, post_id: int):
        original_post_id = self._resolve_post_id(post_id)
        if not original_post_id:
            return ""
        post = self._fetch_post(original_post_id)
        if not post:
            return ""
        return post.get("tweet") or post.get("text") or ""

    def persona_snapshot(self):
        return {}

    def llm_json(self, prompt_key, variables, config=None):
        # Enforce contract: LLM calls must stay on the client side.
        # Delegate to the client-supplied provider when available.
        if self._llm_provider is not None:
            try:
                result = self._llm_provider(prompt_key, variables or {}, as_json=True)
                if isinstance(result, dict):
                    return result
            except Exception as exc:
                self.logger.debug(f"llm_json provider call failed for '{prompt_key}': {exc}")
        return {}

    def llm_text(self, prompt_key, variables, config=None):
        # Enforce contract: LLM calls must stay on the client side.
        # Delegate to the client-supplied provider when available.
        if self._llm_provider is not None:
            try:
                result = self._llm_provider(prompt_key, variables or {}, as_json=False)
                if isinstance(result, str):
                    return result
                if isinstance(result, dict):
                    return str(result.get("text") or "")
            except Exception as exc:
                self.logger.debug(f"llm_text provider call failed for '{prompt_key}': {exc}")
        return ""

    def decision_log(self, payload):
        self.logger.debug("memory decision", extra={"extra_data": {"memory": payload}})
        return None


class YSimulatorMemoryManager:
    """Per-client coordinator for agent memory engines.

    Contract:
    - All database reads/writes are routed through the server actor.
      No direct DB connection is opened here or in ``YSimulatorMemoryRuntime``.
    - All LLM calls are performed on the client side through the
      ``_llm_provider`` callback injected into the runtime.  The server
      never invokes an LLM for memory operations.
    """

    def __init__(self, client, simulation_config: Optional[dict] = None):
        self.client = client
        self.logger = client.logger
        self.simulation_config = simulation_config or {}
        self.agent_memory_config = dict((self.simulation_config or {}).get("agents", {}))
        self._enabled = bool(self.agent_memory_config.get("memory_enabled", False))
        self.run_id = self._resolve_run_id()
        self._pkg = _load_memory_package() if self._enabled else None
        self.runtime = YSimulatorMemoryRuntime(client, logger=self.logger)
        # Wire the client-side LLM into the runtime so llm_text/llm_json calls
        # stay on the client (enforcing the client/server contract).
        self.runtime._llm_provider = self._client_llm_provider()
        self._engines: Dict[str, Any] = {}
        self._agent_is_llm: Dict[str, bool] = {}
        self._active_recent_post_ids: List[str] = []
        self._refresh_agent_flags()
        if self._enabled:
            self.logger.info(
                "Memory runtime enabled",
                extra={
                    "extra_data": {
                        "run_id": self.run_id,
                        "backend": self.agent_memory_config.get("memory_backend", "hybrid_semantic"),
                    }
                },
            )

    def _resolve_run_id(self) -> str:
        raw = (
            self.agent_memory_config.get("memory_run_id")
            or self.agent_memory_config.get("run_id")
            or self.simulation_config.get("memory_run_id")
            or self.simulation_config.get("run_id")
            or getattr(self.client, "client_id", "")
            or "ysimulator_memory"
        )
        text = str(raw or "").strip()
        if len(text) > 128:
            digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]
            text = f"run_{digest}"
        return text or "ysimulator_memory"

    def is_enabled(self) -> bool:
        return self._enabled

    def _client_llm_provider(self):
        """Return a callable that routes llm_text/llm_json calls to the client LLM.

        This keeps all LLM usage on the client side (enforcing the
        client/server contract).  The yclient-memory engine calls
        ``runtime.llm_text(prompt_key, variables)`` or
        ``runtime.llm_json(prompt_key, variables)``; this provider maps those
        calls to the client's LLM manager when one is available.

        Returns ``None`` when no LLM manager is configured so the runtime
        falls back to its stub (empty string / empty dict).
        """
        llm_manager = getattr(self.client, "llm_manager", None)
        if llm_manager is None:
            return None

        def _provider(prompt_key: str, variables: dict, *, as_json: bool = False):
            # Delegate to the client-side LLM manager.  The manager is a Ray
            # actor handle; call generate_text if available, otherwise return
            # an empty sentinel so the engine degrades gracefully.
            generate_fn = getattr(llm_manager, "generate_text", None)
            if generate_fn is None:
                return {} if as_json else ""
            try:
                result = ray.get(
                    generate_fn.remote(
                        prompt_key=prompt_key,
                        variables=variables,
                        as_json=as_json,
                    )
                )
                return result if result is not None else ({} if as_json else "")
            except Exception as exc:
                self.logger.debug(
                    f"Client LLM provider call failed for '{prompt_key}': {exc}"
                )
                return {} if as_json else ""

        return _provider

    def round_number(self, day: int, slot: int) -> int:
        return self.client.round_number(day, slot)

    def set_recent_post_ids(self, recent_post_ids: Optional[List[str]]) -> None:
        self._active_recent_post_ids = list(recent_post_ids or [])

    def get_recent_post_ids(self) -> List[str]:
        return list(self._active_recent_post_ids)

    def _refresh_agent_flags(self) -> None:
        for agent in getattr(self.client, "agent_profiles", []) or []:
            self._agent_is_llm[str(agent.id)] = bool(getattr(agent, "llm", False))

    def _memory_enabled_for_agent(self, agent_id: str) -> bool:
        if str(agent_id) not in self._agent_is_llm:
            self._refresh_agent_flags()
        return self._enabled and bool(self._agent_is_llm.get(str(agent_id), False))

    def _server_memory_call(self, method_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            method = getattr(self.client.server, method_name)
            result = ray.get(method.remote(payload, client_id=self.client.client_id))
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            self.logger.warning(f"Server memory call {method_name} failed: {exc}")
            return {}

    def _server_memory_search(
        self,
        agent_id: str,
        query_text: str,
        *,
        day: int,
        slot: int,
        other_user_id: Optional[str] = None,
        thread_root_id: Optional[str] = None,
    ) -> str:
        if not query_text:
            return ""
        result = self._server_memory_call(
            "memory_search",
            {
                "run_id": self.run_id,
                "agent_user_id": str(agent_id),
                "query_text": query_text,
                "round_id": self.round_number(day, slot),
                "other_user_id": other_user_id,
                "thread_root_id": thread_root_id,
                "time_window_rounds": int(
                    self.agent_memory_config.get("memory_search_time_window_rounds", 40)
                ),
                "k": int(self.agent_memory_config.get("memory_search_k", 8)),
                "max_chars": int(self.agent_memory_config.get("memory_search_max_chars", 900)),
            },
        )
        items = result.get("items") if isinstance(result, dict) else []
        lines = []
        for item in items or []:
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)

    def _get_engine(self, agent_id: str):
        agent_id = str(agent_id)
        if not self._memory_enabled_for_agent(agent_id):
            return None
        if agent_id in self._engines:
            return self._engines[agent_id]
        raw = {
            "memory_enabled": bool(self.agent_memory_config.get("memory_enabled", False)),
            "memory_backend": self.agent_memory_config.get("memory_backend", "hybrid_semantic"),
            "memory_prompt_mode": self.agent_memory_config.get(
                "memory_prompt_mode", "subtle_timeline"
            ),
            "memory_vote_signal_only": bool(
                self.agent_memory_config.get("memory_vote_signal_only", False)
            ),
            "memory_reply_context_max_chars": int(
                self.agent_memory_config.get("memory_reply_context_max_chars", 220)
            ),
            "memory_cross_thread_callback_min_score": float(
                self.agent_memory_config.get("memory_cross_thread_callback_min_score", 0.8)
            ),
            "memory_high_affect_enabled": bool(
                self.agent_memory_config.get("memory_high_affect_enabled", False)
            ),
            "memory_high_affect_rule_threshold": float(
                self.agent_memory_config.get("memory_high_affect_rule_threshold", 0.55)
            ),
            "memory_high_affect_uncertain_low": float(
                self.agent_memory_config.get("memory_high_affect_uncertain_low", 0.35)
            ),
            "memory_high_affect_uncertain_high": float(
                self.agent_memory_config.get("memory_high_affect_uncertain_high", 0.7)
            ),
            "memory_high_affect_search_k": int(
                self.agent_memory_config.get("memory_high_affect_search_k", 12)
            ),
            "memory_high_affect_max_items": int(
                self.agent_memory_config.get("memory_high_affect_max_items", 6)
            ),
            "memory_high_affect_max_chars": int(
                self.agent_memory_config.get("memory_high_affect_max_chars", 900)
            ),
            "memory_high_affect_llm_fallback": bool(
                self.agent_memory_config.get("memory_high_affect_llm_fallback", False)
            ),
            "memory_nuance_enabled": bool(
                self.agent_memory_config.get("memory_nuance_enabled", True)
            ),
            "memory_nuance_min_score": float(
                self.agent_memory_config.get("memory_nuance_min_score", 0.35)
            ),
            "memory_nuance_callback_probability": float(
                self.agent_memory_config.get("memory_nuance_callback_probability", 0.55)
            ),
            "memory_nuance_cues_max_chars": int(
                self.agent_memory_config.get("memory_nuance_cues_max_chars", 320)
            ),
            "memory_pair_limit": int(self.agent_memory_config.get("memory_pair_limit", 8)),
            "pair_history_limit": int(self.agent_memory_config.get("memory_pair_limit", 8)),
            "thread_history_limit": int(
                self.agent_memory_config.get("memory_evidence_tail_max", 12)
            ),
            "memory_semantic_enabled": bool(
                self.agent_memory_config.get("memory_semantic_enabled", True)
            ),
            "memory_search_k": int(self.agent_memory_config.get("memory_search_k", 8)),
            "memory_search_max_chars": int(
                self.agent_memory_config.get("memory_search_max_chars", 900)
            ),
            "memory_search_time_window_rounds": int(
                self.agent_memory_config.get("memory_search_time_window_rounds", 18)
            ),
            "memory_total_max_chars": int(
                self.agent_memory_config.get("memory_total_max_chars", 2200)
            ),
            "memory_tier_a_max_chars": int(
                self.agent_memory_config.get("memory_tier_a_max_chars", 350)
            ),
            "memory_tier_b_max_chars": int(
                self.agent_memory_config.get("memory_tier_b_max_chars", 900)
            ),
            "memory_tier_c_max_chars": int(
                self.agent_memory_config.get("memory_tier_c_max_chars", 900)
            ),
            "memory_tier_c_uncertainty_threshold": float(
                self.agent_memory_config.get("memory_tier_c_uncertainty_threshold", 0.45)
            ),
            "memory_digest_update_cadence_rounds": int(
                self.agent_memory_config.get("memory_digest_update_cadence_rounds", 3)
            ),
            "memory_digest_events_limit": int(
                self.agent_memory_config.get("memory_digest_events_limit", 24)
            ),
            "memory_reflection_cadence_rounds": int(
                self.agent_memory_config.get("memory_reflection_cadence_rounds", 3)
            ),
            "memory_reflection_min_events": int(
                self.agent_memory_config.get("memory_reflection_min_events", 12)
            ),
            "memory_reflection_trigger_importance_sum": float(
                self.agent_memory_config.get(
                    "memory_reflection_trigger_importance_sum", 3.5
                )
            ),
            "memory_reflection_max_items_per_run": int(
                self.agent_memory_config.get("memory_reflection_max_items_per_run", 60)
            ),
            "memory_embedding_model": str(
                self.agent_memory_config.get("memory_embedding_model", "")
            ),
            "memory_embedding_async": bool(
                self.agent_memory_config.get("memory_embedding_async", False)
            ),
            "memory_importance_mode": str(
                self.agent_memory_config.get("memory_importance_mode", "")
            ),
        }
        config = self._pkg["MemoryConfig"].from_mapping(raw)
        engine = self._pkg["build_memory_engine"](
            backend=str(raw["memory_backend"] or "hybrid_semantic"),
            config=config,
            runtime=self.runtime,
        )
        self._engines[agent_id] = engine
        return engine

    def apply_post_memory(self, agent_id: str, agent_attrs: Optional[dict], day: int, slot: int):
        attrs = dict(agent_attrs or {})
        engine = self._get_engine(agent_id)
        if engine is None:
            return attrs
        request = self._pkg["PostStyleRequest"](round_id=self.round_number(day, slot))
        context = engine.build_post_style_context(request)
        if getattr(context, "rendered_text", ""):
            attrs["memory_post_style_text"] = context.rendered_text
        return attrs

    def apply_reply_memory(
        self,
        agent_id: str,
        agent_attrs: Optional[dict],
        *,
        target_post_id: str,
        target_post_data: dict,
        author_name: str,
        thread_context: Optional[List[dict]],
        day: int,
        slot: int,
        mode: str = "comment",
    ):
        attrs = dict(agent_attrs or {})
        engine = self._get_engine(agent_id)
        if engine is None:
            return attrs
        other_user_id = self.runtime.intern_user_id(str(target_post_data.get("user_id") or ""))
        thread_root_id = self.runtime.intern_post_id(
            str(target_post_data.get("thread_id") or target_post_id)
        )
        self.runtime.intern_post_id(str(target_post_id))
        query_text = target_post_data.get("tweet") or target_post_data.get("text") or ""
        thread_context_text = self._format_thread_context(thread_context)
        request = self._pkg["ReplyMemoryRequest"](
            query_text=query_text,
            other_user_id=other_user_id,
            other_username=author_name,
            thread_root_id=thread_root_id,
            round_id=self.round_number(day, slot),
            thread_context=thread_context_text,
            incoming_text=query_text,
            uncertainty_score=0.0,
            mode=mode,
        )
        context = engine.build_reply_context(request)
        if getattr(context, "rendered_text", ""):
            attrs["memory_reply_context_text"] = context.rendered_text
        cues = getattr(context, "cues", None)
        if getattr(cues, "rendered_text", ""):
            attrs["memory_reply_cues_text"] = cues.rendered_text
        persisted = self._server_memory_search(
            agent_id,
            query_text,
            day=day,
            slot=slot,
            other_user_id=str(target_post_data.get("user_id") or "") or None,
            thread_root_id=str(target_post_data.get("thread_id") or target_post_id),
        )
        if persisted:
            existing = str(attrs.get("memory_reply_context_text") or "").strip()
            attrs["memory_reply_context_text"] = (
                f"{existing}\n\nPersisted memory:\n{persisted}".strip()
            )
        return attrs

    def apply_browse_memory(
        self,
        agent_id: str,
        agent_attrs: Optional[dict],
        *,
        target_post_id: str,
        target_post_data: dict,
        day: int,
        slot: int,
    ):
        attrs = dict(agent_attrs or {})
        engine = self._get_engine(agent_id)
        if engine is None:
            return attrs
        thread_root_id = self.runtime.intern_post_id(
            str(target_post_data.get("thread_id") or target_post_id)
        )
        self.runtime.intern_post_id(str(target_post_id))
        request = self._pkg["BrowseMemoryRequest"](
            thread_root_id=thread_root_id,
            round_id=self.round_number(day, slot),
            scan_snippets=[],
        )
        context = engine.build_browse_context(request)
        if getattr(context, "rendered_text", ""):
            attrs["memory_browse_context_text"] = context.rendered_text
        query_text = target_post_data.get("tweet") or target_post_data.get("text") or ""
        persisted = self._server_memory_search(
            agent_id,
            query_text,
            day=day,
            slot=slot,
            thread_root_id=str(target_post_data.get("thread_id") or target_post_id),
        )
        if persisted:
            existing = str(attrs.get("memory_browse_context_text") or "").strip()
            attrs["memory_browse_context_text"] = (
                f"{existing}\n\nPersisted memory:\n{persisted}".strip()
            )
        return attrs

    def _persist_memory_event(
        self,
        *,
        agent_id: str,
        round_id: int,
        event_type: str,
        text: str,
        target_user_id: Optional[str] = None,
        thread_root_id: Optional[str] = None,
        target_post_id: Optional[str] = None,
        origin_kind: Optional[str] = None,
        importance: float = 0.35,
    ) -> None:
        text = " ".join(str(text or "").split()).strip()
        if not text:
            return
        event_result = self._server_memory_call(
            "memory_event",
            {
                "run_id": self.run_id,
                "round_id": int(round_id),
                "actor_user_id": str(agent_id),
                "target_user_id": target_user_id,
                "thread_root_id": thread_root_id,
                "target_post_id": target_post_id,
                "event_type": event_type,
                "relation_label": origin_kind or event_type,
                "salient_claim": text[:280],
                "event_text": text[:4000],
                "importance": importance,
            },
        )
        self._server_memory_call(
            "memory_item_upsert",
            {
                "run_id": self.run_id,
                "agent_user_id": str(agent_id),
                "item_type": "event",
                "text": text[:4000],
                "source_event_id": event_result.get("id") if isinstance(event_result, dict) else None,
                "thread_root_id": thread_root_id,
                "other_user_id": target_user_id,
                "round_id": int(round_id),
                "recency_anchor_round": int(round_id),
                "importance": importance,
                "metadata": {"event_type": event_type, "origin_kind": origin_kind},
            },
        )

    def record_submitted_actions(self, actions: List[Any], day: int, slot: int) -> None:
        if not self._enabled or not actions:
            return
        round_id = self.round_number(day, slot)
        for action in actions:
            engine = self._get_engine(str(action.agent_id))
            if engine is None:
                continue
            try:
                self._record_single_action(engine, action, round_id)
            except Exception as exc:
                self.logger.warning(
                    f"Memory event recording failed for agent {action.agent_id}: {exc}"
                )

        for engine in self._engines.values():
            try:
                engine.maintenance_tick(
                    self._pkg["MaintenanceTickRequest"](round_id=round_id, reason="slot")
                )
            except Exception as exc:
                self.logger.warning(f"Memory maintenance tick failed: {exc}")

    def _record_single_action(self, engine, action, round_id: int) -> None:
        """Record a single action in both the engine and the server DB.

        The engine call is best-effort: if it fails the server DB write still
        happens.  This ensures that DB tables are always written even when the
        yclient-memory engine raises an unexpected error.
        """
        if action.action_type == "POST" and getattr(action, "content", None):
            origin_kind = "text_post"
            if getattr(action, "article_id", None):
                origin_kind = "share_link"
            elif getattr(action, "image_id", None):
                origin_kind = "share_image"
            try:
                engine.record_post(
                    self._pkg["PostMemoryEvent"](
                        round_id=round_id,
                        text=action.content,
                        post_id=None,
                        user_id=self.runtime.intern_user_id(str(action.agent_id)),
                        origin_kind=origin_kind,
                    )
                )
            except Exception as exc:
                self.logger.debug(f"Engine record_post failed for agent {action.agent_id}: {exc}")
            self._persist_memory_event(
                agent_id=str(action.agent_id),
                round_id=round_id,
                event_type="post",
                text=action.content,
                origin_kind=origin_kind,
                importance=0.45,
            )
        elif action.action_type == "COMMENT" and getattr(action, "target_post_id", None):
            post = self.runtime._fetch_post(str(action.target_post_id))
            if not post:
                return
            other_user = (
                self.runtime._fetch_user(str(post.get("user_id")))
                if post.get("user_id")
                else None
            )
            try:
                engine.record_comment(
                    self._pkg["CommentMemoryEvent"](
                        round_id=round_id,
                        target_post_id=self.runtime.intern_post_id(
                            str(action.target_post_id)
                        ),
                        thread_root_id=self.runtime.intern_post_id(
                            str(post.get("thread_id") or action.target_post_id)
                        ),
                        other_user_id=self.runtime.intern_user_id(
                            str(post.get("user_id") or "")
                        ),
                        other_username=(other_user or {}).get("username"),
                        other_text=post.get("tweet") or post.get("text") or "",
                        my_text=action.content or "",
                        conv_text=self._thread_context_for_post(str(action.target_post_id)),
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    f"Engine record_comment failed for agent {action.agent_id}: {exc}"
                )
            self._persist_memory_event(
                agent_id=str(action.agent_id),
                round_id=round_id,
                event_type="comment",
                text=f"Replied to {(other_user or {}).get('username') or 'someone'}: {action.content or ''}",
                target_user_id=str(post.get("user_id") or "") or None,
                thread_root_id=str(post.get("thread_id") or action.target_post_id),
                target_post_id=str(action.target_post_id),
                importance=0.55,
            )
        elif action.action_type in {"LIKE", "LOVE", "LAUGH", "ANGRY", "SAD"} and getattr(
            action, "target_post_id", None
        ):
            post = self.runtime._fetch_post(str(action.target_post_id))
            if not post:
                return
            other_user = (
                self.runtime._fetch_user(str(post.get("user_id")))
                if post.get("user_id")
                else None
            )
            vote_type = (
                "like" if action.action_type in {"LIKE", "LOVE", "LAUGH"} else "downvote"
            )
            try:
                engine.record_vote(
                    self._pkg["VoteMemoryEvent"](
                        round_id=round_id,
                        post_id=self.runtime.intern_post_id(str(action.target_post_id)),
                        vote_type=vote_type,
                        other_user_id=self.runtime.intern_user_id(
                            str(post.get("user_id") or "")
                        ),
                        other_username=(other_user or {}).get("username"),
                        thread_root_id=self.runtime.intern_post_id(
                            str(post.get("thread_id") or action.target_post_id)
                        ),
                        post_text=post.get("tweet") or post.get("text") or "",
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    f"Engine record_vote failed for agent {action.agent_id}: {exc}"
                )
            self._persist_memory_event(
                agent_id=str(action.agent_id),
                round_id=round_id,
                event_type="reaction",
                text=f"{vote_type} reaction to {(other_user or {}).get('username') or 'someone'}: {post.get('tweet') or post.get('text') or ''}",
                target_user_id=str(post.get("user_id") or "") or None,
                thread_root_id=str(post.get("thread_id") or action.target_post_id),
                target_post_id=str(action.target_post_id),
                origin_kind=vote_type,
                importance=0.25,
            )
        elif action.action_type == "SHARE":
            post = None
            if getattr(action, "target_post_id", None):
                post = self.runtime._fetch_post(str(action.target_post_id))
            share_text = action.content or (
                post.get("tweet") or post.get("text") or "" if post else ""
            )
            try:
                engine.record_post(
                    self._pkg["PostMemoryEvent"](
                        round_id=round_id,
                        text=share_text,
                        post_id=None,
                        user_id=self.runtime.intern_user_id(str(action.agent_id)),
                        origin_kind="share_link" if post and post.get("news_id") else "text_post",
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    f"Engine record_post (share) failed for agent {action.agent_id}: {exc}"
                )
            self._persist_memory_event(
                agent_id=str(action.agent_id),
                round_id=round_id,
                event_type="share",
                text=share_text,
                target_user_id=str(post.get("user_id") or "") if post else None,
                thread_root_id=str(post.get("thread_id") or action.target_post_id)
                if post
                else None,
                target_post_id=str(action.target_post_id)
                if getattr(action, "target_post_id", None)
                else None,
                origin_kind="share_link" if post and post.get("news_id") else "text_post",
                importance=0.4,
            )

    def _format_thread_context(self, thread_context: Optional[List[dict]]) -> str:
        if not thread_context:
            return ""
        lines = []
        for item in thread_context:
            username = item.get("username", "Someone")
            text = item.get("tweet") or item.get("text") or ""
            if text:
                lines.append(f"{username}: {text}")
        return "\n".join(lines)

    def _thread_context_for_post(self, post_id: str) -> str:
        try:
            thread = ray.get(
                self.client.server.get_thread_context.remote(
                    post_id, 5, client_id=self.client.client_id
                )
            )
        except Exception:
            return ""
        return self._format_thread_context(thread)
