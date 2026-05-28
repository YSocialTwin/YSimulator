"""
Unit tests for recommendation engines.

Tests ContentRecommender and FollowRecommender classes with mocked backends.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, text

from YSimulator.YServer.recommendation.content_recommender import ContentRecommender
from YSimulator.YServer.recommendation.follow_recommender import FollowRecommender


@pytest.fixture
def mock_db_adapter():
    """Create mock database adapter for testing."""
    db = Mock()
    db.use_redis = False
    db.engine = Mock()
    db.redis_client = Mock()
    db._redis_key = Mock(side_effect=lambda *args: ":".join(args))
    return db


@pytest.fixture
def mock_db_adapter_redis():
    """Create mock database adapter with Redis enabled."""
    db = Mock()
    db.use_redis = True
    db.engine = Mock()
    db.redis_client = Mock()
    db._redis_key = Mock(side_effect=lambda *args: ":".join(args))

    # Mock Redis responses
    db.redis_client.lrange = Mock(return_value=["post1", "post2", "post3"])
    db.redis_client.pipeline = Mock(
        return_value=Mock(
            hgetall=Mock(),
            execute=Mock(
                return_value=[
                    {"user_id": "user2", "reaction_count": "5"},
                    {"user_id": "user3", "reaction_count": "10"},
                    {"user_id": "user4", "reaction_count": "2"},
                ]
            ),
        )
    )

    return db


class TestContentRecommender:
    """Test ContentRecommender class."""

    def test_init(self, mock_db_adapter):
        """Test ContentRecommender initialization."""
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)
        assert recommender.db == mock_db_adapter
        assert recommender.visibility_rounds == 36
        assert recommender.default_limit == 5
        assert recommender.logger is not None

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_db")
    def test_get_recommended_posts_uses_configured_default_limit(
        self, mock_recsys_db, mock_db_adapter
    ):
        """Test that configured default_limit is used when request limit is omitted."""
        mock_recsys_db.recommend_random = Mock(return_value=["post1", "post2", "post3"])

        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36, default_limit=12)
        _ = recommender.get_recommended_posts(agent_id="agent1", mode="random", day=1, slot=5)

        args = mock_recsys_db.recommend_random.call_args.args
        assert args[4] == 12

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_db")
    def test_get_recommended_posts_sql(self, mock_recsys_db, mock_db_adapter):
        """Test content recommendations using SQL backend."""
        # Mock the recommendation function
        mock_recsys_db.recommend_random = Mock(return_value=["post1", "post2", "post3"])

        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="random", limit=3, day=1, slot=5
        )

        assert len(result) == 3
        assert "post1" in result
        mock_recsys_db.recommend_random.assert_called_once()

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_redis")
    def test_get_recommended_posts_redis(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test content recommendations using Redis backend."""
        # Mock the recommendation function
        mock_recsys_redis.recommend_random_redis = Mock(return_value=["post1", "post2"])

        recommender = ContentRecommender(mock_db_adapter_redis, visibility_rounds=36)
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="random", limit=2, day=1, slot=5
        )

        assert len(result) == 2
        mock_recsys_redis.recommend_random_redis.assert_called_once()

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_db")
    def test_different_recommendation_modes(self, mock_recsys_db, mock_db_adapter):
        """Test different recommendation modes."""
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)

        # Test ReverseChrono mode
        mock_recsys_db.recommend_rchrono = Mock(return_value=["post1"])
        _ = recommender.get_recommended_posts(
            agent_id="agent1", mode="ReverseChrono", day=1, slot=5
        )
        assert mock_recsys_db.recommend_rchrono.called

        # Test ReverseChronoPopularity mode
        mock_recsys_db.recommend_rchrono_popularity = Mock(return_value=["post2"])
        _ = recommender.get_recommended_posts(
            agent_id="agent1", mode="ReverseChronoPopularity", day=1, slot=5
        )
        assert mock_recsys_db.recommend_rchrono_popularity.called

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_db")
    def test_new_collaborative_filtering_modes(self, mock_recsys_db, mock_db_adapter):
        """Test new collaborative filtering recommendation modes."""
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)

        # Test CollaborativeUserUser mode
        mock_recsys_db.recommend_collaborative_user_user = Mock(return_value=["post1", "post2"])
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="CollaborativeUserUser", day=1, slot=5
        )
        assert mock_recsys_db.recommend_collaborative_user_user.called
        assert len(result) == 2

        # Test CollaborativeItemItem mode
        mock_recsys_db.recommend_collaborative_item_item = Mock(return_value=["post3", "post4"])
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="CollaborativeItemItem", day=1, slot=5
        )
        assert mock_recsys_db.recommend_collaborative_item_item.called
        assert len(result) == 2

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_db")
    def test_new_content_based_modes(self, mock_recsys_db, mock_db_adapter):
        """Test new content-based filtering recommendation modes."""
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)

        # Test ContentBasedFeatures mode
        mock_recsys_db.recommend_content_based_features = Mock(return_value=["post5", "post6"])
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="ContentBasedFeatures", day=1, slot=5
        )
        assert mock_recsys_db.recommend_content_based_features.called
        assert len(result) == 2

        # Test ContentBasedVector mode
        mock_recsys_db.recommend_content_based_vector = Mock(return_value=["post7", "post8"])
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="ContentBasedVector", day=1, slot=5
        )
        assert mock_recsys_db.recommend_content_based_vector.called
        assert len(result) == 2

    @patch("YSimulator.YServer.recommendation.content_recommender.content_recsys_redis")
    def test_new_modes_redis(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test new recommendation modes using Redis backend."""
        # Mock the Redis recommendation functions
        mock_recsys_redis.recommend_collaborative_user_user_redis = Mock(
            return_value=["post1", "post2"]
        )
        mock_recsys_redis.recommend_collaborative_item_item_redis = Mock(
            return_value=["post3", "post4"]
        )
        mock_recsys_redis.recommend_content_based_features_redis = Mock(
            return_value=["post5", "post6"]
        )
        mock_recsys_redis.recommend_content_based_vector_redis = Mock(
            return_value=["post7", "post8"]
        )

    def test_shadow_ban_filter_removes_banned_authors(self, tmp_path: Path):
        db_path = tmp_path / "shadow_ban_filter.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE rounds (id VARCHAR(36) PRIMARY KEY, day INTEGER, hour INTEGER)"))
            conn.execute(text("CREATE TABLE user_mgmt (id VARCHAR(36) PRIMARY KEY, username TEXT)"))
            conn.execute(text("CREATE TABLE post (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), round VARCHAR(36))"))
            conn.execute(text("CREATE TABLE shadow_ban (uid VARCHAR(36), start_tid VARCHAR(36), duration INTEGER)"))
            conn.execute(text("INSERT INTO rounds (id, day, hour) VALUES ('r0', 0, 0)"))
            conn.execute(text("INSERT INTO rounds (id, day, hour) VALUES ('r4', 0, 4)"))
            conn.execute(text("INSERT INTO user_mgmt (id, username) VALUES ('u1', 'banned_user')"))
            conn.execute(text("INSERT INTO user_mgmt (id, username) VALUES ('u2', 'visible_user')"))
            conn.execute(text("INSERT INTO post (id, user_id, round) VALUES ('p1', 'u1', 'r0')"))
            conn.execute(text("INSERT INTO post (id, user_id, round) VALUES ('p2', 'u2', 'r0')"))
            conn.execute(text("INSERT INTO shadow_ban (uid, start_tid, duration) VALUES ('u1', 'r0', 8)"))

        db = Mock()
        db.engine = engine
        db.use_redis = False
        recommender = ContentRecommender(db, visibility_rounds=36)

        filtered = recommender._filter_shadow_banned_posts(["p1", "p2"], day=0, slot=4)

        assert filtered == ["p2"]

    def test_shadow_ban_filter_is_noop_when_table_missing(self, mock_db_adapter):
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)
        with patch("YSimulator.YServer.recommendation.content_recommender.inspect") as mock_inspect:
            mock_inspect.return_value.get_table_names.return_value = []
            assert recommender._filter_shadow_banned_posts(["post1"], day=0, slot=1) == ["post1"]

        recommender = ContentRecommender(mock_db_adapter_redis, visibility_rounds=36)

        # Test CollaborativeUserUser
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="CollaborativeUserUser", limit=2, day=1, slot=5
        )
        assert len(result) == 2
        assert mock_recsys_redis.recommend_collaborative_user_user_redis.called

        # Test CollaborativeItemItem
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="CollaborativeItemItem", limit=2, day=1, slot=5
        )
        assert len(result) == 2
        assert mock_recsys_redis.recommend_collaborative_item_item_redis.called

        # Test ContentBasedFeatures
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="ContentBasedFeatures", limit=2, day=1, slot=5
        )
        assert len(result) == 2
        assert mock_recsys_redis.recommend_content_based_features_redis.called

        # Test ContentBasedVector
        result = recommender.get_recommended_posts(
            agent_id="agent1", mode="ContentBasedVector", limit=2, day=1, slot=5
        )
        assert len(result) == 2
        assert mock_recsys_redis.recommend_content_based_vector_redis.called

    def test_calculate_visibility_params(self, mock_db_adapter):
        """Test visibility parameter calculation."""
        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)

        # Test with day=2, slot=12, visibility_rounds=36
        vis_day, vis_hour = recommender._calculate_visibility_params(2, 12, 36)

        # Total slots = 2*24 + 12 = 60
        # Visible slots = 60 - 36 = 24
        # vis_day = 24 // 24 = 1
        # vis_hour = 24 % 24 = 0
        assert vis_day == 1
        assert vis_hour == 0

    def test_error_handling(self, mock_db_adapter):
        """Test error handling in get_recommended_posts."""
        mock_db_adapter.engine = None  # Force an error

        recommender = ContentRecommender(mock_db_adapter, visibility_rounds=36)
        result = recommender.get_recommended_posts(agent_id="agent1", mode="random", day=1, slot=5)

        # Should return empty list on error
        assert result == []


class TestFollowRecommender:
    """Test FollowRecommender class."""

    def test_init(self, mock_db_adapter):
        """Test FollowRecommender initialization."""
        recommender = FollowRecommender(mock_db_adapter)
        assert recommender.db == mock_db_adapter
        assert recommender.logger is not None

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_db")
    def test_get_follow_suggestions_sql(self, mock_recsys_db, mock_db_adapter):
        """Test follow suggestions using SQL backend."""
        from unittest.mock import MagicMock

        from sqlalchemy.orm import Session

        # Mock session and query results
        mock_session = MagicMock(spec=Session)
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        # Mock User_mgmt query
        mock_agent = Mock()
        mock_agent.id = "agent1"
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_agent

        # Mock Follow query for following_ids
        mock_session.query.return_value.filter.return_value.group_by.return_value.subquery.return_value = (
            Mock()
        )
        mock_session.query.return_value.join.return_value.all.return_value = []

        # Mock recommendation function
        mock_recsys_db.recommend_random_follows = Mock(return_value=["user1", "user2"])
        mock_recsys_db.apply_leaning_bias = Mock(side_effect=lambda sess, aid, sugg, bias, n: sugg)

        with patch("sqlalchemy.orm.Session", return_value=mock_session):
            recommender = FollowRecommender(mock_db_adapter)
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="random", n_neighbors=2
            )

            assert len(result) == 2
            assert "user1" in result

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_db")
    def test_new_recommendation_modes_sql(self, mock_recsys_db, mock_db_adapter):
        """Test new recommendation modes (SQL backend)."""
        from unittest.mock import MagicMock

        from sqlalchemy.orm import Session

        # Mock session and query results
        mock_session = MagicMock(spec=Session)
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        # Mock User_mgmt query
        mock_agent = Mock()
        mock_agent.id = "agent1"
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_agent

        # Mock Follow query for following_ids
        mock_session.query.return_value.filter.return_value.group_by.return_value.subquery.return_value = (
            Mock()
        )
        mock_session.query.return_value.join.return_value.all.return_value = []

        mock_recsys_db.apply_leaning_bias = Mock(side_effect=lambda sess, aid, sugg, bias, n: sugg)

        with patch("sqlalchemy.orm.Session", return_value=mock_session):
            recommender = FollowRecommender(mock_db_adapter)

            # Test ResourceAllocation mode
            mock_recsys_db.recommend_resource_allocation = Mock(return_value=["user1"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="ResourceAllocation", n_neighbors=1
            )
            assert mock_recsys_db.recommend_resource_allocation.called

            # Test CosineSimilarity mode
            mock_recsys_db.recommend_cosine_similarity = Mock(return_value=["user2"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="CosineSimilarity", n_neighbors=1
            )
            assert mock_recsys_db.recommend_cosine_similarity.called

            # Test CoEngagement mode
            mock_recsys_db.recommend_co_engagement = Mock(return_value=["user3"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="CoEngagement", n_neighbors=1
            )
            assert mock_recsys_db.recommend_co_engagement.called

            # Test RandomWalkRestart mode
            mock_recsys_db.recommend_random_walk_with_restart = Mock(return_value=["user4"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="RandomWalkRestart", n_neighbors=1
            )
            assert mock_recsys_db.recommend_random_walk_with_restart.called

            # Test ReactionsOnContent mode
            mock_recsys_db.recommend_reactions_on_content = Mock(return_value=["user5"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="ReactionsOnContent", n_neighbors=1
            )
            assert mock_recsys_db.recommend_reactions_on_content.called

            # Test TwoHopEgoSampling mode
            mock_recsys_db.recommend_two_hop_ego_sampling = Mock(return_value=["user6"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="TwoHopEgoSampling", n_neighbors=1
            )
            assert mock_recsys_db.recommend_two_hop_ego_sampling.called

            # Test Activity mode
            mock_recsys_db.recommend_activity = Mock(return_value=["user7"])
            result = recommender.get_follow_suggestions(
                agent_id="agent1", mode="Activity", n_neighbors=1
            )
            assert mock_recsys_db.recommend_activity.called

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_redis")
    def test_get_follow_suggestions_redis(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test follow suggestions using Redis backend."""
        # Mock the recommendation function
        mock_recsys_redis.recommend_random_follows_redis = Mock(return_value=["user1", "user2"])

        recommender = FollowRecommender(mock_db_adapter_redis)
        result = recommender.get_follow_suggestions(agent_id="agent1", mode="random", n_neighbors=2)

        assert len(result) == 2
        mock_recsys_redis.recommend_random_follows_redis.assert_called_once()

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_redis")
    def test_leaning_bias_applied(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test that leaning bias is applied when specified."""
        mock_recsys_redis.recommend_random_follows_redis = Mock(return_value=["user1", "user2"])
        mock_recsys_redis.apply_leaning_bias_redis = Mock(return_value=["user1"])

        recommender = FollowRecommender(mock_db_adapter_redis)
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="random", n_neighbors=2, leaning_bias=1
        )

        # Bias should be applied
        mock_recsys_redis.apply_leaning_bias_redis.assert_called_once()

    def test_error_handling(self, mock_db_adapter):
        """Test error handling in get_follow_suggestions."""
        mock_db_adapter.engine = None  # Force an error

        recommender = FollowRecommender(mock_db_adapter)
        result = recommender.get_follow_suggestions(agent_id="agent1", mode="random", n_neighbors=2)

        # Should return empty list on error
        assert result == []

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_redis")
    def test_different_recommendation_modes(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test different recommendation modes."""
        recommender = FollowRecommender(mock_db_adapter_redis)

        # Test CommonNeighbors mode
        mock_recsys_redis.recommend_common_neighbors_redis = Mock(return_value=["user1"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="CommonNeighbors", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_common_neighbors_redis.called

        # Test Jaccard mode
        mock_recsys_redis.recommend_jaccard_redis = Mock(return_value=["user2"])
        _ = recommender.get_follow_suggestions(agent_id="agent1", mode="Jaccard", n_neighbors=1)
        assert mock_recsys_redis.recommend_jaccard_redis.called

    @patch("YSimulator.YServer.recommendation.follow_recommender.follow_recsys_redis")
    def test_new_recommendation_modes(self, mock_recsys_redis, mock_db_adapter_redis):
        """Test new recommendation modes (Resource Allocation, Cosine Similarity, etc.)."""
        recommender = FollowRecommender(mock_db_adapter_redis)

        # Test ResourceAllocation mode
        mock_recsys_redis.recommend_resource_allocation_redis = Mock(return_value=["user1"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="ResourceAllocation", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_resource_allocation_redis.called

        # Test CosineSimilarity mode
        mock_recsys_redis.recommend_cosine_similarity_redis = Mock(return_value=["user2"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="CosineSimilarity", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_cosine_similarity_redis.called

        # Test CoEngagement mode
        mock_recsys_redis.recommend_co_engagement_redis = Mock(return_value=["user3"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="CoEngagement", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_co_engagement_redis.called

        # Test RandomWalkRestart mode
        mock_recsys_redis.recommend_random_walk_with_restart_redis = Mock(return_value=["user4"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="RandomWalkRestart", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_random_walk_with_restart_redis.called

        # Test ReactionsOnContent mode
        mock_recsys_redis.recommend_reactions_on_content_redis = Mock(return_value=["user5"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="ReactionsOnContent", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_reactions_on_content_redis.called

        # Test TwoHopEgoSampling mode
        mock_recsys_redis.recommend_two_hop_ego_sampling_redis = Mock(return_value=["user6"])
        _ = recommender.get_follow_suggestions(
            agent_id="agent1", mode="TwoHopEgoSampling", n_neighbors=1
        )
        assert mock_recsys_redis.recommend_two_hop_ego_sampling_redis.called

        # Test Activity mode
        mock_recsys_redis.recommend_activity_redis = Mock(return_value=["user7"])
        _ = recommender.get_follow_suggestions(agent_id="agent1", mode="Activity", n_neighbors=1)
        assert mock_recsys_redis.recommend_activity_redis.called


class TestRecommendationIntegration:
    """Integration tests for recommendation engines."""

    def test_content_and_follow_recommenders_together(self, mock_db_adapter):
        """Test that both recommenders can be instantiated together."""
        content_rec = ContentRecommender(mock_db_adapter, visibility_rounds=36)
        follow_rec = FollowRecommender(mock_db_adapter)

        assert content_rec is not None
        assert follow_rec is not None
        assert content_rec.db == follow_rec.db
