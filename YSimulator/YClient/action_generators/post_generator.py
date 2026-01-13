"""
Post action generator for YSimulator agents.

This module generates POST actions where agents create new posts on the platform.
"""

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_llm_post_async, generate_rule_based_post
from YSimulator.YClient.classes.ray_models import AgentProfile


class PostGenerator(BaseActionGenerator):
    """
    Generator for POST actions.

    Handles both LLM and rule-based agents creating posts.
    LLM agents generate contextual content based on their persona and interests.
    Rule-based agents create simple deterministic posts.
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a POST action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Extract agent attributes (interests, opinions, etc.) for context
        agent_attrs = self._extract_agent_attrs(agent)
        selected_topic = agent_attrs.get("topic")  # Get the sampled topic

        if agent_type == "llm":
            # LLM: Fire off async call (don't wait for result yet)
            future = generate_llm_post_async(
                self.context.llm,
                agent.cluster,
                self.context.day,
                self.context.slot,
                agent_attrs,
                agent.id,
            )
            # Store pending call: (agent_id, cluster_id, future, selected_topic, day, slot, agent_attrs)
            # Extended tuple for vLLM batching support - day, slot, agent_attrs are used for batch inference
            result.pending_llm_calls.append((
                agent.id, 
                agent.cluster, 
                future, 
                selected_topic,
                self.context.day,
                self.context.slot,
                agent_attrs
            ))
            result.metadata["selected_topic"] = selected_topic
        else:
            # Rule-based: Execute immediately
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Attach the sampled topic to the action
            if selected_topic:
                action.topic = selected_topic
            # Annotate rule-based post content
            self._annotate_action(action)
            result.actions.append(action)
            result.metadata["selected_topic"] = selected_topic

        return result
