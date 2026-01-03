"""
SQLAlchemy-based repository implementations.

This module provides concrete implementations of repository interfaces
using SQLAlchemy for SQL database operations.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import (
    Agent_Opinion,
    Follow,
    Interest,
    Post,
    PostTopic,
    Reaction,
    Round,
    User_mgmt,
    UserInterest,
)
from .base_repository import (
    ArticleRepository,
    FollowRepository,
    ImageRepository,
    InterestRepository,
    PostRepository,
    RecommendationRepository,
    UserRepository,
)


class SQLUserRepository(UserRepository):
    """SQLAlchemy implementation of UserRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL user repository."""
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            session = Session(self.engine)
            try:
                session.execute("SELECT 1")
                return True
            finally:
                session.close()
        except Exception:
            return False
    
    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """Register a single user."""
        try:
            session = Session(self.engine)
            try:
                existing = session.query(User_mgmt).filter_by(id=user_data["id"]).first()
                if existing:
                    return False
                
                user = User_mgmt(**user_data)
                session.add(user)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error registering user: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def register_users_batch(self, users_data: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
        """Register multiple users in a batch."""
        if not users_data:
            return (0, set())
        
        try:
            session = Session(self.engine)
            try:
                # Get existing user IDs to avoid duplicates
                existing_ids = {
                    row[0]
                    for row in session.query(User_mgmt.id)
                    .filter(User_mgmt.id.in_([u["id"] for u in users_data]))
                    .all()
                }
                
                # Filter out users that already exist
                new_users = [u for u in users_data if u["id"] not in existing_ids]
                
                if not new_users:
                    return (0, set())
                
                # Bulk insert new users
                session.bulk_insert_mappings(User_mgmt, new_users)
                session.commit()
                
                # Return count and set of newly registered IDs
                newly_registered_ids = {u["id"] for u in new_users}
                return (len(new_users), newly_registered_ids)
            except Exception as e:
                session.rollback()
                self.logger.error(
                    f"Error in batch user registration: {e}",
                    extra={"extra_data": {"error": str(e), "batch_size": len(users_data)}},
                )
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error registering users in batch: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(users_data)}},
            )
            return (0, set())
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        try:
            session = Session(self.engine)
            try:
                user = session.query(User_mgmt).filter_by(id=user_id).first()
                if not user:
                    return None
                
                return {
                    "id": user.id,
                    "username": user.username,
                    "leaning": user.leaning,
                    "archetype": user.archetype,
                    "is_llm": user.is_llm,
                    "model_name": user.model_name,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting user: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        try:
            session = Session(self.engine)
            try:
                users = session.query(User_mgmt).all()
                return [
                    {
                        "id": user.id,
                        "username": user.username,
                        "leaning": user.leaning,
                        "archetype": user.archetype,
                        "is_llm": user.is_llm,
                        "model_name": user.model_name,
                    }
                    for user in users
                ]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting all users: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """Update user's archetype."""
        try:
            session = Session(self.engine)
            try:
                user = session.query(User_mgmt).filter_by(id=user_id).first()
                if not user:
                    return False
                
                user.archetype = new_archetype
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error updating user archetype: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False


