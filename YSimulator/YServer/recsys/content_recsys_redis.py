"""
Redis-based content recommendation strategies.

Each function implements a specific recommendation algorithm using Redis key-value operations.
"""

import random
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session, aliased

from YSimulator.YServer.classes.models import (
    Follow,
    PostTopic,
    Reaction,
    Round,
    User_mgmt,
    UserInterest,
)

# Constants for hybrid linear ranker
RECENT_AFFINITY_DISCOUNT = 0.5  # Weight for recent interactions (50% of total affinity)
SIMILAR_USERS_SAMPLE_LIMIT = 100  # Max users to consider for similarity calculation (performance)


def _normalize_set(values) -> Set[str]:
    """Normalize Redis/SQL iterable values to a set of strings."""
    return {
        (v.decode() if isinstance(v, bytes) else str(v))
        for v in (values or [])
        if v is not None and str(v) != ""
    }


def _read_set(redis_client, key: str) -> Set[str]:
    """Read a Redis set if it exists."""
    if redis_client.exists(key):
        return _normalize_set(redis_client.smembers(key))
    return set()


def _get_user_interests(
    agent_id: str,
    redis_client,
    redis_key_fn,
    db_engine=None,
) -> Set[str]:
    """Get user interests from Redis with SQL fallback."""
    candidates = [
        redis_key_fn("user", agent_id) + ":interests",
        redis_key_fn("user_interests", agent_id),
    ]
    for key in candidates:
        if redis_client.exists(key):
            return _normalize_set(redis_client.smembers(key))

    if db_engine is None:
        return set()

    with Session(db_engine) as session:
        query = session.query(UserInterest.interest_id).filter(UserInterest.user_id == agent_id)
        return {row[0] for row in query.all()}


def _get_post_topics(
    post_id: str,
    redis_client,
    redis_key_fn,
    db_engine=None,
) -> Set[str]:
    """Get post topics from Redis with SQL fallback."""
    candidates = [
        redis_key_fn("post", post_id) + ":topics",
        redis_key_fn("post_topics", post_id),
    ]
    for key in candidates:
        if redis_client.exists(key):
            return _normalize_set(redis_client.smembers(key))

    if db_engine is None:
        return set()

    with Session(db_engine) as session:
        query = session.query(PostTopic.topic_id).filter(PostTopic.post_id == post_id)
        return {row[0] for row in query.all()}


def _get_post_reaction_users(
    post_id: str,
    redis_client,
    redis_key_fn,
    db_engine=None,
) -> Set[str]:
    """Get users who liked a post from Redis with SQL fallback."""
    key = redis_key_fn("post", post_id) + ":reactions"
    if redis_client.exists(key):
        return _normalize_set(redis_client.smembers(key))

    if db_engine is None:
        return set()

    with Session(db_engine) as session:
        query = session.query(Reaction.user_id).filter(
            Reaction.post_id == post_id, Reaction.type == "LIKE"
        )
        return {row[0] for row in query.all()}


def _get_user_likes(user_id: str, redis_client, redis_key_fn, db_engine=None) -> Set[str]:
    """Get posts liked by user from Redis with SQL fallback."""
    key = redis_key_fn("user", user_id) + ":likes"
    if redis_client.exists(key):
        return _normalize_set(redis_client.smembers(key))

    if db_engine is None:
        return set()

    with Session(db_engine) as session:
        query = session.query(Reaction.post_id).filter(
            Reaction.user_id == user_id, Reaction.type == "LIKE"
        )
        return {row[0] for row in query.all()}


def _get_user_follows(user_id: str, redis_client, redis_key_fn, db_engine=None) -> Set[str]:
    """Get users followed by user from Redis with SQL fallback."""
    key = redis_key_fn("user", user_id) + ":follows"
    if redis_client.exists(key):
        return _normalize_set(redis_client.smembers(key))

    if db_engine is None:
        return set()

    with Session(db_engine) as session:
        query = session.query(Follow.user_id).filter(
            Follow.follower_id == user_id, Follow.action == "follow"
        )
        return {row[0] for row in query.all()}


def _get_user_profile(user_id: str, redis_client, redis_key_fn, db_engine=None) -> Dict[str, Any]:
    """Get user profile (age_group/gender/leaning) from Redis with SQL fallback."""
    for key in (redis_key_fn("users", user_id), redis_key_fn("user_mgmt", user_id)):
        if redis_client.exists(key):
            data = redis_client.hgetall(key)
            if data:
                return data

    if db_engine is None:
        return {}

    with Session(db_engine) as session:
        user = session.query(User_mgmt).filter(User_mgmt.id == user_id).first()
        if not user:
            return {}
        return {
            "age_group": getattr(user, "age_group", None),
            "gender": user.gender,
            "leaning": user.leaning,
        }


def recommend_rchrono_redis(
    valid_posts_with_data: List[Dict[str, Any]], limit: int, **kwargs
) -> List[str]:
    """
    Reverse chronological ordering - newest posts first.

    Args:
        valid_posts_with_data: List of post dictionaries with 'id', 'index', 'reaction_count'
        limit: Number of posts to recommend

    Returns:
        List of post IDs in reverse chronological order
    """
    # Redis recent list is already in reverse chronological order (newest first)
    # Just take the first 'limit' items
    return [p["id"] for p in valid_posts_with_data[:limit]]


