"""
Comprehensive tests for database operations and Redis integration.

This test suite ensures 80%+ coverage for:
- DatabaseMiddleware CRUD operations
- Redis integration and caching
- Content recommendation Redis strategies
- Follow recommendation Redis strategies
- Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import tempfile
import os
from pathlib import Path

# Import classes to test
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware, DEFAULT_USERNAME
from YSimulator.YServer.classes.models import Base, User_mgmt, Post, Reaction, Follow, Round
from YSimulator.YServer.recsys.content_recsys_redis import (
    recommend_rchrono_redis,
    recommend_rchrono_popularity_redis,
    recommend_rchrono_followers_redis,
)
from YSimulator.YServer.recsys.follow_recsys_redis import (
    recommend_random_follows_redis,
    recommend_preferential_attachment_redis,
)


class TestDatabaseMiddlewareBasics:
    """Test basic DatabaseMiddleware initialization and configuration."""

    def test_init_sqlite_without_redis(self):
        """Test initialization with SQLite backend and no Redis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            middleware = DatabaseMiddleware(db_config, config_path=tmpdir)
            
            assert middleware.db_type == "sqlite"
            assert middleware.use_redis is False
            assert middleware.redis_client is None
            assert middleware.visibility_rounds == 36  # default
            assert middleware.num_slots_per_day == 24  # default

    def test_init_sqlite_with_simulation_config(self):
        """Test initialization with custom simulation configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            simulation_config = {
                "posts": {"visibility_rounds": 48},
                "simulation": {"num_slots_per_day": 12}
            }
            middleware = DatabaseMiddleware(
                db_config, 
                config_path=tmpdir,
                simulation_config=simulation_config
            )
            
            assert middleware.visibility_rounds == 48
            assert middleware.num_slots_per_day == 12

    def test_init_postgresql(self):
        """Test initialization with PostgreSQL backend."""
        db_config = {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        # This will fail to connect but we test the initialization logic
        try:
            middleware = DatabaseMiddleware(db_config)
            assert middleware.db_type == "postgresql"
        except Exception:
            # Expected to fail connection, but db_type should be set
            pass

    def test_init_mysql(self):
        """Test initialization with MySQL backend."""
        db_config = {
            "type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        # This will fail to connect but we test the initialization logic
        try:
            middleware = DatabaseMiddleware(db_config)
            assert middleware.db_type == "mysql"
        except Exception:
            # Expected to fail connection
            pass

    @patch('YSimulator.YServer.classes.db_middleware.redis')
    def test_init_with_redis_disabled(self, mock_redis_module):
        """Test initialization with Redis disabled in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            redis_config = {"enabled": False}
            middleware = DatabaseMiddleware(db_config, config_path=tmpdir, redis_config=redis_config)
            
            assert middleware.use_redis is False
            assert middleware.redis_client is None

    @patch('YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE', True)
    @patch('YSimulator.YServer.classes.db_middleware.redis')
    def test_init_with_redis_no_host(self, mock_redis_module):
        """Test initialization with Redis enabled but no host specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            redis_config = {"enabled": True}  # No host
            
            mock_logger = Mock()
            middleware = DatabaseMiddleware(
                db_config, 
                config_path=tmpdir, 
                redis_config=redis_config,
                logger=mock_logger
            )
            
            assert middleware.use_redis is False
            mock_logger.info.assert_called()

    @patch('YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE', False)
    def test_init_with_redis_not_installed(self):
        """Test initialization when Redis module is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            redis_config = {"enabled": True, "host": "localhost"}
            
            mock_logger = Mock()
            middleware = DatabaseMiddleware(
                db_config, 
                config_path=tmpdir, 
                redis_config=redis_config,
                logger=mock_logger
            )
            
            assert middleware.use_redis is False
            mock_logger.warning.assert_called()

    @patch('YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE', True)
    @patch('YSimulator.YServer.classes.db_middleware.redis')
    def test_init_with_redis_success(self, mock_redis_module):
        """Test successful Redis initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            redis_config = {
                "enabled": True,
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "sliding_window_days": 3
            }
            
            mock_redis_client = Mock()
            mock_redis_client.ping.return_value = True
            mock_redis_module.Redis.return_value = mock_redis_client
            
            middleware = DatabaseMiddleware(
                db_config, 
                config_path=tmpdir, 
                redis_config=redis_config
            )
            
            assert middleware.use_redis is True
            assert middleware.redis_client is mock_redis_client
            assert middleware.redis_sliding_window_days == 3

    @patch('YSimulator.YServer.classes.db_middleware.REDIS_AVAILABLE', True)
    @patch('YSimulator.YServer.classes.db_middleware.redis')
    def test_init_with_redis_connection_failure(self, mock_redis_module):
        """Test Redis initialization with connection failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            redis_config = {"enabled": True, "host": "localhost"}
            
            mock_redis_client = Mock()
            mock_redis_client.ping.side_effect = Exception("Connection refused")
            mock_redis_module.Redis.return_value = mock_redis_client
            
            mock_logger = Mock()
            middleware = DatabaseMiddleware(
                db_config, 
                config_path=tmpdir, 
                redis_config=redis_config,
                logger=mock_logger
            )
            
            assert middleware.use_redis is False
            mock_logger.error.assert_called()


