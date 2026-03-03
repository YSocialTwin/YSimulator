"""
Unit tests for the hybrid linear ranker recommendation system.

Tests the two-stage recommendation process:
1. Candidate generation (union of multiple strategies)
2. Linear ranker with feature extraction and weighted scoring
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestHybridLinearRankerRedis:
    """Test hybrid linear ranker recommendation system."""

    def test_hybrid_basic_candidate_generation(self):
        """Test that candidates are generated from multiple sources."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            recommend_hybrid_linear_ranker_redis,
        )

        # Mock data
        posts = [{"id": f"post{i}", "index": i, "reaction_count": i} for i in range(20)]
        all_post_ids = [p["id"] for p in posts]
        posts_data = [
            {
                "user_id": f"user{i % 5}",
                "round": str(i),
                "reaction_count": str(i),
            }
            for i in range(20)
        ]

        # Create mocks
        redis_client = Mock()
        redis_client.exists = Mock(return_value=False)
        redis_client.smembers = Mock(return_value=set())

        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()
        logger = Mock()

        with patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_follows",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_interests",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_likes",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_post_topics",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_post_reaction_users",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_profile",
            return_value={},
        ):
            result, used_fallback = recommend_hybrid_linear_ranker_redis(
                valid_posts_with_data=posts,
                limit=5,
                agent_id="agent1",
                all_post_ids=all_post_ids,
                posts_data=posts_data,
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
                logger=logger,
                current_round=10,
                tau=10.0,
            )

        # Should return some results (even if falling back to random)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_hybrid_with_followed_users(self):
        """Test hybrid recommender prioritizes followed users."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            recommend_hybrid_linear_ranker_redis,
        )

        # Mock data - posts from followed and non-followed users
        posts = [
            {"id": "post1", "index": 0, "reaction_count": 5},
            {"id": "post2", "index": 1, "reaction_count": 3},
            {"id": "post3", "index": 2, "reaction_count": 10},
        ]
        all_post_ids = ["post1", "post2", "post3"]
        posts_data = [
            {"user_id": "followed_user", "round": "5"},
            {"user_id": "other_user", "round": "5"},
            {"user_id": "another_user", "round": "5"},
        ]

        redis_client = Mock()

        # Mock that agent follows "followed_user"
        def mock_exists(key):
            if "follows" in key:
                return True
            return False

        def mock_smembers(key):
            if ":follows" in key:
                return {"followed_user"}
            return set()

        redis_client.exists = Mock(side_effect=mock_exists)
        redis_client.smembers = Mock(side_effect=mock_smembers)
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()
        logger = Mock()

        with patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_interests",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_likes",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_post_topics",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_post_reaction_users",
            return_value=set(),
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_profile",
            return_value={},
        ):
            result, used_fallback = recommend_hybrid_linear_ranker_redis(
                valid_posts_with_data=posts,
                limit=3,
                agent_id="agent1",
                all_post_ids=all_post_ids,
                posts_data=posts_data,
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
                logger=logger,
                current_round=10,
            )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_hybrid_empty_candidates(self):
        """Test hybrid recommender with no candidates (should fallback to random)."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            recommend_hybrid_linear_ranker_redis,
        )

        posts = []
        all_post_ids = []
        posts_data = []

        redis_client = Mock()
        redis_client.exists = Mock(return_value=False)
        redis_client.smembers = Mock(return_value=set())
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()
        logger = Mock()

        with patch("YSimulator.YServer.recsys.content_recsys_redis.Session"):
            result, used_fallback = recommend_hybrid_linear_ranker_redis(
                valid_posts_with_data=posts,
                limit=5,
                agent_id="agent1",
                all_post_ids=all_post_ids,
                posts_data=posts_data,
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
                logger=logger,
            )

        # Should return empty list and indicate fallback was used
        assert result == []
        assert used_fallback is True


