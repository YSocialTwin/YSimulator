"""
Redis-based content recommendation strategies.

Each function implements a specific recommendation algorithm using Redis key-value operations.
"""
from typing import List, Dict, Any, Set, Optional
import random
from sqlalchemy import text


def recommend_rchrono_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    **kwargs
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
    return [p['id'] for p in valid_posts_with_data[:limit]]


def recommend_rchrono_popularity_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    **kwargs
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
    sorted_posts = sorted(
        valid_posts_with_data,
        key=lambda x: (x['index'], -x['reaction_count'])
    )
    return [p['id'] for p in sorted_posts[:limit]]


def recommend_rchrono_followers_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    followers_ratio: float,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    db_engine,
    **kwargs
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
    
    # Get followed user IDs from database
    with db_engine.begin() as connection:
        result = connection.execute(
            text("SELECT follower_id FROM follow WHERE user_id = :agent_id AND action = 'follow'"),
            {"agent_id": agent_id}
        )
        followed_user_ids = set(row[0] for row in result)
    
    # Create mapping for efficient lookup (avoid O(n²))
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
    
    # Filter posts by followed users
    follower_posts = []
    other_posts = []
    for post in valid_posts_with_data:
        post_data = post_id_to_data.get(post['id'])
        if post_data and post_data.get('user_id') in followed_user_ids:
            follower_posts.append(post)
        else:
            other_posts.append(post)
    
    # Take from followers first, then fill with others
    post_ids = [p['id'] for p in follower_posts[:follower_posts_limit]]
    if len(post_ids) < limit:
        post_ids.extend([p['id'] for p in other_posts[:additional_posts_limit]])
    
    return post_ids


def recommend_rchrono_followers_popularity_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    followers_ratio: float,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    db_engine,
    **kwargs
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
    
    # Get follow relationships
    with db_engine.begin() as connection:
        result = connection.execute(
            text("SELECT follower_id FROM follow WHERE user_id = :agent_id AND action = 'follow'"),
            {"agent_id": agent_id}
        )
        followed_user_ids = set(row[0] for row in result)
    
    # Create mapping for efficient lookup
    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
    
    # Filter and sort
    follower_posts = []
    other_posts = []
    for post in valid_posts_with_data:
        post_data = post_id_to_data.get(post['id'])
        if post_data and post_data.get('user_id') in followed_user_ids:
            follower_posts.append(post)
        else:
            other_posts.append(post)
    
    # Sort by index (time) then popularity
    follower_posts_sorted = sorted(follower_posts, key=lambda x: (x['index'], -x['reaction_count']))
    other_posts_sorted = sorted(other_posts, key=lambda x: (x['index'], -x['reaction_count']))
    
    post_ids = [p['id'] for p in follower_posts_sorted[:follower_posts_limit]]
    if len(post_ids) < limit:
        post_ids.extend([p['id'] for p in other_posts_sorted[:additional_posts_limit]])
    
    return post_ids


