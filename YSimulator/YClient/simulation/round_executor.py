"""
Round Executor Module for YClient Simulation.

This module handles per-round execution logic including:
- Agent action selection and dispatching
- Coordinating with action generators
- Managing pending LLM calls
- Processing secondary follows
- Opinion updates

Extracted from client.py's _simulate() method as part of Phase 2 refactoring.
"""

import logging
import random
from typing import List, Tuple

import ray

from YSimulator.YClient.action_generators import ActionGeneratorFactory
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile


class RoundExecutor:
    """
    Executes simulation logic for a single round/slot.

    Coordinates:
    - Agent action selection
    - Action generator dispatch
    - LLM call batching (scatter phase)
    - Secondary follow processing
    """

    def __init__(
        self,
        agent_profiles: List[AgentProfile],
        server,
        client_id: str,
        logger: logging.Logger,
        agent_downcast: bool,
        actions_likelihood: dict,
        select_action_fn,
        determine_agent_type_fn,
        dispatch_action_with_generator_fn,
    ):
        """
        Initialize the RoundExecutor.

        Args:
            agent_profiles: List of all agent profiles
            server: Ray server actor handle
            client_id: Client identifier
            logger: Logger instance
            agent_downcast: Whether agent downcast is enabled
            actions_likelihood: Action probability configuration
            select_action_fn: Function to select agent actions
            determine_agent_type_fn: Function to determine agent type
            dispatch_action_with_generator_fn: Function to dispatch actions with generators
        """
        self.agent_profiles = agent_profiles
        self.server = server
        self.client_id = client_id
        self.logger = logger
        self.agent_downcast = agent_downcast
        self.actions_likelihood = actions_likelihood
        self.select_action_fn = select_action_fn
        self.determine_agent_type_fn = determine_agent_type_fn
        self.dispatch_action_with_generator_fn = dispatch_action_with_generator_fn

    def execute_round(
        self,
        active_agents: List[AgentProfile],
        recent_posts: List[str],
        action_generator_factory: ActionGeneratorFactory,
    ) -> Tuple[List[ActionDTO], List, List, List, List]:
        """
        Execute simulation for one round with the given active agents.

        This method:
        1. For each active agent: samples number of actions from daily_activity_level
        2. For each action: calls select_action() to determine what to do
        3. Dispatches actions using action generators
        4. Collects pending LLM calls for parallel execution (scatter phase)
        5. Tracks rule-based interactions for secondary follow

        The gather phase (resolving LLM calls) is handled separately by BatchProcessor.

        Args:
            active_agents: List of agents active in this round
            recent_posts: List of recent post UUIDs for reactions
            action_generator_factory: Factory for creating action generators

        Returns:
            Tuple of:
            - actions: List of immediate (non-LLM) actions
            - pending_llm_posts: List of pending post generation futures
            - pending_llm_reactions: List of pending reaction/comment futures
            - pending_llm_follows: List of pending follow decision futures
            - rule_based_interactions: List of rule-based interaction tracking data
        """
        actions = []
        pending_llm_posts = []
        pending_llm_reactions = []
        pending_llm_follows = []
        rule_based_interactions = []

        self.logger.info(f"[REPLY] Starting simulation for {len(active_agents)} active agents")

        # --- SCATTER PHASE: Select and dispatch actions ---
        for agent in active_agents:
            # Determine agent type (llm or rule_based) with agent_downcast logic
            agent_type = self.determine_agent_type_fn(agent)

            # REPLY PIPELINE: Check for unreplied mentions and reply to one if present
            # This happens BEFORE the agent's normal actions
            # Page agents are excluded from reply pipeline (handled in ReplyGenerator)
            self.logger.debug(
                f"[REPLY] Processing agent {
                    agent.username} (type: {agent_type}, is_page: {
                    agent.is_page})"
            )

            # Use action generator framework for reply (Phase 1 consistency)
            immediate_actions, pending_calls, metadata = self.dispatch_action_with_generator_fn(
                "reply", agent, agent_type, None
            )

            # Add immediate actions (rule-based)
            actions.extend(immediate_actions)

            # Add pending LLM calls to the pending_llm_reactions list
            pending_llm_reactions.extend(pending_calls)

            # Sample number of actions for this agent based on daily_activity_level
            # Page agents can perform at most 1 action (0 or 1)
            # Regular agents: Random from 1 to daily_activity_level (minimum 1)
            if agent.daily_activity_level <= 0:
                # Skip agents with 0 or negative activity level
                continue

            if agent.is_page == 1:
                # Page agents perform at most 1 action (0 or 1)
                # Use a probability-based decision: 50% chance to act
                num_actions = 1 if random.random() < 0.5 else 0
                if num_actions > 0:
                    self.logger.info(f"Page agent {agent.username} will perform 1 action")
                else:
                    self.logger.debug(f"Page agent {agent.username} will skip this round")
            else:
                # Regular agents perform 1 to daily_activity_level actions
                num_actions = random.randint(1, agent.daily_activity_level)

            for action_idx in range(num_actions):
                action_type, agent_type, target = self.select_action_fn(agent, recent_posts)

                if agent.is_page == 1:
                    self.logger.info(
                        f"Page agent {
                            agent.username} action {
                            action_idx + 1}/{num_actions}: type={action_type}, agent_type={agent_type}"
                    )

                # Dispatch action using action generator framework
                immediate_actions, pending_calls, metadata = self.dispatch_action_with_generator_fn(
                    action_type, agent, agent_type, target
                )

                # Add immediate actions
                actions.extend(immediate_actions)

                # Route pending LLM calls to appropriate lists
                # The structure of pending_calls depends on action type
                if action_type in ["post", "image", "cast", "share_link"]:
                    pending_llm_posts.extend(pending_calls)
                elif action_type in ["comment", "read", "search", "share"]:
                    pending_llm_reactions.extend(pending_calls)
                elif action_type == "follow":
                    pending_llm_follows.extend(pending_calls)

                # Track rule-based interactions if metadata indicates it
                if metadata.get("rule_based_interaction"):
                    rb_interaction = metadata["rule_based_interaction"]
                    # Need to fetch post data for secondary follow
                    post_data = ray.get(
                        self.server.get_post.remote(
                            rb_interaction["target_post"], client_id=self.client_id
                        )
                    )
                    if post_data:
                        rule_based_interactions.append(
                            (
                                rb_interaction["agent_id"],
                                rb_interaction["cluster_id"],
                                post_data.get("user_id"),
                                post_data.get("tweet", ""),
                                False,
                            )
                        )

        self.logger.info(
            f"Scatter phase complete: pending_llm_posts={len(pending_llm_posts)}, "
            f"pending_llm_reactions={len(pending_llm_reactions)}, "
            f"pending_llm_follows={len(pending_llm_follows)}, "
            f"actions_so_far={len(actions)}"
        )

        return (
            actions,
            pending_llm_posts,
            pending_llm_reactions,
            pending_llm_follows,
            rule_based_interactions,
        )
