from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import Base, Post, Reported, Round, User_mgmt
from YSimulator.YServer.repositories.sql_repository import SQLPostRepository


def test_sql_post_repository_add_report_persists_row(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'report_repo.db'}")
    Base.metadata.create_all(engine)

    session = Session(engine)
    session.add(Round(id="round-1", day=0, hour=0))
    session.add(
        User_mgmt(id="author", username="author", password="pwd", round_actions=1, is_page=0)
    )
    session.add(
        User_mgmt(id="reporter", username="reporter", password="pwd", round_actions=1, is_page=0)
    )
    session.add(
        Post(
            id="post-1",
            tweet="toxic post",
            user_id="author",
            round="round-1",
            comment_to="-1",
            thread_id="post-1",
            reaction_count=0,
        )
    )
    session.commit()
    session.close()

    repo = SQLPostRepository(engine)
    assert (
        repo.add_report(
            {
                "type": "toxic",
                "to_uid": "author",
                "to_post": "post-1",
                "from_uid": "reporter",
                "tid": "round-1",
            }
        )
        is True
    )

    session = Session(engine)
    report = session.query(Reported).one()
    assert report.type == "toxic"
    assert report.to_uid == "author"
    assert report.to_post == "post-1"
    assert report.from_uid == "reporter"
    assert report.tid == "round-1"
    session.close()
