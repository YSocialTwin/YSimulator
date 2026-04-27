"""Regression tests for server-owned memory integration."""

import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect

from YSimulator.YServer.classes.models import Base
from YSimulator.YServer.services.memory_service import MemoryService


def test_memory_service_creates_reddit_blueprint_tables_and_searches():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "memory_interaction_events" in table_names
    assert "memory_items" in table_names
    assert "memory_social_cards" in table_names
    assert "memory_thread_cards" in table_names
    assert "memory_community_digests" in table_names

    service = MemoryService(engine, logging.getLogger("test-memory"))
    event = service.record_event(
        {
            "run_id": "run-1",
            "round_id": 26,
            "actor_user_id": "agent-1",
            "target_user_id": "agent-2",
            "thread_root_id": "post-root",
            "target_post_id": "post-1",
            "event_type": "comment",
            "event_text": "I answered a healthcare freedom argument.",
            "importance": 0.6,
        }
    )
    assert event["status"] == 200

    item = service.upsert_item(
        {
            "run_id": "run-1",
            "agent_user_id": "agent-1",
            "item_type": "event",
            "text": "Replied to agent-2 about healthcare freedom and policy",
            "source_event_id": event["id"],
            "thread_root_id": "post-root",
            "other_user_id": "agent-2",
            "round_id": 26,
            "importance": 0.6,
        }
    )
    assert item["status"] == 200

    result = service.search(
        {
            "run_id": "run-1",
            "agent_user_id": "agent-1",
            "query_text": "healthcare policy",
            "round_id": 27,
            "k": 3,
        }
    )
    assert result["status"] == 200
    assert result["count"] == 1
    assert "healthcare freedom" in result["items"][0]["text"]


def test_memory_contract_keeps_db_on_server_and_llm_off_server():
    root = Path(__file__).resolve().parents[1]
    client_source = (root / "YClient" / "memory_runtime.py").read_text()
    server_source = (root / "YServer" / "services" / "memory_service.py").read_text()

    assert "sqlite3" not in client_source
    assert "sqlalchemy" not in client_source
    assert "Session(" not in client_source
    assert "ray.get(method.remote" in client_source

    lowered_server = server_source.lower()
    assert "import openai" not in lowered_server
    assert "import ollama" not in lowered_server
    assert "embed_text" not in lowered_server
    assert "generate_reply" not in lowered_server
    assert "generate_completion" not in lowered_server
