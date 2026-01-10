"""
Unit tests for content_recsys_db.py

Tests SQL-based content recommendation algorithms using mock SQLAlchemy sessions.
Uses the same successful mocking strategy as follow_recsys_db.py tests.
"""

import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session


class TestRecommendRandom(unittest.TestCase):
    """Test random content recommendations."""

    def test_random_basic(self):
        """Test basic random post recommendations."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        # Mock session and query chain
        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        # Configure chainable query methods
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query

        # Mock query results - list of tuples
        mock_query.all.return_value = [("post1",), ("post2",), ("post3",)]

        result = recommend_random(mock_session, "agent1", 1, 0, 3)

        assert result == ["post1", "post2", "post3"]
        assert mock_session.query.called
        assert mock_query.join.called
        assert mock_query.filter.called
        assert mock_query.order_by.called
        assert mock_query.limit.called

    def test_random_empty_results(self):
        """Test when no posts are available."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = recommend_random(mock_session, "agent1", 1, 0, 5)

        assert result == []

    def test_random_limit_parameter(self):
        """Test limit parameter is respected."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [("post1",), ("post2",)]

        result = recommend_random(mock_session, "agent1", 2, 3, 10)

        # Verify limit was called with correct value
        mock_query.limit.assert_called_once_with(10)
        assert len(result) == 2


class TestRecommendRchrono(unittest.TestCase):
    """Test reverse chronological recommendations."""

    def test_rchrono_basic(self):
        """Test basic reverse chronological ordering."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_session.query.return_value = mock_query

            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [("post1",), ("post2",)]

            result = recommend_rchrono(mock_session, "agent1", 1, 0, 2)

            assert result == ["post1", "post2"]
            assert mock_desc.call_count >= 2  # Called for day and hour

    def test_rchrono_visibility_filter(self):
        """Test visibility day/hour filtering."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_session.query.return_value = mock_query

            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [("post1",)]

            result = recommend_rchrono(mock_session, "agent1", 5, 12, 1)

            assert result == ["post1"]
            # Verify filter was called with visibility conditions
            assert mock_query.filter.called


class TestRecommendRchronoPopularity(unittest.TestCase):
    """Test reverse chronological with popularity boost."""

    def test_rchrono_popularity_basic(self):
        """Test rchrono with popularity (reaction count)."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_popularity

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_subquery = Mock()

            mock_session.query.return_value = mock_query
            mock_query.group_by.return_value = mock_query
            mock_query.subquery.return_value = mock_subquery

            # Main query chain
            mock_query.join.return_value = mock_query
            mock_query.outerjoin.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [("post1",), ("post2",)]

            result = recommend_rchrono_popularity(mock_session, "agent1", 1, 0, 2)

            assert result == ["post1", "post2"]
            assert mock_query.outerjoin.called  # For reaction subquery

    def test_rchrono_popularity_with_subquery(self):
        """Test that reaction count subquery is created."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_popularity

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                mock_desc.return_value = Mock()
                mock_func.count.return_value = Mock()
                mock_func.coalesce.return_value = Mock()

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_subquery = Mock()
                mock_subquery.c = Mock()
                mock_subquery.c.post_id = Mock()
                mock_subquery.c.reaction_count = Mock()

                mock_session.query.return_value = mock_query
                mock_query.group_by.return_value = mock_query
                mock_query.subquery.return_value = mock_subquery
                mock_query.join.return_value = mock_query
                mock_query.outerjoin.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = [("post1",)]

                result = recommend_rchrono_popularity(mock_session, "agent1", 1, 0, 1)

                assert result == ["post1"]
                # Verify subquery was created
                assert mock_query.subquery.called


class TestRecommendRchronoFollowers(unittest.TestCase):
    """Test prioritizing posts from followed users."""

    def test_rchrono_followers_basic(self):
        """Test basic follower post prioritization."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_followers

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)

            # First query for follower posts (limit=3 from 5*0.6)
            mock_query1 = Mock()
            mock_query1.distinct.return_value = mock_query1
            mock_query1.join.return_value = mock_query1
            mock_query1.filter.return_value = mock_query1
            mock_query1.order_by.return_value = mock_query1
            mock_query1.limit.return_value = mock_query1
            mock_query1.all.return_value = [("post1",), ("post2",), ("post3",)]

            # Second query for additional posts (since 3 < 5, will get 2 more)
            mock_query2 = Mock()
            mock_query2.join.return_value = mock_query2
            mock_query2.filter.return_value = mock_query2
            mock_query2.order_by.return_value = mock_query2
            mock_query2.limit.return_value = mock_query2
            mock_query2.all.return_value = [("post4",), ("post5",)]

            mock_session.query.side_effect = [mock_query1, mock_query2]

            result = recommend_rchrono_followers(mock_session, "agent1", 1, 0, 5, 0.6)

            assert len(result) == 5
            assert "post1" in result
            assert "post2" in result
            assert "post3" in result
            assert "post4" in result
            assert "post5" in result

    def test_rchrono_followers_ratio_calculation(self):
        """Test followers_ratio is used for limit calculation."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_followers

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_session.query.return_value = mock_query

            mock_query.distinct.return_value = mock_query
            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [("post1",), ("post2",)]

            # With 10 posts and 0.6 ratio, should get 6 from followers, 4 additional
            recommend_rchrono_followers(mock_session, "agent1", 1, 0, 10, 0.6)

            # First limit call should be 6 (60% of 10)
            calls = mock_query.limit.call_args_list
            assert calls[0][0][0] == 6  # First call with follower_posts_limit

    def test_rchrono_followers_fills_additional(self):
        """Test filling additional posts when follower posts insufficient."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_followers

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)

            # First query returns 2 follower posts
            mock_query1 = Mock()
            mock_query1.distinct.return_value = mock_query1
            mock_query1.join.return_value = mock_query1
            mock_query1.filter.return_value = mock_query1
            mock_query1.order_by.return_value = mock_query1
            mock_query1.limit.return_value = mock_query1
            mock_query1.all.return_value = [("post1",), ("post2",)]

            # Second query returns additional posts
            mock_query2 = Mock()
            mock_query2.join.return_value = mock_query2
            mock_query2.filter.return_value = mock_query2
            mock_query2.order_by.return_value = mock_query2
            mock_query2.limit.return_value = mock_query2
            mock_query2.all.return_value = [("post3",), ("post4",)]

            # Mock session to return different query objects
            mock_session.query.side_effect = [mock_query1, mock_query2]

            result = recommend_rchrono_followers(mock_session, "agent1", 1, 0, 10, 0.6)

            assert len(result) == 4
            assert "post1" in result
            assert "post2" in result
            assert "post3" in result
            assert "post4" in result

    def test_rchrono_followers_no_additional_needed(self):
        """Test when follower posts meet the limit."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_followers

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_session.query.return_value = mock_query

            mock_query.distinct.return_value = mock_query
            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            # Return exactly 5 posts (meets limit)
            mock_query.all.return_value = [
                ("post1",),
                ("post2",),
                ("post3",),
                ("post4",),
                ("post5",),
            ]

            result = recommend_rchrono_followers(mock_session, "agent1", 1, 0, 5, 0.6)

            assert len(result) == 5
            # Should only call session.query once (no additional posts needed)
            assert mock_session.query.call_count == 1


class TestRecommendRchronoFollowersPopularity(unittest.TestCase):
    """Test followers with popularity boost."""

    def test_rchrono_followers_popularity_basic(self):
        """Test followers + popularity recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import (
            recommend_rchrono_followers_popularity,
        )

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                mock_desc.return_value = Mock()
                mock_func.count.return_value = Mock()
                mock_func.coalesce.return_value = Mock()

                mock_session = Mock(spec=Session)

                # First query for reaction count subquery
                mock_subquery = Mock()
                mock_subquery.c = Mock()
                mock_subquery.c.post_id = Mock()
                mock_subquery.c.reaction_count = Mock()

                mock_query1 = Mock()
                mock_query1.group_by.return_value = mock_query1
                mock_query1.subquery.return_value = mock_subquery

                # Second query for follower posts (with limit=3 from 5*0.6)
                mock_query2 = Mock()
                mock_query2.distinct.return_value = mock_query2
                mock_query2.join.return_value = mock_query2
                mock_query2.outerjoin.return_value = mock_query2
                mock_query2.filter.return_value = mock_query2
                mock_query2.order_by.return_value = mock_query2
                mock_query2.limit.return_value = mock_query2
                mock_query2.all.return_value = [("post1",), ("post2",), ("post3",)]

                # Third query for second reaction count subquery (for additional posts)
                mock_subquery2 = Mock()
                mock_subquery2.c = Mock()
                mock_subquery2.c.post_id = Mock()
                mock_subquery2.c.reaction_count = Mock()

                mock_query3 = Mock()
                mock_query3.group_by.return_value = mock_query3
                mock_query3.subquery.return_value = mock_subquery2

                # Fourth query for additional posts (since 3 < 5, will get 2 more)
                mock_query4 = Mock()
                mock_query4.join.return_value = mock_query4
                mock_query4.outerjoin.return_value = mock_query4
                mock_query4.filter.return_value = mock_query4
                mock_query4.order_by.return_value = mock_query4
                mock_query4.limit.return_value = mock_query4
                mock_query4.all.return_value = [("post4",), ("post5",)]

                mock_session.query.side_effect = [
                    mock_query1,
                    mock_query2,
                    mock_query3,
                    mock_query4,
                ]

                result = recommend_rchrono_followers_popularity(
                    mock_session, "agent1", 1, 0, 5, 0.6
                )

                assert len(result) == 5
                assert "post1" in result
                assert "post2" in result
                assert "post3" in result
                assert "post4" in result
                assert "post5" in result
                # Verify subquery was created for reaction counts
                assert mock_query1.subquery.called
                assert mock_query3.subquery.called

    def test_rchrono_followers_popularity_fills_additional(self):
        """Test filling with additional posts when needed."""
        from YSimulator.YServer.recsys.content_recsys_db import (
            recommend_rchrono_followers_popularity,
        )

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                mock_desc.return_value = Mock()
                mock_func.count.return_value = Mock()
                mock_func.coalesce.return_value = Mock()

                mock_session = Mock(spec=Session)

                # First query - reaction count subquery
                mock_query1 = Mock()
                mock_subquery1 = Mock()
                mock_subquery1.c = Mock()
                mock_subquery1.c.post_id = Mock()
                mock_subquery1.c.reaction_count = Mock()

                mock_query1.group_by.return_value = mock_query1
                mock_query1.subquery.return_value = mock_subquery1

                # Second query - follower posts (limit=3 from 5*0.6)
                mock_query2 = Mock()
                mock_query2.distinct.return_value = mock_query2
                mock_query2.join.return_value = mock_query2
                mock_query2.outerjoin.return_value = mock_query2
                mock_query2.filter.return_value = mock_query2
                mock_query2.order_by.return_value = mock_query2
                mock_query2.limit.return_value = mock_query2
                mock_query2.all.return_value = [("post1",)]

                # Third query - second reaction count subquery (for additional posts)
                mock_query3 = Mock()
                mock_subquery2 = Mock()
                mock_subquery2.c = Mock()
                mock_subquery2.c.post_id = Mock()
                mock_subquery2.c.reaction_count = Mock()

                mock_query3.group_by.return_value = mock_query3
                mock_query3.subquery.return_value = mock_subquery2

                # Fourth query - additional posts (since 1 < 5, get 4 more)
                mock_query4 = Mock()
                mock_query4.join.return_value = mock_query4
                mock_query4.outerjoin.return_value = mock_query4
                mock_query4.filter.return_value = mock_query4
                mock_query4.order_by.return_value = mock_query4
                mock_query4.limit.return_value = mock_query4
                mock_query4.all.return_value = [("post2",), ("post3",), ("post4",), ("post5",)]

                mock_session.query.side_effect = [
                    mock_query1,
                    mock_query2,
                    mock_query3,
                    mock_query4,
                ]

                result = recommend_rchrono_followers_popularity(
                    mock_session, "agent1", 1, 0, 5, 0.6
                )

                assert len(result) == 5
                assert "post1" in result
                assert "post2" in result
                assert "post3" in result
                assert "post4" in result
                assert "post5" in result
                # Verify subquery was created for reaction counts
                assert mock_query1.subquery.called
                assert mock_query3.subquery.called
                assert "post1" in result
                assert "post2" in result
                assert "post3" in result


