"""
SQLAlchemy-based repository implementations.

This module provides concrete implementations of repository interfaces
using SQLAlchemy for SQL database operations.

IMPORTANT: Session Management Pattern
All write methods MUST follow this pattern to ensure proper transaction handling:

    session = Session(self.engine)
    try:
        # Database operations
        session.add(obj) or session.commit()
    except Exception as e:
        session.rollback()  # Critical! Prevents stuck sessions
        self.logger.error(...)
        return failure_value
    finally:
        session.close()

WITHOUT rollback(), sessions remain in inconsistent state and all subsequent
writes will fail. This was the root cause of widespread database write failures.

Methods register_user(), update_user_archetype(), and add_post() have been
fixed as examples. Other write methods still need this fix applied.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import (
    Agent_Opinion,
    Article,
    ArticleTopic,
    Emotion,
    Follow,
    Hashtag,
    Image,
    Interest,
    Post,
    PostEmotion,
    PostHashtag,
    PostSentiment,
    PostTopic,
    PostToxicity,
    Reaction,
    Round,
    User_mgmt,
    UserInterest,
    Website,
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
        session = Session(self.engine)
        try:
            existing = session.query(User_mgmt).filter_by(id=user_data["id"]).first()
            if existing:
                return False
            
            user = User_mgmt(**user_data)
            session.add(user)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error registering user: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
        finally:
            session.close()
    
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
        session = Session(self.engine)
        try:
            user = session.query(User_mgmt).filter_by(id=user_id).first()
            if not user:
                return False
            
            user.archetype = new_archetype
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error updating user archetype: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
        finally:
            session.close()
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        try:
            session = Session(self.engine)
            try:
                user = session.query(User_mgmt).filter_by(username=username).first()
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
                f"Error getting user by username: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def update_agent_last_active_day(self, agent_id: str, day: int) -> bool:
        """Update agent's last active day."""
        try:
            session = Session(self.engine)
            try:
                user = session.query(User_mgmt).filter_by(id=agent_id).first()
                if not user:
                    return False
                
                user.last_active_day = day
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error updating agent last active day: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_churned_agents(self, day: int = None, inactivity_threshold: int = None) -> List[str]:
        """Get churned agents."""
        try:
            session = Session(self.engine)
            try:
                query = session.query(User_mgmt).filter(User_mgmt.churned == True)
                if day is not None and inactivity_threshold is not None:
                    query = query.filter(User_mgmt.last_active_day < day - inactivity_threshold)
                
                users = query.all()
                return [user.id for user in users]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting churned agents: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def set_agent_churned(self, agent_id: str, churned: bool) -> bool:
        """Set agent churned status."""
        try:
            session = Session(self.engine)
            try:
                user = session.query(User_mgmt).filter_by(id=agent_id).first()
                if not user:
                    return False
                
                user.churned = churned
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error setting agent churned: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_inactive_agents(self, inactivity_threshold: int) -> List[str]:
        """Get inactive agents."""
        try:
            session = Session(self.engine)
            try:
                from datetime import datetime, timedelta
                
                # Get current day (you may need to adjust this based on your simulation logic)
                current_day = 1  # This should be passed from somewhere
                cutoff_day = current_day - inactivity_threshold
                
                users = session.query(User_mgmt).filter(
                    User_mgmt.last_active_day < cutoff_day
                ).all()
                return [user.id for user in users]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting inactive agents: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []


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
        import uuid
        session = Session(self.engine)
        try:
            # Map common field names to actual model field names
            mapped_data = {
                "id": post_data.get("id") or str(uuid.uuid4()),  # Generate UUID if not provided
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
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding post: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
        finally:
            session.close()
    
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
        session = Session(self.engine)
        try:
            # Generate UUID for PostTopic id
            post_topic = PostTopic(
                id=str(uuid.uuid4()),
                post_id=post_id, 
                topic_id=topic_id
            )
            session.add(post_topic)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding post topic: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
        finally:
            session.close()
    
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
    
    # Metadata methods
    def add_post_emotion(self, post_id: str, emotion_id: str) -> bool:
        """Add emotion to a post."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                post_emotion = PostEmotion(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    emotion_id=emotion_id
                )
                session.add(post_emotion)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post emotion: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_emotion_by_name(self, emotion_name: str) -> Optional[str]:
        """Get emotion ID by name."""
        try:
            session = Session(self.engine)
            try:
                emotion = session.query(Emotion).filter_by(emotion=emotion_name).first()
                return emotion.id if emotion else None
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting emotion by name: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def initialize_emotions_table(self):
        """Initialize emotions table with standard emotions."""
        try:
            session = Session(self.engine)
            try:
                # Check if emotions already exist
                count = session.query(func.count(Emotion.id)).scalar()
                if count > 0:
                    return True
                
                # Standard emotions with IDs and icons
                import uuid
                emotions = [
                    {"id": str(uuid.uuid4()), "emotion": "joy", "icon": "😊"},
                    {"id": str(uuid.uuid4()), "emotion": "sadness", "icon": "😢"},
                    {"id": str(uuid.uuid4()), "emotion": "anger", "icon": "😠"},
                    {"id": str(uuid.uuid4()), "emotion": "fear", "icon": "😨"},
                    {"id": str(uuid.uuid4()), "emotion": "surprise", "icon": "😲"},
                    {"id": str(uuid.uuid4()), "emotion": "disgust", "icon": "🤢"},
                ]
                
                for emotion_data in emotions:
                    emotion = Emotion(**emotion_data)
                    session.add(emotion)
                
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error initializing emotions table: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def add_post_sentiment(self, post_id: str, sentiment_score: float) -> bool:
        """Add sentiment score to a post."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                # Get post to extract required fields
                post = session.query(Post).filter_by(id=post_id).first()
                if not post:
                    return False
                
                post_sentiment = PostSentiment(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    compound=sentiment_score,
                    user_id=post.user_id,
                    round=post.round,
                    topic_id="0",  # Default topic
                    is_post=1,
                    is_comment=0 if post.comment_to in (-1, "-1", None) else 1,
                    is_reaction=0
                )
                session.add(post_sentiment)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post sentiment: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_post_sentiment(self, post_id: str) -> Optional[float]:
        """Get sentiment score for a post."""
        try:
            session = Session(self.engine)
            try:
                sentiment = session.query(PostSentiment).filter_by(post_id=post_id).first()
                return sentiment.compound if sentiment else None
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post sentiment: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add toxicity score to a post."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                post_toxicity = PostToxicity(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    toxicity=toxicity_score
                )
                session.add(post_toxicity)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post toxicity: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def add_or_get_hashtag(self, hashtag: str) -> Optional[str]:
        """Add or get hashtag ID."""
        try:
            session = Session(self.engine)
            try:
                # Try to get existing hashtag
                existing = session.query(Hashtag).filter_by(hashtag=hashtag).first()
                if existing:
                    return existing.id
                
                # Create new hashtag
                import uuid
                hashtag_id = str(uuid.uuid4())
                new_hashtag = Hashtag(id=hashtag_id, hashtag=hashtag)
                session.add(new_hashtag)
                session.commit()
                return hashtag_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding/getting hashtag: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def add_post_hashtag(self, post_id: str, hashtag_id: str) -> bool:
        """Add hashtag to a post."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                post_hashtag = PostHashtag(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    hashtag_id=hashtag_id
                )
                session.add(post_hashtag)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post hashtag: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False


    # Mention methods
    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """Add a mention to a post."""
        try:
            from YSimulator.YServer.classes.models import Mention
            import uuid
            session = Session(self.engine)
            try:
                mention = Mention(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    mentioned_user_id=mentioned_user_id,
                    replied=False
                )
                session.add(mention)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding mention: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False
    
    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions for a user."""
        try:
            from YSimulator.YServer.classes.models import Mention
            session = Session(self.engine)
            try:
                mentions = session.query(Mention).filter(
                    Mention.mentioned_user_id == user_id,
                    Mention.replied == False
                ).all()
                
                return [
                    {
                        "id": mention.id,
                        "post_id": mention.post_id,
                        "mentioned_user_id": mention.mentioned_user_id,
                        "replied": mention.replied
                    }
                    for mention in mentions
                ]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting unreplied mentions: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []
    
    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark a mention as replied."""
        try:
            from YSimulator.YServer.classes.models import Mention
            session = Session(self.engine)
            try:
                mention = session.query(Mention).filter(
                    Mention.post_id == post_id,
                    Mention.mentioned_user_id == mentioned_user_id
                ).first()
                
                if not mention:
                    return False
                
                mention.replied = True
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error marking mention replied: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False


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
        
        # Generate IDs for follows that don't have them
        for follow in follows_data:
            if "id" not in follow or not follow["id"]:
                follow["id"] = str(uuid.uuid4())
        
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


class SQLArticleRepository(ArticleRepository):
    """SQLAlchemy implementation of ArticleRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL article repository."""
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
    
    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """Add a website."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                website_id = website_data.get("id", str(uuid.uuid4()))
                website = Website(
                    id=website_id,
                    name=website_data.get("name"),
                    url=website_data.get("url"),
                    rss_url=website_data.get("rss_url"),
                )
                session.add(website)
                session.commit()
                return website_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding website: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def add_websites_batch(self, websites_data: List[Dict[str, Any]]) -> int:
        """Add multiple websites in a batch, skipping duplicates."""
        if not websites_data:
            return 0
        
        session = Session(self.engine)
        try:
            import uuid
            
            # First, deduplicate within the batch itself by ID and RSS
            seen_ids = set()
            seen_rss = set()
            deduplicated = []
            
            for website in websites_data:
                website_id = website.get("id")
                website_rss = website.get("rss")
                
                # Skip if we've seen this ID or RSS in this batch
                if website_id and website_id in seen_ids:
                    continue
                if website_rss and website_rss in seen_rss:
                    continue
                
                # Mark as seen
                if website_id:
                    seen_ids.add(website_id)
                if website_rss:
                    seen_rss.add(website_rss)
                
                deduplicated.append(website)
            
            if not deduplicated:
                return 0
            
            # Now check for existing websites in database by both ID and RSS
            website_ids = [w.get("id") for w in deduplicated if w.get("id")]
            rss_urls = [w.get("rss") for w in deduplicated if w.get("rss")]
            
            existing_ids = set()
            existing_rss = set()
            
            if website_ids:
                existing_ids = {
                    row[0] for row in session.query(Website.id).filter(Website.id.in_(website_ids)).all()
                }
            
            if rss_urls:
                existing_rss = {
                    row[0] for row in session.query(Website.rss).filter(Website.rss.in_(rss_urls)).all()
                }
            
            # Filter out websites that already exist in database
            new_websites = [
                w for w in deduplicated
                if w.get("id") not in existing_ids and w.get("rss") not in existing_rss
            ]
            
            if not new_websites:
                return 0
            
            # Ensure all websites have IDs
            for website in new_websites:
                if "id" not in website or not website["id"]:
                    website["id"] = str(uuid.uuid4())
                if "last_fetched" not in website:
                    website["last_fetched"] = str(uuid.uuid4())
            
            session.bulk_insert_mappings(Website, new_websites)
            session.commit()
            return len(new_websites)
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding websites in batch: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(websites_data)}},
            )
            return 0
        finally:
            session.close()
    
    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """Add an article."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                article_id = article_data.get("id", str(uuid.uuid4()))
                article = Article(
                    id=article_id,
                    title=article_data.get("title"),
                    url=article_data.get("url"),
                    content=article_data.get("content"),
                    website_id=article_data.get("website_id"),
                    round_id=article_data.get("round_id"),
                )
                session.add(article)
                session.commit()
                return article_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding article: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get an article by ID."""
        try:
            session = Session(self.engine)
            try:
                article = session.query(Article).filter_by(id=article_id).first()
                if not article:
                    return None
                
                return {
                    "id": article.id,
                    "title": article.title,
                    "url": article.url,
                    "content": article.content,
                    "website_id": article.website_id,
                    "round_id": article.round_id,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting article: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """Get website by RSS URL."""
        try:
            session = Session(self.engine)
            try:
                website = session.query(Website).filter_by(rss_url=rss_url).first()
                if not website:
                    return None
                
                return {
                    "id": website.id,
                    "name": website.name,
                    "url": website.url,
                    "rss_url": website.rss_url,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting website by RSS: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_article_topics(self, article_id: str) -> List[str]:
        """Get topics associated with an article."""
        try:
            session = Session(self.engine)
            try:
                topics = (
                    session.query(ArticleTopic.topic_id)
                    .filter_by(article_id=article_id)
                    .all()
                )
                return [topic[0] for topic in topics]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting article topics: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []


class SQLImageRepository(ImageRepository):
    """SQLAlchemy implementation of ImageRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """Initialize SQL image repository."""
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
    
    def add_image(self, image_data: Dict[str, Any]) -> Optional[str]:
        """Add an image."""
        try:
            session = Session(self.engine)
            try:
                import uuid
                image_id = image_data.get("id", str(uuid.uuid4()))
                image = Image(
                    id=image_id,
                    url=image_data.get("url"),
                    description=image_data.get("description"),
                )
                session.add(image)
                session.commit()
                return image_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding image: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
    
    def get_random_image(self) -> Optional[Dict[str, Any]]:
        """Get a random image."""
        try:
            session = Session(self.engine)
            try:
                # Get a random image using SQL random function
                image = session.query(Image).order_by(func.random()).first()
                if not image:
                    return None
                
                return {
                    "id": image.id,
                    "url": image.url,
                    "description": image.description,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting random image: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

