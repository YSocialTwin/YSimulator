"""Native SQL-backed memory backend for YSimulator."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from YSimulator.YClient.memory.backends.base import (
    BackendHealth,
    ForgetResult,
    IngestResult,
    MemoryBackend,
    MemoryItemDTO,
    MemoryQuery,
    ReinforceResult,
)


class NativeMemoryBackend(MemoryBackend):
    """Persistent native memory backend using the simulation SQL database."""

    def __init__(self, backend_config: Dict[str, Any], engine: Any, logger: Any = None):
        self.config = backend_config or {}
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
        self._initialized = False

    @property
    def name(self) -> str:
        return "native"

    def initialize(self, simulation_context: Dict[str, Any]) -> None:
        if self.engine is None:
            raise RuntimeError("NativeMemoryBackend requires a SQLAlchemy engine")

        session = Session(self.engine)
        try:
            session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS agent_memory_items (
                        memory_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        memory_text TEXT NOT NULL,
                        topic TEXT,
                        target_user_id TEXT,
                        thread_id TEXT,
                        action_type TEXT,
                        confidence FLOAT DEFAULT 0.5,
                        strength FLOAT DEFAULT 0.5,
                        sentiment FLOAT DEFAULT 0.0,
                        reuse_count INTEGER DEFAULT 0,
                        forgotten INTEGER DEFAULT 0,
                        created_round_id TEXT,
                        created_day INTEGER,
                        created_slot INTEGER,
                        last_access_round_id TEXT,
                        last_access_day INTEGER,
                        last_access_slot INTEGER,
                        metadata_json TEXT
                    )
                    """
                )
            )
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_memory_agent_forgotten "
                    "ON agent_memory_items(agent_id, forgotten)"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_memory_agent_strength "
                    "ON agent_memory_items(agent_id, strength)"
                )
            )
            session.commit()
            self._initialized = True
        finally:
            session.close()

    def ingest_event(
        self, agent_id: str, event: Dict[str, Any], context: Dict[str, Any]
    ) -> IngestResult:
        if not self._initialized:
            return IngestResult(success=False, error="backend_not_initialized")

        action_type = str(event.get("action_type", "")).upper()
        topic = event.get("topic")
        target_user_id = event.get("target_user_id")
        thread_id = event.get("thread_id")
        memory_text = self._build_memory_text(action_type, topic, target_user_id, event)
        confidence = float(self.config.get("initial_confidence", 0.6))
        strength = float(self.config.get("initial_strength", 0.6))
        sentiment = self._extract_sentiment(event)

        session = Session(self.engine)
        try:
            existing = (
                session.execute(
                    text(
                        """
                        SELECT memory_id, strength, confidence, reuse_count
                        FROM agent_memory_items
                        WHERE agent_id=:agent_id AND action_type=:action_type
                          AND COALESCE(topic,'')=COALESCE(:topic,'')
                          AND COALESCE(target_user_id,'')=COALESCE(:target_user_id,'')
                          AND COALESCE(thread_id,'')=COALESCE(:thread_id,'')
                          AND forgotten=0
                        LIMIT 1
                        """
                    ),
                    {
                        "agent_id": agent_id,
                        "action_type": action_type,
                        "topic": topic,
                        "target_user_id": target_user_id,
                        "thread_id": thread_id,
                    },
                ).mappings().first()
                if action_type
                else None
            )

            if existing:
                session.execute(
                    text(
                        """
                        UPDATE agent_memory_items
                        SET memory_text=:memory_text,
                            strength=:strength,
                            confidence=:confidence,
                            sentiment=:sentiment,
                            reuse_count=:reuse_count,
                            last_access_round_id=:round_id,
                            last_access_day=:day,
                            last_access_slot=:slot,
                            metadata_json=:metadata_json
                        WHERE memory_id=:memory_id
                        """
                    ),
                    {
                        "memory_id": existing["memory_id"],
                        "memory_text": memory_text,
                        "strength": min(1.0, float(existing["strength"]) + 0.05),
                        "confidence": min(1.0, float(existing["confidence"]) + 0.02),
                        "sentiment": sentiment,
                        "reuse_count": int(existing["reuse_count"]) + 1,
                        "round_id": context.get("current_round_id"),
                        "day": context.get("day"),
                        "slot": context.get("slot"),
                        "metadata_json": json.dumps(event.get("metadata", {})),
                    },
                )
                session.commit()
                self._enforce_capacity(session, agent_id)
                session.commit()
                return IngestResult(success=True, updated=1)

            memory_id = str(uuid.uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO agent_memory_items (
                        memory_id, agent_id, memory_text, topic, target_user_id, thread_id,
                        action_type, confidence, strength, sentiment, reuse_count, forgotten,
                        created_round_id, created_day, created_slot,
                        last_access_round_id, last_access_day, last_access_slot, metadata_json
                    ) VALUES (
                        :memory_id, :agent_id, :memory_text, :topic, :target_user_id, :thread_id,
                        :action_type, :confidence, :strength, :sentiment, 0, 0,
                        :round_id, :day, :slot,
                        :round_id, :day, :slot, :metadata_json
                    )
                    """
                ),
                {
                    "memory_id": memory_id,
                    "agent_id": agent_id,
                    "memory_text": memory_text,
                    "topic": topic,
                    "target_user_id": target_user_id,
                    "thread_id": thread_id,
                    "action_type": action_type,
                    "confidence": confidence,
                    "strength": strength,
                    "sentiment": sentiment,
                    "round_id": context.get("current_round_id"),
                    "day": context.get("day"),
                    "slot": context.get("slot"),
                    "metadata_json": json.dumps(event.get("metadata", {})),
                },
            )
            self._enforce_capacity(session, agent_id)
            session.commit()
            return IngestResult(success=True, created=1)
        except Exception as e:
            session.rollback()
            self.logger.error(f"Native memory ingest failed: {e}")
            return IngestResult(success=False, error=str(e))
        finally:
            session.close()

    def retrieve(
        self, agent_id: str, query: MemoryQuery, context: Dict[str, Any]
    ) -> List[MemoryItemDTO]:
        if not self._initialized:
            return []

        where = ["agent_id=:agent_id", "forgotten=0"]
        params: Dict[str, Any] = {"agent_id": agent_id, "limit": max(1, int(query.max_items))}

        if query.topic:
            where.append("topic=:topic")
            params["topic"] = query.topic
        if query.target_user_id:
            where.append("target_user_id=:target_user_id")
            params["target_user_id"] = query.target_user_id
        if query.thread_id:
            where.append("thread_id=:thread_id")
            params["thread_id"] = query.thread_id
        if query.action_type:
            where.append("action_type=:action_type")
            params["action_type"] = query.action_type.upper()

        sql = (
            "SELECT memory_id, memory_text, confidence, strength, sentiment, metadata_json "
            f"FROM agent_memory_items WHERE {' AND '.join(where)} "
            "ORDER BY strength DESC, confidence DESC, reuse_count DESC LIMIT :limit"
        )

        session = Session(self.engine)
        try:
            rows = session.execute(text(sql), params).mappings().all()
            memory_ids = [row["memory_id"] for row in rows]
            if memory_ids:
                session.execute(
                    text(
                        """
                        UPDATE agent_memory_items
                        SET last_access_round_id=:round_id,
                            last_access_day=:day,
                            last_access_slot=:slot
                        WHERE memory_id IN :memory_ids
                        """
                    ).bindparams(bindparam("memory_ids", expanding=True)),
                    {
                        "memory_ids": memory_ids,
                        "round_id": context.get("current_round_id"),
                        "day": context.get("day"),
                        "slot": context.get("slot"),
                    },
                )
                session.commit()

            items: List[MemoryItemDTO] = []
            for row in rows:
                confidence = float(row["confidence"] or 0.0)
                strength = float(row["strength"] or 0.0)
                items.append(
                    MemoryItemDTO(
                        memory_id=row["memory_id"],
                        memory_text=row["memory_text"],
                        relevance_score=(0.65 * strength) + (0.35 * confidence),
                        confidence=confidence,
                        strength=strength,
                        sentiment=float(row["sentiment"] or 0.0),
                        metadata=self._safe_load_json(row["metadata_json"]),
                    )
                )
            return items
        finally:
            session.close()

    def reinforce(
        self, agent_id: str, memory_ids: List[str], context: Dict[str, Any]
    ) -> ReinforceResult:
        if not self._initialized or not memory_ids:
            return ReinforceResult(success=True, skipped=len(memory_ids))

        reinforce_gain = float(self.config.get("reinforce_gain", 0.08))
        session = Session(self.engine)
        try:
            rows = session.execute(
                text(
                    """
                    SELECT memory_id, strength, confidence, reuse_count
                    FROM agent_memory_items
                    WHERE agent_id=:agent_id AND memory_id IN :memory_ids AND forgotten=0
                    """
                ).bindparams(bindparam("memory_ids", expanding=True)),
                {"agent_id": agent_id, "memory_ids": memory_ids},
            ).mappings().all()

            reinforced = 0
            for row in rows:
                session.execute(
                    text(
                        """
                        UPDATE agent_memory_items
                        SET strength=:strength,
                            confidence=:confidence,
                            reuse_count=:reuse_count,
                            last_access_round_id=:round_id,
                            last_access_day=:day,
                            last_access_slot=:slot
                        WHERE memory_id=:memory_id
                        """
                    ),
                    {
                        "memory_id": row["memory_id"],
                        "strength": min(1.0, float(row["strength"]) + reinforce_gain),
                        "confidence": min(1.0, float(row["confidence"]) + (reinforce_gain * 0.5)),
                        "reuse_count": int(row["reuse_count"]) + 1,
                        "round_id": context.get("current_round_id"),
                        "day": context.get("day"),
                        "slot": context.get("slot"),
                    },
                )
                reinforced += 1

            session.commit()
            return ReinforceResult(success=True, reinforced=reinforced, skipped=len(memory_ids) - reinforced)
        except Exception as e:
            session.rollback()
            self.logger.error(f"Native memory reinforce failed: {e}")
            return ReinforceResult(success=False, error=str(e))
        finally:
            session.close()

    def forget_cycle(self, context: Dict[str, Any]) -> ForgetResult:
        if not self._initialized:
            return ForgetResult(success=False, error="backend_not_initialized")

        decay_lambda = float(self.config.get("time_decay_lambda", 0.015))
        soft_threshold = float(self.config.get("soft_forget_threshold", 0.12))
        hard_delete_after_days = int(self.config.get("hard_delete_after_days", 14))
        current_day = int(context.get("day", 0) or 0)

        session = Session(self.engine)
        try:
            rows = session.execute(
                text("SELECT memory_id, strength, last_access_day FROM agent_memory_items WHERE forgotten=0")
            ).mappings().all()

            decayed = 0
            soft_forgotten = 0
            for row in rows:
                new_strength = max(0.0, float(row["strength"]) * (1.0 - decay_lambda))
                forgotten = 1 if new_strength < soft_threshold else 0
                if forgotten:
                    soft_forgotten += 1
                session.execute(
                    text(
                        """
                        UPDATE agent_memory_items
                        SET strength=:strength, forgotten=:forgotten
                        WHERE memory_id=:memory_id
                        """
                    ),
                    {
                        "memory_id": row["memory_id"],
                        "strength": new_strength,
                        "forgotten": forgotten,
                    },
                )
                decayed += 1

            hard_deleted = 0
            if current_day > 0:
                cutoff_day = current_day - hard_delete_after_days
                result = session.execute(
                    text(
                        """
                        DELETE FROM agent_memory_items
                        WHERE forgotten=1 AND COALESCE(last_access_day, 0) <= :cutoff_day
                        """
                    ),
                    {"cutoff_day": cutoff_day},
                )
                hard_deleted = int(result.rowcount or 0)

            session.commit()
            return ForgetResult(
                success=True,
                decayed=decayed,
                soft_forgotten=soft_forgotten,
                hard_deleted=hard_deleted,
            )
        except Exception as e:
            session.rollback()
            self.logger.error(f"Native memory forget cycle failed: {e}")
            return ForgetResult(success=False, error=str(e))
        finally:
            session.close()

    def health_check(self) -> BackendHealth:
        if self.engine is None:
            return BackendHealth(ok=False, backend=self.name, details={"error": "missing_engine"})
        return BackendHealth(ok=True, backend=self.name, details={"initialized": self._initialized})

    def _build_memory_text(
        self,
        action_type: str,
        topic: Optional[str],
        target_user_id: Optional[str],
        event: Dict[str, Any],
    ) -> str:
        if action_type == "POST" and topic:
            return f"Agent posted about topic '{topic}'"
        if action_type == "COMMENT" and topic:
            return f"Agent commented on topic '{topic}'"
        if action_type == "FOLLOW" and target_user_id:
            return f"Agent followed user '{target_user_id}'"
        if action_type == "UNFOLLOW" and target_user_id:
            return f"Agent unfollowed user '{target_user_id}'"
        if action_type and target_user_id:
            return f"Agent performed {action_type} targeting '{target_user_id}'"
        if action_type and topic:
            return f"Agent performed {action_type} about '{topic}'"
        return f"Agent performed {action_type or 'ACTION'}"

    def _extract_sentiment(self, event: Dict[str, Any]) -> float:
        try:
            metadata = event.get("metadata", {})
            sentiment = metadata.get("sentiment") if isinstance(metadata, dict) else None
            if sentiment is None:
                return 0.0
            return float(sentiment)
        except Exception:
            return 0.0

    def _safe_load_json(self, value: Any) -> Dict[str, Any]:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except Exception:
            return {}

    def _enforce_capacity(self, session: Session, agent_id: str) -> None:
        max_memories = int(self.config.get("max_memories_per_agent", 500))
        if max_memories <= 0:
            return

        count_row = session.execute(
            text("SELECT COUNT(*) AS c FROM agent_memory_items WHERE agent_id=:agent_id"),
            {"agent_id": agent_id},
        ).mappings().first()
        total = int(count_row["c"] if count_row else 0)
        if total <= max_memories:
            return

        excess = total - max_memories
        old_rows = session.execute(
            text(
                """
                SELECT memory_id FROM agent_memory_items
                WHERE agent_id=:agent_id
                ORDER BY forgotten DESC, strength ASC, confidence ASC, reuse_count ASC
                LIMIT :limit
                """
            ),
            {"agent_id": agent_id, "limit": excess},
        ).mappings().all()
        if not old_rows:
            return

        session.execute(
            text("DELETE FROM agent_memory_items WHERE memory_id IN :memory_ids").bindparams(
                bindparam("memory_ids", expanding=True)
            ),
            {"memory_ids": [row["memory_id"] for row in old_rows]},
        )
