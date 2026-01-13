"""
Search action generator for YSimulator agents.

This module generates SEARCH actions where agents search for posts on topics
of interest and then engage with them (comment, share, or react).
"""

import random

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import (
    generate_llm_search_action_async,
    generate_rule_based_comment,
    generate_rule_based_share,
)
from YSimulator.YClient.actions.llm_actions import _should_use_vllm_batching
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile

# Basic reactions for rule-based agents
BASIC_REACTIONS = ["LIKE", "ANGRY"]


class SearchGenerator(BaseActionGenerator):
    """
    Generator for SEARCH actions.

    Handles agents searching for posts on topics of interest and engaging with them.
    The search process:
    1. Sample a topic from agent's interests
    2. Search for recent posts on that topic
    3. Select one post from search results
    4. Decide action: comment, share, or react
    5. Execute the chosen engagement action
    """

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a SEARCH action for the agent.

        Args:
            agent: Agent profile
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Sample a topic from agent's interests
        agent_attrs = self._extract_agent_attrs(agent)
        selected_topic = agent_attrs.get("topic")

        if not selected_topic:
            result.metadata["reason"] = "no_topics"
            return result

        result.metadata["selected_topic"] = selected_topic

        # Get topic_id from topic name
        try:
            topic_id = ray.get(self.context.server.get_topic_id_by_name.remote(selected_topic))
            if not topic_id:
                result.metadata["reason"] = "topic_not_found"
                return result
        except Exception as e:
            result.metadata["reason"] = "topic_id_error"
            result.metadata["error"] = str(e)
            return result

        result.metadata["topic_id"] = topic_id

        # Search for posts on this topic (up to 10 recent posts from other users)
        try:
            found_posts = ray.get(
                self.context.server.search_posts_by_topic.remote(
                    topic_id, agent.id, limit=10, client_id=self.context.client_id
                )
            )
        except Exception as e:
            result.metadata["reason"] = "search_error"
            result.metadata["error"] = str(e)
            return result

        if not found_posts:
            result.metadata["reason"] = "no_posts_found"
            return result

        result.metadata["posts_found"] = len(found_posts)

        # Randomly sample one post from the found posts
        target_post = random.choice(found_posts)
        result.metadata["target_post"] = target_post

        # Get the post content
        try:
            post_data = ray.get(
                self.context.server.get_post.remote(target_post, client_id=self.context.client_id)
            )
            if not post_data:
                result.metadata["reason"] = "post_not_found"
                return result
            post_content = post_data.get("tweet", "")
            post_author_id = post_data.get("user_id", "unknown")
        except Exception as e:
            result.metadata["reason"] = "post_fetch_error"
            result.metadata["error"] = str(e)
            return result

        result.metadata["post_author_id"] = post_author_id

        if agent_type == "llm":
            # LLM: Ask LLM to decide which action to perform (comment/share/react)
            # Get opinions for the topics in this post
            opinion_info = self._get_opinions_for_post(agent.id, target_post)
            if opinion_info["topics"]:
                # Add opinion information to agent attrs
                agent_attrs["post_topics"] = opinion_info["topics"]
                agent_attrs["post_opinions"] = opinion_info["opinions"]
                agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

            # Check if vLLM batching should be used
            if _should_use_vllm_batching(self.context.llm):
                # vLLM batching: Return None future and include metadata for batch processing
                result.pending_llm_calls.append(
                    (
                        agent.id,
                        agent.cluster,
                        target_post,
                        None,  # No individual future
                        {
                            "post_content": post_content,
                            "agent_attrs": agent_attrs,
                            "post_data": post_data,
                        },
                    )
                )
            else:
                # Standard: Create individual future
                future = generate_llm_search_action_async(
                    self.context.llm, agent.cluster, post_content, agent_attrs, agent.id
                )
                # Store: (agent_id, cluster_id, target_post_id, future)
                result.pending_llm_calls.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Randomly select action among comment, share, or react
            possible_actions = ["comment", "share", "react"]
            selected_action = random.choice(possible_actions)
            result.metadata["selected_action"] = selected_action

            if selected_action == "comment":
                action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
                # Calculate opinion updates for the comment
                if post_data:
                    updated_opinions = self._calculate_opinion_updates(
                        agent.id, target_post, post_data
                    )
                    if updated_opinions:
                        action.updated_opinions = updated_opinions
            elif selected_action == "share":
                action = generate_rule_based_share(agent.id, agent.cluster, target_post)
                # Calculate opinion updates for the share
                if post_data:
                    updated_opinions = self._calculate_opinion_updates(
                        agent.id, target_post, post_data
                    )
                    if updated_opinions:
                        action.updated_opinions = updated_opinions
            else:  # react
                # Use basic reactions (simple positive/negative responses)
                reaction_type = random.choice(BASIC_REACTIONS)
                action = ActionDTO(
                    agent.id, agent.cluster, reaction_type, target_post_id=target_post
                )
                result.metadata["reaction_type"] = reaction_type

            # Annotate rule-based action if it has content
            if hasattr(action, "content") and action.content:
                self._annotate_action(action)

            result.actions.append(action)
            result.metadata["action_type"] = action.action_type

        return result
