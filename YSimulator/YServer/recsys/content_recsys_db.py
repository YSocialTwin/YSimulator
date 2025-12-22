"""
SQL-based content recommendation strategies.

Each function implements a specific recommendation algorithm using SQL queries for scalability.
All functions follow a consistent signature for easy integration with the server.
"""
from typing import List
from sqlalchemy import text


def recommend_random(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Random post ordering (default strategy).
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT p.id FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        ORDER BY RANDOM()
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "agent_id": agent_id,
        "limit": limit
    })
    return [row[0] for row in result]


def recommend_rchrono(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Reverse chronological ordering: newest posts first.
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT p.id FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        ORDER BY rd.day DESC, rd.hour DESC
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "agent_id": agent_id,
        "limit": limit
    })
    return [row[0] for row in result]


def recommend_rchrono_popularity(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Reverse chronological with popularity boost (reaction count).
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT p.id 
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        LEFT JOIN (
            SELECT post_id, COUNT(*) as reaction_count
            FROM reaction
            GROUP BY post_id
        ) r ON p.id = r.post_id
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        ORDER BY rd.day DESC, rd.hour DESC, COALESCE(r.reaction_count, 0) DESC
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "agent_id": agent_id,
        "limit": limit
    })
    return [row[0] for row in result]


def recommend_rchrono_followers(connection, agent_id: str, visibility_day: int, visibility_hour: int, 
                                 limit: int, followers_ratio: float) -> List[str]:
    """
    Prioritize posts from followed users, then fill with other posts.
    
    Args:
        connection: SQLAlchemy connection object
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
    query_followers = text("""
        SELECT DISTINCT p.id 
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN follow f ON p.user_id = f.follower_id
        WHERE f.user_id = :agent_id 
            AND f.action = 'follow'
            AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        ORDER BY rd.day DESC, rd.hour DESC
        LIMIT :follower_limit
    """)
    result = connection.execute(query_followers, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "follower_limit": follower_posts_limit
    })
    post_ids = [row[0] for row in result]
    
    # If we need more posts, get additional ones
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = text("""
                SELECT p.id FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                    AND p.user_id != :agent_id
                    AND p.id NOT IN :existing_ids
                ORDER BY rd.day DESC, rd.hour DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "agent_id": agent_id,
                "existing_ids": tuple(post_ids),
                "additional_limit": additional_posts_limit
            })
        else:
            # No existing posts, skip the NOT IN clause
            query_additional = text("""
                SELECT p.id FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                    AND p.user_id != :agent_id
                ORDER BY rd.day DESC, rd.hour DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "agent_id": agent_id,
                "additional_limit": additional_posts_limit
            })
        post_ids.extend([row[0] for row in result])
    
    return post_ids


def recommend_rchrono_followers_popularity(connection, agent_id: str, visibility_day: int, visibility_hour: int, 
                                           limit: int, followers_ratio: float) -> List[str]:
    """
    Followers with popularity boost (combines following and reaction count).
    
    Args:
        connection: SQLAlchemy connection object
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
    
    query_followers = text("""
        SELECT DISTINCT p.id 
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN follow f ON p.user_id = f.follower_id
        LEFT JOIN (
            SELECT post_id, COUNT(*) as reaction_count
            FROM reaction
            GROUP BY post_id
        ) r ON p.id = r.post_id
        WHERE f.user_id = :agent_id 
            AND f.action = 'follow'
            AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
        LIMIT :follower_limit
    """)
    result = connection.execute(query_followers, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "follower_limit": follower_posts_limit
    })
    post_ids = [row[0] for row in result]
    
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = text("""
                SELECT p.id 
                FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                LEFT JOIN (
                    SELECT post_id, COUNT(*) as reaction_count
                    FROM reaction
                    GROUP BY post_id
                ) r ON p.id = r.post_id
                WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour)) 
                    AND p.user_id != :agent_id
                    AND p.id NOT IN :existing_ids
                ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "agent_id": agent_id,
                "existing_ids": tuple(post_ids),
                "additional_limit": additional_posts_limit
            })
        else:
            query_additional = text("""
                SELECT p.id 
                FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                LEFT JOIN (
                    SELECT post_id, COUNT(*) as reaction_count
                    FROM reaction
                    GROUP BY post_id
                ) r ON p.id = r.post_id
                WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour)) 
                    AND p.user_id != :agent_id
                ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "agent_id": agent_id,
                "additional_limit": additional_posts_limit
            })
        post_ids.extend([row[0] for row in result])
    
    return post_ids


def recommend_rchrono_comments(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Prioritize posts with more comments (thread activity).
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT p.id
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        LEFT JOIN post c ON p.id = c.comment_to
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
            AND p.comment_to IS NULL
        GROUP BY p.id
        ORDER BY COUNT(c.id) DESC, rd.day DESC, rd.hour DESC
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "agent_id": agent_id,
        "limit": limit
    })
    return [row[0] for row in result]


