"""
Tests for repository layer implementations.

This test suite validates the SQL and Redis repository implementations
against their abstract interfaces.

Note on Field Name Mappings:
The repository layer handles translation between API field names and database model field names:
- API 'author' <-> Model 'user_id'
- API 'text' <-> Model 'tweet'
- API 'parent_post' <-> Model 'comment_to'
- API 'root_post' <-> Model 'thread_id'
- API 'num_reactions' <-> Model 'reaction_count'
- API 'followee_id' <-> Model 'user_id' (in Follow model)
- API 'round_id' <-> Model 'tid' (in Agent_Opinion model)

For complete mapping documentation, see docs/REPOSITORY_PATTERN.md
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from YSimulator.YServer.repositories.redis_repository import (
    RedisFollowRepository,
    RedisInterestRepository,
    RedisPostRepository,
    RedisRecommendationRepository,
    RedisUserRepository,
)
from YSimulator.YServer.repositories.sql_repository import (
    SQLFollowRepository,
    SQLInterestRepository,
    SQLPostRepository,
    SQLRecommendationRepository,
    SQLUserRepository,
)

# ============================================================================
# SQL Repository Tests
# ============================================================================


class TestSQLUserRepository:
    """Test suite for SQLUserRepository."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_engine):
        """Create a SQLUserRepository instance."""
        return SQLUserRepository(mock_engine)

    def test_register_user_success(self, repository, mock_engine):
        """Test successful user registration."""
        user_data = {
            "id": "user1",
            "username": "testuser",
            "leaning": 0.5,
            "archetype": "test",
        }

        # Mock the session
        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = None

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.register_user(user_data)

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_register_user_duplicate(self, repository, mock_engine):
        """Test registering a duplicate user."""
        user_data = {"id": "user1", "username": "testuser"}

        # Mock existing user
        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = Mock()

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.register_user(user_data)

        assert result is False
        mock_session.close.assert_called_once()

    def test_get_user_success(self, repository, mock_engine):
        """Test getting a user by ID."""
        user_id = "user1"

        # Mock user object
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.username = "testuser"
        mock_user.leaning = 0.5
        mock_user.archetype = "test"
        mock_user.is_llm = False
        mock_user.model_name = None

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_user

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_user(user_id)

        assert result is not None
        assert result["id"] == user_id
        assert result["username"] == "testuser"
        mock_session.close.assert_called_once()

    def test_get_user_not_found(self, repository, mock_engine):
        """Test getting a non-existent user."""
        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = None

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_user("nonexistent")

        assert result is None
        mock_session.close.assert_called_once()

    def test_register_users_batch(self, repository, mock_engine):
        """Test batch user registration."""
        users_data = [
            {"id": "user1", "username": "user1"},
            {"id": "user2", "username": "user2"},
            {"id": "user3", "username": "user3"},
        ]

        mock_session = Mock(spec=Session)
        mock_session.query().filter().all.return_value = []

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            count, ids = repository.register_users_batch(users_data)

        assert count == 3
        assert len(ids) == 3
        mock_session.bulk_insert_mappings.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_update_user_archetype(self, repository, mock_engine):
        """Test updating user archetype."""
        user_id = "user1"
        new_archetype = "updated"

        mock_user = Mock()
        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_user

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.update_user_archetype(user_id, new_archetype)

        assert result is True
        assert mock_user.archetype == new_archetype
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestSQLPostRepository:
    """Test suite for SQLPostRepository."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_engine):
        """Create a SQLPostRepository instance."""
        return SQLPostRepository(mock_engine)

    def test_add_post_success(self, repository, mock_engine):
        """Test adding a post."""
        post_data = {
            "id": "post1",
            "author": "user1",
            "text": "Test post",
            "round": "round1",
        }

        mock_session = Mock(spec=Session)

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.add_post(post_data)

        assert result == "post1"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_get_post_success(self, repository, mock_engine):
        """Test getting a post by ID."""
        post_id = "post1"

        mock_post = Mock()
        mock_post.id = post_id
        mock_post.user_id = "user1"  # Model uses user_id not author
        mock_post.tweet = "Test post"  # Model uses tweet not text
        mock_post.round = "round1"
        mock_post.comment_to = None  # Model uses comment_to not parent_post
        mock_post.thread_id = None  # Model uses thread_id not root_post
        mock_post.reaction_count = 5  # Model uses reaction_count not num_reactions

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_post

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_post(post_id)

        assert result is not None
        assert result["id"] == post_id
        assert result["author"] == "user1"
        mock_session.close.assert_called_once()

    def test_get_recent_posts(self, repository, mock_engine):
        """Test getting recent posts."""
        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_query.order_by().limit().all.return_value = [("post1",), ("post2",), ("post3",)]
        mock_session.query.return_value = mock_query

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_recent_posts(limit=3)

        assert len(result) == 3
        assert result == ["post1", "post2", "post3"]
        mock_session.close.assert_called_once()

    def test_increment_post_reaction_count(self, repository, mock_engine):
        """Test incrementing post reaction count."""
        post_id = "post1"

        mock_post = Mock()
        mock_post.reaction_count = 5  # Model uses reaction_count not num_reactions

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_post

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.increment_post_reaction_count(post_id)

        assert result is True
        assert mock_post.reaction_count == 6
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestSQLFollowRepository:
    """Test suite for SQLFollowRepository."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_engine):
        """Create a SQLFollowRepository instance."""
        return SQLFollowRepository(mock_engine)

    def test_add_follow_success(self, repository, mock_engine):
        """Test adding a follow relationship."""
        follow_data = {
            "follower_id": "user1",
            "followee_id": "user2",
        }

        mock_session = Mock(spec=Session)

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.add_follow(follow_data)

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_add_follows_batch(self, repository, mock_engine):
        """Test batch adding follow relationships."""
        follows_data = [
            {"follower_id": "user1", "followee_id": "user2"},
            {"follower_id": "user1", "followee_id": "user3"},
            {"follower_id": "user2", "followee_id": "user3"},
        ]

        mock_session = Mock(spec=Session)

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            count = repository.add_follows_batch(follows_data)

        assert count == 3
        mock_session.bulk_insert_mappings.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestSQLInterestRepository:
    """Test suite for SQLInterestRepository."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_engine):
        """Create a SQLInterestRepository instance."""
        return SQLInterestRepository(mock_engine)

    def test_add_or_get_interest_new(self, repository, mock_engine):
        """Test adding a new interest."""
        interest_name = "politics"

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = None

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.add_or_get_interest(interest_name)

        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_add_or_get_interest_existing(self, repository, mock_engine):
        """Test getting an existing interest."""
        interest_name = "politics"
        interest_id = "interest1"

        mock_interest = Mock()
        mock_interest.iid = interest_id

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_interest

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.add_or_get_interest(interest_name)

        assert result == interest_id
        mock_session.add.assert_not_called()
        mock_session.close.assert_called_once()

    def test_add_agent_opinion(self, repository, mock_engine):
        """Test adding an agent opinion."""
        mock_session = Mock(spec=Session)

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.add_agent_opinion("agent1", "topic1", 0.8, "round1")

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestSQLRecommendationRepository:
    """Test suite for SQLRecommendationRepository."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_engine):
        """Create a SQLRecommendationRepository instance."""
        return SQLRecommendationRepository(mock_engine)

    def test_get_or_create_round_new(self, repository, mock_engine):
        """Test creating a new round."""
        day = 1
        hour = 10

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = None

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_or_create_round(day, hour)

        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_get_or_create_round_existing(self, repository, mock_engine):
        """Test getting an existing round."""
        day = 1
        hour = 10
        round_id = "round1"

        mock_round = Mock()
        mock_round.id = round_id

        mock_session = Mock(spec=Session)
        mock_session.query().filter_by().first.return_value = mock_round

        with patch(
            "YSimulator.YServer.repositories.sql_repository.Session", return_value=mock_session
        ):
            result = repository.get_or_create_round(day, hour)

        assert result == round_id
        mock_session.add.assert_not_called()
        mock_session.close.assert_called_once()


