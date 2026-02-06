"""
SQL-based content recommendation strategies.

Each function implements a specific recommendation algorithm using SQLAlchemy ORM for DBMS independence.
All functions follow a consistent signature for easy integration with the server.
"""

from typing import List

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import aliased

from YSimulator.YServer.classes.models import (
    Follow,
    Post,
    PostTopic,
    Reaction,
    Round,
    User_mgmt,
    UserInterest,
)


def recommend_random(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
    """
    Random post ordering (default strategy).

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        List of post UUIDs
    """
    query = (
        session.query(Post.id)
        .join(Round, Post.round == Round.id)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
        )
        .order_by(func.random())
        .limit(limit)
    )

    return [row[0] for row in query.all()]


def recommend_rchrono(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
    """
    Reverse chronological ordering: newest posts first.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        List of post UUIDs
    """
    query = (
        session.query(Post.id)
        .join(Round, Post.round == Round.id)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
        )
        .order_by(desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    return [row[0] for row in query.all()]


def recommend_rchrono_popularity(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
    """
    Reverse chronological with popularity boost (reaction count).

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        List of post UUIDs
    """
    # Subquery to count reactions per post
    # reaction_count_subq = (
    #    session.query(Reaction.post_id, func.count().label("reaction_count"))
    #    .group_by(Reaction.post_id)
    #    .subquery()
    # )

    query = (
        session.query(Post.id)
        .join(Round, Post.round == Round.id)
        # .join(reaction_count_subq, Post.id == reaction_count_subq.c.post_id)  # inner join
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            # reaction_count_subq.c.reaction_count > 0,  # technically redundant now
        )
        .order_by(
            desc(Post.reaction_count),
            # desc(reaction_count_subq.c.reaction_count),
            desc(Round.day),
            desc(Round.hour),
        )
        .limit(limit)
    )

    return [row[0] for row in query.all()]


def recommend_rchrono_followers(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
    followers_ratio: float,
) -> List[str]:
    """
    Prioritize posts from followed users, then fill with other posts.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        followers_ratio: Ratio of posts from followers (e.g., 0.6 = 60%)

    Returns:
        List of post UUIDs
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Get posts from followed users
    query_followers = (
        session.query(Post.id)
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Follow, Post.user_id == Follow.follower_id)
        .filter(
            Follow.user_id == agent_id,
            Follow.action == "follow",
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
        )
        .order_by(desc(Round.day), desc(Round.hour))
        .limit(follower_posts_limit)
    )

    post_ids = [row[0] for row in query_followers.all()]

    # If we need more posts, get additional ones
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = (
                session.query(Post.id)
                .join(Round, Post.round == Round.id)
                .filter(
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                    Post.id.notin_(post_ids),
                )
                .order_by(desc(Round.day), desc(Round.hour))
                .limit(additional_posts_limit)
            )
        else:
            # No existing posts, skip the NOT IN clause
            query_additional = (
                session.query(Post.id)
                .join(Round, Post.round == Round.id)
                .filter(
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                )
                .order_by(desc(Round.day), desc(Round.hour))
                .limit(additional_posts_limit)
            )

        post_ids.extend([row[0] for row in query_additional.all()])

    return post_ids


def recommend_rchrono_followers_popularity(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
    followers_ratio: float,
) -> List[str]:
    """
    Followers with popularity boost (combines following and reaction count).

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        followers_ratio: Ratio of posts from followers

    Returns:
        List of post UUIDs
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Subquery to count reactions per post
    # reaction_count_subq = (
    #    session.query(Reaction.post_id, func.count().label("reaction_count"))
    #    .group_by(Reaction.post_id)
    #    .subquery()
    # )

    query_followers = (
        session.query(Post.id)
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Follow, Post.user_id == Follow.follower_id)
        # .outerjoin(reaction_count_subq, Post.id == reaction_count_subq.c.post_id)
        .filter(
            Follow.user_id == agent_id,
            Follow.action == "follow",
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            # func.coalesce(reaction_count_subq.c.reaction_count, 0) > 0,  # added
        )
        .order_by(
            desc(Post.reaction_count),
            desc(Post.round),
            # desc(func.coalesce(reaction_count_subq.c.reaction_count, 0)),
        )
        .limit(follower_posts_limit)
    )

    post_ids = [row[0] for row in query_followers.all()]

    if len(post_ids) < limit and additional_posts_limit > 0:
        # Recreate reaction count subquery for additional posts
        # reaction_count_subq2 = (
        #    session.query(Reaction.post_id, func.count().label("reaction_count"))
        #    .group_by(Reaction.post_id)
        #    .subquery()
        # )

        if post_ids:
            query_additional = (
                session.query(Post.id)
                .join(Round, Post.round == Round.id)
                # .outerjoin(reaction_count_subq2, Post.id == reaction_count_subq2.c.post_id)
                .filter(
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                    Post.id.notin_(post_ids),
                )
                .order_by(
                    desc(Post.reaction_count),
                    desc(
                        Post.round
                    ),  # , desc(func.coalesce(reaction_count_subq2.c.reaction_count, 0))
                )
                .limit(additional_posts_limit)
            )
        else:
            query_additional = (
                session.query(Post.id)
                .join(Round, Post.round == Round.id)
                # .outerjoin(reaction_count_subq2, Post.id == reaction_count_subq2.c.post_id)
                .filter(
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                )
                .order_by(
                    desc(Post.reaction_count),
                    desc(
                        Post.round
                    ),  # , desc(func.coalesce(reaction_count_subq2.c.reaction_count, 0))
                )
                .limit(additional_posts_limit)
            )

        post_ids.extend([row[0] for row in query_additional.all()])

    return post_ids


def recommend_rchrono_comments(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
    """
    Prioritize posts with more comments (thread activity).

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        List of post UUIDs
    """
    # Alias for comment posts
    CommentPost = aliased(Post)

    query = (
        session.query(Post.id)
        .join(Round, Post.round == Round.id)
        .outerjoin(CommentPost, Post.id == CommentPost.comment_to)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            Post.comment_to.is_(None),
        )
        .group_by(Post.id)
        .order_by(desc(func.count(CommentPost.id)), desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    return [row[0] for row in query.all()]


def recommend_common_interests(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
    followers_ratio: float,
) -> tuple[List[str], bool]:
    """
    Posts with common topic interests (based on user_interest and post_topics).
    Prioritizes posts from followed users, then fills with other posts.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        followers_ratio: Ratio of posts from followers

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Get posts matching user's interests from followers
    query = (
        session.query(Post.id)
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(PostTopic, Post.id == PostTopic.post_id)
        .join(UserInterest, PostTopic.topic_id == UserInterest.interest_id)
        .join(Follow, Post.user_id == Follow.follower_id)
        .filter(
            UserInterest.user_id == agent_id,
            Follow.user_id == agent_id,
            Follow.action == "follow",
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
        )
        .group_by(Post.id)
        .order_by(desc(func.count(PostTopic.topic_id)), desc(Round.day), desc(Round.hour))
        .limit(follower_posts_limit)
    )

    post_ids = [row[0] for row in query.all()]

    # Get additional posts with common interests
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = (
                session.query(Post.id)
                .distinct()
                .join(Round, Post.round == Round.id)
                .join(PostTopic, Post.id == PostTopic.post_id)
                .join(UserInterest, PostTopic.topic_id == UserInterest.interest_id)
                .filter(
                    UserInterest.user_id == agent_id,
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                    Post.id.notin_(post_ids),
                )
                .group_by(Post.id)
                .order_by(desc(func.count(PostTopic.topic_id)), desc(Round.day), desc(Round.hour))
                .limit(additional_posts_limit)
            )
        else:
            query_additional = (
                session.query(Post.id)
                .distinct()
                .join(Round, Post.round == Round.id)
                .join(PostTopic, Post.id == PostTopic.post_id)
                .join(UserInterest, PostTopic.topic_id == UserInterest.interest_id)
                .filter(
                    UserInterest.user_id == agent_id,
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                )
                .group_by(Post.id)
                .order_by(desc(func.count(PostTopic.topic_id)), desc(Round.day), desc(Round.hour))
                .limit(additional_posts_limit)
            )

        post_ids.extend([row[0] for row in query_additional.all()])

    # Cold start fallback: if no results, return random posts
    if not post_ids:
        post_ids = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return post_ids, True

    return post_ids, False


def recommend_common_user_interests(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
    followers_ratio: float,
) -> tuple[List[str], bool]:
    """
    Posts by users with common interests (most interacted).
    Prioritizes posts from followed users with common interests.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        followers_ratio: Ratio of posts from followers

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    follower_posts_limit = int(limit * followers_ratio)
    additional_posts_limit = limit - follower_posts_limit

    # Alias for user interests
    UserInterest1 = aliased(UserInterest)
    UserInterest2 = aliased(UserInterest)

    # Get posts reacted to by users with common interests who are followers
    query = (
        session.query(Post.id, func.count(Reaction.id).label("reaction_count"))
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Reaction, Post.id == Reaction.post_id)
        .join(User_mgmt, Reaction.user_id == User_mgmt.id)
        .join(UserInterest1, User_mgmt.id == UserInterest1.user_id)
        .join(UserInterest2, UserInterest1.interest_id == UserInterest2.interest_id)
        .join(Follow, User_mgmt.id == Follow.follower_id)
        .filter(
            UserInterest2.user_id == agent_id,
            Follow.user_id == agent_id,
            Follow.action == "follow",
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
        )
        .group_by(Post.id)
        .order_by(desc("reaction_count"), desc(Round.day), desc(Round.hour))
        .limit(follower_posts_limit)
    )

    post_ids = [row[0] for row in query.all()]

    # Get additional from non-followers with common interests
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            # Recreate aliases for the additional query
            UserInterest1_add = aliased(UserInterest)
            UserInterest2_add = aliased(UserInterest)

            query_additional = (
                session.query(Post.id, func.count(Reaction.id).label("reaction_count"))
                .distinct()
                .join(Round, Post.round == Round.id)
                .join(Reaction, Post.id == Reaction.post_id)
                .join(User_mgmt, Reaction.user_id == User_mgmt.id)
                .join(UserInterest1_add, User_mgmt.id == UserInterest1_add.user_id)
                .join(
                    UserInterest2_add,
                    UserInterest1_add.interest_id == UserInterest2_add.interest_id,
                )
                .filter(
                    UserInterest2_add.user_id == agent_id,
                    or_(
                        Round.day > visibility_day,
                        and_(Round.day == visibility_day, Round.hour >= visibility_hour),
                    ),
                    Post.user_id != agent_id,
                    Post.id.notin_(post_ids),
                )
                .group_by(Post.id)
                .order_by(desc("reaction_count"), desc(Round.day), desc(Round.hour))
                .limit(additional_posts_limit)
            )

            post_ids.extend([row[0] for row in query_additional.all()])

    # Cold start fallback: if no results, return random posts
    if not post_ids:
        post_ids = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return post_ids, True

    return post_ids, False


def recommend_similar_users_react(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Posts from similar users (based on demographics/personality) that they reacted to.
    Similarity defined by age_group, gender, or political leaning.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Alias for user_mgmt to differentiate between reactor and target
    ReactorUser = aliased(User_mgmt)
    TargetUser = aliased(User_mgmt)

    query = (
        session.query(Post.id)
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Reaction, Post.id == Reaction.post_id)
        .join(ReactorUser, Reaction.user_id == ReactorUser.id)
        .join(TargetUser, TargetUser.id == agent_id)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            ReactorUser.id != agent_id,
            Reaction.type == "LIKE",
            or_(
                ReactorUser.age_group == TargetUser.age_group,
                ReactorUser.gender == TargetUser.gender,
                ReactorUser.leaning == TargetUser.leaning,
            ),
        )
        .group_by(Post.id)
        .order_by(desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_similar_users_posts(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Posts created by similar users (based on demographics/personality).
    Similarity defined by age_group, gender, or political leaning.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Alias for user_mgmt to differentiate between post author and target
    PostAuthor = aliased(User_mgmt)
    TargetUser = aliased(User_mgmt)

    query = (
        session.query(Post.id)
        .join(Round, Post.round == Round.id)
        .join(PostAuthor, Post.user_id == PostAuthor.id)
        .join(TargetUser, TargetUser.id == agent_id)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
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

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_collaborative_user_user(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Collaborative Filtering - User-User.
    Finds users with a high overlap in liked posts and recommends posts they liked.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Get posts liked by the agent
    agent_likes_subq = (
        session.query(Reaction.post_id)
        .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
        .subquery()
    )

    # Find users who liked similar posts (high overlap)
    # Count how many posts each user has in common with the agent
    similar_users_subq = (
        session.query(Reaction.user_id, func.count(Reaction.post_id).label("common_likes_count"))
        .filter(
            Reaction.post_id.in_(agent_likes_subq),
            Reaction.user_id != agent_id,
            Reaction.type == "LIKE",
        )
        .group_by(Reaction.user_id)
        .order_by(desc("common_likes_count"))
        .limit(50)  # Top 50 similar users
        .subquery()
    )

    # Get posts liked by similar users (but not by agent)
    query = (
        session.query(Post.id, func.count(Reaction.id).label("recommendation_score"))
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Reaction, Post.id == Reaction.post_id)
        .join(similar_users_subq, Reaction.user_id == similar_users_subq.c.user_id)
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            Reaction.type == "LIKE",
            Post.id.notin_(agent_likes_subq),
        )
        .group_by(Post.id)
        .order_by(desc("recommendation_score"), desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_collaborative_item_item(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Collaborative Filtering - Item-Item.
    Finds posts that are often liked together by the same groups.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Get posts liked by the agent
    agent_likes_subq = (
        session.query(Reaction.post_id)
        .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
        .subquery()
    )

    # For each post the agent liked, find other posts liked by the same users
    # Alias for the second reaction
    Reaction2 = aliased(Reaction)

    query = (
        session.query(Post.id, func.count(Reaction2.user_id).label("co_occurrence_score"))
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(Reaction2, Post.id == Reaction2.post_id)
        .join(
            Reaction,
            and_(
                Reaction.user_id == Reaction2.user_id,
                Reaction.post_id.in_(agent_likes_subq),
            ),
        )
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            Reaction2.type == "LIKE",
            Reaction.type == "LIKE",
            Post.id.notin_(agent_likes_subq),
        )
        .group_by(Post.id)
        .order_by(desc("co_occurrence_score"), desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_content_based_features(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Content Based Filtering - Feature Extraction.
    Analyzes attributes of content the user has interacted with (hashtags, topics).

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Get topics from posts the agent has liked
    liked_topics_subq = (
        session.query(PostTopic.topic_id, func.count(PostTopic.topic_id).label("topic_freq"))
        .join(Reaction, PostTopic.post_id == Reaction.post_id)
        .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
        .group_by(PostTopic.topic_id)
        .subquery()
    )

    # Find new posts with matching topics
    query = (
        session.query(Post.id, func.count(PostTopic.topic_id).label("feature_match_score"))
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(PostTopic, Post.id == PostTopic.post_id)
        .join(liked_topics_subq, PostTopic.topic_id == liked_topics_subq.c.topic_id)
        .outerjoin(Reaction, and_(Reaction.post_id == Post.id, Reaction.user_id == agent_id))
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            Reaction.id.is_(None),  # Not already reacted to
        )
        .group_by(Post.id)
        .order_by(desc("feature_match_score"), desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_content_based_vector(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> tuple[List[str], bool]:
    """
    Content Based Filtering - Vector Space Similarity.
    Recommends new posts mathematically close to the user's "preference vector".
    Uses topic distribution as a simple vector representation.

    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend

    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    # Build user preference vector from liked posts' topics
    # Get all topics from posts the agent has liked, weighted by frequency
    user_topics_subq = (
        session.query(PostTopic.topic_id, func.count(PostTopic.topic_id).label("weight"))
        .join(Reaction, PostTopic.post_id == Reaction.post_id)
        .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
        .group_by(PostTopic.topic_id)
        .subquery()
    )

    # Calculate similarity score for each candidate post
    # Similarity = sum of weights for matching topics
    query = (
        session.query(Post.id, func.sum(user_topics_subq.c.weight).label("similarity_score"))
        .distinct()
        .join(Round, Post.round == Round.id)
        .join(PostTopic, Post.id == PostTopic.post_id)
        .join(user_topics_subq, PostTopic.topic_id == user_topics_subq.c.topic_id)
        .outerjoin(Reaction, and_(Reaction.post_id == Post.id, Reaction.user_id == agent_id))
        .filter(
            or_(
                Round.day > visibility_day,
                and_(Round.day == visibility_day, Round.hour >= visibility_hour),
            ),
            Post.user_id != agent_id,
            Reaction.id.is_(None),  # Not already reacted to
        )
        .group_by(Post.id)
        .order_by(desc("similarity_score"), desc(Round.day), desc(Round.hour))
        .limit(limit)
    )

    results = [row[0] for row in query.all()]

    # Cold start fallback: if no results, return random posts
    if not results:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True

    return results, False


def recommend_hybrid_linear_ranker(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
) -> tuple[List[str], bool]:
    """
    Hybrid content recommendation system with two-stage process (SQL backend).
    
    Stage 1: Candidate Generation (SQL)
      - Combines rchrono_followers, rchrono_popularity, and collaborative_user_user
      - Union and deduplicate results
    
    Stage 2: Linear Ranker (Python)
      - Fetches post metadata from SQL
      - Computes features in Python
      - Scores with weighted linear combination:
        score = 0.28 * recency_score +
                0.25 * is_followed_author +
                0.15 * user_author_affinity +
                0.08 * recent_user_author_affinity +
                0.16 * content_topic_similarity +
                0.08 * similar_user_author
    
    Args:
        session: SQLAlchemy session object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
    
    Returns:
        Tuple of (List of post UUIDs, bool indicating if fallback was used)
    """
    import math
    
    used_fallback = False
    
    # ==========================================
    # STAGE 1: CANDIDATE GENERATION (SQL)
    # ==========================================
    
    candidate_limit = min(limit * 10, 100)
    candidates_set = set()
    
    # 1. rchrono_followers
    try:
        cand1, fb1 = recommend_rchrono_followers(
            session, agent_id, visibility_day, visibility_hour, candidate_limit, followers_ratio=0.6
        )
        candidates_set.update(cand1)
        used_fallback = used_fallback or fb1
    except Exception:
        pass
    
    # 2. rchrono_popularity
    try:
        cand2 = recommend_rchrono_popularity(
            session, agent_id, visibility_day, visibility_hour, candidate_limit
        )
        candidates_set.update(cand2)
    except Exception:
        pass
    
    # 3. collaborative_user_user
    try:
        cand3, fb3 = recommend_collaborative_user_user(
            session, agent_id, visibility_day, visibility_hour, candidate_limit
        )
        candidates_set.update(cand3)
        used_fallback = used_fallback or fb3
    except Exception:
        pass
    
    # If no candidates, fall back to random
    if not candidates_set:
        results = recommend_random(session, agent_id, visibility_day, visibility_hour, limit)
        return results, True
    
    # ==========================================
    # STAGE 2: FEATURE EXTRACTION & RANKING (PYTHON)
    # ==========================================
    
    # Get current round for recency calculation
    current_round_query = session.query(Round).order_by(desc(Round.day), desc(Round.hour)).first()
    if current_round_query:
        current_day = current_round_query.day
        current_hour = current_round_query.hour
        current_round = current_day * 24 + current_hour  # Approximate round number
    else:
        current_round = 0
    
    tau = 10.0  # Decay parameter for recency
    
    # Get followed users
    followed_users = set(
        row[0] for row in session.query(Follow.follower_id)
        .filter(Follow.user_id == agent_id, Follow.action == "follow")
        .all()
    )
    
    # Get user's topic interests
    user_interests = set(
        row[0] for row in session.query(UserInterest.topic_id)
        .filter(UserInterest.user_id == agent_id)
        .all()
    )
    
    # Fetch post metadata for all candidates
    posts_query = (
        session.query(
            Post.id,
            Post.user_id,
            Post.round,
            Post.reaction_count,
            Round.day,
            Round.hour
        )
        .join(Round, Post.round == Round.id)
        .filter(Post.id.in_(candidates_set))
        .all()
    )
    
    # Score each candidate in Python
    post_scores = []
    for post_id, author_id, round_id, reaction_count, post_day, post_hour in posts_query:
        if author_id == agent_id:  # Skip own posts
            continue
        
        # Feature 1: Recency score (exponential decay)
        post_round_num = post_day * 24 + post_hour
        age_rounds = max(0, current_round - post_round_num)
        recency_score = math.exp(-age_rounds / tau)
        
        # Feature 2: Is followed author
        is_followed_author = 1.0 if author_id in followed_users else 0.0
        
        # Feature 3: User-author affinity (engagement count, log scale)
        user_author_affinity = _calculate_user_author_affinity_sql(
            session, agent_id, author_id
        )
        
        # Feature 4: Recent user-author affinity (simplified)
        recent_user_author_affinity = user_author_affinity * 0.5
        
        # Feature 5: Content topic similarity
        content_topic_similarity = _calculate_content_topic_similarity_sql(
            session, post_id, user_interests
        )
        
        # Feature 6: Similar user author score
        similar_user_author = _calculate_similar_user_author_score_sql(
            session, agent_id, author_id
        )
        
        # Calculate composite score with weights
        composite_score = (
            0.28 * recency_score +
            0.25 * is_followed_author +
            0.15 * user_author_affinity +
            0.08 * recent_user_author_affinity +
            0.16 * content_topic_similarity +
            0.08 * similar_user_author
        )
        
        post_scores.append((post_id, composite_score))
    
    # Sort by score descending
    post_scores.sort(key=lambda x: -x[1])
    
    # Return top N
    results = [post_id for post_id, score in post_scores[:limit]]
    
    # If not enough results, fill with random
    if len(results) < limit:
        additional = recommend_random(session, agent_id, visibility_day, visibility_hour, limit - len(results))
        results.extend([p for p in additional if p not in results])
        used_fallback = True
    
    return results, used_fallback


# ==========================================
# HELPER FUNCTIONS FOR HYBRID RECOMMENDER (SQL)
# ==========================================

def _calculate_user_author_affinity_sql(session, agent_id: str, author_id: str) -> float:
    """
    Calculate user-author affinity based on engagement count (log scale).
    affinity = log(1 + interactions_user_author)
    """
    import math
    
    # Count likes on author's posts
    likes_count = (
        session.query(Reaction)
        .join(Post, Reaction.post_id == Post.id)
        .filter(
            Reaction.user_id == agent_id,
            Post.user_id == author_id,
            Reaction.type == "LIKE"
        )
        .count()
    )
    
    # Count comments on author's posts (if Reply table exists)
    try:
        from YSimulator.YServer.classes.models import Reply
        comments_count = (
            session.query(Reply)
            .join(Post, Reply.post_id == Post.id)
            .filter(
                Reply.user_id == agent_id,
                Post.user_id == author_id
            )
            .count()
        )
    except ImportError:
        comments_count = 0
    
    interactions = likes_count + comments_count
    return math.log(1 + interactions)


def _calculate_content_topic_similarity_sql(session, post_id: str, user_interests: set) -> float:
    """
    Calculate content topic similarity using Jaccard similarity.
    """
    if not user_interests:
        return 0.0
    
    # Get post topics
    post_topics = set(
        row[0] for row in session.query(PostTopic.topic_id)
        .filter(PostTopic.post_id == post_id)
        .all()
    )
    
    if not post_topics:
        return 0.0
    
    # Jaccard similarity
    intersection = len(user_interests & post_topics)
    union = len(user_interests | post_topics)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def _calculate_similar_user_author_score_sql(session, agent_id: str, author_id: str) -> float:
    """
    Calculate how many similar users follow this author (log scale).
    Similar users = users with overlapping liked posts.
    """
    import math
    
    # Get agent's liked posts
    agent_likes = set(
        row[0] for row in session.query(Reaction.post_id)
        .filter(Reaction.user_id == agent_id, Reaction.type == "LIKE")
        .all()
    )
    
    if not agent_likes:
        return 0.0
    
    # Find similar users (users who liked similar posts) - limit for performance
    similar_users_query = (
        session.query(Reaction.user_id, func.count(Reaction.post_id).label("overlap"))
        .filter(
            Reaction.post_id.in_(agent_likes),
            Reaction.user_id != agent_id,
            Reaction.type == "LIKE"
        )
        .group_by(Reaction.user_id)
        .having(func.count(Reaction.post_id) > 0)
        .limit(100)
    )
    similar_users = set(row[0] for row in similar_users_query.all())
    
    if not similar_users:
        return 0.0
    
    # Count how many similar users follow this author
    count = (
        session.query(Follow)
        .filter(
            Follow.user_id.in_(similar_users),
            Follow.follower_id == author_id,
            Follow.action == "follow"
        )
        .count()
    )
    
    return math.log(1 + count)
