from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YClient.LLM_interactions.llm_service import LLMService
from YSimulator.YServer.classes.models import Base, Round, SysMessage, User_mgmt
from YSimulator.YServer.repositories.sql_repository import SQLPostRepository


def test_sql_post_repository_get_active_system_messages_uses_round_day_hour(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'system_messages.db'}")
    Base.metadata.create_all(engine)

    session = Session(engine)
    session.add_all(
        [
            Round(id="r1", day=1, hour=1),
            Round(id="r2", day=1, hour=2),
            Round(id="r3", day=1, hour=3),
            User_mgmt(id="user-1", username="user1", password="pwd", round_actions=1, is_page=0),
            SysMessage(
                id="m1",
                type="moderation",
                to_uid="user-1",
                message="Use MOD NOTICE.",
                from_round="r1",
                to_round="r2",
            ),
            SysMessage(
                id="m2",
                type="moderation",
                to_uid="user-1",
                message="Expired.",
                from_round="r1",
                to_round="r1",
            ),
        ]
    )
    session.commit()
    session.close()

    repo = SQLPostRepository(engine)
    active = repo.get_active_system_messages("user-1", "r2")

    assert active == [
        {
            "id": "m1",
            "type": "moderation",
            "message": "Use MOD NOTICE.",
            "to_uid": "user-1",
            "from_round": "r1",
            "to_round": "r2",
        }
    ]


def test_llm_service_system_messages_block_renders_instruction_lines():
    service = object.__new__(LLMService.__ray_metadata__.modified_class)

    rendered = service._system_messages_block(
        {
            "system_messages": [
                {"type": "moderation", "message": "Use MOD NOTICE."},
                {"type": "policy", "message": "Avoid slurs."},
            ]
        }
    )

    assert "Active system messages addressed to you for this round." in rendered
    assert "[moderation] Use MOD NOTICE." in rendered
    assert "[policy] Avoid slurs." in rendered


def test_llm_service_system_messages_block_returns_empty_string_when_no_messages():
    service = object.__new__(LLMService.__ray_metadata__.modified_class)

    assert service._system_messages_block({"system_messages": []}) == ""
