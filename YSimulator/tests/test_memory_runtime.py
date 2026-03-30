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


def _make_client():
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
    server = SimpleNamespace(
        get_post=_RemoteMethod(lambda post_id, client_id=None: posts[post_id]),
        get_user=_RemoteMethod(lambda user_id, client_id=None: users[user_id]),
        get_round_info=_RemoteMethod(lambda round_id: rounds[round_id]),
        get_thread_context=_RemoteMethod(
            lambda post_id, max_length=5, client_id=None: thread_context
        ),
    )
    return SimpleNamespace(
        client_id="client-1",
        server=server,
        logger=MagicMock(),
        agent_profiles=[SimpleNamespace(id="agent-1", llm=True), SimpleNamespace(id="agent-2", llm=False)],
        round_number=lambda day, slot: (day * 100) + slot,
        get_recent_post_ids=lambda: ["p2", "p1"],
    )


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
