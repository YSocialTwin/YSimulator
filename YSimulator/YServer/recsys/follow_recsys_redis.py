"""
Redis-based follow recommendation strategies.

This module contains isolated functions for computing follow recommendations
using Redis key-value operations for better scalability.
"""

import math
import random
from typing import List

from redis import Redis


def recommend_random_follows_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Recommend random users to follow.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs
    """
    try:
        # Get all user IDs
        user_ids_key = redis_key_func("user_mgmt", "ids")
        all_user_ids = list(redis_client.smembers(user_ids_key))

        if not all_user_ids:
            return []

        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Get candidates (not following, not self)
        candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]

        if not candidates:
            return []

        # Random selection
        random.shuffle(candidates)
        return candidates[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_random_follows_redis: {e}")
        return []


def recommend_preferential_attachment_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Recommend users with many followers (preferential attachment).

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs sorted by follower count
    """
    try:
        # Get all user IDs
        user_ids_key = redis_key_func("user_mgmt", "ids")
        all_user_ids = list(redis_client.smembers(user_ids_key))

        if not all_user_ids:
            return []

        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Get candidates
        candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]

        if not candidates:
            return []

        # Count followers for each candidate
        follower_counts = {}
        for candidate in candidates:
            count = 0
            for key in follow_keys:
                follow_data = redis_client.hgetall(key)
                if (
                    follow_data.get("user_id") == candidate
                    and follow_data.get("action") == "follow"
                ):
                    count += 1
            follower_counts[candidate] = count

        # Sort by follower count
        sorted_candidates = sorted(follower_counts.items(), key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in sorted_candidates[:n_neighbors]]

    except Exception as e:
        logger.error(f"Error in recommend_preferential_attachment_redis: {e}")
        return []


def recommend_common_neighbors_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Recommend users that agent's friends also follow (friend-of-friend).

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs sorted by common neighbor count
    """
    try:
        # Get all user IDs
        user_ids_key = redis_key_func("user_mgmt", "ids")
        all_user_ids = list(redis_client.smembers(user_ids_key))

        if not all_user_ids:
            return []

        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Get candidates
        candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]

        if not candidates or not following_ids:
            # Fallback to random if no friends
            random.shuffle(candidates)
            return candidates[:n_neighbors]

        # Find users that agent's friends also follow
        common_neighbor_counts = {}
        for candidate in candidates:
            common_count = 0
            # Check how many of agent's friends also follow this candidate
            for friend_id in following_ids:
                # Check if friend follows candidate
                for key in follow_keys:
                    follow_data = redis_client.hgetall(key)
                    if (
                        follow_data.get("follower_id") == friend_id
                        and follow_data.get("user_id") == candidate
                        and follow_data.get("action") == "follow"
                    ):
                        common_count += 1
                        break
            common_neighbor_counts[candidate] = common_count

        # Sort by common neighbor count
        sorted_candidates = sorted(common_neighbor_counts.items(), key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in sorted_candidates[:n_neighbors]]

    except Exception as e:
        logger.error(f"Error in recommend_common_neighbors_redis: {e}")
        return []


def recommend_jaccard_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Recommend users using Jaccard similarity of follow sets.
    For Redis implementation, uses same logic as common neighbors.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs sorted by Jaccard similarity
    """
    # For Redis, we use the same approach as common neighbors
    # Full Jaccard calculation would be too expensive with key-value operations
    return recommend_common_neighbors_redis(
        redis_client, redis_key_func, agent_id, n_neighbors, logger
    )