def recommend_rchrono_popularity_redis(
    valid_posts_with_data: List[Dict[str, Any]], limit: int, **kwargs
) -> List[str]:
    """
    Reverse chronological with popularity boost.

    Now ensures that the full `limit` of posts is returned by including posts
    with 0 popularity if needed.

    Args:
        valid_posts_with_data: List of post dictionaries with 'id', 'index', 'reaction_count'
        limit: Number of posts to recommend

    Returns:
        List of post IDs sorted by time then popularity (always `limit` items or all available)
    """
    # Sort by popularity first, then recency (lower index = newer).
    sorted_posts = sorted(valid_posts_with_data, key=lambda x: (-x["reaction_count"], x["index"]))
    return [p["id"] for p in sorted_posts[:limit]]


def recommend_rchrono_followers_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    followers_ratio: float,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    db_engine,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Prioritize posts from followed users.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        followers_ratio: Ratio of posts from followers vs others (0.0-1.0)
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        db_engine: Database engine for follow queries

    Returns:
        Tuple of (List of post IDs prioritizing followed users, False indicating no fallback used)
    """
    follower_posts_limit = int(limit * followers_ratio)

    # Get followed user IDs from database using SQLAlchemy ORM
    with Session(db_engine) as session:
        query = session.query(Follow.user_id).filter(
            Follow.follower_id == agent_id, Follow.action == "follow"
        )
        followed_user_ids = set(row[0] for row in query.all())

    # Create mapping for efficient lookup (avoid O(n²))
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}

    # Filter posts by followed users
    follower_posts = []
    other_posts = []
    for post in valid_posts_with_data:
        post_data = post_id_to_data.get(post["id"])
        if post_data and post_data.get("user_id") in followed_user_ids:
            follower_posts.append(post)
        else:
            other_posts.append(post)

    # Take from followers first, then fill with others
    post_ids = [p["id"] for p in follower_posts[:follower_posts_limit]]
    if len(post_ids) < limit:
        remaining = limit - len(post_ids)
        post_ids.extend([p["id"] for p in other_posts[:remaining]])

    return post_ids, False


def recommend_rchrono_followers_popularity_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    followers_ratio: float,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    db_engine,
    **kwargs,
) -> List[str]:
    """
    Combine followers and popularity.

    Now ensures that the full `limit` of posts is returned by:
    1. Getting posts from followers (prioritized by popularity)
    2. Filling remaining slots with non-follower posts (by popularity)
    3. Automatically includes posts with 0 popularity if needed

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        followers_ratio: Ratio of posts from followers vs others
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        db_engine: Database engine for follow queries

    Returns:
        List of post IDs combining follower priority and popularity (always `limit` items or all available)
    """
    follower_posts_limit = int(limit * followers_ratio)

    # Get follow relationships using SQLAlchemy ORM
    with Session(db_engine) as session:
        query = session.query(Follow.user_id).filter(
            Follow.follower_id == agent_id, Follow.action == "follow"
        )
        followed_user_ids = set(row[0] for row in query.all())

    # Create mapping for efficient lookup
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}

    # Filter and sort
    follower_posts = []
    other_posts = []
    for post in valid_posts_with_data:
        post_data = post_id_to_data.get(post["id"])
        if post_data and post_data.get("user_id") in followed_user_ids:
            follower_posts.append(post)
        else:
            other_posts.append(post)

    # Sort by popularity first, then recency.
    follower_posts_sorted = sorted(follower_posts, key=lambda x: (-x["reaction_count"], x["index"]))
    other_posts_sorted = sorted(other_posts, key=lambda x: (-x["reaction_count"], x["index"]))

    # Build result ensuring we get the full limit
    post_ids = [p["id"] for p in follower_posts_sorted[:follower_posts_limit]]

    # Fill remaining slots with other posts
    if len(post_ids) < limit:
        remaining = limit - len(post_ids)
        post_ids.extend([p["id"] for p in other_posts_sorted[:remaining]])

    return post_ids


def recommend_rchrono_comments_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    **kwargs,
) -> List[str]:
    """
    Prioritize highly commented posts.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis

    Returns:
        List of post IDs sorted by comment count
    """
    # Count comments for each post
    posts_with_comment_counts = []
    for i, post_data in enumerate(posts_data):
        if post_data and post_data.get("user_id") != agent_id:
            post_id = all_post_ids[i]
            # Check if this is a top-level post (not a comment itself)
            if post_data.get("comment_to", "-1") == "-1":
                # Count comments by checking other posts
                comment_count = sum(
                    1 for pd in posts_data if pd and pd.get("comment_to") == post_id
                )
                posts_with_comment_counts.append(
                    {
                        "id": post_id,
                        "index": i,
                        "comment_count": comment_count,
                        "reaction_count": int(post_data.get("reaction_count", 0) or 0),
                    }
                )

    # Sort by comment count desc, then by recency
    sorted_posts = sorted(
        posts_with_comment_counts, key=lambda x: (-x["comment_count"], x["index"])
    )
    return [p["id"] for p in sorted_posts[:limit]]


def recommend_common_interests_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Posts matching user's topic interests.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs with matching topic interests, bool indicating if fallback was used)
    """
    user_interests = _get_user_interests(
        agent_id=agent_id,
        redis_client=redis_client,
        redis_key_fn=redis_key_fn,
        db_engine=db_engine,
    )
    if user_interests:

        # Score posts by number of matching interests
        posts_with_scores = []
        for post in valid_posts_with_data:
            post_topics = _get_post_topics(
                post_id=post["id"],
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
            )
            common_count = len(user_interests & post_topics)
            if common_count > 0:
                posts_with_scores.append(
                    {"id": post["id"], "index": post["index"], "score": common_count}
                )

        # Sort by score desc, then by recency
        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # Fallback to SQL query when Redis data not available yet
        logger.info(
            "Mode common_interests - Redis cache for interests/topics not available yet, using SQLAlchemy ORM"
        )
        with Session(db_engine) as session:
            from sqlalchemy import desc

            from YSimulator.YServer.classes.models import Post

            query = (
                session.query(UserInterest.interest_id)
                .filter(UserInterest.user_id == agent_id)
                .distinct()
            )

            user_interests = set(row[0] for row in query.all())

            if user_interests:
                post_query = (
                    session.query(PostTopic.post_id)
                    .join(Post, PostTopic.post_id == Post.id)
                    .join(Round, Post.round == Round.id)
                    .filter(PostTopic.topic_id.in_(user_interests), Post.user_id != agent_id)
                    .distinct()
                    .order_by(desc(Round.day), desc(Round.hour))
                    .limit(limit)
                )

                sql_post_ids = [row[0] for row in post_query.all()]
                post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
            else:
                sql_post_ids = []
                post_ids = []

            # Cold start check: if no results, return random posts
            if not post_ids:
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True

            if len(post_ids) < limit:
                additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                post_ids.extend(additional[: limit - len(post_ids)])

    return post_ids, False


