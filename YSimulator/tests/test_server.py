"""
Unit tests for YServer/server.py

Tests the Orchestrator Server functionality with comprehensive mocking.
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Mark all tests in this module to run in isolated execution group
pytestmark = pytest.mark.xdist_group(name="server_tests")


# Use a module-level fixture that ONLY affects this test file
@pytest.fixture(scope="module", autouse=True)
def mock_ray_remote_for_server_tests():
    """Patch ray.remote ONLY for this test module."""
    # Import ray here to ensure we're patching the right thing
    import ray

    # Store original
    original_remote = ray.remote

    # Replace with identity function
    ray.remote = lambda x: x

    # Normalize the already-imported server module if another test imported it first.
    try:
        import YSimulator.YServer.server as server_module

        orchestrator = getattr(server_module, "OrchestratorServer", None)
        if hasattr(orchestrator, "__ray_actor_class__"):
            server_module.OrchestratorServer = orchestrator.__ray_actor_class__
    except Exception:
        pass

    yield

    # Restore original
    ray.remote = original_remote


class TestLogServerRequestDecorator:
    """Test log_server_request decorator."""

    def test_decorator_logs_successful_request(self):
        """Test decorator logs successful request."""
        from YSimulator.YServer.server import log_server_request

        # Create a mock function
        @log_server_request
        def mock_method(self, client_id):
            return "success"

        # Create mock server instance
        mock_server = Mock()
        mock_server.logger = Mock()
        mock_server.server_request_logger = Mock()  # Add server_request_logger
        mock_server.current_round_id = "round_1"
        mock_server.day = 1
        mock_server.slot = 1

        # Call the decorated function
        result = mock_method(mock_server, "client_1")

        # Verify result
        assert result == "success"

        # Verify logging was called on server_request_logger
        assert mock_server.server_request_logger.info.called

    def test_decorator_logs_failed_request(self):
        """Test decorator logs failed request with status 500."""
        from YSimulator.YServer.server import log_server_request

        @log_server_request
        def mock_method(self, client_id):
            raise ValueError("Test error")

        mock_server = Mock()
        mock_server.logger = Mock()
        mock_server.server_request_logger = Mock()  # Add server_request_logger
        mock_server.current_round_id = "round_1"
        mock_server.day = 1
        mock_server.slot = 1

        # Call should raise the exception
        with pytest.raises(ValueError):
            mock_method(mock_server, "client_1")

        # Verify logging was still called on server_request_logger
        assert mock_server.server_request_logger.info.called

    def test_decorator_extracts_client_id_from_kwargs(self):
        """Test decorator extracts client_id from kwargs."""
        from YSimulator.YServer.server import log_server_request

        @log_server_request
        def mock_method(self, agent_id, client_id=None):
            return client_id

        mock_server = Mock()
        mock_server.logger = Mock()
        mock_server.server_request_logger = Mock()  # Add server_request_logger
        mock_server.current_round_id = "round_1"
        mock_server.day = 1
        mock_server.slot = 1

        result = mock_method(mock_server, "agent_1", client_id="client_1")

        assert result == "client_1"
        assert mock_server.server_request_logger.info.called


class TestCompressRotatedLog:
    """Test compress_rotated_log function."""

    def test_compress_rotated_log(self):
        """Test log compression functionality."""
        import gzip

        from YSimulator.YServer.server import compress_rotated_log

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as source_file:
            source_file.write("Test log content\n")
            source_path = source_file.name

        dest_path = source_path + ".gz"

        try:
            # Compress the log
            compress_rotated_log(source_path, dest_path)

            # Verify compressed file exists
            assert Path(dest_path).exists()

            # Verify content can be decompressed
            with gzip.open(dest_path, "rt") as f:
                content = f.read()

            assert "Test log content" in content

        finally:
            # Clean up
            Path(source_path).unlink(missing_ok=True)
            Path(dest_path).unlink(missing_ok=True)


class TestOrchestratorServerInit:
    """Test OrchestratorServer initialization."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_init_basic(self, mock_interest_mgr_class):
        """Test basic server initialization."""
        from YSimulator.YServer.server import OrchestratorServer

        # Mock database middleware
        # Mock interest manager
        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

            server = OrchestratorServer(
                db_config=db_config, config_path=tmpdir, min_to_start=2, server_name="test_server"
            )

            # Verify initialization
            assert server.min_to_start == 2
            assert server.server_name == "test_server"
            assert server.day == 1
            assert server.slot == 1
            # current_round_id should be a valid UUID (service layer generates UUIDs)
            assert server.current_round_id is not None
            assert isinstance(server.current_round_id, str)
            assert len(server.current_round_id) > 0
            assert len(server.registered_clients) == 0

            # Note: With service layer, DatabaseMiddleware mock is bypassed
            # The server uses real repository implementations that generate UUIDs


