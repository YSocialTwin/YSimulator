"""
Comprehensive test suite for YServer components.

This module tests the YServer server.py, db_middleware.py, and related functionality
to achieve 80%+ coverage.
"""

import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YClient.classes.ray_models import SimulationInstruction
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import (
    Agent_Opinion,
    Base,
    Follow,
    Post,
    Reaction,
    Round,
    User_mgmt,
)


class TestDatabaseMiddleware:
    """Test suite for DatabaseMiddleware class."""

    def test_initialization_sqlite(self, tmp_path):
        """Test DatabaseMiddleware initialization with SQLite."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        assert middleware.db_type == "sqlite"
        assert not middleware.use_redis
        assert middleware.redis_client is None
        assert middleware.visibility_rounds == 36
        assert middleware.num_slots_per_day == 24

    def test_initialization_with_simulation_config(self, tmp_path):
        """Test DatabaseMiddleware with simulation config."""
        db_config = {"type": "sqlite"}
        simulation_config = {
            "posts": {"visibility_rounds": 48},
            "simulation": {"num_slots_per_day": 12},
        }
        middleware = DatabaseMiddleware(
            db_config=db_config,
            config_path=str(tmp_path),
            redis_config=None,
            simulation_config=simulation_config,
        )

        assert middleware.visibility_rounds == 48
        assert middleware.num_slots_per_day == 12

    def test_initialization_redis_disabled(self, tmp_path):
        """Test DatabaseMiddleware with Redis disabled."""
        db_config = {"type": "sqlite"}
        redis_config = {"enabled": False}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=redis_config
        )

        assert not middleware.use_redis
        assert middleware.redis_client is None

    def test_initialization_redis_no_host(self, tmp_path):
        """Test DatabaseMiddleware with Redis enabled but no host."""
        db_config = {"type": "sqlite"}
        redis_config = {"enabled": True, "port": 6379}  # No host
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=redis_config
        )

        assert not middleware.use_redis

    @patch("YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE", True)
    @patch("YSimulator.YServer.classes.db_middleware.redis")
    def test_initialization_redis_enabled_success(self, mock_redis, tmp_path):
        """Test DatabaseMiddleware with Redis successfully enabled."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis.Redis.return_value = mock_redis_instance

        db_config = {"type": "sqlite"}
        redis_config = {
            "enabled": True,
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "sliding_window_days": 3,
        }
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=redis_config
        )

        assert middleware.use_redis
        assert middleware.redis_sliding_window_days == 3
        mock_redis.Redis.assert_called_once()
        mock_redis_instance.ping.assert_called_once()

    @patch("YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE", True)
    @patch("YSimulator.YServer.classes.db_middleware.redis")
    def test_initialization_redis_connection_failure(self, mock_redis, tmp_path):
        """Test DatabaseMiddleware with Redis connection failure."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.side_effect = Exception("Connection failed")
        mock_redis.Redis.return_value = mock_redis_instance

        db_config = {"type": "sqlite"}
        redis_config = {"enabled": True, "host": "localhost", "port": 6379}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=redis_config
        )

        assert not middleware.use_redis
        assert middleware.redis_client is None

    def test_sqlite_database_creation(self, tmp_path):
        """Test SQLite database file creation."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Database file should be created
        db_file = tmp_path / "agent.db"
        assert db_file.exists()

        # Should be able to create session
        session = middleware.get_session()
        assert isinstance(session, Session)
        session.close()

    def test_get_session(self, tmp_path):
        """Test get_session method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        session = middleware.get_session()
        assert isinstance(session, Session)
        session.close()

    def test_close_session(self, tmp_path):
        """Test close_session method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        session = middleware.get_session()
        middleware.close_session(session)
        # Session should be closed (no error should occur)

    def test_get_user_by_id(self, tmp_path):
        """Test get_user_by_id method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create a test user
        session = middleware.get_session()
        user = User_mgmt(id=1, username="testuser", email="test@example.com")
        session.add(user)
        session.commit()

        # Retrieve the user
        retrieved_user = middleware.get_user_by_id(1)
        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"
        assert retrieved_user.email == "test@example.com"

        session.close()

    def test_get_user_by_id_not_found(self, tmp_path):
        """Test get_user_by_id with non-existent user."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        user = middleware.get_user_by_id(999)
        assert user is None

    def test_get_username_by_id(self, tmp_path):
        """Test get_username_by_id method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create a test user
        session = middleware.get_session()
        user = User_mgmt(id=1, username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        session.close()

        # Retrieve username
        username = middleware.get_username_by_id(1)
        assert username == "testuser"

    def test_get_username_by_id_not_found(self, tmp_path):
        """Test get_username_by_id with non-existent user."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        username = middleware.get_username_by_id(999)
        assert username == "Someone"  # Default username

    def test_get_round(self, tmp_path):
        """Test get_round method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create a test round
        session = middleware.get_session()
        round_obj = Round(id=1, day=1, slot=0)
        session.add(round_obj)
        session.commit()
        session.close()

        # Retrieve the round
        retrieved_round = middleware.get_round(1, 0)
        assert retrieved_round is not None
        assert retrieved_round.day == 1
        assert retrieved_round.slot == 0

    def test_get_round_not_found(self, tmp_path):
        """Test get_round with non-existent round."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        round_obj = middleware.get_round(999, 999)
        assert round_obj is None

    def test_create_round(self, tmp_path):
        """Test create_round method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create a round
        round_obj = middleware.create_round(day=1, slot=0)
        assert round_obj is not None
        assert round_obj.day == 1
        assert round_obj.slot == 0

        # Verify it was saved
        session = middleware.get_session()
        saved_round = session.query(Round).filter_by(day=1, slot=0).first()
        assert saved_round is not None
        session.close()

    def test_get_or_create_round_create(self, tmp_path):
        """Test get_or_create_round when round doesn't exist."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        round_obj = middleware.get_or_create_round(day=1, slot=0)
        assert round_obj is not None
        assert round_obj.day == 1
        assert round_obj.slot == 0

    def test_get_or_create_round_get(self, tmp_path):
        """Test get_or_create_round when round already exists."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create round first
        middleware.create_round(day=1, slot=0)

        # Get existing round
        round_obj = middleware.get_or_create_round(day=1, slot=0)
        assert round_obj is not None
        assert round_obj.day == 1
        assert round_obj.slot == 0

    def test_add_post(self, tmp_path):
        """Test add_post method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create dependencies
        session = middleware.get_session()
        user = User_mgmt(id=1, username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        session.close()

        round_obj = middleware.create_round(day=1, slot=0)

        # Add a post
        post = middleware.add_post(
            user_id=1, content="Test post", round_id=round_obj.id, parent_post_id=None
        )
        assert post is not None
        assert post.user_id == 1
        assert post.content == "Test post"
        assert post.round_id == round_obj.id

    def test_add_reaction(self, tmp_path):
        """Test add_reaction method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create dependencies
        session = middleware.get_session()
        user = User_mgmt(id=1, username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        session.close()

        round_obj = middleware.create_round(day=1, slot=0)
        post = middleware.add_post(user_id=1, content="Test post", round_id=round_obj.id)

        # Add a reaction
        reaction = middleware.add_reaction(user_id=1, post_id=post.id, reaction_type="like")
        assert reaction is not None
        assert reaction.user_id == 1
        assert reaction.post_id == post.id
        assert reaction.reaction_type == "like"

    def test_add_follow(self, tmp_path):
        """Test add_follow method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create dependencies
        session = middleware.get_session()
        user1 = User_mgmt(id=1, username="user1", email="user1@example.com")
        user2 = User_mgmt(id=2, username="user2", email="user2@example.com")
        session.add_all([user1, user2])
        session.commit()
        session.close()

        # Add a follow relationship
        follow = middleware.add_follow(follower_id=1, followee_id=2)
        assert follow is not None
        assert follow.follower_id == 1
        assert follow.followee_id == 2

    def test_get_post_by_id(self, tmp_path):
        """Test get_post_by_id method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create dependencies and post
        session = middleware.get_session()
        user = User_mgmt(id=1, username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        session.close()

        round_obj = middleware.create_round(day=1, slot=0)
        post = middleware.add_post(user_id=1, content="Test post", round_id=round_obj.id)

        # Retrieve the post
        retrieved_post = middleware.get_post_by_id(post.id)
        assert retrieved_post is not None
        assert retrieved_post.content == "Test post"

    def test_get_post_by_id_not_found(self, tmp_path):
        """Test get_post_by_id with non-existent post."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        post = middleware.get_post_by_id(999)
        assert post is None

    def test_get_followers(self, tmp_path):
        """Test get_followers method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create users and follow relationships
        session = middleware.get_session()
        for i in range(1, 4):
            user = User_mgmt(id=i, username=f"user{i}", email=f"user{i}@example.com")
            session.add(user)
        session.commit()
        session.close()

        # User 2 and 3 follow user 1
        middleware.add_follow(follower_id=2, followee_id=1)
        middleware.add_follow(follower_id=3, followee_id=1)

        # Get followers of user 1
        followers = middleware.get_followers(1)
        assert len(followers) == 2
        assert 2 in followers
        assert 3 in followers

    def test_get_followees(self, tmp_path):
        """Test get_followees method."""
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None
        )

        # Create users and follow relationships
        session = middleware.get_session()
        for i in range(1, 4):
            user = User_mgmt(id=i, username=f"user{i}", email=f"user{i}@example.com")
            session.add(user)
        session.commit()
        session.close()

        # User 1 follows user 2 and 3
        middleware.add_follow(follower_id=1, followee_id=2)
        middleware.add_follow(follower_id=1, followee_id=3)

        # Get followees of user 1
        followees = middleware.get_followees(1)
        assert len(followees) == 2
        assert 2 in followees
        assert 3 in followees

    def test_custom_logger(self, tmp_path):
        """Test DatabaseMiddleware with custom logger."""
        custom_logger = logging.getLogger("test_logger")
        db_config = {"type": "sqlite"}
        middleware = DatabaseMiddleware(
            db_config=db_config, config_path=str(tmp_path), redis_config=None, logger=custom_logger
        )

        assert middleware.logger == custom_logger


class TestServerLogDecorator:
    """Test suite for log_server_request decorator."""

    def test_log_decorator_basic(self):
        """Test basic decorator functionality."""
        from YSimulator.YServer.server import log_server_request

        # Create a mock class with a method
        class MockServer:
            def __init__(self):
                self.logger = MagicMock()

            @log_server_request
            def test_method(self, client_id, value):
                return value * 2

        server = MockServer()
        result = server.test_method("client1", 5)

        assert result == 10
        # Logger should have been called
        assert server.logger.info.called

    def test_log_decorator_with_kwargs(self):
        """Test decorator with keyword arguments."""
        from YSimulator.YServer.server import log_server_request

        class MockServer:
            def __init__(self):
                self.logger = MagicMock()

            @log_server_request
            def test_method(self, client_id, value):
                return value * 2

        server = MockServer()
        result = server.test_method(client_id="client1", value=5)

        assert result == 10
        assert server.logger.info.called

    def test_log_decorator_with_exception(self):
        """Test decorator when method raises exception."""
        from YSimulator.YServer.server import log_server_request

        class MockServer:
            def __init__(self):
                self.logger = MagicMock()

            @log_server_request
            def test_method(self, client_id):
                raise ValueError("Test error")

        server = MockServer()
        with pytest.raises(ValueError, match="Test error"):
            server.test_method("client1")

        # Logger should still be called
        assert server.logger.info.called

    def test_log_decorator_unknown_client(self):
        """Test decorator with unknown client."""
        from YSimulator.YServer.server import log_server_request

        class MockServer:
            def __init__(self):
                self.logger = MagicMock()

            @log_server_request
            def test_method(self, value):
                return value

        server = MockServer()
        result = server.test_method(10)

        assert result == 10
        assert server.logger.info.called


class TestServerConstants:
    """Test server constants are defined correctly."""

    def test_constants_defined(self):
        """Test that server constants are properly defined."""
        from YSimulator.YServer import server

        assert hasattr(server, "RECOMMENDATION_TTL_SECONDS")
        assert hasattr(server, "NETWORK_EDGE_CHECK_LIMIT")
        assert hasattr(server, "LOG_FILE_MAX_BYTES")
        assert hasattr(server, "LOG_FILE_BACKUP_COUNT")

        assert server.RECOMMENDATION_TTL_SECONDS == 7 * 24 * 60 * 60
        assert server.NETWORK_EDGE_CHECK_LIMIT == 10
        assert server.LOG_FILE_MAX_BYTES == 10 * 1024 * 1024
        assert server.LOG_FILE_BACKUP_COUNT == 5