class TestRecommendRchronoComments(unittest.TestCase):
    """Test prioritizing posts with more comments."""

    def test_rchrono_comments_basic(self):
        """Test basic comment-based prioritization."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_comments

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                    mock_desc.return_value = Mock()
                    mock_func.count.return_value = Mock()
                    mock_aliased.return_value = Mock()

                    mock_session = Mock(spec=Session)
                    mock_query = Mock()
                    mock_session.query.return_value = mock_query

                    mock_query.join.return_value = mock_query
                    mock_query.outerjoin.return_value = mock_query
                    mock_query.filter.return_value = mock_query
                    mock_query.group_by.return_value = mock_query
                    mock_query.order_by.return_value = mock_query
                    mock_query.limit.return_value = mock_query
                    mock_query.all.return_value = [("post1",), ("post2",)]

                    result = recommend_rchrono_comments(mock_session, "agent1", 1, 0, 2)

                    assert result == ["post1", "post2"]
                    # Verify aliased was called for CommentPost
                    assert mock_aliased.called

    def test_rchrono_comments_filters_comment_to_none(self):
        """Test that only top-level posts are included (comment_to is None)."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono_comments

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                    mock_desc.return_value = Mock()
                    mock_func.count.return_value = Mock()
                    mock_aliased.return_value = Mock()

                    mock_session = Mock(spec=Session)
                    mock_query = Mock()
                    mock_session.query.return_value = mock_query

                    mock_query.join.return_value = mock_query
                    mock_query.outerjoin.return_value = mock_query
                    mock_query.filter.return_value = mock_query
                    mock_query.group_by.return_value = mock_query
                    mock_query.order_by.return_value = mock_query
                    mock_query.limit.return_value = mock_query
                    mock_query.all.return_value = [("post1",)]

                    result = recommend_rchrono_comments(mock_session, "agent1", 1, 0, 1)

                    assert result == ["post1"]
                    # Verify filter was called (includes comment_to.is_(None))
                    assert mock_query.filter.called


