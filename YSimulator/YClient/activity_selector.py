"""
Activity Selector Module for YClient.

This module handles temporal activity selection including activity profiles,
agent sampling, and action selection for simulation agents.
"""

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import ray

from YSimulator.YClient.classes.ray_models import AgentProfile


def parse_activity_profiles(
    activity_profiles_config: Dict[str, any], logger: logging.Logger
) -> Dict[str, List[int]]:
    """
    Parse activity profiles from configuration.

    Converts string representations like "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23"
    into lists of integers representing active hours.

    Args:
        activity_profiles_config: Dictionary mapping profile names to hour strings
        logger: Logger instance

    Returns:
        dict: Dictionary mapping profile names to lists of active hours (0-23)
    """
    parsed_profiles = {}
    for profile_name, hours_str in activity_profiles_config.items():
        if isinstance(hours_str, str):
            hours = [int(h.strip()) for h in hours_str.split(",")]
            # Validate that all hours are in valid range 0-23
            valid_hours = [h for h in hours if 0 <= h <= 23]
            if len(valid_hours) != len(hours):
                logger.warning(
                    f"Invalid hours found in activity profile '{profile_name}', filtered to valid range 0-23"
                )
            parsed_profiles[profile_name] = valid_hours
        elif isinstance(hours_str, list):
            # Validate list hours as well
            valid_hours = [h for h in hours_str if isinstance(h, int) and 0 <= h <= 23]
            parsed_profiles[profile_name] = valid_hours
        else:
            logger.warning(f"Invalid activity profile format for '{profile_name}': {hours_str}")
            parsed_profiles[profile_name] = list(range(24))  # Default to always active
    return parsed_profiles


def sample_agents_by_archetype(
    available_agents: List[AgentProfile],
    num_active: int,
    archetype_distribution: Dict[str, float],
    logger: logging.Logger,
) -> List[AgentProfile]:
    """
    Sample agents according to archetype distribution.

    Ensures that active agents are composed using the archetype distribution
    from the configuration. If a percentage is > 0, at least one agent of that
    archetype is always selected (if available).

    Args:
        available_agents: List of agents available for selection
        num_active: Total number of agents to activate
        archetype_distribution: Dictionary mapping archetype to percentage
        logger: Logger instance

    Returns:
        list: List of selected agents respecting archetype distribution
    """
    # Group agents by archetype
    agents_by_archetype = {}
    agents_without_archetype = []

    for agent in available_agents:
        archetype = agent.archetype
        # Normalize archetype to lowercase for comparison
        if archetype:
            archetype_key = archetype.lower()
            if archetype_key not in agents_by_archetype:
                agents_by_archetype[archetype_key] = []
            agents_by_archetype[archetype_key].append(agent)
        else:
            # Track agents without archetype separately
            agents_without_archetype.append(agent)

    selected_agents = []
    remaining_slots = num_active

    # Count how many archetypes have distribution > 0 and are available
    available_archetypes = [
        arch
        for arch, pct in archetype_distribution.items()
        if pct > 0 and arch in agents_by_archetype
    ]

    # First pass: ensure at least 1 agent per archetype if distribution > 0
    if num_active >= len(available_archetypes):
        # We have enough slots to give at least 1 to each archetype
        for archetype in available_archetypes:
            if remaining_slots > 0:
                available_for_archetype = agents_by_archetype[archetype]
                if available_for_archetype:
                    selected = random.choice(available_for_archetype)
                    selected_agents.append(selected)
                    agents_by_archetype[archetype].remove(selected)
                    remaining_slots -= 1

        # Second pass: distribute remaining slots according to distribution
        if remaining_slots > 0:
            for archetype, percentage in archetype_distribution.items():
                if archetype in agents_by_archetype and remaining_slots > 0:
                    available_for_archetype = agents_by_archetype[archetype]
                    # Calculate additional agents for this archetype (beyond the guaranteed 1)
                    additional = round(remaining_slots * percentage)
                    num_to_select = min(additional, len(available_for_archetype), remaining_slots)

                    if num_to_select > 0:
                        selected = random.sample(available_for_archetype, k=num_to_select)
                        selected_agents.extend(selected)
                        remaining_slots -= num_to_select
                        for agent in selected:
                            agents_by_archetype[archetype].remove(agent)
    else:
        # Not enough slots for all archetypes, use strict proportional distribution
        for archetype, percentage in archetype_distribution.items():
            if archetype in agents_by_archetype and remaining_slots > 0:
                available_for_archetype = agents_by_archetype[archetype]
                target = round(num_active * percentage)
                num_to_select = min(target, len(available_for_archetype), remaining_slots)

                if num_to_select > 0:
                    selected = random.sample(available_for_archetype, k=num_to_select)
                    selected_agents.extend(selected)
                    remaining_slots -= num_to_select
                    for agent in selected:
                        agents_by_archetype[archetype].remove(agent)

    # Fill any remaining slots with any available agents (including those without archetype)
    if remaining_slots > 0:
        all_remaining = agents_without_archetype.copy()
        for agents_list in agents_by_archetype.values():
            all_remaining.extend(agents_list)

        if all_remaining:
            additional_needed = min(remaining_slots, len(all_remaining))
            if additional_needed > 0:
                additional = random.sample(all_remaining, k=additional_needed)
                selected_agents.extend(additional)

    return selected_agents