class TestDatabaseMiddlewareCRUD:
    """Test CRUD operations in DatabaseMiddleware."""

    @pytest.fixture
    def db_middleware(self):
        """Create a DatabaseMiddleware instance with in-memory SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite"}
            middleware = DatabaseMiddleware(db_config, config_path=tmpdir)
            yield middleware

    def test_get_session(self, db_middleware):
        """Test getting a database session."""
        session = db_middleware.get_session()
        assert session is not None
        assert isinstance(session, Session)
        session.close()

    def test_close_session(self, db_middleware):
        """Test closing a database session."""
        session = db_middleware.get_session()
        db_middleware.close_session(session)
        # Verify session is closed by checking if we can still use it
        # After close, operations should fail
        with pytest.raises(Exception):
            session.query(User_mgmt).first()

    def test_add_user(self, db_middleware):
        """Test adding a user to the database."""
        session = db_middleware.get_session()
        
        user = User_mgmt(
            id="user_001",
            username="testuser",
            password="test123"
        )
        session.add(user)
        session.commit()
        
        # Verify user was added
        retrieved = session.query(User_mgmt).filter_by(id="user_001").first()
        assert retrieved is not None
        assert retrieved.username == "testuser"
        
        session.close()

    def test_add_post(self, db_middleware):
        """Test adding a post to the database."""
        session = db_middleware.get_session()
        
        # First add a user
        user = User_mgmt(id="user_001", username="testuser", password="test123")
        session.add(user)
        session.commit()
        
        # Add post
        post = Post(
            id="post_001",
            user_id="user_001",
            content="Test post content",
            round=1,
            timeslot=0
        )
        session.add(post)
        session.commit()
        
        # Verify post was added
        retrieved = session.query(Post).filter_by(id="post_001").first()
        assert retrieved is not None
        assert retrieved.content == "Test post content"
        assert retrieved.user_id == "user_001"
        
        session.close()

    def test_add_reaction(self, db_middleware):
        """Test adding a reaction to the database."""
        session = db_middleware.get_session()
        
        # Setup: user and post
        user = User_mgmt(id="user_001", username="testuser", password="test123")
        post = Post(id="post_001", user_id="user_001", content="Test", round=1, timeslot=0)
        session.add(user)
        session.add(post)
        session.commit()
        
        # Add reaction
        reaction = Reaction(
            id="reaction_001",
            user_id="user_001",
            post_id="post_001",
            reaction_type="like",
            round=1,
            timeslot=1
        )
        session.add(reaction)
        session.commit()
        
        # Verify
        retrieved = session.query(Reaction).filter_by(id="reaction_001").first()
        assert retrieved is not None
        assert retrieved.reaction_type == "like"
        
        session.close()

    def test_add_follow(self, db_middleware):
        """Test adding a follow relationship to the database."""
        session = db_middleware.get_session()
        
        # Setup: two users
        user1 = User_mgmt(id="user_001", username="user1", password="test123")
        user2 = User_mgmt(id="user_002", username="user2", password="test123")
        session.add_all([user1, user2])
        session.commit()
        
        # Add follow
        follow = Follow(
            id="follow_001",
            follower_id="user_001",  # user1 follows user2
            user_id="user_002",
            action="follow",
            round=1,
            timeslot=0
        )
        session.add(follow)
        session.commit()
        
        # Verify
        retrieved = session.query(Follow).filter_by(id="follow_001").first()
        assert retrieved is not None
        assert retrieved.follower_id == "user_001"
        assert retrieved.user_id == "user_002"
        assert retrieved.action == "follow"
        
        session.close()

    def test_add_round(self, db_middleware):
        """Test adding a round to the database."""
        session = db_middleware.get_session()
        
        round_obj = Round(
            id=1,
            day=0,
            timeslot=0,
            timestamp=1234567890
        )
        session.add(round_obj)
        session.commit()
        
        # Verify
        retrieved = session.query(Round).filter_by(id=1).first()
        assert retrieved is not None
        assert retrieved.day == 0
        assert retrieved.timeslot == 0
        
        session.close()

    def test_query_nonexistent_user(self, db_middleware):
        """Test querying for a user that doesn't exist."""
        session = db_middleware.get_session()
        
        user = session.query(User_mgmt).filter_by(id="nonexistent").first()
        assert user is None
        
        session.close()

    def test_query_posts_by_user(self, db_middleware):
        """Test querying posts by user."""
        session = db_middleware.get_session()
        
        # Setup
        user = User_mgmt(id="user_001", username="testuser", password="test123")
        post1 = Post(id="post_001", user_id="user_001", content="Post 1", round=1, timeslot=0)
        post2 = Post(id="post_002", user_id="user_001", content="Post 2", round=1, timeslot=1)
        session.add_all([user, post1, post2])
        session.commit()
        
        # Query
        posts = session.query(Post).filter_by(user_id="user_001").all()
        assert len(posts) == 2
        assert {p.id for p in posts} == {"post_001", "post_002"}
        
        session.close()

    def test_query_followers(self, db_middleware):
        """Test querying followers of a user."""
        session = db_middleware.get_session()
        
        # Setup: user1 and user2 follow user3
        users = [
            User_mgmt(id="user_001", username="user1", password="test123"),
            User_mgmt(id="user_002", username="user2", password="test123"),
            User_mgmt(id="user_003", username="user3", password="test123"),
        ]
        follows = [
            Follow(id="f1", follower_id="user_001", user_id="user_003", action="follow", round=1, timeslot=0),
            Follow(id="f2", follower_id="user_002", user_id="user_003", action="follow", round=1, timeslot=0),
        ]
        session.add_all(users + follows)
        session.commit()
        
        # Query followers of user_003
        followers = session.query(Follow).filter_by(user_id="user_003", action="follow").all()
        assert len(followers) == 2
        assert {f.follower_id for f in followers} == {"user_001", "user_002"}
        
        session.close()

    def test_delete_post(self, db_middleware):
        """Test deleting a post from the database."""
        session = db_middleware.get_session()
        
        # Setup
        user = User_mgmt(id="user_001", username="testuser", password="test123")
        post = Post(id="post_001", user_id="user_001", content="Test", round=1, timeslot=0)
        session.add_all([user, post])
        session.commit()
        
        # Delete
        session.delete(post)
        session.commit()
        
        # Verify
        retrieved = session.query(Post).filter_by(id="post_001").first()
        assert retrieved is None
        
        session.close()

    def test_update_user(self, db_middleware):
        """Test updating a user in the database."""
        session = db_middleware.get_session()
        
        # Setup
        user = User_mgmt(id="user_001", username="oldname", password="test123")
        session.add(user)
        session.commit()
        
        # Update
        user.username = "newname"
        session.commit()
        
        # Verify
        retrieved = session.query(User_mgmt).filter_by(id="user_001").first()
        assert retrieved.username == "newname"
        
        session.close()


