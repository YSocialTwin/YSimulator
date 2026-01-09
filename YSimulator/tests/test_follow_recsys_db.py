"""
Unit tests for follow_recsys_db.py

Tests SQL-based follow recommendation algorithms using mock SQLAlchemy sessions.
Uses the same successful mocking strategy as content_recsys_redis.py tests.
"""

from unittest.mock import Mock

from sqlalchemy.orm import Session


class TestRecommendRandomFollows:
    """Test random follow recommendations."""

    def test_random_follows_basic(self):
        """Test basic random follow recommendations."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        # Mock session and query
        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Mock User_mgmt objects (excluding user1 and user2 which are already following)
        mock_users = [Mock(id=f"user{i}") for i in range(3, 7)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_random_follows(mock_session, "agent1", {"user1", "user2"}, 3)

        assert isinstance(result, list)
        assert len(result) <= 3
        # All results should be from mock_users (user3-user6)
        for user_id in result:
            assert user_id in ["user3", "user4", "user5", "user6"]

    def test_random_follows_no_following(self):
        """Test when agent follows no one."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_random_follows(mock_session, "agent1", set(), 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_random_follows_no_candidates(self):
        """Test when no candidates are available."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = recommend_random_follows(mock_session, "agent1", {"user1"}, 5)

        assert result == []

    def test_random_follows_exception_handling(self):
        """Test exception handling returns empty list."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        mock_session = Mock(spec=Session)
        mock_session.query.side_effect = Exception("Database error")

        result = recommend_random_follows(mock_session, "agent1", set(), 5)

        assert result == []


