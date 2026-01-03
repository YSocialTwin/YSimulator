"""
Activity Selector Module for YClient.

This module handles temporal activity selection including activity profiles,
agent sampling, and action selection for simulation agents.
"""

import logging
import random
from typing import Dict, List, Optional, Tuple

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


def select_action(
    agent_profile: AgentProfile,
    recent_posts: List[str],
    actions_likelihood: Dict[str, float],
    logger: logging.Logger,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Determine which action an agent should perform.

    This method implements the action selection logic based on:
    - actions_likelihood from simulation config (weighted action selection)
    - Agent's archetype (filters available actions)
    - Availability of recent posts (for comment/reaction actions)
    - Agent type (LLM vs rule-based)
    - Page agents can ONLY perform share_link action

    Args:
        agent_profile: Agent profile containing behavior settings
        recent_posts: List of recent post UUIDs available for reactions
        actions_likelihood: Dictionary mapping action types to weights
        logger: Logger instance

    Returns:
        tuple: (action_type, agent_type, target_post_id) where:
            - action_type: "post", "comment", "read", "image", "share_link", "share", "search", "cast", or None
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
