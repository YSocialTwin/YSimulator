from __future__ import annotations

from sqlalchemy import inspect, text


def _ensure_sys_messages_duration_schema(engine, inspector) -> None:
    table_names = set(inspector.get_table_names())
    if "sys_messages" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    has_duration = "duration" in columns
    has_to_round = "to_round" in columns

    if has_duration and not has_to_round:
        return

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE sys_messages__new (
                        id VARCHAR(36) PRIMARY KEY,
                        type TEXT NOT NULL,
                        to_uid VARCHAR(36) REFERENCES user_mgmt(id),
                        message TEXT NOT NULL,
                        from_round VARCHAR(36) REFERENCES rounds(id),
                        duration INTEGER
                    )
                    """
                )
            )
            if has_to_round:
                conn.execute(
                    text(
                        """
                        INSERT INTO sys_messages__new (id, type, to_uid, message, from_round, duration)
                        SELECT
                            sm.id,
                            sm.type,
                            sm.to_uid,
                            sm.message,
                            sm.from_round,
                            CASE
                                WHEN rf.day IS NOT NULL
                                     AND rf.hour IS NOT NULL
                                     AND rt.day IS NOT NULL
                                     AND rt.hour IS NOT NULL
                                THEN ((rt.day * 24 + rt.hour) - (rf.day * 24 + rf.hour))
                                ELSE NULL
                            END
                        FROM sys_messages sm
                        LEFT JOIN rounds rf ON rf.id = sm.from_round
                        LEFT JOIN rounds rt ON rt.id = sm.to_round
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO sys_messages__new (id, type, to_uid, message, from_round, duration)
                        SELECT id, type, to_uid, message, from_round, duration
                        FROM sys_messages
                        """
                    )
                )
            conn.execute(text("DROP TABLE sys_messages"))
            conn.execute(text("ALTER TABLE sys_messages__new RENAME TO sys_messages"))
        else:
            if not has_duration:
                conn.execute(text("ALTER TABLE sys_messages ADD COLUMN duration INTEGER"))
            if has_to_round:
                conn.execute(
                    text(
                        """
                        UPDATE sys_messages AS sm
                        SET duration = CASE
                            WHEN sm.duration IS NOT NULL THEN sm.duration
                            WHEN rf.day IS NOT NULL
                                 AND rf.hour IS NOT NULL
                                 AND rt.day IS NOT NULL
                                 AND rt.hour IS NOT NULL
                            THEN ((rt.day * 24 + rt.hour) - (rf.day * 24 + rf.hour))
                            ELSE NULL
                        END
                        FROM rounds AS rf, rounds AS rt
                        WHERE rf.id = sm.from_round AND rt.id = sm.to_round
                        """
                    )
                )
                conn.execute(text("ALTER TABLE sys_messages DROP COLUMN to_round"))


def ensure_moderation_schema(engine) -> None:
    from YSimulator.YServer.classes.models import Reported, SysMessage

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "post" in table_names:
        post_columns = {column["name"] for column in inspector.get_columns("post")}
        if "moderated" not in post_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE post ADD COLUMN moderated INTEGER DEFAULT 0"))
        if "is_moderation_comment" not in post_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE post ADD COLUMN is_moderation_comment INTEGER DEFAULT 0")
                )

    SysMessage.__table__.create(bind=engine, checkfirst=True)
    Reported.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    _ensure_sys_messages_duration_schema(engine, inspector)
