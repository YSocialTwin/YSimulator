"""
Unit tests for time-based follow action decay.

Tests the follow action decay functionality that reduces follow action
probability based on time since agent registration.
"""

from unittest.mock import MagicMock, patch

import pytest

from YSimulator.YClient.activity_selector import calculate_follow_action_decay, select_action
from YSimulator.YClient.classes.ray_models import AgentProfile


class TestCalculateFollowActionDecay:
    """Test the calculate_follow_action_decay function."""

    def test_decay_disabled(self):
        """Test that no decay is applied when disabled."""
        decay_config = {"enabled": False}
        result = calculate_follow_action_decay(
            "round-123", 10, 5, None, decay_config, MagicMock()
        )
        assert result == 1.0

    def test_decay_no_config(self):
        """Test that no decay is applied when config is None."""
        result = calculate_follow_action_decay("round-123", 10, 5, None, None, MagicMock())
        assert result == 1.0

    def test_decay_no_joined_round(self):
        """Test that no decay is applied for initial agents without joined_on."""
        decay_config = {"enabled": True}
        result = calculate_follow_action_decay(None, 10, 5, None, decay_config, MagicMock())
        assert result == 1.0

    @patch("ray.get")
    def test_exponential_decay(self, mock_ray_get):
        """Test exponential decay calculation."""
        # Mock server response for round info
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = {"day": 0, "hour": 0}

        decay_config = {
            "enabled": True,
            "decay_function": "exponential",
            "half_life_rounds": 50,
            "min_probability_ratio": 0.1,
            "slots_per_day": 24,
        }

        # Agent joined at day 0, hour 0
        # Current time: day 2, hour 2 = 50 total rounds (2*24 + 2)
        # Elapsed: 50 rounds = 1 half-life
        # Expected multiplier: 0.5^1 = 0.5
        result = calculate_follow_action_decay(
            "round-123", 2, 2, mock_server, decay_config, MagicMock()
        )

        assert result == pytest.approx(0.5, rel=0.01)

    @patch("ray.get")
    def test_exponential_decay_multiple_half_lives(self, mock_ray_get):
        """Test exponential decay with multiple half-lives."""
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = {"day": 0, "hour": 0}

        decay_config = {
            "enabled": True,
            "decay_function": "exponential",
            "half_life_rounds": 50,
            "min_probability_ratio": 0.1,
            "slots_per_day": 24,
        }

        # Elapsed: 100 rounds = 2 half-lives
        # Expected multiplier: 0.5^2 = 0.25
        result = calculate_follow_action_decay(
            "round-123", 4, 4, mock_server, decay_config, MagicMock()
        )

        assert result == pytest.approx(0.25, rel=0.01)

    @patch("ray.get")
    def test_exponential_decay_with_min_ratio(self, mock_ray_get):
        """Test that exponential decay respects min_probability_ratio."""
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = {"day": 0, "hour": 0}

        decay_config = {
            "enabled": True,
            "decay_function": "exponential",
            "half_life_rounds": 10,
            "min_probability_ratio": 0.2,
            "slots_per_day": 24,
        }

        # Elapsed: 100 rounds = 10 half-lives
        # Expected multiplier without min: 0.5^10 ≈ 0.00098 < 0.2
        # Should be clamped to 0.2
        result = calculate_follow_action_decay(
            "round-123", 4, 4, mock_server, decay_config, MagicMock()
        )

        assert result == pytest.approx(0.2, rel=0.01)

    @patch("ray.get")
    def test_linear_decay(self, mock_ray_get):
        """Test linear decay calculation."""
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = {"day": 0, "hour": 0}

        decay_config = {
            "enabled": True,
            "decay_function": "linear",
            "decay_rate": 0.01,
            "min_probability_ratio": 0.1,
            "slots_per_day": 24,
        }

        # Elapsed: 50 rounds
        # Expected multiplier: 1.0 - (0.01 * 50) = 0.5
        result = calculate_follow_action_decay(
            "round-123", 2, 2, mock_server, decay_config, MagicMock()
        )

        assert result == pytest.approx(0.5, rel=0.01)

    @patch("ray.get")
    def test_linear_decay_with_min_ratio(self, mock_ray_get):
        """Test that linear decay respects min_probability_ratio."""
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = {"day": 0, "hour": 0}

        decay_config = {
            "enabled": True,
            "decay_function": "linear",
            "decay_rate": 0.01,
            "min_probability_ratio": 0.2,
            "slots_per_day": 24,
        }

        # Elapsed: 100 rounds
        # Expected multiplier without min: 1.0 - (0.01 * 100) = 0.0 < 0.2
        # Should be clamped to 0.2
        result = calculate_follow_action_decay(
            "round-123", 4, 4, mock_server, decay_config, MagicMock()
        )

        assert result == pytest.approx(0.2, rel=0.01)

    @patch("ray.get")
    def test_decay_with_missing_round_info(self, mock_ray_get):
        """Test graceful handling when round info is not found."""
        mock_server = MagicMock()
        mock_server.get_round_info.remote.return_value = "future"
        mock_ray_get.return_value = None

        decay_config = {
            "enabled": True,
            "decay_function": "exponential",
            "half_life_rounds": 50,
            "slots_per_day": 24,
        }

        result = calculate_follow_action_decay(
            "round-123", 2, 2, mock_server, decay_config, MagicMock()
        )

        # Should return 1.0 (no decay) when round info not found
        assert result == 1.0


