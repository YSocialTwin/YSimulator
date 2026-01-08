"""
Lifecycle Manager Module for YClient Simulation.

This module handles agent lifecycle management including:
- Daily follow evaluations
- Churn evaluation and processing
- New agent creation
- Agent population tracking

Extracted from client.py as part of Phase 2 refactoring.
"""

import logging
import random
import uuid
from typing import Dict, List, Optional, Set

import ray
from faker import Faker

from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YClient.recsys.FollowRecSysRay import (
    AdamicAdarFollowRecSys,
    CommonNeighborsFollowRecSys,
    JaccardFollowRecSys,
    PreferentialAttachmentFollowRecSys,
    RandomFollowRecSys,
)

# Follow recommendation system class mapping
FOLLOW_RECSYS_CLASS_MAP = {
    "random": RandomFollowRecSys,
    "common_neighbors": CommonNeighborsFollowRecSys,
    "jaccard": JaccardFollowRecSys,
    "adamic_adar": AdamicAdarFollowRecSys,
    "preferential_attachment": PreferentialAttachmentFollowRecSys,
    "default": CommonNeighborsFollowRecSys,  # Default to common neighbors algorithm
}


class LifecycleManager:
    """
    Manages agent lifecycle events in the simulation.

    Handles end-of-day operations including:
    - Daily follow actions (based on probability_of_daily_follow)
    - Churn evaluation (removing inactive agents)
    - New agent creation (population growth)
    """

    def __init__(
        self,
        server,
        client_id: str,
        agent_profiles: List[AgentProfile],
        config_path,
        probability_of_daily_follow: float,
        churn_enabled: bool,
        churn_probability: float,
        inactivity_threshold: int,
        churn_percentage: float,
        new_agents_enabled: bool,
        percentage_new_agents: float,
        probability_new_agents: float,
        logger: logging.Logger,
    ):
        """
        Initialize the LifecycleManager.

        Args:
            server: Ray server actor handle
            client_id: Client identifier
            agent_profiles: List of agent profiles (mutable reference)
            config_path: Path to config directory
            probability_of_daily_follow: Probability of daily follow action per agent
            churn_enabled: Whether churn is enabled
            churn_probability: Probability of churning a candidate
            inactivity_threshold: Days of inactivity to be considered for churn
            churn_percentage: Percentage of inactive agents to consider
            new_agents_enabled: Whether new agent creation is enabled
            percentage_new_agents: Percentage of population as new agent slots
            probability_new_agents: Probability of creating agent in each slot
            logger: Logger instance
        """
        self.server = server
        self.client_id = client_id
        self.agent_profiles = agent_profiles
        self.config_path = config_path
        self.probability_of_daily_follow = probability_of_daily_follow
        self.churn_enabled = churn_enabled
        self.churn_probability = churn_probability
        self.inactivity_threshold = inactivity_threshold
        self.churn_percentage = churn_percentage
        self.new_agents_enabled = new_agents_enabled
        self.percentage_new_agents = percentage_new_agents
        self.probability_new_agents = probability_new_agents
        self.logger = logger

    def evaluate_daily_follows(self, active_agent_ids: Set[str], current_day: int) -> List[ActionDTO]:
        """
        Evaluate daily follow actions for agents that were active during the day.

        For each active agent, with probability_of_daily_follow, use the agent's
        follow recommendation system to suggest users and create a follow action.

        Args:
            active_agent_ids: Set of agent IDs that were active during the day
            current_day: Current simulation day

        Returns:
            List of ActionDTO objects for follow actions
        """
        daily_follow_actions = []

        # Get agent profiles for active agents
        active_agents = [agent for agent in self.agent_profiles if agent.id in active_agent_ids]

        for agent in active_agents:
            # With probability, evaluate follow action for this agent
            if random.random() > self.probability_of_daily_follow:
                continue

            # Get agent's follow recommendation strategy
            agent_frecsys_mode = getattr(agent, "frecsys_type", None) or "random"
            frecsys_class = FOLLOW_RECSYS_CLASS_MAP.get(agent_frecsys_mode, RandomFollowRecSys)

            # Initialize follow recsys
            frecsys = frecsys_class(
                n_neighbors=10,  # Request top 10 suggestions
                leaning_bias=1,  # No political bias for daily follows (1 = neutral)
            )

            # Get follow suggestions from server
            try:
                follow_suggestions = frecsys.get_follow_suggestions(
                    self.server, agent.id, client_id=self.client_id
                )

                if follow_suggestions:
                    # Randomly select one candidate to follow
                    target_user_id = random.choice(follow_suggestions)

                    # Create follow action
                    action = ActionDTO(
                        agent.id, agent.cluster, "FOLLOW", target_user_id=target_user_id
                    )
                    daily_follow_actions.append(action)
                    self.logger.debug(
                        f"Daily follow: Agent {agent.id} will follow user {target_user_id}"
                    )

            except Exception as e:
                self.logger.warning(f"Failed to get follow suggestions for agent {agent.id}: {e}")

        return daily_follow_actions

    def evaluate_churn(self) -> Dict[str, int]:
        """
        Evaluate and process churn at the end of a day.

        Delegates to churn_manager module for the actual churn logic.

        Returns:
            Dictionary with churn statistics (inactive_agents, candidates, churned)
        """
        from YSimulator.YClient.churn_manager import evaluate_churn

        return evaluate_churn(
            self.server,
            self.client_id,
            self.agent_profiles,
            self.churn_enabled,
            self.churn_probability,
            self.inactivity_threshold,
            self.churn_percentage,
            self.logger,
        )

    def evaluate_new_agents(self, current_round_id: str) -> int:
        """
        Evaluate and create new agents at end of day.

        Creates new agents by:
        1. Calculating available slots based on non-churned population
        2. For each slot, rolling probability to create agent
        3. Selecting random template from existing agents
        4. Generating realistic name with Faker
        5. Batch registering with server
        6. Updating agent_population.json

        Args:
            current_round_id: Current round UUID

        Returns:
            Number of new agents created
        """
        if not self.new_agents_enabled:
            return 0

        try:
            # Count non-churned agents
            non_churned_agents = [a for a in self.agent_profiles if a.left_on is None]
            num_non_churned = len(non_churned_agents)

            # Calculate available slots
            num_slots = int(num_non_churned * self.percentage_new_agents)

            if num_slots == 0:
                self.logger.info("No new agent slots available")
                return 0

            # Roll probability for each slot
            new_agents = []
            fake = Faker()
            existing_usernames = {a.username for a in self.agent_profiles}

            for _ in range(num_slots):
                if random.random() < self.probability_new_agents:
                    # Select random template
                    template = random.choice(non_churned_agents)

                    # Generate name based on template gender
                    gender = getattr(template, "gender", "male")
                    max_attempts = 10
                    for attempt in range(max_attempts):
                        if gender == "female":
                            name = fake.name_female()
                        else:
                            name = fake.name_male()

                        # Convert to username format
                        username = name.replace(" ", "_").replace(".", "_")

                        if username not in existing_usernames:
                            break
                    else:
                        # Fallback with UUID if can't find unique name
                        username = f"{name.replace(' ', '_')}_{str(uuid.uuid4())[:8]}"

                    # Create new agent from template
                    new_agent = AgentProfile(
                        id=str(uuid.uuid4()),
                        username=username,
                        joined_on=current_round_id,
                        left_on=None,
                        # Copy attributes from template
                        gender=getattr(template, "gender", "male"),
                        archetype=template.archetype,
                        llm=template.llm,
                        round_actions=template.round_actions,
                        daily_activity_level=getattr(template, "daily_activity_level", 1),
                        activity_profile=getattr(template, "activity_profile", "Always On"),
                        recsys_type=getattr(template, "recsys_type", "random"),
                        frecsys_type=getattr(template, "frecsys_type", "random"),
                        # Additional attributes
                        leaning=getattr(template, "leaning", 0),
                        leaning_bias=getattr(template, "leaning_bias", 1),
                        profile=getattr(template, "profile", ""),
                        action_likelihoods=getattr(template, "action_likelihoods", {}),
                    )

                    new_agents.append(new_agent)
                    existing_usernames.add(username)
                    self.logger.info(
                        f"Created new agent: {username} (template: {template.username})"
                    )

            if not new_agents:
                self.logger.info("No new agents created this evaluation")
                return 0

            # Batch register with server
            self.logger.info(f"Batch registering {len(new_agents)} new agents")
            ray.get(self.server.register_agents.remote(new_agents))

            # Add to local agent_profiles
            self.agent_profiles.extend(new_agents)

            # Update agent_population.json for persistence
            from YSimulator.YClient.agent_manager import add_agent_to_population_file

            for agent in new_agents:
                add_agent_to_population_file(
                    agent,
                    self.config_path,
                    self.client_id,
                    self.logger,
                )

            self.logger.info(f"Successfully created and registered {len(new_agents)} new agents")
            return len(new_agents)

        except Exception as e:
            self.logger.error(f"Error evaluating new agents: {e}", exc_info=True)
            return 0

    def save_updated_agent_interests(self):
        """
        Save updated agent interests to agent_population.json at end of day.
        """
        try:
            # Get updated interests from server
            updated_interests = ray.get(self.server.get_updated_agent_interests.remote())
            if updated_interests:
                from YSimulator.YClient.agent_manager import save_updated_agent_population

                save_updated_agent_population(
                    updated_interests,
                    self.config_path,
                    self.client_id,
                    self.logger,
                )
        except Exception as e:
            self.logger.error(
                f"Error saving updated agent interests: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
