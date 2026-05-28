from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import Base, Follow, Round, User_mgmt
from YSimulator.YServer.recommendation.follow_recommender import FollowRecommender


class _DBStub:
    def __init__(self, engine):
        self.engine = engine
        self.use_redis = False


def test_follow_recommender_uses_round_day_hour_not_uuid_order():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Round(id="z-round", day=1, hour=1),
                Round(id="a-round", day=2, hour=1),
                User_mgmt(id="agent", username="agent", password="x"),
                User_mgmt(id="target", username="target", password="x"),
                User_mgmt(id="other", username="other", password="x"),
                Follow(
                    id="f1",
                    follower_id="agent",
                    user_id="target",
                    action="follow",
                    round="z-round",
                ),
                Follow(
                    id="f2",
                    follower_id="agent",
                    user_id="target",
                    action="unfollow",
                    round="a-round",
                ),
            ]
        )
        session.commit()

    recommender = FollowRecommender(_DBStub(engine))
    suggestions = recommender.get_follow_suggestions(
        agent_id="agent",
        mode="FollowRecSys",
        n_neighbors=10,
        leaning_bias=0,
    )

    assert "target" in suggestions
