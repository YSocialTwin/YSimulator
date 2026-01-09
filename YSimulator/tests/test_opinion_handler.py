"""
Unit tests for opinion dynamics handler.

Tests OpinionHandler class with mocked database backends.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from YSimulator.YServer.opinion_dynamics.opinion_handler import OpinionHandler


@pytest.fixture
def mock_db_adapter():
    """Create mock database adapter for testing."""
    db = Mock()
    db.use_redis = False
    db.engine = Mock()
    db.redis_client = Mock()
    db.get_latest_agent_opinion = Mock(return_value=None)
    db.add_agent_opinion = Mock(return_value=True)
    db.get_redis_key_pattern = Mock(return_value="follow:*")
    return db


@pytest.fixture
def opinion_handler(mock_db_adapter):
    """Create OpinionHandler instance for testing."""
    return OpinionHandler(
        db_adapter=mock_db_adapter,
        simulation_config={"opinion_dynamics": {"enabled": True}},
        agent_profiles_cache={},
        current_round_id_getter=lambda: "round_1",
    )


class TestOpinionHandler:
    """Test OpinionHandler class."""

    def test_init(self, mock_db_adapter):
        """Test OpinionHandler initialization."""
        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={},
            current_round_id_getter=lambda: "round_1",
        )
        assert handler.db == mock_db_adapter
        assert handler.enabled is True
        assert handler.logger is not None

    def test_init_disabled(self, mock_db_adapter):
        """Test OpinionHandler with disabled opinion dynamics."""
        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": False}},
            agent_profiles_cache={},
            current_round_id_getter=lambda: "round_1",
        )
        assert handler.enabled is False

    def test_ensure_opinion_exists_when_exists(self, opinion_handler, mock_db_adapter):
        """Test that ensure_agent_opinion_exists returns early if opinion exists."""
        mock_db_adapter.get_latest_agent_opinion = Mock(return_value=0.7)

        opinion_handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="Politics"
        )

        # Should not add new opinion since one exists
        mock_db_adapter.add_agent_opinion.assert_not_called()

    def test_ensure_opinion_exists_regular_agent(self, mock_db_adapter):
        """Test that ensure_agent_opinion_exists checks but doesn't create opinion."""
        # Mock agent profile with opinions
        profile = Mock()
        profile.is_page = 0
        profile.opinions = {"Politics": 0.8}

        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={"agent1": profile},
            current_round_id_getter=lambda: "round_1",
        )

        handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="Politics"
        )

        # Should NOT create opinion preemptively (deferred to interaction time)
        mock_db_adapter.add_agent_opinion.assert_not_called()

    def test_ensure_opinion_exists_page_agent(self, mock_db_adapter):
        """Test that ensure_agent_opinion_exists checks but doesn't create opinion for page agent."""
        # Mock page agent profile
        profile = Mock()
        profile.is_page = 1

        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={"agent1": profile},
            current_round_id_getter=lambda: "round_1",
        )

        handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="Politics"
        )

        # Should NOT create opinion preemptively (deferred to interaction time)
        mock_db_adapter.add_agent_opinion.assert_not_called()

    def test_ensure_opinion_exists_neutral_fallback(self, opinion_handler, mock_db_adapter):
        """Test that ensure_agent_opinion_exists doesn't create opinion when not in profile."""
        opinion_handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="Unknown Topic"
        )

        # Should NOT create opinion preemptively (deferred to interaction time)
        mock_db_adapter.add_agent_opinion.assert_not_called()

    def test_ensure_opinion_disabled(self, mock_db_adapter):
        """Test that ensure_opinion_exists does nothing when disabled."""
        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": False}},
            agent_profiles_cache={},
            current_round_id_getter=lambda: "round_1",
        )

        handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="Politics"
        )

        # Should not interact with database
        mock_db_adapter.get_latest_agent_opinion.assert_not_called()
        mock_db_adapter.add_agent_opinion.assert_not_called()

    def test_get_latest_opinion(self, opinion_handler, mock_db_adapter):
        """Test getting latest opinion."""
        mock_db_adapter.get_latest_agent_opinion = Mock(return_value=0.6)

        result = opinion_handler.get_latest_opinion("agent1", "topic1")

        assert result == 0.6
        mock_db_adapter.get_latest_agent_opinion.assert_called_once_with("agent1", "topic1")

    def test_add_opinion(self, opinion_handler, mock_db_adapter):
        """Test adding opinion."""
        result = opinion_handler.add_opinion(
            agent_id="agent1",
            topic_id="topic1",
            opinion=0.75,
            id_interacted_with="agent2",
            id_post="post1",
        )

        assert result is True
        mock_db_adapter.add_agent_opinion.assert_called_once()

    def test_get_neighbors_opinions_sql(self, mock_db_adapter):
        """Test getting neighbors opinions using SQL backend."""
        mock_db_adapter.use_redis = False

        # The code uses 'from sqlalchemy.orm import Session' inside the method
        # We need to mock Session from sqlalchemy.orm
        with patch("sqlalchemy.orm.Session") as mock_session_class:
            # Mock the session context manager
            mock_session = MagicMock()
            mock_session_class.return_value.__enter__ = Mock(return_value=mock_session)
            mock_session_class.return_value.__exit__ = Mock(return_value=False)

            # Mock the query results - simulate followees query
            mock_query = MagicMock()
            mock_query.filter.return_value.all.return_value = [
                ("followee1",),
                ("followee2",),
            ]
            mock_session.query.return_value = mock_query

            # Mock opinion retrieval for each followee
            mock_db_adapter.get_latest_agent_opinion = Mock(side_effect=[0.6, 0.8])

            handler = OpinionHandler(
                db_adapter=mock_db_adapter,
                simulation_config={"opinion_dynamics": {"enabled": True}},
                agent_profiles_cache={},
                current_round_id_getter=lambda: "round_1",
            )

            result = handler.get_neighbors_opinions("agent1", "topic1")

            assert len(result) == 2
            assert 0.6 in result
            assert 0.8 in result

    def test_get_neighbors_opinions_redis(self, mock_db_adapter):
        """Test getting neighbors opinions using Redis backend."""
        mock_db_adapter.use_redis = True

        # Mock Redis follow keys
        mock_db_adapter.redis_client.keys = Mock(return_value=[b"follow:1", b"follow:2"])

        # Mock follow data
        mock_db_adapter.redis_client.hgetall = Mock(
            side_effect=[
                {b"follower_id": b"agent1", b"user_id": b"followee1", b"action": b"follow"},
                {b"follower_id": b"agent1", b"user_id": b"followee2", b"action": b"follow"},
            ]
        )

        # Mock opinion retrieval
        mock_db_adapter.get_latest_agent_opinion = Mock(side_effect=[0.7, 0.9])

        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={},
            current_round_id_getter=lambda: "round_1",
        )

        result = handler.get_neighbors_opinions("agent1", "topic1")

        assert len(result) == 2
        assert 0.7 in result
        assert 0.9 in result

    def test_get_neighbors_opinions_error_handling(self, mock_db_adapter):
        """Test error handling in get_neighbors_opinions."""
        mock_db_adapter.use_redis = False
        mock_db_adapter.engine = None  # Force an error

        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={},
            current_round_id_getter=lambda: "round_1",
        )

        result = handler.get_neighbors_opinions("agent1", "topic1")

        # Should return empty list on error
        assert result == []

    def test_case_insensitive_topic_match(self, mock_db_adapter):
        """Test that ensure_agent_opinion_exists doesn't create opinion (even with case mismatch)."""
        # Mock agent profile with mixed case opinions
        profile = Mock()
        profile.is_page = 0
        profile.opinions = {"POLITICS": 0.8}

        handler = OpinionHandler(
            db_adapter=mock_db_adapter,
            simulation_config={"opinion_dynamics": {"enabled": True}},
            agent_profiles_cache={"agent1": profile},
            current_round_id_getter=lambda: "round_1",
        )

        handler.ensure_agent_opinion_exists(
            agent_id="agent1", topic_id="topic1", topic_name="politics"  # lowercase
        )

        # Should NOT create opinion preemptively (deferred to interaction time)
        mock_db_adapter.add_agent_opinion.assert_not_called()
