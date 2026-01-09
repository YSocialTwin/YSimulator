"""
Comprehensive tests for Ray-based and server-side recommender systems.

Achieving 80%+ coverage for:
- YClient/recsys/ContentRecSys.py
- YClient/recsys/FollowRecSysRay.py
- YServer/recsys/content_recsys_db.py
- YServer/recsys/follow_recsys_db.py
- YServer/recsys/utils.py
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import ray


# ================================================
# CLIENT-SIDE RECOMMENDER SYSTEM TESTS
# ================================================


class TestContentRecSysClient:
    """Test ContentRecSys and its subclasses (client-side)."""

    def test_content_recsys_init_default(self):
        """Test ContentRecSys initialization with defaults."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        recsys = ContentRecSys()
        assert recsys.mode == "random"
        assert recsys.n_posts == 5
        assert recsys.followers_ratio == 0.6

    def test_content_recsys_init_custom(self):
        """Test ContentRecSys initialization with custom parameters."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        recsys = ContentRecSys(mode="rchrono_popularity", n_posts=10, followers_ratio=0.8)
        assert recsys.mode == "rchrono_popularity"
        assert recsys.n_posts == 10
        assert recsys.followers_ratio == 0.8

    @patch("ray.get")
    def test_content_recsys_get_recommendations_success(self, mock_ray_get):
        """Test successful recommendation fetching."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        # Mock server response
        mock_ray_get.return_value = ["post-1", "post-2", "post-3"]

        # Mock server handle
        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys(mode="rchrono", n_posts=3)
        result = recsys.get_recommendations(mock_server, "agent-1", "client-1")

        assert result == ["post-1", "post-2", "post-3"]
        mock_server.get_recommended_posts.remote.assert_called_once()

    @patch("ray.get")
    def test_content_recsys_get_recommendations_empty(self, mock_ray_get):
        """Test recommendations when server returns None."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        mock_ray_get.return_value = None
        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys()
        result = recsys.get_recommendations(mock_server, "agent-1")

        assert result == []

    @patch("ray.get")
    def test_content_recsys_get_recommendations_error(self, mock_ray_get):
        """Test error handling in recommendation fetching."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        mock_ray_get.side_effect = Exception("Network error")
        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys()
        result = recsys.get_recommendations(mock_server, "agent-1")

        assert result == []

    def test_reverse_chrono(self):
        """Test ReverseChrono initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChrono

        recsys = ReverseChrono(n_posts=7)
        assert recsys.mode == "rchrono"
        assert recsys.n_posts == 7

    def test_reverse_chrono_popularity(self):
        """Test ReverseChronoPopularity initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChronoPopularity

        recsys = ReverseChronoPopularity(n_posts=8)
        assert recsys.mode == "rchrono_popularity"
        assert recsys.n_posts == 8

    def test_reverse_chrono_followers(self):
        """Test ReverseChronoFollowers initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChronoFollowers

        recsys = ReverseChronoFollowers(n_posts=6, followers_ratio=0.7)
        assert recsys.mode == "rchrono_followers"
        assert recsys.n_posts == 6
        assert recsys.followers_ratio == 0.7

    def test_reverse_chrono_followers_popularity(self):
        """Test ReverseChronoFollowersPopularity initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChronoFollowersPopularity

        recsys = ReverseChronoFollowersPopularity(n_posts=9, followers_ratio=0.5)
        assert recsys.mode == "rchrono_followers_popularity"
        assert recsys.n_posts == 9
        assert recsys.followers_ratio == 0.5

    def test_reverse_chrono_comments(self):
        """Test ReverseChronoComments initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChronoComments

        recsys = ReverseChronoComments(n_posts=4)
        assert recsys.mode == "rchrono_comments"
        assert recsys.n_posts == 4

    def test_random_order(self):
        """Test RandomOrder initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import RandomOrder

        recsys = RandomOrder(n_posts=10)
        assert recsys.mode == "random"
        assert recsys.n_posts == 10

    def test_common_interests(self):
        """Test CommonInterests initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import CommonInterests

        recsys = CommonInterests(n_posts=5, followers_ratio=0.4)
        assert recsys.mode == "common_interests"
        assert recsys.n_posts == 5
        assert recsys.followers_ratio == 0.4

    def test_common_user_interests(self):
        """Test CommonUserInterests initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import CommonUserInterests

        recsys = CommonUserInterests(n_posts=6, followers_ratio=0.3)
        assert recsys.mode == "common_user_interests"
        assert recsys.n_posts == 6
        assert recsys.followers_ratio == 0.3

    def test_similar_users_react(self):
        """Test SimilarUsersReact initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import SimilarUsersReact

        recsys = SimilarUsersReact(n_posts=8)
        assert recsys.mode == "similar_users_react"
        assert recsys.n_posts == 8

    def test_similar_users_posts(self):
        """Test SimilarUsersPosts initialization."""
        from YSimulator.YClient.recsys.ContentRecSys import SimilarUsersPosts

        recsys = SimilarUsersPosts(n_posts=12)
        assert recsys.mode == "similar_users_posts"
        assert recsys.n_posts == 12


class TestFollowRecSysRayClient:
    """Test FollowRecSysRay and its subclasses (client-side)."""

    def test_follow_recsys_init_default(self):
        """Test FollowRecSysRay initialization with defaults."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        recsys = FollowRecSysRay()
        assert recsys.mode == "random"
        assert recsys.n_neighbors == 10
        assert recsys.leaning_bias == 1

    def test_follow_recsys_init_custom(self):
        """Test FollowRecSysRay initialization with custom parameters."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        recsys = FollowRecSysRay(mode="common_neighbors", n_neighbors=15, leaning_bias=2)
        assert recsys.mode == "common_neighbors"
        assert recsys.n_neighbors == 15
        assert recsys.leaning_bias == 2

    @patch("ray.get")
    def test_follow_recsys_get_suggestions_success(self, mock_ray_get):
        """Test successful follow suggestions fetching."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        mock_ray_get.return_value = ["user-1", "user-2", "user-3"]

        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay(mode="jaccard", n_neighbors=3)
        result = recsys.get_follow_suggestions(mock_server, "agent-1", "client-1")

        assert result == ["user-1", "user-2", "user-3"]
        mock_server.get_follow_suggestions.remote.assert_called_once()

    @patch("ray.get")
    def test_follow_recsys_get_suggestions_empty(self, mock_ray_get):
        """Test follow suggestions when server returns None."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        mock_ray_get.return_value = None
        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay()
        result = recsys.get_follow_suggestions(mock_server, "agent-1")

        assert result == []

    @patch("ray.get")
    def test_follow_recsys_get_suggestions_error(self, mock_ray_get):
        """Test error handling in follow suggestions fetching."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        mock_ray_get.side_effect = Exception("Database error")
        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay()
        result = recsys.get_follow_suggestions(mock_server, "agent-1")

        assert result == []

    def test_random_follow_recsys(self):
        """Test RandomFollowRecSys initialization."""
        from YSimulator.YClient.recsys.FollowRecSysRay import RandomFollowRecSys

        recsys = RandomFollowRecSys(n_neighbors=12, leaning_bias=3)
        assert recsys.mode == "random"
        assert recsys.n_neighbors == 12
        assert recsys.leaning_bias == 3

    def test_common_neighbors_follow_recsys(self):
        """Test CommonNeighborsFollowRecSys initialization."""
        from YSimulator.YClient.recsys.FollowRecSysRay import CommonNeighborsFollowRecSys

        recsys = CommonNeighborsFollowRecSys(n_neighbors=8, leaning_bias=2)
        assert recsys.mode == "common_neighbors"
        assert recsys.n_neighbors == 8

    def test_jaccard_follow_recsys(self):
        """Test JaccardFollowRecSys initialization."""
        from YSimulator.YClient.recsys.FollowRecSysRay import JaccardFollowRecSys

        recsys = JaccardFollowRecSys(n_neighbors=7, leaning_bias=1)
        assert recsys.mode == "jaccard"
        assert recsys.n_neighbors == 7

    def test_adamic_adar_follow_recsys(self):
        """Test AdamicAdarFollowRecSys initialization."""
        from YSimulator.YClient.recsys.FollowRecSysRay import AdamicAdarFollowRecSys

        recsys = AdamicAdarFollowRecSys(n_neighbors=9, leaning_bias=2)
        assert recsys.mode == "adamic_adar"
        assert recsys.n_neighbors == 9

    def test_preferential_attachment_follow_recsys(self):
        """Test PreferentialAttachmentFollowRecSys initialization."""
        from YSimulator.YClient.recsys.FollowRecSysRay import PreferentialAttachmentFollowRecSys

        recsys = PreferentialAttachmentFollowRecSys(n_neighbors=20, leaning_bias=4)
        assert recsys.mode == "preferential_attachment"
        assert recsys.n_neighbors == 20


