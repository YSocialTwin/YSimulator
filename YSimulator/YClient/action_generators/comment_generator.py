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
            CollaborativeItemItem,
            CollaborativeUserUser,
            CommonInterests,
            CommonUserInterests,
            ContentBasedFeatures,
            ContentBasedVector,
            HybridLinearRanker,
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
            "ReverseChrono": ReverseChrono,
            "ReverseChronoPopularity": ReverseChronoPopularity,
            "ReverseChronoFollowers": ReverseChronoFollowers,
            "ReverseChronoFollowersPopularity": ReverseChronoFollowersPopularity,
            "ReverseChronoComments": ReverseChronoComments,
            "CommonInterests": CommonInterests,
            "CommonUserInterests": CommonUserInterests,
            "SimilarUsersReactions": SimilarUsersReact,
            "SimilarUsersPosts": SimilarUsersPosts,
            "CollaborativeUserUser": CollaborativeUserUser,
            "CollaborativeItemItem": CollaborativeItemItem,
            "ContentBasedFeatures": ContentBasedFeatures,
            "ContentBasedVector": ContentBasedVector,
            "HybridLinearRanker": HybridLinearRanker,
            # Legacy support for old naming pattern
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
            # LLM: Get the post content and ask for a comment
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if post_data:
                # Handle None value explicitly - .get() returns None if key exists with None value
                post_content = post_data.get("tweet") or post_data.get("text") or ""

                # Log what we got for debugging
                self.context.logger.debug(
                    f"Post {target_post} data keys: {list(post_data.keys())}, "
                    f"tweet value: {repr(post_data.get('tweet'))}, "
                    f"text value: {repr(post_data.get('text'))}, "
                    f"final content length: {len(post_content) if post_content else 0}"
                )

                # Validate post content is not empty
                if not post_content or not post_content.strip():
                    self.context.logger.warning(
                        f"Skipping comment on post {target_post} - post content is empty or whitespace only. "
                        f"Post data keys: {list(post_data.keys())}, tweet={repr(post_data.get('tweet'))}, "
                        f"text={repr(post_data.get('text'))}"
                    )
                    result.metadata["reason"] = "empty_post_content"
                    return result
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

                # Get opinions for the topics in this post
                opinion_info = self._get_opinions_for_post(agent.id, target_post)
                if opinion_info["topics"]:
                    # Add opinion information to agent attrs
                    agent_attrs["post_topics"] = opinion_info["topics"]
                    agent_attrs["post_opinions"] = opinion_info["opinions"]
                    agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

                # Retrieve memory context for this thread/author for better continuity.
                memory_items = self._fetch_agent_memory(
                    str(agent.id),
                    {
                        "topic": opinion_info["topics"][0] if opinion_info["topics"] else None,
                        "target_user_id": str(author_id) if author_id else None,
                        "thread_id": post_data.get("thread_id"),
                        "action_type": "COMMENT",
                        "max_items": 3,
                    },
                )
                if memory_items:
                    agent_attrs["memory_context"] = [m.get("memory_text", "") for m in memory_items]
                    used_memory_ids = [m.get("memory_id") for m in memory_items if m.get("memory_id")]
                    if used_memory_ids:
                        self._record_memory_usage(str(agent.id), used_memory_ids)
                    result.metadata["memory_items_used"] = len(memory_items)

                # Fire off async LLM call to generate comment
                from YSimulator.YClient.actions.llm_actions import (
                    _get_llm_actor,
                    _should_use_vllm_batching,
                )

                llm_actor = _get_llm_actor(self.context.llm, agent.id)

                # For vLLM batching: Don't create future, use None as placeholder
                if _should_use_vllm_batching(self.context.llm):
                    future = None  # Batch processor will create batch call
                else:
                    # For Ollama: Create individual future (standard scatter/gather)
                    future = llm_actor.generate_comment.remote(
                        agent.cluster, post_content, agent_attrs, author_name, thread_context
                    )

                # Store: (agent_id, cluster_id, target_post_id, future, metadata_dict)
                # Extended tuple for vLLM batching support - metadata includes parameters for batch inference
                metadata = {
                    "type": "comment",
                    "post_content": post_content,
                    "agent_attrs": agent_attrs,
                    "author_name": author_name,
                    "thread_context": thread_context,
                }
                result.pending_llm_calls.append(
                    (agent.id, agent.cluster, target_post, future, metadata)
                )
                result.metadata["author_name"] = author_name
        else:
            # Rule-based: Just comment "COMMENT"
            action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
            self._annotate_action(action)

            # Calculate opinion updates for rule-based comment
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if post_data:
                updated_opinions = self._calculate_opinion_updates(agent.id, target_post, post_data)
                if updated_opinions:
                    action.updated_opinions = updated_opinions

                # Track for secondary follow (rule-based comment)
                result.metadata["rule_based_interaction"] = {
                    "agent_id": agent.id,
                    "cluster_id": agent.cluster,
                    "post_author_id": post_data.get("user_id"),
                    "post_content": post_data.get("tweet") or post_data.get("text") or "",
                    "is_llm": False,
                }

            result.actions.append(action)

        return result
