"""
Unit tests for action processors.

Tests each action processor in isolation with mocked services.
"""

import pytest
from unittest.mock import Mock, MagicMock
from YSimulator.YServer.action_processors.base_processor import ActionContext, ActionResult
from YSimulator.YServer.action_processors.post_processor import PostProcessor
from YSimulator.YServer.action_processors.comment_processor import CommentProcessor
from YSimulator.YServer.action_processors.share_processor import ShareProcessor
from YSimulator.YServer.action_processors.follow_processor import FollowProcessor
from YSimulator.YServer.action_processors.unfollow_processor import UnfollowProcessor
from YSimulator.YServer.action_processors.reaction_processor import ReactionProcessor
from YSimulator.YServer.action_processors.action_router import ActionRouter


@pytest.fixture
def mock_services():
    """Create mock services for testing."""
    services = Mock()

    # Create nested service mocks to match actual service structure
    services.post_service = Mock()
    services.post_service.create_post = Mock(return_value="post_123")
    services.post_service.get_post = Mock(
        return_value={"user_id": "user_1", "thread_id": "thread_1"}
    )
    services.post_service.add_post_topic = Mock(return_value=True)
    services.post_service.get_post_topics = Mock(return_value=["topic_1"])
    services.post_service.get_post_sentiment = Mock(return_value={"compound": 0.5})
    services.post_service.add_post_sentiment = Mock(return_value=True)
    services.post_service.increment_post_reaction_count = Mock(return_value=True)
    services.post_service.add_interaction = Mock(return_value=True)

    services.article_service = Mock()
    services.article_service.get_article = Mock(
        return_value={"title": "Test", "content": "Content"}
    )
    services.article_service.get_article_topics = Mock(return_value=["topic_1", "topic_2"])
    services.article_service.get_article_reference = Mock(return_value=None)
    services.article_service.copy_article_reference = Mock()

    services.interest_service = Mock()
    services.interest_service.get_topic_name_from_id = Mock(return_value="Politics")
    services.interest_service.add_or_get_interest = Mock(return_value="topic_1")
    services.interest_service.add_user_interest = Mock(return_value=True)
    services.interest_service.add_agent_opinion = Mock(return_value=True)

    services.follow_service = Mock()
    services.follow_service.add_follow = Mock(return_value=True)

    services.metadata_service = Mock()
    services.metadata_service.get_post_sentiment = Mock(return_value={"compound": 0.5})
    services.metadata_service.add_post_sentiment = Mock(return_value=True)
    services.metadata_service._is_empty_or_default = Mock(return_value=False)

    # Server-level helper methods (on services object itself)
    services._ensure_agent_opinion_exists = Mock()
    services._update_agent_interest_counter = Mock()
    services._process_annotations = Mock(return_value=[])
    services._get_topic_name_from_id = Mock(return_value="Politics")

    return services


@pytest.fixture
def action_context():
    """Create action context for testing."""
    return ActionContext(current_round_id="round_1", day=1, slot=1)


@pytest.fixture
def mock_action():
    """Create mock action DTO."""
    action = Mock()
    action.agent_id = "agent_1"
    action.action_type = "POST"
    action.content = "Test post content"
    return action


class TestPostProcessor:
    """Test PostProcessor."""

    def test_process_simple_post(self, mock_services, action_context, mock_action):
        """Test processing a simple post."""
        processor = PostProcessor(mock_services)
        mock_action.action_type = "POST"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "POST"
        assert "post_123" in result.new_ids
        assert mock_services.post_service.create_post.called

    def test_process_article_post(self, mock_services, action_context, mock_action):
        """Test processing an article post."""
        processor = PostProcessor(mock_services)
        mock_action.article_id = "article_1"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        mock_services.article_service.get_article.assert_called()
        mock_services.post_service.add_post_topic.assert_called()

    def test_process_post_with_topic(self, mock_services, action_context, mock_action):
        """Test processing a post with topic."""
        processor = PostProcessor(mock_services)
        mock_action.topic = "Technology"
        mock_action.article_id = None  # Not an article post
        mock_action.image_id = None  # Not an image post
        # Don't set topic_ids attribute at all (use hasattr check)
        if hasattr(mock_action, "topic_ids"):
            delattr(mock_action, "topic_ids")

        result = processor.process(mock_action, action_context)

        assert result.success is True
        # Verify add_or_get_interest was called with the topic
        mock_services.interest_service.add_or_get_interest.assert_called_with("Technology")


class TestCommentProcessor:
    """Test CommentProcessor."""

    def test_process_comment(self, mock_services, action_context, mock_action):
        """Test processing a comment."""
        processor = CommentProcessor(mock_services)
        mock_action.action_type = "COMMENT"
        mock_action.target_post_id = "post_1"
        mock_action.annotations = None  # No annotations for simplicity
        mock_action.updated_opinions = None  # No opinion updates

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "COMMENT"
        mock_services.post_service.get_post.assert_called()
        mock_services.post_service.create_post.assert_called()
        mock_services.post_service.increment_post_reaction_count.assert_called()

    def test_comment_parent_not_found(self, mock_services, action_context, mock_action):
        """Test comment when parent post not found."""
        processor = CommentProcessor(mock_services)
        mock_action.action_type = "COMMENT"
        mock_action.target_post_id = "post_1"
        mock_services.post_service.get_post = Mock(return_value=None)

        result = processor.process(mock_action, action_context)

        assert result.success is False
        assert "Parent post not found" in result.error


