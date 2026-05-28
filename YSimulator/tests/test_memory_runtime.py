from types import SimpleNamespace
from unittest.mock import MagicMock

from YSimulator.YClient.memory_runtime import YSimulatorMemoryManager


class _RemoteMethod:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


class _FakeEngine:
    def __init__(self, runtime, config):
        self.runtime = runtime
        self.config = config
        self.posts = []
        self.comments = []
        self.votes = []
        self.ticks = []

    def build_post_style_context(self, request):
        return SimpleNamespace(rendered_text=f"style@{request.round_id}")

    def build_reply_context(self, request):
        return SimpleNamespace(
            rendered_text=f"reply@{request.other_username}",
            cues=SimpleNamespace(rendered_text=f"cues@{request.mode}"),
        )

    def build_browse_context(self, request):
        return SimpleNamespace(rendered_text=f"browse@{request.round_id}")

    def record_post(self, event):
        self.posts.append(event)

    def record_comment(self, event):
        self.comments.append(event)

    def record_vote(self, event):
        self.votes.append(event)

    def maintenance_tick(self, request):
        self.ticks.append(request)


class _RaisingEngine(_FakeEngine):
    """Engine whose record_* methods always raise to test DB-write isolation."""

    def record_post(self, event):
        raise RuntimeError("engine failure")

    def record_comment(self, event):
        raise RuntimeError("engine failure")

    def record_vote(self, event):
        raise RuntimeError("engine failure")


def _fake_memory_package():
    class MemoryConfig:
        @classmethod
        def from_mapping(cls, mapping):
            return SimpleNamespace(raw=mapping)

    def build_memory_engine(*, backend, config, runtime):
        assert backend == "hybrid_semantic"
        return _FakeEngine(runtime, config)

    ctor = lambda **kwargs: SimpleNamespace(**kwargs)
    return {
        "BrowseMemoryRequest": ctor,
        "CommentMemoryEvent": ctor,
        "MaintenanceTickRequest": ctor,
        "PostMemoryEvent": ctor,
        "PostStyleRequest": ctor,
        "ReplyMemoryRequest": ctor,
        "VoteMemoryEvent": ctor,
        "MemoryConfig": MemoryConfig,
        "build_memory_engine": build_memory_engine,
    }


def _fake_memory_package_raising():
    """Memory package whose engines raise on every record_* call."""

    class MemoryConfig:
        @classmethod
        def from_mapping(cls, mapping):
            return SimpleNamespace(raw=mapping)

    def build_memory_engine(*, backend, config, runtime):
        return _RaisingEngine(runtime, config)

    ctor = lambda **kwargs: SimpleNamespace(**kwargs)
    return {
        "BrowseMemoryRequest": ctor,
        "CommentMemoryEvent": ctor,
        "MaintenanceTickRequest": ctor,
        "PostMemoryEvent": ctor,
        "PostStyleRequest": ctor,
        "ReplyMemoryRequest": ctor,
        "VoteMemoryEvent": ctor,
        "MemoryConfig": MemoryConfig,
        "build_memory_engine": build_memory_engine,
    }