def determine_agent_type(agent_profile: AgentProfile) -> str:
    """
    Determine whether an agent uses LLM or rule-based behavior.

    Args:
        agent_profile: Agent profile containing behavior settings

    Returns:
        str: "llm" if agent uses LLM, "rule_based" otherwise
    """
    return "llm" if agent_profile.llm else "rule_based"


def calculate_follow_action_decay(
    agent_joined_round: Optional[str],
    current_day: int,
    current_hour: int,
    server: Any,
    decay_config: Optional[Dict[str, Any]],
    logger: logging.Logger,
) -> float:
    """
    Calculate time-based decay multiplier for follow action probability.

    Primary follow actions (not resulting from other interactions) typically occur
    during the first period of user activity. This function implements a decreasing
    likelihood based on the time (in rounds) since agent registration.

    Args:
        agent_joined_round: Round ID (UUID) when agent joined
        current_day: Current simulation day
        current_hour: Current simulation hour/slot
        server: Ray server actor handle for querying round information
        decay_config: Configuration dictionary with:
            - enabled (bool): Whether decay is enabled
            - decay_function (str): Type of decay ("exponential" or "linear")
            - half_life_rounds (int): For exponential, rounds to reach 50% of initial value
            - decay_rate (float): For linear, reduction per round (0.0-1.0)
            - min_probability_ratio (float): Minimum multiplier (0.0-1.0), default 0.1
        logger: Logger instance

    Returns:
        float: Decay multiplier between min_probability_ratio and 1.0 (1.0 = no decay)

    Example:
        >>> # Exponential decay: agent joined 100 rounds ago, half-life is 50 rounds
        >>> decay = calculate_follow_action_decay(
        ...     joined_round, 5, 10, server, config, logger
        ... )
        >>> # Result: 0.25 (if 2 half-lives passed, so 0.5^2 = 0.25)

    Note:
        All agents are assigned a joined_on round when first registered with the server.
        Initial agents from agent_population.json get the round ID from their first
        registration at simulation start.
    """
    # If decay is not configured or not enabled, return 1.0 (no decay)
    if not decay_config or not decay_config.get("enabled", False):
        return 1.0

    # If agent has no joined_on date, apply no decay
    # This should rarely happen as all agents get joined_on during registration
    if not agent_joined_round:
        logger.debug("Agent has no joined_on round, skipping decay calculation")
        return 1.0

    try:
        # Get agent's join round info from server
        join_round_info = ray.get(server.get_round_info.remote(agent_joined_round))

        if not join_round_info:
            logger.debug(f"Could not find round info for agent join round {agent_joined_round}")
            return 1.0

        join_day = join_round_info.get("day", 0)
        join_hour = join_round_info.get("hour", 0)

        # Calculate elapsed rounds
        # Each day has num_slots_per_day hours/slots
        # We need to get num_slots_per_day from somewhere - let's use 24 as default
        # or get it from decay_config
        slots_per_day = decay_config.get("slots_per_day", 24)

        current_total_rounds = current_day * slots_per_day + current_hour
        join_total_rounds = join_day * slots_per_day + join_hour
        rounds_since_join = max(0, current_total_rounds - join_total_rounds)

        # Get decay parameters
        decay_function = decay_config.get("decay_function", "exponential")
        min_ratio = decay_config.get("min_probability_ratio", 0.1)
        min_ratio = max(0.0, min(1.0, min_ratio))  # Clamp between 0 and 1

        # Calculate decay based on function type
        if decay_function == "exponential":
            half_life = decay_config.get("half_life_rounds", 50)
            if half_life <= 0:
                logger.warning(f"Invalid half_life_rounds {half_life}, using no decay")
                return 1.0

            # Exponential decay: multiplier = 0.5 ^ (rounds_since_join / half_life)
            decay_multiplier = 0.5 ** (rounds_since_join / half_life)

        elif decay_function == "linear":
            decay_rate = decay_config.get("decay_rate", 0.01)
            decay_rate = max(0.0, min(1.0, decay_rate))  # Clamp between 0 and 1

            # Linear decay: multiplier = 1.0 - (decay_rate * rounds_since_join)
            decay_multiplier = 1.0 - (decay_rate * rounds_since_join)

        else:
            logger.warning(f"Unknown decay_function '{decay_function}', using no decay")
            return 1.0

        # Apply minimum ratio constraint
        final_multiplier = max(min_ratio, decay_multiplier)

        logger.debug(
            f"Follow action decay: rounds_since_join={rounds_since_join}, "
            f"function={decay_function}, multiplier={final_multiplier:.3f}"
        )

        return final_multiplier

    except Exception as e:
        logger.warning(f"Error calculating follow action decay: {e}")
        return 1.0


