"""
Share link action generator for YSimulator agents.

This module generates SHARE_LINK actions where page agents share news articles
from their RSS feeds. This is the most complex action type as it involves:
- Fetching articles from news service
- Extracting topics using LLM
- Managing article opinions
- Generating commentary (for LLM agents)
"""

import ray

from YSimulator.YClient.action_generators.base_generator import (
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.actions import generate_news_post_async, generate_rule_based_news_post
from YSimulator.YClient.classes.ray_models import AgentProfile


class ShareLinkGenerator(BaseActionGenerator):
    """
    Generator for SHARE_LINK actions.

    This is the most complex generator as it handles:
    - News article fetching from RSS feeds
    - Topic extraction using LLM
    - Opinion inference for page agents
    - Commentary generation (LLM agents)

    Only page agents (is_page==1) can perform SHARE_LINK actions.
    """

    def can_generate(self, agent: AgentProfile, agent_type: str) -> bool:
        """
        Check if agent can perform SHARE_LINK action.

        Only page agents with feed URLs can share links.
        """
        return agent.is_page == 1 and bool(agent.feed_url)

    def generate(self, agent: AgentProfile, agent_type: str) -> ActionGeneratorResult:
        """
        Generate a SHARE_LINK action for the agent.

        Args:
            agent: Agent profile (must be page agent)
            agent_type: "llm" or "rule_based"

        Returns:
            ActionGeneratorResult with action or pending LLM call
        """
        result = ActionGeneratorResult()

        # Log the action initiation
        self.context.logger.info(
            f"share_link action: agent={agent.username}, is_page={agent.is_page}, "
            f"feed_url={agent.feed_url[:50] if agent.feed_url else None}, "
            f"news_service={self.context.news_service is not None}"
        )

        # Validate agent is a page
        if agent.is_page != 1:
            self.context.logger.warning(f"share_link skipped: {agent.username} is not a page agent")
            result.metadata["error"] = "not_page_agent"
            return result

        if not agent.feed_url:
            self.context.logger.warning(f"share_link skipped: {agent.username} has no feed_url")
            result.metadata["error"] = "no_feed_url"
            return result

        if not self.context.news_service:
            self.context.logger.warning(
                f"share_link skipped: {agent.username} - news_service is None"
            )
            result.metadata["error"] = "no_news_service"
            return result

        # Get an article from this page's specific feed
        try:
            self.context.logger.info(
                f"Page {agent.username} fetching article from {agent.feed_url[:50]}"
            )
            article_future = self.context.news_service.get_article_from_feed.remote(agent.feed_url)
            article = ray.get(article_future)

            if not article:
                self.context.logger.warning(f"Page {agent.username} got no article from feed")
                result.metadata["error"] = "no_article"
                return result

            self.context.logger.info(
                f"Page {agent.username} got article: {article.get('title', 'NO TITLE')[:50]}"
            )
            result.metadata["article_title"] = article.get("title", "")[:50]

            # Verify the article's website_id matches the page's user_id
            article_website_id = article.get("website_id")
            if article_website_id:
                normalized_article_id = str(article_website_id).lower()
                normalized_agent_id = str(agent.id).lower()
                if normalized_article_id != normalized_agent_id:
                    self.context.logger.warning(
                        f"Page {agent.username} attempted to share from wrong feed. "
                        f"Page ID: {agent.id}, Article Website ID: {article_website_id}"
                    )
                    result.metadata["error"] = "website_id_mismatch"
                    return result

            if agent_type == "llm":
                # LLM page posts news with commentary
                self.context.logger.info(f"LLM Page {agent.username} generating news post async")
                future, article_id = generate_news_post_async(
                    self.context.news_service,
                    self.context.llm,
                    agent.cluster,
                    article,
                    agent.username,
                )
                self.context.logger.info(f"LLM Page {agent.username} got article_id: {article_id}")

                # Extract and store article topics (if we have article_id)
                if article_id:
                    self._process_article_topics(agent, article, article_id)

                # Store pending call: (agent_id, cluster_id, future, article_id)
                result.pending_llm_calls.append((agent.id, agent.cluster, future, article_id))
                result.metadata["article_id"] = article_id
            else:
                # Rule-based page posts news directly
                self.context.logger.info(f"Rule-based Page {agent.username} generating news post")
                action, article_id = generate_rule_based_news_post(
                    agent.id, agent.cluster, article, self.context.news_service
                )
                self.context.logger.info(
                    f"Rule-based Page {agent.username} got article_id: {article_id}"
                )

                # Extract and store article topics
                if article_id:
                    self._process_article_topics(agent, article, article_id)

                action.article_id = article_id
                self._annotate_action(action)
                result.actions.append(action)
                result.metadata["article_id"] = article_id

        except Exception as e:
            result.metadata["error"] = "exception"
            result.metadata["exception"] = str(e)
            self.context.logger.warning(f"Share link action failed for page {agent.username}: {e}")
            import traceback

            self.context.logger.warning(f"Traceback: {traceback.format_exc()}")

        return result

    def _process_article_topics(self, agent: AgentProfile, article: dict, article_id: str):
        """
        Extract and store article topics, and manage page agent opinions.

        This is a complex operation that:
        1. Checks if article already has topics
        2. If not, extracts topics using LLM
        3. Stores topics in database
        4. Infers and stores page agent opinions on topics (if opinion dynamics enabled)
        """
        if not article_id or not self.context.llm:
            return

        try:
            # Check if article already has topics (avoid duplicate extraction)
            existing_topics = ray.get(self.context.server.get_article_topics.remote(article_id))

            if not existing_topics:
                # Extract topics using LLM (client-side)
                self.context.logger.info(
                    f"Extracting topics for article {article_id}: {article.get('title', '')[:50]}..."
                )
                topics_future = self.context.llm.extract_topics_from_article.remote(
                    article.get("title", ""), article.get("summary", "")
                )
                topic_names = ray.get(topics_future)
                self.context.logger.info(f"LLM extracted topics: {topic_names}")

                if topic_names:
                    # Store topics in database (server-side)
                    topic_ids = ray.get(
                        self.context.server.store_article_topics.remote(
                            article_id, topic_names[:2]  # Up to 2 topics
                        )
                    )

                    if topic_ids:
                        self.context.logger.info(
                            f"Stored {len(topic_ids)} topics for article {article_id}"
                        )

                        if self._is_opinion_dynamics_enabled():
                            self._store_page_agent_opinions(agent, article, topic_names[:2])
            else:
                self.context.logger.info(
                    f"Article {article_id} already has {len(existing_topics)} topics"
                )
                # Ensure opinions exist for existing article topics
                if self._is_opinion_dynamics_enabled():
                    self._ensure_page_agent_opinions(agent, article, existing_topics)

        except Exception as e:
            self.context.logger.warning(
                f"Failed to extract/store topics for article {article_id}: {e}"
            )
            import traceback

            self.context.logger.warning(f"Traceback: {traceback.format_exc()}")

    def _store_page_agent_opinions(self, agent: AgentProfile, article: dict, topic_names: list):
        """Store page agent opinions for newly extracted topics."""
        if not self.context.infer_page_agent_opinion_fn:
            return

        article_content = f"{article.get('title', '')} {article.get('summary', '')}"

        for topic_name in topic_names:
            try:
                opinion_value = self.context.infer_page_agent_opinion_fn(
                    agent.id, article_content, topic_name
                )
                # Get topic ID
                topic_id = ray.get(self.context.server.get_topic_id_by_name.remote(topic_name))
                if topic_id:
                    # Store opinion in database
                    ray.get(
                        self.context.server.add_agent_opinion.remote(
                            agent.id, self.context.round_id, topic_id, opinion_value, None, None
                        )
                    )
                    self.context.logger.info(
                        f"Stored opinion {opinion_value:.3f} for page {agent.username} on topic '{topic_name}'"
                    )
            except Exception as e:
                self.context.logger.warning(
                    f"Failed to infer/store opinion for topic '{topic_name}': {e}"
                )

    def _ensure_page_agent_opinions(self, agent: AgentProfile, article: dict, topic_ids: list):
        """Ensure page agent opinions exist for existing article topics."""
        if not self.context.infer_page_agent_opinion_fn:
            return

        article_content = f"{article.get('title', '')} {article.get('summary', '')}"

        for topic_id in topic_ids:
            try:
                # Get topic name from ID
                topic_name = ray.get(self.context.server.get_topic_name_from_id.remote(topic_id))
                if not topic_name:
                    continue

                # Check if opinion already exists
                existing_opinion = ray.get(
                    self.context.server.get_latest_agent_opinion.remote(agent.id, topic_id)
                )
                if existing_opinion is None:
                    opinion_value = self.context.infer_page_agent_opinion_fn(
                        agent.id, article_content, topic_name
                    )
                    ray.get(
                        self.context.server.add_agent_opinion.remote(
                            agent.id, self.context.round_id, topic_id, opinion_value, None, None
                        )
                    )
                    self.context.logger.info(
                        f"Stored opinion {opinion_value:.3f} for page {agent.username} on existing topic '{topic_name}'"
                    )
            except Exception as e:
                self.context.logger.warning(f"Failed to ensure opinion for existing topic: {e}")
