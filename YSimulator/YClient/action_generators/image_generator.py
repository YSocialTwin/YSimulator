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
        agent_attrs = self._apply_post_memory(agent, agent_attrs)

        if agent_type == "llm":
            # LLM: Fetch a random image from the server
            try:
                image = ray.get(self.context.server.get_random_image.remote())
                if not image or not image.get("id"):
                    self.context.logger.warning(f"No image available for LLM agent {agent.id}")
                    return result  # Return empty result if no image available

                image_id = image["id"]
                self.context.logger.info(
                    f"LLM agent {agent.id} selected image {image_id} for image post"
                )
            except Exception as e:
                self.context.logger.error(f"Error fetching image for LLM agent {agent.id}: {e}")
                return result  # Return empty result on error

            # Fire off async call to generate image post
            future = generate_image_post_async(
                self.context.llm,
                agent.cluster,
                self.context.day,
                self.context.slot,
                agent_attrs,
            )
            # Store pending call with extended format for vLLM batching support
            # Format: (agent_id, cluster_id, future, topic, day, slot, agent_attrs, image_id)
            # For image posts: topic (4th element) is None and image_id is added as 8th element
            result.pending_llm_calls.append(
                (
                    agent.id,
                    agent.cluster,
                    future,
                    None,  # topic (not applicable for image posts)
                    self.context.day,
                    self.context.slot,
                    agent_attrs,
                    image_id,  # Add image_id as 8th element for LLM agents
                )
            )
        else:
            # Rule-based: Keep as is - use placeholder image_id
            image_id = "image_placeholder"
            action = generate_rule_based_image_post(agent.id, agent.cluster, image_id)
            self._annotate_action(action)
            result.actions.append(action)
            result.metadata["image_id"] = image_id

        return result
