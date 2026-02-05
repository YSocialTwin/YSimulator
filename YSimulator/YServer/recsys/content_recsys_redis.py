"""
Redis-based content recommendation strategies.

Each function implements a specific recommendation algorithm using Redis key-value operations.
"""

import random
from typing import Any, Dict, List

from YSimulator.YServer.classes.models import Follow, PostTopic, Reaction, User_mgmt, UserInterest


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

    Args:
        valid_posts_with_data: List of post dictionaries with 'id', 'index', 'reaction_count'
        limit: Number of posts to recommend

    Returns:
        List of post IDs sorted by time then popularity
    """
    # Sort by index (time proxy) first, then by reaction_count
    # This aligns better with SQL which sorts by time first, then popularity
    sorted_posts = sorted(valid_posts_with_data, key=lambda x: (x["index"], -x["reaction_count"]))
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
) -> List[str]:
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
        List of post IDs prioritizing followed users
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Get followed user IDs from database using SQLAlchemy ORM
    from sqlalchemy.orm import Session

    with Session(db_engine) as session:
        query = session.query(Follow.follower_id).filter(
            Follow.user_id == agent_id, Follow.action == "follow"
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
        post_ids.extend([p["id"] for p in other_posts[:additional_posts_limit]])

    return post_ids


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

    Args:
        valid_posts_with_data: List of post dictionaries
        limit: Number of posts to recommend
        agent_id: UUID of agent requesting recommendations
        followers_ratio: Ratio of posts from followers vs others
        all_post_ids: All post IDs from Redis
        posts_data: All post data from Redis
        db_engine: Database engine for follow queries

    Returns:
        List of post IDs combining follower priority and popularity
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Get follow relationships using SQLAlchemy ORM
    from sqlalchemy.orm import Session

    with Session(db_engine) as session:
        query = session.query(Follow.follower_id).filter(
            Follow.user_id == agent_id, Follow.action == "follow"
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

    # Sort by index (time) then popularity
    follower_posts_sorted = sorted(follower_posts, key=lambda x: (x["index"], -x["reaction_count"]))
    other_posts_sorted = sorted(other_posts, key=lambda x: (x["index"], -x["reaction_count"]))

    post_ids = [p["id"] for p in follower_posts_sorted[:follower_posts_limit]]
    if len(post_ids) < limit:
        post_ids.extend([p["id"] for p in other_posts_sorted[:additional_posts_limit]])

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
    # Try to get user interests from Redis
    user_interests_key = redis_key_fn("user", agent_id) + ":interests"
    if redis_client.exists(user_interests_key):
        # Redis implementation when data is available
        user_interests = redis_client.smembers(user_interests_key)

        # Score posts by number of matching interests
        posts_with_scores = []
        for post in valid_posts_with_data:
            post_topics_key = redis_key_fn("post", post["id"]) + ":topics"
            if redis_client.exists(post_topics_key):
                post_topics = redis_client.smembers(post_topics_key)
                # Calculate intersection (common interests)
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
        from sqlalchemy.orm import Session

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
                    .filter(PostTopic.topic_id.in_(user_interests), Post.user_id != agent_id)
                    .distinct()
                    .order_by(desc(PostTopic.post_id))
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
    user_interests_key = redis_key_fn("user", agent_id) + ":interests"
    if redis_client.exists(user_interests_key):
        # Redis implementation when data is available
        user_interests = redis_client.smembers(user_interests_key)

        # Find users with common interests
        user_ids_key = redis_key_fn("user_mgmt", "ids")
        all_user_ids = (
            redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []
        )

        similar_users = set()
        for uid in all_user_ids:
            if uid != agent_id:
                other_interests_key = redis_key_fn("user", uid) + ":interests"
                if redis_client.exists(other_interests_key):
                    other_interests = redis_client.smembers(other_interests_key)
                    if len(user_interests & other_interests) > 0:
                        similar_users.add(uid)

        # Get posts liked by similar users
        posts_with_scores = []

        for post in valid_posts_with_data:
            # Check if any similar user liked this post
            post_reactions_key = redis_key_fn("post", post["id"]) + ":reactions"
            if redis_client.exists(post_reactions_key):
                reaction_user_ids = redis_client.smembers(post_reactions_key)
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
        from sqlalchemy.orm import Session, aliased

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
                .filter(
                    UserInterest2.user_id == agent_id,
                    Reaction.user_id != agent_id,
                    Post.user_id != agent_id,
                    Reaction.type == "LIKE",
                )
                .order_by(desc(Reaction.post_id))
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
    # Get agent demographics from Redis
    agent_key = redis_key_fn("users", agent_id)
    agent_data = redis_client.hgetall(agent_key) if redis_client.exists(agent_key) else {}

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
            post_reactions_key = redis_key_fn("post", post["id"]) + ":reactions"
            if redis_client.exists(post_reactions_key):
                reaction_user_ids = redis_client.smembers(post_reactions_key)
                similar_count = 0
                for uid in reaction_user_ids:
                    user_key = redis_key_fn("users", uid)
                    user_data = (
                        redis_client.hgetall(user_key) if redis_client.exists(user_key) else {}
                    )
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
        from sqlalchemy.orm import Session, aliased

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
                .order_by(desc(Reaction.post_id))
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
    # Get agent demographics from Redis
    agent_key = redis_key_fn("users", agent_id)
    agent_data = redis_client.hgetall(agent_key) if redis_client.exists(agent_key) else {}

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
                    author_key = redis_key_fn("users", author_id)
                    author_data = (
                        redis_client.hgetall(author_key) if redis_client.exists(author_key) else {}
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
        from sqlalchemy.orm import Session, aliased

        with Session(db_engine) as session:
            PostAuthor = aliased(User_mgmt)
            TargetUser = aliased(User_mgmt)

            from YSimulator.YServer.classes.models import Post

            query = (
                session.query(Post.id)
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
                .order_by(desc(Post.id))
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
    # Try to get liked posts from Redis
    agent_likes_key = redis_key_fn("user", agent_id) + ":likes"
    if redis_client.exists(agent_likes_key):
        agent_likes = redis_client.smembers(agent_likes_key)

        if not agent_likes:
            # No likes yet, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Find similar users based on like overlap
        user_ids_key = redis_key_fn("user_mgmt", "ids")
        all_user_ids = (
            redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []
        )

        # Calculate overlap for each user
        user_similarities = []
        for uid in all_user_ids:
            if uid != agent_id:
                user_likes_key = redis_key_fn("user", uid) + ":likes"
                if redis_client.exists(user_likes_key):
                    user_likes = redis_client.smembers(user_likes_key)
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
                post_reactions_key = redis_key_fn("post", post["id"]) + ":reactions"
                if redis_client.exists(post_reactions_key):
                    reaction_user_ids = redis_client.smembers(post_reactions_key)
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
        # Fallback to SQLAlchemy ORM
        logger.info(
            "Mode collaborative_user_user - Redis cache not available yet, using SQLAlchemy ORM"
        )
        from sqlalchemy import desc
        from sqlalchemy.orm import Session

        with Session(db_engine) as session:
            from YSimulator.YServer.classes.models import Post, Reaction

            # Get agent's liked posts
            agent_likes_query = session.query(Reaction.post_id).filter(
                Reaction.user_id == agent_id, Reaction.type == "LIKE"
            )
            agent_likes_ids = [row[0] for row in agent_likes_query.all()]

            if not agent_likes_ids:
                # No likes, cold start fallback to random posts
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True
            else:
                # Find similar users
                similar_users_query = (
                    session.query(Reaction.user_id)
                    .filter(
                        Reaction.post_id.in_(agent_likes_ids),
                        Reaction.user_id != agent_id,
                        Reaction.type == "LIKE",
                    )
                    .distinct()
                    .limit(50)
                )
                similar_user_ids = [row[0] for row in similar_users_query.all()]

                if similar_user_ids:
                    # Get posts liked by similar users
                    posts_query = (
                        session.query(Reaction.post_id)
                        .join(Post, Reaction.post_id == Post.id)
                        .filter(
                            Reaction.user_id.in_(similar_user_ids),
                            Reaction.type == "LIKE",
                            Post.user_id != agent_id,
                            Reaction.post_id.notin_(agent_likes_ids),
                        )
                        .distinct()
                        .order_by(desc(Reaction.post_id))
                        .limit(limit)
                    )
                    sql_post_ids = [row[0] for row in posts_query.all()]
                    post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
                else:
                    post_ids = []

                # Check if we need cold start fallback
                if not post_ids:
                    result = recommend_random_redis(valid_posts_with_data, limit)
                    return result, True

                # Fill with random posts if needed (partial results, not full cold start)
                if len(post_ids) < limit:
                    additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                    post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False


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
    # Try to get liked posts from Redis
    agent_likes_key = redis_key_fn("user", agent_id) + ":likes"
    if redis_client.exists(agent_likes_key):
        agent_likes = redis_client.smembers(agent_likes_key)

        if not agent_likes:
            # No likes yet, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # For each post the agent liked, find users who also liked it
        # Then find other posts those users liked (co-occurrence)
        post_co_occurrences = {}

        for liked_post_id in agent_likes:
            # Get users who liked this post
            liked_post_reactions_key = redis_key_fn("post", liked_post_id) + ":reactions"
            if redis_client.exists(liked_post_reactions_key):
                users_who_liked = redis_client.smembers(liked_post_reactions_key)

                # Find other posts these users liked
                for user_id in users_who_liked:
                    if user_id != agent_id:
                        user_likes_key = redis_key_fn("user", user_id) + ":likes"
                        if redis_client.exists(user_likes_key):
                            user_other_likes = redis_client.smembers(user_likes_key)
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
        # Fallback to SQLAlchemy ORM
        logger.info(
            "Mode collaborative_item_item - Redis cache not available yet, using SQLAlchemy ORM"
        )
        from sqlalchemy import desc
        from sqlalchemy.orm import Session, aliased

        with Session(db_engine) as session:
            from YSimulator.YServer.classes.models import Post, Reaction

            # Get agent's liked posts
            agent_likes_query = session.query(Reaction.post_id).filter(
                Reaction.user_id == agent_id, Reaction.type == "LIKE"
            )
            agent_likes_ids = [row[0] for row in agent_likes_query.all()]

            if not agent_likes_ids:
                # No likes, cold start fallback to random posts
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True
            else:
                # Find posts liked by users who liked the same posts as agent
                Reaction2 = aliased(Reaction)
                posts_query = (
                    session.query(Reaction2.post_id)
                    .join(Reaction, Reaction.user_id == Reaction2.user_id)
                    .join(Post, Reaction2.post_id == Post.id)
                    .filter(
                        Reaction.post_id.in_(agent_likes_ids),
                        Reaction.type == "LIKE",
                        Reaction2.type == "LIKE",
                        Reaction2.user_id != agent_id,
                        Post.user_id != agent_id,
                        Reaction2.post_id.notin_(agent_likes_ids),
                    )
                    .distinct()
                    .order_by(desc(Reaction2.post_id))
                    .limit(limit)
                )
                sql_post_ids = [row[0] for row in posts_query.all()]
                post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

                # Cold start check: if no results, return random posts
                if not post_ids:
                    result = recommend_random_redis(valid_posts_with_data, limit)
                    return result, True

                # Fill with random posts if needed (partial results, not full cold start)
                if len(post_ids) < limit:
                    additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                    post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False


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
    # Try to get liked posts from Redis
    agent_likes_key = redis_key_fn("user", agent_id) + ":likes"
    if redis_client.exists(agent_likes_key):
        agent_likes = redis_client.smembers(agent_likes_key)

        if not agent_likes:
            # No likes yet, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Extract topics from liked posts
        liked_topics = set()
        for liked_post_id in agent_likes:
            post_topics_key = redis_key_fn("post", liked_post_id) + ":topics"
            if redis_client.exists(post_topics_key):
                post_topics = redis_client.smembers(post_topics_key)
                liked_topics.update(post_topics)

        if not liked_topics:
            # No topic data available, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Score posts by topic match
        posts_with_scores = []
        for post in valid_posts_with_data:
            if post["id"] not in agent_likes:  # Not already liked
                post_topics_key = redis_key_fn("post", post["id"]) + ":topics"
                if redis_client.exists(post_topics_key):
                    post_topics = redis_client.smembers(post_topics_key)
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
        # Fallback to SQLAlchemy ORM
        logger.info(
            "Mode content_based_features - Redis cache not available yet, using SQLAlchemy ORM"
        )
        from sqlalchemy import desc
        from sqlalchemy.orm import Session

        with Session(db_engine) as session:
            from YSimulator.YServer.classes.models import Post, PostTopic, Reaction

            # Get topics from liked posts
            liked_topics_query = (
                session.query(PostTopic.topic_id)
                .join(Reaction, PostTopic.post_id == Reaction.post_id)
                .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
                .distinct()
            )
            liked_topic_ids = [row[0] for row in liked_topics_query.all()]

            if not liked_topic_ids:
                # Cold start fallback to random posts
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True
            else:
                # Find posts with matching topics
                posts_query = (
                    session.query(PostTopic.post_id)
                    .join(Post, PostTopic.post_id == Post.id)
                    .outerjoin(Reaction, Reaction.post_id == Post.id)
                    .filter(
                        PostTopic.topic_id.in_(liked_topic_ids),
                        Post.user_id != agent_id,
                        Reaction.id.is_(None),
                    )
                    .distinct()
                    .order_by(desc(PostTopic.post_id))
                    .limit(limit)
                )
                sql_post_ids = [row[0] for row in posts_query.all()]
                post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

                # Cold start check: if no results, return random posts
                if not post_ids:
                    result = recommend_random_redis(valid_posts_with_data, limit)
                    return result, True

                # Fill with random posts if needed (partial results, not full cold start)
                if len(post_ids) < limit:
                    additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                    post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False


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
    # Try to get liked posts from Redis
    agent_likes_key = redis_key_fn("user", agent_id) + ":likes"
    if redis_client.exists(agent_likes_key):
        agent_likes = redis_client.smembers(agent_likes_key)

        if not agent_likes:
            # No likes yet, cold start fallback to random posts
            result = recommend_random_redis(valid_posts_with_data, limit)
            return result, True

        # Build preference vector: topic -> weight (frequency)
        preference_vector = {}
        for liked_post_id in agent_likes:
            post_topics_key = redis_key_fn("post", liked_post_id) + ":topics"
            if redis_client.exists(post_topics_key):
                post_topics = redis_client.smembers(post_topics_key)
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
                post_topics_key = redis_key_fn("post", post["id"]) + ":topics"
                if redis_client.exists(post_topics_key):
                    post_topics = redis_client.smembers(post_topics_key)
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
        # Fallback to SQLAlchemy ORM
        logger.info(
            "Mode content_based_vector - Redis cache not available yet, using SQLAlchemy ORM"
        )
        from sqlalchemy import desc, func
        from sqlalchemy.orm import Session

        with Session(db_engine) as session:
            from YSimulator.YServer.classes.models import Post, PostTopic, Reaction

            # Build preference vector from liked posts
            user_topics_query = (
                session.query(PostTopic.topic_id, func.count(PostTopic.topic_id).label("weight"))
                .join(Reaction, PostTopic.post_id == Reaction.post_id)
                .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
                .group_by(PostTopic.topic_id)
            )
            user_topics = {row[0]: row[1] for row in user_topics_query.all()}

            if not user_topics:
                # Cold start fallback to random posts
                result = recommend_random_redis(valid_posts_with_data, limit)
                return result, True
            else:
                # Find posts with matching topics, weighted by preference
                posts_query = (
                    session.query(PostTopic.post_id)
                    .join(Post, PostTopic.post_id == Post.id)
                    .outerjoin(Reaction, Reaction.post_id == Post.id)
                    .filter(
                        PostTopic.topic_id.in_(user_topics.keys()),
                        Post.user_id != agent_id,
                        Reaction.id.is_(None),
                    )
                    .distinct()
                    .order_by(desc(PostTopic.post_id))
                    .limit(limit)
                )
                sql_post_ids = [row[0] for row in posts_query.all()]
                post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]

                # Cold start check: if no results, return random posts
                if not post_ids:
                    result = recommend_random_redis(valid_posts_with_data, limit)
                    return result, True

                # Fill with random posts if needed (partial results, not full cold start)
                if len(post_ids) < limit:
                    additional = [p["id"] for p in valid_posts_with_data if p["id"] not in post_ids]
                    post_ids.extend(additional[: limit - len(post_ids)])

        return post_ids, False
