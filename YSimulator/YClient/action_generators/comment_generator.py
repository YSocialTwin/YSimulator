"""
Comment action generator for YSimulator agents.

This module generates COMMENT actions where agents comment on existing posts.
"""

import random

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_rule_based_comment
from YSimulator.YClient.classes.ray_models import AgentProfile


class CommentGenerator(BaseActionGenerator):
    """
    Generator for COMMENT actions.
    
    Handles both LLM and rule-based agents commenting on posts.
    Uses recommendation systems to find posts to comment on.
    LLM agents generate contextual comments based on post content and thread context.
    Rule-based agents create simple deterministic comments.
    """
    
    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a COMMENT action for the agent.
        
        This method:
        1. Gets recommended posts from the recommendation system
        2. Selects a post to comment on
        3. For LLM agents: fetches post content and fires async comment generation
        4. For rule-based agents: creates simple comment immediately
        
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
            # LLM: Get the post content and ask for a comment
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if post_data:
                post_content = post_data.get("tweet", "")
                author_id = post_data.get("user_id")
                
                # Get author username
                author_name = "Someone"
                if author_id:
                    author_user = ray.get(
                        self.context.server.get_user.remote(
                            author_id, client_id=self.context.client_id
                        )
                    )
                    if author_user:
                        author_name = author_user.get("username", "Someone")
                
                # Get thread context (preceding posts/comments in chronological order)
                max_thread_length = self.context.recsys_settings.get("max_length_thread_reading", 3)
                thread_context = ray.get(
                    self.context.server.get_thread_context.remote(
                        target_post, max_thread_length, client_id=self.context.client_id
                    )
                )
                
                # Get agent attributes including opinions on post topics
                agent_attrs = self._extract_agent_attrs(agent)
                
                # Get opinions for the topics in this post (if opinion dynamics enabled)
                if self._is_opinion_dynamics_enabled():
                    # This would call a helper function from context
                    # For now, we'll skip this to keep it simple
                    pass
                
                # Fire off async LLM call to generate comment
                future = self.context.llm.generate_comment.remote(
                    agent.cluster, post_content, agent_attrs, author_name, thread_context
                )
                # Store: (agent_id, cluster_id, target_post_id, future)
                result.pending_llm_calls.append((agent.id, agent.cluster, target_post, future))
                result.metadata["author_name"] = author_name
        else:
            # Rule-based: Just comment "COMMENT"
            action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
            self._annotate_action(action)
            
            # Note: Opinion dynamics and secondary follow tracking would be handled
            # by the caller (client.py) in the gather phase
            result.actions.append(action)
            result.metadata["rule_based_interaction"] = {
                "agent_id": agent.id,
                "cluster_id": agent.cluster,
                "target_post": target_post,
            }
        
        return result
