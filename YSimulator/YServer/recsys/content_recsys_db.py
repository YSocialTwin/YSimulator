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
) -> List[str]:
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
        List of post UUIDs
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

    return post_ids


def recommend_common_user_interests(
    session,
    agent_id: str,
    visibility_day: int,
    visibility_hour: int,
    limit: int,
    followers_ratio: float,
) -> List[str]:
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
        List of post UUIDs
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

    return post_ids


def recommend_similar_users_react(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
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
        List of post UUIDs
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
            Reaction.type == "like",
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

    return [row[0] for row in query.all()]


def recommend_similar_users_posts(
    session, agent_id: str, visibility_day: int, visibility_hour: int, limit: int
) -> List[str]:
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
        List of post UUIDs
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

    return [row[0] for row in query.all()]
