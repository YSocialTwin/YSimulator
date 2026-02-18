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
                elif mode == "Activity":
                    suggestions = follow_recsys_db.recommend_activity(
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
                elif mode == "TwoHopEgoSampling":
                    suggestions = follow_recsys_db.recommend_two_hop_ego_sampling(
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
            # Check if user data is available in Redis
            user_ids_key = self.db._redis_key("user_mgmt", "ids")
            # scard returns 0 for non-existent keys, so no need for exists() check
            user_count = self.db.redis_client.scard(user_ids_key)
            
            # If no users in Redis, try to populate from SQL first
            if user_count == 0:
                self.logger.info(
                    f"Redis user cache empty for agent {agent_id}, attempting to populate from SQL",
                    extra={"extra_data": {"agent_id": agent_id, "mode": mode}}
                )
                
                # Try to populate Redis from SQL
                populated = self._populate_redis_users_from_sql()
                
                if populated:
                    # Re-check user count after population
                    user_count = self.db.redis_client.scard(user_ids_key)
                    self.logger.info(
                        f"Populated {user_count} users into Redis cache from SQL",
                        extra={"extra_data": {"user_count": user_count}}
                    )
                
                # If still no users, fall back to SQL-based recommendations
                # (SQL backend handles empty user case gracefully)
                if user_count == 0:
                    self.logger.info(
                        f"Redis user population completed but no users found, using SQL-based recommendations",
                        extra={"extra_data": {"agent_id": agent_id, "mode": mode}}
                    )
                    return self._get_suggestions_sql(agent_id, mode, n_neighbors, leaning_bias)
            
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
            elif mode == "Activity":
                recommendations = follow_recsys_redis.recommend_activity_redis(
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
            elif mode == "TwoHopEgoSampling":
                recommendations = follow_recsys_redis.recommend_two_hop_ego_sampling_redis(
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
            
            # If no recommendations found, fall back to SQL
            if not recommendations:
                self.logger.info(
                    f"No follow recommendations from Redis for agent {agent_id}, falling back to SQL",
                    extra={"extra_data": {"agent_id": agent_id, "mode": mode}}
                )
                return self._get_suggestions_sql(agent_id, mode, n_neighbors, leaning_bias)

            return recommendations

        except Exception as e:
            self.logger.error(
                f"Error getting Redis follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}},
            )
            # Fallback to random
            return self._get_fallback_suggestions_redis(agent_id, n_neighbors)

    def _populate_redis_users_from_sql(self) -> bool:
        """
        Populate Redis user cache from SQL database.
        
        This is called when Redis user cache is empty but we want to use Redis for performance.
        It loads all users from SQL and registers them in Redis.
        
        Returns:
            bool: True if users were successfully populated, False otherwise
        """
        try:
            from sqlalchemy.orm import Session
            from YSimulator.YServer.classes.models import User_mgmt
            
            with Session(self.db.engine) as session:
                # Get all users from SQL
                users = session.query(User_mgmt).all()
                
                if not users:
                    return False
                
                # Register each user in Redis
                user_ids_key = self.db._redis_key("user_mgmt", "ids")
                count = 0
                
                for user in users:
                    try:
                        # Add to user IDs set
                        self.db.redis_client.sadd(user_ids_key, user.id)
                        
                        # Store user data as hash
                        user_key = self.db._redis_key("user_mgmt", user.id)
                        user_data = {
                            "id": user.id,
                            "username": user.username,
                            "archetype": user.archetype,
                        }
                        # Filter out None values
                        user_data = {k: v for k, v in user_data.items() if v is not None}
                        self.db.redis_client.hset(user_key, mapping=user_data)
                        
                        # Create username index
                        if user.username:
                            username_key = self.db._redis_key("user_mgmt:by_username", user.username)
                            self.db.redis_client.set(username_key, user.id)
                        
                        count += 1
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to populate user {user.id} in Redis: {e}",
                            extra={"extra_data": {"user_id": user.id, "error": str(e)}}
                        )
                        continue
                
                self.logger.info(
                    f"Successfully populated {count} users from SQL to Redis cache",
                    extra={"extra_data": {"users_populated": count}}
                )
                return count > 0
                
        except Exception as e:
            self.logger.error(
                f"Error populating Redis users from SQL: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return False

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
