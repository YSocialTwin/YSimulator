"""
Tests for Agent Management Module (Phase 6).

This module tests the Phase 6 refactoring: Agent Manager extraction.
Tests cover:
- AgentManager main coordinator
- PopulationLoader for agent creation and persistence
- NetworkLoader for social network management
- AgentSelector for agent selection and type determination
"""

import csv
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from YSimulator.YClient.agent_management import (
    AgentManager,
    AgentSelector,
    NetworkLoader,
    PopulationLoader,
)
from YSimulator.YClient.classes.ray_models import AgentProfile


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
    server.add_follow_relationships_batch = Mock()
    server.add_follow_relationships_batch.remote = Mock(return_value=Mock())
    return server


@pytest.fixture
def temp_config_dir():
    """Create a temporary configuration directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)

        # Create predefined agents file
        agents_file = config_path / "agents_predefined.csv"
        with open(agents_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["id", "username", "cluster", "llm", "is_page", "daily_activity_level", "archetype"]
            )
            writer.writerow([1, "agent_001", 1, 0, 0, 3, "default"])
            writer.writerow([2, "agent_002", 1, 1, 0, 5, "influencer"])

        # Create network file
        network_file = config_path / "network.csv"
        with open(network_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["agent_001", "agent_002"])
            writer.writerow(["agent_002", "agent_001"])

        yield config_path


@pytest.fixture
def archetype_distribution():
    """Create sample archetype distribution."""
    return {
        "default": 0.7,
        "influencer": 0.2,
        "lurker": 0.1,
    }


@pytest.fixture
def actions_likelihood():
    """Create sample actions likelihood configuration."""
    return {
        "post": 0.3,
        "comment": 0.4,
        "follow": 0.2,
        "read": 0.1,
    }


@pytest.fixture
def sample_agents():
    """Create sample agent profiles."""
    return [
        AgentProfile(
            id=1,
            username="agent_001",
            cluster=1,
            llm=False,
            is_page=0,
            daily_activity_level=3,
            activity_profile="default",
        ),
        AgentProfile(
            id=2,
            username="agent_002",
            cluster=1,
            llm=True,
            is_page=0,
            daily_activity_level=5,
            activity_profile="influencer",
        ),
        AgentProfile(
            id=3,
            username="PageAgent",
            cluster=0,
            llm=False,
            is_page=1,
            daily_activity_level=10,
            activity_profile="page",
        ),
    ]


# ============================================================================
# AgentManager Tests
# ============================================================================


class TestAgentManager:
    """Tests for AgentManager main coordinator."""

    def test_init_creates_components(
        self, temp_config_dir, mock_server, mock_logger, archetype_distribution, actions_likelihood
    ):
        """Test AgentManager initialization creates all components."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        assert manager.population_loader is not None
        assert manager.network_loader is not None
        assert manager.agent_selector is not None
        assert manager.config_path == temp_config_dir
        assert manager.client_id == "test_client"

    def test_sample_agents_by_archetype_delegates(
        self,
        temp_config_dir,
        mock_server,
        mock_logger,
        archetype_distribution,
        actions_likelihood,
        sample_agents,
    ):
        """Test sample_agents_by_archetype delegates to AgentSelector."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        num_active = 2
        with patch.object(manager.agent_selector, "sample_agents_by_archetype") as mock_sample:
            mock_sample.return_value = sample_agents[:num_active]
            result = manager.sample_agents_by_archetype(sample_agents, num_active=num_active)

            mock_sample.assert_called_once_with(sample_agents, num_active)
            assert len(result) == num_active

    def test_create_agents_from_config_delegates(
        self, temp_config_dir, mock_server, mock_logger, archetype_distribution, actions_likelihood
    ):
        """Test create_agents_from_config delegates to PopulationLoader."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        with patch.object(manager.population_loader, "create_agents_from_config") as mock_create:
            mock_create.return_value = []
            agent_config = {"agents": [], "generation_config": {"num_additional_agents": 10}}
            result = manager.create_agents_from_config(agent_config)

            mock_create.assert_called_once_with(agent_config)
            assert isinstance(result, list)


