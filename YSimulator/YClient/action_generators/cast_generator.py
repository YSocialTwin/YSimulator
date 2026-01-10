"""
Cast action generator for YSimulator agents.

This module generates CAST actions where agents broadcast posts.
CAST is similar to POST but may have different distribution/visibility.
"""

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_llm_post_async, generate_rule_based_post
from YSimulator.YClient.classes.ray_models import AgentProfile


class CastGenerator(BaseActionGenerator):
    """
    Generator for CAST actions.

    Handles both LLM and rule-based agents creating broadcast posts.
    CAST actions are similar to POST but may have broader reach.
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a CAST action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Extract agent attributes for context
        agent_attrs = self._extract_agent_attrs(agent)
        selected_topic = agent_attrs.get("topic")

        if agent_type == "llm":
            # LLM: Fire off async call (similar to POST)
            future = generate_llm_post_async(
                self.context.llm,
                agent.cluster,
                self.context.day,
                self.context.slot,
                agent_attrs,
            )
            # Store pending call: (agent_id, cluster_id, future, selected_topic)
            result.pending_llm_calls.append((agent.id, agent.cluster, future, selected_topic))
            result.metadata["selected_topic"] = selected_topic
        else:
            # Rule-based: Execute immediately (similar to POST)
            action = generate_rule_based_post(agent.id, agent.cluster)
            if selected_topic:
                action.topic = selected_topic
            self._annotate_action(action)
            result.actions.append(action)
            result.metadata["selected_topic"] = selected_topic

        return result