class TestRecommendationPersistence:
    def test_save_recommendation_retries_when_sqlite_is_locked(self, monkeypatch):
        from YSimulator.YServer import server as server_module

        state = {"commits": 0}

        class _FakeSession:
            def add(self, _recommendation):
                return None

            def commit(self):
                state["commits"] += 1
                if state["commits"] == 1:
                    raise OperationalError(
                        "INSERT INTO recommendations", {}, Exception("database is locked")
                    )

            def rollback(self):
                return None

            def close(self):
                return None

        monkeypatch.setattr(server_module, "Session", lambda _engine: _FakeSession())
        monkeypatch.setattr(server_module.time, "sleep", lambda _seconds: None)

        server = Mock()
        server.db = Mock(engine=object())
        server.current_round_id = "round-1"
        server.use_redis = False
        server.logger = Mock()

        server_module.OrchestratorServer._save_recommendation(
            server, "agent-1", ["post-1", "post-2"]
        )

        assert state["commits"] == 2
        server.logger.error.assert_not_called()

    @patch("YSimulator.YServer.server.InterestManager")
    @patch("redis.Redis")
    def test_init_with_redis(self, mock_redis_class, mock_interest_mgr_class):
        """Test server initialization with Redis config."""
        from YSimulator.YServer.server import OrchestratorServer

        # Mock Redis client
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis_class.return_value = mock_redis

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            redis_config = {"enabled": True, "host": "localhost", "port": 6379}

            server = OrchestratorServer(
                db_config=db_config, config_path=tmpdir, redis_config=redis_config
            )

            # Verify redis is enabled
            assert server.db.use_redis is True
            mock_redis_class.assert_called_once()

    @patch("YSimulator.YServer.server.InterestManager")
    def test_init_with_archetype_config(self, mock_interest_mgr_class):
        """Test server initialization with archetype configuration."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        simulation_config = {
            "agent_archetypes": {
                "enabled": True,
                "distribution": {"casual": 0.7, "activist": 0.3},
                "transitions": {"casual": {"activist": 0.1}},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

            server = OrchestratorServer(
                db_config=db_config, config_path=tmpdir, simulation_config=simulation_config
            )

            # Verify archetype config
            assert server.archetypes_enabled is True
            assert server.archetype_distribution == {"casual": 0.7, "activist": 0.3}


class TestValidateAndExtractInterests:
    """Test _validate_and_extract_interests method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_validate_dict_interests(self, mock_interest_mgr_class):
        """Test validation of dict interests."""
        from YSimulator.YServer.server import OrchestratorServer

        # Configure InterestManager mock to return tuple (topics, counts)
        mock_interest_mgr = Mock()
        topics = ["technology", "sports"]
        counts = [8, 5]
        mock_interest_mgr.validate_and_extract_interests.return_value = (topics, counts)
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            interests = [["technology", "sports"], [8, 5]]
            result = server._validate_and_extract_interests(interests)

            assert result == (topics, counts)

    @patch("YSimulator.YServer.server.InterestManager")
    def test_validate_list_interests(self, mock_interest_mgr_class):
        """Test validation of list interests."""
        from YSimulator.YServer.server import OrchestratorServer

        # Configure InterestManager mock to return tuple
        mock_interest_mgr = Mock()
        topics = ["technology", "sports"]
        counts = [1, 1]
        mock_interest_mgr.validate_and_extract_interests.return_value = (topics, counts)
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            interests_list = [["technology", "sports"], [1, 1]]
            result = server._validate_and_extract_interests(interests_list)

            # Should return tuple of topics and counts
            assert result == (topics, counts)


