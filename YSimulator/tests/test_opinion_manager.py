"""
Tests for the opinion dynamics module.

This module tests the Phase 4 refactoring: Opinion Manager extraction.
Tests cover:
- OpinionManager main interface
- OpinionCalculator for opinion updates
- OpinionInferencer for page agent opinions
- OpinionCache for performance optimization
"""

from unittest.mock import Mock, patch

import pytest

from YSimulator.YClient.classes.ray_models import AgentProfile
from YSimulator.YClient.opinion import (
    OpinionCache,
    OpinionCalculator,
    OpinionInferencer,
    OpinionManager,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = Mock()
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def mock_server():
    """Create a mock Ray server actor."""
    server = Mock()
    return server


@pytest.fixture
def mock_llm_manager():
    """Create a mock LLM manager."""
    # Use spec to prevent auto-creation of attributes
    llm = Mock(spec=["infer_article_opinion", "__class__"])
    llm.__class__.__name__ = "LLMManager"
    return llm


@pytest.fixture
def basic_simulation_config():
    """Create a basic simulation config with opinion dynamics."""
    return {
        "opinion_dynamics": {
            "enabled": True,
            "model_name": "bounded_confidence",
            "parameters": {
                "epsilon": 0.25,
                "mu": 0.5,
                "theta": 0.0,
                "cold_start": "neutral",
            },
            "opinion_groups": {
                "Strongly against": [0.0, 0.2],
                "Against": [0.2, 0.4],
                "Neutral": [0.4, 0.6],
                "In favor": [0.6, 0.8],
                "Strongly in favor": [0.8, 1.0],
            },
        }
    }


@pytest.fixture
def agent_profiles():
    """Create test agent profiles."""
    # LLM agent
    llm_agent = AgentProfile(
        id="agent_llm_1",
        username="llm_user",
        llm=True,
        is_page=0,
        opinions={"climate_change": 0.7, "technology": 0.8},
    )

    # Rule-based agent
    rule_agent = AgentProfile(
        id="agent_rule_1",
        username="rule_user",
        llm=False,
        is_page=0,
        opinions={"climate_change": 0.3, "healthcare": 0.6},
    )

    # Page agent (LLM)
    page_agent = AgentProfile(
        id="agent_page_1",
        username="page_user",
        llm=True,
        is_page=1,
        feed_url="https://example.com/feed",
        opinions={},
    )

    return [llm_agent, rule_agent, page_agent]


class TestOpinionCache:
    """Tests for OpinionCache class."""

    def test_cache_initialization(self, mock_logger):
        """Test cache initializes with empty state."""
        cache = OpinionCache(logger=mock_logger)
        stats = cache.get_stats()
        assert stats["agent_opinions_count"] == 0
        assert stats["topic_names_count"] == 0
        assert stats["opinion_groups_count"] == 0

    def test_cache_agent_opinion(self, mock_logger):
        """Test caching and retrieving agent opinions."""
        cache = OpinionCache(logger=mock_logger)

        # Set opinion
        cache.set_agent_opinion("agent_1", "topic_1", 0.75)

        # Get opinion
        opinion = cache.get_agent_opinion("agent_1", "topic_1")
        assert opinion == 0.75

        # Non-existent opinion
        assert cache.get_agent_opinion("agent_2", "topic_1") is None
        assert cache.get_agent_opinion("agent_1", "topic_2") is None

    def test_cache_topic_name(self, mock_logger):
        """Test caching and retrieving topic names."""
        cache = OpinionCache(logger=mock_logger)

        # Set topic name
        cache.set_topic_name("topic_id_1", "Climate Change")

        # Get topic name
        name = cache.get_topic_name("topic_id_1")
        assert name == "Climate Change"

        # Non-existent topic
        assert cache.get_topic_name("topic_id_2") is None

    def test_cache_opinion_group(self, mock_logger):
        """Test caching and retrieving opinion group labels."""
        cache = OpinionCache(logger=mock_logger)

        # Set opinion group
        cache.set_opinion_group(0.75, "In favor")

        # Get opinion group
        group = cache.get_opinion_group(0.75)
        assert group == "In favor"

        # Non-existent group
        assert cache.get_opinion_group(0.25) is None

    def test_clear_cache(self, mock_logger):
        """Test clearing all cache data."""
        cache = OpinionCache(logger=mock_logger)

        # Add some data
        cache.set_agent_opinion("agent_1", "topic_1", 0.75)
        cache.set_topic_name("topic_id_1", "Climate Change")
        cache.set_opinion_group(0.75, "In favor")

        # Clear cache
        cache.clear()

        # Verify all cleared
        assert cache.get_agent_opinion("agent_1", "topic_1") is None
        assert cache.get_topic_name("topic_id_1") is None
        assert cache.get_opinion_group(0.75) is None

        stats = cache.get_stats()
        assert stats["agent_opinions_count"] == 0

    def test_clear_agent(self, mock_logger):
        """Test clearing cache for specific agent."""
        cache = OpinionCache(logger=mock_logger)

        # Add data for two agents
        cache.set_agent_opinion("agent_1", "topic_1", 0.75)
        cache.set_agent_opinion("agent_2", "topic_1", 0.25)

        # Clear agent_1
        cache.clear_agent("agent_1")

        # Verify agent_1 cleared but agent_2 remains
        assert cache.get_agent_opinion("agent_1", "topic_1") is None
        assert cache.get_agent_opinion("agent_2", "topic_1") == 0.25


class TestOpinionInferencer:
    """Tests for OpinionInferencer class."""

    def test_infer_llm_opinion(self, basic_simulation_config, mock_llm_manager, mock_logger):
        """Test inferring opinion for LLM page agent."""
        inferencer = OpinionInferencer(
            opinion_config=basic_simulation_config["opinion_dynamics"],
            llm_manager=mock_llm_manager,
            logger=mock_logger,
        )

        # Create LLM page agent
        agent = AgentProfile(
            id="page_1",
            username="page",
            llm=True,
            is_page=1,
            feed_url="https://example.com",
        )

        # Mock LLM response
        with patch("ray.get", return_value=0.85):
            opinion = inferencer.infer_opinion(
                agent_profile=agent,
                article_content="Article about renewable energy benefits",
                topic_name="climate_change",
            )

        assert opinion == 0.85
        mock_llm_manager.infer_article_opinion.assert_called_once()

    def test_infer_rule_based_opinion(self, basic_simulation_config, mock_llm_manager, mock_logger):
        """Test inferring opinion for rule-based page agent."""
        inferencer = OpinionInferencer(
            opinion_config=basic_simulation_config["opinion_dynamics"],
            llm_manager=mock_llm_manager,
            logger=mock_logger,
        )

        # Create rule-based page agent
        agent = AgentProfile(
            id="page_1",
            username="page",
            llm=False,
            is_page=1,
            feed_url="https://example.com",
        )

        # Should return random value
        opinion = inferencer.infer_opinion(
            agent_profile=agent,
            article_content="Some article",
            topic_name="topic",
        )

        assert 0.0 <= opinion <= 1.0
        # LLM should not be called for rule-based
        mock_llm_manager.infer_article_opinion.assert_not_called()

    def test_infer_opinion_no_profile(self, basic_simulation_config, mock_llm_manager, mock_logger):
        """Test inferring opinion when agent profile not found."""
        inferencer = OpinionInferencer(
            opinion_config=basic_simulation_config["opinion_dynamics"],
            llm_manager=mock_llm_manager,
            logger=mock_logger,
        )

        # No profile provided
        opinion = inferencer.infer_opinion(
            agent_profile=None,
            article_content="Some article",
            topic_name="topic",
        )

        assert 0.0 <= opinion <= 1.0
        mock_logger.warning.assert_called()


class TestOpinionCalculator:
    """Tests for OpinionCalculator class."""

    def test_calculate_bounded_confidence_updates(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test calculating opinion updates with bounded confidence model."""
        calculator = OpinionCalculator(
            opinion_config=basic_simulation_config["opinion_dynamics"],
            server=mock_server,
            llm_manager=mock_llm_manager,
            client_id="test_client",
            logger=mock_logger,
            get_opinion_group_fn=lambda x: "Neutral",
        )

        # Mock server responses
        with patch("ray.get") as mock_ray_get:
            # Setup mock return values in order
            mock_ray_get.side_effect = [
                ["topic_1"],  # get_post_topics
                "climate_change",  # get_topic_name_from_id
                0.5,  # get_latest_agent_opinion (agent)
                0.7,  # get_latest_agent_opinion (author)
            ]

            post_data = {"user_id": "author_1", "tweet": "Test post content"}

            updates = calculator.calculate_updates(
                agent_id="agent_1",
                parent_post_id="post_1",
                parent_post_data=post_data,
                agent_profiles=agent_profiles,
            )

        assert updates is not None
        assert "topic_1" in updates
        # Bounded confidence should update the opinion
        assert updates["topic_1"] != 0.5

    def test_calculate_updates_no_config(
        self, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test that no updates are calculated when config is empty."""
        calculator = OpinionCalculator(
            opinion_config={},
            server=mock_server,
            llm_manager=mock_llm_manager,
            client_id="test_client",
            logger=mock_logger,
            get_opinion_group_fn=lambda x: "Neutral",
        )

        post_data = {"user_id": "author_1", "tweet": "Test post"}

        updates = calculator.calculate_updates(
            agent_id="agent_1",
            parent_post_id="post_1",
            parent_post_data=post_data,
            agent_profiles=agent_profiles,
        )

        assert updates is None

    def test_calculate_updates_no_author_opinion(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test that updates are skipped when author has no opinion."""
        calculator = OpinionCalculator(
            opinion_config=basic_simulation_config["opinion_dynamics"],
            server=mock_server,
            llm_manager=mock_llm_manager,
            client_id="test_client",
            logger=mock_logger,
            get_opinion_group_fn=lambda x: "Neutral",
        )

        # Mock server responses
        with patch("ray.get") as mock_ray_get:
            mock_ray_get.side_effect = [
                ["topic_1"],  # get_post_topics
                "climate_change",  # get_topic_name_from_id
                0.5,  # get_latest_agent_opinion (agent)
                None,  # get_latest_agent_opinion (author) - no opinion
            ]

            post_data = {"user_id": "author_1", "tweet": "Test post"}

            updates = calculator.calculate_updates(
                agent_id="agent_1",
                parent_post_id="post_1",
                parent_post_data=post_data,
                agent_profiles=agent_profiles,
            )

        # Should return None or empty dict since author has no opinion
        assert updates is None or updates == {}
        mock_logger.debug.assert_called()


class TestOpinionManager:
    """Tests for OpinionManager main interface."""

    def test_manager_initialization(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test opinion manager initializes correctly."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        assert manager.is_enabled() is True
        assert manager.calculator is not None
        assert manager.inferencer is not None
        assert manager.cache is not None

    def test_is_enabled(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test checking if opinion dynamics is enabled."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        assert manager.is_enabled() is True

        # Test disabled config
        disabled_config = {"opinion_dynamics": {"enabled": False}}
        manager2 = OpinionManager(
            simulation_config=disabled_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        assert manager2.is_enabled() is False

    def test_map_opinion_to_group(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test mapping opinion values to group labels."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        assert manager.map_opinion_to_group(0.1) == "Strongly against"
        assert manager.map_opinion_to_group(0.3) == "Against"
        assert manager.map_opinion_to_group(0.5) == "Neutral"
        assert manager.map_opinion_to_group(0.7) == "In favor"
        assert manager.map_opinion_to_group(0.9) == "Strongly in favor"

    def test_map_opinion_to_group_default(
        self, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test default opinion group mapping when not configured."""
        config = {"opinion_dynamics": {"enabled": True}}
        manager = OpinionManager(
            simulation_config=config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        # Should use default mapping
        assert manager.map_opinion_to_group(0.1) == "Strongly against"
        assert manager.map_opinion_to_group(0.5) == "Neutral"
        assert manager.map_opinion_to_group(0.9) == "Strongly in favor"

    def test_get_opinions_for_post(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test getting agent opinions for a post."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        # Mock server responses
        with patch("ray.get") as mock_ray_get:
            mock_ray_get.side_effect = [
                ["topic_1"],  # get_post_topics
                "climate_change",  # get_topic_name_from_id
            ]

            opinions = manager.get_opinions_for_post("agent_llm_1", "post_1")

        assert "topics" in opinions
        assert "opinions" in opinions
        assert "opinion_values" in opinions
        assert "climate_change" in opinions["topics"]
        assert opinions["opinion_values"]["climate_change"] == 0.7

    def test_get_opinions_for_post_disabled(
        self, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test that no opinions are returned when disabled."""
        config = {"opinion_dynamics": {"enabled": False}}
        manager = OpinionManager(
            simulation_config=config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        opinions = manager.get_opinions_for_post("agent_llm_1", "post_1")

        assert opinions["topics"] == []
        assert opinions["opinions"] == {}
        assert opinions["opinion_values"] == {}

    def test_calculate_opinion_updates_delegates(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test that calculate_opinion_updates delegates to calculator."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        # Mock the calculator's method
        manager.calculator.calculate_updates = Mock(return_value={"topic_1": 0.6})

        post_data = {"user_id": "author_1", "tweet": "Test"}
        updates = manager.calculate_opinion_updates("agent_1", "post_1", post_data)

        assert updates == {"topic_1": 0.6}
        manager.calculator.calculate_updates.assert_called_once()

    def test_infer_page_agent_opinion_delegates(
        self, basic_simulation_config, mock_server, mock_llm_manager, mock_logger, agent_profiles
    ):
        """Test that infer_page_agent_opinion delegates to inferencer."""
        manager = OpinionManager(
            simulation_config=basic_simulation_config,
            server=mock_server,
            llm_manager=mock_llm_manager,
            agent_profiles=agent_profiles,
            client_id="test_client",
            logger=mock_logger,
        )

        # Mock the inferencer's method
        manager.inferencer.infer_opinion = Mock(return_value=0.75)

        opinion = manager.infer_page_agent_opinion("agent_page_1", "Article content", "topic")

        assert opinion == 0.75
        manager.inferencer.infer_opinion.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