class TestShareProcessor:
    """Test ShareProcessor."""

    def test_process_share(self, mock_services, action_context, mock_action):
        """Test processing a share action."""
        processor = ShareProcessor(mock_services)
        mock_action.action_type = "SHARE"
        mock_action.target_post_id = "post_1"
        mock_action.content = "Sharing this post"
        mock_action.updated_opinions = None  # No opinion updates

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "SHARE"
        mock_services.post_service.get_post.assert_called()
        mock_services.post_service.create_post.assert_called()

    def test_share_original_not_found(self, mock_services, action_context, mock_action):
        """Test share when original post not found."""
        processor = ShareProcessor(mock_services)
        mock_action.action_type = "SHARE"
        mock_action.target_post_id = "post_1"
        mock_services.post_service.get_post = Mock(return_value=None)

        result = processor.process(mock_action, action_context)

        assert result.success is False
        assert "Original post not found" in result.error


class TestFollowProcessor:
    """Test FollowProcessor."""

    def test_process_follow(self, mock_services, action_context, mock_action):
        """Test processing a follow action."""
        processor = FollowProcessor(mock_services)
        mock_action.action_type = "FOLLOW"
        mock_action.target_user_id = "user_2"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "FOLLOW"
        mock_services.follow_service.add_follow.assert_called()

    def test_follow_failure(self, mock_services, action_context, mock_action):
        """Test follow when database operation fails."""
        processor = FollowProcessor(mock_services)
        mock_action.action_type = "FOLLOW"
        mock_action.target_user_id = "user_2"
        mock_services.follow_service.add_follow = Mock(return_value=False)

        result = processor.process(mock_action, action_context)

        assert result.success is False


class TestUnfollowProcessor:
    """Test UnfollowProcessor."""

    def test_process_unfollow(self, mock_services, action_context, mock_action):
        """Test processing an unfollow action."""
        processor = UnfollowProcessor(mock_services)
        mock_action.action_type = "UNFOLLOW"
        mock_action.target_user_id = "user_2"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "UNFOLLOW"
        mock_services.follow_service.add_follow.assert_called()


class TestReactionProcessor:
    """Test ReactionProcessor."""

    def test_process_like(self, mock_services, action_context, mock_action):
        """Test processing a LIKE reaction."""
        processor = ReactionProcessor(mock_services)
        mock_action.action_type = "LIKE"
        mock_action.target_post_id = "post_1"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "LIKE"
        mock_services.post_service.add_interaction.assert_called()
        mock_services.post_service.increment_post_reaction_count.assert_called()

    def test_process_reaction_with_sentiment(self, mock_services, action_context, mock_action):
        """Test reaction processing includes sentiment."""
        processor = ReactionProcessor(mock_services)
        mock_action.action_type = "LOVE"
        mock_action.target_post_id = "post_1"

        result = processor.process(mock_action, action_context)

        assert result.success is True
        mock_services.metadata_service.add_post_sentiment.assert_called()


class TestActionRouter:
    """Test ActionRouter."""

    def test_route_post_action(self, mock_services, action_context, mock_action):
        """Test routing POST action."""
        router = ActionRouter(mock_services)
        mock_action.action_type = "POST"

        result = router.route(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "POST"

    def test_route_comment_action(self, mock_services, action_context, mock_action):
        """Test routing COMMENT action."""
        router = ActionRouter(mock_services)
        mock_action.action_type = "COMMENT"
        mock_action.target_post_id = "post_1"
        mock_action.annotations = None  # No annotations
        mock_action.updated_opinions = None  # No opinion updates

        result = router.route(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "COMMENT"

    def test_route_reaction_action(self, mock_services, action_context, mock_action):
        """Test routing reaction action (uses default processor)."""
        router = ActionRouter(mock_services)
        mock_action.action_type = "LIKE"
        mock_action.target_post_id = "post_1"

        result = router.route(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "LIKE"

    def test_register_custom_processor(self, mock_services, action_context):
        """Test registering a custom processor."""
        router = ActionRouter(mock_services)
        custom_processor = Mock(spec=PostProcessor)
        custom_processor.validate = Mock(return_value=True)
        custom_processor.process = Mock(
            return_value=ActionResult(success=True, action_type="CUSTOM", agent_id="agent_1")
        )

        router.register_processor("CUSTOM", custom_processor)

        mock_action = Mock()
        mock_action.action_type = "CUSTOM"
        mock_action.agent_id = "agent_1"

        result = router.route(mock_action, action_context)

        assert result.success is True
        assert result.action_type == "CUSTOM"
        custom_processor.process.assert_called()
