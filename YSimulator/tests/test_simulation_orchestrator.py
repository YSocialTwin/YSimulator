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
from pathlib import Path
from types import SimpleNamespace
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

    def test_select_active_agents_promotes_agents_with_pending_mentions(
        self, sample_agents, mock_logger
    ):
        """Agents with pending mentions should be added even if not sampled by hourly activity."""
        mock_server = MagicMock()
        mock_server.get_users_with_unreplied_mentions.remote = MagicMock(return_value=["agent_4"])

        scheduler = AgentScheduler(
            agent_profiles=sample_agents,
            hourly_activity={12: 0.2},
            activity_profiles={"Always On": list(range(24))},
            archetypes_enabled=False,
            archetype_distribution={},
            churn_enabled=False,
            server=mock_server,
            logger=mock_logger,
        )

        with patch(
            "YSimulator.YClient.simulation.agent_scheduler.ray.get",
            side_effect=lambda value: value,
        ), patch(
            "YSimulator.YClient.simulation.agent_scheduler.random.sample",
            return_value=[sample_agents[0]],
        ):
            regular_agents, page_agents = scheduler.select_active_agents(slot=12)

        assert len(page_agents) == 0
        active_ids = {agent.id for agent in regular_agents}
        assert "agent_0" in active_ids
        assert "agent_4" in active_ids


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
        )

        assert executor.client_id == "test_client"

    def test_execute_round_respects_stress_reward_activity_multiplier(
        self, sample_agents, mock_logger
    ):
        sample_agents[0].daily_activity_level = 4
        setattr(sample_agents[0], "stress_reward_activity_multiplier", 0.25)

        select_action = MagicMock(return_value=("post", "rule_based", None))
        determine_agent_type = MagicMock(return_value="rule_based")
        dispatch = MagicMock(return_value=([], [], {}))

        executor = RoundExecutor(
            agent_profiles=sample_agents,
            server=MagicMock(),
            client_id="test_client",
            logger=mock_logger,
            agent_downcast=False,
            actions_likelihood={},
            select_action_fn=select_action,
            determine_agent_type_fn=determine_agent_type,
            dispatch_action_with_generator_fn=dispatch,
        )

        actions, pending_posts, pending_reactions, pending_follows, rb = executor.execute_round(
            active_agents=[sample_agents[0]],
            recent_posts=[],
            action_generator_factory=MagicMock(),
        )

        assert actions == []
        assert pending_posts == []
        assert pending_reactions == []
        assert pending_follows == []
        assert rb == []
        assert select_action.call_count == 1
        assert len(executor.agent_profiles) == 5

    def test_execute_round_keeps_active_page_agents_always_posting(
        self, sample_agents, mock_logger
    ):
        page_agent = sample_agents[0]
        page_agent.is_page = 1
        page_agent.daily_activity_level = 1

        select_action = MagicMock(return_value=("share_link", "llm", None))
        determine_agent_type = MagicMock(return_value="llm")

        def dispatch(action_type, agent, agent_type, target):
            if action_type == "reply":
                return [], [], {}
            return [], [("pending",)], {}

        executor = RoundExecutor(
            agent_profiles=sample_agents,
            server=MagicMock(),
            client_id="test_client",
            logger=mock_logger,
            agent_downcast=False,
            actions_likelihood={},
            select_action_fn=select_action,
            determine_agent_type_fn=determine_agent_type,
            dispatch_action_with_generator_fn=dispatch,
        )

        actions, pending_posts, pending_reactions, pending_follows, rb = executor.execute_round(
            active_agents=[page_agent],
            recent_posts=[],
            action_generator_factory=MagicMock(),
        )

        assert actions == []
        assert pending_posts == [("pending",)]
        assert pending_reactions == []
        assert pending_follows == []
        assert rb == []
        assert select_action.call_count == 1


class TestSimulator:
    """Test Simulator functionality."""

    def test_initialization(self, sample_agents, mock_logger):
        """Test Simulator initialization."""
        from YSimulator.YClient.simulation.secondary_follow_processor import (
            SecondaryFollowProcessor,
        )

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
            secondary_follow_processor=MagicMock(spec=SecondaryFollowProcessor),
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

    def test_run_does_not_mark_client_completed_after_exception(self, sample_agents, mock_logger):
        from YSimulator.YClient.simulation.secondary_follow_processor import (
            SecondaryFollowProcessor,
        )

        server = MagicMock()
        server.register_agents.remote = MagicMock(return_value={"registered": 5})
        server.register_client.remote = MagicMock(
            return_value={"registered": True, "start_day": 1, "start_slot": 0}
        )
        server.get_instruction.remote = MagicMock(
            return_value=SimpleNamespace(status="RUN", day=1, slot=0, recent_post_ids=[])
        )
        server.complete_client.remote = MagicMock(return_value=True)
        server.heartbeat.remote = MagicMock(return_value=True)

        simulator = Simulator(
            server=server,
            client_id="test_client",
            agent_profiles=sample_agents,
            config_path=Path("/tmp"),
            num_days=-1,
            num_slots_per_day=24,
            heartbeat_interval=5.0,
            agent_scheduler=MagicMock(spec=AgentScheduler),
            batch_processor=MagicMock(spec=BatchProcessor),
            lifecycle_manager=MagicMock(spec=LifecycleManager),
            round_executor=MagicMock(spec=RoundExecutor),
            secondary_follow_processor=MagicMock(spec=SecondaryFollowProcessor),
            logger=mock_logger,
            parse_network_edges_fn=MagicMock(return_value=[]),
            load_and_create_social_network_fn=MagicMock(),
            create_action_generator_factory_fn=MagicMock(),
            log_action_fn=MagicMock(),
            log_hourly_summary_fn=MagicMock(),
            log_daily_summary_fn=MagicMock(),
        )
        simulator._simulate_round = MagicMock(side_effect=RuntimeError("boom"))

        with patch(
            "YSimulator.YClient.simulation.simulator.ray.get", side_effect=lambda value: value
        ):
            with pytest.raises(RuntimeError, match="boom"):
                simulator.run(calculate_opinion_updates_fn=MagicMock())

        server.complete_client.remote.assert_not_called()