class TestPopulationLoaderCustomFeatures:
    """Targeted tests for structured agent metadata loading."""

    def test_load_predefined_agents_preserves_stubborn_topics_and_custom_features(
        self, temp_config_dir, mock_logger
    ):
        loader = PopulationLoader(
            config_path=temp_config_dir,
            client_id="test_client",
            logger=mock_logger,
        )

        agents = loader._load_predefined_agents(
            [
                {
                    "id": "agent-1",
                    "username": "agent_001",
                    "opinions": {"topic a": 0.8},
                    "stubborn_topics": {"topic a": True},
                    "custom_features": {"Class": "Mage"},
                }
            ]
        )

        assert len(agents) == 1
        assert agents[0].opinions == {"topic a": 0.8}
        assert agents[0].stubborn_topics == {"topic a": True}
        assert agents[0].custom_features == {"Class": "Mage"}

    def test_load_and_create_social_network_delegates(
        self,
        temp_config_dir,
        mock_server,
        mock_logger,
        archetype_distribution,
        actions_likelihood,
        sample_agents,
    ):
        """Test load_and_create_social_network delegates to NetworkLoader."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        network_path = temp_config_dir / "network.csv"

        with patch.object(manager.network_loader, "load_and_create_social_network") as mock_load:
            mock_load.return_value = 0
            manager.load_and_create_social_network(
                network_csv_path=network_path, agent_profiles=sample_agents
            )

            mock_load.assert_called_once_with(network_path, sample_agents)

    def test_determine_agent_type_delegates(
        self,
        temp_config_dir,
        mock_server,
        mock_logger,
        archetype_distribution,
        actions_likelihood,
        sample_agents,
    ):
        """Test determine_agent_type delegates to AgentSelector."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        agent = sample_agents[0]

        with patch.object(manager.agent_selector, "determine_agent_type") as mock_determine:
            mock_determine.return_value = "rule_based"
            result = manager.determine_agent_type(agent)

            mock_determine.assert_called_once_with(agent)
            assert result == "rule_based"


# ============================================================================
# PopulationLoader Tests
# ============================================================================


