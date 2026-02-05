"""
SQL-based follow recommendation strategies.

This module contains isolated functions for each follow recommendation algorithm
using SQLAlchemy ORM for DBMS independence. Each function is independent and testable.
"""

import math
import random
from typing import List

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, aliased

from YSimulator.YServer.classes.models import Follow, User_mgmt


def recommend_random_follows(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
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
        candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)

        if following_ids:
            candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))

        candidates = candidates_query.all()
        candidate_ids = [c.id for c in candidates]
        random.shuffle(candidate_ids)
        return candidate_ids[:n_neighbors]

    except Exception:
        return []


def recommend_common_neighbors(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
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

        fof_query = (
            session.query(Follow2.user_id, func.count().label("common_count"))
            .select_from(Follow1)
            .join(Follow2, Follow1.user_id == Follow2.follower_id)
            .filter(
                Follow1.follower_id == agent_id,
                Follow1.action == "follow",
                Follow2.action == "follow",
                Follow2.user_id != agent_id,
                Follow2.user_id.notin_(following_list),
            )
            .group_by(Follow2.user_id)
            .order_by(desc("common_count"))
            .limit(n_neighbors)
        )

        suggestions = [row[0] for row in fof_query.all()]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_jaccard(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
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
        common_query = (
            session.query(
                Follow2.user_id.label("candidate_id"),
                func.count(func.distinct(Follow1.user_id)).label("common_count"),
            )
            .select_from(Follow1)
            .join(Follow2, Follow1.user_id == Follow2.follower_id)
            .filter(
                Follow1.follower_id == agent_id,
                Follow1.action == "follow",
                Follow2.action == "follow",
                Follow2.user_id != agent_id,
                Follow2.user_id.notin_(following_list),
            )
            .group_by(Follow2.user_id)
            .subquery()
        )

        # Get union count (agent's following count + candidate's following count - common)
        agent_following_count = len(following_ids)

        # For each candidate, get their following count
        Follow3 = aliased(Follow)
        union_query = (
            session.query(
                common_query.c.candidate_id,
                common_query.c.common_count,
                func.count(Follow3.user_id).label("candidate_following_count"),
            )
            .select_from(common_query)
            .outerjoin(
                Follow3,
                (common_query.c.candidate_id == Follow3.follower_id) & (Follow3.action == "follow"),
            )
            .group_by(common_query.c.candidate_id, common_query.c.common_count)
            .subquery()
        )

        # Calculate Jaccard score
        from sqlalchemy import Float

        jaccard_query = (
            session.query(
                union_query.c.candidate_id,
                (
                    func.cast(union_query.c.common_count, Float)
                    / func.nullif(
                        agent_following_count
                        + union_query.c.candidate_following_count
                        - union_query.c.common_count,
                        0,
                    )
                ).label("jaccard_score"),
            )
            .order_by(desc("jaccard_score"))
            .limit(n_neighbors)
        )

        suggestions = [row[0] for row in jaccard_query.all()]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_adamic_adar(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
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

        common_neighbors_query = (
            session.query(Follow2.user_id, Follow2.follower_id.label("common_neighbor"))
            .select_from(Follow1)
            .join(Follow2, Follow1.user_id == Follow2.follower_id)
            .filter(
                Follow1.follower_id == agent_id,
                Follow1.action == "follow",
                Follow2.action == "follow",
                Follow2.user_id != agent_id,
                Follow2.user_id.notin_(following_list),
            )
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
        degree_query = (
            session.query(Follow.follower_id, func.count().label("out_degree"))
            .filter(Follow.follower_id.in_(common_neighbor_ids), Follow.action == "follow")
            .group_by(Follow.follower_id)
        )

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
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_preferential_attachment(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
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

        popular_users_query = (
            session.query(Follow.user_id, func.count().label("follower_count"))
            .filter(
                Follow.action == "follow",
                Follow.user_id != agent_id,
                Follow.user_id.notin_(following_list),
            )
            .group_by(Follow.user_id)
            .order_by(desc("follower_count"))
            .limit(n_neighbors)
        )

        suggestions = [row[0] for row in popular_users_query.all()]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_resource_allocation(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
) -> List[str]:
    """
    Resource Allocation index follow recommendation strategy.

    Similar to Adamic/Adar but uses 1/degree instead of 1/log(degree).
    Each common neighbor contributes inversely proportional to their degree.

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

        common_neighbors_query = (
            session.query(Follow2.user_id, Follow2.follower_id.label("common_neighbor"))
            .select_from(Follow1)
            .join(Follow2, Follow1.user_id == Follow2.follower_id)
            .filter(
                Follow1.follower_id == agent_id,
                Follow1.action == "follow",
                Follow2.action == "follow",
                Follow2.user_id != agent_id,
                Follow2.user_id.notin_(following_list),
            )
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
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Step 2: Calculate Resource Allocation score
        common_neighbor_ids = set()
        for neighbors in candidate_common_neighbors.values():
            common_neighbor_ids.update(neighbors)

        # Query to get degree for each common neighbor
        degree_query = (
            session.query(Follow.follower_id, func.count().label("out_degree"))
            .filter(Follow.follower_id.in_(common_neighbor_ids), Follow.action == "follow")
            .group_by(Follow.follower_id)
        )

        # Build degree map
        neighbor_degrees = {row[0]: row[1] for row in degree_query.all()}

        # Calculate Resource Allocation score (1/degree instead of 1/log(degree))
        ra_scores = {}
        for candidate_id, neighbors in candidate_common_neighbors.items():
            score = 0.0
            for neighbor in neighbors:
                degree = neighbor_degrees.get(neighbor, 1)
                score += 1.0 / max(degree, 1)  # Avoid division by zero
            ra_scores[candidate_id] = score

        # Sort by Resource Allocation score (highest first)
        sorted_candidates = sorted(ra_scores.items(), key=lambda x: x[1], reverse=True)
        suggestions = [uid for uid, score in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_cosine_similarity(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int, sample_size: int = 100
) -> List[str]:
    """
    Cosine similarity on agents' profile vectors.

    Recommends users with similar profiles based on interests and personality traits.
    Uses a random sample for efficiency in large networks.

    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        sample_size: Number of candidates to sample for comparison

    Returns:
        List of recommended user IDs
    """
    try:
        from YSimulator.YServer.classes.models import UserInterest

        # Get agent's profile vector (interests + personality traits)
        agent = session.query(User_mgmt).filter(User_mgmt.id == agent_id).first()
        if not agent:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Build agent's profile vector
        agent_interests = (
            session.query(UserInterest.interest_id)
            .filter(UserInterest.user_id == agent_id)
            .all()
        )
        agent_interest_ids = set([i.interest_id for i in agent_interests])

        # Agent personality traits (Big Five)
        agent_traits = {
            "openness": agent.openness or 0.0,
            "conscientiousness": agent.conscientiousness or 0.0,
            "extraversion": agent.extraversion or 0.0,
            "agreeableness": agent.agreeableness or 0.0,
            "neuroticism": agent.neuroticism or 0.0,
        }

        # Get candidates (exclude self and already following)
        following_list = list(following_ids) if following_ids else [agent_id]
        candidates_query = (
            session.query(User_mgmt)
            .filter(User_mgmt.id != agent_id, User_mgmt.id.notin_(following_list))
            .limit(sample_size * 2)
        )

        candidates = candidates_query.all()
        if not candidates:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Randomly sample candidates for efficiency
        if len(candidates) > sample_size:
            candidates = random.sample(candidates, sample_size)

        # Calculate cosine similarity for each candidate
        similarities = {}
        for candidate in candidates:
            # Get candidate's interests
            candidate_interests = (
                session.query(UserInterest.interest_id)
                .filter(UserInterest.user_id == candidate.id)
                .all()
            )
            candidate_interest_ids = set([i.interest_id for i in candidate_interests])

            # Calculate interest similarity (Jaccard coefficient)
            if agent_interest_ids or candidate_interest_ids:
                interest_intersection = len(agent_interest_ids & candidate_interest_ids)
                interest_union = len(agent_interest_ids | candidate_interest_ids)
                interest_similarity = (
                    interest_intersection / interest_union if interest_union > 0 else 0.0
                )
            else:
                interest_similarity = 0.0

            # Calculate personality trait similarity (cosine similarity)
            candidate_traits = {
                "openness": candidate.openness or 0.0,
                "conscientiousness": candidate.conscientiousness or 0.0,
                "extraversion": candidate.extraversion or 0.0,
                "agreeableness": candidate.agreeableness or 0.0,
                "neuroticism": candidate.neuroticism or 0.0,
            }

            # Cosine similarity for personality traits
            dot_product = sum(agent_traits[k] * candidate_traits[k] for k in agent_traits)
            agent_norm = math.sqrt(sum(v**2 for v in agent_traits.values()))
            candidate_norm = math.sqrt(sum(v**2 for v in candidate_traits.values()))

            if agent_norm > 0 and candidate_norm > 0:
                trait_similarity = dot_product / (agent_norm * candidate_norm)
            else:
                trait_similarity = 0.0

            # Combined similarity (weighted average)
            # Weight interests more heavily (0.7) than personality traits (0.3)
            combined_similarity = 0.7 * interest_similarity + 0.3 * trait_similarity
            similarities[candidate.id] = combined_similarity

        # Sort by similarity (highest first)
        sorted_candidates = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        suggestions = [uid for uid, score in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            extra_candidates = (
                session.query(User_mgmt)
                .filter(
                    User_mgmt.id != agent_id,
                    User_mgmt.id.notin_(following_list),
                    User_mgmt.id.notin_(suggestions) if suggestions else True,
                )
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_co_engagement(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
) -> List[str]:
    """
    Co-engagement follow recommendation strategy.

    Recommends users who interact with the same content (posts) as the agent.
    Users who like/comment on similar posts are recommended.

    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return

    Returns:
        List of recommended user IDs
    """
    try:
        from YSimulator.YServer.classes.models import Post, Reaction

        # Get posts that the agent has reacted to
        agent_reactions = (
            session.query(Reaction.post_id)
            .filter(Reaction.user_id == agent_id)
            .distinct()
            .all()
        )
        agent_post_ids = [r.post_id for r in agent_reactions]

        # Get agent's posts (to find who reacted to them)
        agent_posts = session.query(Post.id).filter(Post.user_id == agent_id).all()
        agent_post_ids.extend([p.id for p in agent_posts])

        if not agent_post_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        following_list = list(following_ids) if following_ids else [agent_id]

        # Find users who also reacted to the same posts
        co_engaged_users = (
            session.query(Reaction.user_id, func.count(Reaction.post_id).label("engagement_count"))
            .filter(
                Reaction.post_id.in_(agent_post_ids),
                Reaction.user_id != agent_id,
                Reaction.user_id.notin_(following_list),
            )
            .group_by(Reaction.user_id)
            .order_by(desc("engagement_count"))
            .limit(n_neighbors)
        )

        suggestions = [row[0] for row in co_engaged_users.all()]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_random_walk_with_restart(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int,
    k: int = 10,
    walk_length: int = 3,
    restart_prob: float = 0.15,
) -> List[str]:
    """
    Random Walk with Restart follow recommendation strategy.

    Performs k random walks of specified length rooted in the agent,
    with a probability of restarting at each step.

    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        k: Number of random walks to perform
        walk_length: Maximum length of each random walk
        restart_prob: Probability of restarting at the root node

    Returns:
        List of recommended user IDs
    """
    try:
        if not following_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Count visits to each node during random walks
        visit_counts = {}
        following_list = list(following_ids)

        # Perform k random walks
        for _ in range(k):
            current_node = agent_id
            for step in range(walk_length):
                # Check if we should restart
                if random.random() < restart_prob:
                    current_node = agent_id
                    continue

                # Get neighbors of current node (users they follow)
                neighbors = (
                    session.query(Follow.user_id)
                    .filter(Follow.follower_id == current_node, Follow.action == "follow")
                    .all()
                )

                if not neighbors:
                    # Dead end, restart
                    current_node = agent_id
                    continue

                # Randomly select next node
                neighbor_ids = [n.user_id for n in neighbors]
                current_node = random.choice(neighbor_ids)

                # Count visit (exclude self and already following)
                if (
                    current_node != agent_id
                    and current_node not in following_ids
                ):
                    visit_counts[current_node] = visit_counts.get(current_node, 0) + 1

        if not visit_counts:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Sort by visit count (most visited first)
        sorted_candidates = sorted(visit_counts.items(), key=lambda x: x[1], reverse=True)
        suggestions = [uid for uid, count in sorted_candidates[:n_neighbors]]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_reactions_on_content(
    session: Session, agent_id: str, following_ids: set, n_neighbors: int
) -> List[str]:
    """
    Reactions on agent content follow recommendation strategy.

    Recommends users who have reacted to the agent's content.
    The more reactions/interactions a user has with agent's posts, the higher they rank.

    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return

    Returns:
        List of recommended user IDs
    """
    try:
        from YSimulator.YServer.classes.models import Post, Reaction

        # Get agent's posts
        agent_posts = session.query(Post.id).filter(Post.user_id == agent_id).all()
        agent_post_ids = [p.id for p in agent_posts]

        if not agent_post_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        following_list = list(following_ids) if following_ids else [agent_id]

        # Find users who reacted to agent's posts
        reactors = (
            session.query(Reaction.user_id, func.count(Reaction.id).label("reaction_count"))
            .filter(
                Reaction.post_id.in_(agent_post_ids),
                Reaction.user_id != agent_id,
                Reaction.user_id.notin_(following_list),
            )
            .group_by(Reaction.user_id)
            .order_by(desc("reaction_count"))
            .limit(n_neighbors)
        )

        suggestions = [row[0] for row in reactors.all()]

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def recommend_two_hop_ego_sampling(
    session: Session,
    agent_id: str,
    following_ids: set,
    n_neighbors: int,
    k_one_hop: int = 20,
    k_two_hop: int = 50,
    recent_posts_window: int = 10,
    weight_posts: float = 0.3,
    weight_interactions: float = 0.4,
    weight_triangles: float = 0.3,
) -> List[str]:
    """
    2-hop ego sampling follow recommendation strategy.

    Samples 1-hop and 2-hop neighbors, then scores 2-hop neighbors based on:
    - Number of recent posts
    - Number of interactions with 1-hop neighbors
    - Number of triangles closed if edge is established

    Args:
        session: SQLAlchemy database session
        agent_id: ID of the agent requesting recommendations
        following_ids: Set of user IDs the agent is already following
        n_neighbors: Number of recommendations to return
        k_one_hop: Maximum number of 1-hop neighbors to sample
        k_two_hop: Maximum number of 2-hop neighbors to sample per 1-hop neighbor
        recent_posts_window: Number of recent rounds to consider for post counting
        weight_posts: Weight for recent posts score component
        weight_interactions: Weight for interactions score component
        weight_triangles: Weight for triangle closure score component

    Returns:
        List of recommended user IDs
    """
    try:
        from YSimulator.YServer.classes.models import Post, Reaction, Round

        if not following_ids:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        following_list = list(following_ids)

        # Step 1: Sample up to k_one_hop 1-hop neighbors
        if len(following_list) > k_one_hop:
            sampled_one_hop = random.sample(following_list, k_one_hop)
        else:
            sampled_one_hop = following_list

        # Step 2: Get 2-hop neighbors (users that 1-hop neighbors follow)
        # Exclude agent and users already following
        Follow1 = aliased(Follow)
        two_hop_candidates = {}  # Map 2-hop user -> list of 1-hop neighbors connecting them

        for one_hop_user in sampled_one_hop:
            # Get users that this 1-hop neighbor follows
            two_hop_query = (
                session.query(Follow1.user_id)
                .filter(
                    Follow1.follower_id == one_hop_user,
                    Follow1.action == "follow",
                    Follow1.user_id != agent_id,
                    Follow1.user_id.notin_(following_list),
                )
                .limit(k_two_hop)
            )

            for row in two_hop_query.all():
                two_hop_user = row[0]
                if two_hop_user not in two_hop_candidates:
                    two_hop_candidates[two_hop_user] = []
                two_hop_candidates[two_hop_user].append(one_hop_user)

        if not two_hop_candidates:
            return recommend_random_follows(session, agent_id, following_ids, n_neighbors)

        # Step 3: Score each 2-hop candidate
        candidate_scores = {}

        # Get recent round IDs for post counting
        recent_rounds = (
            session.query(Round.id)
            .order_by(desc(Round.day), desc(Round.hour))
            .limit(recent_posts_window)
            .all()
        )
        recent_round_ids = [r.id for r in recent_rounds]

        for candidate_id, connecting_neighbors in two_hop_candidates.items():
            # Component 1: Number of recent posts
            if recent_round_ids:
                post_count = (
                    session.query(func.count(Post.id))
                    .filter(Post.user_id == candidate_id, Post.round.in_(recent_round_ids))
                    .scalar()
                    or 0
                )
            else:
                post_count = 0

            # Component 2: Number of interactions with 1-hop neighbors
            # Count reactions by candidate on posts by 1-hop neighbors
            interaction_count = (
                session.query(func.count(Reaction.id))
                .join(Post, Reaction.post_id == Post.id)
                .filter(
                    Reaction.user_id == candidate_id, Post.user_id.in_(sampled_one_hop)
                )
                .scalar()
                or 0
            )

            # Component 3: Number of triangles closed
            # A triangle is closed if candidate follows any of the 1-hop neighbors
            # (who already follow the candidate or are followed by agent)
            triangle_count = len(connecting_neighbors)

            # Normalize scores (simple min-max style normalization across candidates)
            candidate_scores[candidate_id] = {
                "posts": post_count,
                "interactions": interaction_count,
                "triangles": triangle_count,
            }

        # Normalize each component
        if candidate_scores:
            max_posts = max((s["posts"] for s in candidate_scores.values()), default=1)
            max_interactions = max(
                (s["interactions"] for s in candidate_scores.values()), default=1
            )
            max_triangles = max(
                (s["triangles"] for s in candidate_scores.values()), default=1
            )

            # Avoid division by zero
            max_posts = max(max_posts, 1)
            max_interactions = max(max_interactions, 1)
            max_triangles = max(max_triangles, 1)

            final_scores = {}
            for candidate_id, scores in candidate_scores.items():
                normalized_posts = scores["posts"] / max_posts
                normalized_interactions = scores["interactions"] / max_interactions
                normalized_triangles = scores["triangles"] / max_triangles

                # Linear combination
                final_score = (
                    weight_posts * normalized_posts
                    + weight_interactions * normalized_interactions
                    + weight_triangles * normalized_triangles
                )
                final_scores[candidate_id] = final_score

            # Sort by score (highest first)
            sorted_candidates = sorted(
                final_scores.items(), key=lambda x: x[1], reverse=True
            )
            suggestions = [uid for uid, score in sorted_candidates[:n_neighbors]]
        else:
            suggestions = []

        # Fill with random if needed
        if len(suggestions) < n_neighbors:
            remaining = n_neighbors - len(suggestions)
            candidates_query = session.query(User_mgmt).filter(User_mgmt.id != agent_id)
            if following_ids:
                candidates_query = candidates_query.filter(User_mgmt.id.notin_(following_ids))
            extra_candidates = (
                candidates_query.filter(User_mgmt.id.notin_(suggestions) if suggestions else True)
                .limit(remaining * 2)
                .all()
            )
            extra_ids = [c.id for c in extra_candidates]
            random.shuffle(extra_ids)
            suggestions.extend(extra_ids[:remaining])

        return suggestions[:n_neighbors]

    except Exception:
        return recommend_random_follows(session, agent_id, following_ids, n_neighbors)


def apply_leaning_bias(
    session: Session, agent_id: str, suggestions: List[str], leaning_bias: int, n_neighbors: int
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
        user_leanings = (
            session.query(User_mgmt.id, User_mgmt.leaning)
            .filter(User_mgmt.id.in_(suggestions))
            .all()
        )
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
            k=min(n_neighbors, len(leaning_scores)),
        )
        return weighted_suggestions

    except Exception:
        return suggestions[:n_neighbors]