def recommend_common_user_interests_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Posts interacted with by users who share interests.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs liked by users with common interests, bool indicating if fallback was used)
    """
    user_interests = _get_user_interests(
        agent_id=agent_id,
        redis_client=redis_client,
        redis_key_fn=redis_key_fn,
        db_engine=db_engine,
    )
    if user_interests:

        # Find users with common interests
        user_ids_key = redis_key_fn("user_mgmt", "ids")
        all_user_ids = (
            redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []
        )

        similar_users = set()
        for uid in all_user_ids:
            if uid != agent_id:
                other_interests = _get_user_interests(
                    agent_id=uid,
                    redis_client=redis_client,
                    redis_key_fn=redis_key_fn,
                    db_engine=db_engine,
                )
                if len(user_interests & other_interests) > 0:
                    similar_users.add(uid)

        # Get posts liked by similar users
        posts_with_scores = []

        for post in valid_posts_with_data:
            # Check if any similar user liked this post
            reaction_user_ids = _get_post_reaction_users(
                post_id=post["id"],
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
            )
            common_users = similar_users & reaction_user_ids
            if common_users:
                posts_with_scores.append(
                    {"id": post["id"], "index": post["index"], "score": len(common_users)}
                )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # Fallback to SQLAlchemy ORM
        logger.info(
            "Mode common_user_interests - Redis cache for interests not available yet, using SQLAlchemy ORM"
        )
        from sqlalchemy import desc
        from sqlalchemy.orm import aliased

        with Session(db_engine) as session:
            # Get user interests
            UserInterest1 = aliased(UserInterest)
            UserInterest2 = aliased(UserInterest)

            # Find posts liked by users with common interests
            from YSimulator.YServer.classes.models import Post

            query = (
                session.query(Reaction.post_id)
                .distinct()
                .join(UserInterest1, Reaction.user_id == UserInterest1.user_id)
                .join(UserInterest2, UserInterest1.interest_id == UserInterest2.interest_id)
                .join(Post, Reaction.post_id == Post.id)
                .join(Round, Post.round == Round.id)
                .filter(
                    UserInterest2.user_id == agent_id,
                    Reaction.user_id != agent_id,
                    Post.user_id != agent_id,
                    Reaction.type == "LIKE",
                )
                .order_by(desc(Round.day), desc(Round.hour))
                .limit(limit)
            )

            sql_post_ids = [row[0] for row in query.all()]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

            # Cold start check: if no results, return random posts
            if not post_ids:
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True

            if len(post_ids) < limit:
                additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                post_ids.extend(additional[: limit - len(post_ids)])

    return post_ids, False


def recommend_similar_users_react_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Posts liked by demographically similar users (by reactions).

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs liked by similar users, bool indicating if fallback was used)
    """
    # Get agent demographics from Redis/SQL
    agent_data = _get_user_profile(agent_id, redis_client, redis_key_fn, db_engine)

    if agent_data:
        # Redis implementation using cached user data
        agent_age_group = agent_data.get("age_group")
        agent_gender = agent_data.get("gender")
        agent_leaning = agent_data.get("leaning")

        # Create mapping

        # Get posts liked by similar users
        posts_with_scores = []
        for post in valid_posts_with_data:
            # Check reactions for this post
            reaction_user_ids = _get_post_reaction_users(
                post_id=post["id"],
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
            )
            similar_count = 0
            for uid in reaction_user_ids:
                user_data = _get_user_profile(uid, redis_client, redis_key_fn, db_engine)
                if user_data:
                    # Check similarity
                    if (
                        user_data.get("age_group") == agent_age_group
                        or user_data.get("gender") == agent_gender
                        or user_data.get("leaning") == agent_leaning
                    ):
                        similar_count += 1

            if similar_count > 0:
                posts_with_scores.append(
                    {"id": post["id"], "index": post["index"], "score": similar_count}
                )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # Fallback to SQLAlchemy ORM query
        logger.info("Mode similar_users_react - Using SQLAlchemy ORM for user demographics query")
        from sqlalchemy import desc, or_
        from sqlalchemy.orm import aliased

        with Session(db_engine) as session:
            ReactorUser = aliased(User_mgmt)
            TargetUser = aliased(User_mgmt)

            from YSimulator.YServer.classes.models import Post

            query = (
                session.query(Reaction.post_id)
                .distinct()
                .join(ReactorUser, Reaction.user_id == ReactorUser.id)
                .join(TargetUser, TargetUser.id == agent_id)
                .join(Post, Reaction.post_id == Post.id)
                .join(Round, Post.round == Round.id)
                .filter(
                    Post.user_id != agent_id,
                    ReactorUser.id != agent_id,
                    Reaction.type == "LIKE",
                    or_(
                        ReactorUser.age_group == TargetUser.age_group,
                        ReactorUser.gender == TargetUser.gender,
                        ReactorUser.leaning == TargetUser.leaning,
                    ),
                )
                .order_by(desc(Round.day), desc(Round.hour))
                .limit(limit)
            )

            sql_post_ids = [row[0] for row in query.all()]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

            # Cold start check: if no results, return random posts
            if not post_ids:
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True

            if len(post_ids) < limit:
                additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                post_ids.extend(additional[: limit - len(post_ids)])

    return post_ids, False