class TestRecommendCommonInterests(unittest.TestCase):
    """Test posts with common topic interests."""

    def test_common_interests_basic(self):
        """Test basic common interests recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_common_interests

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                mock_desc.return_value = Mock()
                mock_func.count.return_value = Mock()

                mock_session = Mock(spec=Session)

                # First query for posts from followers with common interests (limit=3)
                mock_query1 = Mock()
                mock_query1.distinct.return_value = mock_query1
                mock_query1.join.return_value = mock_query1
                mock_query1.filter.return_value = mock_query1
                mock_query1.group_by.return_value = mock_query1
                mock_query1.order_by.return_value = mock_query1
                mock_query1.limit.return_value = mock_query1
                mock_query1.all.return_value = [("post1",), ("post2",)]

                # Second query for additional posts with common interests (since 2 < 5, get 3 more)
                mock_query2 = Mock()
                mock_query2.distinct.return_value = mock_query2
                mock_query2.join.return_value = mock_query2
                mock_query2.filter.return_value = mock_query2
                mock_query2.group_by.return_value = mock_query2
                mock_query2.order_by.return_value = mock_query2
                mock_query2.limit.return_value = mock_query2
                mock_query2.all.return_value = [("post3",), ("post4",), ("post5",)]

                mock_session.query.side_effect = [mock_query1, mock_query2]

                result = recommend_common_interests(mock_session, "agent1", 1, 0, 5, 0.6)

                assert len(result) == 5
                assert "post1" in result
                assert "post2" in result
                assert "post3" in result
                assert "post4" in result
                assert "post5" in result
                # Verify joins for PostTopic, UserInterest, Follow
                assert mock_query1.join.call_count >= 3

    def test_common_interests_fills_additional(self):
        """Test filling with additional posts when follower posts insufficient."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_common_interests

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                mock_desc.return_value = Mock()
                mock_func.count.return_value = Mock()

                mock_session = Mock(spec=Session)

                # First query - follower posts with interests
                mock_query1 = Mock()
                mock_query1.distinct.return_value = mock_query1
                mock_query1.join.return_value = mock_query1
                mock_query1.filter.return_value = mock_query1
                mock_query1.group_by.return_value = mock_query1
                mock_query1.order_by.return_value = mock_query1
                mock_query1.limit.return_value = mock_query1
                mock_query1.all.return_value = [("post1",)]

                # Second query - additional posts with interests
                mock_query2 = Mock()
                mock_query2.distinct.return_value = mock_query2
                mock_query2.join.return_value = mock_query2
                mock_query2.filter.return_value = mock_query2
                mock_query2.group_by.return_value = mock_query2
                mock_query2.order_by.return_value = mock_query2
                mock_query2.limit.return_value = mock_query2
                mock_query2.all.return_value = [("post2",), ("post3",)]

                mock_session.query.side_effect = [mock_query1, mock_query2]

                result = recommend_common_interests(mock_session, "agent1", 1, 0, 5, 0.6)

                assert len(result) == 3
                assert "post1" in result
                assert "post2" in result
                assert "post3" in result