def recommend_adamic_adar_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Recommend users using Adamic/Adar index with Redis.
    Two-step approach:
    1. Find common neighbors (friend-of-friend candidates)
    2. Calculate Adamic/Adar score: Σ(1/log(degree)) for each common neighbor

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs sorted by Adamic/Adar score
    """
    try:
        # Get all user IDs
        user_ids_key = redis_key_func("user_mgmt", "ids")
        all_user_ids = list(redis_client.smembers(user_ids_key))

        if not all_user_ids:
            return []

        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Get candidates
        candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]

        if not candidates or not following_ids:
            # Fallback to random if no friends
            random.shuffle(candidates)
            return candidates[:n_neighbors]

        # Step 1: Build candidate -> common neighbors mapping
        candidate_common_neighbors = {}
        for candidate in candidates:
            common_neighbors = []
            # Find which of agent's friends also follow this candidate
            for friend_id in following_ids:
                # Check if friend follows candidate
                for key in follow_keys:
                    follow_data = redis_client.hgetall(key)
                    if (
                        follow_data.get("follower_id") == friend_id
                        and follow_data.get("user_id") == candidate
                        and follow_data.get("action") == "follow"
                    ):
                        common_neighbors.append(friend_id)
                        break
            if common_neighbors:
                candidate_common_neighbors[candidate] = common_neighbors

        if not candidate_common_neighbors:
            # No common neighbors found
            random.shuffle(candidates)
            return candidates[:n_neighbors]

        # Step 2: Calculate degree for each common neighbor
        neighbor_degrees = {}
        all_common_neighbors = set()
        for neighbors in candidate_common_neighbors.values():
            all_common_neighbors.update(neighbors)

        for neighbor in all_common_neighbors:
            # Count how many users this neighbor follows
            degree = 0
            for key in follow_keys:
                follow_data = redis_client.hgetall(key)
                if (
                    follow_data.get("follower_id") == neighbor
                    and follow_data.get("action") == "follow"
                ):
                    degree += 1
            neighbor_degrees[neighbor] = max(degree, 1)  # At least 1 to avoid division issues

        # Step 3: Calculate Adamic/Adar score for each candidate
        adamic_adar_scores = {}
        for candidate, neighbors in candidate_common_neighbors.items():
            score = 0.0
            for neighbor in neighbors:
                degree = neighbor_degrees.get(neighbor, 1)
                if degree > 1:  # Only count if degree > 1 (log(1) = 0)
                    score += 1.0 / math.log(degree)
            adamic_adar_scores[candidate] = score

        # Sort by Adamic/Adar score (highest first)
        sorted_candidates = sorted(adamic_adar_scores.items(), key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in sorted_candidates[:n_neighbors]]

    except Exception as e:
        logger.error(f"Error in recommend_adamic_adar_redis: {e}")
        return []


def recommend_resource_allocation_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Resource Allocation index follow recommendation (Redis).

    Similar to Adamic/Adar but uses 1/degree instead of 1/log(degree).

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs
    """
    try:
        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        if not following_ids:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Find friend-of-friend candidates with their common neighbors
        candidate_common_neighbors = {}
        for friend_id in following_ids:
            # Get friends of friend
            for key in follow_keys:
                follow_data = redis_client.hgetall(key)
                if (
                    follow_data.get("follower_id") == friend_id
                    and follow_data.get("action") == "follow"
                ):
                    fof_id = follow_data.get("user_id")
                    if fof_id != agent_id and fof_id not in following_ids:
                        if fof_id not in candidate_common_neighbors:
                            candidate_common_neighbors[fof_id] = []
                        candidate_common_neighbors[fof_id].append(friend_id)

        if not candidate_common_neighbors:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Calculate Resource Allocation scores
        ra_scores = {}
        for candidate_id, common_neighbors in candidate_common_neighbors.items():
            score = 0.0
            for neighbor_id in common_neighbors:
                # Count degree of common neighbor
                degree = 0
                for key in follow_keys:
                    follow_data = redis_client.hgetall(key)
                    if (
                        follow_data.get("follower_id") == neighbor_id
                        and follow_data.get("action") == "follow"
                    ):
                        degree += 1
                # Resource Allocation: 1/degree
                if degree > 0:
                    score += 1.0 / degree
            ra_scores[candidate_id] = score

        # Sort by score (highest first)
        sorted_candidates = sorted(ra_scores.items(), key=lambda x: x[1], reverse=True)
        recommendations = [uid for uid, score in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(recommendations) < n_neighbors:
            remaining = n_neighbors - len(recommendations)
            user_ids_key = redis_key_func("user_mgmt", "ids")
            all_user_ids = list(redis_client.smembers(user_ids_key))
            candidates = [
                uid
                for uid in all_user_ids
                if uid != agent_id and uid not in following_ids and uid not in recommendations
            ]
            random.shuffle(candidates)
            recommendations.extend(candidates[:remaining])

        return recommendations[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_resource_allocation_redis: {e}")
        return recommend_random_follows_redis(
            redis_client, redis_key_func, agent_id, n_neighbors, logger
        )


def recommend_cosine_similarity_redis(
    redis_client: Redis,
    redis_key_func,
    agent_id: str,
    n_neighbors: int,
    logger,
    sample_size: int = 100,
) -> List[str]:
    """
    Cosine similarity on agents' profile vectors (Redis).

    Recommends users with similar profiles based on interests and personality traits.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance
        sample_size: Number of candidates to sample

    Returns:
        List of recommended user IDs
    """
    try:
        # Get agent's profile
        agent_key = redis_key_func("user_mgmt", agent_id)
        agent_data = redis_client.hgetall(agent_key)

        if not agent_data:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Get agent's interests
        user_interest_pattern = redis_key_func("user_interests", "*")
        user_interest_keys = redis_client.keys(user_interest_pattern)

        agent_interests = set()
        for key in user_interest_keys:
            interest_data = redis_client.hgetall(key)
            if interest_data.get("user_id") == agent_id:
                agent_interests.add(interest_data.get("interest_id"))

        # Get agent's personality traits
        agent_traits = {
            "openness": float(agent_data.get("openness", 0)),
            "conscientiousness": float(agent_data.get("conscientiousness", 0)),
            "extraversion": float(agent_data.get("extraversion", 0)),
            "agreeableness": float(agent_data.get("agreeableness", 0)),
            "neuroticism": float(agent_data.get("neuroticism", 0)),
        }

        # Get following IDs
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Get all user IDs
        user_ids_key = redis_key_func("user_mgmt", "ids")
        all_user_ids = list(redis_client.smembers(user_ids_key))
        candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]

        if not candidates:
            return []

        # Sample candidates for efficiency
        if len(candidates) > sample_size:
            candidates = random.sample(candidates, sample_size)

        # Calculate cosine similarity for each candidate
        similarities = {}
        for candidate_id in candidates:
            candidate_key = redis_key_func("user_mgmt", candidate_id)
            candidate_data = redis_client.hgetall(candidate_key)

            if not candidate_data:
                continue

            # Get candidate's interests
            candidate_interests = set()
            for key in user_interest_keys:
                interest_data = redis_client.hgetall(key)
                if interest_data.get("user_id") == candidate_id:
                    candidate_interests.add(interest_data.get("interest_id"))

            # Calculate interest similarity (Jaccard)
            if agent_interests or candidate_interests:
                intersection = len(agent_interests & candidate_interests)
                union = len(agent_interests | candidate_interests)
                interest_similarity = intersection / union if union > 0 else 0.0
            else:
                interest_similarity = 0.0

            # Get candidate's personality traits
            candidate_traits = {
                "openness": float(candidate_data.get("openness", 0)),
                "conscientiousness": float(candidate_data.get("conscientiousness", 0)),
                "extraversion": float(candidate_data.get("extraversion", 0)),
                "agreeableness": float(candidate_data.get("agreeableness", 0)),
                "neuroticism": float(candidate_data.get("neuroticism", 0)),
            }

            # Cosine similarity for personality traits
            dot_product = sum(agent_traits[k] * candidate_traits[k] for k in agent_traits)
            agent_norm = math.sqrt(sum(v**2 for v in agent_traits.values()))
            candidate_norm = math.sqrt(sum(v**2 for v in candidate_traits.values()))

            if agent_norm > 0 and candidate_norm > 0:
                trait_similarity = dot_product / (agent_norm * candidate_norm)
            else:
                trait_similarity = 0.0

            # Combined similarity (weighted: 70% interests, 30% traits)
            combined_similarity = 0.7 * interest_similarity + 0.3 * trait_similarity
            similarities[candidate_id] = combined_similarity

        # Sort by similarity (highest first)
        sorted_candidates = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        recommendations = [uid for uid, score in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(recommendations) < n_neighbors:
            remaining = n_neighbors - len(recommendations)
            extra_candidates = [uid for uid in candidates if uid not in recommendations]
            random.shuffle(extra_candidates)
            recommendations.extend(extra_candidates[:remaining])

        return recommendations[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_cosine_similarity_redis: {e}")
        return recommend_random_follows_redis(
            redis_client, redis_key_func, agent_id, n_neighbors, logger
        )


def recommend_co_engagement_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Co-engagement follow recommendation (Redis).

    Recommends users who interact with the same content.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs
    """
    try:
        # Get posts agent has reacted to
        reaction_pattern = redis_key_func("reactions", "*")
        reaction_keys = redis_client.keys(reaction_pattern)

        agent_post_ids = set()
        for key in reaction_keys:
            reaction_data = redis_client.hgetall(key)
            if reaction_data.get("user_id") == agent_id:
                agent_post_ids.add(reaction_data.get("post_id"))

        # Get agent's posts
        post_pattern = redis_key_func("post", "*")
        post_keys = redis_client.keys(post_pattern)

        for key in post_keys:
            post_data = redis_client.hgetall(key)
            if post_data.get("user_id") == agent_id:
                agent_post_ids.add(post_data.get("id"))

        if not agent_post_ids:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Get following IDs
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Find users who reacted to the same posts
        engagement_counts = {}
        for key in reaction_keys:
            reaction_data = redis_client.hgetall(key)
            post_id = reaction_data.get("post_id")
            user_id = reaction_data.get("user_id")

            if (
                post_id in agent_post_ids
                and user_id != agent_id
                and user_id not in following_ids
            ):
                engagement_counts[user_id] = engagement_counts.get(user_id, 0) + 1

        if not engagement_counts:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Sort by engagement count (highest first)
        sorted_candidates = sorted(engagement_counts.items(), key=lambda x: x[1], reverse=True)
        recommendations = [uid for uid, count in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(recommendations) < n_neighbors:
            remaining = n_neighbors - len(recommendations)
            user_ids_key = redis_key_func("user_mgmt", "ids")
            all_user_ids = list(redis_client.smembers(user_ids_key))
            candidates = [
                uid
                for uid in all_user_ids
                if uid != agent_id and uid not in following_ids and uid not in recommendations
            ]
            random.shuffle(candidates)
            recommendations.extend(candidates[:remaining])

        return recommendations[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_co_engagement_redis: {e}")
        return recommend_random_follows_redis(
            redis_client, redis_key_func, agent_id, n_neighbors, logger
        )


def recommend_random_walk_with_restart_redis(
    redis_client: Redis,
    redis_key_func,
    agent_id: str,
    n_neighbors: int,
    logger,
    k: int = 10,
    walk_length: int = 3,
    restart_prob: float = 0.15,
) -> List[str]:
    """
    Random Walk with Restart follow recommendation (Redis).

    Performs k random walks of specified length with restart probability.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance
        k: Number of random walks
        walk_length: Maximum walk length
        restart_prob: Probability of restarting

    Returns:
        List of recommended user IDs
    """
    try:
        # Get users agent is following
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        follow_graph = {}  # Map of follower_id -> list of user_ids they follow

        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("action") == "follow":
                follower_id = follow_data.get("follower_id")
                user_id = follow_data.get("user_id")

                if follower_id not in follow_graph:
                    follow_graph[follower_id] = []
                follow_graph[follower_id].append(user_id)

                if follower_id == agent_id:
                    following_ids.add(user_id)

        if not following_ids:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Perform random walks
        visit_counts = {}
        for _ in range(k):
            current_node = agent_id
            for step in range(walk_length):
                # Check restart
                if random.random() < restart_prob:
                    current_node = agent_id
                    continue

                # Get neighbors
                neighbors = follow_graph.get(current_node, [])
                if not neighbors:
                    current_node = agent_id
                    continue

                # Random step
                current_node = random.choice(neighbors)

                # Count visit
                if current_node != agent_id and current_node not in following_ids:
                    visit_counts[current_node] = visit_counts.get(current_node, 0) + 1

        if not visit_counts:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Sort by visit count (highest first)
        sorted_candidates = sorted(visit_counts.items(), key=lambda x: x[1], reverse=True)
        recommendations = [uid for uid, count in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(recommendations) < n_neighbors:
            remaining = n_neighbors - len(recommendations)
            user_ids_key = redis_key_func("user_mgmt", "ids")
            all_user_ids = list(redis_client.smembers(user_ids_key))
            candidates = [
                uid
                for uid in all_user_ids
                if uid != agent_id and uid not in following_ids and uid not in recommendations
            ]
            random.shuffle(candidates)
            recommendations.extend(candidates[:remaining])

        return recommendations[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_random_walk_with_restart_redis: {e}")
        return recommend_random_follows_redis(
            redis_client, redis_key_func, agent_id, n_neighbors, logger
        )


def recommend_reactions_on_content_redis(
    redis_client: Redis, redis_key_func, agent_id: str, n_neighbors: int, logger
) -> List[str]:
    """
    Reactions on agent content follow recommendation (Redis).

    Recommends users who have reacted to the agent's content.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent requesting recommendations
        n_neighbors: Number of recommendations to return
        logger: Logger instance

    Returns:
        List of recommended user IDs
    """
    try:
        # Get agent's posts
        post_pattern = redis_key_func("post", "*")
        post_keys = redis_client.keys(post_pattern)

        agent_post_ids = set()
        for key in post_keys:
            post_data = redis_client.hgetall(key)
            if post_data.get("user_id") == agent_id:
                agent_post_ids.add(post_data.get("id"))

        if not agent_post_ids:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Get following IDs
        follow_pattern = redis_key_func("follow", "*")
        follow_keys = redis_client.keys(follow_pattern)

        following_ids = set()
        for key in follow_keys:
            follow_data = redis_client.hgetall(key)
            if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                following_ids.add(follow_data.get("user_id"))

        # Find users who reacted to agent's posts
        reaction_pattern = redis_key_func("reactions", "*")
        reaction_keys = redis_client.keys(reaction_pattern)

        reaction_counts = {}
        for key in reaction_keys:
            reaction_data = redis_client.hgetall(key)
            post_id = reaction_data.get("post_id")
            user_id = reaction_data.get("user_id")

            if (
                post_id in agent_post_ids
                and user_id != agent_id
                and user_id not in following_ids
            ):
                reaction_counts[user_id] = reaction_counts.get(user_id, 0) + 1

        if not reaction_counts:
            return recommend_random_follows_redis(
                redis_client, redis_key_func, agent_id, n_neighbors, logger
            )

        # Sort by reaction count (highest first)
        sorted_candidates = sorted(reaction_counts.items(), key=lambda x: x[1], reverse=True)
        recommendations = [uid for uid, count in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(recommendations) < n_neighbors:
            remaining = n_neighbors - len(recommendations)
            user_ids_key = redis_key_func("user_mgmt", "ids")
            all_user_ids = list(redis_client.smembers(user_ids_key))
            candidates = [
                uid
                for uid in all_user_ids
                if uid != agent_id and uid not in following_ids and uid not in recommendations
            ]
            random.shuffle(candidates)
            recommendations.extend(candidates[:remaining])

        return recommendations[:n_neighbors]

    except Exception as e:
        logger.error(f"Error in recommend_reactions_on_content_redis: {e}")
        return recommend_random_follows_redis(
            redis_client, redis_key_func, agent_id, n_neighbors, logger
        )


def apply_leaning_bias_redis(
    redis_client: Redis,
    redis_key_func,
    agent_id: str,
    candidates: List[str],
    leaning_bias: int,
    logger,
) -> List[str]:
    """
    Apply political leaning bias to reorder candidates based on similarity.

    Args:
        redis_client: Redis client instance
        redis_key_func: Function to generate Redis keys
        agent_id: ID of the agent
        candidates: List of candidate user IDs
        leaning_bias: Weight for political leaning similarity (0-100)
        logger: Logger instance

    Returns:
        Reordered list of candidates with political leaning bias applied
    """
    if not candidates or leaning_bias == 0:
        return candidates

    try:
        # Get agent's political leaning
        agent_key = redis_key_func("user_mgmt", agent_id)
        agent_data = redis_client.hgetall(agent_key)

        if not agent_data or "political_leaning" not in agent_data:
            return candidates

        agent_leaning = int(agent_data["political_leaning"])

        # Calculate similarity scores for candidates
        leaning_scores = {}
        for candidate_id in candidates:
            candidate_key = redis_key_func("user_mgmt", candidate_id)
            candidate_data = redis_client.hgetall(candidate_key)

            if candidate_data and "political_leaning" in candidate_data:
                candidate_leaning = int(candidate_data["political_leaning"])
                # Calculate similarity (smaller difference = higher score)
                difference = abs(agent_leaning - candidate_leaning)
                # Normalize to 0-1 range (assuming leaning is 0-10)
                similarity = 1.0 - (difference / 10.0)
                leaning_scores[candidate_id] = similarity
            else:
                leaning_scores[candidate_id] = 0.5  # Neutral score if unknown

        # Weight by leaning_bias (0-100)
        weight = leaning_bias / 100.0

        # Combine original order with leaning scores
        # Higher weight = more influence from political leaning
        weighted_candidates = []
        for idx, candidate_id in enumerate(candidates):
            # Original score (higher for earlier candidates)
            original_score = (len(candidates) - idx) / len(candidates)
            # Combined score
            combined_score = (1 - weight) * original_score + weight * leaning_scores.get(
                candidate_id, 0.5
            )
            weighted_candidates.append((candidate_id, combined_score))

        # Sort by combined score (descending)
        weighted_candidates.sort(key=lambda x: x[1], reverse=True)

        return [uid for uid, _ in weighted_candidates]

    except Exception as e:
        logger.error(f"Error applying leaning bias: {e}")
        return candidates
