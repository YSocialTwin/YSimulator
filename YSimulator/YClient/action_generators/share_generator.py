"""
Share action generator for YSimulator agents.

This module generates SHARE actions where agents reshare existing posts.

Note: LLM-based SHARE with custom commentary is not yet implemented.
Currently, LLM agents fall back to rule-based sharing behavior.
"""

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
        
        if agent_type == "llm":
            # TODO: Implement LLM share with commentary in future enhancement
            # For now, use rule-based approach
            self.context.logger.warning(
                f"LLM SHARE not yet implemented for agent {agent.username}, using rule-based"
            )
        
        # Generate rule-based share action
        action = generate_rule_based_share(agent.id, agent.cluster, target_post)
        result.actions.append(action)
        result.metadata["target_post"] = target_post
        
        return result
