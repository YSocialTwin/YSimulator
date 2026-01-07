"""
Share action generator for YSimulator agents.

This module generates SHARE actions where agents reshare existing posts.
LLM agents add personalized commentary based on their profile and opinions.
Rule-based agents reshare without commentary.
"""

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_llm_share_async, generate_rule_based_share
from YSimulator.YClient.classes.ray_models import AgentProfile


class ShareGenerator(BaseActionGenerator):
    """
    Generator for SHARE actions.

    Handles agents resharing existing posts:
    - LLM agents: Add personalized commentary based on profile and opinions
    - Rule-based agents: Simple reshare without commentary
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a SHARE action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Target post must be provided in context
        target_post = self.context.target
        if not target_post:
            result.metadata["error"] = "no_target_post"
            return result

        # Get post data for opinion updates
        post_data = ray.get(
            self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
        )

        if not post_data:
            result.metadata["error"] = "post_not_found"
            return result

        if agent_type == "llm":
            # LLM: Generate share with personalized commentary
            post_content = post_data.get("tweet", "")
            author_id = post_data.get("user_id")

            # Get author username
            author_name = "Someone"
            if author_id:
                author_user = ray.get(
                    self.context.server.get_user.remote(author_id, client_id=self.context.client_id)
                )
                if author_user:
                    author_name = author_user.get("username", "Someone")

            # Get agent attributes including opinions on post topics
            agent_attrs = self._extract_agent_attrs(agent)

            # Get opinions for the topics in this post
            opinion_info = self._get_opinions_for_post(agent.id, target_post)
            if opinion_info["topics"]:
                # Add opinion information to agent attrs
                agent_attrs["post_topics"] = opinion_info["topics"]
                agent_attrs["post_opinions"] = opinion_info["opinions"]
                agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

            # Fire off async LLM call to generate share commentary
            future = generate_llm_share_async(
                self.context.llm, agent.cluster, post_content, agent_attrs, author_name
            )
            # Store with action_type indicator: (agent_id, cluster_id, target_post_id, future, action_type)
            result.pending_llm_calls.append((agent.id, agent.cluster, target_post, future, "SHARE"))
            result.metadata["author_name"] = author_name
        else:
            # Rule-based: Simple reshare without commentary
            action = generate_rule_based_share(agent.id, agent.cluster, target_post)

            # Calculate opinion updates for the share
            updated_opinions = self._calculate_opinion_updates(agent.id, target_post, post_data)
            if updated_opinions:
                action.updated_opinions = updated_opinions

            result.actions.append(action)
            result.metadata["target_post"] = target_post

        return result
