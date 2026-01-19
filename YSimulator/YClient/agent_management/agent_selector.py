"""
Agent Selector for Agent Management.

Handles agent selection logic including archetype-based sampling and action selection.
"""

import logging
import random
from typing import Dict, List, Optional, Tuple

from YSimulator.YClient.classes.ray_models import AgentProfile


class AgentSelector:
    """
    Manages agent selection operations.

    Responsibilities:
    - Sample agents by archetype distribution
    - Determine agent types (LLM vs rule-based)
    - Select actions for agents
    - Extract agent attributes for persona building
    """

    def __init__(
        self,
        archetype_distribution: Dict[str, float],
        agent_downcast: bool,
        actions_likelihood: Dict,
        logger: logging.Logger,
        follow_decay_manager=None,
        current_day: int = 0,
        current_hour: int = 0,
    ):
        """
        Initialize AgentSelector.

        Args:
            archetype_distribution: Distribution weights for archetypes
            agent_downcast: Whether to downcast certain agent types to rule-based
            actions_likelihood: Action probability configuration
            logger: Logger instance
            follow_decay_manager: Optional FollowDecayManager for time-based follow decay
            current_day: Current simulation day (for follow decay)
            current_hour: Current simulation hour (for follow decay)
        """
        self.archetype_distribution = archetype_distribution
        self.agent_downcast = agent_downcast
        self.actions_likelihood = actions_likelihood
        self.logger = logger
        self.follow_decay_manager = follow_decay_manager
        self.current_day = current_day
        self.current_hour = current_hour

    def sample_agents_by_archetype(
        self, available_agents: List[AgentProfile], num_active: int
    ) -> List[AgentProfile]:
        """
        Sample agents according to archetype distribution.
        Delegates to activity_selector module.

        Args:
            available_agents: List of available agent profiles
            num_active: Number of agents to sample

        Returns:
            List of sampled agent profiles
        """
        from YSimulator.YClient.activity_selector import sample_agents_by_archetype

        return sample_agents_by_archetype(
            available_agents, num_active, self.archetype_distribution, self.logger
        )

    def determine_agent_type(self, agent_profile: AgentProfile) -> str:
        """
        Determine the agent type (llm or rule_based) based on profile and downcast settings.

        Args:
            agent_profile: Agent profile containing behavior settings

        Returns:
            "llm" or "rule_based"
        """
        # Start with the agent's configured type
        agent_type = "llm" if agent_profile.llm else "rule_based"

        # Apply agent_downcast logic: if enabled, treat validator and explorer as rule-based
        if self.agent_downcast and agent_profile.archetype:
            archetype_lower = agent_profile.archetype.lower()
            if archetype_lower in ["validator", "explorer"]:
                agent_type = "rule_based"

        return agent_type

    def select_action(self, agent_profile: AgentProfile, recent_posts: list) -> Tuple:
        """
        Determine which action an agent should perform.
        Delegates to activity_selector module.

        Args:
            agent_profile: Agent profile
            recent_posts: List of recent posts for context

        Returns:
            Tuple of (action_type, action_params)
        """
        from YSimulator.YClient.activity_selector import select_action

        return select_action(
            agent_profile,
            recent_posts,
            self.actions_likelihood,
            self.logger,
            follow_decay_manager=self.follow_decay_manager,
            current_day=self.current_day,
            current_hour=self.current_hour,
        )

    def update_round_info(self, current_day: int, current_hour: int):
        """
        Update the current round information for decay calculations.

        Args:
            current_day: Current simulation day
            current_hour: Current simulation hour/slot
        """
        self.current_day = current_day
        self.current_hour = current_hour

    def extract_agent_attrs(
        self,
        agent: AgentProfile,
        validate_and_extract_interests_func,
        is_opinion_dynamics_enabled_func,
        map_opinion_to_group_func,
    ) -> dict:
        """
        Extract agent attributes for dynamic persona building.

        Args:
            agent: AgentProfile object
            validate_and_extract_interests_func: Function to validate interests
            is_opinion_dynamics_enabled_func: Function to check if opinion dynamics enabled
            map_opinion_to_group_func: Function to map opinion values to groups

        Returns:
            Dictionary of agent attributes for persona template
        """
        # Sample a topic from agent's interests if available
        selected_topic = None
        topics, counts = validate_and_extract_interests_func(agent.interests)
        
        # DEBUG: Log if agent has no interests
        if not topics or not counts:
            logger.warning(
                f"Agent {agent.username} (ID: {agent.id}) has no interests defined. "
                f"Interests: {agent.interests}. Posts will be generic without topics."
            )
        elif topics and counts:
            # Weight topics by their interaction counts
            selected_topic = random.choices(topics, weights=counts, k=1)[0]
            logger.debug(
                f"Sampled topic '{selected_topic}' for agent {agent.username} from interests: {topics}"
            )

        # Get opinion on the selected topic if available
        topic_opinion = None
        topic_opinion_label = None
        if (
            is_opinion_dynamics_enabled_func()
            and selected_topic
            and agent.opinions
            and selected_topic in agent.opinions
        ):
            topic_opinion = agent.opinions[selected_topic]
            topic_opinion_label = map_opinion_to_group_func(topic_opinion)

        attrs = {
            "name": agent.username,
            "age": agent.age if agent.age else "unknown",
            "gender": agent.gender if agent.gender else "person",
            "nationality": agent.nationality if agent.nationality else "citizen",
            "profession": agent.profession if agent.profession else "individual",
            "political_leaning": agent.leaning if agent.leaning else "neutral",
            "oe": agent.oe if agent.oe else "average in openness",
            "co": agent.co if agent.co else "average in conscientiousness",
            "ex": agent.ex if agent.ex else "average in extraversion",
            "ag": agent.ag if agent.ag else "average in agreeableness",
            "ne": agent.ne if agent.ne else "average in neuroticism",
            "toxicity": agent.toxicity if agent.toxicity and agent.toxicity != "" else "no",
            "topic": selected_topic,
        }

        # Add opinion information if available
        if topic_opinion is not None and topic_opinion_label:
            attrs["topic_opinion"] = topic_opinion_label
            attrs["topic_opinion_value"] = topic_opinion

        return attrs
