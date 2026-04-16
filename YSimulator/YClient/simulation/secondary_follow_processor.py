"""
Secondary Follow Processor Module for YClient Simulation.

This module handles secondary follow/unfollow decisions for agents who
interacted with content during the simulation round.

Extracted from client.py to align with Phase 1 action generator architecture.
Part of the simulation orchestration layer (Phase 2).
"""

import logging
import random
from typing import List, Tuple

import ray

from YSimulator.YClient.classes.ray_models import ActionDTO


class SecondaryFollowProcessor:
    """
    Processes secondary follow/unfollow decisions based on agent interactions.

    This processor handles the secondary follow pipeline where agents may decide
    to follow or unfollow content authors after reading or commenting on their posts.

    The decision is based on:
    - probability_of_secondary_follow configuration parameter
    - Post content (for LLM agents)
    - Current follow relationship status
    - Random choice (for rule-based agents)
    """

    def __init__(
        self,
        server,
        client_id: str,
        logger: logging.Logger,
        llm_manager,
        probability_of_secondary_follow: float,
        probability_of_follow_back: float = 0.0,
    ):
        """
        Initialize the SecondaryFollowProcessor.

        Args:
            server: Ray server actor handle
            client_id: Client identifier
            logger: Logger instance
            llm_manager: LLM manager for generating follow decisions
            probability_of_secondary_follow: Probability of evaluating follow decision
        """
        self.server = server
        self.client_id = client_id
        self.logger = logger
        self.llm_manager = llm_manager
        self.probability_of_secondary_follow = probability_of_secondary_follow
        self.probability_of_follow_back = probability_of_follow_back

    def process_secondary_follows(
        self,
        secondary_follow_candidates: List[Tuple],
        rule_based_interactions: List[Tuple],
        actions: List[ActionDTO],
    ) -> None:
        """
        Process secondary follow/unfollow decisions for agents who interacted with content.

        Args:
            secondary_follow_candidates: List of LLM agent interactions
                [(agent_id, cluster_id, author_id, post_content, is_llm)]
            rule_based_interactions: List of rule-based agent interactions (same format)
            actions: List to append follow/unfollow actions to
        """
        # Merge rule-based interactions into secondary follow candidates
        all_candidates = secondary_follow_candidates + rule_based_interactions

        if self.probability_of_secondary_follow <= 0 or not all_candidates:
            return

        self.logger.info(
            f"Secondary follow phase: {len(all_candidates)} candidates, "
            f"probability={self.probability_of_secondary_follow}"
        )

        # Process each candidate for secondary follow
        pending_secondary_follow_llm = (
            []
        )  # List of (agent_id, cluster_id, author_id, is_following, future)

        for agent_id, cluster_id, author_id, post_content, is_llm_agent in all_candidates:
            # Skip if author is self
            if agent_id == author_id:
                continue

            # Decide whether to evaluate secondary follow based on probability
            if random.random() >= self.probability_of_secondary_follow:
                continue

            # Get current follow relationship status
            is_following = ray.get(
                self.server.check_follow_relationship.remote(agent_id, author_id)
            )

            if is_llm_agent:
                # LLM-based: Ask LLM whether to follow/unfollow based on post content
                future = self.llm_manager.generate_secondary_follow_decision(
                    cluster_id, post_content, is_following, agent_id
                )
                pending_secondary_follow_llm.append(
                    (agent_id, cluster_id, author_id, is_following, future)
                )
            else:
                # Rule-based: Randomly decide to follow/unfollow
                decision = random.choice(["follow", "unfollow", "no_change"])

                if decision == "follow" and not is_following:
                    # Follow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "FOLLOW", target_user_id=author_id)
                    )
                elif decision == "unfollow" and is_following:
                    # Unfollow the author
                    actions.append(
                        ActionDTO(agent_id, cluster_id, "UNFOLLOW", target_user_id=author_id)
                    )

    def process_reciprocal_follows(self, actions: List[ActionDTO], agent_profiles: list) -> None:
        """
        Process reciprocal follow/unfollow events triggered by explicit FOLLOW/UNFOLLOW actions.
        """
        if self.probability_of_follow_back <= 0 or not actions:
            return

        by_id = {getattr(agent, "id", None): agent for agent in agent_profiles}
        pending_llm = []
        explicit_actions = [
            action
            for action in list(actions)
            if getattr(action, "action_type", None) in {"FOLLOW", "UNFOLLOW"}
            and getattr(action, "target_user_id", None) is not None
        ]

        for action in explicit_actions:
            if random.random() >= self.probability_of_follow_back:
                continue

            actor_id = action.agent_id
            target_id = action.target_user_id
            if actor_id == target_id:
                continue

            target_agent = by_id.get(target_id)
            source_agent = by_id.get(actor_id)
            if target_agent is None:
                continue

            reverse_exists = ray.get(
                self.server.check_follow_relationship.remote(target_id, actor_id)
            )
            normalized_action = str(action.action_type).strip().upper()
            if normalized_action == "FOLLOW" and reverse_exists:
                continue
            if normalized_action == "UNFOLLOW" and not reverse_exists:
                continue

            if getattr(target_agent, "llm", False):
                future = self.llm_manager.generate_reciprocal_follow_decision(
                    target_agent.cluster,
                    source_agent.__dict__ if source_agent is not None else {},
                    normalized_action.lower(),
                    agent_attrs=target_agent.__dict__,
                    agent_id=target_agent.id,
                )
                pending_llm.append((target_agent, actor_id, normalized_action, future))
            else:
                actions.append(
                    ActionDTO(
                        target_agent.id,
                        target_agent.cluster,
                        normalized_action,
                        target_user_id=actor_id,
                    )
                )

        if pending_llm:
            futures = [item[3] for item in pending_llm]
            results = ray.get(futures)
            for idx, decision in enumerate(results):
                target_agent, actor_id, normalized_action, _ = pending_llm[idx]
                if str(decision or "").strip().lower() == normalized_action.lower():
                    actions.append(
                        ActionDTO(
                            target_agent.id,
                            target_agent.cluster,
                            normalized_action,
                            target_user_id=actor_id,
                        )
                    )
