"""
Unit tests for simulation orchestration modules (Phase 2 refactoring).

Tests cover:
- AgentScheduler: Agent selection and activity filtering
- LifecycleManager: Daily follows, churn, new agents
- BatchProcessor: LLM call batching
- RoundExecutor: Per-round execution
- Simulator: Main loop coordination
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from YSimulator.YClient.classes.ray_models import AgentProfile
from YSimulator.YClient.simulation import (
    AgentScheduler,
    BatchProcessor,
    LifecycleManager,
    RoundExecutor,
    Simulator,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def sample_agents():
    """Create sample agent profiles for testing."""
    agents = []
    for i in range(5):
        agent = AgentProfile(
            id=f"agent_{i}",
            username=f"user_{i}",
            llm=(i % 2 == 0),  # Alternate between LLM and rule-based
            cluster=i % 2,
            daily_activity_level=3,
            activity_profile="Always On",
            archetype="creator" if i < 3 else "validator",
            is_page=0,
        )
        agents.append(agent)
    return agents


class TestAgentScheduler:
    """Test AgentScheduler functionality."""

    def test_initialization(self, sample_agents, mock_logger):
        """Test AgentScheduler initialization."""
        scheduler = AgentScheduler(
            agent_profiles=sample_agents,
            hourly_activity={0: 0.1, 12: 0.5},
            activity_profiles={"Always On": list(range(24))},
            archetypes_enabled=False,
            archetype_distribution={},
            churn_enabled=False,
            server=MagicMock(),
            logger=mock_logger,
        )

        assert scheduler.agent_profiles == sample_agents
        assert len(scheduler.hourly_activity) == 2
        assert scheduler.archetypes_enabled is False

    def test_select_active_agents_no_churn(self, sample_agents, mock_logger):
        """Test agent selection when churn is disabled."""
        mock_server = MagicMock()

        scheduler = AgentScheduler(
            agent_profiles=sample_agents,
            hourly_activity={12: 0.5},
            activity_profiles={"Always On": list(range(24))},
            archetypes_enabled=False,
            archetype_distribution={},
            churn_enabled=False,
            server=mock_server,
            logger=mock_logger,
        )

        regular_agents, page_agents = scheduler.select_active_agents(slot=12)

        # All 5 agents are regular (is_page=0)
        assert len(page_agents) == 0
        # Should select some agents based on hourly probability (0.5 = 50%)
        assert len(regular_agents) >= 1

    def test_invalidate_churn_cache(self, sample_agents, mock_logger):
        """Test churn cache invalidation."""
        scheduler = AgentScheduler(
            agent_profiles=sample_agents,
            hourly_activity={},
            activity_profiles={},
            archetypes_enabled=False,
            archetype_distribution={},
            churn_enabled=True,
            server=MagicMock(),
            logger=mock_logger,
        )

        scheduler._churned_agents_cache_valid = True
        scheduler.invalidate_churn_cache()
        assert scheduler._churned_agents_cache_valid is False


class TestLifecycleManager:
    """Test LifecycleManager functionality."""

    def test_initialization(self, sample_agents, mock_logger):
        """Test LifecycleManager initialization."""
        manager = LifecycleManager(
            server=MagicMock(),
            client_id="test_client",
            agent_profiles=sample_agents,
            config_path="/tmp",
            probability_of_daily_follow=0.1,
            churn_enabled=False,
            churn_probability=0.01,
            inactivity_threshold=5,
            churn_percentage=0.1,
            new_agents_enabled=False,
            percentage_new_agents=0.01,
            probability_new_agents=0.01,
            logger=mock_logger,
        )

        assert manager.client_id == "test_client"
        assert manager.probability_of_daily_follow == 0.1
        assert manager.churn_enabled is False

    def test_evaluate_daily_follows_disabled(self, sample_agents, mock_logger):
        """Test daily follows when probability is 0."""
        manager = LifecycleManager(
            server=MagicMock(),
            client_id="test_client",
            agent_profiles=sample_agents,
            config_path="/tmp",
            probability_of_daily_follow=0.0,
            churn_enabled=False,
            churn_probability=0.01,
            inactivity_threshold=5,
            churn_percentage=0.1,
            new_agents_enabled=False,
            percentage_new_agents=0.01,
            probability_new_agents=0.01,
            logger=mock_logger,
        )

        active_agent_ids = {agent.id for agent in sample_agents}
        actions = manager.evaluate_daily_follows(active_agent_ids, current_day=1)

        # With probability 0, no actions should be generated
        assert len(actions) == 0


class TestBatchProcessor:
    """Test BatchProcessor functionality."""

    def test_initialization(self, mock_logger):
        """Test BatchProcessor initialization."""
        processor = BatchProcessor(
            server=MagicMock(),
            client_id="test_client",
            llm=MagicMock(),
            enable_sentiment=True,
            enable_toxicity=False,
            enable_emotions=True,
            perspective_api_key=None,
            logger=mock_logger,
        )

        assert processor.client_id == "test_client"
        assert processor.enable_sentiment is True
        assert processor.enable_toxicity is False

    def test_gather_empty_lists(self, mock_logger):
        """Test gathering with empty pending lists."""
        processor = BatchProcessor(
            server=MagicMock(),
            client_id="test_client",
            llm=MagicMock(),
            enable_sentiment=False,
            enable_toxicity=False,
            enable_emotions=False,
            perspective_api_key=None,
            logger=mock_logger,
        )

        actions = []
        processor.gather_pending_llm_posts([], actions)
        assert len(actions) == 0

        processor.gather_pending_llm_follows([], actions)
        assert len(actions) == 0


class TestRoundExecutor:
    """Test RoundExecutor functionality."""

    def test_initialization(self, sample_agents, mock_logger):
        """Test RoundExecutor initialization."""
        executor = RoundExecutor(
            agent_profiles=sample_agents,
            server=MagicMock(),
            client_id="test_client",
            logger=mock_logger,
            agent_downcast=False,
            actions_likelihood={},
            select_action_fn=MagicMock(),
            determine_agent_type_fn=MagicMock(),
            dispatch_action_with_generator_fn=MagicMock(return_value=([], [], {})),
            process_secondary_follows_fn=MagicMock(),
        )

        assert executor.client_id == "test_client"
        assert len(executor.agent_profiles) == 5


class TestSimulator:
    """Test Simulator functionality."""

    def test_initialization(self, sample_agents, mock_logger):
        """Test Simulator initialization."""
        simulator = Simulator(
            server=MagicMock(),
            client_id="test_client",
            agent_profiles=sample_agents,
            config_path="/tmp",
            num_days=1,
            num_slots_per_day=24,
            heartbeat_interval=5.0,
            agent_scheduler=MagicMock(spec=AgentScheduler),
            batch_processor=MagicMock(spec=BatchProcessor),
            lifecycle_manager=MagicMock(spec=LifecycleManager),
            round_executor=MagicMock(spec=RoundExecutor),
            logger=mock_logger,
            parse_network_edges_fn=MagicMock(),
            load_and_create_social_network_fn=MagicMock(),
            create_action_generator_factory_fn=MagicMock(),
            log_action_fn=MagicMock(),
            log_hourly_summary_fn=MagicMock(),
            log_daily_summary_fn=MagicMock(),
        )

        assert simulator.client_id == "test_client"
        assert simulator.num_days == 1
        assert simulator.num_slots_per_day == 24
        assert len(simulator.agent_profiles) == 5