# ============================================================================
# Redis Repository Tests
# ============================================================================


class TestRedisUserRepository:
    """Test suite for RedisUserRepository."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_redis):
        """Create a RedisUserRepository instance."""
        return RedisUserRepository(mock_redis)

    def test_register_user_success(self, repository, mock_redis):
        """Test successful user registration."""
        user_data = {
            "id": "user1",
            "username": "testuser",
            "leaning": "0.5",
        }

        mock_redis.exists.return_value = False
        result = repository.register_user(user_data)

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.sadd.assert_called_once()

    def test_register_user_duplicate(self, repository, mock_redis):
        """Test registering a duplicate user."""
        user_data = {"id": "user1", "username": "testuser"}

        mock_redis.exists.return_value = True
        result = repository.register_user(user_data)

        assert result is False
        mock_redis.hset.assert_not_called()

    def test_get_user_success(self, repository, mock_redis):
        """Test getting a user by ID."""
        user_id = "user1"

        mock_redis.hgetall.return_value = {
            b"id": b"user1",
            b"username": b"testuser",
            b"leaning": b"0.5",
        }

        result = repository.get_user(user_id)

        assert result is not None
        assert result["id"] == "user1"
        assert result["username"] == "testuser"

    def test_get_user_not_found(self, repository, mock_redis):
        """Test getting a non-existent user."""
        mock_redis.hgetall.return_value = {}
        result = repository.get_user("nonexistent")

        assert result is None

    def test_update_user_archetype(self, repository, mock_redis):
        """Test updating user archetype."""
        user_id = "user1"
        new_archetype = "updated"

        mock_redis.exists.return_value = True
        result = repository.update_user_archetype(user_id, new_archetype)

        assert result is True
        mock_redis.hset.assert_called_once()


class TestRedisPostRepository:
    """Test suite for RedisPostRepository."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_redis):
        """Create a RedisPostRepository instance."""
        return RedisPostRepository(mock_redis)

    def test_add_post_success(self, repository, mock_redis):
        """Test adding a post."""
        post_data = {
            "id": "post1",
            "author": "user1",
            "text": "Test post",
        }

        result = repository.add_post(post_data)

        assert result == "post1"
        mock_redis.hset.assert_called_once()
        # Changed from sadd to lpush to align with db_middleware
        mock_redis.lpush.assert_called_once()

    def test_get_post_success(self, repository, mock_redis):
        """Test getting a post by ID."""
        mock_redis.hgetall.return_value = {
            b"id": b"post1",
            b"author": b"user1",
            b"text": b"Test post",
        }

        result = repository.get_post("post1")

        assert result is not None
        assert result["id"] == "post1"
        assert result["author"] == "user1"

    def test_increment_post_reaction_count(self, repository, mock_redis):
        """Test incrementing post reaction count."""
        post_id = "post1"

        mock_redis.exists.return_value = True
        # Mock the hget to return current count
        mock_redis.hget.return_value = b"5"
        result = repository.increment_post_reaction_count(post_id)

        assert result is True
        # Changed from hincrby to hget+hset to align with db_middleware
        mock_redis.hget.assert_called_once()
        mock_redis.hset.assert_called_once_with(
            repository._redis_key("posts", post_id),
            "reaction_count",  # Changed from num_reactions to reaction_count
            6,
        )