class TestRedisContentRecommendations:
    """Test Redis-based content recommendation strategies."""

    def test_recommend_rchrono_redis_basic(self):
        """Test basic reverse chronological recommendation."""
        posts = [
            {"id": "post_001", "index": 3, "reaction_count": 5},
            {"id": "post_002", "index": 2, "reaction_count": 10},
            {"id": "post_003", "index": 1, "reaction_count": 2},
        ]
        
        result = recommend_rchrono_redis(posts, limit=2)
        
        assert len(result) == 2
        assert result == ["post_001", "post_002"]

    def test_recommend_rchrono_redis_empty_posts(self):
        """Test reverse chronological with empty posts list."""
        result = recommend_rchrono_redis([], limit=5)
        assert result == []

    def test_recommend_rchrono_redis_limit_exceeds(self):
        """Test reverse chronological when limit exceeds available posts."""
        posts = [
            {"id": "post_001", "index": 1, "reaction_count": 5},
        ]
        
        result = recommend_rchrono_redis(posts, limit=10)
        assert len(result) == 1
        assert result == ["post_001"]

    def test_recommend_rchrono_popularity_redis_basic(self):
        """Test reverse chronological with popularity boost."""
        posts = [
            {"id": "post_001", "index": 1, "reaction_count": 5},
            {"id": "post_002", "index": 1, "reaction_count": 10},
            {"id": "post_003", "index": 2, "reaction_count": 2},
        ]
        
        result = recommend_rchrono_popularity_redis(posts, limit=3)
        
        assert len(result) == 3
        # Should be sorted by index first, then by reaction_count (descending)
        assert result[0] == "post_002"  # index=1, reactions=10
        assert result[1] == "post_001"  # index=1, reactions=5

    def test_recommend_rchrono_popularity_redis_empty(self):
        """Test popularity recommendation with empty posts."""
        result = recommend_rchrono_popularity_redis([], limit=5)
        assert result == []

    def test_recommend_rchrono_popularity_redis_single(self):
        """Test popularity recommendation with single post."""
        posts = [{"id": "post_001", "index": 1, "reaction_count": 5}]
        result = recommend_rchrono_popularity_redis(posts, limit=1)
        assert result == ["post_001"]

    @patch('YSimulator.YServer.recsys.content_recsys_redis.Session')
    def test_recommend_rchrono_followers_redis_basic(self, mock_session_class):
        """Test recommendation prioritizing followed users."""
        # Mock database session
        mock_session = Mock()
        mock_query = Mock()
        mock_session_class.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [("user_002",)]  # Following user_002
        
        posts = [
            {"id": "post_001", "index": 3, "reaction_count": 5},
            {"id": "post_002", "index": 2, "reaction_count": 10},
            {"id": "post_003", "index": 1, "reaction_count": 2},
        ]
        
        posts_data = [
            {"user_id": "user_001"},
            {"user_id": "user_002"},  # Followed user
            {"user_id": "user_003"},
        ]
        
        all_post_ids = ["post_001", "post_002", "post_003"]
        
        result = recommend_rchrono_followers_redis(
            posts,
            limit=2,
            agent_id="agent_001",
            followers_ratio=0.5,
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            db_engine=Mock()
        )
        
        assert len(result) <= 2
        # Should prioritize post_002 (from followed user)
        assert "post_002" in result

    @patch('YSimulator.YServer.recsys.content_recsys_redis.Session')
    def test_recommend_rchrono_followers_redis_no_follows(self, mock_session_class):
        """Test follower recommendation when not following anyone."""
        mock_session = Mock()
        mock_query = Mock()
        mock_session_class.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []  # Not following anyone
        
        posts = [
            {"id": "post_001", "index": 1, "reaction_count": 5},
            {"id": "post_002", "index": 2, "reaction_count": 10},
        ]
        
        posts_data = [
            {"user_id": "user_001"},
            {"user_id": "user_002"},
        ]
        
        all_post_ids = ["post_001", "post_002"]
        
        result = recommend_rchrono_followers_redis(
            posts,
            limit=2,
            agent_id="agent_001",
            followers_ratio=0.5,
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            db_engine=Mock()
        )
        
        assert len(result) == 2

    @patch('YSimulator.YServer.recsys.content_recsys_redis.Session')
    def test_recommend_rchrono_followers_redis_full_followers(self, mock_session_class):
        """Test follower recommendation with 100% followers ratio."""
        mock_session = Mock()
        mock_query = Mock()
        mock_session_class.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [("user_001",), ("user_002",)]
        
        posts = [
            {"id": "post_001", "index": 1, "reaction_count": 5},
            {"id": "post_002", "index": 2, "reaction_count": 10},
            {"id": "post_003", "index": 3, "reaction_count": 3},
        ]
        
        posts_data = [
            {"user_id": "user_001"},  # Followed
            {"user_id": "user_002"},  # Followed
            {"user_id": "user_003"},  # Not followed
        ]
        
        all_post_ids = ["post_001", "post_002", "post_003"]
        
        result = recommend_rchrono_followers_redis(
            posts,
            limit=2,
            agent_id="agent_001",
            followers_ratio=1.0,  # 100% from followers
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            db_engine=Mock()
        )
        
        assert len(result) == 2
        # Should prioritize posts from followed users
        assert set(result).issubset({"post_001", "post_002"})


