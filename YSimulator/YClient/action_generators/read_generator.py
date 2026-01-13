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
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile


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
        agent_recsys_mode = getattr(agent, "recsys_type", None) or self.context.recsys_settings.get(
            "recsys_mode", "rchrono"
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

                # Get opinions for the topics in this post
                opinion_info = self._get_opinions_for_post(agent.id, target_post)
                if opinion_info["topics"]:
                    # Add opinion information to agent attrs
                    agent_attrs["post_topics"] = opinion_info["topics"]
                    agent_attrs["post_opinions"] = opinion_info["opinions"]
                    agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

                # Fire off async LLM call to decide reaction
                from YSimulator.YClient.actions.llm_actions import _should_use_vllm_batching
                
                # For vLLM batching: Don't create future, use None as placeholder
                if _should_use_vllm_batching(self.context.llm):
                    future = None  # Batch processor will create batch call
                else:
                    # For Ollama: Create individual future (standard scatter/gather)
                    future = generate_llm_read_async(
                        self.context.llm, agent.cluster, post_content, agent_attrs, agent.id
                    )
                
                # Store with metadata for vLLM batching support
                # Format: (agent_id, cluster_id, target_post_id, future, metadata_dict)
                metadata = {
                    "type": "read",
                    "post_content": post_content,
                    "agent_attrs": agent_attrs,
                }
                result.pending_llm_calls.append((agent.id, agent.cluster, target_post, future, metadata))
        else:
            # Rule-based: Consider opinion when choosing reaction
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if post_data:
                # Get opinions for the topics in this post
                opinion_info = self._get_opinions_for_post(agent.id, target_post)

                # Generate reaction based on opinion if available
                if opinion_info["topics"] and opinion_info["opinion_values"]:
                    # Calculate average opinion
                    avg_opinion = sum(opinion_info["opinion_values"].values()) / len(
                        opinion_info["opinion_values"]
                    )

                    # Choose reaction based on opinion
                    # Higher opinion -> more likely to LIKE, lower -> more likely to express
                    # negative reaction
                    if avg_opinion > 0.6:
                        # Positive opinion - mostly LIKE
                        reaction_type = random.choices(
                            ["LIKE", "LOVE", "IGNORE"], weights=[0.6, 0.3, 0.1]
                        )[0]
                    elif avg_opinion < 0.4:
                        # Negative opinion - more likely to express disagreement or ignore
                        reaction_type = random.choices(
                            ["ANGRY", "SAD", "IGNORE"], weights=[0.4, 0.2, 0.4]
                        )[0]
                    else:
                        # Neutral - balanced reactions
                        reaction_type = random.choices(
                            ["LIKE", "IGNORE", "ANGRY"], weights=[0.4, 0.4, 0.2]
                        )[0]

                    if reaction_type != "IGNORE":
                        action = ActionDTO(
                            agent.id, agent.cluster, reaction_type, target_post_id=target_post
                        )
                        result.actions.append(action)
                        result.metadata["reaction_type"] = reaction_type
                        # Track for secondary follow
                        result.metadata["rule_based_interaction"] = {
                            "agent_id": agent.id,
                            "cluster_id": agent.cluster,
                            "post_author_id": post_data.get("user_id"),
                            "post_content": post_data.get("tweet", ""),
                            "is_llm": False,
                        }
                    else:
                        result.metadata["reaction_type"] = "IGNORE"
                else:
                    # No opinion information, use default rule-based behavior
                    action = generate_rule_based_read(agent.id, agent.cluster, target_post)
                    if action:  # Only add if not IGNORE
                        result.actions.append(action)
                        result.metadata["reaction_type"] = action.action_type
                        # Track for secondary follow (rule-based read)
                        result.metadata["rule_based_interaction"] = {
                            "agent_id": agent.id,
                            "cluster_id": agent.cluster,
                            "post_author_id": post_data.get("user_id"),
                            "post_content": post_data.get("tweet", ""),
                            "is_llm": False,
                        }
                    else:
                        result.metadata["reaction_type"] = "IGNORE"

        return result