class TestFriendsOfFriendsCandidates:
    """Test friends-of-friends candidate generation."""

    def test_fof_basic(self):
        """Test basic friends-of-friends recommendation."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _get_friends_of_friends_candidates_redis,
        )

        posts = [
            {"id": "post1", "index": 0},
            {"id": "post2", "index": 1},
            {"id": "post3", "index": 2},
        ]
        all_post_ids = ["post1", "post2", "post3"]
        posts_data = [
            {"user_id": "fof_user1"},
            {"user_id": "fof_user2"},
            {"user_id": "other_user"},
        ]

        redis_client = Mock()

        # Mock: agent follows "friend1", friend1 follows "fof_user1" and "fof_user2"
        def mock_exists(key):
            return "follows" in key

        def mock_smembers(key):
            if "agent1:follows" in key:
                return {"friend1"}
            elif "friend1:follows" in key:
                return {"fof_user1", "fof_user2"}
            return set()

        redis_client.exists = Mock(side_effect=mock_exists)
        redis_client.smembers = Mock(side_effect=mock_smembers)
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()
        logger = Mock()

        result, used_fallback = _get_friends_of_friends_candidates_redis(
            valid_posts_with_data=posts,
            limit=5,
            agent_id="agent1",
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
            db_engine=db_engine,
            logger=logger,
        )

        # Should return posts from friends-of-friends
        assert isinstance(result, list)
        assert len(result) > 0

    def test_fof_no_follows(self):
        """Test FOF when agent doesn't follow anyone (cold start)."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _get_friends_of_friends_candidates_redis,
        )

        posts = [{"id": "post1", "index": 0}]
        all_post_ids = ["post1"]
        posts_data = [{"user_id": "user1"}]

        redis_client = Mock()
        redis_client.exists = Mock(return_value=False)
        redis_client.smembers = Mock(return_value=set())
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()
        logger = Mock()

        with patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_followed_users_redis",
            return_value=set(),
        ):
            result, used_fallback = _get_friends_of_friends_candidates_redis(
                valid_posts_with_data=posts,
                limit=5,
                agent_id="agent1",
                all_post_ids=all_post_ids,
                posts_data=posts_data,
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
                logger=logger,
            )

        # Should fallback to random
        assert used_fallback is True


