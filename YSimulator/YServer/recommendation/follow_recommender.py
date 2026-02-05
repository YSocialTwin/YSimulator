"""
Follow recommendation engine.

Handles follow (user) recommendations with pluggable strategies for different recommendation modes.
"""

import logging
import random
from typing import List, Optional

from YSimulator.YServer.recsys import follow_recsys_db, follow_recsys_redis


class FollowRecommender:
    """
    Follow recommendation engine for user suggestions.

    Encapsulates all follow recommendation logic and strategies,
    supporting both SQL and Redis backends.
    """

    def __init__(self, db_adapter, logger: Optional[logging.Logger] = None):
        """
        Initialize follow recommender.

        Args:
            db_adapter: Database adapter (with engine, redis_client, use_redis flag)
            logger: Logger instance
        """
        self.db = db_adapter
        self.logger = logger or logging.getLogger(__name__)

    def get_follow_suggestions(
        self,
        agent_id: str,
        mode: str = "FollowRecSys",
        n_neighbors: int = 5,
        leaning_bias: int = 0,
    ) -> List[str]:
        """
        Get follow suggestions for an agent.

        Args:
            agent_id: UUID of the agent requesting suggestions
            mode: Recommendation mode (random, CommonNeighbors, Jaccard, etc.)
            n_neighbors: Number of suggestions to return
            leaning_bias: Political leaning bias strength (0 = no bias)

        Returns:
            List of user UUIDs recommended to follow
        """
        try:
            if self.db.use_redis:
                suggestions = self._get_suggestions_redis(agent_id, mode, n_neighbors, leaning_bias)
            else:
                suggestions = self._get_suggestions_sql(agent_id, mode, n_neighbors, leaning_bias)

            self.logger.info(
                f"Generated {len(suggestions)} follow suggestions (mode={mode})",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "mode": mode,
                        "n_neighbors": n_neighbors,
                        "found": len(suggestions),
                    }
                },
            )

            return suggestions

        except Exception as e:
            self.logger.error(
                f"Error getting follow suggestions: {e}",
                extra={"extra_data": {"agent_id": agent_id, "mode": mode, "error": str(e)}},
            )
            return []

    def _get_suggestions_sql(
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int,
    ) -> List[str]:
        """Get follow suggestions using SQL backend."""
        try:
            from sqlalchemy import and_, func
            from sqlalchemy.orm import Session

            from YSimulator.YServer.classes.models import Follow, User_mgmt

            with Session(self.db.engine) as session:
                # Get agent's info
                agent = session.query(User_mgmt).filter_by(id=agent_id).first()
                if not agent:
                    self.logger.warning(f"Agent {agent_id} not found for follow suggestions")
                    return []

                # Get users that agent is currently following
                latest_follows_subq = (
                    session.query(
                        Follow.follower_id,
                        Follow.user_id,
                        func.max(Follow.round).label("max_round"),
                    )
                    .filter(Follow.follower_id == agent_id)
                    .group_by(Follow.follower_id, Follow.user_id)
                    .subquery()
                )

                following = (
                    session.query(Follow.user_id)
                    .join(
                        latest_follows_subq,
                        and_(
                            Follow.follower_id == latest_follows_subq.c.follower_id,
                            Follow.user_id == latest_follows_subq.c.user_id,
                            Follow.round == latest_follows_subq.c.max_round,
                            Follow.action == "follow",
                        ),
                    )
                    .all()
                )
                following_ids = {f.user_id for f in following}

                # Dispatch to appropriate recommendation function
                if mode == "FollowRecSys":
                    suggestions = follow_recsys_db.recommend_random_follows(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "CommonNeighbors":
                    suggestions = follow_recsys_db.recommend_common_neighbors(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "Jaccard":
                    suggestions = follow_recsys_db.recommend_jaccard(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "AdamicAdar":
                    suggestions = follow_recsys_db.recommend_adamic_adar(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "PreferentialAttachment":
                    suggestions = follow_recsys_db.recommend_preferential_attachment(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "ResourceAllocation":
                    suggestions = follow_recsys_db.recommend_resource_allocation(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "CosineSimilarity":
                    suggestions = follow_recsys_db.recommend_cosine_similarity(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "CoEngagement":
                    suggestions = follow_recsys_db.recommend_co_engagement(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "RandomWalkRestart":
                    suggestions = follow_recsys_db.recommend_random_walk_with_restart(
                        session, agent_id, following_ids, n_neighbors
                    )
                elif mode == "ReactionsOnContent":
                    suggestions = follow_recsys_db.recommend_reactions_on_content(
                        session, agent_id, following_ids, n_neighbors
                    )
                else:
                    # Unknown mode, fallback to random
                    self.logger.warning(f"Unknown follow mode: {mode}, using random")
                    suggestions = follow_recsys_db.recommend_random_follows(
                        session, agent_id, following_ids, n_neighbors
                    )

                # Apply leaning bias if requested
                suggestions = follow_recsys_db.apply_leaning_bias(
                    session, agent_id, suggestions, leaning_bias, n_neighbors
                )

                return suggestions[:n_neighbors]

        except Exception as e:
            self.logger.error(
                f"Error getting SQL follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}},
            )
            # Fallback to simple random
            return self._get_fallback_suggestions_sql(agent_id, n_neighbors)

    def _get_suggestions_redis(
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int,
    ) -> List[str]:
        """Get follow suggestions using Redis backend."""
        try:
            # Dispatch to appropriate recommendation function
            if mode == "FollowRecSys":
                recommendations = follow_recsys_redis.recommend_random_follows_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "PreferentialAttachment":
                recommendations = follow_recsys_redis.recommend_preferential_attachment_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "CommonNeighbors":
                recommendations = follow_recsys_redis.recommend_common_neighbors_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "Jaccard":
                recommendations = follow_recsys_redis.recommend_jaccard_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "AdamicAdar":
                recommendations = follow_recsys_redis.recommend_adamic_adar_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "ResourceAllocation":
                recommendations = follow_recsys_redis.recommend_resource_allocation_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "CosineSimilarity":
                recommendations = follow_recsys_redis.recommend_cosine_similarity_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "CoEngagement":
                recommendations = follow_recsys_redis.recommend_co_engagement_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "RandomWalkRestart":
                recommendations = follow_recsys_redis.recommend_random_walk_with_restart_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            elif mode == "ReactionsOnContent":
                recommendations = follow_recsys_redis.recommend_reactions_on_content_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )
            else:
                # Unknown mode, fallback to random
                self.logger.warning(f"Unknown follow recommendation mode: {mode}, using random")
                recommendations = follow_recsys_redis.recommend_random_follows_redis(
                    self.db.redis_client, self.db._redis_key, agent_id, n_neighbors, self.logger
                )

            # Apply political leaning bias if specified
            if leaning_bias > 0 and recommendations:
                recommendations = follow_recsys_redis.apply_leaning_bias_redis(
                    self.db.redis_client,
                    self.db._redis_key,
                    agent_id,
                    recommendations,
                    leaning_bias,
                    self.logger,
                )

            return recommendations

        except Exception as e:
            self.logger.error(
                f"Error getting Redis follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}},
            )
            # Fallback to random
            return self._get_fallback_suggestions_redis(agent_id, n_neighbors)

    def _get_fallback_suggestions_sql(self, agent_id: str, n_neighbors: int) -> List[str]:
        """Fallback to simple random SQL suggestions."""
        try:
            from sqlalchemy.orm import Session

            from YSimulator.YServer.classes.models import User_mgmt

            with Session(self.db.engine) as session:
                candidates = (
                    session.query(User_mgmt.id)
                    .filter(User_mgmt.id != agent_id)
                    .limit(n_neighbors * 2)
                    .all()
                )
                candidate_ids = [c.id for c in candidates]
                random.shuffle(candidate_ids)
                return candidate_ids[:n_neighbors]
        except Exception as e:
            self.logger.error(f"Failed to get fallback SQL follow suggestions: {e}")
            return []

    def _get_fallback_suggestions_redis(self, agent_id: str, n_neighbors: int) -> List[str]:
        """Fallback to simple random Redis suggestions."""
        try:
            user_ids_key = self.db._redis_key("user_mgmt", "ids")
            all_user_ids = list(self.db.redis_client.smembers(user_ids_key))
            candidates = [uid for uid in all_user_ids if uid != agent_id]
            random.shuffle(candidates)
            return candidates[:n_neighbors]
        except Exception as e:
            self.logger.error(f"Failed to get fallback Redis follow suggestions: {e}")
            return []
