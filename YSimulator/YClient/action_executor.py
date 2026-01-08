"""
Action Executor Module for YClient.

This module provides action execution methods as a mixin class for SimulationClient.
Contains all action handler methods (_handle_*_action) for different action types.
"""

import random

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO

from YSimulator.YClient.actions import (
    generate_image_post_async,
    generate_llm_follow_async,
    generate_llm_post_async,
    generate_llm_read_async,
    generate_llm_search_action_async,
    generate_news_post_async,
    generate_rule_based_comment,
    generate_rule_based_follow,
    generate_rule_based_image_post,
    generate_rule_based_news_post,
    generate_rule_based_post,
    generate_rule_based_reaction,
    generate_rule_based_read,
    generate_rule_based_share,
)
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
from YSimulator.YClient.recsys.FollowRecSysRay import (
    AdamicAdarFollowRecSys,
    CommonNeighborsFollowRecSys,
    JaccardFollowRecSys,
    PreferentialAttachmentFollowRecSys,
    RandomFollowRecSys,
)

# Constants
REACTION_TYPES = ["LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"]
BASIC_REACTIONS = ["LIKE", "ANGRY"]

# Recommendation system class mapping
RECSYS_CLASS_MAP = {
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
    "default": ReverseChrono,  # Default to reverse chronological
}

# Follow recommendation system class mapping
FOLLOW_RECSYS_CLASS_MAP = {
    "random": RandomFollowRecSys,
    "common_neighbors": CommonNeighborsFollowRecSys,
    "jaccard": JaccardFollowRecSys,
    "adamic_adar": AdamicAdarFollowRecSys,
    "preferential_attachment": PreferentialAttachmentFollowRecSys,
    "default": CommonNeighborsFollowRecSys,  # Default to common neighbors algorithm
}


