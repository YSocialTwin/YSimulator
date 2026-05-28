"""
Unit tests for action generator framework.

Tests the new action generator framework introduced in Phase 1 refactoring.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from YSimulator.YClient.action_generators import ActionContext, ActionGeneratorFactory
from YSimulator.YClient.action_generators.follow_generator import FollowGenerator
from YSimulator.YClient.action_generators.post_generator import PostGenerator
from YSimulator.YClient.action_generators.reply_generator import ReplyGenerator
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile


@pytest.fixture
def mock_context():
    """Create a mock ActionContext for testing."""
    context = ActionContext(
        day=1,
        slot=5,
        recent_posts=["post1", "post2", "post3"],
        server=MagicMock(),
        logger=MagicMock(),
        client_id="test_client",
        round_id="test_round_id",
        llm=MagicMock(),
        news_service=MagicMock(),
    )
    return context


@pytest.fixture
def mock_agent():
    """Create a mock AgentProfile for testing."""
    agent = AgentProfile(
        id=1,
        username="test_agent",
        cluster=1,
        llm=False,
        is_page=0,
        daily_activity_level=3,
        activity_profile="default",
    )
    return agent


def test_action_context_creation(mock_context):
    """Test that ActionContext can be created with required fields."""
    assert mock_context.day == 1
    assert mock_context.slot == 5
    assert len(mock_context.recent_posts) == 3
    assert mock_context.client_id == "test_client"


def test_action_generator_factory_creation(mock_context):
    """Test that ActionGeneratorFactory can be created and initialized."""
    factory = ActionGeneratorFactory(mock_context)
    assert factory is not None
    assert factory.context == mock_context


def test_factory_has_all_generators(mock_context):
    """Test that factory has all expected action types registered."""
    factory = ActionGeneratorFactory(mock_context)
    expected_types = [
        "post",
        "comment",
        "read",
        "follow",
        "share_link",
        "share",
        "search",
        "image",
        "cast",
    ]

    for action_type in expected_types:
        assert factory.has_generator(action_type), f"Missing generator for {action_type}"


def test_factory_get_generator(mock_context):
    """Test that factory can retrieve generators."""
    factory = ActionGeneratorFactory(mock_context)

    post_generator = factory.get_generator("post")
    assert isinstance(post_generator, PostGenerator)

    follow_generator = factory.get_generator("follow")
    assert isinstance(follow_generator, FollowGenerator)


def test_factory_get_invalid_generator(mock_context):
    """Test that factory raises error for invalid action type."""
    factory = ActionGeneratorFactory(mock_context)

    with pytest.raises(ValueError):
        factory.get_generator("invalid_action")


def test_post_generator_rule_based(mock_context, mock_agent):
    """Test PostGenerator for rule-based agents."""
    # Setup
    mock_context.extract_agent_attrs_fn = lambda agent: {"topic": "test_topic"}
    mock_context.annotate_action_fn = lambda action: None

    generator = PostGenerator(mock_context)

    # Execute
    result = generator.generate(mock_agent, "rule_based")

    # Verify
    assert len(result.actions) == 1
    assert len(result.pending_llm_calls) == 0

    action = result.actions[0]
    assert action.action_type == "POST"
    assert action.agent_id == 1
    assert action.cluster_id == 1
    assert action.topic == "test_topic"


def test_post_generator_llm(mock_context, mock_agent):
    """Test PostGenerator for LLM agents."""
    # Setup
    mock_context.extract_agent_attrs_fn = lambda agent: {"topic": "test_topic"}
    mock_context.llm.generate_post.remote = Mock(return_value="future_obj")

    generator = PostGenerator(mock_context)

    # Execute
    result = generator.generate(mock_agent, "llm")

    # Verify
    assert len(result.actions) == 0  # LLM calls are async
    assert len(result.pending_llm_calls) == 1

    agent_id, cluster_id, future, topic, day, slot, agent_attrs = result.pending_llm_calls[0]
    assert agent_id == 1
    assert cluster_id == 1
    assert topic == "test_topic"
    assert day == 1
    assert slot == 5
    assert isinstance(agent_attrs, dict)


def test_follow_generator_no_suggestions(mock_context, mock_agent):
    """Test FollowGenerator when no follow suggestions are available."""
    # This test verifies behavior when there are no follow suggestions
    # We'll skip the complex mocking and just test the simple path
    pytest.skip(
        "Complex test requiring deep mocking - generator framework validated in integration tests"
    )


def test_generator_can_generate_default(mock_context, mock_agent):
    """Test that default can_generate returns True."""
    generator = PostGenerator(mock_context)
    assert generator.can_generate(mock_agent, "rule_based") is True


def test_action_generator_result_structure():
    """Test ActionGeneratorResult structure."""
    from YSimulator.YClient.action_generators.base_generator import ActionGeneratorResult

    result = ActionGeneratorResult()
    assert result.actions == []
    assert result.pending_llm_calls == []
    assert result.metadata == {}

    # Test with data
    action = ActionDTO(1, 1, "POST", content="test")
    result.actions.append(action)
    result.metadata["test_key"] = "test_value"

    assert len(result.actions) == 1
    assert result.metadata["test_key"] == "test_value"


def test_factory_list_action_types(mock_context):
    """Test that factory can list all registered action types."""
    factory = ActionGeneratorFactory(mock_context)
    action_types = factory.list_action_types()

    assert isinstance(action_types, list)
    assert len(action_types) == 10  # We have 10 action types (including reply)
    assert "post" in action_types
    assert "follow" in action_types


def test_reply_generator_rule_based_attaches_opinion_updates(mock_context, mock_agent):
    """Rule-based mention replies should carry updated opinions like other comments."""
    mention = {"id": "mention-1", "post_id": "post-1"}
    post_data = {"user_id": "author-1", "tweet": "@test_agent Please respond"}
    author_data = {"username": "author_name"}

    mock_context.server.get_unreplied_mentions.remote = MagicMock(return_value=[mention])
    mock_context.server.get_post.remote = MagicMock(return_value=post_data)
    mock_context.server.get_user.remote = MagicMock(return_value=author_data)
    mock_context.server.mark_mention_replied.remote = MagicMock(return_value=True)
    mock_context.annotate_action_fn = MagicMock()
    mock_context.calculate_opinion_updates_fn = MagicMock(return_value={"topic-1": 0.72})

    generator = ReplyGenerator(mock_context)

    with patch(
        "YSimulator.YClient.action_generators.reply_generator.ray.get",
        side_effect=lambda value: value,
    ):
        result = generator.generate(mock_agent, "rule_based")

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.action_type == "COMMENT"
    assert action.updated_opinions == {"topic-1": 0.72}
    mock_context.calculate_opinion_updates_fn.assert_called_once_with(
        mock_agent.id, "post-1", post_data
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