class TestReactionToSentiment:
    """Test _reaction_to_sentiment method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_reaction_like_sentiment(self, mock_interest_mgr_class):
        """Test sentiment for 'like' reaction."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            result = server._reaction_to_sentiment("like")

            assert result is not None
            assert "compound" in result  # VADER sentiment uses compound, not valence
            assert result["compound"] > 0  # Positive sentiment

    @patch("YSimulator.YServer.server.InterestManager")
    def test_reaction_dislike_sentiment(self, mock_interest_mgr_class):
        """Test sentiment for negative reaction."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Use ANGRY which is a supported negative reaction
            result = server._reaction_to_sentiment("ANGRY")

            assert result is not None
            assert "compound" in result  # VADER sentiment uses compound, not valence
            assert result["compound"] < 0  # Negative sentiment

    @patch("YSimulator.YServer.server.InterestManager")
    def test_reaction_unknown_sentiment(self, mock_interest_mgr_class):
        """Test sentiment for unknown reaction."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            result = server._reaction_to_sentiment("unknown_reaction")

            assert result is None


class TestGetArticleTopics:
    """Test get_article_topics method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_article_topics(self, mock_interest_mgr_class):
        """Test retrieving article topics."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr.get_article_topics.return_value = ["technology", "AI"]
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # The server created its own InterestManager instance, so we need to configure it
            server.interest_manager.get_article_topics = Mock(return_value=["technology", "AI"])

            result = server.get_article_topics("article_1")

            assert result == ["technology", "AI"]
            server.interest_manager.get_article_topics.assert_called_once_with("article_1")


class TestStoreArticleTopics:
    """Test store_article_topics method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_store_article_topics(self, mock_interest_mgr_class):
        """Test storing article topics."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr.store_article_topics.return_value = ["topic_1", "topic_2"]
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # The server created its own InterestManager instance, so we need to configure it
            server.interest_manager.store_article_topics = Mock(return_value=["topic_1", "topic_2"])

            result = server.store_article_topics("article_1", ["tech", "AI"])

            assert result == ["topic_1", "topic_2"]
            server.interest_manager.store_article_topics.assert_called_once_with(
                "article_1", ["tech", "AI"]
            )


