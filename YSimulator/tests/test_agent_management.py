"""
Tests for Agent Management Module (Phase 6).

This module tests the Phase 6 refactoring: Agent Manager extraction.
Tests cover:
- AgentManager main coordinator
- PopulationLoader for agent creation and persistence
- NetworkLoader for social network management
- AgentSelector for agent selection and type determination
"""

import pytest
import tempfile
import csv
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from YSimulator.YClient.agent_management import (
    AgentManager,
    PopulationLoader,
    NetworkLoader,
    AgentSelector,
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
            writer.writerow(["id", "username", "cluster", "llm", "is_page", "daily_activity_level", "archetype"])
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
        self, temp_config_dir, mock_server, mock_logger, 
        archetype_distribution, actions_likelihood
    ):
        """Test AgentManager initialization creates all components."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        assert manager.population_loader is not None
        assert manager.network_loader is not None
        assert manager.agent_selector is not None
        assert manager.config_path == temp_config_dir
        assert manager.client_id == "test_client"
    
    def test_sample_agents_by_archetype_delegates(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood, sample_agents
    ):
        """Test sample_agents_by_archetype delegates to AgentSelector."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        with patch.object(manager.agent_selector, 'sample_agents_by_archetype') as mock_sample:
            mock_sample.return_value = sample_agents[:2]
            result = manager.sample_agents_by_archetype(sample_agents)
            
            mock_sample.assert_called_once_with(sample_agents)
            assert len(result) == 2
    
    def test_create_agents_from_config_delegates(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood
    ):
        """Test create_agents_from_config delegates to PopulationLoader."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        with patch.object(manager.population_loader, 'create_agents_from_config') as mock_create:
            mock_create.return_value = ([], [])
            result = manager.create_agents_from_config(
                num_agents=10,
                network_file=None,
                num_predefined=2,
                agents_predefined_file="agents_predefined.csv"
            )
            
            mock_create.assert_called_once()
            assert isinstance(result, tuple)
    
    def test_load_and_create_social_network_delegates(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood, sample_agents
    ):
        """Test load_and_create_social_network delegates to NetworkLoader."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        agent_profiles = {agent.username: agent for agent in sample_agents}
        
        with patch.object(manager.network_loader, 'load_and_create_social_network') as mock_load:
            mock_load.return_value = None
            manager.load_and_create_social_network(
                network_file="network.csv",
                agent_profiles=agent_profiles
            )
            
            mock_load.assert_called_once_with("network.csv", agent_profiles)
    
    def test_determine_agent_type_delegates(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood, sample_agents
    ):
        """Test determine_agent_type delegates to AgentSelector."""
        manager = AgentManager(
            config_path=temp_config_dir,
            server=mock_server,
            client_id="test_client",
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        agent = sample_agents[0]
        
        with patch.object(manager.agent_selector, 'determine_agent_type') as mock_determine:
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
        """Test loading predefined agents from CSV."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        agents = loader._load_predefined_agents("agents_predefined.csv", 2)
        
        assert len(agents) == 2
        assert agents[0].username == "agent_001"
        assert agents[0].llm == False
        assert agents[1].username == "agent_002"
        assert agents[1].llm == True
    
    def test_generate_random_agent(self, temp_config_dir, mock_logger):
        """Test generating a random agent."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        agent = loader._generate_random_agent(
            agent_id=100,
            cluster=1,
            archetype="default"
        )
        
        assert agent.id == 100
        assert agent.cluster == 1
        assert agent.username.startswith("agent_")
        assert agent.activity_profile == "default"
    
    def test_create_agents_from_config_with_predefined(
        self, temp_config_dir, mock_logger
    ):
        """Test creating agents with predefined agents."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        all_agents, agent_profiles = loader.create_agents_from_config(
            num_agents=5,
            network_file=None,
            num_predefined=2,
            agents_predefined_file="agents_predefined.csv"
        )
        
        # Should have 2 predefined + 3 generated = 5 total
        assert len(all_agents) == 5
        assert len(agent_profiles) == 5
        
        # First two should be predefined
        assert all_agents[0].username == "agent_001"
        assert all_agents[1].username == "agent_002"
    
    def test_create_agents_from_config_without_predefined(
        self, temp_config_dir, mock_logger
    ):
        """Test creating agents without predefined agents."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        all_agents, agent_profiles = loader.create_agents_from_config(
            num_agents=3,
            network_file=None,
            num_predefined=0,
            agents_predefined_file=None
        )
        
        # Should have 3 generated agents
        assert len(all_agents) == 3
        assert len(agent_profiles) == 3
    
    def test_validate_and_extract_interests(self, temp_config_dir, mock_logger):
        """Test interest validation and extraction."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        # Valid interests
        interests = loader._validate_and_extract_interests("tech,science,art")
        assert interests == ["tech", "science", "art"]
        
        # Empty interests
        interests = loader._validate_and_extract_interests("")
        assert interests == []
        
        # None interests
        interests = loader._validate_and_extract_interests(None)
        assert interests == []
    
    def test_save_updated_agent_population(self, temp_config_dir, mock_logger, sample_agents):
        """Test saving updated agent population."""
        loader = PopulationLoader(temp_config_dir, "test_client", mock_logger)
        
        output_file = "agents_updated.csv"
        loader.save_updated_agent_population(sample_agents, output_file)
        
        # Verify file was created
        output_path = temp_config_dir / output_file
        assert output_path.exists()
        
        # Verify content
        with open(output_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3
            assert rows[0]["username"] == "agent_001"


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
        
        # Create agent_profiles dict
        agent_profiles = {agent.username: agent for agent in sample_agents}
        
        network_file = temp_config_dir / "network.csv"
        edges = loader.parse_network_edges(str(network_file), agent_profiles)
        
        # Should have 2 edges
        assert len(edges) == 2
        assert edges[0] == (1, 2)  # agent_001 -> agent_002
        assert edges[1] == (2, 1)  # agent_002 -> agent_001
    
    def test_parse_network_edges_missing_agents(
        self, temp_config_dir, mock_server, mock_logger
    ):
        """Test parsing network edges when agents are missing."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)
        
        # Only one agent in profiles
        agent_profiles = {
            "agent_001": AgentProfile(
                id=1, username="agent_001", cluster=1, llm=False,
                is_page=0, daily_activity_level=3, activity_profile="default"
            )
        }
        
        network_file = temp_config_dir / "network.csv"
        edges = loader.parse_network_edges(str(network_file), agent_profiles)
        
        # Should have 0 edges (agent_002 not in profiles)
        assert len(edges) == 0
    
    def test_load_and_create_social_network(
        self, temp_config_dir, mock_server, mock_logger, sample_agents
    ):
        """Test loading and creating social network."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)
        
        agent_profiles = {agent.username: agent for agent in sample_agents}
        
        # Mock ray.get to return batch count
        with patch('YSimulator.YClient.agent_management.network_loader.ray.get') as mock_ray_get:
            mock_ray_get.return_value = 2  # 2 edges created successfully
            
            loader.load_and_create_social_network(
                str(temp_config_dir / "network.csv"),
                agent_profiles
            )
            
            # Verify server method was called
            mock_server.add_follow_relationships_batch.remote.assert_called()
            mock_logger.info.assert_called()
    
    def test_load_and_create_social_network_empty_file(
        self, temp_config_dir, mock_server, mock_logger, sample_agents
    ):
        """Test loading network with empty file."""
        loader = NetworkLoader(mock_server, "test_client", mock_logger)
        
        agent_profiles = {agent.username: agent for agent in sample_agents}
        
        # Create empty network file
        empty_network = temp_config_dir / "empty_network.csv"
        empty_network.write_text("")
        
        loader.load_and_create_social_network(
            str(empty_network),
            agent_profiles
        )
        
        # Should log warning about no edges
        assert any("No valid edges" in str(call) for call in mock_logger.warning.call_args_list)


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
            logger=mock_logger
        )
        
        assert selector.archetype_distribution == archetype_distribution
        assert selector.agent_downcast == False
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
            logger=mock_logger
        )
        
        # Sample from 3 agents
        selected = selector.sample_agents_by_archetype(sample_agents)
        
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
            logger=mock_logger
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
            logger=mock_logger
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
            logger=mock_logger
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
            logger=mock_logger
        )
        
        agent = sample_agents[0]
        action = selector.select_action(agent)
        
        # Should return one of the configured actions
        assert action in actions_likelihood.keys()
    
    def test_extract_agent_attrs(
        self, archetype_distribution, actions_likelihood, mock_logger, sample_agents
    ):
        """Test extracting agent attributes for persona."""
        selector = AgentSelector(
            archetype_distribution=archetype_distribution,
            agent_downcast=False,
            actions_likelihood=actions_likelihood,
            logger=mock_logger
        )
        
        agent = sample_agents[0]
        attrs = selector.extract_agent_attrs(agent)
        
        # Should return dict with agent attributes
        assert isinstance(attrs, dict)
        assert "username" in attrs
        assert "cluster" in attrs
        assert "activity_profile" in attrs
        assert attrs["username"] == "agent_001"


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentManagementIntegration:
    """Integration tests for agent management components."""
    
    def test_end_to_end_agent_creation(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood
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
            logger=mock_logger
        )
        
        # Create agents
        all_agents, agent_profiles = manager.create_agents_from_config(
            num_agents=5,
            network_file=None,
            num_predefined=2,
            agents_predefined_file="agents_predefined.csv"
        )
        
        assert len(all_agents) == 5
        assert len(agent_profiles) == 5
        
        # Sample agents
        selected = manager.sample_agents_by_archetype(all_agents)
        assert len(selected) > 0
        
        # Determine agent types
        for agent in selected:
            agent_type = manager.determine_agent_type(agent)
            assert agent_type in ["llm", "rule_based"]
    
    def test_end_to_end_network_loading(
        self, temp_config_dir, mock_server, mock_logger,
        archetype_distribution, actions_likelihood, sample_agents
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
            logger=mock_logger
        )
        
        agent_profiles = {agent.username: agent for agent in sample_agents}
        
        # Mock ray.get
        with patch('YSimulator.YClient.agent_management.network_loader.ray.get') as mock_ray_get:
            mock_ray_get.return_value = 2
            
            # Load network
            manager.load_and_create_social_network(
                network_file=str(temp_config_dir / "network.csv"),
                agent_profiles=agent_profiles
            )
            
            # Verify server was called
            mock_server.add_follow_relationships_batch.remote.assert_called()