class TestPopulationLoader:
    """Tests for PopulationLoader."""

    def test_init(self, temp_config_dir, mock_logger):
        """Test PopulationLoader initialization."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        assert loader.config_path == temp_config_dir
        assert loader.client_id == "test_client"
        assert loader.logger == mock_logger

    def test_load_predefined_agents(self, temp_config_dir, mock_logger):
        """Test loading predefined agents from config."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        agents_config = [
            {
                "id": 1,
                "username": "agent_001",
                "cluster": 1,
                "llm": False,
                "daily_activity_level": 3,
                "activity_profile": "default",
            },
            {
                "id": 2,
                "username": "agent_002",
                "cluster": 1,
                "llm": True,
                "daily_activity_level": 5,
                "activity_profile": "influencer",
            },
        ]

        agents = loader._load_predefined_agents(agents_config)

        assert len(agents) == 2
        assert agents[0].username == "agent_001"
        assert agents[0].llm is False
        assert agents[1].username == "agent_002"
        assert agents[1].llm is True

    def test_generate_agents(self, temp_config_dir, mock_logger):
        """Test generating random agents."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        gen_config = {
            "num_additional_agents": 5,
            "cluster_distribution": {"weights": [0.33, 0.33, 0.34]},
            "llm_enabled_probability": 0.1,
            "default_settings": {"password": "test_password", "leaning": "neutral"},
            "age_range": [18, 65],
        }

        agents = loader._generate_agents(gen_config, existing_count=0)

        assert len(agents) == 5
        for agent in agents:
            assert agent.username.startswith("agent_")
            assert agent.cluster in [0, 1, 2]

    def test_create_agents_from_config_with_predefined(self, temp_config_dir, mock_logger):
        """Test creating agents with predefined agents."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        agent_config = {
            "agents": [
                {"id": 1, "username": "agent_001", "cluster": 1, "llm": False},
                {"id": 2, "username": "agent_002", "cluster": 1, "llm": True},
            ],
            "generation_config": {
                "num_additional_agents": 3,
                "cluster_distribution": {"weights": [0.33, 0.33, 0.34]},
                "llm_enabled_probability": 0.1,
            },
        }

        all_agents = loader.create_agents_from_config(agent_config)

        # Should have 2 predefined + 3 generated = 5 total
        assert len(all_agents) == 5

        # First two should be predefined
        assert all_agents[0].username == "agent_001"
        assert all_agents[1].username == "agent_002"

    def test_create_agents_from_config_without_predefined(self, temp_config_dir, mock_logger):
        """Test creating agents without predefined agents."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        agent_config = {
            "generation_config": {
                "num_additional_agents": 3,
                "cluster_distribution": {"weights": [0.33, 0.33, 0.34]},
                "llm_enabled_probability": 0.1,
            }
        }

        all_agents = loader.create_agents_from_config(agent_config)

        # Should have 3 generated agents
        assert len(all_agents) == 3

    def test_validate_and_extract_interests(self, temp_config_dir, mock_logger):
        """Test interest validation and extraction."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        # Valid interests
        topics, counts = loader.validate_and_extract_interests(
            [["tech", "science", "art"], [5, 3, 2]]
        )
        assert topics == ["tech", "science", "art"]
        assert counts == [5, 3, 2]

        # Empty interests
        topics, counts = loader.validate_and_extract_interests([])
        assert topics is None
        assert counts is None

        # None interests
        topics, counts = loader.validate_and_extract_interests(None)
        assert topics is None
        assert counts is None

    def test_save_updated_agent_population(self, temp_config_dir, mock_logger, sample_agents):
        """Test saving updated agent population."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)

        # Create initial agent config file
        import json

        agent_config_file = temp_config_dir / "agent_population.json"
        agent_data = {
            "agents": [{"id": str(agent.id), "username": agent.username} for agent in sample_agents]
        }
        with open(agent_config_file, "w") as f:
            json.dump(agent_data, f)

        # Update interests
        updated_interests = {
            str(sample_agents[0].id): {"topics": ["tech", "science"], "counts": [5, 3]}
        }
        loader.save_updated_agent_population(updated_interests)

        # Verify file was updated
        assert agent_config_file.exists()

        # Verify content
        with open(agent_config_file, "r") as f:
            updated_data = json.load(f)
            assert "agents" in updated_data
            assert updated_data["agents"][0]["interests"] == [["tech", "science"], [5, 3]]


# ============================================================================
# NetworkLoader Tests
# ============================================================================


class TestNetworkLoader:
    """Tests for NetworkLoader."""

    def test_init(self, mock_server, mock_logger):
        """Test NetworkLoader initialization."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)

        assert loader.server == mock_server
        assert loader.client_id == "test_client"
        assert loader.logger == mock_logger

    def test_parse_network_edges(self, temp_config_dir, mock_server, mock_logger, sample_agents):
        """Test parsing network edges from CSV."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)

        network_file = temp_config_dir / "network.csv"
        edges = loader.parse_network_edges(network_file, sample_agents)

        # Should have 2 edges
        assert len(edges) == 2
        # Check that both expected edges exist (order may vary)
        expected_edges = {
            (str(sample_agents[0].id), str(sample_agents[1].id)),  # agent_001 -> agent_002
            (str(sample_agents[1].id), str(sample_agents[0].id)),  # agent_002 -> agent_001
        }
        assert set(edges) == expected_edges

    def test_parse_network_edges_missing_agents(self, temp_config_dir, mock_server, mock_logger):
        """Test parsing network edges when agents are missing."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)

        # Only one agent in profiles
        agent_profiles = [
            AgentProfile(
                id=1,
                username="agent_001",
                cluster=1,
                llm=False,
                is_page=0,
                daily_activity_level=3,
                activity_profile="default",
            )
        ]

        network_file = temp_config_dir / "network.csv"
        edges = loader.parse_network_edges(network_file, agent_profiles)

        # Should have 0 edges (agent_002 not in profiles)
        assert len(edges) == 0

    def test_load_and_create_social_network(
        self, temp_config_dir, mock_server, mock_logger, sample_agents
    ):
        """Test loading and creating social network."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)

        # Mock ray.get to return batch count
        with patch("YSimulator.YClient.agent_management.network_loader.ray.get") as mock_ray_get:
            mock_ray_get.return_value = 2  # 2 edges created successfully

            network_file = temp_config_dir / "network.csv"
            loader.load_and_create_social_network(network_file, sample_agents)

            # Verify server method was called
            mock_server.add_follow_relationships_batch.remote.assert_called()
            mock_logger.info.assert_called()

    def test_load_and_create_social_network_empty_file(
        self, temp_config_dir, mock_server, mock_logger, sample_agents
    ):
        """Test loading network with empty file."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)

        # Create empty network file
        empty_network = temp_config_dir / "empty_network.csv"
        empty_network.write_text("")

        loader.load_and_create_social_network(empty_network, sample_agents)

        # Should log warning about no edges (case-insensitive check)
        warning_calls = mock_logger.warning.call_args_list
        assert any("no edges" in str(c).lower() for c in warning_calls)


# ============================================================================
# AgentSelector Tests
# ============================================================================


