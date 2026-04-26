"""Server-owned memory persistence and retrieval.

The client may use LLMs to generate or summarize memory text, but all database
state for memory is owned by the server through this service.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import (
    MemoryCommunityDigest,
    MemoryInteractionEvent,
    MemoryItem,
    MemorySocialCard,
    MemoryThreadCard,
)


def _safe_text(value: Any, *, max_len: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_len > 0 and len(text) > max_len:
        return text[:max_len].rstrip()
    return text


def _safe_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    try:
        return json.dumps(value)
    except Exception:
        return None


def _opt_str(value: Any, *, max_len: int = 36) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_len]


def _opt_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _tokenize(value: str) -> set:
    return {
        tok
        for tok in re.findall(r"[a-z0-9_]{3,}", str(value or "").lower())
        if tok
    }


class MemoryService:
    """Persistence facade for run-scoped agent memory."""

    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)

    def reset(self, run_id: str) -> Dict[str, Any]:
        run_id = _safe_text(run_id, max_len=128)
        if not run_id:
            return {"status": 400, "error": "run_id required"}

        session = Session(self.engine)
        try:
            for model in (
                MemoryInteractionEvent,
                MemoryItem,
                MemorySocialCard,
                MemoryThreadCard,
                MemoryCommunityDigest,
            ):
                session.query(model).filter_by(run_id=run_id).delete()
            session.commit()
            return {"status": 200}
        except Exception as exc:
            session.rollback()
            self.logger.error(f"Error resetting memory run {run_id}: {exc}")
            return {"status": 500, "error": str(exc)}
        finally:
            session.close()

    def record_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = _safe_text(payload.get("run_id"), max_len=128)
        actor_user_id = _opt_str(payload.get("actor_user_id"))
        round_id = _opt_int(payload.get("round_id"))
        event_type = _safe_text(payload.get("event_type"), max_len=32).lower()
        if not run_id or not actor_user_id or round_id is None:
            return {"status": 400, "error": "run_id, round_id and actor_user_id required"}
        if event_type not in {"comment", "post", "share", "upvote", "downvote", "reaction"}:
            return {"status": 400, "error": "invalid event_type"}

        session = Session(self.engine)
        try:
            event = MemoryInteractionEvent(
                run_id=run_id,
                round_id=round_id,
                actor_user_id=actor_user_id,
                target_user_id=_opt_str(payload.get("target_user_id")),
                thread_root_id=_opt_str(payload.get("thread_root_id")),
                target_post_id=_opt_str(payload.get("target_post_id")),
                actor_post_id=_opt_str(payload.get("actor_post_id")),
                event_type=event_type,
                relation_label=_safe_text(payload.get("relation_label"), max_len=32) or None,
                tone_label=_safe_text(payload.get("tone_label"), max_len=32) or None,
                topics_json=_safe_json(payload.get("topics")),
                salient_claim=_safe_text(payload.get("salient_claim"), max_len=300) or None,
                event_text=_safe_text(payload.get("event_text"), max_len=4000) or None,
                weight=float(payload.get("weight") or 1.0),
                importance=float(payload.get("importance") or 0.35),
                last_accessed_round=round_id,
                access_count=0,
            )
            session.add(event)
            session.flush()
            event_id = int(event.id)
            session.commit()
            return {"status": 200, "id": event_id}
        except Exception as exc:
            session.rollback()
            self.logger.error(f"Error recording memory event: {exc}")
            return {"status": 500, "error": str(exc)}
        finally:
            session.close()

    def upsert_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = _safe_text(payload.get("run_id"), max_len=128)
        agent_user_id = _opt_str(payload.get("agent_user_id"))
        text = _safe_text(payload.get("text"), max_len=4000)
        item_type = _safe_text(payload.get("item_type") or "event", max_len=32).lower()
        if not run_id or not agent_user_id or not text:
            return {"status": 400, "error": "run_id, agent_user_id and text required"}
        if item_type not in {"event", "reflection", "summary"}:
            item_type = "event"

        session = Session(self.engine)
        try:
            item_id = _opt_int(payload.get("id"))
            item = None
            if item_id is not None:
                item = (
                    session.query(MemoryItem)
                    .filter_by(id=item_id, run_id=run_id, agent_user_id=agent_user_id)
                    .first()
                )
            if item is None:
                item = MemoryItem(
                    run_id=run_id,
                    agent_user_id=agent_user_id,
                    item_type=item_type,
                    text=text,
                )
                session.add(item)
            else:
                item.item_type = item_type
                item.text = text

            round_id = _opt_int(payload.get("round_id"))
            item.metadata_json = _safe_json(payload.get("metadata"))
            item.source_event_id = _opt_int(payload.get("source_event_id"))
            item.thread_root_id = _opt_str(payload.get("thread_root_id"))
            item.other_user_id = _opt_str(payload.get("other_user_id"))
            item.topic_tags_json = _safe_json(payload.get("topic_tags"))
            item.round_id = round_id
            item.importance = float(payload.get("importance") or 0.35)
            item.recency_anchor_round = _opt_int(payload.get("recency_anchor_round")) or round_id
            item.last_accessed_round = _opt_int(payload.get("last_accessed_round")) or round_id
            item.access_count = _opt_int(payload.get("access_count")) or 0
            item.embedding_status = "unavailable"
            session.flush()
            out_id = int(item.id)
            session.commit()
            return {"status": 200, "id": out_id, "embedding_status": item.embedding_status}
        except Exception as exc:
            session.rollback()
            self.logger.error(f"Error upserting memory item: {exc}")
            return {"status": 500, "error": str(exc)}
        finally:
            session.close()

    def search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = _safe_text(payload.get("run_id"), max_len=128)
        agent_user_id = _opt_str(payload.get("agent_user_id"))
        query_text = _safe_text(payload.get("query_text"), max_len=2000)
        if not run_id or not agent_user_id or not query_text:
            return {"status": 400, "error": "run_id, agent_user_id and query_text required"}

        k = _opt_int(payload.get("k")) or 8
        k = max(1, min(k, 40))
        current_round = _opt_int(payload.get("round_id"))
        time_window_rounds = _opt_int(payload.get("time_window_rounds"))
        other_user_id = _opt_str(payload.get("other_user_id"))
        thread_root_id = _opt_str(payload.get("thread_root_id"))
        types = payload.get("types") or ["event", "reflection", "summary"]
        if isinstance(types, str):
            types = [types]
        types = [str(t).strip().lower() for t in types if str(t).strip()]
        if not types:
            types = ["event", "reflection", "summary"]

        session = Session(self.engine)
        try:
            q = session.query(MemoryItem).filter(
                MemoryItem.run_id == run_id,
                MemoryItem.agent_user_id == agent_user_id,
                MemoryItem.item_type.in_(types),
            )
            if other_user_id:
                q = q.filter(or_(MemoryItem.other_user_id == other_user_id, MemoryItem.other_user_id.is_(None)))
            if thread_root_id:
                q = q.filter(
                    or_(MemoryItem.thread_root_id == thread_root_id, MemoryItem.thread_root_id.is_(None))
                )
            if current_round is not None and time_window_rounds is not None and time_window_rounds > 0:
                q = q.filter(
                    or_(
                        MemoryItem.round_id.is_(None),
                        MemoryItem.round_id >= current_round - time_window_rounds,
                    )
                )

            candidates = q.order_by(MemoryItem.importance.desc(), MemoryItem.id.desc()).limit(250).all()
            query_tokens = _tokenize(query_text)
            scored = []
            for item in candidates:
                item_tokens = _tokenize(item.text)
                overlap = len(query_tokens & item_tokens)
                relevance = overlap / max(1, len(query_tokens))
                recency = 0.0
                anchor = item.recency_anchor_round or item.round_id
                if current_round is not None and anchor is not None:
                    recency = 1.0 / (1.0 + max(0, current_round - int(anchor)) / 24.0)
                score = (0.65 * relevance) + (0.25 * float(item.importance or 0.0)) + (0.10 * recency)
                if score <= 0 and query_tokens:
                    continue
                scored.append((score, item))
            scored.sort(key=lambda pair: pair[0], reverse=True)

            rows = []
            for score, item in scored[:k]:
                item.access_count = int(item.access_count or 0) + 1
                if current_round is not None:
                    item.last_accessed_round = current_round
                rows.append(
                    {
                        "id": int(item.id),
                        "item_id": int(item.id),
                        "run_id": item.run_id,
                        "agent_user_id": item.agent_user_id,
                        "item_type": item.item_type,
                        "text": item.text,
                        "metadata": json.loads(item.metadata_json) if item.metadata_json else None,
                        "thread_root_id": item.thread_root_id,
                        "other_user_id": item.other_user_id,
                        "round_id": item.round_id,
                        "importance": float(item.importance or 0.0),
                        "score": float(score),
                    }
                )
            session.commit()
            return {"status": 200, "items": rows, "count": len(rows)}
        except Exception as exc:
            session.rollback()
            self.logger.error(f"Error searching memory: {exc}")
            return {"status": 500, "error": str(exc), "items": []}
        finally:
            session.close()

    def get_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = _safe_text(payload.get("run_id"), max_len=128)
        agent_user_id = _opt_str(payload.get("agent_user_id"))
        if not run_id or not agent_user_id:
            return {"status": 400, "error": "run_id and agent_user_id required"}
        query = _safe_text(payload.get("query_text") or "recent interactions", max_len=1000)
        return self.search({**payload, "query_text": query, "k": payload.get("k", 8)})

    def events_recent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = _safe_text(payload.get("run_id"), max_len=128)
        agent_user_id = _opt_str(payload.get("agent_user_id"))
        limit = max(1, min(_opt_int(payload.get("limit")) or 50, 200))
        if not run_id:
            return {"status": 400, "error": "run_id required", "events": []}

        session = Session(self.engine)
        try:
            q = session.query(MemoryInteractionEvent).filter(MemoryInteractionEvent.run_id == run_id)
            if agent_user_id:
                q = q.filter(MemoryInteractionEvent.actor_user_id == agent_user_id)
            events = q.order_by(MemoryInteractionEvent.id.desc()).limit(limit).all()
            rows = [
                {
                    "id": int(ev.id),
                    "run_id": ev.run_id,
                    "round_id": ev.round_id,
                    "actor_user_id": ev.actor_user_id,
                    "target_user_id": ev.target_user_id,
                    "thread_root_id": ev.thread_root_id,
                    "target_post_id": ev.target_post_id,
                    "actor_post_id": ev.actor_post_id,
                    "event_type": ev.event_type,
                    "salient_claim": ev.salient_claim,
                    "event_text": ev.event_text,
                    "importance": float(ev.importance or 0.0),
                }
                for ev in events
            ]
            return {"status": 200, "events": rows}
        except Exception as exc:
            self.logger.error(f"Error reading recent memory events: {exc}")
            return {"status": 500, "error": str(exc), "events": []}
        finally:
            session.close()
