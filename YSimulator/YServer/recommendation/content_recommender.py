"""
Content recommendation engine.

Handles content (post) recommendations with pluggable strategies for different recommendation modes.
"""

import logging
from typing import List, Optional

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.orm import Session

from YSimulator.YServer.recsys import content_recsys_db, content_recsys_redis


class ContentRecommender:
    """
    Content recommendation engine for posts.

    Encapsulates all content recommendation logic and strategies,
    supporting both SQL and Redis backends.
    """

    def __init__(
        self,
        db_adapter,
        visibility_rounds: int,
        num_slots_per_day: int = 24,
        default_limit: int = 5,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize content recommender.

        Args:
            db_adapter: Database adapter (with engine, redis_client, use_redis flag)
            visibility_rounds: Number of rounds posts remain visible
            num_slots_per_day: Number of time slots per simulation day (default: 24)
            default_limit: Default number of posts when request limit is not specified
            logger: Logger instance
        """
        self.db = db_adapter
        self.visibility_rounds = visibility_rounds
        self.num_slots_per_day = num_slots_per_day
        self.default_limit = default_limit
        self.logger = logger or logging.getLogger(__name__)

    def get_recommended_posts(
        self,
        agent_id: str,
        mode: str = "random",
        limit: Optional[int] = None,
        followers_ratio: float = 0.6,
        day: int = None,
        slot: int = None,
    ) -> List[str]:
        """
        Get recommended posts for an agent using the specified recommendation strategy.

        Args:
            agent_id: UUID of the agent requesting recommendations
            mode: Recommendation mode (random, rchrono, rchrono_popularity, etc.)
            limit: Number of posts to recommend
            followers_ratio: Ratio of posts from followers vs others
            day: Current simulation day (for visibility calculation)
            slot: Current simulation slot (for visibility calculation)

        Returns:
            List of post UUIDs recommended for the agent
        """
        try:
            if limit is None:
                limit = self.default_limit

            # Debug logging for incoming request
            self.logger.debug(
                f"get_recommended_posts called: agent={agent_id}, mode={mode}, limit={limit}",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "mode": mode,
                        "limit": limit,
                        "followers_ratio": followers_ratio,
                        "day": day,
                        "slot": slot,
                    }
                },
            )

            # Calculate visibility threshold
            visibility_day, visibility_hour = self._calculate_visibility_params(
                day, slot, self.visibility_rounds
            )

            used_fallback = False
            if self.db.use_redis:
                result = self._get_recommendations_redis(agent_id, mode, limit, followers_ratio)
                # Check if result is a tuple (new recommenders with fallback)
                if isinstance(result, tuple):
                    post_ids, used_fallback = result
                else:
                    post_ids = result
            else:
                result = self._get_recommendations_sql(
                    agent_id, mode, limit, followers_ratio, visibility_day, visibility_hour
                )
                # Check if result is a tuple (new recommenders with fallback)
                if isinstance(result, tuple):
                    post_ids, used_fallback = result
                else:
                    post_ids = result

            # Update mode name if fallback was used
            post_ids = self._filter_shadow_banned_posts(post_ids, day=day, slot=slot)
            log_mode = f"{mode}-Random" if used_fallback else mode

            self.logger.info(
                f"Recommended {len(post_ids)} posts (mode={log_mode})",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "mode": log_mode,
                        "limit": limit,
                        "found": len(post_ids),
                    }
                },
            )

            return post_ids

        except Exception as e:
            self.logger.error(
                f"Error getting recommended posts: {e}",
                extra={"extra_data": {"agent_id": agent_id, "mode": mode, "error": str(e)}},
            )
            return []

    def _get_recommendations_redis(
        self,
        agent_id: str,
        mode: str,
        limit: int,
        followers_ratio: float,
    ) -> List[str]:
        """Get recommendations using Redis backend."""
        # Get recent posts from Redis
        recent_posts_key = self.db._redis_key("posts", "recent")
        all_post_ids = self.db.redis_client.lrange(recent_posts_key, 0, -1)

        # Use Redis pipeline to fetch post data efficiently
        if all_post_ids:
            pipeline = self.db.redis_client.pipeline()
            for post_id in all_post_ids:
                post_key = self.db._redis_key("posts", post_id)
                pipeline.hgetall(post_key)

            posts_data = pipeline.execute()

            # Build list of valid posts with metadata
            valid_posts_with_data = []
            for i, post_data in enumerate(posts_data):
                if post_data:
                    post_user_id = post_data.get("user_id")
                    # Exclude own posts
                    if post_user_id and post_user_id != agent_id:
                        valid_posts_with_data.append(
                            {
                                "id": all_post_ids[i],
                                "index": i,
                                "reaction_count": int(post_data.get("reaction_count", 0) or 0),
                            }
                        )
        else:
            valid_posts_with_data = []
            posts_data = []

        # If no valid posts in Redis, fall back to SQL
        if not valid_posts_with_data:
            # Determine why we're falling back for better logging
            if not all_post_ids:
                reason = "no posts in Redis cache"
            elif not posts_data:
                reason = "post data could not be fetched from Redis"
            else:
                # Posts exist but were filtered out (likely all from agent)
                reason = (
                    f"no posts from other users (found {len(all_post_ids)} posts, all filtered)"
                )

            self.logger.info(
                f"No valid posts for recommendations - {reason}, falling back to SQL",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "mode": mode,
                        "total_posts_in_redis": len(all_post_ids) if all_post_ids else 0,
                        "reason": reason,
                    }
                },
            )
            # Calculate visibility parameters for SQL fallback
            # Pass None for day and slot to use default visibility calculation
            visibility_day, visibility_hour = self._calculate_visibility_params(
                None, None, self.visibility_rounds
            )
            return self._get_recommendations_sql(
                agent_id, mode, limit, followers_ratio, visibility_day, visibility_hour
            )

        # Prepare common kwargs for recommendation functions
        common_kwargs = {
            "valid_posts_with_data": valid_posts_with_data,
            "limit": limit,
            "agent_id": agent_id,
            "all_post_ids": all_post_ids,
            "posts_data": posts_data,
            "followers_ratio": followers_ratio,
            "db_engine": self.db.engine,
            "redis_client": self.db.redis_client,
            "redis_key_fn": self.db._redis_key,
            "logger": self.logger,
        }

        # Dispatch to appropriate recommendation function
        self.logger.debug(
            f"Dispatching to recommendation function for mode: {mode}",
            extra={"extra_data": {"mode": mode, "agent_id": agent_id}},
        )

        if mode == "ReverseChrono":
            return content_recsys_redis.recommend_rchrono_redis(**common_kwargs)
        elif mode == "ReverseChronoPopularity":
            return content_recsys_redis.recommend_rchrono_popularity_redis(**common_kwargs)
        elif mode == "ReverseChronoFollowers":
            return content_recsys_redis.recommend_rchrono_followers_redis(**common_kwargs)
        elif mode == "ReverseChronoFollowersPopularity":
            return content_recsys_redis.recommend_rchrono_followers_popularity_redis(
                **common_kwargs
            )
        elif mode == "ReverseChronoComments":
            return content_recsys_redis.recommend_rchrono_comments_redis(**common_kwargs)
        elif mode == "CommonInterests":
            return content_recsys_redis.recommend_common_interests_redis(**common_kwargs)
        elif mode == "CommonUserInterests":
            return content_recsys_redis.recommend_common_user_interests_redis(**common_kwargs)
        elif mode == "SimilarUsersReactions":
            return content_recsys_redis.recommend_similar_users_react_redis(**common_kwargs)
        elif mode == "SimilarUsersPosts":
            return content_recsys_redis.recommend_similar_users_posts_redis(**common_kwargs)
        elif mode == "CollaborativeUserUser":
            return content_recsys_redis.recommend_collaborative_user_user_redis(**common_kwargs)
        elif mode == "CollaborativeItemItem":
            return content_recsys_redis.recommend_collaborative_item_item_redis(**common_kwargs)
        elif mode == "ContentBasedFeatures":
            return content_recsys_redis.recommend_content_based_features_redis(**common_kwargs)
        elif mode == "ContentBasedVector":
            return content_recsys_redis.recommend_content_based_vector_redis(**common_kwargs)
        elif mode == "HybridLinearRanker":
            self.logger.debug(
                f"Calling HybridLinearRanker for agent {agent_id}",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "valid_posts_count": len(valid_posts_with_data),
                    }
                },
            )
            return content_recsys_redis.recommend_hybrid_linear_ranker_redis(**common_kwargs)
        else:
            # Default: random ordering
            self.logger.debug(
                f"Mode '{mode}' not recognized, using random ordering",
                extra={"extra_data": {"mode": mode, "agent_id": agent_id}},
            )
            return content_recsys_redis.recommend_random_redis(**common_kwargs)

    def _get_recommendations_sql(
        self,
        agent_id: str,
        mode: str,
        limit: int,
        followers_ratio: float,
        visibility_day: int,
        visibility_hour: int,
    ) -> List[str]:
        """Get recommendations using SQL backend."""
        session = Session(self.db.engine)
        try:
            if mode == "ReverseChrono":
                return content_recsys_db.recommend_rchrono(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "ReverseChronoPopularity":
                return content_recsys_db.recommend_rchrono_popularity(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "ReverseChronoFollowers":
                return content_recsys_db.recommend_rchrono_followers(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "ReverseChronoFollowersPopularity":
                return content_recsys_db.recommend_rchrono_followers_popularity(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "ReverseChronoComments":
                return content_recsys_db.recommend_rchrono_comments(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "CommonInterests":
                return content_recsys_db.recommend_common_interests(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "CommonUserInterests":
                return content_recsys_db.recommend_common_user_interests(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "SimilarUsersReactions":
                return content_recsys_db.recommend_similar_users_react(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "SimilarUsersPosts":
                return content_recsys_db.recommend_similar_users_posts(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "CollaborativeUserUser":
                return content_recsys_db.recommend_collaborative_user_user(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "CollaborativeItemItem":
                return content_recsys_db.recommend_collaborative_item_item(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "ContentBasedFeatures":
                return content_recsys_db.recommend_content_based_features(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "ContentBasedVector":
                return content_recsys_db.recommend_content_based_vector(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "HybridLinearRanker":
                return content_recsys_db.recommend_hybrid_linear_ranker(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            else:
                # Random ordering (default)
                return content_recsys_db.recommend_random(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
        finally:
            session.close()

    def _filter_shadow_banned_posts(
        self,
        post_ids: List[str],
        *,
        day: Optional[int],
        slot: Optional[int],
    ) -> List[str]:
        if not post_ids or day is None or slot is None:
            return post_ids
        try:
            if "shadow_ban" not in inspect(self.db.engine).get_table_names():
                return post_ids
            session = Session(self.db.engine)
            try:
                metadata = MetaData()
                post = Table("post", metadata, autoload_with=self.db.engine)
                rounds = Table("rounds", metadata, autoload_with=self.db.engine)
                shadow_ban = Table("shadow_ban", MetaData(), autoload_with=self.db.engine)
                current_total_rounds = int(day) * self.num_slots_per_day + int(slot)
                active_banned_user_ids = [
                    str(row[0])
                    for row in session.execute(
                        select(shadow_ban.c.uid)
                        .select_from(
                            shadow_ban.join(
                                rounds,
                                rounds.c.id == shadow_ban.c.start_tid,
                            )
                        )
                        .where(
                            ((rounds.c.day * self.num_slots_per_day) + rounds.c.hour)
                            <= current_total_rounds
                        )
                        .where(
                            (shadow_ban.c.duration.is_(None))
                            | (
                                ((rounds.c.day * self.num_slots_per_day) + rounds.c.hour + shadow_ban.c.duration)
                                >= current_total_rounds
                            )
                        )
                    ).all()
                ]
                if not active_banned_user_ids:
                    return post_ids
                banned_post_ids = {
                    str(post_id)
                    for (post_id,) in session.execute(
                        select(post.c.id)
                        .where(post.c.id.in_(post_ids))
                        .where(post.c.user_id.in_(active_banned_user_ids))
                    ).all()
                }
                if not banned_post_ids:
                    return post_ids
                return [post_id for post_id in post_ids if str(post_id) not in banned_post_ids]
            finally:
                session.close()
        except Exception:
            return post_ids

    def _calculate_visibility_params(self, day: int, slot: int, visibility_rounds: int) -> tuple:
        """
        Calculate visibility threshold parameters.

        Args:
            day: Current simulation day (can be None to use default)
            slot: Current simulation slot (can be None to use default)
            visibility_rounds: Number of rounds posts remain visible

        Returns:
            Tuple of (visibility_day, visibility_hour)
            Returns (0, 0) when inputs are None, which shows all posts regardless of age
        """
        # Handle None inputs by defaulting to 0 (show all posts regardless of age)
        if day is None or slot is None:
            return 0, 0

        # Calculate how many full days worth of slots are in visibility_rounds
        visibility_total_slots = day * self.num_slots_per_day + slot - visibility_rounds

        if visibility_total_slots < 0:
            visibility_day = 0
            visibility_hour = 0
        else:
            visibility_day = visibility_total_slots // self.num_slots_per_day
            visibility_hour = visibility_total_slots % self.num_slots_per_day

        return visibility_day, visibility_hour
