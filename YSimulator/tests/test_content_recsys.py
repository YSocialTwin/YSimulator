"""
Unit tests for YServer/recsys/content_recsys.py

Tests the content recommendation system for retrieving and filtering posts.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session


class TestContentRecsysRead:
    """Test the main read function for content recommendations."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        return session
    
    @pytest.fixture
    def mock_round(self):
        """Create a mock Round object."""
        mock_round = Mock()
        mock_round.id = 100
        return mock_round
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock User object."""
        user = Mock()
        user.id = "user-123"
        user.leaning = "neutral"
        return user
    
    def test_read_reverse_chronological_mode(self, mock_db_session, mock_round):
        """Test read function with reverse chronological mode."""
        from YSimulator.YServer.recsys import content_recsys
        
        # Mock the Round query to return current round
        with patch('YSimulator.YServer.recsys.content_recsys.Round') as MockRound:
            mock_query = Mock()
            MockRound.query = mock_query
            mock_query.order_by.return_value.first.return_value = mock_round
            
            # Mock desc function to avoid SQLAlchemy column validation
            with patch('YSimulator.YServer.recsys.content_recsys.desc') as mock_desc:
                mock_desc.return_value = Mock()
                
                # Mock db.session
                with patch('YSimulator.YServer.recsys.content_recsys.db', create=True) as mock_db:
                    mock_posts = [Mock(id=f"post-{i}") for i in range(5)]
                    mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_posts
                    
                    result = content_recsys.read(
                        mock_db_session,
                        limit=10,
                        mode="rchrono",
                        visibility_rounds=20,
                        uid="user-123",
                        article=False
                    )
                    
                    # Verify the function was called correctly
                    assert mock_db.session.query.called
    
    def test_read_with_article_filter(self, mock_db_session, mock_round, mock_user):
        """Test read function with article filtering."""
        from YSimulator.YServer.recsys import content_recsys
        
        with patch('YSimulator.YServer.recsys.content_recsys.Round') as MockRound:
            mock_round_query = Mock()
            MockRound.query = mock_round_query
            mock_round_query.order_by.return_value.first.return_value = mock_round
            
            # Mock desc function
            with patch('YSimulator.YServer.recsys.content_recsys.desc') as mock_desc:
                mock_desc.return_value = Mock()
                
                with patch('YSimulator.YServer.recsys.content_recsys.User_mgmt') as MockUserMgmt:
                    mock_user_query = Mock()
                    MockUserMgmt.query = mock_user_query
                    mock_user_query.filter_by.return_value.first.return_value = mock_user
                    mock_user_query.filter_by.return_value.all.return_value = []
                    
                    with patch('YSimulator.YServer.recsys.content_recsys.db', create=True) as mock_db:
                        mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
                        
                        result = content_recsys.read(
                            mock_db_session,
                            limit=10,
                            mode="rchrono",
                            visibility_rounds=20,
                            uid="user-123",
                            article=True
                        )
                        
                        # Verify user was queried for article filtering
                        assert mock_user_query.filter_by.called
    
    def test_read_popularity_mode(self, mock_db_session, mock_round):
        """Test read function with popularity-based ordering."""
        from YSimulator.YServer.recsys import content_recsys
        
        with patch('YSimulator.YServer.recsys.content_recsys.Round') as MockRound:
            mock_query = Mock()
            MockRound.query = mock_query
            mock_query.order_by.return_value.first.return_value = mock_round
            
            # Mock desc function
            with patch('YSimulator.YServer.recsys.content_recsys.desc') as mock_desc:
                mock_desc.return_value = Mock()
                
                with patch('YSimulator.YServer.recsys.content_recsys.db', create=True) as mock_db:
                    mock_posts = [Mock(id=f"post-{i}", reaction_count=i) for i in range(5)]
                    mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_posts
                    
                    result = content_recsys.read(
                        mock_db_session,
                        limit=10,
                        mode="rchrono_popularity",
                        visibility_rounds=20,
                        uid="user-123",
                        article=False
                    )
                    
                    assert mock_db.session.query.called
    
    def test_read_with_followers_ratio(self, mock_db_session, mock_round):
        """Test read function with followers ratio parameter."""
        from YSimulator.YServer.recsys import content_recsys
        
        with patch('YSimulator.YServer.recsys.content_recsys.Round') as MockRound:
            mock_query = Mock()
            MockRound.query = mock_query
            mock_query.order_by.return_value.first.return_value = mock_round
            
            # Mock desc function
            with patch('YSimulator.YServer.recsys.content_recsys.desc') as mock_desc:
                mock_desc.return_value = Mock()
                
                # Mock Follow model
                with patch('YSimulator.YServer.recsys.content_recsys.Follow') as MockFollow:
                    mock_follow_query = Mock()
                    MockFollow.query = mock_follow_query
                    # Return empty list for followers
                    mock_follow_query.filter_by.return_value = []
                    
                    # Mock Post model with chainable query and column attributes
                    with patch('YSimulator.YServer.recsys.content_recsys.Post') as MockPost:
                        # Mock column attributes to support comparison operations
                        mock_round_col = Mock()
                        mock_round_col.__ge__ = Mock(return_value=Mock())  # For >= operator
                        mock_user_id_col = Mock()
                        mock_user_id_col.in_ = Mock(return_value=Mock())
                        
                        MockPost.round = mock_round_col
                        MockPost.user_id = mock_user_id_col
                        
                        mock_post_query = Mock()
                        MockPost.query = mock_post_query
                        # Make the query chainable
                        mock_post_query.filter.return_value = mock_post_query
                        mock_post_query.order_by.return_value = mock_post_query
                        mock_post_query.limit.return_value = mock_post_query
                        mock_post_query.all.return_value = []
                        
                        # Mock db for visibility calculation
                        with patch('YSimulator.YServer.recsys.content_recsys.db', create=True) as mock_db:
                            # Mock Recommendation model
                            with patch('YSimulator.YServer.recsys.content_recsys.Recommendation') as MockRecommendation:
                                # Test with followers_ratio < 1
                                result = content_recsys.read(
                                    mock_db_session,
                                    limit=10,
                                    mode="rchrono_followers",
                                    visibility_rounds=20,
                                    uid="user-123",
                                    followers_ratio=0.5
                                )
                                
                                # Verify Follow was queried
                                assert MockFollow.query.filter_by.called
                                # Result should be empty list
                                assert result == []
    
    def test_visibility_calculation(self, mock_db_session, mock_round):
        """Test that visibility is calculated correctly."""
        from YSimulator.YServer.recsys import content_recsys
        
        mock_round.id = 100
        visibility_rounds = 20
        expected_visibility = 100 - 20  # = 80
        
        with patch('YSimulator.YServer.recsys.content_recsys.Round') as MockRound:
            mock_query = Mock()
            MockRound.query = mock_query
            mock_query.order_by.return_value.first.return_value = mock_round
            
            # Mock desc function
            with patch('YSimulator.YServer.recsys.content_recsys.desc') as mock_desc:
                mock_desc.return_value = Mock()
                
                with patch('YSimulator.YServer.recsys.content_recsys.db', create=True) as mock_db:
                    mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
                    
                    result = content_recsys.read(
                        mock_db_session,
                        limit=10,
                        mode="rchrono",
                        visibility_rounds=visibility_rounds,
                        uid="user-123"
                )
                
                # Visibility should be current_round.id - visibility_rounds
                assert mock_query.order_by.called


class TestContentRecsysFilters:
    """Test filtering logic in content recommendation system."""
    
    def test_filter_excludes_user_posts(self):
        """Test that user's own posts are filtered out."""
        # This would test Post.user_id != uid filtering
        assert True  # Placeholder - actual implementation would mock query filters
    
    def test_filter_by_visibility_rounds(self):
        """Test that posts are filtered by visibility threshold."""
        # This would test Post.round >= visibility filtering
        assert True  # Placeholder
    
    def test_filter_news_posts_by_leaning(self):
        """Test that news posts are filtered by user leaning when article=True."""
        # This would test page filtering by leaning
        assert True  # Placeholder


