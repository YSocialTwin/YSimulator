"""
Image action generator for YSimulator agents.

This module generates IMAGE actions where agents post images.
"""

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_image_post_async, generate_rule_based_image_post
from YSimulator.YClient.classes.ray_models import AgentProfile


class ImageGenerator(BaseActionGenerator):
    """
    Generator for IMAGE actions.
    
    Handles both LLM and rule-based agents posting images.
    LLM agents generate contextual image posts with captions.
    Rule-based agents create simple image posts.
    """
    
    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate an IMAGE action for the agent.
        
        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"
        
        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()
        
        # Extract agent attributes for context
        agent_attrs = self._extract_agent_attrs(agent)
        
        if agent_type == "llm":
            # LLM: Fire off async call to generate image post
            future = generate_image_post_async(
                self.context.llm,
                agent.cluster,
                self.context.day,
                self.context.slot,
                agent_attrs,
            )
            # Store pending call: (agent_id, cluster_id, future, image_id=None)
            result.pending_llm_calls.append((agent.id, agent.cluster, future, None))
        else:
            # Rule-based: Create simple image post
            # Use a placeholder image_id (would normally be from image service)
            image_id = "image_placeholder"
            action = generate_rule_based_image_post(agent.id, agent.cluster, image_id)
            self._annotate_action(action)
            result.actions.append(action)
            result.metadata["image_id"] = image_id
        
        return result
