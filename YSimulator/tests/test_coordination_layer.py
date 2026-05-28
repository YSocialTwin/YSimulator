"""
Comprehensive unit tests for the coordination layer components.

Tests ClientManager, BarrierHandler, RoundManager, and ArchetypeManager.
"""

import time
from unittest.mock import Mock

import pytest

from YSimulator.YServer.coordination.archetype_manager import ArchetypeManager
from YSimulator.YServer.coordination.barrier_handler import BarrierHandler
from YSimulator.YServer.coordination.client_manager import ClientManager
from YSimulator.YServer.coordination.round_manager import RoundManager
from YSimulator.YServer.database_adapter import DatabaseServiceAdapter
from YSimulator.YServer.services.simulation_service import SimulationService


class TestClientManager:
    """Tests for ClientManager class."""

    @pytest.fixture
    def client_manager(self):
        """Create a ClientManager instance for testing."""
        return ClientManager(timeout_seconds=60)

    def test_register_client_new(self, client_manager):
        """Test registering a new client."""
        result = client_manager.register_client(
            "client1", num_days=5, current_day=1, current_slot=1
        )

        assert result["registered"] is True
        assert result["start_day"] == 1
        assert result["start_slot"] == 1
        assert "client1" in client_manager.registered_clients
        assert "client1" not in client_manager.completed_clients

    def test_register_client_reregistration(self, client_manager):
        """Test re-registering a completed client."""
        # First registration and completion
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_as_completed("client1")

        # Re-register the completed client
        result = client_manager.register_client(
            "client1", num_days=3, current_day=2, current_slot=3
        )

        assert result["registered"] is True
        assert "client1" in client_manager.registered_clients
        assert "client1" not in client_manager.completed_clients

    def test_mark_client_submitted(self, client_manager):
        """Test marking a client as having submitted actions."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_client_submitted("client1")

        assert "client1" in client_manager.submitted_clients

    def test_mark_client_completed(self, client_manager):
        """Test marking a client as completed."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_as_completed("client1")

        assert "client1" in client_manager.completed_clients
        # Note: client remains in registered_clients but is excluded from active_clients
        assert "client1" not in client_manager.get_active_clients()

    def test_clear_submitted_clients(self, client_manager):
        """Test clearing submitted clients for new round."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_client_submitted("client1")

        client_manager.clear_submitted_clients()

        assert len(client_manager.submitted_clients) == 0

    def test_update_heartbeat(self, client_manager):
        """Test updating client heartbeat via register or heartbeat method."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)

        before_time = time.time()
        client_manager.heartbeat("client1")
        after_time = time.time()

        assert "client1" in client_manager.last_heartbeat
        assert before_time <= client_manager.last_heartbeat["client1"] <= after_time

    def test_get_stale_clients(self, client_manager):
        """Test detecting stale clients via check_for_stale_clients."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.register_client("client2", num_days=5, current_day=1, current_slot=1)

        # Set client1 heartbeat to old time, client2 to recent
        client_manager.last_heartbeat["client1"] = time.time() - 120  # 2 minutes ago
        client_manager.last_heartbeat["client2"] = time.time() - 10  # 10 seconds ago

        # check_for_stale_clients automatically marks stale clients as completed
        client_manager.check_for_stale_clients()

        # client1 should be marked as completed (no longer active), client2 should remain active
        assert "client1" not in client_manager.get_active_clients()
        assert "client2" in client_manager.get_active_clients()
        assert "client1" in client_manager.completed_clients

    def test_deregister_client(self, client_manager):
        """Test deregistering a client."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_client_submitted("client1")
        client_manager.heartbeat("client1")

        client_manager.deregister_client("client1")

        assert "client1" not in client_manager.registered_clients
        assert "client1" not in client_manager.submitted_clients
        assert "client1" not in client_manager.last_heartbeat

    def test_get_active_clients(self, client_manager):
        """Test getting active clients (registered but not completed)."""
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.register_client("client2", num_days=5, current_day=1, current_slot=1)
        client_manager.mark_as_completed("client2")

        active = client_manager.get_active_clients()

        assert "client1" in active
        assert "client2" not in active
        assert len(active) == 1


