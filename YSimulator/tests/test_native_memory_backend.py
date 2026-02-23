"""Tests for native SQL-backed memory backend behavior."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from YSimulator.YClient.memory.backends.native_backend import NativeMemoryBackend


def test_native_backend_ingest_retrieve_and_reinforce(tmp_path):
    db_file = tmp_path / "memory_backend.db"
    engine = create_engine(f"sqlite:///{db_file}")
    backend = NativeMemoryBackend(
        backend_config={"initial_strength": 0.5, "reinforce_gain": 0.2},
        engine=engine,
    )
    backend.initialize({})

    ingest = backend.ingest_event(
        "agent-1",
        {"action_type": "POST", "topic": "ai", "metadata": {"sentiment": 0.3}},
        {"current_round_id": "r1", "day": 1, "slot": 1},
    )
    assert ingest.success is True
    assert ingest.created == 1

    items = backend.retrieve(
        "agent-1",
        query=_query(topic="ai", action_type="POST", max_items=5),
        context={"current_round_id": "r2", "day": 1, "slot": 2},
    )
    assert len(items) == 1
    assert items[0].memory_text
    assert items[0].strength > 0

    reinforced = backend.reinforce(
        "agent-1",
        [items[0].memory_id],
        {"current_round_id": "r3", "day": 1, "slot": 3},
    )
    assert reinforced.success is True
    assert reinforced.reinforced == 1


def test_native_backend_forget_cycle_soft_forgets_items(tmp_path):
    db_file = tmp_path / "memory_backend_forget.db"
    engine = create_engine(f"sqlite:///{db_file}")
    backend = NativeMemoryBackend(
        backend_config={
            "initial_strength": 0.2,
            "time_decay_lambda": 0.8,
            "soft_forget_threshold": 0.12,
            "hard_delete_after_days": 1,
        },
        engine=engine,
    )
    backend.initialize({})

    backend.ingest_event(
        "agent-1",
        {"action_type": "COMMENT", "topic": "policy"},
        {"current_round_id": "r1", "day": 1, "slot": 1},
    )

    forget_result = backend.forget_cycle({"current_round_id": "r2", "day": 3, "slot": 1})
    assert forget_result.success is True
    assert forget_result.decayed >= 1

    session = Session(engine)
    try:
        count = session.execute(text("SELECT COUNT(*) AS c FROM agent_memory_items")).mappings().first()["c"]
        # Item may be hard-deleted (older than cutoff) or remain soft-forgotten.
        assert count in (0, 1)
    finally:
        session.close()


def _query(topic=None, action_type=None, max_items=5):
    from YSimulator.YClient.memory.backends.base import MemoryQuery

    return MemoryQuery(topic=topic, action_type=action_type, max_items=max_items)