class TestRecommendCommonNeighbors:
    """Test common neighbors (friend-of-friend) recommendations."""

    def test_common_neighbors_basic(self):
        """Test basic common neighbors recommendations."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_common_neighbors

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Mock friend-of-friend query results
        mock_query.select_from.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [("user3", 2), ("user4", 1)]

        result = recommend_common_neighbors(mock_session, "agent1", {"user1", "user2"}, 2)

        assert isinstance(result, list)
        assert len(result) <= 2
        assert "user3" in result
        assert "user4" in result

    def test_common_neighbors_no_following_fallback(self):
        """Test fallback to random when no following."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_common_neighbors

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Setup for random fallback
        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_common_neighbors(mock_session, "agent1", set(), 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_common_neighbors_fill_with_random(self):
        """Test filling incomplete results with random users."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_common_neighbors

        mock_session = Mock(spec=Session)

        # First query chain - FOF query returns only 1 result
        mock_fof_query = Mock()
        mock_fof_query.select_from.return_value = mock_fof_query
        mock_fof_query.join.return_value = mock_fof_query
        mock_fof_query.filter.return_value = mock_fof_query
        mock_fof_query.group_by.return_value = mock_fof_query
        mock_fof_query.order_by.return_value = mock_fof_query
        mock_fof_query.limit.return_value = mock_fof_query
        mock_fof_query.all.return_value = [("user3", 2)]

        # Second query chain - random candidates
        mock_random_query = Mock()
        mock_random_query.filter.return_value = mock_random_query
        mock_random_query.limit.return_value = mock_random_query
        mock_random_query.all.return_value = [Mock(id="user4"), Mock(id="user5")]

        # Setup query to return different mocks for different calls
        query_calls = [mock_fof_query, mock_random_query]
        mock_session.query.side_effect = query_calls

        result = recommend_common_neighbors(mock_session, "agent1", {"user1", "user2"}, 3)

        assert isinstance(result, list)
        assert len(result) <= 3
        assert "user3" in result

    def test_common_neighbors_exception_fallback(self):
        """Test exception handling falls back to random."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_common_neighbors

        mock_session = Mock(spec=Session)

        # First call raises exception
        # Second call (fallback to random) succeeds
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [Mock(id="user1")]

        def side_effect(*args):
            if side_effect.call_count == 1:
                side_effect.call_count += 1
                raise Exception("Query error")
            return mock_query

        side_effect.call_count = 1
        mock_session.query.side_effect = side_effect

        result = recommend_common_neighbors(mock_session, "agent1", {"user2"}, 2)

        assert isinstance(result, list)


class TestRecommendJaccard:
    """Test Jaccard similarity recommendations."""

    def test_jaccard_basic(self):
        """Test basic Jaccard similarity recommendations."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_jaccard

        mock_session = Mock(spec=Session)

        # Setup complex query chain for Jaccard calculation
        mock_query = Mock()
        mock_query.select_from.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.subquery.return_value = mock_query

        # Final query results
        mock_query.all.return_value = [("user3", 0.5), ("user4", 0.3)]

        mock_session.query.return_value = mock_query

        result = recommend_jaccard(mock_session, "agent1", {"user1", "user2"}, 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_jaccard_no_following_fallback(self):
        """Test fallback to random when no following."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_jaccard

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Setup for random fallback
        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_jaccard(mock_session, "agent1", set(), 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_jaccard_fill_with_random(self):
        """Test filling incomplete results with random users."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_jaccard

        mock_session = Mock(spec=Session)

        # First query chain returns partial results
        mock_jaccard_query = Mock()
        mock_jaccard_query.select_from.return_value = mock_jaccard_query
        mock_jaccard_query.join.return_value = mock_jaccard_query
        mock_jaccard_query.outerjoin.return_value = mock_jaccard_query
        mock_jaccard_query.filter.return_value = mock_jaccard_query
        mock_jaccard_query.group_by.return_value = mock_jaccard_query
        mock_jaccard_query.order_by.return_value = mock_jaccard_query
        mock_jaccard_query.limit.return_value = mock_jaccard_query
        mock_jaccard_query.subquery.return_value = mock_jaccard_query
        mock_jaccard_query.all.return_value = [("user3", 0.5)]

        # Second query for random fill
        mock_random_query = Mock()
        mock_random_query.filter.return_value = mock_random_query
        mock_random_query.limit.return_value = mock_random_query
        mock_random_query.all.return_value = [Mock(id="user4"), Mock(id="user5")]

        query_calls = [mock_jaccard_query, mock_random_query]
        mock_session.query.side_effect = query_calls

        result = recommend_jaccard(mock_session, "agent1", {"user1", "user2"}, 3)

        assert isinstance(result, list)
        assert len(result) <= 3

    def test_jaccard_exception_fallback(self):
        """Test exception handling falls back to random."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_jaccard

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [Mock(id="user1")]

        def side_effect(*args):
            if side_effect.call_count == 1:
                side_effect.call_count += 1
                raise Exception("Query error")
            return mock_query

        side_effect.call_count = 1
        mock_session.query.side_effect = side_effect

        result = recommend_jaccard(mock_session, "agent1", {"user2"}, 2)

        assert isinstance(result, list)


class TestRecommendAdamicAdar:
    """Test Adamic/Adar index recommendations."""

    def test_adamic_adar_basic(self):
        """Test basic Adamic/Adar recommendations."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_adamic_adar

        mock_session = Mock(spec=Session)

        # First query - common neighbors
        mock_cn_query = Mock()
        mock_cn_query.select_from.return_value = mock_cn_query
        mock_cn_query.join.return_value = mock_cn_query
        mock_cn_query.filter.return_value = mock_cn_query
        # Return tuples: (candidate_id, common_neighbor_id)
        mock_cn_query.all.return_value = [
            ("user3", "user1"),
            ("user3", "user2"),
            ("user4", "user1"),
        ]

        # Second query - degrees of common neighbors
        mock_degree_query = Mock()
        mock_degree_query.filter.return_value = mock_degree_query
        mock_degree_query.group_by.return_value = mock_degree_query
        # Return tuples: (neighbor_id, degree)
        mock_degree_query.all.return_value = [
            ("user1", 10),
            ("user2", 5),
        ]

        query_calls = [mock_cn_query, mock_degree_query]
        mock_session.query.side_effect = query_calls

        result = recommend_adamic_adar(mock_session, "agent1", {"user1", "user2"}, 2)

        assert isinstance(result, list)
        assert len(result) <= 2
        # user3 should have higher score (2 common neighbors)
        if len(result) > 0:
            assert "user3" in result or "user4" in result

    def test_adamic_adar_no_following_fallback(self):
        """Test fallback to random when no following."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_adamic_adar

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Setup for random fallback
        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_adamic_adar(mock_session, "agent1", set(), 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_adamic_adar_no_common_neighbors_fallback(self):
        """Test fallback to random when no common neighbors found."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_adamic_adar

        mock_session = Mock(spec=Session)

        # First query returns no common neighbors
        mock_cn_query = Mock()
        mock_cn_query.select_from.return_value = mock_cn_query
        mock_cn_query.join.return_value = mock_cn_query
        mock_cn_query.filter.return_value = mock_cn_query
        mock_cn_query.all.return_value = []

        # Second query for random fallback
        mock_random_query = Mock()
        mock_random_query.filter.return_value = mock_random_query
        mock_random_query.all.return_value = [Mock(id="user3"), Mock(id="user4")]

        query_calls = [mock_cn_query, mock_random_query]
        mock_session.query.side_effect = query_calls

        result = recommend_adamic_adar(mock_session, "agent1", {"user1", "user2"}, 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_adamic_adar_fill_with_random(self):
        """Test filling incomplete results with random users."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_adamic_adar

        mock_session = Mock(spec=Session)

        # First query - limited common neighbors
        mock_cn_query = Mock()
        mock_cn_query.select_from.return_value = mock_cn_query
        mock_cn_query.join.return_value = mock_cn_query
        mock_cn_query.filter.return_value = mock_cn_query
        mock_cn_query.all.return_value = [("user3", "user1")]

        # Second query - degrees
        mock_degree_query = Mock()
        mock_degree_query.filter.return_value = mock_degree_query
        mock_degree_query.group_by.return_value = mock_degree_query
        mock_degree_query.all.return_value = [("user1", 10)]

        # Third query - random fill
        mock_random_query = Mock()
        mock_random_query.filter.return_value = mock_random_query
        mock_random_query.limit.return_value = mock_random_query
        mock_random_query.all.return_value = [Mock(id="user4"), Mock(id="user5")]

        query_calls = [mock_cn_query, mock_degree_query, mock_random_query]
        mock_session.query.side_effect = query_calls

        result = recommend_adamic_adar(mock_session, "agent1", {"user1", "user2"}, 3)

        assert isinstance(result, list)
        assert len(result) <= 3
        assert "user3" in result

    def test_adamic_adar_exception_fallback(self):
        """Test exception handling falls back to random."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_adamic_adar

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [Mock(id="user1")]

        def side_effect(*args):
            if side_effect.call_count == 1:
                side_effect.call_count += 1
                raise Exception("Query error")
            return mock_query

        side_effect.call_count = 1
        mock_session.query.side_effect = side_effect

        result = recommend_adamic_adar(mock_session, "agent1", {"user2"}, 2)

        assert isinstance(result, list)


class TestRecommendPreferentialAttachment:
    """Test preferential attachment (popularity-based) recommendations."""

    def test_preferential_attachment_basic(self):
        """Test basic preferential attachment recommendations."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_preferential_attachment

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Mock popular users query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        # Return tuples: (user_id, follower_count)
        mock_query.all.return_value = [("user3", 100), ("user4", 50)]

        result = recommend_preferential_attachment(mock_session, "agent1", {"user1", "user2"}, 2)

        assert isinstance(result, list)
        assert len(result) <= 2
        assert "user3" in result
        assert "user4" in result

    def test_preferential_attachment_no_following(self):
        """Test with no existing following."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_preferential_attachment

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [("user1", 100), ("user2", 50)]

        result = recommend_preferential_attachment(mock_session, "agent1", set(), 2)

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_preferential_attachment_fill_with_random(self):
        """Test filling incomplete results with random users."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_preferential_attachment

        mock_session = Mock(spec=Session)

        # First query returns only 1 popular user
        mock_popular_query = Mock()
        mock_popular_query.filter.return_value = mock_popular_query
        mock_popular_query.group_by.return_value = mock_popular_query
        mock_popular_query.order_by.return_value = mock_popular_query
        mock_popular_query.limit.return_value = mock_popular_query
        mock_popular_query.all.return_value = [("user3", 100)]

        # Second query for random fill
        mock_random_query = Mock()
        mock_random_query.filter.return_value = mock_random_query
        mock_random_query.limit.return_value = mock_random_query
        mock_random_query.all.return_value = [Mock(id="user4"), Mock(id="user5")]

        query_calls = [mock_popular_query, mock_random_query]
        mock_session.query.side_effect = query_calls

        result = recommend_preferential_attachment(mock_session, "agent1", {"user1", "user2"}, 3)

        assert isinstance(result, list)
        assert len(result) <= 3
        assert "user3" in result

    def test_preferential_attachment_exception_fallback(self):
        """Test exception handling falls back to random."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_preferential_attachment

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [Mock(id="user1")]

        def side_effect(*args):
            if side_effect.call_count == 1:
                side_effect.call_count += 1
                raise Exception("Query error")
            return mock_query

        side_effect.call_count = 1
        mock_session.query.side_effect = side_effect

        result = recommend_preferential_attachment(mock_session, "agent1", {"user2"}, 2)

        assert isinstance(result, list)


class TestApplyLeaningBias:
    """Test political leaning bias application."""

    def test_leaning_bias_zero_bias_no_change(self):
        """Test that bias=1 or less returns suggestions unchanged."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)
        suggestions = ["user1", "user2", "user3"]

        result = apply_leaning_bias(
            mock_session, "agent1", suggestions, leaning_bias=1, n_neighbors=3
        )

        assert result == suggestions[:3]

    def test_leaning_bias_empty_suggestions(self):
        """Test with empty suggestions."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)

        result = apply_leaning_bias(mock_session, "agent1", [], leaning_bias=5, n_neighbors=3)

        assert result == []

    def test_leaning_bias_matching_leaning(self):
        """Test bias toward users with matching political leaning."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)

        # Mock agent query
        mock_agent = Mock(id="agent1", leaning="liberal")
        mock_agent_query = Mock()
        mock_agent_query.filter.return_value = mock_agent_query
        mock_agent_query.first.return_value = mock_agent

        # Mock user leanings query
        mock_user1 = Mock(id="user1", leaning="liberal")
        mock_user2 = Mock(id="user2", leaning="conservative")
        mock_user3 = Mock(id="user3", leaning="liberal")

        mock_leaning_query = Mock()
        mock_leaning_query.filter.return_value = mock_leaning_query
        mock_leaning_query.all.return_value = [mock_user1, mock_user2, mock_user3]

        query_calls = [mock_agent_query, mock_leaning_query]
        mock_session.query.side_effect = query_calls

        suggestions = ["user1", "user2", "user3"]
        result = apply_leaning_bias(
            mock_session, "agent1", suggestions, leaning_bias=10, n_neighbors=3
        )

        assert isinstance(result, list)
        assert len(result) <= 3
        # Due to weighted random, liberal users should be more likely

    def test_leaning_bias_no_agent_leaning(self):
        """Test when agent has no leaning data."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)

        # Mock agent without leaning
        mock_agent = Mock(id="agent1", leaning=None)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_agent

        mock_session.query.return_value = mock_query

        suggestions = ["user1", "user2", "user3"]
        result = apply_leaning_bias(
            mock_session, "agent1", suggestions, leaning_bias=5, n_neighbors=3
        )

        assert result == suggestions[:3]

    def test_leaning_bias_agent_not_found(self):
        """Test when agent is not found in database."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_session.query.return_value = mock_query

        suggestions = ["user1", "user2", "user3"]
        result = apply_leaning_bias(
            mock_session, "agent1", suggestions, leaning_bias=5, n_neighbors=3
        )

        assert result == suggestions[:3]

    def test_leaning_bias_exception_handling(self):
        """Test exception handling returns suggestions unchanged."""
        from YSimulator.YServer.recsys.follow_recsys_db import apply_leaning_bias

        mock_session = Mock(spec=Session)
        mock_session.query.side_effect = Exception("Database error")

        suggestions = ["user1", "user2", "user3"]
        result = apply_leaning_bias(
            mock_session, "agent1", suggestions, leaning_bias=5, n_neighbors=3
        )

        assert result == suggestions[:3]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_n_neighbors(self):
        """Test with negative n_neighbors."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_random_follows(mock_session, "agent1", set(), -5)

        # Python list slicing with negative numbers should work
        assert isinstance(result, list)

    def test_large_n_neighbors(self):
        """Test with very large n_neighbors."""
        from YSimulator.YServer.recsys.follow_recsys_db import recommend_random_follows

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users

        result = recommend_random_follows(mock_session, "agent1", set(), 1000)

        assert isinstance(result, list)
        assert len(result) <= 3  # Can't return more than available

    def test_empty_following_ids(self):
        """Test all algorithms with empty following_ids set."""
        from YSimulator.YServer.recsys.follow_recsys_db import (
            recommend_adamic_adar,
            recommend_common_neighbors,
            recommend_jaccard,
            recommend_preferential_attachment,
            recommend_random_follows,
        )

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_users = [Mock(id=f"user{i}") for i in range(1, 4)]
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_users
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query

        # Test each algorithm
        result1 = recommend_random_follows(mock_session, "agent1", set(), 2)
        assert isinstance(result1, list)

        # These should fallback to random
        result2 = recommend_common_neighbors(mock_session, "agent1", set(), 2)
        assert isinstance(result2, list)

        result3 = recommend_jaccard(mock_session, "agent1", set(), 2)
        assert isinstance(result3, list)

        result4 = recommend_adamic_adar(mock_session, "agent1", set(), 2)
        assert isinstance(result4, list)

        # Preferential attachment should work
        mock_query.all.return_value = [("user1", 10), ("user2", 5)]
        result5 = recommend_preferential_attachment(mock_session, "agent1", set(), 2)
        assert isinstance(result5, list)
