"""
SQL-based follow recommendation strategies.

This module contains isolated functions for each follow recommendation algorithm
using SQL database queries. Each function is independent and testable.
"""

import random
import math
from typing import List
from sqlalchemy import text
from sqlalchemy.orm import Session
from YSimulator.YServer.classes.User_mgmt import User_mgmt


def recommend_random_follows(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int
) -> List[str]:
    """
    Random follow recommendation strategy.
    
    Randomly selects users that the agent is not following.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs
    """
    try:
        # Get candidates excluding agent and already following
        candidates_query = session.query(User_mgmt).filter(
            User_mgmt.id != agent_id
        )
        
        if following_ids:
            candidates_query = candidates_query.filter(
                User_mgmt.id.notin_(following_ids)
            )
        
        candidates = candidates_query.all()
        candidate_ids = [c.id for c in candidates]
        random.shuffle(candidate_ids)
        return candidate_ids[:n_neighbors]
        
    except Exception as e:
        return []


def recommend_common_neighbors(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int
) -> List[str]:
    """
    Common neighbors follow recommendation strategy.
    
    Recommends users who share mutual friends (common neighbors) with the agent.
    Friend-of-friend approach.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs
    """
    try:
        if not following_ids:
            # No following, fallback to random
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)
        
        # Find users with common neighbors (friend-of-friend)
        fof_query = text("""
            SELECT f2.user_id, COUNT(*) as common_count
            FROM follow f1
            JOIN follow f2 ON f1.user_id = f2.follower_id
            WHERE f1.follower_id = :agent_id
              AND f1.action = 'follow'
              AND f2.action = 'follow'
              AND f2.user_id != :agent_id
              AND f2.user_id NOT IN :following_ids
            GROUP BY f2.user_id
            ORDER BY common_count DESC
            LIMIT :limit
        """)
        
        following_list = list(following_ids) if following_ids else [agent_id]
        result = session.execute(
            fof_query,
            {
                "agent_id": agent_id,
                "following_ids": tuple(following_list),
                "limit": n_neighbors
            }
        )
        suggestions = [row[0] for row in result]
        
        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(
                User_mgmt.id != agent_id
            )
            if following_ids:
                candidates_query = candidates_query.filter(
                    User_mgmt.id.notin_(following_ids)
                )
            extra_candidates = candidates_query.filter(
                User_mgmt.id.notin_(suggestions) if suggestions else True
            ).limit(remaining * 2).all()
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])
        
        return suggestions[:n_neighbors]
        
    except Exception as e:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_jaccard(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int
) -> List[str]:
    """
    Jaccard similarity follow recommendation strategy.
    
    Recommends users based on Jaccard similarity coefficient of their follower sets.
    Similarity = (intersection) / (union) of following sets.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs
    """
    try:
        if not following_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)
        
        # Calculate Jaccard similarity using SQL
        jaccard_query = text("""
            SELECT 
                candidate_id,
                CAST(common_count AS FLOAT) / NULLIF(union_count, 0) as jaccard_score
            FROM (
                SELECT 
                    f2.user_id as candidate_id,
                    COUNT(DISTINCT CASE WHEN f1.user_id = f2.follower_id THEN f1.user_id END) as common_count,
                    COUNT(DISTINCT f1.user_id) + COUNT(DISTINCT f3.user_id) as union_count
                FROM follow f1
                CROSS JOIN follow f2
                LEFT JOIN follow f3 ON f2.user_id = f3.follower_id AND f3.action = 'follow'
                WHERE f1.follower_id = :agent_id
                  AND f1.action = 'follow'
                  AND f2.action = 'follow'
                  AND f2.user_id != :agent_id
                  AND f2.user_id NOT IN :following_ids
                GROUP BY f2.user_id
            ) subq
            ORDER BY jaccard_score DESC
            LIMIT :limit
        """)
        
        following_list = list(following_ids) if following_ids else [agent_id]
        result = session.execute(
            jaccard_query,
            {
                "agent_id": agent_id,
                "following_ids": tuple(following_list),
                "limit": n_neighbors
            }
        )
        suggestions = [row[0] for row in result]
        
        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(
                User_mgmt.id != agent_id
            )
            if following_ids:
                candidates_query = candidates_query.filter(
                    User_mgmt.id.notin_(following_ids)
                )
            extra_candidates = candidates_query.filter(
                User_mgmt.id.notin_(suggestions) if suggestions else True
            ).limit(remaining * 2).all()
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])
        
        return suggestions[:n_neighbors]
        
    except Exception as e:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_adamic_adar(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int
) -> List[str]:
    """
    Adamic/Adar index follow recommendation strategy.
    
    Recommends users based on Adamic/Adar scores computed from common neighbors.
    Score for each common neighbor = 1/log(degree of common neighbor).
    Two-step approach: 1) Find common neighbors, 2) Calculate scores.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs
    """
    try:
        if not following_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)
        
        # Step 1: Get common neighbors (friend-of-friend) candidates
        common_neighbors_query = text("""
            SELECT f2.user_id, f2.follower_id as common_neighbor
            FROM follow f1
            JOIN follow f2 ON f1.user_id = f2.follower_id
            WHERE f1.follower_id = :agent_id
              AND f1.action = 'follow'
              AND f2.action = 'follow'
              AND f2.user_id != :agent_id
              AND f2.user_id NOT IN :following_ids
        """)
        
        following_list = list(following_ids) if following_ids else [agent_id]
        result = session.execute(
            common_neighbors_query,
            {
                "agent_id": agent_id,
                "following_ids": tuple(following_list)
            }
        )
        
        # Build mapping of candidate -> list of common neighbors
        candidate_common_neighbors = {}
        for row in result:
            candidate_id, common_neighbor = row
            if candidate_id not in candidate_common_neighbors:
                candidate_common_neighbors[candidate_id] = []
            candidate_common_neighbors[candidate_id].append(common_neighbor)
        
        if not candidate_common_neighbors:
            # No common neighbors found, fallback to random
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)
        
        # Step 2: Calculate Adamic/Adar score for each candidate
        # For each common neighbor, get their degree (out-degree = users they follow)
        common_neighbor_ids = set()
        for neighbors in candidate_common_neighbors.values():
            common_neighbor_ids.update(neighbors)
        
        # Query to get degree for each common neighbor
        degree_query = text("""
            SELECT follower_id, COUNT(*) as out_degree
            FROM follow
            WHERE follower_id IN :neighbor_ids
              AND action = 'follow'
            GROUP BY follower_id
        """)
        
        degree_result = session.execute(
            degree_query,
            {"neighbor_ids": tuple(common_neighbor_ids)}
        )
        
        # Build degree map
        neighbor_degrees = {row[0]: row[1] for row in degree_result}
        
        # Calculate Adamic/Adar score for each candidate
        adamic_adar_scores = {}
        for candidate_id, neighbors in candidate_common_neighbors.items():
            score = 0.0
            for neighbor in neighbors:
                degree = neighbor_degrees.get(neighbor, 1)  # Default to 1 to avoid division by zero
                if degree > 1:  # Only count if degree > 1 (log(1) = 0)
                    score += 1.0 / math.log(degree)
            adamic_adar_scores[candidate_id] = score
        
        # Sort by Adamic/Adar score (highest first)
        sorted_candidates = sorted(adamic_adar_scores.items(), key=lambda x: x[1], reverse=True)
        suggestions = [uid for uid, score in sorted_candidates[:n_neighbors]]
        
        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(
                User_mgmt.id != agent_id
            )
            if following_ids:
                candidates_query = candidates_query.filter(
                    User_mgmt.id.notin_(following_ids)
                )
            extra_candidates = candidates_query.filter(
                User_mgmt.id.notin_(suggestions) if suggestions else True
            ).limit(remaining * 2).all()
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])
        
        return suggestions[:n_neighbors]
        
    except Exception as e:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_preferential_attachment(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int
) -> List[str]:
    """
    Preferential attachment follow recommendation strategy.
    
    Recommends users based on popularity (number of followers).
    The rich get richer - prefer users with many followers.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs
    """
    try:
        # Prefer users with many followers (popularity-based)
        popular_users = text("""
            SELECT f.user_id, COUNT(*) as follower_count
            FROM follow f
            WHERE f.action = 'follow'
              AND f.user_id != :agent_id
              AND f.user_id NOT IN :following_ids
            GROUP BY f.user_id
            ORDER BY follower_count DESC
            LIMIT :limit
        """)
        
        following_list = list(following_ids) if following_ids else [agent_id]
        result = session.execute(
            popular_users,
            {
                "agent_id": agent_id,
                "following_ids": tuple(following_list),
                "limit": n_neighbors
            }
        )
        suggestions = [row[0] for row in result]
        
        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(
                User_mgmt.id != agent_id
            )
            if following_ids:
                candidates_query = candidates_query.filter(
                    User_mgmt.id.notin_(following_ids)
                )
            extra_candidates = candidates_query.filter(
                User_mgmt.id.notin_(suggestions) if suggestions else True
            ).limit(remaining * 2).all()
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])
        
        return suggestions[:n_neighbors]
        
    except Exception as e:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def apply_leaning_bias(
    session: Session,
    agent_id: str,
    suggestions: List[str],
    leaning_bias: int,
    n_neighbors: int
) -> List[str]:
    """
    Apply political leaning bias to recommendations for homophily.
    
    Weights recommendations toward users with similar political leaning.
    
    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        suggestions: List of recommended user IDs before bias
        leaning_bias: Bias multiplier for same-leaning users (1 = no bias)
        n_neighbors: Number of recommendations to return
        
    Returns:
        List of recommended user IDs after applying bias
    """
    try:
        if leaning_bias <= 1 or not suggestions:
            return suggestions[:n_neighbors]
        
        # Get agent leaning
        agent = session.query(User_mgmt).filter(User_mgmt.id == agent_id).first()
        if not agent or not agent.leaning:
            return suggestions[:n_neighbors]
        
        agent_leaning = agent.leaning
        
        # Get leaning info for suggestions
        user_leanings = session.query(User_mgmt.id, User_mgmt.leaning).filter(
            User_mgmt.id.in_(suggestions)
        ).all()
        leaning_map = {u.id: u.leaning for u in user_leanings}
        
        # Score candidates by leaning match
        leaning_scores = {}
        for candidate in suggestions:
            if leaning_map.get(candidate) == agent_leaning:
                leaning_scores[candidate] = leaning_bias
            else:
                leaning_scores[candidate] = 1
        
        # Weighted random selection
        weighted_suggestions = random.choices(
            list(leaning_scores.keys()),
            weights=list(leaning_scores.values()),
            k=min(n_neighbors, len(leaning_scores))
        )
        return weighted_suggestions
        
    except Exception as e:
        return suggestions[:n_neighbors]