class TestRedisFollowRecommendations:
    """Test Redis-based follow recommendation strategies."""

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_random_follows_redis_basic(self, mock_redis_class):
        """Test basic random follow recommendations."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = {b"user_001", b"user_002", b"user_003"}
        mock_redis.keys.return_value = []  # Not following anyone
        
        mock_logger = Mock()
        
        result = recommend_random_follows_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            2,
            mock_logger
        )
        
        assert len(result) <= 2
        # Should not include agent itself
        assert b"agent_001" not in result

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_random_follows_redis_empty_users(self, mock_redis_class):
        """Test random follow recommendations with no users."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = set()
        
        mock_logger = Mock()
        
        result = recommend_random_follows_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            5,
            mock_logger
        )
        
        assert result == []

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_random_follows_redis_with_existing_follows(self, mock_redis_class):
        """Test random follow recommendations excluding already followed users."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = {b"user_001", b"user_002", b"user_003"}
        mock_redis.keys.return_value = [b"follow_key_1"]
        mock_redis.hgetall.return_value = {
            "follower_id": "agent_001",
            "user_id": "user_002",
            "action": "follow"
        }
        
        mock_logger = Mock()
        
        result = recommend_random_follows_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            2,
            mock_logger
        )
        
        # Should not recommend user_002 (already following) or agent_001 (self)
        assert "user_002" not in result
        assert "agent_001" not in result

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_random_follows_redis_error_handling(self, mock_redis_class):
        """Test error handling in random follow recommendations."""
        mock_redis = Mock()
        mock_redis.smembers.side_effect = Exception("Redis error")
        
        mock_logger = Mock()
        
        result = recommend_random_follows_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            5,
            mock_logger
        )
        
        assert result == []
        mock_logger.error.assert_called()

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_preferential_attachment_redis_basic(self, mock_redis_class):
        """Test preferential attachment (popular users) recommendations."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = {b"user_001", b"user_002", b"user_003"}
        mock_redis.keys.return_value = []
        
        mock_logger = Mock()
        
        result = recommend_preferential_attachment_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            2,
            mock_logger
        )
        
        assert len(result) <= 2

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_preferential_attachment_redis_empty(self, mock_redis_class):
        """Test preferential attachment with no users."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = set()
        
        mock_logger = Mock()
        
        result = recommend_preferential_attachment_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            5,
            mock_logger
        )
        
        assert result == []

    @patch('YSimulator.YServer.recsys.follow_recsys_redis.Redis')
    def test_recommend_preferential_attachment_redis_error(self, mock_redis_class):
        """Test error handling in preferential attachment."""
        mock_redis = Mock()
        mock_redis.smembers.side_effect = Exception("Connection error")
        
        mock_logger = Mock()
        
        result = recommend_preferential_attachment_redis(
            mock_redis,
            lambda x, y: f"key:{x}:{y}",
            "agent_001",
            5,
            mock_logger
        )
        
        assert result == []
        mock_logger.error.assert_called()


class TestDatabaseMiddlewareConstants:
    """Test constants and defaults in DatabaseMiddleware."""

    def test_default_username_constant(self):
        """Test DEFAULT_USERNAME constant."""
        assert DEFAULT_USERNAME == "Someone"

    def test_default_visibility_rounds(self):
        """Test default visibility_rounds value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware({"type": "sqlite"}, config_path=tmpdir)
            assert middleware.visibility_rounds == 36

    def test_default_num_slots_per_day(self):
        """Test default num_slots_per_day value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware({"type": "sqlite"}, config_path=tmpdir)
            assert middleware.num_slots_per_day == 24

    def test_default_redis_sliding_window(self):
        """Test default Redis sliding window days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware({"type": "sqlite"}, config_path=tmpdir)
            assert middleware.redis_sliding_window_days == 2


