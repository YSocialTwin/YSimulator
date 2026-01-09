"""
Agent Scheduler Module for YClient Simulation.

This module handles agent selection and scheduling for simulation rounds.
Determines which agents should be active in each time slot based on:
- Hourly activity probabilities
- Activity profiles
- Archetype distributions
- Churn status

Extracted from client.py as part of Phase 2 refactoring.
"""

import logging
import random
from typing import Dict, List, Set, Tuple

import ray

from YSimulator.YClient.classes.ray_models import AgentProfile


class AgentScheduler:
    """
    Schedules and selects agents for simulation rounds.

    Handles:
    - Filtering agents by activity profiles and churn status
    - Sampling active agents based on hourly activity
    - Archetype-based agent selection
    - Separating regular agents from page agents
    """

    def __init__(
        self,
        agent_profiles: List[AgentProfile],
        hourly_activity: Dict[int, float],
        activity_profiles: Dict[str, List[int]],
        archetypes_enabled: bool,
        archetype_distribution: Dict,
        churn_enabled: bool,
        server,
        logger: logging.Logger,
    ):
        """
        Initialize the AgentScheduler.

        Args:
            agent_profiles: List of agent profiles
            hourly_activity: Mapping of hour to activity probability
            activity_profiles: Mapping of profile name to active hours
            archetypes_enabled: Whether archetype-based sampling is enabled
            archetype_distribution: Archetype distribution configuration
            churn_enabled: Whether churn is enabled
            server: Ray server actor handle
            logger: Logger instance
        """
        self.agent_profiles = agent_profiles
        self.hourly_activity = hourly_activity
        self.activity_profiles = activity_profiles
        self.archetypes_enabled = archetypes_enabled
        self.archetype_distribution = archetype_distribution
        self.churn_enabled = churn_enabled
        self.server = server
        self.logger = logger
        self._churned_agents_cache = set()
        self._churned_agents_cache_valid = False

    def select_active_agents(self, slot: int) -> Tuple[List[AgentProfile], List[AgentProfile]]:
        """
        Select active agents for a given time slot.

        Filters agents by:
        1. Churn status (exclude churned agents)
        2. Activity profile (must be active during this hour)
        3. Hourly activity probability (for regular agents)

        Args:
            slot: Current time slot (0-23, representing hour of day)

        Returns:
            Tuple of (regular_agents, page_agents)
        """
        # Get list of churned agents from server to filter them out
        churned_agent_ids = self._get_churned_agents()

        # Get hourly activity probability for this slot (default to 0.04 if not specified)
        hourly_prob = self.hourly_activity.get(slot, 0.04)

        # Separate regular agents and page agents
        # Pages are always active during their activity profile hours
        # Filter out churned agents
        regular_agents = []
        page_agents = []

        for agent in self.agent_profiles:
            # Skip churned agents
            if agent.id in churned_agent_ids:
                continue

            profile_name = agent.activity_profile
            active_hours = self.activity_profiles.get(profile_name, list(range(24)))
            if slot in active_hours:
                if agent.is_page == 1:
                    page_agents.append(agent)
                else:
                    regular_agents.append(agent)

        self.logger.info(
            f"Activity sampling: slot={slot}, regular_agents={
                len(regular_agents)}, page_agents={
                len(page_agents)}"
        )
        if page_agents:
            self.logger.info(f"Active page agents: {[p.username for p in page_agents]}")

        # Calculate number of regular agents to activate based on hourly_activity
        # Page agents don't count toward the hourly percentage
        active_regular_agents = []
        if regular_agents:
            num_active = max(1, int(len(regular_agents) * hourly_prob))
            num_active = min(num_active, len(regular_agents))  # Can't exceed available agents

            # Sample active agents from regular agents
            if num_active > 0:
                # If archetypes are enabled, sample according to distribution
                if self.archetypes_enabled and self.archetype_distribution:
                    active_regular_agents = self._sample_agents_by_archetype(
                        regular_agents, num_active
                    )
                else:
                    # Random sampling when archetypes are disabled
                    active_regular_agents = random.sample(regular_agents, k=num_active)

        # Combine regular agents and ALL page agents that are available
        self.logger.info(
            f"Total active agents for this round: {len(active_regular_agents) + len(page_agents)} "
            f"(regular: {len(active_regular_agents)}, pages: {len(page_agents)})"
        )

        return active_regular_agents, page_agents

    def _get_churned_agents(self) -> Set[str]:
        """
        Get list of churned agents, using cache to avoid expensive server calls.

        Returns:
            Set of churned agent IDs
        """
        churned_agent_ids = set()
        if self.churn_enabled:
            try:
                # Refresh cache if invalid or empty
                if not self._churned_agents_cache_valid:
                    churned_agent_ids = set(ray.get(self.server.get_churned_agents.remote()))
                    self._churned_agents_cache = churned_agent_ids
                    self._churned_agents_cache_valid = True
                    if churned_agent_ids:
                        self.logger.info(
                            f"Refreshed churned agents cache: {
                                len(churned_agent_ids)} churned agents"
                        )
                else:
                    # Use cached value
                    churned_agent_ids = self._churned_agents_cache
            except Exception as e:
                self.logger.warning(
                    f"Error getting churned agents: {e}", extra={"extra_data": {"error": str(e)}}
                )
        return churned_agent_ids

    def invalidate_churn_cache(self):
        """
        Invalidate the churned agents cache.
        Should be called after churn evaluation.
        """
        self._churned_agents_cache_valid = False

    def _sample_agents_by_archetype(
        self, agents: List[AgentProfile], num_to_sample: int
    ) -> List[AgentProfile]:
        """
        Sample agents according to archetype distribution.

        Args:
            agents: Pool of agents to sample from
            num_to_sample: Number of agents to sample

        Returns:
            List of sampled agents
        """
        # Group agents by archetype
        agents_by_archetype = {}
        for agent in agents:
            archetype = agent.archetype if agent.archetype else "unknown"
            if archetype not in agents_by_archetype:
                agents_by_archetype[archetype] = []
            agents_by_archetype[archetype].append(agent)

        # Get archetype weights from distribution
        archetype_weights = self.archetype_distribution.get("weights", {})

        # Calculate how many agents to sample from each archetype
        sampled_agents = []
        remaining_to_sample = num_to_sample

        for archetype, weight in archetype_weights.items():
            if remaining_to_sample <= 0:
                break

            agents_in_archetype = agents_by_archetype.get(archetype, [])
            if not agents_in_archetype:
                continue

            # Calculate number to sample from this archetype based on weight
            num_from_archetype = max(1, int(num_to_sample * weight))
            num_from_archetype = min(
                num_from_archetype, len(agents_in_archetype), remaining_to_sample
            )

            # Sample from this archetype
            sampled_from_archetype = random.sample(agents_in_archetype, k=num_from_archetype)
            sampled_agents.extend(sampled_from_archetype)
            remaining_to_sample -= num_from_archetype

        # If we haven't sampled enough (due to rounding or missing archetypes),
        # randomly sample remaining from all available agents
        if remaining_to_sample > 0:
            remaining_agents = [a for a in agents if a not in sampled_agents]
            if remaining_agents:
                additional = random.sample(
                    remaining_agents, k=min(remaining_to_sample, len(remaining_agents))
                )
                sampled_agents.extend(additional)

        return sampled_agents