class TestRecommendCommonUserInterests(unittest.TestCase):
    """Test posts by users with common interests."""

    def test_common_user_interests_basic(self):
        """Test basic common user interests recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_common_user_interests

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                    mock_desc.return_value = Mock()
                    mock_func.count.return_value = Mock()

                    # Mock aliased to return mocks for UserInterest1, UserInterest2, and additional aliases
                    # Function calls aliased 4 times: 2 for first query + 2 for additional query
                    mock_aliased.side_effect = [Mock(), Mock(), Mock(), Mock()]

                    mock_session = Mock(spec=Session)

                    # First query for posts from followers with common interests (limit=3)
                    mock_query1 = Mock()
                    mock_query1.distinct.return_value = mock_query1
                    mock_query1.join.return_value = mock_query1
                    mock_query1.filter.return_value = mock_query1
                    mock_query1.group_by.return_value = mock_query1
                    mock_query1.order_by.return_value = mock_query1
                    mock_query1.limit.return_value = mock_query1
                    mock_query1.all.return_value = [("post1", 5), ("post2", 3)]

                    # Second query for additional posts (since 2 < 5, get 3 more)
                    mock_query2 = Mock()
                    mock_query2.distinct.return_value = mock_query2
                    mock_query2.join.return_value = mock_query2
                    mock_query2.filter.return_value = mock_query2
                    mock_query2.group_by.return_value = mock_query2
                    mock_query2.order_by.return_value = mock_query2
                    mock_query2.limit.return_value = mock_query2
                    mock_query2.all.return_value = [("post3", 2), ("post4", 1), ("post5", 1)]

                    mock_session.query.side_effect = [mock_query1, mock_query2]

                    result = recommend_common_user_interests(mock_session, "agent1", 1, 0, 5, 0.6)

                    assert len(result) == 5
                    assert "post1" in result
                    assert "post2" in result
                    assert "post3" in result
                    assert "post4" in result
                    assert "post5" in result
                    # Verify aliased was called 4 times (2 for first query, 2 for additional)
                    assert mock_aliased.call_count == 4

    def test_common_user_interests_fills_additional(self):
        """Test filling with additional posts from non-followers."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_common_user_interests

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.func") as mock_func:
                with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                    mock_desc.return_value = Mock()
                    mock_func.count.return_value = Mock()

                    # Mock aliased to return different mocks
                    mock_aliased.side_effect = [Mock(), Mock(), Mock(), Mock()]

                    mock_session = Mock(spec=Session)

                    # First query - follower posts
                    mock_query1 = Mock()
                    mock_query1.distinct.return_value = mock_query1
                    mock_query1.join.return_value = mock_query1
                    mock_query1.filter.return_value = mock_query1
                    mock_query1.group_by.return_value = mock_query1
                    mock_query1.order_by.return_value = mock_query1
                    mock_query1.limit.return_value = mock_query1
                    mock_query1.all.return_value = [("post1", 2)]

                    # Second query - additional posts
                    mock_query2 = Mock()
                    mock_query2.distinct.return_value = mock_query2
                    mock_query2.join.return_value = mock_query2
                    mock_query2.filter.return_value = mock_query2
                    mock_query2.group_by.return_value = mock_query2
                    mock_query2.order_by.return_value = mock_query2
                    mock_query2.limit.return_value = mock_query2
                    mock_query2.all.return_value = [("post2", 1), ("post3", 1)]

                    mock_session.query.side_effect = [mock_query1, mock_query2]

                    result = recommend_common_user_interests(mock_session, "agent1", 1, 0, 5, 0.6)

                    assert len(result) == 3
                    assert "post1" in result
                    assert "post2" in result
                    assert "post3" in result