class TestBarrierHandler:
    """Tests for BarrierHandler class."""

    @pytest.fixture
    def barrier_handler(self):
        """Create a BarrierHandler instance for testing."""
        return BarrierHandler()

    def test_should_not_advance_no_active_clients(self, barrier_handler):
        """Test that barrier doesn't advance with no active clients."""
        active_clients = set()
        submitted_clients = set()

        should_advance = barrier_handler.check_barrier_and_should_advance(
            active_clients, submitted_clients
        )

        assert should_advance is False

    def test_should_advance_all_submitted(self, barrier_handler):
        """Test that barrier advances when all active clients have submitted."""
        active_clients = {"client1", "client2", "client3"}
        submitted_clients = {"client1", "client2", "client3"}

        should_advance = barrier_handler.check_barrier_and_should_advance(
            active_clients, submitted_clients
        )

        assert should_advance is True

    def test_should_not_advance_partial_submission(self, barrier_handler):
        """Test that barrier doesn't advance when some clients haven't submitted."""
        active_clients = {"client1", "client2", "client3"}
        submitted_clients = {"client1", "client2"}

        should_advance = barrier_handler.check_barrier_and_should_advance(
            active_clients, submitted_clients
        )

        assert should_advance is False

    def test_should_advance_single_client(self, barrier_handler):
        """Test barrier with single active client."""
        active_clients = {"client1"}
        submitted_clients = {"client1"}

        should_advance = barrier_handler.check_barrier_and_should_advance(
            active_clients, submitted_clients
        )

        assert should_advance is True


class TestRoundManager:
    """Tests for RoundManager class."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database adapter."""
        db = Mock()
        db.use_redis = False
        return db

    @pytest.fixture
    def mock_interest_manager(self):
        """Create a mock interest manager."""
        return Mock()

    @pytest.fixture
    def round_manager(self, mock_db, mock_interest_manager):
        """Create a RoundManager instance for testing."""
        return RoundManager(
            db_adapter=mock_db, interest_manager=mock_interest_manager, visibility_rounds=10
        )

    def test_initialize_first_round(self, round_manager, mock_db):
        """Test initializing the first round."""
        mock_db.get_or_create_round.return_value = "round_1_1"

        round_id = round_manager.initialize_first_round()

        assert round_id == "round_1_1"
        assert round_manager.current_round_id == "round_1_1"
        assert round_manager.day == 1
        assert round_manager.slot == 1
        mock_db.get_or_create_round.assert_called_once()

    def test_initialize_from_persisted_state_restores_latest_round(
        self, round_manager, mock_db, mock_interest_manager
    ):
        """Server restart should resume from the latest persisted round."""
        mock_db.get_latest_round.return_value = {
            "id": "round_15_7",
            "day": 15,
            "hour": 7,
        }

        round_id = round_manager.initialize_from_persisted_state()

        assert round_id == "round_15_7"
        assert round_manager.current_round_id == "round_15_7"
        assert round_manager.day == 15
        assert round_manager.slot == 7
        mock_interest_manager.set_current_round.assert_called_once_with("round_15_7")
        mock_db.get_or_create_round.assert_not_called()

    def test_advance_simulation_to_next_slot(self, round_manager, mock_db):
        """Test advancing to the next slot within the same day."""
        round_manager.day = 1
        round_manager.slot = 5
        round_manager.current_round_id = "round_1_5"
        mock_db.get_or_create_round.return_value = "round_1_6"
        mock_db.consolidate_redis_to_sqlite.return_value = {}
        mock_db.cleanup_old_posts_from_redis.return_value = {}

        result = round_manager.advance_simulation(recompute_interests_callback=None)

        assert result["day"] == 1
        assert result["slot"] == 6
        assert result["day_completed"] is False
        assert round_manager.day == 1
        assert round_manager.slot == 6
        mock_db.get_or_create_round.assert_called_once()

    def test_advance_simulation_to_next_day(self, round_manager, mock_db, mock_interest_manager):
        """Test advancing to the next day."""
        round_manager.day = 1
        round_manager.slot = 24
        round_manager.current_round_id = "round_1_24"
        mock_db.add_round.return_value = "round_2_1"
        mock_db.get_posts.return_value = []
        mock_db.consolidate_redis_to_sqlite.return_value = {}
        mock_db.cleanup_old_posts_from_redis.return_value = {}

        recompute_callback = Mock()

        result = round_manager.advance_simulation(recompute_interests_callback=recompute_callback)

        assert result["day"] == 2
        assert result["slot"] == 1
        assert result["day_completed"] is True
        assert round_manager.day == 2
        assert round_manager.slot == 1
        recompute_callback.assert_called_once()

    def test_day_end_consolidation(self, round_manager, mock_db):
        """Test consolidation of data at end of day."""
        round_manager.day = 1
        round_manager.slot = 24

        mock_db.consolidate_redis_to_sqlite.return_value = {
            "posts": 100,
            "interactions": 50,
            "removed_posts": 10,
            "removed_interactions": 5,
        }
        mock_db.cleanup_old_posts_from_redis.return_value = {}
        mock_db.add_round.return_value = "round_2_1"

        result = round_manager.advance_simulation(recompute_interests_callback=None)

        assert result["day_completed"] is True
        mock_db.consolidate_redis_to_sqlite.assert_called_once()