class TestAgentSelector:
    """Tests for AgentSelector."""

    def test_init(self, archetype_distribution, actions_likelihood, mock_logger):
        """Test AgentSelector initialization."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        assert selector.archetype_distribution == archetype_distribution
        assert selector.agent_downcast is False
        assert selector.actions_likelihood == actions_likelihood
        assert selector.logger == mock_logger

    def test_sample_agents_by_archetype(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test sampling agents by archetype distribution."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        # Sample from 3 agents
        selected = selector.sample_agents_by_archetype(sample_agents, num_active=2)

        # Should return some agents
        assert len(selected) > 0
        assert len(selected) <= len(sample_agents)

        # All selected should be from original list
        for agent in selected:
            assert agent in sample_agents

    def test_determine_agent_type_llm_agent(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test determining agent type for LLM agent."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        llm_agent = sample_agents[1]  # agent_002 is LLM
        agent_type = selector.determine_agent_type(llm_agent)

        assert agent_type == "llm"

    def test_determine_agent_type_rule_based(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test determining agent type for rule-based agent."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        rule_agent = sample_agents[0]  # agent_001 is not LLM
        agent_type = selector.determine_agent_type(rule_agent)

        assert agent_type == "rule_based"

    def test_determine_agent_type_with_downcast(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test determining agent type with downcast enabled."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=True,  # Enable downcast
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        llm_agent = sample_agents[1]  # agent_002 is LLM

        # With downcast, LLM agents might be downgraded to rule_based
        # (This is a probabilistic test, so we just check it returns valid type)
        agent_type = selector.determine_agent_type(llm_agent)

        assert agent_type in ["llm", "rule_based"]

    def test_select_action(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test selecting action for agent."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        agent = sample_agents[0]
        recent_posts = []
        action = selector.select_action(agent, recent_posts)

        # Should return a tuple (action_type, action_params)
        assert isinstance(action, tuple)

    def test_extract_agent_attrs(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test extracting agent attributes for persona."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        agent = sample_agents[0]

        # Create mock functions
        def mock_validate_interests(interests):
            return None, None

        def mock_is_opinion_enabled():
            return False

        def mock_map_opinion(opinion):
            return "neutral"

        attrs = selector.extract_agent_attrs(
            agent, mock_validate_interests, mock_is_opinion_enabled, mock_map_opinion
        )

        # Should return dict with agent attributes
        assert isinstance(attrs, dict)
        assert "name" in attrs
        assert "age" in attrs
        assert "profession" in attrs
        assert attrs["name"] == "agent_001"
        assert attrs["custom_features"] == {}

    def test_extract_agent_attrs_includes_custom_features(
        self, archetype_distribution, actions_likelihood, mock_logger
    ):
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        agent = AgentProfile(
            id=1,
            username="agent_001",
            custom_features={"Class": "Mage", "Guild": "North"},
        )

        attrs = selector.extract_agent_attrs(
            agent,
            lambda interests: (None, None),
            lambda: False,
            lambda opinion: "neutral",
        )

        assert attrs["custom_features"] == {"Class": "Mage", "Guild": "North"}


# ============================================================================
# Integration Tests
# ============================================================================


class TestAgentManagementIntegration:
    """Integration tests for agent management components."""

    def test_end_to_end_agent_creation(
        self, temp_config_dir, mock_server, mock_logger, archetype_distribution, actions_likelihood
    ):
        """Test end-to-end agent creation flow."""
        # Create AgentManager
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        # Create agents
        agent_config = {
            "agents": [
                {"id": 1, "username": "agent_001", "cluster": 1, "llm": False},
                {"id": 2, "username": "agent_002", "cluster": 1, "llm": True},
            ],
            "generation_config": {
                "num_additional_agents": 3,
                "cluster_distribution": {"weights": [0.33, 0.33, 0.34]},
                "llm_enabled_probability": 0.1,
            },
        }
        all_agents = manager.create_agents_from_config(agent_config)

        assert len(all_agents) == 5

        # Sample agents
        selected = manager.sample_agents_by_archetype(all_agents, num_active=3)
        assert len(selected) > 0

        # Determine agent types
        for agent in selected:
            agent_type = manager.determine_agent_type(agent)
            assert agent_type in ["llm", "rule_based"]

    def test_end_to_end_network_loading(
        self,
        temp_config_dir,
        mock_server,
        mock_logger,
        archetype_distribution,
        actions_likelihood,
        sample_agents,
    ):
        """Test end-to-end network loading flow."""
        # Create AgentManager
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger,
        )

        # Mock ray.get
        with patch("YSimulator.YClient.agent_management.network_loader.ray.get") as mock_ray_get:
            mock_ray_get.return_value = 2

            # Load network
            network_path = temp_config_dir / "network.csv"
            manager.load_and_create_social_network(
                network_csv_path=network_path, agent_profiles=sample_agents
            )

            # Verify server was called
            mock_server.add_follow_relationships_batch.remote.assert_called()