class TestSelectActionWithDecay:
    """Test the select_action function with follow action decay."""

    @patch("YSimulator.YClient.activity_selector.calculate_follow_action_decay")
    def test_follow_action_decay_applied(self, mock_decay_fn):
        """Test that decay is applied to follow action weight."""
        # Mock the decay function to return 0.1 (10% of original)
        mock_decay_fn.return_value = 0.1

        agent = AgentProfile(
            id="agent-1",
            username="test_agent",
            cluster=1,
            llm=False,
            is_page=0,
            daily_activity_level=3,
            activity_profile="default",
            archetype=None,  # No archetype, so all actions available
            joined_on="round-123",
        )

        actions_likelihood = {
            "follow": 1.0,  # High follow probability
            "post": 0.1,  # Low post probability
        }

        decay_config = {
            "enabled": True,
            "decay_function": "exponential",
            "half_life_rounds": 10,
            "min_probability_ratio": 0.1,
            "slots_per_day": 24,
        }

        mock_server = MagicMock()
        mock_logger = MagicMock()

        # Call select_action multiple times and check that follow is less likely
        # than without decay (statistical test)
        follow_count = 0
        iterations = 100

        for _ in range(iterations):
            action_type, _, _ = select_action(
                agent,
                [],
                actions_likelihood,
                mock_logger,
                server=mock_server,
                current_day=2,
                current_hour=2,
                follow_action_decay_config=decay_config,
            )
            if action_type == "follow":
                follow_count += 1

        # With decay applied (mocked to return 0.1)
        # Follow weight becomes 1.0 * 0.1 = 0.1, post weight is 0.1
        # Expected probability: 0.1 / (0.1 + 0.1) = 50%
        # Allow some variance due to randomness
        assert (
            30 <= follow_count <= 70
        ), f"Expected ~50% follow rate, got {follow_count}%"

        # Verify decay function was called
        assert mock_decay_fn.called, "Decay function should have been called"

    def test_follow_action_no_decay_when_disabled(self):
        """Test that decay is not applied when disabled in config."""
        agent = AgentProfile(
            id="agent-1",
            username="test_agent",
            cluster=1,
            llm=False,
            is_page=0,
            daily_activity_level=3,
            activity_profile="default",
            archetype="explorer",
            joined_on="round-123",  # Has join time but decay is disabled
        )

        actions_likelihood = {"follow": 1.0, "search": 0.1}

        decay_config = {
            "enabled": False,  # Decay disabled
            "decay_function": "exponential",
            "half_life_rounds": 10,
            "slots_per_day": 24,
        }

        mock_server = MagicMock()
        mock_logger = MagicMock()

        # Call select_action multiple times
        follow_count = 0
        iterations = 100

        for _ in range(iterations):
            action_type, _, _ = select_action(
                agent,
                [],
                actions_likelihood,
                mock_logger,
                server=mock_server,
                current_day=100,
                current_hour=0,
                follow_action_decay_config=decay_config,
            )
            if action_type == "follow":
                follow_count += 1

        # Without decay: follow weight 1.0, search weight 0.1
        # Expected probability: 1.0 / (1.0 + 0.1) ≈ 91%
        # Allow variance, but should be significantly higher than with decay
        assert (
            follow_count >= 80
        ), f"Expected high follow rate when decay disabled, got {follow_count}%"