def select_action(
    agent_profile: AgentProfile,
    recent_posts: List[str],
    actions_likelihood: Dict[str, float],
    logger: logging.Logger,
    server: Any = None,
    current_day: int = 0,
    current_hour: int = 0,
    follow_action_decay_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Determine which action an agent should perform.

    This method implements the action selection logic based on:
    - actions_likelihood from simulation config (weighted action selection)
    - Agent's archetype (filters available actions)
    - Availability of recent posts (for comment/reaction actions)
    - Agent type (LLM vs rule-based)
    - Page agents can ONLY perform share_link action
    - Time-based decay for follow actions (based on rounds since registration)

    Args:
        agent_profile: Agent profile containing behavior settings
        recent_posts: List of recent post UUIDs available for reactions
        actions_likelihood: Dictionary mapping action types to weights
        logger: Logger instance
        server: Ray server actor handle (optional, for follow decay calculation)
        current_day: Current simulation day (optional, for follow decay)
        current_hour: Current simulation hour/slot (optional, for follow decay)
        follow_action_decay_config: Configuration for time-based follow action decay

    Returns:
        tuple: (action_type, agent_type, target_post_id) where:
            - action_type: "post", "comment", "read", "image", "share_link", "share", "search", "cast", "follow", or None
            - agent_type: "llm" or "rule_based"
            - target_post_id: UUID string for comment/read/share actions, None for posts/no-action

    Example:
        >>> action_type, agent_type, target = select_action(profile, posts, likelihood, logger)
        >>> if action_type == "post":
        ...     # Generate post action
        >>> elif action_type == "comment":
        ...     # Generate comment to target post
    """
    # Page agents can ONLY perform share_link action
    if agent_profile.is_page == 1:
        agent_type = determine_agent_type(agent_profile)
        return "share_link", agent_type, None

    # Define archetype-to-action mappings
    # This filters which actions are available based on archetype
    # NOTE: Future enhancement - these mappings could be moved to simulation_config.json
    # for easier customization without code changes
    archetype_actions = {
        "validator": [
            "share",
            "read",
            "share_link",
        ],  # Validators react and share content: they are active content consumers
        "broadcaster": [
            "post",
            "image",
            "share",
            "comment",
            "search",
        ],  # Broadcasters post, comment and share contents and images: they are content producers
        "explorer": [
            "follow",
        ],  # Explorers follow and search to grow network: they are lurkers
    }

    # Get archetype-specific action weights with safe fallback
    archetype = agent_profile.archetype

    # If agent has no archetype (archetypes disabled), all actions are available
    if not archetype:
        # Get all action types from actions_likelihood
        available_actions = list(actions_likelihood.keys())
    elif archetype in archetype_actions:
        # Use archetype-specific actions
        available_actions = archetype_actions[archetype]
    else:
        # Unknown archetype - use all available actions as fallback
        available_actions = list(actions_likelihood.keys())

    # Filter actions_likelihood to only include available actions
    filtered_likelihood = {
        action: weight
        for action, weight in actions_likelihood.items()
        if action in available_actions and weight > 0
    }

    # Apply time-based decay to follow action probability if configured
    if "follow" in filtered_likelihood and follow_action_decay_config:
        original_follow_weight = filtered_likelihood["follow"]
        decay_multiplier = calculate_follow_action_decay(
            agent_profile.joined_on,
            current_day,
            current_hour,
            server,
            follow_action_decay_config,
            logger,
        )
        filtered_likelihood["follow"] = original_follow_weight * decay_multiplier

        if decay_multiplier < 1.0:
            logger.debug(
                f"Agent {agent_profile.username}: Applied follow decay {decay_multiplier:.3f}, "
                f"follow weight: {original_follow_weight:.2f} -> {filtered_likelihood['follow']:.2f}"
            )

    # If no valid actions, return no action
    if not filtered_likelihood:
        return None, None, None

    # Select action based on weighted probabilities
    actions = list(filtered_likelihood.keys())
    weights = list(filtered_likelihood.values())

    # random.choices can work directly with unnormalized weights
    selected_action = random.choices(actions, weights=weights)[0]

    # Determine agent type
    agent_type = determine_agent_type(agent_profile)

    # Actions that require a target post
    target_required_actions = ["comment", "read", "share"]

    # If action requires a target but no posts available, return no action
    if selected_action in target_required_actions and not recent_posts:
        return None, None, None

    # Select target post if needed
    target = random.choice(recent_posts) if selected_action in target_required_actions else None

    return selected_action, agent_type, target
