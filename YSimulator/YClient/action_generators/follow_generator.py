"""
Follow action generator for YSimulator agents.

This module generates FOLLOW actions where agents follow other users.
"""

import random

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_llm_follow_async, generate_rule_based_follow
from YSimulator.YClient.classes.ray_models import AgentProfile

# Follow recommendation system class mapping
FOLLOW_RECSYS_CLASS_MAP = {
    "random": "RandomFollowRecSys",
    "common_neighbors": "CommonNeighborsFollowRecSys",
    "jaccard": "JaccardFollowRecSys",
    "adamic_adar": "AdamicAdarFollowRecSys",
    "preferential_attachment": "PreferentialAttachmentFollowRecSys",
    "default": "CommonNeighborsFollowRecSys",
}


class FollowGenerator(BaseActionGenerator):
    """
    Generator for FOLLOW actions.

    Handles both LLM and rule-based agents following other users.
    Uses recommendation systems to suggest follow candidates.
    LLM agents make intelligent decisions about which user to follow.
    Rule-based agents randomly select from suggestions.
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a FOLLOW action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Get follow recommendation system for this agent
        agent_frecsys_mode = getattr(agent, "frecsys_type", None) or "random"

        # Import recommendation system classes
        from YSimulator.YClient.recsys.FollowRecSysRay import (
            AdamicAdarFollowRecSys,
            CommonNeighborsFollowRecSys,
            JaccardFollowRecSys,
            PreferentialAttachmentFollowRecSys,
            RandomFollowRecSys,
        )

        frecsys_class_map = {
            "random": RandomFollowRecSys,
            "common_neighbors": CommonNeighborsFollowRecSys,
            "jaccard": JaccardFollowRecSys,
            "adamic_adar": AdamicAdarFollowRecSys,
            "preferential_attachment": PreferentialAttachmentFollowRecSys,
            "default": CommonNeighborsFollowRecSys,
        }

        frecsys_class = frecsys_class_map.get(agent_frecsys_mode, RandomFollowRecSys)
        frecsys = frecsys_class(n_neighbors=10, leaning_bias=1)

        # Get follow suggestions from server
        suggested_users = frecsys.get_follow_suggestions(
            self.context.server, agent.id, client_id=self.context.client_id
        )

        if not suggested_users:
            # No users available to follow
            result.metadata["reason"] = "no_suggestions"
            return result

        result.metadata["num_suggestions"] = len(suggested_users)

        if agent_type == "llm":
            # LLM: Ask to decide which user to follow
            future = generate_llm_follow_async(self.context.llm, agent.cluster, suggested_users)
            # Store pending call: (agent_id, cluster_id, future)
            result.pending_llm_calls.append((agent.id, agent.cluster, future))
        else:
            # Rule-based: Randomly select one user to follow
            target_user = random.choice(suggested_users)
            action = generate_rule_based_follow(agent.id, agent.cluster, target_user)
            result.actions.append(action)
            result.metadata["target_user"] = target_user

        return result