def recommend_rchrono_comments_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    agent_id: str,
    all_post_ids: List[str],
    posts_data: List[Dict[str, bytes]],
    **kwargs
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
        if post_data and post_data.get('user_id') != agent_id:
            post_id = all_post_ids[i]
            # Check if this is a top-level post (not a comment itself)
            if post_data.get('comment_to', '-1') == '-1':
                # Count comments by checking other posts
                comment_count = sum(1 for pd in posts_data if pd and pd.get('comment_to') == post_id)
                posts_with_comment_counts.append({
                    'id': post_id,
                    'index': i,
                    'comment_count': comment_count,
                    'reaction_count': int(post_data.get("reaction_count", 0) or 0)
                })
    
    # Sort by comment count desc, then by recency
    sorted_posts = sorted(posts_with_comment_counts, key=lambda x: (-x['comment_count'], x['index']))
    return [p['id'] for p in sorted_posts[:limit]]


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
    **kwargs
) -> List[str]:
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
        List of post IDs with matching topic interests
    """
    # Try to get user interests from Redis
    user_interests_key = redis_key_fn("user", agent_id) + ":interests"
    if redis_client.exists(user_interests_key):
        # Redis implementation when data is available
        user_interests = redis_client.smembers(user_interests_key)
        
        # Create mapping for efficient lookup
        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
        
        # Score posts by number of matching interests
        posts_with_scores = []
        for post in valid_posts_with_data:
            post_topics_key = redis_key_fn("post", post['id']) + ":topics"
            if redis_client.exists(post_topics_key):
                post_topics = redis_client.smembers(post_topics_key)
                # Calculate intersection (common interests)
                common_count = len(user_interests & post_topics)
                if common_count > 0:
                    posts_with_scores.append({
                        'id': post['id'],
                        'index': post['index'],
                        'score': common_count
                    })
        
        # Sort by score desc, then by recency
        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
        post_ids = [p['id'] for p in sorted_posts[:limit]]
        
        # Fill with recent posts if needed
        if len(post_ids) < limit:
            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
            post_ids.extend(additional[:limit - len(post_ids)])
    else:
        # Fallback to SQL query when Redis data not available yet
        logger.info(f"Mode common_interests - Redis cache for interests/topics not available yet, using SQL")
        with db_engine.begin() as connection:
            query = text("""
                SELECT DISTINCT p.id
                FROM post p
                INNER JOIN post_topic pt ON p.id = pt.post_id
                INNER JOIN user_interest ui ON pt.topic_id = ui.topic_id
                WHERE ui.user_id = :agent_id AND p.user_id != :agent_id
                ORDER BY p.id DESC
                LIMIT :limit
            """)
            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
            sql_post_ids = [row[0] for row in result]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
            
            if len(post_ids) < limit:
                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                post_ids.extend(additional[:limit - len(post_ids)])
    
    return post_ids


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
    **kwargs
) -> List[str]:
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
        List of post IDs liked by users with common interests
    """
    user_interests_key = redis_key_fn("user", agent_id) + ":interests"
    if redis_client.exists(user_interests_key):
        # Redis implementation when data is available
        user_interests = redis_client.smembers(user_interests_key)
        
        # Find users with common interests
        user_ids_key = redis_key_fn("user_mgmt", "ids")
        all_user_ids = redis_client.smembers(user_ids_key) if redis_client.exists(user_ids_key) else []
        
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
        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
        
        for post in valid_posts_with_data:
            # Check if any similar user liked this post
            post_reactions_key = redis_key_fn("post", post['id']) + ":reactions"
            if redis_client.exists(post_reactions_key):
                reaction_user_ids = redis_client.smembers(post_reactions_key)
                common_users = similar_users & reaction_user_ids
                if common_users:
                    posts_with_scores.append({
                        'id': post['id'],
                        'index': post['index'],
                        'score': len(common_users)
                    })
        
        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
        post_ids = [p['id'] for p in sorted_posts[:limit]]
        
        if len(post_ids) < limit:
            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
            post_ids.extend(additional[:limit - len(post_ids)])
    else:
        # Fallback to SQL
        logger.info(f"Mode common_user_interests - Redis cache for interests not available yet, using SQL")
        with db_engine.begin() as connection:
            query = text("""
                SELECT DISTINCT p.id
                FROM post p
                INNER JOIN reaction r ON p.id = r.post_id
                INNER JOIN user_interest ui1 ON r.user_id = ui1.user_id
                INNER JOIN user_interest ui2 ON ui1.topic_id = ui2.topic_id
                WHERE ui2.user_id = :agent_id 
                    AND r.user_id != :agent_id 
                    AND p.user_id != :agent_id
                    AND r.type = 'like'
                ORDER BY p.id DESC
                LIMIT :limit
            """)
            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
            sql_post_ids = [row[0] for row in result]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
            
            if len(post_ids) < limit:
                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                post_ids.extend(additional[:limit - len(post_ids)])
    
    return post_ids


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
    **kwargs
) -> List[str]:
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
        List of post IDs liked by similar users
    """
    # Get agent demographics from Redis
    agent_key = redis_key_fn("users", agent_id)
    agent_data = redis_client.hgetall(agent_key) if redis_client.exists(agent_key) else {}
    
    if agent_data:
        # Redis implementation using cached user data
        agent_age_group = agent_data.get('age_group')
        agent_gender = agent_data.get('gender')
        agent_leaning = agent_data.get('leaning')
        
        # Create mapping
        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
        
        # Get posts liked by similar users
        posts_with_scores = []
        for post in valid_posts_with_data:
            # Check reactions for this post
            post_reactions_key = redis_key_fn("post", post['id']) + ":reactions"
            if redis_client.exists(post_reactions_key):
                reaction_user_ids = redis_client.smembers(post_reactions_key)
                similar_count = 0
                for uid in reaction_user_ids:
                    user_key = redis_key_fn("users", uid)
                    user_data = redis_client.hgetall(user_key) if redis_client.exists(user_key) else {}
                    if user_data:
                        # Check similarity
                        if (user_data.get('age_group') == agent_age_group or
                            user_data.get('gender') == agent_gender or
                            user_data.get('leaning') == agent_leaning):
                            similar_count += 1
                
                if similar_count > 0:
                    posts_with_scores.append({
                        'id': post['id'],
                        'index': post['index'],
                        'score': similar_count
                    })
        
        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
        post_ids = [p['id'] for p in sorted_posts[:limit]]
        
        # Fill with recent posts if needed
        if len(post_ids) < limit:
            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
            post_ids.extend(additional[:limit - len(post_ids)])
    else:
        # Fallback to SQL query
        logger.info(f"Mode similar_users_react - Using SQL for user demographics query")
        with db_engine.begin() as connection:
            query = text("""
                SELECT DISTINCT p.id
                FROM post p
                INNER JOIN reaction r ON p.id = r.post_id
                INNER JOIN user_mgmt um ON r.user_id = um.id
                INNER JOIN user_mgmt target ON target.id = :agent_id
                WHERE p.user_id != :agent_id
                    AND um.id != :agent_id
                    AND r.type = 'like'
                    AND (
                        (um.age_group = target.age_group) OR
                        (um.gender = target.gender) OR
                        (um.leaning = target.leaning)
                    )
                ORDER BY p.id DESC
                LIMIT :limit
            """)
            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
            sql_post_ids = [row[0] for row in result]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
            
            if len(post_ids) < limit:
                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                post_ids.extend(additional[:limit - len(post_ids)])
    
    return post_ids


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
    **kwargs
) -> List[str]:
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
        List of post IDs from similar users
    """
    # Get agent demographics from Redis
    agent_key = redis_key_fn("users", agent_id)
    agent_data = redis_client.hgetall(agent_key) if redis_client.exists(agent_key) else {}
    
    if agent_data:
        # Redis implementation using cached user data
        agent_age_group = agent_data.get('age_group')
        agent_gender = agent_data.get('gender')
        agent_leaning = agent_data.get('leaning')
        
        # Create mapping
        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
        
        # Get posts from similar users
        posts_with_similarity = []
        for post in valid_posts_with_data:
            post_data = post_id_to_data.get(post['id'])
            if post_data:
                author_id = post_data.get('user_id')
                if author_id and author_id != agent_id:
                    author_key = redis_key_fn("users", author_id)
                    author_data = redis_client.hgetall(author_key) if redis_client.exists(author_key) else {}
                    if author_data:
                        similarity_score = 0
                        if author_data.get('age_group') == agent_age_group:
                            similarity_score += 1
                        if author_data.get('gender') == agent_gender:
                            similarity_score += 1
                        if author_data.get('leaning') == agent_leaning:
                            similarity_score += 1
                        
                        if similarity_score > 0:
                            posts_with_similarity.append({
                                'id': post['id'],
                                'index': post['index'],
                                'score': similarity_score
                            })
        
        sorted_posts = sorted(posts_with_similarity, key=lambda x: (-x['score'], x['index']))
        post_ids = [p['id'] for p in sorted_posts[:limit]]
        
        # Fill with recent posts if needed
        if len(post_ids) < limit:
            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
            post_ids.extend(additional[:limit - len(post_ids)])
    else:
        # Fallback to SQL query
        logger.info(f"Mode similar_users_posts - Using SQL for user demographics query")
        with db_engine.begin() as connection:
            query = text("""
                SELECT p.id
                FROM post p
                INNER JOIN user_mgmt um ON p.user_id = um.id
                INNER JOIN user_mgmt target ON target.id = :agent_id
                WHERE p.user_id != :agent_id
                    AND (
                        (um.age_group = target.age_group) OR
                        (um.gender = target.gender) OR
                        (um.leaning = target.leaning)
                    )
                ORDER BY p.id DESC
                LIMIT :limit
            """)
            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
            sql_post_ids = [row[0] for row in result]
            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
            
            if len(post_ids) < limit:
                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                post_ids.extend(additional[:limit - len(post_ids)])
    
    return post_ids


def recommend_random_redis(
    valid_posts_with_data: List[Dict[str, Any]],
    limit: int,
    **kwargs
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
        return [p['id'] for p in selected]
    else:
        return [p['id'] for p in valid_posts_with_data]
