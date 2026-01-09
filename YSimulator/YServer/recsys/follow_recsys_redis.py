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
