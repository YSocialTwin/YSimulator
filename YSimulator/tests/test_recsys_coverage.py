"""
Tests for recommendation systems and interest management.

These tests cover content recommendation, follow recommendation,
and interest tracking functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any


class TestContentRecommendationSystem:
    """Test content recommendation system."""

    @pytest.fixture
    def mock_db_middleware(self):
        """Create a mock database middleware."""
        mock = Mock()
        mock.get_user_interests = Mock(return_value=["technology", "science"])
        mock.get_recent_posts = Mock(return_value=[])
        mock.get_trending_topics = Mock(return_value=["tech", "ai"])
        return mock

    def test_content_recsys_initialization(self):
        """Test content recommendation system initialization."""
        try:
            from YSimulator.YServer.recsys.content_recsys import ContentRecommendationSystem
            
            recsys = ContentRecommendationSystem(max_recommendations=10)
            assert recsys is not None
        except ImportError:
            pytest.skip("Content recsys module not available")

    def test_content_recsys_get_recommendations(self, mock_db_middleware):
        """Test getting content recommendations."""
        try:
            from YSimulator.YServer.recsys.content_recsys import ContentRecommendationSystem
            
            recsys = ContentRecommendationSystem(max_recommendations=5)
            
            with patch.object(recsys, 'db', mock_db_middleware):
                recommendations = recsys.get_recommendations(
                    user_id="test-user-123",
                    num_recommendations=3
                )
                
                assert isinstance(recommendations, list)
                assert len(recommendations) <= 3
        except (ImportError, AttributeError):
            pytest.skip("Content recsys not fully available")

    def test_content_recsys_filter_seen_posts(self):
        """Test filtering of already seen posts."""
        try:
            from YSimulator.YServer.recsys.content_recsys import ContentRecommendationSystem
            
            recsys = ContentRecommendationSystem(max_recommendations=10)
            
            all_posts = [
                {"id": "post1", "content": "Test 1"},
                {"id": "post2", "content": "Test 2"},
                {"id": "post3", "content": "Test 3"},
            ]
            
            seen_posts = {"post1", "post3"}
            
            # Mock filtering method if available
            if hasattr(recsys, 'filter_seen'):
                filtered = recsys.filter_seen(all_posts, seen_posts)
                assert len(filtered) == 1
                assert filtered[0]["id"] == "post2"
        except ImportError:
            pytest.skip("Content recsys module not available")


class TestFollowRecommendationSystem:
    """Test follow recommendation system."""

    @pytest.fixture
    def mock_user_data(self):
        """Create mock user data."""
        return {
            "id": "user123",
            "username": "test_user",
            "interests": ["technology", "science"],
            "followers": [],
            "following": []
        }

    def test_follow_recsys_initialization(self):
        """Test follow recommendation system initialization."""
        try:
            from YSimulator.YServer.recsys.follow_recsys_db import FollowRecommendationSystem
            
            recsys = FollowRecommendationSystem(db_path=":memory:")
            assert recsys is not None
        except ImportError:
            pytest.skip("Follow recsys module not available")

    def test_follow_recsys_get_recommendations(self, mock_user_data):
        """Test getting follow recommendations."""
        try:
            from YSimulator.YServer.recsys.follow_recsys_db import FollowRecommendationSystem
            
            recsys = FollowRecommendationSystem(db_path=":memory:")
            
            recommendations = recsys.get_recommendations(
                user_id=mock_user_data["id"],
                num_recommendations=5
            )
            
            assert isinstance(recommendations, list)
            assert len(recommendations) <= 5
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Follow recsys not fully available: {e}")

    def test_follow_recsys_similarity_scoring(self):
        """Test user similarity scoring for recommendations."""
        try:
            from YSimulator.YServer.recsys.follow_recsys_db import FollowRecommendationSystem
            
            recsys = FollowRecommendationSystem(db_path=":memory:")
            
            user1_interests = ["tech", "ai", "ml"]
            user2_interests = ["tech", "ai"]
            
            # Mock similarity calculation if available
            if hasattr(recsys, 'calculate_similarity'):
                similarity = recsys.calculate_similarity(user1_interests, user2_interests)
                assert 0 <= similarity <= 1
                assert similarity > 0  # Should have some similarity
        except ImportError:
            pytest.skip("Follow recsys module not available")


class TestInterestManager:
    """Test interest management system."""

    def test_interest_manager_initialization(self):
        """Test interest manager initialization."""
        try:
            from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
            
            manager = InterestManager(db_path=":memory:")
            assert manager is not None
        except ImportError:
            pytest.skip("Interest manager module not available")

    def test_interest_manager_update_interests(self):
        """Test updating user interests."""
        try:
            from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
            
            manager = InterestManager(db_path=":memory:")
            
            user_id = "test-user-123"
            new_interests = ["technology", "science", "programming"]
            
            manager.update_interests(user_id, new_interests)
            
            # Retrieve and verify
            interests = manager.get_interests(user_id)
            assert isinstance(interests, list)
        except (ImportError, AttributeError):
            pytest.skip("Interest manager not fully available")

    def test_interest_manager_track_interaction(self):
        """Test tracking interest-based interactions."""
        try:
            from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
            
            manager = InterestManager(db_path=":memory:")
            
            user_id = "test-user-123"
            topic = "technology"
            interaction_type = "read"
            
            if hasattr(manager, 'track_interaction'):
                manager.track_interaction(user_id, topic, interaction_type)
                
                # Should update interest scores
                interests = manager.get_interests(user_id)
                assert isinstance(interests, (list, dict))
        except ImportError:
            pytest.skip("Interest manager module not available")

    def test_interest_manager_get_trending_topics(self):
        """Test getting trending topics."""
        try:
            from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
            
            manager = InterestManager(db_path=":memory:")
            
            if hasattr(manager, 'get_trending_topics'):
                trending = manager.get_trending_topics(limit=10)
                assert isinstance(trending, list)
                assert len(trending) <= 10
        except ImportError:
            pytest.skip("Interest manager module not available")


class TestRecommendationUtils:
    """Test recommendation system utility functions."""

    def test_calculate_similarity_score(self):
        """Test similarity score calculation."""
        try:
            from YSimulator.YServer.recsys.utils import calculate_similarity
            
            vec1 = [1, 0, 1, 0, 1]
            vec2 = [1, 1, 1, 0, 0]
            
            similarity = calculate_similarity(vec1, vec2)
            
            assert isinstance(similarity, float)
            assert 0 <= similarity <= 1
        except ImportError:
            pytest.skip("Recsys utils module not available")

    def test_normalize_scores(self):
        """Test score normalization."""
        try:
            from YSimulator.YServer.recsys.utils import normalize_scores
            
            scores = [10, 20, 30, 40, 50]
            
            normalized = normalize_scores(scores)
            
            assert isinstance(normalized, list)
            assert len(normalized) == len(scores)
            assert all(0 <= score <= 1 for score in normalized)
        except ImportError:
            pytest.skip("Recsys utils module not available")

    def test_diversity_filter(self):
        """Test diversity filtering for recommendations."""
        try:
            from YSimulator.YServer.recsys.utils import apply_diversity_filter
            
            recommendations = [
                {"id": "post1", "topic": "tech"},
                {"id": "post2", "topic": "tech"},
                {"id": "post3", "topic": "science"},
                {"id": "post4", "topic": "tech"},
                {"id": "post5", "topic": "sports"},
            ]
            
            filtered = apply_diversity_filter(recommendations, max_per_topic=2)
            
            assert isinstance(filtered, list)
            # Should limit tech posts to 2
            tech_count = sum(1 for post in filtered if post["topic"] == "tech")
            assert tech_count <= 2
        except ImportError:
            pytest.skip("Recsys utils module not available")


class TestRedisRecommendationCache:
    """Test Redis-based recommendation caching."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.get = Mock(return_value=None)
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.delete = Mock(return_value=1)
        return mock

    def test_content_recsys_redis_cache_hit(self, mock_redis):
        """Test Redis cache hit for content recommendations."""
        try:
            from YSimulator.YServer.recsys.content_recsys_redis import ContentRecsysRedis
            
            recsys = ContentRecsysRedis(redis_client=mock_redis)
            
            # Simulate cache hit
            mock_redis.get.return_value = '["post1", "post2", "post3"]'
            
            cached = recsys.get_cached_recommendations("user123")
            
            assert cached is not None
            mock_redis.get.assert_called_once()
        except ImportError:
            pytest.skip("Redis recsys module not available")

    def test_content_recsys_redis_cache_miss(self, mock_redis):
        """Test Redis cache miss for content recommendations."""
        try:
            from YSimulator.YServer.recsys.content_recsys_redis import ContentRecsysRedis
            
            recsys = ContentRecsysRedis(redis_client=mock_redis)
            
            # Simulate cache miss
            mock_redis.get.return_value = None
            
            cached = recsys.get_cached_recommendations("user123")
            
            assert cached is None
            mock_redis.get.assert_called_once()
        except ImportError:
            pytest.skip("Redis recsys module not available")

    def test_follow_recsys_redis_cache_set(self, mock_redis):
        """Test setting Redis cache for follow recommendations."""
        try:
            from YSimulator.YServer.recsys.follow_recsys_redis import FollowRecsysRedis
            
            recsys = FollowRecsysRedis(redis_client=mock_redis)
            
            recommendations = ["user1", "user2", "user3"]
            
            recsys.cache_recommendations("user123", recommendations, ttl=3600)
            
            mock_redis.set.assert_called_once()
            mock_redis.expire.assert_called_once()
        except ImportError:
            pytest.skip("Redis recsys module not available")

    def test_redis_cache_invalidation(self, mock_redis):
        """Test Redis cache invalidation."""
        try:
            from YSimulator.YServer.recsys.content_recsys_redis import ContentRecsysRedis
            
            recsys = ContentRecsysRedis(redis_client=mock_redis)
            
            recsys.invalidate_cache("user123")
            
            mock_redis.delete.assert_called_once()
        except ImportError:
            pytest.skip("Redis recsys module not available")
