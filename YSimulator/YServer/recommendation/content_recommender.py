"""
Content recommendation engine.

Handles content (post) recommendations with pluggable strategies for different recommendation modes.
"""

import logging
from typing import List, Optional

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
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize content recommender.
        
        Args:
            db_adapter: Database adapter (with engine, redis_client, use_redis flag)
            visibility_rounds: Number of rounds posts remain visible
            logger: Logger instance
        """
        self.db = db_adapter
        self.visibility_rounds = visibility_rounds
        self.logger = logger or logging.getLogger(__name__)
    
    def get_recommended_posts(
        self,
        agent_id: str,
        mode: str = "random",
        limit: int = 5,
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
            # Calculate visibility threshold
            visibility_day, visibility_hour = self._calculate_visibility_params(
                day, slot, self.visibility_rounds
            )
            
            if self.db.use_redis:
                post_ids = self._get_recommendations_redis(
                    agent_id, mode, limit, followers_ratio
                )
            else:
                post_ids = self._get_recommendations_sql(
                    agent_id, mode, limit, followers_ratio, visibility_day, visibility_hour
                )
            
            self.logger.info(
                f"Recommended {len(post_ids)} posts (mode={mode})",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "mode": mode,
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
        if mode == "rchrono":
            return content_recsys_redis.recommend_rchrono_redis(**common_kwargs)
        elif mode == "rchrono_popularity":
            return content_recsys_redis.recommend_rchrono_popularity_redis(**common_kwargs)
        elif mode == "rchrono_followers":
            return content_recsys_redis.recommend_rchrono_followers_redis(**common_kwargs)
        elif mode == "rchrono_followers_popularity":
            return content_recsys_redis.recommend_rchrono_followers_popularity_redis(**common_kwargs)
        elif mode == "rchrono_comments":
            return content_recsys_redis.recommend_rchrono_comments_redis(**common_kwargs)
        elif mode == "common_interests":
            return content_recsys_redis.recommend_common_interests_redis(**common_kwargs)
        elif mode == "common_user_interests":
            return content_recsys_redis.recommend_common_user_interests_redis(**common_kwargs)
        elif mode == "similar_users_react":
            return content_recsys_redis.recommend_similar_users_react_redis(**common_kwargs)
        elif mode == "similar_users_posts":
            return content_recsys_redis.recommend_similar_users_posts_redis(**common_kwargs)
        else:
            # Default: random ordering
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
        from sqlalchemy.orm import Session
        
        session = Session(self.db.engine)
        try:
            if mode == "rchrono":
                return content_recsys_db.recommend_rchrono(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "rchrono_popularity":
                return content_recsys_db.recommend_rchrono_popularity(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "rchrono_followers":
                return content_recsys_db.recommend_rchrono_followers(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "rchrono_followers_popularity":
                return content_recsys_db.recommend_rchrono_followers_popularity(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "rchrono_comments":
                return content_recsys_db.recommend_rchrono_comments(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "common_interests":
                return content_recsys_db.recommend_common_interests(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "common_user_interests":
                return content_recsys_db.recommend_common_user_interests(
                    session, agent_id, visibility_day, visibility_hour, limit, followers_ratio
                )
            elif mode == "similar_users_react":
                return content_recsys_db.recommend_similar_users_react(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            elif mode == "similar_users_posts":
                return content_recsys_db.recommend_similar_users_posts(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
            else:
                # Random ordering (default)
                return content_recsys_db.recommend_random(
                    session, agent_id, visibility_day, visibility_hour, limit
                )
        finally:
            session.close()
    
    def _calculate_visibility_params(
        self, day: int, slot: int, visibility_rounds: int
    ) -> tuple:
        """
        Calculate visibility threshold parameters.
        
        Args:
            day: Current simulation day
            slot: Current simulation slot
            visibility_rounds: Number of rounds posts remain visible
            
        Returns:
            Tuple of (visibility_day, visibility_hour)
        """
        # Calculate how many full days worth of slots are in visibility_rounds
        slots_per_day = 24  # Assuming 24 slots per day
        visibility_total_slots = day * slots_per_day + slot - visibility_rounds
        
        if visibility_total_slots < 0:
            visibility_day = 0
            visibility_hour = 0
        else:
            visibility_day = visibility_total_slots // slots_per_day
            visibility_hour = visibility_total_slots % slots_per_day
        
        return visibility_day, visibility_hour