def recommend_common_interests(connection, agent_id: str, visibility_day: int, visibility_hour: int,
                                limit: int, followers_ratio: float) -> List[str]:
    """
    Posts with common topic interests (based on user_interest and post_topics).
    Prioritizes posts from followed users, then fills with other posts.
    
    Args:
        connection: SQLAlchemy connection object
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
    query = text("""
        SELECT DISTINCT p.id
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN post_topics pt ON p.id = pt.post_id
        INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
        INNER JOIN follow f ON p.user_id = f.follower_id
        WHERE ui.user_id = :agent_id
            AND f.user_id = :agent_id
            AND f.action = 'follow'
            AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        GROUP BY p.id
        ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
        LIMIT :follower_limit
    """)
    result = connection.execute(query, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "follower_limit": follower_posts_limit
    })
    post_ids = [row[0] for row in result]
    
    # Get additional posts with common interests
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = text("""
                SELECT DISTINCT p.id
                FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                INNER JOIN post_topics pt ON p.id = pt.post_id
                INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
                WHERE ui.user_id = :agent_id
                    AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                    AND p.user_id != :agent_id
                    AND p.id NOT IN :existing_ids
                GROUP BY p.id
                ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "agent_id": agent_id,
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "existing_ids": tuple(post_ids),
                "additional_limit": additional_posts_limit
            })
        else:
            query_additional = text("""
                SELECT DISTINCT p.id
                FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                INNER JOIN post_topics pt ON p.id = pt.post_id
                INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
                WHERE ui.user_id = :agent_id
                    AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                    AND p.user_id != :agent_id
                GROUP BY p.id
                ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "agent_id": agent_id,
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "additional_limit": additional_posts_limit
            })
        post_ids.extend([row[0] for row in result])
    
    return post_ids


def recommend_common_user_interests(connection, agent_id: str, visibility_day: int, visibility_hour: int,
                                     limit: int, followers_ratio: float) -> List[str]:
    """
    Posts by users with common interests (most interacted).
    Prioritizes posts from followed users with common interests.
    
    Args:
        connection: SQLAlchemy connection object
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
    
    # Get posts reacted to by users with common interests who are followers
    query = text("""
        SELECT DISTINCT p.id, COUNT(r.id) as reaction_count
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN reaction r ON p.id = r.post_id
        INNER JOIN user_mgmt um ON r.user_id = um.id
        INNER JOIN user_interest ui1 ON um.id = ui1.user_id
        INNER JOIN user_interest ui2 ON ui1.interest_id = ui2.interest_id
        INNER JOIN follow f ON um.id = f.follower_id
        WHERE ui2.user_id = :agent_id
            AND f.user_id = :agent_id
            AND f.action = 'follow'
            AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
        GROUP BY p.id
        ORDER BY reaction_count DESC, rd.day DESC, rd.hour DESC
        LIMIT :follower_limit
    """)
    result = connection.execute(query, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "follower_limit": follower_posts_limit
    })
    post_ids = [row[0] for row in result]
    
    # Get additional from non-followers with common interests
    if len(post_ids) < limit and additional_posts_limit > 0:
        if post_ids:
            query_additional = text("""
                SELECT DISTINCT p.id, COUNT(r.id) as reaction_count
                FROM post p
                INNER JOIN rounds rd ON p.round = rd.id
                INNER JOIN reaction r ON p.id = r.post_id
                INNER JOIN user_mgmt um ON r.user_id = um.id
                INNER JOIN user_interest ui1 ON um.id = ui1.user_id
                INNER JOIN user_interest ui2 ON ui1.interest_id = ui2.interest_id
                WHERE ui2.user_id = :agent_id
                    AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                    AND p.user_id != :agent_id
                    AND p.id NOT IN :existing_ids
                GROUP BY p.id
                ORDER BY reaction_count DESC, rd.day DESC, rd.hour DESC
                LIMIT :additional_limit
            """)
            result = connection.execute(query_additional, {
                "agent_id": agent_id,
                "vis_day": visibility_day,
                "vis_hour": visibility_hour,
                "existing_ids": tuple(post_ids),
                "additional_limit": additional_posts_limit
            })
            post_ids.extend([row[0] for row in result])
    
    return post_ids


def recommend_similar_users_react(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Posts from similar users (based on demographics/personality) that they reacted to.
    Similarity defined by age_group, gender, or political leaning.
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT DISTINCT p.id
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN reaction r ON p.id = r.post_id
        INNER JOIN user_mgmt um ON r.user_id = um.id
        INNER JOIN user_mgmt target ON target.id = :agent_id
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
            AND um.id != :agent_id
            AND r.type = 'like'
            AND (
                (um.age_group = target.age_group) OR
                (um.gender = target.gender) OR
                (um.leaning = target.leaning)
            )
        GROUP BY p.id
        ORDER BY rd.day DESC, rd.hour DESC
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "limit": limit
    })
    return [row[0] for row in result]


def recommend_similar_users_posts(connection, agent_id: str, visibility_day: int, visibility_hour: int, limit: int) -> List[str]:
    """
    Posts created by similar users (based on demographics/personality).
    Similarity defined by age_group, gender, or political leaning.
    
    Args:
        connection: SQLAlchemy connection object
        agent_id: UUID of the agent requesting recommendations
        visibility_day: Day threshold for post visibility
        visibility_hour: Hour threshold for post visibility
        limit: Number of posts to recommend
        
    Returns:
        List of post UUIDs
    """
    query = text("""
        SELECT p.id
        FROM post p
        INNER JOIN rounds rd ON p.round = rd.id
        INNER JOIN user_mgmt um ON p.user_id = um.id
        INNER JOIN user_mgmt target ON target.id = :agent_id
        WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
            AND p.user_id != :agent_id
            AND (
                (um.age_group = target.age_group) OR
                (um.gender = target.gender) OR
                (um.leaning = target.leaning)
            )
        ORDER BY rd.day DESC, rd.hour DESC
        LIMIT :limit
    """)
    result = connection.execute(query, {
        "agent_id": agent_id,
        "vis_day": visibility_day,
        "vis_hour": visibility_hour,
        "limit": limit
    })
    return [row[0] for row in result]