class TestResumeRoundDelegation:
    """Tests for the service path used when restarting a stopped server."""

    def test_simulation_service_exposes_latest_round_for_resume(self):
        repo = Mock()
        repo.get_latest_round.return_value = {
            "id": "round_26_16",
            "day": 26,
            "hour": 16,
        }

        service = SimulationService(repo)

        assert service.get_latest_round() == {
            "id": "round_26_16",
            "day": 26,
            "hour": 16,
        }
        repo.get_latest_round.assert_called_once_with()

    def test_database_adapter_delegates_latest_round_for_resume(self):
        service = Mock()
        service.get_latest_round.return_value = {
            "id": "round_26_16",
            "day": 26,
            "hour": 16,
        }
        adapter = object.__new__(DatabaseServiceAdapter)
        adapter.simulation_service = service

        assert adapter.get_latest_round() == {
            "id": "round_26_16",
            "day": 26,
            "hour": 16,
        }
        service.get_latest_round.assert_called_once_with()


class TestArchetypeManager:
    """Tests for ArchetypeManager class."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database adapter."""
        db = Mock()
        db.use_redis = False
        return db

    @pytest.fixture
    def archetype_transitions(self):
        """Create sample archetype transition probabilities."""
        return {
            "lurker": {"lurker": 0.8, "poster": 0.15, "commenter": 0.05},
            "poster": {"lurker": 0.1, "poster": 0.7, "commenter": 0.2},
            "commenter": {"lurker": 0.05, "poster": 0.25, "commenter": 0.7},
        }

    @pytest.fixture
    def archetype_manager(self, mock_db, archetype_transitions):
        """Create an ArchetypeManager instance for testing."""
        return ArchetypeManager(
            db_adapter=mock_db, archetypes_enabled=True, archetype_transitions=archetype_transitions
        )

    def test_should_perform_transitions_enabled(self, archetype_manager):
        """Test checking if transitions should be performed."""
        archetype_manager.last_transition_day = 0

        # Should transition after 7 days
        should_transition = archetype_manager.should_perform_transitions(
            current_day=7, transition_interval=7
        )
        assert should_transition is True

        # Should not transition before interval
        should_transition = archetype_manager.should_perform_transitions(
            current_day=5, transition_interval=7
        )
        assert should_transition is False

    def test_should_not_perform_transitions_disabled(self, mock_db, archetype_transitions):
        """Test that transitions are skipped when disabled."""
        manager = ArchetypeManager(
            db_adapter=mock_db,
            archetypes_enabled=False,
            archetype_transitions=archetype_transitions,
        )

        should_transition = manager.should_perform_transitions(
            current_day=10, transition_interval=7
        )
        assert should_transition is False

    def test_perform_transitions(self, archetype_manager, mock_db):
        """Test performing archetype transitions."""
        mock_agents = [
            {"id": "agent1", "archetype": "lurker"},
            {"id": "agent2", "archetype": "poster"},
            {"id": "agent3", "archetype": "commenter"},
        ]
        # Return list - the perform_transitions method will iterate over it
        mock_db.get_all_users.return_value = mock_agents
        mock_db.update_user_archetype.return_value = True

        result = archetype_manager.perform_transitions(current_day=7)

        assert result["total_agents"] == 3
        assert result["transitioned_count"] >= 0
        assert result["error_count"] == 0
        assert archetype_manager.last_transition_day == 7
        mock_db.get_all_users.assert_called_once()

    def test_archetype_transition_logic(self, archetype_manager):
        """Test archetype transition probability logic."""
        # Test that transitions respect configured probabilities
        current_archetype = "lurker"
        possible_targets = list(
            archetype_manager.archetype_transitions.get(current_archetype, {}).keys()
        )

        # Should have valid transitions configured
        assert len(possible_targets) > 0
        assert current_archetype in possible_targets  # Should allow staying same

    def test_transition_probabilities_valid(self, archetype_manager):
        """Test validation of valid transition probabilities."""
        # The probabilities should sum to 1.0 (or close to it within tolerance)
        for archetype, transitions in archetype_manager.archetype_transitions.items():
            prob_sum = sum(transitions.values())
            assert abs(prob_sum - 1.0) < archetype_manager.PROBABILITY_TOLERANCE

    def test_transition_probabilities_invalid(self, mock_db):
        """Test that invalid transition probabilities are handled."""
        invalid_transitions = {
            "lurker": {"lurker": 0.5, "poster": 0.3, "commenter": 0.1}  # Sum is 0.9, not 1.0
        }
        manager = ArchetypeManager(
            db_adapter=mock_db, archetypes_enabled=True, archetype_transitions=invalid_transitions
        )

        # Check that invalid probabilities are detected
        for archetype, transitions in invalid_transitions.items():
            prob_sum = sum(transitions.values())
            # Should not sum to 1.0 within tolerance
            is_invalid = abs(prob_sum - 1.0) >= manager.PROBABILITY_TOLERANCE
            assert is_invalid is True


