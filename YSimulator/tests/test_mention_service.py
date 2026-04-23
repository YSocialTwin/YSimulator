from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from YSimulator.YServer.services.mention_service import MentionService


class _StubPostRepository:
    def __init__(self, mentions):
        self._mentions = list(mentions)

    def health_check(self) -> bool:
        return True

    def add_post(self, post_data):
        raise NotImplementedError

    def get_post(self, post_id):
        raise NotImplementedError

    def get_recent_posts(self, limit=50):
        raise NotImplementedError

    def get_thread_context(self, post_id, max_length=5):
        raise NotImplementedError

    def add_interaction(self, interaction_data):
        raise NotImplementedError

    def increment_post_reaction_count(self, post_id):
        raise NotImplementedError

    def add_post_topic(self, post_id, topic_id):
        raise NotImplementedError

    def get_post_topics(self, post_id):
        raise NotImplementedError

    def search_posts_by_topic(self, topic_id, agent_id, limit=10):
        raise NotImplementedError

    def get_active_system_messages(self, user_id, round_id):
        raise NotImplementedError

    def add_post_emotion(self, post_id, emotion_id):
        raise NotImplementedError

    def get_emotion_by_name(self, emotion_name):
        raise NotImplementedError

    def initialize_emotions_table(self):
        raise NotImplementedError

    def add_post_sentiment(self, post_id, sentiment_score):
        raise NotImplementedError

    def get_post_sentiment(self, post_id):
        raise NotImplementedError

    def add_post_toxicity(self, post_id, toxicity_score):
        raise NotImplementedError

    def add_or_get_hashtag(self, hashtag):
        raise NotImplementedError

    def add_post_hashtag(self, post_id, hashtag_id):
        raise NotImplementedError

    def add_mention(self, post_id, mentioned_user_id):
        raise NotImplementedError

    def get_unreplied_mentions(self, user_id):
        return list(self._mentions)

    def get_mention_by_id(self, mention_id):
        raise NotImplementedError

    def mark_mention_replied(self, post_id, mentioned_user_id):
        raise NotImplementedError


def _build_engine(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER, hour INTEGER)"))
        conn.execute(text("CREATE TABLE post (id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"))
        conn.execute(
            text(
                "CREATE TABLE shadow_ban (uid TEXT NOT NULL, start_tid INTEGER NOT NULL, duration INTEGER)"
            )
        )
        conn.execute(text("INSERT INTO rounds (id, day, hour) VALUES (5, 0, 4)"))
        conn.execute(text("INSERT INTO post (id, user_id) VALUES ('p-banned', 'u-banned')"))
        conn.execute(text("INSERT INTO post (id, user_id) VALUES ('p-visible', 'u-visible')"))
        conn.execute(
            text("INSERT INTO shadow_ban (uid, start_tid, duration) VALUES ('u-banned', 4, 4)")
        )
    return engine


def test_mention_service_skips_posts_from_active_shadow_banned_authors(tmp_path: Path):
    engine = _build_engine(tmp_path / "mentions.db")
    repo = _StubPostRepository(
        [
            {"id": "m1", "user_id": "target", "post_id": "p-banned", "round": 5, "answered": 0},
            {"id": "m2", "user_id": "target", "post_id": "p-visible", "round": 5, "answered": 0},
        ]
    )
    service = MentionService(post_repository=repo, engine=engine)

    result = service.get_unreplied_mentions("target")

    assert result == [
        {"id": "m2", "user_id": "target", "post_id": "p-visible", "round": 5, "answered": 0}
    ]


def test_mention_service_falls_back_when_shadow_ban_table_missing(tmp_path: Path):
    db_path = tmp_path / "mentions-no-shadow.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER, hour INTEGER)"))
        conn.execute(text("CREATE TABLE post (id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO rounds (id, day, hour) VALUES (1, 0, 0)"))
        conn.execute(text("INSERT INTO post (id, user_id) VALUES ('p1', 'u1')"))
    mentions = [{"id": "m1", "user_id": "target", "post_id": "p1", "round": 1, "answered": 0}]
    service = MentionService(post_repository=_StubPostRepository(mentions), engine=engine)

    result = service.get_unreplied_mentions("target")

    assert result == mentions


def test_mention_service_returns_users_with_unreplied_mentions(tmp_path: Path):
    db_path = tmp_path / "mentions-users.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rounds (id TEXT PRIMARY KEY, day INTEGER, hour INTEGER)"))
        conn.execute(text("CREATE TABLE post (id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"))
        conn.execute(
            text(
                "CREATE TABLE mentions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, post_id TEXT NOT NULL, round TEXT, answered INTEGER)"
            )
        )
        conn.execute(text("INSERT INTO rounds (id, day, hour) VALUES ('r1', 1, 0)"))
        conn.execute(text("INSERT INTO post (id, user_id) VALUES ('p1', 'author')"))
        conn.execute(
            text(
                "INSERT INTO mentions (id, user_id, post_id, round, answered) VALUES "
                "('m1', 'u1', 'p1', 'r1', 0),"
                "('m2', 'u2', 'p1', 'r1', 1),"
                "('m3', 'u3', 'p1', 'r1', 0)"
            )
        )

    from YSimulator.YServer.repositories.sql_repository import SQLPostRepository

    repo = SQLPostRepository(engine)
    service = MentionService(post_repository=repo, engine=engine)

    result = service.get_users_with_unreplied_mentions(["u1", "u2", "u3", "u4"])

    assert set(result) == {"u1", "u3"}
