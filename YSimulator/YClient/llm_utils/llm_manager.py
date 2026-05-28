"""
LLM Manager for centralized LLM interaction.

This module provides a unified interface for all LLM calls, wrapping the Ray LLM actor
and providing consistent error handling, logging, and retry logic.
"""

import logging
from typing import Any, Optional


def _get_llm_actor_for_manager(llm_handle: Any, agent_id: Optional[str] = None) -> Any:
    """
    Get the appropriate LLM actor from handle.

    If llm_handle is a LLMLoadBalancer, uses agent_id to route to the correct actor.
    Otherwise returns llm_handle directly (single actor case).

    Args:
        llm_handle: Either a Ray actor handle or a LLMLoadBalancer instance
        agent_id: Optional agent ID for load balancing

    Returns:
        Ray actor handle for LLM service
    """
    # Check if llm_handle is a load balancer by checking its class name
    # This avoids issues with Mock objects that auto-create attributes
    if llm_handle.__class__.__name__ in ("LLMLoadBalancer", "LLMActorPool"):
        if agent_id is None:
            # Fallback to first actor if no agent_id provided
            return llm_handle.get_all_actors()[0]
        return llm_handle.get_actor_for_agent(agent_id)
    # Direct actor handle (including Ray actors)
    return llm_handle


class LLMManager:
    """
    Central manager for LLM interactions.

    Provides a clean interface to the underlying LLM service (Ray actor),
    with consistent error handling and logging.
    """

    def __init__(self, llm_handle: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize the LLM Manager.

        Args:
            llm_handle: Ray actor handle for LLM service or LLMLoadBalancer
            logger: Logger instance for debugging
        """
        self.llm = llm_handle
        self.logger = logger or logging.getLogger(__name__)

    def generate_post(
        self, cluster_id: int, agent_attrs: dict, topic: str, agent_id: Optional[str] = None
    ) -> Any:
        """
        Generate a post using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            topic: Topic for the post
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM generate_post: cluster={cluster_id}, topic={topic}")
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_post.remote(cluster_id, agent_attrs, topic)

    def generate_news_post(
        self,
        cluster_id: int,
        agent_attrs: dict,
        article_title: str,
        article_summary: str,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Generate a news-based post using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            article_title: Title of the news article
            article_summary: Summary of the news article
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_news_post: cluster={cluster_id}, title={article_title[:50]}..."
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_news_post.remote(
            cluster_id, agent_attrs, article_title, article_summary
        )

    def generate_image_post(
        self,
        cluster_id: int,
        agent_attrs: dict,
        topic: str,
        image_id: str,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Generate an image post caption using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            topic: Topic for the image
            image_id: ID of the image
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_image_post: cluster={cluster_id}, topic={topic}, image={image_id}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_image_post.remote(cluster_id, agent_attrs, topic, image_id)

    def generate_comment(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict,
        author_name: str,
        thread_context: str,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Generate a comment on a post using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            post_content: Content of the post being commented on
            agent_attrs: Agent attributes for personalization
            author_name: Name of the post author
            thread_context: Context from the comment thread
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_comment: cluster={cluster_id}, post_len={len(post_content)}, author={author_name}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_comment.remote(
            cluster_id, post_content, agent_attrs, author_name, thread_context
        )

    def generate_share_comment(
        self,
        cluster_id: int,
        agent_attrs: dict,
        post_content: str,
        author_name: str,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Generate a personalized comment for sharing a post.

        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            post_content: Content being shared
            author_name: Name of original post author
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_share_comment: cluster={cluster_id}, post_len={len(post_content)}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_share_comment.remote(
            cluster_id, agent_attrs, post_content, author_name
        )

    def decide_follow(
        self,
        cluster_id: int,
        agent_attrs: dict,
        target_user: dict,
        recent_posts: list,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Decide whether to follow a user using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            agent_attrs: Agent attributes for personalization
            target_user: Target user information
            recent_posts: Recent posts from the target user
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM decide_follow: cluster={cluster_id}, target={target_user.get( 'username', 'unknown')}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.decide_follow.remote(cluster_id, agent_attrs, target_user, recent_posts)

    def extract_topics_from_article(
        self, title: str, summary: str, agent_id: Optional[str] = None
    ) -> Any:
        """
        Extract topics from a news article using the LLM.

        Args:
            title: Article title
            summary: Article summary
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM extract_topics: title={title[:50]}...")
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.extract_topics_from_article.remote(title, summary)

    def infer_emotion(self, text: str, agent_id: Optional[str] = None) -> Any:
        """
        Infer emotion from text using the LLM.

        Args:
            text: Text to analyze
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(f"LLM infer_emotion: text_len={len(text)}")
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.infer_emotion.remote(text)

    def is_available(self) -> bool:
        """
        Check if LLM service is available.

        Returns:
            True if LLM handle is not None, False otherwise
        """
        return self.llm is not None

    def infer_article_opinion(
        self,
        article_content: str,
        topic_name: str,
        opinion_groups: dict,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Infer agent's opinion on an article topic using the LLM.

        Args:
            article_content: Article text to analyze
            topic_name: Topic to infer opinion about
            opinion_groups: Opinion group configuration
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM infer_article_opinion: topic={topic_name}, content_len={len(article_content)}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.infer_article_opinion.remote(article_content, topic_name, opinion_groups)

    def generate_secondary_follow_decision(
        self,
        cluster_id: int,
        post_content: str,
        is_currently_following: bool,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Decide whether to follow/unfollow post author as secondary follow using the LLM.

        Args:
            cluster_id: Agent's cluster ID
            post_content: Content of the post
            is_currently_following: Whether agent currently follows the author
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_secondary_follow_decision: cluster={cluster_id}, following={is_currently_following}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_secondary_follow_decision.remote(
            cluster_id, post_content, is_currently_following
        )

    def generate_reciprocal_follow_decision(
        self,
        cluster_id: int,
        source_agent_profile,
        action: str,
        agent_attrs: dict = None,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Decide whether to reciprocate a direct follow/unfollow event using the LLM.

        Args:
            cluster_id: Target agent cluster/persona
            source_agent_profile: Profile of the agent who initiated the link action
            action: "follow" or "unfollow"
            agent_attrs: Optional target agent attributes for persona building
            agent_id: Optional target agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM generate_reciprocal_follow_decision: cluster={cluster_id}, action={action}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.generate_reciprocal_follow_decision.remote(
            cluster_id, source_agent_profile, action, agent_attrs
        )

    def evaluate_opinion(
        self,
        agent_opinion: str,
        author_opinion: str,
        post_text: str,
        topic: str,
        peers_opinions: list = None,
        agent_id: Optional[str] = None,
    ) -> Any:
        """
        Evaluate how an agent's opinion should change after reading a post.

        Uses LLM to determine if the agent agrees, disagrees, or remains neutral
        about the expressed opinion in the post.

        Args:
            agent_opinion: Agent's current opinion label (e.g., "Neutral", "In favor")
            author_opinion: Post author's opinion label
            post_text: Content of the post being evaluated
            topic: Topic name being discussed
            peers_opinions: Optional list of (opinion_label, count) tuples for neighbors
            agent_id: Optional agent ID for load balancing

        Returns:
            Ray ObjectRef (future) for the LLM call
        """
        self.logger.debug(
            f"LLM evaluate_opinion: agent={agent_opinion}, author={author_opinion}, topic={topic}"
        )
        llm_actor = _get_llm_actor_for_manager(self.llm, agent_id)
        return llm_actor.evaluate_opinion.remote(
            agent_opinion, author_opinion, post_text, topic, peers_opinions
        )