class TestGetFirstRoundId:
    """Test get_first_round_id method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_first_round_id_returns_current(self, mock_interest_mgr_class):
        """Test get_first_round_id returns current round when day=1, slot=1."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Server starts at day=1, slot=1
            result = server.get_first_round_id()

            # Should return the current_round_id (a UUID from service layer)
            assert result == server.current_round_id
            assert result is not None
            assert isinstance(result, str)

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_first_round_id_creates_round(self, mock_interest_mgr_class):
        """Test get_first_round_id creates round if needed."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Advance to day 2 by setting it on round_manager
            server.round_manager.day = 2
            server.round_manager.slot = 5

            result = server.get_first_round_id()

            # Should return a valid round ID for day=1, slot=1
            # With service layer, this creates a real round in the database
            assert result is not None
            assert isinstance(result, str)
            # The result should be different from current_round_id since we're at day 2
            # But both should be valid UUIDs


class TestCheckFollowRelationship:
    """Test check_follow_relationship method."""

    @patch("YSimulator.YServer.server.InterestManager")
    @patch("sqlalchemy.orm.Session")
    def test_check_follow_relationship_exists(self, mock_session_class, mock_interest_mgr_class):
        """Test checking existing follow relationship."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        # Mock the SQLAlchemy session and query
        mock_session = Mock()
        mock_session_class.return_value.__enter__.return_value = mock_session

        mock_follow = Mock()
        mock_follow.action = "follow"
        (
            mock_session.query.return_value.outerjoin.return_value.filter.return_value.order_by.return_value.first.return_value
        ) = mock_follow

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            result = server.check_follow_relationship("user1", "user2")

            assert result is True

    @patch("YSimulator.YServer.server.InterestManager")
    @patch("sqlalchemy.orm.Session")
    def test_check_follow_relationship_not_exists(
        self, mock_session_class, mock_interest_mgr_class
    ):
        """Test checking non-existing follow relationship."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        # Mock the SQLAlchemy session and query to return None
        mock_session = Mock()
        mock_session_class.return_value.__enter__.return_value = mock_session
        (
            mock_session.query.return_value.outerjoin.return_value.filter.return_value.order_by.return_value.first.return_value
        ) = None

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            result = server.check_follow_relationship("user1", "user3")

            assert result is False


class TestGetCurrentDay:
    """Test get_current_day method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_current_day(self, mock_interest_mgr_class):
        """Test getting current simulation day."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Default is day 1
            assert server.get_current_day() == 1

            # Change day via round_manager
            server.round_manager.day = 5
            assert server.get_current_day() == 5


class TestGetCurrentRoundId:
    """Test get_current_round_id method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_current_round_id(self, mock_interest_mgr_class):
        """Test getting current round ID."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Should return the server's current_round_id (a UUID from service layer)
            result = server.get_current_round_id()
            assert result == server.current_round_id
            assert result is not None
            assert isinstance(result, str)


class TestHeartbeat:
    """Test heartbeat method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_heartbeat_updates_timestamp(self, mock_interest_mgr_class):
        """Test heartbeat updates client timestamp."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Register a client
            server.registered_clients.add("client_1")

            # Send heartbeat
            result = server.heartbeat("client_1")

            assert result is True
            assert "client_1" in server.last_heartbeat
            assert isinstance(server.last_heartbeat["client_1"], float)

    @patch("YSimulator.YServer.server.InterestManager")
    def test_heartbeat_unregistered_client(self, mock_interest_mgr_class):
        """Test heartbeat for unregistered client returns False."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Send heartbeat without registering
            result = server.heartbeat("unknown_client")

            assert result is False


class TestGetActiveClients:
    """Test _get_active_clients method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_active_clients_all_active(self, mock_interest_mgr_class):
        """Test getting active clients when all are active."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Register clients via client_manager
            server.client_manager.registered_clients = {"client_1", "client_2"}
            server.client_manager.completed_clients = set()

            active = server._get_active_clients()

            assert active == {"client_1", "client_2"}

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_active_clients_some_completed(self, mock_interest_mgr_class):
        """Test getting active clients when some have completed."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Register clients via client_manager
            server.client_manager.registered_clients = {"client_1", "client_2", "client_3"}
            server.client_manager.completed_clients = {"client_2"}

            active = server._get_active_clients()

            assert active == {"client_1", "client_3"}


class TestCalculateVisibilityParams:
    """Test _calculate_visibility_params method."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_calculate_visibility_params(self, mock_interest_mgr_class):
        """Test calculating visibility parameters."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            # Set num_slots_per_day
            server.num_slots_per_day = 24
            server.round_manager.day = 3
            server.round_manager.slot = 10

            visibility_rounds = 48  # 2 days
            visibility_day, visibility_slot = server._calculate_visibility_params(visibility_rounds)

            # Should calculate correct day and slot
            assert isinstance(visibility_day, int)
            assert isinstance(visibility_slot, int)
            assert visibility_day <= server.day


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_empty_client_list(self, mock_interest_mgr_class):
        """Test handling empty client list."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            active = server._get_active_clients()
            assert active == set()

    @patch("YSimulator.YServer.server.InterestManager")
    def test_zero_visibility_rounds(self, mock_interest_mgr_class):
        """Test calculate visibility with zero rounds."""
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(db_config=db_config, config_path=tmpdir)

            visibility_day, visibility_slot = server._calculate_visibility_params(0)

            # Should handle zero visibility
            assert visibility_day == server.day
            assert visibility_slot == server.slot


