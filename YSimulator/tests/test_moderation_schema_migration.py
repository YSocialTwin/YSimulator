from sqlalchemy import create_engine, inspect, text

from YSimulator.YServer.schema_migrations import ensure_moderation_schema


def test_ensure_moderation_schema_adds_tables_and_post_column(tmp_path):
    db_path = tmp_path / "moderation_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE user_mgmt (
                    id VARCHAR(36) PRIMARY KEY,
                    username TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE rounds (
                    id VARCHAR(36) PRIMARY KEY,
                    day INTEGER,
                    hour INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE post (
                    id VARCHAR(36) PRIMARY KEY,
                    tweet TEXT NOT NULL,
                    round VARCHAR(36),
                    user_id VARCHAR(36) NOT NULL
                )
                """
            )
        )

    ensure_moderation_schema(engine)

    inspector = inspect(engine)
    assert "sys_messages" in inspector.get_table_names()
    assert "reported" in inspector.get_table_names()
    post_columns = {column["name"] for column in inspector.get_columns("post")}
    assert "moderated" in post_columns
    assert "is_moderation_comment" in post_columns
    sys_message_columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    assert "duration" in sys_message_columns
    assert "to_round" not in sys_message_columns