def _make_client(*, track_memory_calls=False):
    posts = {
        "p1": {
            "id": "p1",
            "user_id": "u1",
            "tweet": "Root post",
            "thread_id": "p1",
            "round": "r1",
        },
        "p2": {
            "id": "p2",
            "user_id": "u2",
            "tweet": "Reply post",
            "thread_id": "p1",
            "comment_to": "p1",
            "round": "r2",
            "news_id": "news-1",
        },
    }
    users = {
        "u1": {"id": "u1", "username": "alice"},
        "u2": {"id": "u2", "username": "bob"},
    }
    rounds = {
        "r1": {"day": 1, "hour": 1},
        "r2": {"day": 1, "hour": 2},
    }
    thread_context = [
        {"username": "alice", "tweet": "Root post"},
        {"username": "bob", "tweet": "Reply post"},
    ]

    # Track server-side memory calls so tests can assert on them.
    memory_calls = []

    def _memory_event(payload, client_id=None):
        if track_memory_calls:
            memory_calls.append(("memory_event", payload))
        return {"status": 200, "id": len(memory_calls) - 1}

    def _memory_item_upsert(payload, client_id=None):
        if track_memory_calls:
            memory_calls.append(("memory_item_upsert", payload))
        return {"status": 200, "id": len(memory_calls) - 1, "embedding_status": "unavailable"}

    def _memory_search(payload, client_id=None):
        if track_memory_calls:
            memory_calls.append(("memory_search", payload))
        return {"status": 200, "items": [], "count": 0}

    server = SimpleNamespace(
        get_post=_RemoteMethod(lambda post_id, client_id=None: posts[post_id]),
        get_user=_RemoteMethod(lambda user_id, client_id=None: users[user_id]),
        get_round_info=_RemoteMethod(lambda round_id: rounds[round_id]),
        get_thread_context=_RemoteMethod(
            lambda post_id, max_length=5, client_id=None: thread_context
        ),
        # Server-side memory endpoints (enforce: only server accesses DB).
        memory_event=_RemoteMethod(_memory_event),
        memory_item_upsert=_RemoteMethod(_memory_item_upsert),
        memory_search=_RemoteMethod(_memory_search),
    )
    client = SimpleNamespace(
        client_id="client-1",
        server=server,
        logger=MagicMock(),
        llm_manager=None,
        agent_profiles=[SimpleNamespace(id="agent-1", llm=True), SimpleNamespace(id="agent-2", llm=False)],
        round_number=lambda day, slot: (day * 100) + slot,
        get_recent_post_ids=lambda: ["p2", "p1"],
    )
    client._memory_calls = memory_calls
    return client


def test_memory_manager_applies_prompt_context(monkeypatch):
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client()
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={
            "agents": {
                "memory_enabled": True,
                "memory_backend": "hybrid_semantic",
                "memory_embedding_model": "embeddinggemma",
            }
        },
    )

    post_attrs = manager.apply_post_memory("agent-1", {"topic": "ai"}, 1, 2)
    assert post_attrs["memory_post_style_text"] == "style@102"

    reply_attrs = manager.apply_reply_memory(
        "agent-1",
        {"topic": "ai"},
        target_post_id="p2",
        target_post_data={"id": "p2", "user_id": "u2", "tweet": "Reply post", "thread_id": "p1"},
        author_name="bob",
        thread_context=[{"username": "alice", "tweet": "Root post"}],
        day=1,
        slot=2,
        mode="comment",
    )
    assert reply_attrs["memory_reply_context_text"] == "reply@bob"
    assert reply_attrs["memory_reply_cues_text"] == "cues@comment"

    browse_attrs = manager.apply_browse_memory(
        "agent-1",
        {"topic": "ai"},
        target_post_id="p2",
        target_post_data={"id": "p2", "thread_id": "p1"},
        day=1,
        slot=2,
    )
    assert browse_attrs["memory_browse_context_text"] == "browse@102"

    untouched = manager.apply_post_memory("agent-2", {"topic": "ai"}, 1, 2)
    assert untouched == {"topic": "ai"}


def test_memory_manager_records_post_comment_vote_and_share(monkeypatch):
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client()
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={"agents": {"memory_enabled": True, "memory_backend": "hybrid_semantic"}},
    )

    actions = [
        SimpleNamespace(action_type="POST", content="hello", agent_id="agent-1"),
        SimpleNamespace(
            action_type="COMMENT",
            content="reply",
            agent_id="agent-1",
            target_post_id="p2",
        ),
        SimpleNamespace(
            action_type="LIKE",
            agent_id="agent-1",
            target_post_id="p2",
        ),
        SimpleNamespace(
            action_type="SHARE",
            content="reshared",
            agent_id="agent-1",
            target_post_id="p2",
        ),
    ]

    manager.record_submitted_actions(actions, 1, 3)
    engine = manager._engines["agent-1"]

    assert [event.origin_kind for event in engine.posts] == [
        "text_post",
        "share_link",
    ]
    assert engine.comments[0].other_username == "bob"
    assert engine.comments[0].conv_text == "alice: Root post\nbob: Reply post"
    assert engine.votes[0].vote_type == "like"
    assert engine.ticks[0].round_id == 103