class TestRedisFollowRepository:
    """Test suite for RedisFollowRepository."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_redis):
        """Create a RedisFollowRepository instance."""
        return RedisFollowRepository(mock_redis)

    def test_add_follow_success(self, repository, mock_redis):
        """Test adding a follow relationship."""
        follow_data = {
            "follower_id": "user1",
            "followee_id": "user2",
        }

        result = repository.add_follow(follow_data)

        assert result is True
        # Changed from bidirectional sadd to single hset to align with db_middleware
        mock_redis.hset.assert_called_once()


class TestRedisInterestRepository:
    """Test suite for RedisInterestRepository."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_redis):
        """Create a RedisInterestRepository instance."""
        return RedisInterestRepository(mock_redis)

    def test_add_or_get_interest_new(self, repository, mock_redis):
        """Test adding a new interest."""
        interest_name = "politics"

        mock_redis.get.return_value = None
        result = repository.add_or_get_interest(interest_name)

        assert result is not None
        mock_redis.hset.assert_called_once()
        mock_redis.set.assert_called_once()

    def test_add_or_get_interest_existing(self, repository, mock_redis):
        """Test getting an existing interest."""
        interest_name = "politics"
        interest_id = "interest1"

        mock_redis.get.return_value = interest_id.encode()
        result = repository.add_or_get_interest(interest_name)

        assert result == interest_id
        mock_redis.hset.assert_not_called()


class TestRedisRecommendationRepository:
    """Test suite for RedisRecommendationRepository."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_redis):
        """Create a RedisRecommendationRepository instance."""
        return RedisRecommendationRepository(mock_redis)

    def test_get_or_create_round_new(self, repository, mock_redis):
        """Test creating a new round."""
        day = 1
        hour = 10

        mock_redis.get.return_value = None
        result = repository.get_or_create_round(day, hour)

        assert result is not None
        mock_redis.set.assert_called()
        mock_redis.hset.assert_called_once()

    def test_get_or_create_round_existing(self, repository, mock_redis):
        """Test getting an existing round."""
        day = 1
        hour = 10
        round_id = "round1"

        mock_redis.get.return_value = round_id.encode()
        result = repository.get_or_create_round(day, hour)

        assert result == round_id
        mock_redis.hset.assert_not_called()