class SQLPostRepository(PostRepository):
    """SQLAlchemy implementation of PostRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL post repository."""
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            session = Session(self.engine)
            try:
                session.execute("SELECT 1")
                return True
            finally:
                session.close()
        except Exception:
            return False
    
    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """Add a new post."""
        try:
            session = Session(self.engine)
            try:
                # Map common field names to actual model field names
                mapped_data = {
                    "id": post_data.get("id"),
                    "tweet": post_data.get("text") or post_data.get("tweet"),
                    "user_id": post_data.get("author") or post_data.get("user_id"),
                    "round": post_data.get("round"),
                    "comment_to": post_data.get("parent_post") or post_data.get("comment_to", -1),
                    "thread_id": post_data.get("root_post") or post_data.get("thread_id"),
                    "reaction_count": post_data.get("num_reactions") or post_data.get("reaction_count", 0),
                }
                # Filter out None values
                mapped_data = {k: v for k, v in mapped_data.items() if v is not None}
                
                post = Post(**mapped_data)
                session.add(post)
                session.commit()
                return post.id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post by ID."""
        try:
            session = Session(self.engine)
            try:
                post = session.query(Post).filter_by(id=post_id).first()
                if not post:
                    return None
                
                return {
                    "id": post.id,
                    "author": post.user_id,  # Map user_id to author
                    "text": post.tweet,  # Map tweet to text
                    "round": post.round,
                    "parent_post": post.comment_to,  # Map comment_to to parent_post
                    "root_post": post.thread_id,  # Map thread_id to root_post
                    "num_reactions": post.reaction_count,  # Map reaction_count to num_reactions
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """Get recent post IDs."""
        try:
            session = Session(self.engine)
            try:
                posts = (
                    session.query(Post.id)
                    .order_by(Post.round.desc())
                    .limit(limit)
                    .all()
                )
                return [post[0] for post in posts]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting recent posts: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def get_thread_context(self, post_id: str, max_length: int = 5) -> List[Dict[str, Any]]:
        """Get thread context for a post."""
        # Constant for "no parent" value used in the database
        NO_PARENT_MARKERS = (-1, "-1", None)
        
        try:
            session = Session(self.engine)
            try:
                thread = []
                current_id = post_id
                
                for _ in range(max_length):
                    post = session.query(Post).filter_by(id=current_id).first()
                    if not post:
                        break
                    
                    thread.append({
                        "id": post.id,
                        "author": post.user_id,  # Map user_id to author
                        "text": post.tweet,  # Map tweet to text
                        "parent_post": post.comment_to,  # Map comment_to to parent_post
                    })
                    
                    # Check if this is a root post (no parent)
                    if post.comment_to in NO_PARENT_MARKERS:
                        break
                    
                    current_id = post.comment_to
                
                return list(reversed(thread))
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting thread context: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """Add a reaction/interaction to a post."""
        try:
            session = Session(self.engine)
            try:
                reaction = Reaction(**interaction_data)
                session.add(reaction)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding interaction: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def increment_post_reaction_count(self, post_id: str) -> bool:
        """Increment the reaction count for a post."""
        try:
            session = Session(self.engine)
            try:
                post = session.query(Post).filter_by(id=post_id).first()
                if not post:
                    return False
                
                if post.reaction_count is None:  # Model uses reaction_count
                    post.reaction_count = 1
                else:
                    post.reaction_count += 1
                
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error incrementing post reaction count: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False
    
    def add_post_topic(self, post_id: str, topic_id: str) -> bool:
        """Associate a topic with a post."""
        try:
            session = Session(self.engine)
            try:
                post_topic = PostTopic(post_id=post_id, topic_id=topic_id)
                session.add(post_topic)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post topic: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_post_topics(self, post_id: str) -> List[str]:
        """Get all topics associated with a post."""
        try:
            session = Session(self.engine)
            try:
                topics = (
                    session.query(PostTopic.topic_id)
                    .filter_by(post_id=post_id)
                    .all()
                )
                return [topic[0] for topic in topics]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post topics: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
        """Search posts by topic."""
        try:
            session = Session(self.engine)
            try:
                posts = (
                    session.query(Post.id)
                    .join(PostTopic, Post.id == PostTopic.post_id)
                    .filter(PostTopic.topic_id == topic_id)
                    .filter(Post.user_id != agent_id)  # Model uses user_id not author
                    .order_by(Post.round.desc())
                    .limit(limit)
                    .all()
                )
                return [post[0] for post in posts]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error searching posts by topic: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []


class SQLFollowRepository(FollowRepository):
    """SQLAlchemy implementation of FollowRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL follow repository."""
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            session = Session(self.engine)
            try:
                session.execute("SELECT 1")
                return True
            finally:
                session.close()
        except Exception:
            return False
    
    def add_follow(self, follow_data: Dict[str, Any]) -> bool:
        """Add a follow relationship."""
        try:
            session = Session(self.engine)
            try:
                # Map field names - Follow model uses user_id and follower_id
                # where user_id is the one being followed (followee)
                import uuid
                mapped_data = {
                    "id": follow_data.get("id", str(uuid.uuid4())),
                    "user_id": follow_data.get("followee_id") or follow_data.get("user_id"),
                    "follower_id": follow_data.get("follower_id"),
                    "action": follow_data.get("action"),
                    "round": follow_data.get("round"),
                }
                # Filter out None values
                mapped_data = {k: v for k, v in mapped_data.items() if v is not None}
                
                follow = Follow(**mapped_data)
                session.add(follow)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding follow: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """Add multiple follow relationships in a batch."""
        if not follows_data:
            return 0
        
        try:
            session = Session(self.engine)
            try:
                session.bulk_insert_mappings(Follow, follows_data)
                session.commit()
                return len(follows_data)
            except Exception as e:
                session.rollback()
                self.logger.error(
                    f"Error in batch follow insertion: {e}",
                    extra={"extra_data": {"error": str(e), "batch_size": len(follows_data)}},
                )
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding follows in batch: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(follows_data)}},
            )
            return 0


class SQLInterestRepository(InterestRepository):
    """SQLAlchemy implementation of InterestRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL interest repository."""
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            session = Session(self.engine)
            try:
                session.execute("SELECT 1")
                return True
            finally:
                session.close()
        except Exception:
            return False
    
    def get_interest_by_id(self, interest_id: str) -> Optional[Dict[str, Any]]:
        """Get interest by ID."""
        try:
            session = Session(self.engine)
            try:
                interest = session.query(Interest).filter_by(iid=interest_id).first()
                if not interest:
                    return None
                
                return {
                    "iid": interest.iid,
                    "interest": interest.interest,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting interest: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def add_or_get_interest(self, interest_name: str) -> Optional[str]:
        """Add a new interest or get existing one's ID."""
        try:
            session = Session(self.engine)
            try:
                # Check if interest exists
                existing = session.query(Interest).filter_by(interest=interest_name).first()
                if existing:
                    return existing.iid
                
                # Create new interest
                import uuid
                interest_id = str(uuid.uuid4())
                interest = Interest(iid=interest_id, interest=interest_name)
                session.add(interest)
                session.commit()
                return interest_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding or getting interest: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
        """Get topic ID by name."""
        try:
            session = Session(self.engine)
            try:
                interest = session.query(Interest).filter_by(interest=topic_name).first()
                if not interest:
                    return None
                return interest.iid
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting topic ID: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_topic_name_from_id(self, topic_id: str) -> Optional[str]:
        """Get topic name from ID."""
        try:
            session = Session(self.engine)
            try:
                interest = session.query(Interest).filter_by(iid=topic_id).first()
                if not interest:
                    return None
                return interest.interest
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting topic name: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add a user interest."""
        try:
            session = Session(self.engine)
            try:
                user_interest = UserInterest(
                    user_id=user_id,
                    interest_id=interest_id,
                    round_id=round_id
                )
                session.add(user_interest)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding user interest: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def add_agent_opinion(
        self, agent_id: str, topic_id: str, opinion: float, round_id: str
    ) -> bool:
        """Add an agent opinion on a topic."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                # Agent_Opinion model uses 'tid' for round_id
                agent_opinion = Agent_Opinion(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    topic_id=topic_id,
                    opinion=opinion,
                    tid=round_id  # Note: model uses 'tid' not 'round_id'
                )
                session.add(agent_opinion)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding agent opinion: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion on a topic."""
        try:
            session = Session(self.engine)
            try:
                opinion = (
                    session.query(Agent_Opinion)
                    .filter_by(agent_id=agent_id, topic_id=topic_id)
                    .order_by(Agent_Opinion.tid.desc())  # Note: model uses 'tid' not 'round_id'
                    .first()
                )
                if not opinion:
                    return None
                return opinion.opinion
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting latest agent opinion: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None
    
    def get_user_interests_in_window(
        self, user_id: str, start_round: int, end_round: int
    ) -> List[str]:
        """Get user interests within a time window."""
        try:
            session = Session(self.engine)
            try:
                interests = (
                    session.query(UserInterest.interest_id)
                    .filter(UserInterest.user_id == user_id)
                    .filter(UserInterest.round_id >= start_round)
                    .filter(UserInterest.round_id <= end_round)
                    .all()
                )
                return [interest[0] for interest in interests]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting user interests in window: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []


class SQLRecommendationRepository(RecommendationRepository):
    """SQLAlchemy implementation of RecommendationRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL recommendation repository."""
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            session = Session(self.engine)
            try:
                session.execute("SELECT 1")
                return True
            finally:
                session.close()
        except Exception:
            return False
    
    def get_or_create_round(self, day: int, hour: int) -> str:
        """
        Get or create a round ID.
        
        Args:
            day: Day number
            hour: Hour/slot number
            
        Returns:
            Round ID (UUID string)
            
        Raises:
            RuntimeError: If unable to create or retrieve round
        """
        try:
            session = Session(self.engine)
            try:
                # Check if round exists
                existing = session.query(Round).filter_by(day=day, hour=hour).first()
                if existing:
                    return existing.id
                
                # Create new round
                import uuid
                round_id = str(uuid.uuid4())
                round_obj = Round(id=round_id, day=day, hour=hour)
                session.add(round_obj)
                session.commit()
                return round_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting or creating round: {e}", extra={"extra_data": {"error": str(e)}}
            )
            raise RuntimeError(f"Failed to get or create round for day={day}, hour={hour}: {e}")
    
    def cleanup_old_posts_from_redis(self, current_day: int, current_slot: int) -> Dict[str, int]:
        """Cleanup old posts (not applicable for SQL)."""
        return {"status": "not_applicable", "method": "sql"}
    
    def consolidate_redis_to_sqlite(self, day: int) -> Dict[str, Any]:
        """Consolidate Redis data to SQLite (not applicable for SQL)."""
        return {"status": "not_applicable", "method": "sql"}