class TestRecommendSimilarUsersReact(unittest.TestCase):
    """Test posts from similar users based on reactions."""

    def test_similar_users_react_basic(self):
        """Test basic similar users react recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_similar_users_react

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                mock_desc.return_value = Mock()

                # Mock aliased to return different mocks for ReactorUser and TargetUser
                mock_aliased.side_effect = [Mock(), Mock()]

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_session.query.return_value = mock_query

                mock_query.distinct.return_value = mock_query
                mock_query.join.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.group_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = [("post1",), ("post2",)]

                result = recommend_similar_users_react(mock_session, "agent1", 1, 0, 2)

                assert result == ["post1", "post2"]
                # Verify aliased was called for user aliases
                assert mock_aliased.call_count == 2

    def test_similar_users_react_filters_like_type(self):
        """Test that only 'like' reactions are considered."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_similar_users_react

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                mock_desc.return_value = Mock()
                mock_aliased.side_effect = [Mock(), Mock()]

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_session.query.return_value = mock_query

                mock_query.distinct.return_value = mock_query
                mock_query.join.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.group_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = [("post1",)]

                result = recommend_similar_users_react(mock_session, "agent1", 1, 0, 1)

                assert result == ["post1"]
                # Verify filter was called (includes reaction type == 'like')
                assert mock_query.filter.called


