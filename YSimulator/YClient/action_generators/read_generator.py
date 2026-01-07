"""
Read action generator for YSimulator agents.

This module generates READ actions where agents discover and react to posts
through the recommendation system.
"""

import random

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_llm_read_async, generate_rule_based_read
from YSimulator.YClient.classes.ray_models import AgentProfile


class ReadGenerator(BaseActionGenerator):
    """
    Generator for READ actions.
    
    Handles agents discovering posts through recommendations and reacting to them.
    LLM agents make nuanced decisions about how to react.
    Rule-based agents randomly choose simple reactions.
    """
    
    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a READ action for the agent.
        
        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"
        
        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()
        
        # Get recommendation system for this agent
        from YSimulator.YClient.recsys import (
            CommonInterests,
            CommonUserInterests,
            RandomOrder,
            ReverseChrono,
            ReverseChronoComments,
            ReverseChronoFollowers,
            ReverseChronoFollowersPopularity,
            ReverseChronoPopularity,
            SimilarUsersPosts,
            SimilarUsersReact,
        )
        
        recsys_class_map = {
            "random": RandomOrder,
            "rchrono": ReverseChrono,
            "rchrono_popularity": ReverseChronoPopularity,
            "rchrono_followers": ReverseChronoFollowers,
            "rchrono_followers_popularity": ReverseChronoFollowersPopularity,
            "rchrono_comments": ReverseChronoComments,
            "common_interests": CommonInterests,
            "common_user_interests": CommonUserInterests,
            "similar_users_react": SimilarUsersReact,
            "similar_users_posts": SimilarUsersPosts,
            "default": ReverseChrono,
        }
        
        # Get agent's recsys mode from config
        agent_recsys_mode = (
            getattr(agent, "recsys_type", None)
            or self.context.recsys_settings.get("recsys_mode", "rchrono")
        )
        recsys_class = recsys_class_map.get(agent_recsys_mode, RandomOrder)
        recsys_n_posts = self.context.recsys_settings.get("recsys_n_posts", 10)
        recsys = recsys_class(n_posts=recsys_n_posts)
        
        # Get recommended posts from server
        recommended_posts = recsys.get_recommendations(
            self.context.server, agent.id, client_id=self.context.client_id
        )
        
        if not recommended_posts:
            result.metadata["reason"] = "no_recommendations"
            return result
        
        # Select one post randomly from recommendations
        target_post = random.choice(recommended_posts)
        result.metadata["target_post"] = target_post
        result.metadata["num_recommendations"] = len(recommended_posts)
        
        if agent_type == "llm":
            # LLM: Get post content and decide reaction
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if post_data:
                post_content = post_data.get("tweet", "")
                
                # Get agent attributes for persona
                agent_attrs = self._extract_agent_attrs(agent)
                
                # Fire off async LLM call to decide reaction
                future = generate_llm_read_async(
                    self.context.llm, agent.cluster, post_content, agent_attrs
                )
                # Store: (agent_id, cluster_id, target_post_id, future)
                result.pending_llm_calls.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Random reaction (LIKE, ANGRY, or IGNORE)
            action = generate_rule_based_read(agent.id, agent.cluster, target_post)
            if action:  # None if IGNORE
                self._annotate_action(action)
                result.actions.append(action)
                result.metadata["reaction_type"] = action.action_type
                result.metadata["rule_based_interaction"] = {
                    "agent_id": agent.id,
                    "cluster_id": agent.cluster,
                    "target_post": target_post,
                }
            else:
                result.metadata["reaction_type"] = "IGNORE"
        
        return result