def test_memory_manager_writes_to_server_db(monkeypatch):
    """Verify that _persist_memory_event calls the server DB endpoints.

    Enforces the contract: only the server can access the DB.  All DB writes
    must go through the server memory RPC methods.
    """
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client(track_memory_calls=True)
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={"agents": {"memory_enabled": True, "memory_backend": "hybrid_semantic"}},
    )

    actions = [
        SimpleNamespace(action_type="POST", content="hello world", agent_id="agent-1"),
        SimpleNamespace(
            action_type="COMMENT",
            content="nice post",
            agent_id="agent-1",
            target_post_id="p2",
        ),
    ]
    manager.record_submitted_actions(actions, 1, 0)

    # Each action should produce one memory_event + one memory_item_upsert call.
    event_calls = [c for c in client._memory_calls if c[0] == "memory_event"]
    upsert_calls = [c for c in client._memory_calls if c[0] == "memory_item_upsert"]
    assert len(event_calls) == 2, f"Expected 2 memory_event calls, got {len(event_calls)}"
    assert len(upsert_calls) == 2, f"Expected 2 memory_item_upsert calls, got {len(upsert_calls)}"

    # Verify the POST event payload
    post_event = next(c[1] for c in event_calls if c[1].get("event_type") == "post")
    assert post_event["run_id"] == manager.run_id
    assert post_event["actor_user_id"] == "agent-1"
    assert post_event["event_text"] == "hello world"

    # Verify the COMMENT event payload
    comment_event = next(c[1] for c in event_calls if c[1].get("event_type") == "comment")
    assert comment_event["actor_user_id"] == "agent-1"
    assert comment_event["target_post_id"] == "p2"


def test_memory_db_write_survives_engine_failure(monkeypatch):
    """DB writes must happen even when the yclient-memory engine raises.

    This test enforces the fix for the core bug: _persist_memory_event was
    previously inside the same try/except as engine.record_*, so an engine
    failure would silently skip the server DB write.
    """
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package_raising)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client(track_memory_calls=True)
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={"agents": {"memory_enabled": True, "memory_backend": "hybrid_semantic"}},
    )

    actions = [
        SimpleNamespace(action_type="POST", content="important post", agent_id="agent-1"),
        SimpleNamespace(
            action_type="LIKE",
            agent_id="agent-1",
            target_post_id="p2",
        ),
    ]
    # Should not raise even though the engine raises internally.
    manager.record_submitted_actions(actions, 2, 1)

    # DB writes must still have happened despite engine failures.
    event_calls = [c for c in client._memory_calls if c[0] == "memory_event"]
    upsert_calls = [c for c in client._memory_calls if c[0] == "memory_item_upsert"]
    assert len(event_calls) == 2, (
        f"Expected 2 memory_event DB calls even with engine failure, got {len(event_calls)}"
    )
    assert len(upsert_calls) == 2, (
        f"Expected 2 memory_item_upsert DB calls even with engine failure, got {len(upsert_calls)}"
    )


def test_memory_runtime_filters_recent_root_posts(monkeypatch):
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client()
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={"agents": {"memory_enabled": True, "memory_backend": "hybrid_semantic"}},
    )

    rows = manager.runtime.get_recent_root_posts(round_id=105, limit=10, rounds_back=10)
    assert len(rows) == 1
    assert rows[0]["tweet"] == "Root post"


def test_llm_provider_is_client_side(monkeypatch):
    """Verify that llm_text / llm_json use a client-side provider, not the server.

    Enforces the contract: only the client can use LLMs.
    """
    from YSimulator.YClient import memory_runtime

    monkeypatch.setattr(memory_runtime, "_load_memory_package", _fake_memory_package)
    monkeypatch.setattr(memory_runtime.ray, "get", lambda value: value)

    client = _make_client()
    manager = YSimulatorMemoryManager(
        client,
        simulation_config={"agents": {"memory_enabled": True, "memory_backend": "hybrid_semantic"}},
    )
    runtime = manager.runtime

    # Without a provider the stubs return safe empty values.
    assert runtime.llm_text("any_key", {}) == ""
    assert runtime.llm_json("any_key", {}) == {}

    # With a provider the result is delegated to it (client side).
    provider_calls = []

    def _mock_provider(prompt_key, variables, *, as_json=False):
        provider_calls.append((prompt_key, variables, as_json))
        return {"answer": 42} if as_json else "generated text"

    runtime._llm_provider = _mock_provider

    assert runtime.llm_text("reflection", {"x": 1}) == "generated text"
    assert runtime.llm_json("reflection", {"x": 1}) == {"answer": 42}
    assert len(provider_calls) == 2
    # Provider must never be on the server — it is a Python callable living
    # in the client actor process.
    assert callable(runtime._llm_provider)