def recommend_similar_users_posts_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Posts from demographically similar users (by posting behavior).

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs from similar users, bool indicating if fallback was used)
    """
    # Get agent demographics from Redis/SQL
    agent_data = _get_user_profile(agent_id, redis_client, redis_key_fn, db_engine)

    if agent_data:
        # Redis implementation using cached user data
        agent_age_group = agent_data.get("age_group")
        agent_gender = agent_data.get("gender")
        agent_leaning = agent_data.get("leaning")

        # Create mapping
        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}

        # Get posts from similar users
        posts_with_similarity = []
        for post in valid_posts_with_data:
            post_data = post_id_to_data.get(post["id"])
            if post_data:
                author_id = post_data.get("user_id")
                if author_id and author_id != agent_id:
                    author_data = _get_user_profile(
                        author_id, redis_client, redis_key_fn, db_engine
                    )
                    if author_data:
                        similarity_score = 0
                        if author_data.get("age_group") == agent_age_group:
                            similarity_score += 1
                        if author_data.get("gender") == agent_gender:
                            similarity_score += 1
                        if author_data.get("leaning") == agent_leaning:
                            similarity_score += 1

                        if similarity_score > 0:
                            posts_with_similarity.append(
                                {
                                    "id": post["id"],
                                    "index": post["index"],
                                    "score": similarity_score,
                                }
                            )

        sorted_posts = sorted(posts_with_similarity, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # Fallback to SQLAlchemy ORM query
        logger.info("Mode similar_users_posts - Using SQLAlchemy ORM for user demographics query")
        from sqlalchemy import desc, or_
        from sqlalchemy.orm import aliased

        with Session(db_engine) as session:
            PostAuthor = aliased(User_mgmt)
            TargetUser = aliased(User_mgmt)

            from YSimulator.YServer.classes.models import Post

            query = (
                session.query(Post.id)
                .join(Round, Post.round == Round.id)
                .join(PostAuthor, Post.user_id == PostAuthor.id)
                .join(TargetUser, TargetUser.id == agent_id)
                .filter(
                    Post.user_id != agent_id,
                    or_(
                        PostAuthor.age_group == TargetUser.age_group,
                        PostAuthor.gender == TargetUser.gender,
                        PostAuthor.leaning == TargetUser.leaning,
                    ),
                )
                .order_by(desc(Round.day), desc(Round.hour))
                .limit(limit)
            )

            sql_post_ids = [row[0] for row in query.all()]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

            # Cold start check: if no results, return random posts
            if not post_ids:
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True

            if len(post_ids) < limit:
                additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                post_ids.extend(additional[: limit - len(post_ids)])

    return post_ids, False


def recommend_random_redis(
    valid_posts_with_data: List[Dict[str, Any]], limit: int, **kwargs
) -> List[str]:
    """
    Random post ordering (default).

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend

    Returns:
        List of randomly selected post IDs
    """
    if len(valid_posts_with_data) > limit:
        selected = random.sample(valid_posts_with_data, limit)
        return [p["id"] for p in selected]
    else:
        return [p["id"] for p in valid_posts_with_data]


def recommend_collaborative_user_user_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Collaborative Filtering - User-User (Redis).
    Finds users with high overlap in liked posts and recommends their liked posts.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs, bool indicating if fallback was used)
    """
    # Try to get liked posts from Redis/SQL.
    agent_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    if agent_likes:

        # Find similar users based on like overlap
        user_ids_key = redis_key_fn("user_mgmt", "ids")
        all_user_ids = (
            redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []
        )

        # Calculate overlap for each user
        user_similarities = []
        for uid in all_user_ids:
            if uid != agent_id:
                user_likes = _get_user_likes(uid, redis_client, redis_key_fn, db_engine)
                overlap = len(agent_likes & user_likes)
                if overlap > 0:
                    user_similarities.append({"user_id": uid, "overlap": overlap})

        # Sort by overlap
        user_similarities.sort(key=lambda x: -x["overlap"])
        similar_users = {u["user_id"] for u in user_similarities[:50]}  # Top 50

        # Get posts liked by similar users
        posts_with_scores = []
        for post in valid_posts_with_data:
            if post["id"] not in agent_likes:  # Not already liked
                reaction_user_ids = _get_post_reaction_users(
                    post_id=post["id"],
                    redis_client=redis_client,
                    redis_key_fn=redis_key_fn,
                    db_engine=db_engine,
                )
                similar_user_likes = len(similar_users & reaction_user_ids)
                if similar_user_likes > 0:
                    posts_with_scores.append(
                        {"id": post["id"], "index": post["index"], "score": similar_user_likes}
                    )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Check if we need cold start fallback
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # No likes yet, cold start fallback to random posts
        result = recommend_random_redis(valid_posts_with_data, limit)
        return result, True


