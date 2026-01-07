"""
Share action generator for YSimulator agents.

This module generates SHARE actions where agents reshare existing posts.

Note: LLM-based SHARE with custom commentary is not yet implemented.
Currently, LLM agents fall back to rule-based sharing behavior.
"""

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_rule_based_share
from YSimulator.YClient.classes.ray_models import AgentProfile


class ShareGenerator(BaseActionGenerator):
    """
    Generator for SHARE actions.

    Handles agents resharing existing posts with optional commentary.
    Currently supports rule-based agents (LLM version to be added).
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a SHARE action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action
        """
        result = ActionGeneratorResult()

        # Target post must be provided in context
        target_post = self.context.target
        if not target_post:
            result.metadata["error"] = "no_target_post"
            return result

        # For now, only rule-based agents share (matches original implementation)
        # LLM share with commentary is not implemented - silently skip for LLM agents
        if agent_type != "rule_based":
            result.metadata["skipped"] = True
            result.metadata["reason"] = "llm_share_not_implemented"
            return result

        # Generate rule-based share action
        action = generate_rule_based_share(agent.id, agent.cluster, target_post)

        # Calculate opinion updates for the share
        post_data = ray.get(
            self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
        )
        if post_data:
            updated_opinions = self._calculate_opinion_updates(agent.id, target_post, post_data)
            if updated_opinions:
                action.updated_opinions = updated_opinions

        result.actions.append(action)
        result.metadata["target_post"] = target_post

        return result