class TestCoordinationIntegration:
    """Integration tests for coordination components working together."""

    def test_full_simulation_step_workflow(self):
        """Test a complete simulation step with all coordination components."""
        # Setup
        client_manager = ClientManager(timeout_seconds=60)
        barrier_handler = BarrierHandler()
        mock_db = Mock()
        mock_interest_manager = Mock()
        mock_db.use_redis = False
        mock_db.add_round.return_value = "round_1_2"
        mock_db.consolidate_redis_to_sqlite.return_value = {}
        mock_db.cleanup_old_posts_from_redis.return_value = {}

        round_manager = RoundManager(
            db_adapter=mock_db, interest_manager=mock_interest_manager, visibility_rounds=10
        )

        # Register clients
        client_manager.register_client("client1", num_days=5, current_day=1, current_slot=1)
        client_manager.register_client("client2", num_days=5, current_day=1, current_slot=1)

        # Clients submit actions
        client_manager.mark_client_submitted("client1")
        client_manager.mark_client_submitted("client2")

        # Check barrier
        active_clients = client_manager.get_active_clients()
        should_advance = barrier_handler.check_barrier_and_should_advance(
            active_clients, client_manager.submitted_clients
        )

        assert should_advance is True

        # Advance simulation
        client_manager.clear_submitted_clients()
        result = round_manager.advance_simulation(recompute_interests_callback=None)

        assert result["day"] == 1
        assert result["slot"] == 2
        assert len(client_manager.submitted_clients) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