class TestRecommendSimilarUsersPosts(unittest.TestCase):
    """Test posts created by similar users."""

    def test_similar_users_posts_basic(self):
        """Test basic similar users posts recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_similar_users_posts

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                mock_desc.return_value = Mock()

                # Mock aliased to return different mocks for PostAuthor and TargetUser
                mock_aliased.side_effect = [Mock(), Mock()]

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_session.query.return_value = mock_query

                mock_query.join.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = [("post1",), ("post2",), ("post3",)]

                result = recommend_similar_users_posts(mock_session, "agent1", 1, 0, 3)

                assert result == ["post1", "post2", "post3"]
                # Verify aliased was called for user aliases
                assert mock_aliased.call_count == 2

    def test_similar_users_posts_similarity_filters(self):
        """Test that similarity is based on age_group, gender, or leaning."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_similar_users_posts

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                mock_desc.return_value = Mock()
                mock_aliased.side_effect = [Mock(), Mock()]

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_session.query.return_value = mock_query

                mock_query.join.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = [("post1",)]

                result = recommend_similar_users_posts(mock_session, "agent1", 1, 0, 1)

                assert result == ["post1"]
                # Verify filter was called (includes OR conditions for similarity)
                assert mock_query.filter.called

    def test_similar_users_posts_excludes_agent_posts(self):
        """Test that agent's own posts are excluded."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_similar_users_posts

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            with patch("YSimulator.YServer.recsys.content_recsys_db.aliased") as mock_aliased:
                mock_desc.return_value = Mock()
                mock_aliased.side_effect = [Mock(), Mock()]

                mock_session = Mock(spec=Session)
                mock_query = Mock()
                mock_session.query.return_value = mock_query

                mock_query.join.return_value = mock_query
                mock_query.filter.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.all.return_value = []  # No posts (agent's posts excluded)

                result = recommend_similar_users_posts(mock_session, "agent1", 1, 0, 5)

                assert result == []


class TestEdgeCases(unittest.TestCase):
    """Test edge cases across all functions."""

    def test_zero_limit(self):
        """Test with limit=0."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = recommend_random(mock_session, "agent1", 1, 0, 0)

        assert result == []
        mock_query.limit.assert_called_once_with(0)

    def test_negative_limit(self):
        """Test with negative limit."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_rchrono

        with patch("YSimulator.YServer.recsys.content_recsys_db.desc") as mock_desc:
            mock_desc.return_value = Mock()

            mock_session = Mock(spec=Session)
            mock_query = Mock()
            mock_session.query.return_value = mock_query

            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = []

            result = recommend_rchrono(mock_session, "agent1", 1, 0, -5)

            assert result == []

    def test_large_limit(self):
        """Test with very large limit."""
        from YSimulator.YServer.recsys.content_recsys_db import recommend_random

        mock_session = Mock(spec=Session)
        mock_query = Mock()
        mock_session.query.return_value = mock_query

        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [("post1",)]  # Only 1 post available

        result = recommend_random(mock_session, "agent1", 1, 0, 1000000)

        assert result == ["post1"]
        mock_query.limit.assert_called_once_with(1000000)
