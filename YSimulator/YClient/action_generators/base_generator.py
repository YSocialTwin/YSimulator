"""
Base action generator interface for YSimulator.

This module defines the abstract base class and supporting data structures
for action generators. All action generators must inherit from BaseActionGenerator
and implement the generate() method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile


@dataclass
class ActionContext:
    """
    Context information needed for action generation.

    This encapsulates all the external state and dependencies that an
    action generator needs to make decisions and generate actions.

    Attributes:
        day: Current simulation day
        slot: Current time slot (hour 0-23)
        recent_posts: List of recent post UUIDs for reactions
        target: Optional target (post UUID, user ID, etc.) from action selection
        server: Ray actor handle for the orchestrator server
        llm: Ray actor handle for LLM service (optional)
        news_service: Ray actor handle for news service (optional)
        logger: Logger instance for debugging and monitoring
        client_id: ID of the simulation client
        round_id: Current round UUID for opinion dynamics tracking
        activity_profiles: Dict mapping profile name to active hours
        actions_likelihood: Dict of action probability settings
        recsys_settings: Dict of recommendation system settings
        opinion_dynamics_config: Dict of opinion dynamics settings (optional)
        extract_agent_attrs_fn: Function to extract agent attributes
        annotate_action_fn: Function to annotate action content
        is_opinion_dynamics_enabled_fn: Function to check if opinion dynamics is enabled
        map_opinion_to_group_fn: Function to map opinion value to group
        infer_page_agent_opinion_fn: Function to infer page agent opinion
        get_opinions_for_post_fn: Function to get agent opinions on post topics
        calculate_opinion_updates_fn: Function to calculate opinion updates from interactions
    """

    day: int
    slot: int
    recent_posts: List[str]
    server: Any
    logger: Any
    client_id: str
    round_id: str

    # Optional dependencies
    target: Optional[Any] = None
    llm: Optional[Any] = None
    news_service: Optional[Any] = None

    # Configuration
    activity_profiles: Dict[str, List[int]] = field(default_factory=dict)
    actions_likelihood: Dict[str, Any] = field(default_factory=dict)
    recsys_settings: Dict[str, Any] = field(default_factory=dict)
    opinion_dynamics_config: Optional[Dict[str, Any]] = None
    memory_manager: Optional[Any] = None

    # Helper functions
    extract_agent_attrs_fn: Optional[Any] = None
    annotate_action_fn: Optional[Any] = None
    is_opinion_dynamics_enabled_fn: Optional[Any] = None
    map_opinion_to_group_fn: Optional[Any] = None
    infer_page_agent_opinion_fn: Optional[Any] = None
    get_opinions_for_post_fn: Optional[Any] = None
    calculate_opinion_updates_fn: Optional[Any] = None


@dataclass
class ActionGeneratorResult:
    """
    Result from an action generator.

    This encapsulates both immediate actions (for rule-based agents)
    and pending LLM calls (for LLM agents) that need to be gathered later.

    Attributes:
        actions: List of immediate ActionDTO objects to be submitted
        pending_llm_calls: List of tuples for async LLM calls to be gathered
                          Format varies by action type but typically includes:
                          (agent_id, cluster_id, future, [optional metadata])
        metadata: Optional metadata about the action generation (for debugging)
    """

    actions: List[ActionDTO] = field(default_factory=list)
    pending_llm_calls: List[tuple] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseActionGenerator(ABC):
    """
    Abstract base class for all action generators.

    Each action generator is responsible for generating actions of a specific type
    (POST, COMMENT, READ, etc.) for both LLM and rule-based agents.

    Subclasses must implement:
    - generate(): Main method to generate actions for an agent
    - can_generate(): Check if this generator can handle the given agent/context
    """

    def __init__(self, context: ActionContext):
        """
        Initialize the action generator.

        Args:
            context: Action context with all dependencies and configuration
        """
        self.context = context

    @abstractmethod
    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate action(s) for the given agent.

        This is the main method that subclasses must implement. It should:
        1. Check if the agent can perform this action
        2. Generate the action based on agent type (llm or rule_based)
        3. Return immediate actions and/or pending LLM calls

        Args:
            agent: Agent profile containing agent attributes
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with actions and/or pending LLM calls
        """

    def can_generate(self, agent: AgentProfile, agent_type: str) -> bool:
        """
        Check if this generator can generate actions for the given agent.

        Default implementation returns True. Subclasses can override to add
        specific constraints (e.g., only page agents can share_link).

        Args:
            agent: Agent profile to check
            agent_type: "llm" or "rule_based"

        Returns:
            bool: True if this generator can handle the agent/context
        """
        return True

    def _extract_agent_attrs(self, agent: AgentProfile) -> Dict[str, Any]:
        """
        Extract agent attributes for dynamic persona building.

        Args:
            agent: Agent profile

        Returns:
            Dict with agent attributes (name, age, interests, opinions, etc.)
        """
        if self.context.extract_agent_attrs_fn:
            return self.context.extract_agent_attrs_fn(agent)
        return {}

    def _annotate_action(self, action: ActionDTO) -> None:
        """
        Annotate action content (e.g., extract topics, entities).

        Args:
            action: Action to annotate
        """
        if self.context.annotate_action_fn:
            self.context.annotate_action_fn(action)

    def _is_opinion_dynamics_enabled(self) -> bool:
        """Check if opinion dynamics is enabled."""
        if self.context.is_opinion_dynamics_enabled_fn:
            return self.context.is_opinion_dynamics_enabled_fn()
        return False

    def _get_opinions_for_post(self, agent_id: str, post_id: str) -> dict:
        """
        Get agent's opinions on the topics discussed in a post.

        Args:
            agent_id: UUID of the agent
            post_id: UUID of the post

        Returns:
            dict: {"topics": [...], "opinions": [...], "opinion_values": [...]}
        """
        if self.context.get_opinions_for_post_fn:
            return self.context.get_opinions_for_post_fn(agent_id, post_id)
        return {"topics": [], "opinions": [], "opinion_values": []}

    def _calculate_opinion_updates(
        self, agent_id: str, parent_post_id: str, parent_post_data: dict
    ):
        """
        Calculate opinion updates when an agent interacts with a post.

        Args:
            agent_id: UUID of the agent
            parent_post_id: UUID of the post
            parent_post_data: Post data dictionary

        Returns:
            Optional[dict]: Mapping of topic_id to new opinion value, or None
        """
        if self.context.calculate_opinion_updates_fn:
            return self.context.calculate_opinion_updates_fn(
                agent_id, parent_post_id, parent_post_data
            )
        return None

    def _apply_post_memory(
        self, agent: AgentProfile, agent_attrs: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.context.memory_manager:
            return agent_attrs
        return self.context.memory_manager.apply_post_memory(
            agent.id, agent_attrs, self.context.day, self.context.slot
        )

    def _apply_reply_memory(
        self,
        agent: AgentProfile,
        agent_attrs: Dict[str, Any],
        *,
        target_post_id: str,
        target_post_data: dict,
        author_name: str,
        thread_context: Optional[List[dict]],
        mode: str = "comment",
    ) -> Dict[str, Any]:
        if not self.context.memory_manager:
            return agent_attrs
        return self.context.memory_manager.apply_reply_memory(
            agent.id,
            agent_attrs,
            target_post_id=target_post_id,
            target_post_data=target_post_data,
            author_name=author_name,
            thread_context=thread_context,
            day=self.context.day,
            slot=self.context.slot,
            mode=mode,
        )

    def _apply_browse_memory(
        self,
        agent: AgentProfile,
        agent_attrs: Dict[str, Any],
        *,
        target_post_id: str,
        target_post_data: dict,
    ) -> Dict[str, Any]:
        if not self.context.memory_manager:
            return agent_attrs
        return self.context.memory_manager.apply_browse_memory(
            agent.id,
            agent_attrs,
            target_post_id=target_post_id,
            target_post_data=target_post_data,
            day=self.context.day,
            slot=self.context.slot,
        )

    def _apply_system_messages(
        self, agent: AgentProfile, agent_attrs: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.context.server:
            return agent_attrs
        try:
            messages = ray.get(
                self.context.server.get_active_system_messages.remote(
                    agent.id,
                    self.context.round_id,
                    client_id=self.context.client_id,
                )
            )
        except Exception:
            return agent_attrs

        if isinstance(messages, list) and messages:
            agent_attrs["system_messages"] = messages
        return agent_attrs