class TestStressRewardWindowing:
    """Regression tests for stress/reward aggregate reconstruction."""

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_stress_reward_uses_round_day_hour_not_uuid_order(self, mock_interest_mgr_class):
        """Stress/reward windowing should be based on Round(day, hour) even when tids are UUIDs."""
        from YSimulator.YServer.classes.models import Round, StressReward
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        simulation_config = {"stress_reward": {"enabled": True}}

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(
                db_config=db_config, config_path=tmpdir, simulation_config=simulation_config
            )

            target_round_id = str(uuid.uuid4())
            sparse_mid_round_id = str(uuid.uuid4())
            old_round_id = str(uuid.uuid4())
            agent_id = str(uuid.uuid4())

            with Session(server.db.engine) as session:
                session.add_all(
                    [
                        Round(id=old_round_id, day=1, hour=3),
                        Round(id=sparse_mid_round_id, day=4, hour=18),
                        Round(id=target_round_id, day=9, hour=7),
                    ]
                )
                session.add_all(
                    [
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="stress",
                            value=0.45,
                            type="aggregate",
                            action=None,
                            tid=old_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="stress",
                            value=0.15,
                            type="variation",
                            action="comment:hostile",
                            tid=sparse_mid_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="reward",
                            value=0.25,
                            type="aggregate",
                            action=None,
                            tid=old_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="reward",
                            value=0.10,
                            type="variation",
                            action="reaction:like",
                            tid=sparse_mid_round_id,
                        ),
                    ]
                )
                session.commit()

            payload = server.get_stress_reward(agent_id, target_round_id, backward_rounds=1)

            assert payload["status"] == 200
            assert payload["stress"] == pytest.approx(0.60)
            assert payload["reward"] == pytest.approx(0.35)

            with Session(server.db.engine) as session:
                persisted = (
                    session.query(StressReward)
                    .filter_by(uid=agent_id, type="aggregate", tid=target_round_id)
                    .all()
                )
                persisted_by_var = {row.variable: row.value for row in persisted}

    @patch("YSimulator.YServer.server.InterestManager")
    def test_get_stress_reward_includes_same_round_variations_after_anchor(
        self, mock_interest_mgr_class
    ):
        """A prior aggregate checkpoint must not discard variations written in the same round."""
        from YSimulator.YServer.classes.models import Round, StressReward
        from YSimulator.YServer.server import OrchestratorServer

        mock_interest_mgr = Mock()
        mock_interest_mgr_class.return_value = mock_interest_mgr

        simulation_config = {"stress_reward": {"enabled": True}}

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
            server = OrchestratorServer(
                db_config=db_config, config_path=tmpdir, simulation_config=simulation_config
            )

            anchor_round_id = str(uuid.uuid4())
            target_round_id = str(uuid.uuid4())
            agent_id = str(uuid.uuid4())

            with Session(server.db.engine) as session:
                session.add_all(
                    [
                        Round(id=anchor_round_id, day=1, hour=5),
                        Round(id=target_round_id, day=1, hour=6),
                    ]
                )
                session.add_all(
                    [
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="stress",
                            value=0.0,
                            type="aggregate",
                            action=None,
                            tid=anchor_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="stress",
                            value=0.03,
                            type="variation",
                            action="reaction:angry",
                            tid=anchor_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="reward",
                            value=0.0,
                            type="aggregate",
                            action=None,
                            tid=anchor_round_id,
                        ),
                        StressReward(
                            id=str(uuid.uuid4()),
                            uid=agent_id,
                            variable="reward",
                            value=-0.02,
                            type="variation",
                            action="reaction:angry",
                            tid=anchor_round_id,
                        ),
                    ]
                )
                session.commit()

            payload = server.get_stress_reward(agent_id, target_round_id, backward_rounds=1)

            assert payload["status"] == 200
            assert payload["stress"] == pytest.approx(0.03)
            assert payload["reward"] == pytest.approx(0.0)