class ActionExecutorMixin:
    """
    Mixin class providing action execution methods for SimulationClient.
    
    This mixin requires the following attributes from the parent class:
    - self.server: Ray server actor handle
    - self.client_id: Client identifier
    - self.llm: LLM service handle
    - self.logger: Logger instance
    - self.recsys_mode: Recommendation system mode
    - self.recsys_n_posts: Number of posts for recommendations
    - self.max_length_thread_reading: Maximum thread context length
    - self.news_service: News feed service handle
    - And methods: _extract_agent_attrs, _annotate_action_content,
      _get_opinions_for_post, _calculate_opinion_updates
    """
    def _handle_post_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle post action for an agent."""
        if agent_type == "llm":
            # LLM: Fire off async call (don't wait for result yet)
            agent_attrs = self._extract_agent_attrs(agent)
            selected_topic = agent_attrs.get("topic")  # Get the sampled topic
            future = generate_llm_post_async(self.llm, agent.cluster, day, slot, agent_attrs)
            pending_llm_posts.append((agent.id, agent.cluster, future, selected_topic))
        else:
            # Rule-based: Execute immediately with sampled topic
            # Sample a topic from agent's interests (same as LLM agents)
            agent_attrs = self._extract_agent_attrs(agent)
            selected_topic = agent_attrs.get("topic")
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Attach the sampled topic to the action
            if selected_topic:
                action.topic = selected_topic
            # Annotate rule-based post
            self._annotate_action_content(action)
            actions.append(action)

    def _handle_comment_action(
        self, agent, agent_type, pending_llm_reactions, actions, rule_based_interactions
    ):
        """Handle comment action for an agent."""
        # Use recsys to get recommended posts to comment on
        agent_recsys_mode = agent.recsys_type if (hasattr(agent, "recsys_type") and agent.recsys_type) else self.recsys_mode
        recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
        recsys = recsys_class(n_posts=self.recsys_n_posts)

        # Get recommended posts from server
        recommended_posts = recsys.get_recommendations(
            self.server, agent.id, client_id=self.client_id
        )

        if not recommended_posts:
            return  # No posts available to comment on

        # Select one post randomly from recommendations
        target_post = random.choice(recommended_posts)

        if agent_type == "llm":
            # LLM: Get the post content and ask for a comment
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            if post_data:
                post_content = post_data.get("tweet", "")
                author_id = post_data.get("user_id")
                # Get author username
                author_name = "Someone"
                if author_id:
                    author_user = ray.get(
                        self.server.get_user.remote(author_id, client_id=self.client_id)
                    )
                    if author_user:
                        author_name = author_user.get("username", "Someone")

                # Get thread context (preceding posts/comments in chronological order)
                thread_context = ray.get(
                    self.server.get_thread_context.remote(
                        target_post, self.max_length_thread_reading, client_id=self.client_id
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

                # Fire off async LLM call to generate comment with agent attributes, author name, and thread context
                future = self.llm_manager.generate_comment(
                    agent.cluster, post_content, agent_attrs, author_name, thread_context
                )
                pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Just comment "COMMENT"
            action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
            # Annotate rule-based comment
            self._annotate_action_content(action)

            # Calculate opinion updates for rule-based comment
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            if post_data:
                updated_opinions = self._calculate_opinion_updates(agent.id, target_post, post_data)
                if updated_opinions:
                    action.updated_opinions = updated_opinions

                # Track for secondary follow (rule-based comment)
                rule_based_interactions.append(
                    (
                        agent.id,
                        agent.cluster,
                        post_data.get("user_id"),
                        post_data.get("tweet", ""),
                        False,
                    )
                )

            actions.append(action)

    def _handle_read_action(
        self, agent, agent_type, pending_llm_reactions, actions, rule_based_interactions
    ):
        """Handle read action for an agent."""
        # Use recsys to get recommended posts
        agent_recsys_mode = agent.recsys_type if (hasattr(agent, "recsys_type") and agent.recsys_type) else self.recsys_mode
        recsys_class = RECSYS_CLASS_MAP.get(agent_recsys_mode, RandomOrder)
        recsys = recsys_class(n_posts=self.recsys_n_posts)

        # Get recommended posts from server
        recommended_posts = recsys.get_recommendations(
            self.server, agent.id, client_id=self.client_id
        )

        if not recommended_posts:
            return  # No posts available to read

        # Select one post randomly from recommendations
        target_post = random.choice(recommended_posts)

        if agent_type == "llm":
            # LLM: Get the post content and ask for a reaction decision
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            if post_data:
                post_content = post_data.get("tweet", "")
                # Get agent attributes
                agent_attrs = self._extract_agent_attrs(agent)

                # Get opinions for the topics in this post
                opinion_info = self._get_opinions_for_post(agent.id, target_post)
                if opinion_info["topics"]:
                    # Add opinion information to agent attrs
                    agent_attrs["post_topics"] = opinion_info["topics"]
                    agent_attrs["post_opinions"] = opinion_info["opinions"]
                    agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

                # Fire off async LLM call to decide reaction with agent attributes
                future = generate_llm_read_async(self.llm, agent.cluster, post_content, agent_attrs)
                pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Randomly choose LIKE, DISLIKE (ANGRY), or IGNORE
            # Consider opinion when choosing reaction
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
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
                    # Higher opinion -> more likely to LIKE, lower -> more likely to express negative reaction
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
                        actions.append(action)
                        # Track for secondary follow
                        rule_based_interactions.append(
                            (
                                agent.id,
                                agent.cluster,
                                post_data.get("user_id"),
                                post_data.get("tweet", ""),
                                False,
                            )
                        )
                else:
                    # No opinion information, use default rule-based behavior
                    action = generate_rule_based_read(agent.id, agent.cluster, target_post)
                    if action:  # Only add if not IGNORE
                        actions.append(action)
                        # Track for secondary follow (rule-based read)
                        rule_based_interactions.append(
                            (
                                agent.id,
                                agent.cluster,
                                post_data.get("user_id"),
                                post_data.get("tweet", ""),
                                False,
                            )
                        )
                if post_data:
                    rule_based_interactions.append(
                        (
                            agent.id,
                            agent.cluster,
                            post_data.get("user_id"),
                            post_data.get("tweet", ""),
                            False,
                        )
                    )

    def _handle_follow_action(self, agent, agent_type, pending_llm_follows, actions):
        """Handle follow action for an agent."""
        # Use follow recsys to get suggested users
        agent_frecsys_mode = agent.frecsys_type if (hasattr(agent, "frecsys_type") and agent.frecsys_type) else "random"
        frecsys_class = FOLLOW_RECSYS_CLASS_MAP.get(agent_frecsys_mode, RandomFollowRecSys)
        frecsys = frecsys_class(n_neighbors=10, leaning_bias=1)

        # Get follow suggestions from server
        suggested_users = frecsys.get_follow_suggestions(
            self.server, agent.id, client_id=self.client_id
        )

        if not suggested_users:
            return  # No users available to follow

        if agent_type == "llm":
            # LLM: Ask to decide which user to follow
            future = generate_llm_follow_async(self.llm, agent.cluster, suggested_users)
            pending_llm_follows.append((agent.id, agent.cluster, future))
        else:
            # Rule-based: Randomly select one user to follow
            target_user = random.choice(suggested_users)
            action = generate_rule_based_follow(agent.id, agent.cluster, target_user)
            actions.append(action)

    def _handle_share_link_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle share_link action for page agents (news sharing)."""
        self.logger.info(
            f"share_link action: agent={agent.username}, is_page={agent.is_page}, feed_url={agent.feed_url[:50] if agent.feed_url else None}, news_service={self.news_service is not None}"
        )

        if agent.is_page != 1:
            self.logger.warning(f"share_link skipped: {agent.username} is not a page agent")
            return

        if not agent.feed_url:
            self.logger.warning(f"share_link skipped: {agent.username} has no feed_url")
            return

        if not self.news_service:
            self.logger.warning(f"share_link skipped: {agent.username} - news_service is None")
            return

        # Get an article from this page's specific feed
        try:
            self.logger.info(f"Page {agent.username} fetching article from {agent.feed_url[:50]}")
            article_future = self.news_service.get_article_from_feed.remote(agent.feed_url)
            article = ray.get(article_future)

            if article:
                self.logger.info(
                    f"Page {agent.username} got article: {article.get('title', 'NO TITLE')[:50]}"
                )

                # Verify the article's website_id matches the page's user_id
                article_website_id = article.get("website_id")
                if article_website_id:
                    normalized_article_id = str(article_website_id).lower()
                    normalized_agent_id = str(agent.id).lower()
                    if normalized_article_id != normalized_agent_id:
                        self.logger.warning(
                            f"Page {agent.username} attempted to share from wrong feed. "
                            f"Page ID: {agent.id}, Article Website ID: {article_website_id}"
                        )
                        return

                if agent_type == "llm":
                    # LLM page posts news with commentary
                    self.logger.info(f"LLM Page {agent.username} generating news post async")
                    future, article_id = generate_news_post_async(
                        self.news_service, self.llm, agent.cluster, article, agent.username
                    )
                    self.logger.info(f"LLM Page {agent.username} got article_id: {article_id}")

                    # Extract and store article topics after article is saved
                    if article_id:
                        try:
                            # Check if article already has topics (avoid duplicate extraction)
                            existing_topics = ray.get(
                                self.server.get_article_topics.remote(article_id)
                            )

                            if not existing_topics:
                                # Extract topics using LLM (client-side)
                                self.logger.info(
                                    f"Extracting topics for article {article_id}: {article.get('title', '')[:50]}..."
                                )
                                topics_future = self.llm_manager.extract_topics_from_article(
                                    article.get("title", ""), article.get("summary", "")
                                )
                                topic_names = ray.get(topics_future)
                                self.logger.info(f"LLM extracted topics: {topic_names}")

                                if topic_names:
                                    # Store topics in database (server-side)
                                    topic_ids = ray.get(
                                        self.server.store_article_topics.remote(
                                            article_id, topic_names[:2]  # Up to 2 topics
                                        )
                                    )
                                    if topic_ids:
                                        self.logger.info(
                                            f"Stored {len(topic_ids)} topics for article {article_id}"
                                        )

                                        # CLIENT-SIDE: Infer and store opinions for LLM page agent on article topics
                                        if self._is_opinion_dynamics_enabled():
                                            article_content = f"{article.get('title', '')} {article.get('summary', '')}"
                                            for topic_name in topic_names[:2]:
                                                try:
                                                    opinion_value = self._infer_page_agent_opinion(
                                                        agent.id, article_content, topic_name
                                                    )
                                                    # Get topic ID
                                                    topic_id = ray.get(
                                                        self.server.get_topic_id_by_name.remote(
                                                            topic_name
                                                        )
                                                    )
                                                    if topic_id:
                                                        # Store opinion in database
                                                        ray.get(
                                                            self.server.add_agent_opinion.remote(
                                                                agent.id,
                                                                topic_id,
                                                                opinion_value,
                                                                None,
                                                                None,
                                                            )
                                                        )
                                                        self.logger.info(
                                                            f"Stored opinion {opinion_value:.3f} for LLM page {agent.username} on topic '{topic_name}'"
                                                        )
                                                except Exception as e:
                                                    self.logger.warning(
                                                        f"Failed to infer/store opinion for topic '{topic_name}': {e}"
                                                    )
                            else:
                                self.logger.info(
                                    f"Article {article_id} already has {len(existing_topics)} topics"
                                )
                                # CLIENT-SIDE: Ensure opinions exist for existing article topics
                                if self._is_opinion_dynamics_enabled():
                                    article_content = (
                                        f"{article.get('title', '')} {article.get('summary', '')}"
                                    )
                                    # existing_topics is List[str] of topic IDs
                                    for topic_id in existing_topics:
                                        try:
                                            # Get topic name from ID
                                            topic_name = ray.get(
                                                self.server.get_topic_name_from_id.remote(topic_id)
                                            )
                                            if not topic_name:
                                                continue

                                            # Check if opinion already exists
                                            existing_opinion = ray.get(
                                                self.server.get_latest_agent_opinion.remote(
                                                    agent.id, topic_id
                                                )
                                            )
                                            if existing_opinion is None:
                                                opinion_value = self._infer_page_agent_opinion(
                                                    agent.id, article_content, topic_name
                                                )
                                                ray.get(
                                                    self.server.add_agent_opinion.remote(
                                                        agent.id,
                                                        topic_id,
                                                        opinion_value,
                                                        None,
                                                        None,
                                                    )
                                                )
                                                self.logger.info(
                                                    f"Stored opinion {opinion_value:.3f} for LLM page {agent.username} on existing topic '{topic_name}'"
                                                )
                                        except Exception as e:
                                            self.logger.warning(
                                                f"Failed to ensure opinion for existing topic: {e}"
                                            )
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to extract/store topics for article {article_id}: {e}"
                            )
                            import traceback

                            self.logger.warning(f"Traceback: {traceback.format_exc()}")

                    pending_llm_posts.append((agent.id, agent.cluster, future, article_id))
                else:
                    # Rule-based page posts news directly
                    self.logger.info(f"Rule-based Page {agent.username} generating news post")
                    action, article_id = generate_rule_based_news_post(
                        agent.id, agent.cluster, article, self.news_service
                    )
                    self.logger.info(
                        f"Rule-based Page {agent.username} got article_id: {article_id}"
                    )

                    # Extract and store article topics after article is saved
                    if article_id:
                        try:
                            # Check if article already has topics (avoid duplicate extraction)
                            existing_topics = ray.get(
                                self.server.get_article_topics.remote(article_id)
                            )

                            if not existing_topics:
                                # Extract topics using LLM (client-side)
                                self.logger.info(
                                    f"Extracting topics for article {article_id}: {article.get('title', '')[:50]}..."
                                )
                                topics_future = self.llm_manager.extract_topics_from_article(
                                    article.get("title", ""), article.get("summary", "")
                                )
                                topic_names = ray.get(topics_future)
                                self.logger.info(f"LLM extracted topics: {topic_names}")

                                if topic_names:
                                    # Store topics in database (server-side)
                                    topic_ids = ray.get(
                                        self.server.store_article_topics.remote(
                                            article_id, topic_names[:2]  # Up to 2 topics
                                        )
                                    )
                                    if topic_ids:
                                        self.logger.info(
                                            f"Stored {len(topic_ids)} topics for article {article_id}"
                                        )

                                        # CLIENT-SIDE: Infer and store opinions for rule-based page agent on article topics
                                        if self._is_opinion_dynamics_enabled():
                                            article_content = f"{article.get('title', '')} {article.get('summary', '')}"
                                            for topic_name in topic_names[:2]:
                                                try:
                                                    opinion_value = self._infer_page_agent_opinion(
                                                        agent.id, article_content, topic_name
                                                    )
                                                    # Get topic ID
                                                    topic_id = ray.get(
                                                        self.server.get_topic_id_by_name.remote(
                                                            topic_name
                                                        )
                                                    )
                                                    if topic_id:
                                                        # Store opinion in database
                                                        ray.get(
                                                            self.server.add_agent_opinion.remote(
                                                                agent.id,
                                                                topic_id,
                                                                opinion_value,
                                                                None,
                                                                None,
                                                            )
                                                        )
                                                        self.logger.info(
                                                            f"Stored opinion {opinion_value:.3f} for rule-based page {agent.username} on topic '{topic_name}'"
                                                        )
                                                except Exception as e:
                                                    self.logger.warning(
                                                        f"Failed to infer/store opinion for topic '{topic_name}': {e}"
                                                    )

                            else:
                                self.logger.info(
                                    f"Article {article_id} already has {len(existing_topics)} topics"
                                )
                                # CLIENT-SIDE: Ensure opinions exist for existing article topics
                                if self._is_opinion_dynamics_enabled():
                                    article_content = (
                                        f"{article.get('title', '')} {article.get('summary', '')}"
                                    )
                                    # existing_topics is List[str] of topic IDs
                                    for topic_id in existing_topics:
                                        try:
                                            # Get topic name from ID
                                            topic_name = ray.get(
                                                self.server.get_topic_name_from_id.remote(topic_id)
                                            )
                                            if not topic_name:
                                                continue

                                            # Check if opinion already exists
                                            existing_opinion = ray.get(
                                                self.server.get_latest_agent_opinion.remote(
                                                    agent.id, topic_id
                                                )
                                            )
                                            if existing_opinion is None:
                                                opinion_value = self._infer_page_agent_opinion(
                                                    agent.id, article_content, topic_name
                                                )
                                                ray.get(
                                                    self.server.add_agent_opinion.remote(
                                                        agent.id,
                                                        topic_id,
                                                        opinion_value,
                                                        None,
                                                        None,
                                                    )
                                                )
                                                self.logger.info(
                                                    f"Stored opinion {opinion_value:.3f} for rule-based page {agent.username} on existing topic '{topic_name}'"
                                                )
                                        except Exception as e:
                                            self.logger.warning(
                                                f"Failed to ensure opinion for existing topic: {e}"
                                            )
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to extract/store topics for article {article_id}: {e}"
                            )
                            import traceback

                            self.logger.warning(f"Traceback: {traceback.format_exc()}")

                    action.article_id = article_id
                    # Annotate rule-based news post
                    self._annotate_action_content(action)
                    actions.append(action)
            else:
                self.logger.warning(f"Page {agent.username} got no article from feed")
        except Exception as e:
            self.logger.warning(f"Share link action failed for page {agent.username}: {e}")
            import traceback

            self.logger.warning(f"Traceback: {traceback.format_exc()}")

    def _handle_share_action(self, agent, agent_type, target, actions):
        """Handle share action (reshare existing post)."""
        # For now, only rule-based agents share
        if agent_type == "rule_based" and target:
            action = generate_rule_based_share(agent.id, agent.cluster, target)
            # Calculate opinion updates for the share
            post_data = ray.get(self.server.get_post.remote(target, client_id=self.client_id))
            if post_data:
                updated_opinions = self._calculate_opinion_updates(agent.id, target, post_data)
                if updated_opinions:
                    action.updated_opinions = updated_opinions
            actions.append(action)

    def _handle_search_action(self, agent, agent_type, pending_llm_reactions, actions):
        """
        Handle search action for an agent.

        Agent searches for posts on a topic of interest:
        1. Sample a topic from agent's interests (same as post action)
        2. Search for up to 10 recent posts on that topic from other users
        3. Randomly sample one of the found posts
        4. Decide whether to comment, share, or react to it
        5. Execute the selected action
        """
        self.logger.info(
            f"search action initiated: agent={agent.username}, type={agent_type}",
            extra={
                "extra_data": {
                    "agent_id": agent.id,
                    "agent_type": agent_type,
                    "archetype": agent.archetype,
                }
            },
        )

        # Sample a topic from agent's interests
        agent_attrs = self._extract_agent_attrs(agent)
        selected_topic = agent_attrs.get("topic")

        if not selected_topic:
            # No topics available, skip search action
            self.logger.debug(
                f"search action skipped: no topics available for agent {agent.username}",
                extra={"extra_data": {"agent_id": agent.id}},
            )
            return

        self.logger.info(
            f"search action: topic sampled '{selected_topic}' for agent {agent.username}",
            extra={"extra_data": {"agent_id": agent.id, "topic": selected_topic}},
        )

        # Get topic_id from topic name
        try:
            topic_id = ray.get(self.server.get_topic_id_by_name.remote(selected_topic))
            if not topic_id:
                self.logger.debug(
                    f"search action: topic '{selected_topic}' not found in database, skipping for agent {agent.username}",
                    extra={"extra_data": {"agent_id": agent.id, "topic": selected_topic}},
                )
                return
        except Exception as e:
            self.logger.warning(
                f"search action error: failed to get topic_id for '{selected_topic}' for agent {agent.username}: {e}",
                extra={
                    "extra_data": {"agent_id": agent.id, "topic": selected_topic, "error": str(e)}
                },
            )
            return

        # Search for posts on this topic (up to 10 recent posts from other users)
        try:
            found_posts = ray.get(
                self.server.search_posts_by_topic.remote(
                    topic_id, agent.id, limit=10, client_id=self.client_id
                )
            )
        except Exception as e:
            self.logger.warning(
                f"search action error: failed to search posts for topic '{selected_topic}' for agent {agent.username}: {e}",
                extra={
                    "extra_data": {
                        "agent_id": agent.id,
                        "topic": selected_topic,
                        "topic_id": topic_id,
                        "error": str(e),
                    }
                },
            )
            return

        if not found_posts:
            # No posts found on this topic
            self.logger.debug(
                f"search action: no posts found for topic '{selected_topic}' for agent {agent.username}",
                extra={
                    "extra_data": {
                        "agent_id": agent.id,
                        "topic": selected_topic,
                        "topic_id": topic_id,
                    }
                },
            )
            return

        self.logger.info(
            f"search action: found {len(found_posts)} posts on topic '{selected_topic}' for agent {agent.username}",
            extra={
                "extra_data": {
                    "agent_id": agent.id,
                    "topic": selected_topic,
                    "posts_found": len(found_posts),
                }
            },
        )

        # Randomly sample one post from the found posts
        target_post = random.choice(found_posts)

        # Get the post content
        try:
            post_data = ray.get(self.server.get_post.remote(target_post, client_id=self.client_id))
            if not post_data:
                self.logger.warning(
                    f"search action: post {target_post} not found for agent {agent.username}",
                    extra={"extra_data": {"agent_id": agent.id, "target_post_id": target_post}},
                )
                return
            post_content = post_data.get("tweet", "")
            post_author_id = post_data.get("user_id", "unknown")
        except Exception as e:
            self.logger.warning(
                f"search action error: failed to get post {target_post} for agent {agent.username}: {e}",
                extra={
                    "extra_data": {
                        "agent_id": agent.id,
                        "target_post_id": target_post,
                        "error": str(e),
                    }
                },
            )
            return

        self.logger.info(
            f"search action: selected post {target_post} on topic '{selected_topic}' for agent {agent.username}",
            extra={
                "extra_data": {
                    "agent_id": agent.id,
                    "topic": selected_topic,
                    "target_post_id": target_post,
                    "post_author_id": post_author_id,
                    "post_length": len(post_content),
                }
            },
        )

        if agent_type == "llm":
            # LLM: Ask LLM to decide which action to perform (comment/share/react)
            self.logger.info(
                f"search action: LLM deciding engagement for agent {agent.username}",
                extra={"extra_data": {"agent_id": agent.id, "target_post_id": target_post}},
            )

            # Get opinions for the topics in this post
            opinion_info = self._get_opinions_for_post(agent.id, target_post)
            if opinion_info["topics"]:
                # Add opinion information to agent attrs
                agent_attrs["post_topics"] = opinion_info["topics"]
                agent_attrs["post_opinions"] = opinion_info["opinions"]
                agent_attrs["post_opinion_values"] = opinion_info["opinion_values"]

            future = generate_llm_search_action_async(
                self.llm, agent.cluster, post_content, agent_attrs
            )
            pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
        else:
            # Rule-based: Randomly select action among comment, share, or react
            possible_actions = ["comment", "share", "react"]
            selected_action = random.choice(possible_actions)

            self.logger.info(
                f"search action: rule-based agent {agent.username} selected '{selected_action}' action",
                extra={
                    "extra_data": {
                        "agent_id": agent.id,
                        "selected_action": selected_action,
                        "target_post_id": target_post,
                    }
                },
            )

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
                self.logger.info(
                    f"search action: rule-based agent {agent.username} reacting with {reaction_type}",
                    extra={
                        "extra_data": {
                            "agent_id": agent.id,
                            "reaction_type": reaction_type,
                            "target_post_id": target_post,
                        }
                    },
                )

            # Annotate rule-based action if it has content
            if hasattr(action, "content") and action.content:
                self._annotate_action_content(action)
            actions.append(action)

            self.logger.info(
                f"search action completed: rule-based action created for agent {agent.username}",
                extra={
                    "extra_data": {
                        "agent_id": agent.id,
                        "action_type": action.action_type,
                        "target_post_id": target_post,
                    }
                },
            )

    def _handle_image_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle image post action - share an image with commentary."""
        # Get a random image from the database
        try:
            image_data = ray.get(self.server.get_random_image.remote())

            if not image_data:
                self.logger.info(f"No images available for agent {agent.username} to share")
                return

            image_id = image_data.get("id")
            article_id = image_data.get("article_id")

            # Get topics associated with the article
            topic_ids = []
            topic_names = []
            if article_id:
                topic_ids = ray.get(self.server.get_article_topics.remote(article_id))
                # Get topic names from interest table
                for topic_id in topic_ids:
                    interest = ray.get(self.server.get_interest_by_id.remote(topic_id))
                    if interest:
                        topic_names.append(interest.get("interest", ""))

            if agent_type == "llm":
                # LLM agent: Generate personalized commentary
                agent_attrs = self._extract_agent_attrs(agent)
                future, img_id = generate_image_post_async(
                    self.server, self.llm, agent.cluster, image_data, topic_names, agent_attrs
                )
                # Store future along with image_id and topic_ids
                pending_llm_posts.append((agent.id, agent.cluster, future, None, img_id, topic_ids))
            else:
                # Rule-based: Share with "IMAGE" text
                action = generate_rule_based_image_post(agent.id, agent.cluster, image_id)
                # Store topic_ids to be added after post creation
                action.topic_ids = topic_ids
                # Log the action details
                self.logger.info(
                    f"Rule-based image action created for agent {agent.username}: image_id={action.image_id if hasattr(action, 'image_id') else 'NOT SET'}, topics={len(topic_ids)}"
                )
                # Annotate content
                self._annotate_action_content(action)
                actions.append(action)

        except Exception as e:
            self.logger.error(f"Error handling image action for agent {agent.username}: {e}")
            import traceback

            traceback.print_exc()

    def _handle_cast_action(self, agent, agent_type, day, slot, pending_llm_posts, actions):
        """Handle cast/broadcast action (stub for future broadcast mechanism)."""
        if agent_type == "llm":
            future = generate_llm_post_async(self.llm, agent.cluster, day, slot)
            pending_llm_posts.append((agent.id, agent.cluster, future, None))
        else:
            # Rule-based: Execute immediately with sampled topic
            # Sample a topic from agent's interests (same as LLM agents)
            agent_attrs = self._extract_agent_attrs(agent)
            selected_topic = agent_attrs.get("topic")
            action = generate_rule_based_post(agent.id, agent.cluster)
            # Attach the sampled topic to the action
            if selected_topic:
                action.topic = selected_topic
            # Annotate rule-based post
            self._annotate_action_content(action)
            actions.append(action)