def recommend_collaborative_item_item_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Collaborative Filtering - Item-Item (Redis).
    Finds posts often liked together by the same groups.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs, bool indicating if fallback was used)
    """
    # Try to get liked posts from Redis/SQL
    agent_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    if agent_likes:

        # For each post the agent liked, find users who also liked it
        # Then find other posts those users liked (co-occurrence)
        post_co_occurrences = {}

        for liked_post_id in agent_likes:
            # Get users who liked this post
            users_who_liked = _get_post_reaction_users(
                post_id=liked_post_id,
                redis_client=redis_client,
                redis_key_fn=redis_key_fn,
                db_engine=db_engine,
            )

            # Find other posts these users liked
            for user_id in users_who_liked:
                if user_id != agent_id:
                    user_other_likes = _get_user_likes(
                        user_id, redis_client, redis_key_fn, db_engine
                    )
                    for other_post_id in user_other_likes:
                        if other_post_id not in agent_likes:
                            post_co_occurrences[other_post_id] = (
                                post_co_occurrences.get(other_post_id, 0) + 1
                            )

        # Score valid posts based on co-occurrence
        posts_with_scores = []
        for post in valid_posts_with_data:
            if post["id"] in post_co_occurrences:
                posts_with_scores.append(
                    {
                        "id": post["id"],
                        "index": post["index"],
                        "score": post_co_occurrences[post["id"]],
                    }
                )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        # No likes yet, cold start fallback to random posts
        result = recommend_random_redis(valid_posts_with_data, limit)
        return result, True


def recommend_content_based_features_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Content Based Filtering - Feature Extraction (Redis).
    Analyzes attributes of content the user has interacted with (hashtags, topics).

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs, bool indicating if fallback was used)
    """
    # Try to get liked posts from Redis/SQL
    agent_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    if agent_likes:

        # Extract topics from liked posts
        liked_topics = set()
        for liked_post_id in agent_likes:
            liked_topics.update(
                _get_post_topics(liked_post_id, redis_client, redis_key_fn, db_engine)
            )

        if not liked_topics:
            # No topic data available, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Score posts by topic match
        posts_with_scores = []
        for post in valid_posts_with_data:
            if post["id"] not in agent_likes:  # Not already liked
                post_topics = _get_post_topics(post["id"], redis_client, redis_key_fn, db_engine)
                topic_match = len(liked_topics & post_topics)
                if topic_match > 0:
                    posts_with_scores.append(
                        {"id": post["id"], "index": post["index"], "score": topic_match}
                    )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        result = recommend_random_redis(valid_posts_with_data, limit)
        return result, True