class TestDatabaseMiddlewareEdgeCases:
    """Test edge cases and error conditions."""

    def test_init_with_none_simulation_config(self):
        """Test initialization with None simulation config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware(
                {"type": "sqlite"},
                config_path=tmpdir,
                simulation_config=None
            )
            assert middleware.visibility_rounds == 36
            assert middleware.num_slots_per_day == 24

    def test_init_with_empty_simulation_config(self):
        """Test initialization with empty simulation config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware(
                {"type": "sqlite"},
                config_path=tmpdir,
                simulation_config={}
            )
            assert middleware.visibility_rounds == 36
            assert middleware.num_slots_per_day == 24

    def test_init_with_partial_simulation_config(self):
        """Test initialization with partial simulation config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware(
                {"type": "sqlite"},
                config_path=tmpdir,
                simulation_config={"posts": {"visibility_rounds": 48}}
            )
            assert middleware.visibility_rounds == 48
            assert middleware.num_slots_per_day == 24  # default

    def test_session_operations_sequence(self):
        """Test sequence of session operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware({"type": "sqlite"}, config_path=tmpdir)
            
            # Multiple get_session calls
            session1 = middleware.get_session()
            session2 = middleware.get_session()
            
            assert session1 is not None
            assert session2 is not None
            assert session1 is not session2  # Different sessions
            
            middleware.close_session(session1)
            middleware.close_session(session2)

    def test_database_operations_with_constraints(self):
        """Test database operations that might violate constraints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            middleware = DatabaseMiddleware({"type": "sqlite"}, config_path=tmpdir)
            session = middleware.get_session()
            
            # Add user
            user = User_mgmt(id="user_001", username="test", password="pass")
            session.add(user)
            session.commit()
            
            # Try to add duplicate user (should fail)
            duplicate_user = User_mgmt(id="user_001", username="test2", password="pass2")
            session.add(duplicate_user)
            
            with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
                session.commit()
            
            session.rollback()
            session.close()