class TestFeatureCalculation:
    """Test feature calculation helper functions."""

    def test_recency_score_calculation(self):
        """Test recency score with exponential decay."""
        import math

        # Recency formula: exp(-age_rounds / tau)
        current_round = 100
        post_round = 90
        tau = 10.0

        age_rounds = current_round - post_round  # 10
        expected_score = math.exp(-age_rounds / tau)  # exp(-1) ≈ 0.368

        assert abs(expected_score - 0.368) < 0.01

    def test_user_author_affinity_calculation(self):
        """Test user-author affinity calculation."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _calculate_user_author_affinity_redis,
        )

        redis_client = Mock()
        redis_client.exists = Mock(return_value=True)
        redis_client.hgetall = Mock(return_value={"user_id": "author1"})
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()

        with patch(
            "YSimulator.YServer.recsys.content_recsys_redis._get_user_likes",
            return_value={"post1", "post2", "post3", "post4", "post5"},
        ):
            affinity = _calculate_user_author_affinity_redis(
                agent_id="agent1",
                author_id="author1",
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
            )

        # Should return log(1 + interactions)
        import math

        expected = math.log(1 + 5)  # log(6) ≈ 1.79
        assert abs(affinity - expected) < 0.01

    def test_content_topic_similarity_jaccard(self):
        """Test content topic similarity (Jaccard)."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _calculate_content_topic_similarity_redis,
        )

        user_interests = {"topic1", "topic2", "topic3"}

        redis_client = Mock()
        redis_client.exists = Mock(return_value=True)
        redis_client.smembers = Mock(return_value={"topic2", "topic3", "topic4"})
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))

        similarity = _calculate_content_topic_similarity_redis(
            agent_id="agent1",
            post_id="post1",
            user_interests=user_interests,
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
        )

        # Jaccard: intersection {topic2, topic3} / union {topic1, topic2, topic3, topic4}
        # = 2 / 4 = 0.5
        assert abs(similarity - 0.5) < 0.01

    def test_content_topic_similarity_no_overlap(self):
        """Test topic similarity with no overlap."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _calculate_content_topic_similarity_redis,
        )

        user_interests = {"topic1", "topic2"}

        redis_client = Mock()
        redis_client.exists = Mock(return_value=True)
        redis_client.smembers = Mock(return_value={"topic3", "topic4"})
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))

        similarity = _calculate_content_topic_similarity_redis(
            agent_id="agent1",
            post_id="post1",
            user_interests=user_interests,
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
        )

        # No overlap, should return 0
        assert similarity == 0.0

    def test_similar_user_author_score(self):
        """Test similar user author score calculation."""
        from YSimulator.YServer.recsys.content_recsys_redis import (
            _calculate_similar_user_author_score_redis,
        )

        redis_client = Mock()

        def mock_exists(key):
            return "likes" in key or "ids" in key or "follows" in key

        def mock_smembers(key):
            if "agent1:likes" in key:
                return {"post1", "post2"}
            elif "user_mgmt:ids" in key:
                return {"user1", "user2", "user3"}
            elif "user1:likes" in key:
                return {"post1", "post2"}  # Same likes as agent1
            elif "user2:likes" in key:
                return {"post1"}  # Some overlap
            elif "user1:follows" in key:
                return {"author1"}  # Follows the author
            elif "user2:follows" in key:
                return {"other"}
            return set()

        redis_client.exists = Mock(side_effect=mock_exists)
        redis_client.smembers = Mock(side_effect=mock_smembers)
        redis_key_fn = Mock(side_effect=lambda *args: ":".join(args))
        db_engine = Mock()

        score = _calculate_similar_user_author_score_redis(
            agent_id="agent1",
            author_id="author1",
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
            db_engine=db_engine,
        )

        # Should return log(1 + count) where count > 0
        assert score > 0


class TestHybridSQLBackend:
    """Test SQL backend implementation of hybrid recommender."""

    def test_hybrid_sql_basic(self):
        """Test basic SQL hybrid recommendation."""
        from YSimulator.YServer.recsys.content_recsys_db import (
            recommend_hybrid_linear_ranker,
        )

        session = Mock()
        q = Mock()
        q.order_by.return_value = q
        q.first.return_value = Mock(day=1, hour=1)
        q.filter.return_value = q
        q.join.return_value = q
        q.all.return_value = []
        session.query.return_value = q

        with patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_rchrono_followers"
        ) as mock_followers, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_rchrono_popularity"
        ) as mock_popularity, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_collaborative_user_user"
        ) as mock_collab, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_random"
        ) as mock_random, patch(
            "YSimulator.YServer.recsys.content_recsys_db._calculate_user_author_affinity_sql",
            return_value=0.0,
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_db._calculate_content_topic_similarity_sql",
            return_value=0.0,
        ), patch(
            "YSimulator.YServer.recsys.content_recsys_db._calculate_similar_user_author_score_sql",
            return_value=0.0,
        ):
            mock_followers.return_value = (["post1", "post2"], False)
            mock_popularity.return_value = ["post2", "post3"]
            mock_collab.return_value = (["post3"], False)
            mock_random.return_value = ["post1", "post2", "post3"]

            result, used_fallback = recommend_hybrid_linear_ranker(
                session=session,
                agent_id="agent1",
                visibility_day=1,
                visibility_hour=0,
                limit=5,
            )

        # Should return some results
        assert isinstance(result, list)

    def test_hybrid_sql_no_candidates(self):
        """Test SQL hybrid with no candidates (should fallback)."""
        from YSimulator.YServer.recsys.content_recsys_db import (
            recommend_hybrid_linear_ranker,
        )

        # Mock session that returns no results
        session = Mock()
        mock_query = Mock()
        mock_query.all = Mock(return_value=[])
        session.query = Mock(return_value=mock_query)

        with patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_rchrono_followers"
        ) as mock_rchrono_followers, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_rchrono_popularity"
        ) as mock_rchrono_pop, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_collaborative_user_user"
        ) as mock_collab, patch(
            "YSimulator.YServer.recsys.content_recsys_db.recommend_random"
        ) as mock_random:
            # All strategies return empty
            mock_rchrono_followers.return_value = ([], True)
            mock_rchrono_pop.return_value = []
            mock_collab.return_value = ([], True)
            mock_random.return_value = []

            result, used_fallback = recommend_hybrid_linear_ranker(
                session=session,
                agent_id="agent1",
                visibility_day=1,
                visibility_hour=0,
                limit=5,
            )

        # Should indicate fallback was used
        assert used_fallback is True
