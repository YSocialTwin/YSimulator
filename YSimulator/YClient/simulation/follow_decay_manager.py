"""
Follow Decay Manager Module for YClient Simulation.

This module handles time-based decay of follow action probability.
Models the realistic behavior where users are most likely to follow others
during their initial period of activity, with decreasing likelihood over time.

Follows the structural pattern established in Phase 2 refactoring.
"""

import logging
from typing import Any, Dict, Optional

import ray


class FollowDecayManager:
    """
    Manages time-based decay for follow action probability.

    Handles:
    - Calculating decay multipliers based on rounds since agent registration
    - Supporting exponential and linear decay functions
    - Enforcing minimum probability constraints
    - Querying round information from server
    """

    def __init__(
        self,
        server,
        decay_config: Dict[str, Any],
        logger: logging.Logger,
    ):
        """
        Initialize the FollowDecayManager.

        Args:
            server: Ray server actor handle for querying round information
            decay_config: Configuration dictionary with:
                - enabled (bool): Whether decay is enabled
                - decay_function (str): Type of decay ("exponential" or "linear")
                - half_life_rounds (int): For exponential, rounds to reach 50%
                - decay_rate (float): For linear, reduction per round
                - min_probability_ratio (float): Minimum multiplier (0.0-1.0)
                - slots_per_day (int): Number of time slots per day
            logger: Logger instance
        """
        self.server = server
        self.decay_config = decay_config
        self.logger = logger
        self.enabled = decay_config.get("enabled", False)

    def get_decay_multiplier(
        self,
        agent_joined_round: Optional[str],
        current_day: int,
        current_hour: int,
    ) -> float:
        """
        Calculate decay multiplier for follow action probability.

        Args:
            agent_joined_round: Round ID (UUID) when agent joined
            current_day: Current simulation day
            current_hour: Current simulation hour/slot

        Returns:
            float: Decay multiplier between min_probability_ratio and 1.0 (1.0 = no decay)

        Example:
            >>> multiplier = manager.get_decay_multiplier("round-123", 5, 10)
            >>> # Returns 0.5 if agent has been active for one half-life period
        """
        # If decay is not enabled, return 1.0 (no decay)
        if not self.enabled:
            return 1.0

        # If agent has no joined_on date, apply no decay
        # This should rarely happen as all agents get joined_on during registration
        if not agent_joined_round:
            self.logger.debug("Agent has no joined_on round, skipping decay calculation")
            return 1.0

        try:
            # Get agent's join round info from server
            join_round_info = ray.get(self.server.get_round_info.remote(agent_joined_round))

            if not join_round_info:
                self.logger.debug(
                    f"Could not find round info for agent join round {agent_joined_round}"
                )
                return 1.0

            join_day = join_round_info.get("day", 0)
            join_hour = join_round_info.get("hour", 0)

            # Calculate elapsed rounds
            slots_per_day = self.decay_config.get("slots_per_day", 24)

            current_total_rounds = current_day * slots_per_day + current_hour
            join_total_rounds = join_day * slots_per_day + join_hour
            rounds_since_join = max(0, current_total_rounds - join_total_rounds)

            # Get decay parameters
            decay_function = self.decay_config.get("decay_function", "exponential")
            min_ratio = self.decay_config.get("min_probability_ratio", 0.1)
            min_ratio = max(0.0, min(1.0, min_ratio))  # Clamp between 0 and 1

            # Calculate decay based on function type
            if decay_function == "exponential":
                half_life = self.decay_config.get("half_life_rounds", 50)
                if half_life <= 0:
                    self.logger.warning(f"Invalid half_life_rounds {half_life}, using no decay")
                    return 1.0

                # Exponential decay: multiplier = 0.5 ^ (rounds_since_join / half_life)
                decay_multiplier = 0.5 ** (rounds_since_join / half_life)

            elif decay_function == "linear":
                decay_rate = self.decay_config.get("decay_rate", 0.01)
                decay_rate = max(0.0, min(1.0, decay_rate))  # Clamp between 0 and 1

                # Linear decay: multiplier = 1.0 - (decay_rate * rounds_since_join)
                decay_multiplier = 1.0 - (decay_rate * rounds_since_join)

            else:
                self.logger.warning(f"Unknown decay_function '{decay_function}', using no decay")
                return 1.0

            # Apply minimum ratio constraint
            final_multiplier = max(min_ratio, decay_multiplier)

            self.logger.debug(
                f"Follow action decay: rounds_since_join={rounds_since_join}, "
                f"function={decay_function}, multiplier={final_multiplier:.3f}"
            )

            return final_multiplier

        except Exception as e:
            self.logger.warning(f"Error calculating follow action decay: {e}")
            return 1.0