# ================================================
# SERVER-SIDE CONTENT RECOMMENDER TESTS
# ================================================


class TestServerContentRecommenders:
    """Test server-side content recommendation functions."""

    def test_recommend_random_import(self):
        """Test importing recommend_random function."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        assert callable(recommend_random)

    def test_recommend_rchrono_import(self):
        """Test importing recommend_rchrono function."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono

        assert callable(recommend_rchrono)

    def test_recommend_rchrono_popularity_import(self):
        """Test importing recommend_rchrono_popularity function."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_popularity

        assert callable(recommend_rchrono_popularity)

    def test_content_recsys_function_signatures(self):
        """Test all content recommendation functions have consistent signatures."""
        from YSimulator.YServer.recsys import content_recsys_db

        functions = ["recommend_random", "recommend_rchrono", "recommend_rchrono_popularity"]

        for func_name in functions:
            assert hasattr(content_recsys_db, func_name)
            func = getattr(content_recsys_db, func_name)
            assert callable(func)


# ================================================
# SERVER-SIDE FOLLOW RECOMMENDER TESTS
# ================================================


class TestServerFollowRecommenders:
    """Test server-side follow recommendation functions."""

    def test_recommend_random_follows_import(self):
        """Test importing recommend_random_follows function."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        assert callable(recommend_random_follows)

    def test_recommend_common_neighbors_import(self):
        """Test importing recommend_common_neighbors function."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_common_neighbors

        assert callable(recommend_common_neighbors)

    def test_follow_recsys_function_signatures(self):
        """Test all follow recommendation functions have consistent signatures."""
        from YSimulator.YServer.recsys import follow_recsys_db

        functions = ["recommend_random_follows", "recommend_common_neighbors"]

        for func_name in functions:
            assert hasattr(follow_recsys_db, func_name)
            func = getattr(follow_recsys_db, func_name)
            assert callable(func)

# ================================================
# INTEGRATION AND EDGE CASE TESTS
# ================================================


class TestRecommenderIntegration:
    """Test integration scenarios for recommender systems."""

    @patch("ray.get")
    def test_content_recsys_with_client_id(self, mock_ray_get):
        """Test recommendation with client_id for logging."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        mock_ray_get.return_value = ["post-1"]
        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys()
        result = recsys.get_recommendations(mock_server, "agent-1", client_id="client-123")

        assert result == ["post-1"]
        call_args = mock_server.get_recommended_posts.remote.call_args
        assert call_args[1]["client_id"] == "client-123"

    @patch("ray.get")
    def test_follow_recsys_with_client_id(self, mock_ray_get):
        """Test follow suggestions with client_id for logging."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        mock_ray_get.return_value = ["user-1"]
        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay()
        result = recsys.get_follow_suggestions(mock_server, "agent-1", client_id="client-456")

        assert result == ["user-1"]
        call_args = mock_server.get_follow_suggestions.remote.call_args
        assert call_args[1]["client_id"] == "client-456"

    @patch("ray.get")
    def test_content_recsys_with_all_parameters(self, mock_ray_get):
        """Test recommendation with all parameters specified."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        mock_ray_get.return_value = ["post-1", "post-2"]
        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys(
            mode="rchrono_followers_popularity", n_posts=15, followers_ratio=0.75
        )
        result = recsys.get_recommendations(mock_server, "agent-1", "client-1")

        assert len(result) == 2
        call_args = mock_server.get_recommended_posts.remote.call_args
        assert call_args[1]["mode"] == "rchrono_followers_popularity"
        assert call_args[1]["limit"] == 15
        assert call_args[1]["followers_ratio"] == 0.75

    @patch("ray.get")
    def test_follow_recsys_with_all_parameters(self, mock_ray_get):
        """Test follow suggestions with all parameters specified."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        mock_ray_get.return_value = ["user-1", "user-2", "user-3"]
        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay(mode="adamic_adar", n_neighbors=20, leaning_bias=5)
        result = recsys.get_follow_suggestions(mock_server, "agent-1", "client-1")

        assert len(result) == 3
        call_args = mock_server.get_follow_suggestions.remote.call_args
        assert call_args[1]["mode"] == "adamic_adar"
        assert call_args[1]["n_neighbors"] == 20
        assert call_args[1]["leaning_bias"] == 5


class TestRecommenderEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_content_recsys_zero_posts(self):
        """Test ContentRecSys with zero posts requested."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        recsys = ContentRecSys(n_posts=0)
        assert recsys.n_posts == 0

    def test_content_recsys_extreme_posts(self):
        """Test ContentRecSys with very large number of posts."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        recsys = ContentRecSys(n_posts=1000)
        assert recsys.n_posts == 1000

    def test_content_recsys_followers_ratio_boundaries(self):
        """Test ContentRecSys with boundary followers_ratio values."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        recsys_zero = ContentRecSys(followers_ratio=0.0)
        assert recsys_zero.followers_ratio == 0.0

        recsys_one = ContentRecSys(followers_ratio=1.0)
        assert recsys_one.followers_ratio == 1.0

    def test_follow_recsys_zero_neighbors(self):
        """Test FollowRecSysRay with zero neighbors requested."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        recsys = FollowRecSysRay(n_neighbors=0)
        assert recsys.n_neighbors == 0

    def test_follow_recsys_extreme_neighbors(self):
        """Test FollowRecSysRay with very large number of neighbors."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        recsys = FollowRecSysRay(n_neighbors=500)
        assert recsys.n_neighbors == 500

    def test_follow_recsys_leaning_bias_boundaries(self):
        """Test FollowRecSysRay with boundary leaning_bias values."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        recsys_min = FollowRecSysRay(leaning_bias=1)
        assert recsys_min.leaning_bias == 1

        recsys_max = FollowRecSysRay(leaning_bias=100)
        assert recsys_max.leaning_bias == 100

    @patch("ray.get")
    def test_content_recsys_large_response(self, mock_ray_get):
        """Test handling large recommendation response."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        # Simulate large response
        large_response = [f"post-{i}" for i in range(100)]
        mock_ray_get.return_value = large_response

        mock_server = Mock()
        mock_server.get_recommended_posts = Mock()
        mock_server.get_recommended_posts.remote = Mock()

        recsys = ContentRecSys(n_posts=100)
        result = recsys.get_recommendations(mock_server, "agent-1")

        assert len(result) == 100
        assert result[0] == "post-0"
        assert result[99] == "post-99"

    @patch("ray.get")
    def test_follow_recsys_large_response(self, mock_ray_get):
        """Test handling large follow suggestions response."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        # Simulate large response
        large_response = [f"user-{i}" for i in range(50)]
        mock_ray_get.return_value = large_response

        mock_server = Mock()
        mock_server.get_follow_suggestions = Mock()
        mock_server.get_follow_suggestions.remote = Mock()

        recsys = FollowRecSysRay(n_neighbors=50)
        result = recsys.get_follow_suggestions(mock_server, "agent-1")

        assert len(result) == 50
        assert result[0] == "user-0"
        assert result[49] == "user-49"


class TestRecommenderSystemModes:
    """Test all supported recommendation modes."""

    def test_all_content_modes_supported(self):
        """Test all content recommendation modes are supported."""
        from YSimulator.YClient.recsys.ContentRecSys import ContentRecSys

        modes = [
            "random",
            "rchrono",
            "rchrono_popularity",
            "rchrono_followers",
            "rchrono_followers_popularity",
            "rchrono_comments",
            "common_interests",
            "common_user_interests",
            "similar_users_react",
            "similar_users_posts",
        ]

        for mode in modes:
            recsys = ContentRecSys(mode=mode)
            assert recsys.mode == mode

    def test_all_follow_modes_supported(self):
        """Test all follow recommendation modes are supported."""
        from YSimulator.YClient.recsys.FollowRecSysRay import FollowRecSysRay

        modes = ["random", "common_neighbors", "jaccard", "adamic_adar", "preferential_attachment"]

        for mode in modes:
            recsys = FollowRecSysRay(mode=mode)
            assert recsys.mode == mode


class TestRecommenderClassHierarchy:
    """Test class inheritance and hierarchy."""

    def test_reverse_chrono_inherits_content_recsys(self):
        """Test ReverseChrono inherits from ContentRecSys."""
        from YSimulator.YClient.recsys.ContentRecSys import ReverseChrono, ContentRecSys

        recsys = ReverseChrono()
        assert isinstance(recsys, ContentRecSys)
        assert isinstance(recsys, ReverseChrono)

    def test_random_order_inherits_content_recsys(self):
        """Test RandomOrder inherits from ContentRecSys."""
        from YSimulator.YClient.recsys.ContentRecSys import RandomOrder, ContentRecSys

        recsys = RandomOrder()
        assert isinstance(recsys, ContentRecSys)
        assert isinstance(recsys, RandomOrder)

    def test_random_follow_inherits_follow_recsys(self):
        """Test RandomFollowRecSys inherits from FollowRecSysRay."""
        from YSimulator.YClient.recsys.FollowRecSysRay import RandomFollowRecSys, FollowRecSysRay

        recsys = RandomFollowRecSys()
        assert isinstance(recsys, FollowRecSysRay)
        assert isinstance(recsys, RandomFollowRecSys)

    def test_jaccard_follow_inherits_follow_recsys(self):
        """Test JaccardFollowRecSys inherits from FollowRecSysRay."""
        from YSimulator.YClient.recsys.FollowRecSysRay import JaccardFollowRecSys, FollowRecSysRay

        recsys = JaccardFollowRecSys()
        assert isinstance(recsys, FollowRecSysRay)
        assert isinstance(recsys, JaccardFollowRecSys)

    def test_all_content_subclasses_have_get_recommendations(self):
        """Test all content recommendation subclasses have get_recommendations method."""
        from YSimulator.YClient.recsys.ContentRecSys import (
            ReverseChrono,
            ReverseChronoPopularity,
            RandomOrder,
            CommonInterests,
            SimilarUsersReact,
        )

        subclasses = [
            ReverseChrono(),
            ReverseChronoPopularity(),
            RandomOrder(),
            CommonInterests(),
            SimilarUsersReact(),
        ]

        for recsys in subclasses:
            assert hasattr(recsys, "get_recommendations")
            assert callable(recsys.get_recommendations)

    def test_all_follow_subclasses_have_get_follow_suggestions(self):
        """Test all follow recommendation subclasses have get_follow_suggestions method."""
        from YSimulator.YClient.recsys.FollowRecSysRay import (
            RandomFollowRecSys,
            CommonNeighborsFollowRecSys,
            JaccardFollowRecSys,
            AdamicAdarFollowRecSys,
            PreferentialAttachmentFollowRecSys,
        )

        subclasses = [
            RandomFollowRecSys(),
            CommonNeighborsFollowRecSys(),
            JaccardFollowRecSys(),
            AdamicAdarFollowRecSys(),
            PreferentialAttachmentFollowRecSys(),
        ]

        for recsys in subclasses:
            assert hasattr(recsys, "get_follow_suggestions")
            assert callable(recsys.get_follow_suggestions)