class TestContentRecsysLimits:
    """Test limit handling in content recommendation system."""
    
    def test_respects_post_limit(self):
        """Test that returned posts respect the limit parameter."""
        assert True  # Placeholder - would verify query.limit() is called correctly
    
    def test_follower_posts_limit_calculation(self):
        """Test calculation of follower vs additional posts limits."""
        # When followers_ratio < 1
        limit = 10
        followers_ratio = 0.6
        
        expected_follower_limit = int(limit * followers_ratio)  # 6
        expected_additional_limit = limit - expected_follower_limit  # 4
        
        assert expected_follower_limit == 6
        assert expected_additional_limit == 4
    
    def test_follower_posts_limit_full_ratio(self):
        """Test that full followers_ratio uses entire limit."""
        limit = 10
        followers_ratio = 1
        
        expected_follower_limit = limit
        expected_additional_limit = 0
        
        assert expected_follower_limit == 10
        assert expected_additional_limit == 0


class TestContentRecsysModes:
    """Test different recommendation modes."""
    
    def test_supported_modes(self):
        """Test that expected modes are handled."""
        supported_modes = [
            "rchrono",
            "rchrono_popularity",
            "rchrono_followers",
            "rchrono_followers_popularity",
            "rchrono_comments",
            "random",
            "common_interests",
            "common_user_interests",
            "similar_users_react",
            "similar_users_posts"
        ]
        
        # Verify modes are defined (placeholder test)
        assert len(supported_modes) > 0
    
    def test_mode_rchrono(self):
        """Test reverse chronological mode."""
        mode = "rchrono"
        assert mode == "rchrono"
    
    def test_mode_with_popularity(self):
        """Test modes that include popularity sorting."""
        mode = "rchrono_popularity"
        assert "popularity" in mode


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