def recommend_content_based_vector_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Content Based Filtering - Vector Space Similarity (Redis).
    Recommends posts mathematically close to the user's preference vector.

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs, bool indicating if fallback was used)
    """
    # Try to get liked posts from Redis/SQL
    agent_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    if agent_likes:

        # Build preference vector: topic -> weight (frequency)
        preference_vector = {}
        for liked_post_id in agent_likes:
            post_topics = _get_post_topics(liked_post_id, redis_client, redis_key_fn, db_engine)
            for topic in post_topics:
                preference_vector[topic] = preference_vector.get(topic, 0) + 1

        if not preference_vector:
            # No topic data available, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Calculate similarity score for each post
        posts_with_scores = []
        for post in valid_posts_with_data:
            if post["id"] not in agent_likes:  # Not already liked
                post_topics = _get_post_topics(post["id"], redis_client, redis_key_fn, db_engine)
                # Calculate dot product (simple similarity)
                similarity_score = sum(preference_vector.get(topic, 0) for topic in post_topics)
                if similarity_score > 0:
                    posts_with_scores.append(
                        {"id": post["id"], "index": post["index"], "score": similarity_score}
                    )

        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x["score"], x["index"]))
        post_ids = [p["id"] for p in sorted_posts[:limit]]

        # Cold start check: if no results, return random posts
        if not post_ids:
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Fill with random posts if needed (partial results, not full cold start)
        if len(post_ids) < limit:
            additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
            post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
    else:
        result = recommend_random_redis(valid_posts_with_data, limit)
        return result, True


def recommend_hybrid_linear_ranker_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
    **kwargs,
) -> tuple[List[str], bool]:
    """
    Hybrid content recommendation system with two-stage process:

    Stage 1: Candidate Generation
      - Combines rchrono_followers, friends_of_friends, rchrono_popularity,
        and collaborative_user_user
      - Union and deduplicate results

    Stage 2: Linear Ranker
      - Extracts features for each candidate
      - Scores with weighted linear combination:
        score = 0.28 * recency_score +
                0.25 * is_followed_author +
                0.15 * user_author_affinity +
                0.08 * recent_user_author_affinity +
                0.16 * content_topic_similarity +
                0.08 * similar_user_author

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        redis_client: Redis client instance
        redis_key_fn: Function to generate Redis keys
        db_engine: Database engine for SQL fallback
        logger: Logger instance

    Returns:
        Tuple of (List of post IDs ranked by score, bool indicating if fallback was used)
    """
    import math

    used_fallback = False

    # ==========================================
    # STAGE 1: CANDIDATE GENERATION
    # ==========================================

    # Ensure limit has a valid value (defensive check)
    limit = 5 if limit is None else limit  # Default to 5 if None

    # Get candidates from multiple sources
    candidate_limit = min(limit * 10, 100)  # Get more candidates to rank

    logger.debug(
        f"HybridLinearRanker Stage 1 starting: candidate_limit={candidate_limit}, valid_posts={len(valid_posts_with_data)}",
        extra={
            "extra_data": {
                "agent_id": agent_id,
                "candidate_limit": candidate_limit,
                "valid_posts_count": len(valid_posts_with_data),
            }
        },
    )

    # 1. rchrono_followers
    try:
        candidates_followers, fallback1 = recommend_rchrono_followers_redis(
            valid_posts_with_data=valid_posts_with_data,
            limit=candidate_limit,
            agent_id=agent_id,
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            db_engine=db_engine,
            **kwargs,
        )
        used_fallback = used_fallback or fallback1
    except Exception as e:
        logger.error(
            f"HybridLinearRanker: Error in followers candidate source: {e}",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "error": str(e),
                    "source": "rchrono_followers",
                }
            },
        )
        candidates_followers = []
        used_fallback = True

    # 2. friends_of_friends (posts from users followed by users you follow)
    try:
        candidates_fof, fallback2 = _get_friends_of_friends_candidates_redis(
            valid_posts_with_data=valid_posts_with_data,
            limit=candidate_limit,
            agent_id=agent_id,
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
            db_engine=db_engine,
            logger=logger,
        )
        used_fallback = used_fallback or fallback2
    except Exception as e:
        logger.error(
            f"HybridLinearRanker: Error in friends-of-friends candidate source: {e}",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "error": str(e),
                    "source": "friends_of_friends",
                }
            },
        )
        candidates_fof = []
        used_fallback = True

    # 3. rchrono_popularity
    try:
        candidates_popularity = recommend_rchrono_popularity_redis(
            valid_posts_with_data=valid_posts_with_data, limit=candidate_limit, **kwargs
        )
    except Exception as e:
        logger.error(
            f"HybridLinearRanker: Error in popularity candidate source: {e}",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "error": str(e),
                    "source": "rchrono_popularity",
                }
            },
        )
        candidates_popularity = []
        used_fallback = True

    # 4. collaborative_user_user
    try:
        candidates_collab, fallback3 = recommend_collaborative_user_user_redis(
            valid_posts_with_data=valid_posts_with_data,
            limit=candidate_limit,
            agent_id=agent_id,
            all_post_ids=all_post_ids,
            posts_data=posts_data,
            redis_client=redis_client,
            redis_key_fn=redis_key_fn,
            db_engine=db_engine,
            logger=logger,
            **kwargs,
        )
        used_fallback = used_fallback or fallback3
    except Exception as e:
        logger.error(
            f"HybridLinearRanker: Error in collaborative candidate source: {e}",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "error": str(e),
                    "source": "collaborative_user_user",
                }
            },
        )
        candidates_collab = []
        used_fallback = True

    # Union and deduplicate
    candidate_set = set()
    candidate_set.update(candidates_followers)
    candidate_set.update(candidates_fof)
    candidate_set.update(candidates_popularity)
    candidate_set.update(candidates_collab)

    # Log candidate generation results for diagnostics
    logger.info(
        f"HybridLinearRanker candidate generation: "
        f"followers={len(candidates_followers)}, "
        f"fof={len(candidates_fof)}, "
        f"popularity={len(candidates_popularity)}, "
        f"collab={len(candidates_collab)}, "
        f"total_unique={len(candidate_set)}",
        extra={
            "extra_data": {
                "agent_id": agent_id,
                "candidates_followers": len(candidates_followers),
                "candidates_fof": len(candidates_fof),
                "candidates_popularity": len(candidates_popularity),
                "candidates_collab": len(candidates_collab),
                "candidate_set_size": len(candidate_set),
                "valid_posts_count": len(valid_posts_with_data),
            }
        },
    )

    # If no candidates found, fall back to random
    if not candidate_set:
        logger.warning(
            f"HybridLinearRanker: No candidates generated from any source, falling back to random",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "valid_posts_count": len(valid_posts_with_data),
                }
            },
        )
        result = recommend_random_redis(valid_posts_with_data, limit)
        return result, True

    # ==========================================
    # STAGE 2: FEATURE EXTRACTION & RANKING
    # ==========================================

    # Get current round info for recency calculation
    current_round = kwargs.get("current_round", 0)
    tau = kwargs.get("tau", 10.0)  # Decay parameter for recency

    # Build post_id to data mapping for efficient lookup
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}

    # Get followed users
    followed_users = _get_followed_users_redis(agent_id, redis_client, redis_key_fn, db_engine)

    # Get user's topic interests
    user_interests = _get_user_interests(agent_id, redis_client, redis_key_fn, db_engine)

    # Score each candidate post
    post_scores = []
    for post_id in candidate_set:
        post_data = post_id_to_data.get(post_id)
        if not post_data:
            continue

        # Extract features
        author_id = post_data.get("user_id")
        if author_id == agent_id:  # Skip own posts
            continue

        # Feature 1: Recency score (exponential decay)
        post_round = int(post_data.get("round", 0) or 0)
        age_rounds = max(0, current_round - post_round)
        recency_score = math.exp(-age_rounds / tau)

        # Feature 2: Is followed author
        is_followed_author = 1.0 if author_id in followed_users else 0.0

        # Feature 3: User-author affinity (engagement count, log scale)
        user_author_affinity = _calculate_user_author_affinity_redis(
            agent_id, author_id, redis_client, redis_key_fn, db_engine
        )

        # Feature 4: Recent user-author affinity (interactions in recent rounds)
        recent_user_author_affinity = _calculate_recent_user_author_affinity_redis(
            agent_id, author_id, current_round, redis_client, redis_key_fn, db_engine, tau
        )

        # Feature 5: Content topic similarity (Jaccard similarity as proxy for cosine)
        content_topic_similarity = _calculate_content_topic_similarity_redis(
            agent_id, post_id, user_interests, redis_client, redis_key_fn, db_engine
        )

        # Feature 6: Similar user author score (people like you follow/like this author)
        similar_user_author = _calculate_similar_user_author_score_redis(
            agent_id, author_id, redis_client, redis_key_fn, db_engine
        )

        # Calculate composite score with weights
        composite_score = (
            0.28 * recency_score
            + 0.25 * is_followed_author
            + 0.15 * user_author_affinity
            + 0.08 * recent_user_author_affinity
            + 0.16 * content_topic_similarity
            + 0.08 * similar_user_author
        )

        post_scores.append(
            {
                "id": post_id,
                "score": composite_score,
                "features": {
                    "recency": recency_score,
                    "is_followed": is_followed_author,
                    "affinity": user_author_affinity,
                    "recent_affinity": recent_user_author_affinity,
                    "topic_sim": content_topic_similarity,
                    "similar_user": similar_user_author,
                },
            }
        )

    # Sort by score descending
    post_scores.sort(key=lambda x: -x["score"])

    # Return top N
    result_ids = [p["id"] for p in post_scores[:limit]]

    # If not enough results, fill with random posts
    if len(result_ids) < limit:
        additional = [p["id"] for p in valid_posts_with_data if p["id"] not in result_ids]
        result_ids.extend(additional[: limit - len(result_ids)])
        used_fallback = True

    return result_ids, used_fallback


# ==========================================
# HELPER FUNCTIONS FOR HYBRID RECOMMENDER
# ==========================================


def _get_friends_of_friends_candidates_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    redis_client,
    redis_key_fn,
    db_engine,
    logger,
) -> tuple[List[str], bool]:
    """
    Get posts from friends-of-friends (users followed by users you follow).

    Returns:
        Tuple of (List of post IDs, bool indicating if fallback was used)
    """
    # Get users that current agent follows
    followed_users = _get_followed_users_redis(agent_id, redis_client, redis_key_fn, db_engine)

    if not followed_users:
        # No follows, return random
        result = recommend_random_redis(
            valid_posts_with_data, min(limit, len(valid_posts_with_data))
        )
        return result, True

    # Get users followed by the agent's followed users (friends-of-friends)
    fof_users = set()

    # Try Redis first
    for followed_user_id in followed_users:
        fof_users.update(_get_user_follows(followed_user_id, redis_client, redis_key_fn, db_engine))

    # Remove agent and direct follows
    fof_users.discard(agent_id)
    fof_users -= followed_users

    # If Redis didn't have data, fall back to SQL
    if not fof_users:
        with Session(db_engine) as session:
            # Get follows of follows
            fof_query = (
                session.query(Follow.user_id)
                .filter(
                    Follow.follower_id.in_(followed_users),
                    Follow.user_id != agent_id,
                    Follow.user_id.notin_(followed_users),
                    Follow.action == "follow",
                )
                .distinct()
            )
            fof_users = set(row[0] for row in fof_query.all())

    if not fof_users:
        result = recommend_random_redis(
            valid_posts_with_data, min(limit, len(valid_posts_with_data))
        )
        return result, True

    # Get posts from friends-of-friends
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}

    fof_posts = []
    for post in valid_posts_with_data:
        post_data = post_id_to_data.get(post["id"])
        if post_data and post_data.get("user_id") in fof_users:
            fof_posts.append(post)

    # Sort by recency (index)
    fof_posts.sort(key=lambda x: x["index"])
    result_ids = [p["id"] for p in fof_posts[:limit]]

    # Fill with random if needed
    if len(result_ids) < limit:
        additional = [p["id"] for p in valid_posts_with_data if p["id"] not in result_ids]
        result_ids.extend(additional[: limit - len(result_ids)])

    return result_ids, False


def _get_followed_users_redis(agent_id: str, redis_client, redis_key_fn, db_engine) -> set:
    """Get set of users that the agent follows."""
    # Try Redis first
    follows = _get_user_follows(agent_id, redis_client, redis_key_fn, db_engine)
    if follows:
        return follows

    # Fallback to SQL
    try:
        with Session(db_engine) as session:
            query = session.query(Follow.user_id).filter(
                Follow.follower_id == agent_id, Follow.action == "follow"
            )
            return set(row[0] for row in query.all())
    except Exception:
        return set()


def _calculate_user_author_affinity_redis(
    agent_id: str, author_id: str, redis_client, redis_key_fn, db_engine
) -> float:
    """
    Calculate user-author affinity based on engagement count (log scale).
    affinity = log(1 + interactions_user_author)
    """
    import math

    # Try Redis: count interactions (likes/comments)
    interactions = 0

    # Check likes
    user_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    # Count how many of these posts are by the author
    for post_id in user_likes:
        post_key = redis_key_fn("posts", post_id)
        if redis_client.exists(post_key):
            post_data = redis_client.hgetall(post_key)
            if post_data.get("user_id") == author_id:
                interactions += 1

    # If Redis doesn't have data, fall back to SQL
    if interactions == 0:
        try:
            with Session(db_engine) as session:
                from YSimulator.YServer.classes.models import Post

                # Count likes on author's posts
                likes_count = (
                    session.query(Reaction)
                    .join(Post, Reaction.post_id == Post.id)
                    .filter(
                        Reaction.user_id == agent_id,
                        Post.user_id == author_id,
                        Reaction.type == "LIKE",
                    )
                    .count()
                )

                # Comments are posts whose `comment_to` points to a parent post
                parent_post = aliased(Post)
                comments_count = (
                    session.query(Post)
                    .join(parent_post, Post.comment_to == parent_post.id)
                    .filter(
                        Post.user_id == agent_id,
                        Post.comment_to.isnot(None),
                        Post.comment_to != "-1",
                        parent_post.user_id == author_id,
                    )
                    .count()
                )

                interactions = likes_count + comments_count
        except Exception:
            interactions = 0

    # Log scale
    return math.log(1 + interactions)


def _calculate_recent_user_author_affinity_redis(
    agent_id: str,
    author_id: str,
    current_round: int,
    redis_client,
    redis_key_fn,
    db_engine,
    tau: float = 10.0,
) -> float:
    """
    Calculate recent user-author affinity with time decay.
    Similar to user_author_affinity but weighted by recency.
    """
    # This is a simplified version that returns a fraction of the overall affinity
    # In a full implementation, you'd track interaction timestamps
    # For now, we'll return a scaled-down version of the overall affinity
    overall_affinity = _calculate_user_author_affinity_redis(
        agent_id, author_id, redis_client, redis_key_fn, db_engine
    )

    # Return a fraction to represent "recent" interactions
    return overall_affinity * RECENT_AFFINITY_DISCOUNT


def _calculate_content_topic_similarity_redis(
    agent_id: str,
    post_id: str,
    user_interests: set,
    redis_client,
    redis_key_fn,
    db_engine=None,
) -> float:
    """
    Calculate content topic similarity using cosine similarity.
    Simplified: Jaccard similarity (intersection / union) of topics.
    """
    # Get post topics (Redis with SQL fallback)
    post_topics = _get_post_topics(post_id, redis_client, redis_key_fn, db_engine)

    if not user_interests or not post_topics:
        return 0.0

    # Jaccard similarity as proxy for cosine similarity
    intersection = len(user_interests & post_topics)
    union = len(user_interests | post_topics)

    if union == 0:
        return 0.0

    return intersection / union


def _calculate_similar_user_author_score_redis(
    agent_id: str, author_id: str, redis_client, redis_key_fn, db_engine
) -> float:
    """
    Calculate how many similar users follow/like this author (log scale).
    Similar users = users with overlapping interests or liked posts.
    """
    import math

    # Get agent's likes
    agent_likes = _get_user_likes(agent_id, redis_client, redis_key_fn, db_engine)
    if not agent_likes:
        return 0.0

    # Find similar users (users who liked similar posts)
    similar_users = set()
    user_ids_key = redis_key_fn("user_mgmt", "ids")
    all_user_ids = redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []

    # Calculate overlap for each user (simplified - take top N with overlap)
    for uid in list(all_user_ids)[:SIMILAR_USERS_SAMPLE_LIMIT]:
        if uid != agent_id:
            user_likes = _get_user_likes(uid, redis_client, redis_key_fn, db_engine)
            overlap = len(agent_likes & user_likes)
            if overlap > 0:
                similar_users.add(uid)

    # Count how many similar users follow or liked posts by this author
    count = 0
    for user_id in similar_users:
        # Check if they follow the author
        user_follows = _get_user_follows(user_id, redis_client, redis_key_fn, db_engine)
        if author_id in user_follows:
            count += 1

    # Log scale
    return math.log(1 + count)
