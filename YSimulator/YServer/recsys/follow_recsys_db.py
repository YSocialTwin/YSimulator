"""
SQL-based follow recommendation strategies.

This module contains isolated functions for each follow recommendation algorithm
using SQLAlchemy ORM for DBMS independence. Each function is independent and testable.
"""

import random
import math
from typing import List
from sqlalchemy import func, desc
from sqlalchemy.orm import Session, aliased
from YSimulator.YServer.classes.models import User_mgmt, Follow


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
        # f1: agent's follows, f2: friends of friends
        Follow1 = aliased(Follow)
        Follow2 = aliased(Follow)
        
        following_list = list(following_ids) if following_ids else [agent_id]
        
        fof_query = session.query(
            Follow2.user_id,
            func.count().label('common_count')
        ).select_from(Follow1).join(
            Follow2, Follow1.user_id == Follow2.follower_id
        ).filter(
            Follow1.follower_id == agent_id,
            Follow1.action == 'follow',
            Follow2.action == 'follow',
            Follow2.user_id != agent_id,
            Follow2.user_id.notin_(following_list)
        ).group_by(Follow2.user_id).order_by(desc('common_count')).limit(n_neighbors)
        
        suggestions = [row[0] for row in fof_query.all()]
        
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
        
        # Get friend-of-friend candidates with common neighbors count
        Follow1 = aliased(Follow)
        Follow2 = aliased(Follow)
        
        following_list = list(following_ids)
        
        # Get common neighbors count for each candidate
        common_query = session.query(
            Follow2.user_id.label('candidate_id'),
            func.count(func.distinct(Follow1.user_id)).label('common_count')
        ).select_from(Follow1).join(
            Follow2, Follow1.user_id == Follow2.follower_id
        ).filter(
            Follow1.follower_id == agent_id,
            Follow1.action == 'follow',
            Follow2.action == 'follow',
            Follow2.user_id != agent_id,
            Follow2.user_id.notin_(following_list)
        ).group_by(Follow2.user_id).subquery()
        
        # Get union count (agent's following count + candidate's following count - common)
        agent_following_count = len(following_ids)
        
        # For each candidate, get their following count
        Follow3 = aliased(Follow)
        union_query = session.query(
            common_query.c.candidate_id,
            common_query.c.common_count,
            func.count(Follow3.user_id).label('candidate_following_count')
        ).select_from(common_query).outerjoin(
            Follow3, 
            (common_query.c.candidate_id == Follow3.follower_id) & 
            (Follow3.action == 'follow')
        ).group_by(
            common_query.c.candidate_id,
            common_query.c.common_count
        ).subquery()
        
        # Calculate Jaccard score
        from sqlalchemy import Float
        jaccard_query = session.query(
            union_query.c.candidate_id,
            (func.cast(union_query.c.common_count, Float) / 
             func.nullif(
                 agent_following_count + union_query.c.candidate_following_count - union_query.c.common_count,
                 0
             )).label('jaccard_score')
        ).order_by(desc('jaccard_score')).limit(n_neighbors)
        
        suggestions = [row[0] for row in jaccard_query.all()]
        
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
        Follow1 = aliased(Follow)
        Follow2 = aliased(Follow)
        
        following_list = list(following_ids)
        
        common_neighbors_query = session.query(
            Follow2.user_id,
            Follow2.follower_id.label('common_neighbor')
        ).select_from(Follow1).join(
            Follow2, Follow1.user_id == Follow2.follower_id
        ).filter(
            Follow1.follower_id == agent_id,
            Follow1.action == 'follow',
            Follow2.action == 'follow',
            Follow2.user_id != agent_id,
            Follow2.user_id.notin_(following_list)
        )
        
        result = common_neighbors_query.all()
        
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
        degree_query = session.query(
            Follow.follower_id,
            func.count().label('out_degree')
        ).filter(
            Follow.follower_id.in_(common_neighbor_ids),
            Follow.action == 'follow'
        ).group_by(Follow.follower_id)
        
        # Build degree map
        neighbor_degrees = {row[0]: row[1] for row in degree_query.all()}
        
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
        following_list = list(following_ids) if following_ids else [agent_id]
        
        popular_users_query = session.query(
            Follow.user_id,
            func.count().label('follower_count')
        ).filter(
            Follow.action == 'follow',
            Follow.user_id != agent_id,
            Follow.user_id.notin_(following_list)
        ).group_by(Follow.user_id).order_by(desc('follower_count')).limit(n_neighbors)
        
        suggestions = [row[0] for row in popular_users_query.all()]
        
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
