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
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
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
    Reported,
    Round,
    SysMessage,
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

                # Convert SQLAlchemy model to dict - use getattr for optional fields
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": getattr(user, "email", None),
                    "leaning": getattr(user, "leaning", None),
                    "archetype": getattr(user, "archetype", None),
                    "user_type": getattr(user, "user_type", None),
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error getting user: {e}", extra={"extra_data": {"error": str(e)}})
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
                        "email": getattr(user, "email", None),
                        "leaning": getattr(user, "leaning", None),
                        "archetype": getattr(user, "archetype", None),
                        "user_type": getattr(user, "user_type", None),
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
                    "email": getattr(user, "email", None),
                    "leaning": getattr(user, "leaning", None),
                    "archetype": getattr(user, "archetype", None),
                    "user_type": getattr(user, "user_type", None),
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
                f"Error updating agent last active day: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return False

    def get_churned_agents(self) -> List[str]:
        """
        Get all churned agents (agents with left_on set).
        Matches old middleware signature.

        Returns:
            List of agent IDs (UUID strings) that are churned
        """
        try:
            session = Session(self.engine)
            try:
                # Agent is churned if left_on is set (not null)
                users = session.query(User_mgmt).filter(User_mgmt.left_on.isnot(None)).all()
                return [user.id for user in users]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting churned agents: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    def set_agent_churned(self, agent_id: str, round_id: str) -> bool:
        """
        Mark an agent as churned by setting the left_on field to the current round.
        Matches old middleware signature.

        Args:
            agent_id: Agent ID (UUID string)
            round_id: Round ID when agent churned (UUID string)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session = Session(self.engine)
            try:
                # Set left_on field to round_id to mark as churned
                result = (
                    session.query(User_mgmt).filter_by(id=agent_id).update({"left_on": round_id})
                )
                session.commit()
                return result > 0
            except Exception as e:
                session.rollback()
                self.logger.error(
                    f"Error setting left_on for agent {agent_id}: {e}",
                    extra={"extra_data": {"agent_id": agent_id, "error": str(e)}},
                )
                return False
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error setting agent churned: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_inactive_agents(self, current_day: int, inactivity_threshold: int) -> List[str]:
        """Get inactive agents."""
        try:
            session = Session(self.engine)
            try:
                cutoff_day = current_day - inactivity_threshold

                users = (
                    session.query(User_mgmt).filter(User_mgmt.last_active_day < cutoff_day).all()
                )
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
            # Generate post ID if not provided
            post_id = post_data.get("id") or str(uuid.uuid4())

            # Determine comment_to value
            comment_to = post_data.get("parent_post") or post_data.get("comment_to", -1)

            # Get thread_id from data, or set to post's own ID if this is a root post (not a comment)
            thread_id = post_data.get("root_post") or post_data.get("thread_id")
            if not thread_id and comment_to in (-1, "-1", None):
                # This is a root post (not a comment), so it starts its own thread
                thread_id = post_id

            # Map common field names to actual model field names
            mapped_data = {
                "id": post_id,
                "tweet": post_data.get("text") or post_data.get("tweet"),
                "user_id": post_data.get("author") or post_data.get("user_id"),
                "round": post_data.get("round"),
                "comment_to": comment_to,
                "thread_id": thread_id,
                "reaction_count": post_data.get("num_reactions")
                or post_data.get("reaction_count", 0),
                # CRITICAL: Include news_id and shared_from for proper post referencing
                "news_id": post_data.get("news_id"),
                "shared_from": post_data.get("shared_from"),
                # Include image-related fields
                "image_id": post_data.get("image_id"),
                "post_img": post_data.get("post_img"),
                "is_moderation_comment": post_data.get("is_moderation_comment", 0),
            }
            # Filter out None values
            mapped_data = {k: v for k, v in mapped_data.items() if v is not None}

            post = Post(**mapped_data)
            session.add(post)
            session.commit()
            return post.id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding post: {e}", extra={"extra_data": {"error": str(e)}})
            return None
        finally:
            session.close()

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post by ID - returns API field names with proper mapping."""
        try:
            session = Session(self.engine)
            try:
                post = session.query(Post).filter_by(id=post_id).first()
                if not post:
                    return None

                # Map model field names to API field names
                return {
                    "id": post.id,
                    "root_post": post.thread_id,  # API: root_post <-> Model: thread_id
                    "news_id": post.news_id,
                    "parent_post": post.comment_to,  # API: parent_post <-> Model: comment_to
                    "shared_from": post.shared_from,
                    "author": post.user_id,  # API: author <-> Model: user_id
                    "user_id": post.user_id,  # Alias for backward compatibility
                    "text": post.tweet,  # API: text <-> Model: tweet
                    "round": post.round,
                    "is_moderation_comment": int(getattr(post, "is_moderation_comment", 0) or 0),
                    # API: num_reactions <-> Model: reaction_count
                    "num_reactions": post.reaction_count,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error getting post: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """Get recent post IDs."""
        try:
            session = Session(self.engine)
            try:
                posts = session.query(Post.id).order_by(Post.round.desc()).limit(limit).all()
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

                    thread.append(
                        {
                            "id": post.id,
                            "author": post.user_id,  # Map user_id to author
                            "text": post.tweet,  # Map tweet to text
                            "parent_post": post.comment_to,  # Map comment_to to parent_post
                        }
                    )

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
            import uuid

            session = Session(self.engine)
            try:
                # Generate UUID if not provided
                if "id" not in interaction_data:
                    interaction_data["id"] = str(uuid.uuid4())

                reaction = Reaction(**interaction_data)
                session.add(reaction)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding interaction: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_report(self, report_data: Dict[str, Any]) -> bool:
        """Add a moderation report for a post."""
        try:
            import uuid

            session = Session(self.engine)
            try:
                if "id" not in report_data:
                    report_data["id"] = str(uuid.uuid4())

                report = Reported(**report_data)
                session.add(report)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding report: {e}", extra={"extra_data": {"error": str(e)}}
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
                import uuid

                post_topic = PostTopic(id=str(uuid.uuid4()), post_id=post_id, topic_id=topic_id)
                session.add(post_topic)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
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
                topics = session.query(PostTopic.topic_id).filter_by(post_id=post_id).all()
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

    def get_active_system_messages(self, user_id: str, round_id: str) -> List[Dict[str, Any]]:
        """Get active system messages for a user, comparing rounds by day/hour."""
        try:
            session = Session(self.engine)
            try:
                current_round = session.query(Round).filter_by(id=round_id).first()
                if not current_round:
                    return []

                current_position = (int(current_round.day or 0), int(current_round.hour or 0))
                current_flat_round = current_position[0] * 24 + current_position[1]
                messages = session.query(SysMessage).filter_by(to_uid=user_id).all()
                active_messages = []

                for message in messages:
                    lower_bound = None

                    if message.from_round:
                        from_round = session.query(Round).filter_by(id=message.from_round).first()
                        if from_round is None:
                            continue
                        lower_bound = (int(from_round.day or 0), int(from_round.hour or 0))

                    if lower_bound is not None and current_position < lower_bound:
                        continue
                    if message.duration is not None and lower_bound is not None:
                        lower_flat_round = lower_bound[0] * 24 + lower_bound[1]
                        if current_flat_round > (lower_flat_round + int(message.duration)):
                            continue

                    active_messages.append(
                        {
                            "id": message.id,
                            "type": message.type,
                            "message": message.message,
                            "to_uid": message.to_uid,
                            "from_round": message.from_round,
                            "duration": message.duration,
                        }
                    )

                return active_messages
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting active system messages: {e}",
                extra={"extra_data": {"user_id": user_id, "round_id": round_id, "error": str(e)}},
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
                    id=str(uuid.uuid4()), post_id=post_id, emotion_id=emotion_id
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

    def get_emotion_by_name_full(self, emotion_name: str) -> Optional[Dict[str, str]]:
        """Get full emotion data by name (old middleware signature)."""
        try:
            session = Session(self.engine)
            try:
                emotion = session.query(Emotion).filter_by(emotion=emotion_name).first()
                if not emotion:
                    return None

                return {"id": emotion.id, "emotion": emotion.emotion, "icon": emotion.icon}
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting emotion by name (full): {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return None

    def initialize_emotions_table(self):
        """Initialize emotions table with GoEmotions taxonomy (28 emotions)."""
        try:
            session = Session(self.engine)
            try:
                # GoEmotions taxonomy with Material Design icon mappings
                import uuid

                emotions_data = [
                    ("amusement", "mdi-emoticon-happy"),
                    ("admiration", "mdi-weather-sunny"),
                    ("anger", "mdi-emoticon-devil"),
                    ("annoyance", "mdi-emoticon-tongue"),
                    ("approval", "mdi-thumb-up-outline"),
                    ("caring", "mdi-cake"),
                    ("confusion", "mdi-emoticon-neutral"),
                    ("curiosity", "mdi-beaker-outline"),
                    ("desire", "mdi-cash-multiple"),
                    ("disappointment", "mdi-close-circle"),
                    ("disapproval", "mdi-thumb-down-outline"),
                    ("disgust", "mdi-emoticon-poop"),
                    ("embarrassment", "mdi-minus-circle"),
                    ("excitement", "mdi-rocket"),
                    ("fear", "mdi-weather-lightning"),
                    ("gratitude", "mdi-panda"),
                    ("grief", "mdi-weather-pouring"),
                    ("joy", "mdi-emoticon"),
                    ("love", "mdi-heart"),
                    ("nervousness", "mdi-alert"),
                    ("optimism", "mdi-leaf"),
                    ("pride", "mdi-emoticon-cool"),
                    ("realization", "mdi-lightbulb-outline"),
                    ("relief", "mdi-weather-sunset-up"),
                    ("remorse", "mdi-ambulance"),
                    ("sadness", "mdi-emoticon-sad"),
                    ("surprise", "mdi-wallet-giftcard"),
                    ("trust", "mdi-brightness-5"),
                ]

                created_count = 0
                for emotion_name, icon in emotions_data:
                    # Check if emotion already exists
                    existing = (
                        session.query(Emotion).filter(Emotion.emotion == emotion_name).first()
                    )

                    if not existing:
                        # Create new emotion
                        emotion_id = str(uuid.uuid4())
                        emotion = Emotion(id=emotion_id, emotion=emotion_name, icon=icon)
                        session.add(emotion)
                        created_count += 1

                session.commit()
                self.logger.info(
                    f"Initialized emotions table: {created_count}new emotions added, "
                    f"{len(emotions_data) - created_count}already existed"
                )
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
                    is_reaction=0,
                )
                session.add(post_sentiment)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post sentiment: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_post_sentiment_full(self, sentiment_data: Dict[str, Any]) -> bool:
        """Add sentiment data using full dict (old middleware signature)."""
        try:
            session = Session(self.engine)
            try:
                import uuid

                # Prepare sentiment data with id if not present
                if "id" not in sentiment_data:
                    sentiment_data = dict(sentiment_data)  # Make a copy
                    sentiment_data["id"] = str(uuid.uuid4())

                post_sentiment = PostSentiment(**sentiment_data)
                session.add(post_sentiment)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post sentiment (full): {e}", extra={"extra_data": {"error": str(e)}}
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

    def get_post_sentiment_full(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get full sentiment data for a post (old middleware signature)."""
        try:
            session = Session(self.engine)
            try:
                sentiment = session.query(PostSentiment).filter_by(post_id=post_id).first()
                if not sentiment:
                    return None

                return {
                    "id": sentiment.id,
                    "post_id": sentiment.post_id,
                    "user_id": sentiment.user_id,
                    "topic_id": sentiment.topic_id,
                    "round": sentiment.round,
                    "neg": sentiment.neg,
                    "pos": sentiment.pos,
                    "neu": sentiment.neu,
                    "compound": sentiment.compound,
                    "sentiment_parent": sentiment.sentiment_parent,
                    "is_post": sentiment.is_post,
                    "is_comment": sentiment.is_comment,
                    "is_reaction": sentiment.is_reaction,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post sentiment (full): {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def add_post_toxicity(self, post_id: str, toxicity_score: float) -> bool:
        """Add toxicity score to a post."""
        try:
            session = Session(self.engine)
            try:
                import uuid

                post_toxicity = PostToxicity(
                    id=str(uuid.uuid4()), post_id=post_id, toxicity=toxicity_score
                )
                session.add(post_toxicity)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post toxicity: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_post_toxicity_full(self, toxicity_data: Dict[str, Any]) -> bool:
        """Add toxicity data using full dict (old middleware signature)."""
        try:
            session = Session(self.engine)
            try:
                import uuid

                # Prepare toxicity data with id if not present
                if "id" not in toxicity_data:
                    toxicity_data = dict(toxicity_data)  # Make a copy
                    toxicity_data["id"] = str(uuid.uuid4())

                post_toxicity = PostToxicity(**toxicity_data)
                session.add(post_toxicity)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding post toxicity (full): {e}", extra={"extra_data": {"error": str(e)}}
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
                    id=str(uuid.uuid4()), post_id=post_id, hashtag_id=hashtag_id
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
            import uuid

            from YSimulator.YServer.classes.models import Mention, Post

            session = Session(self.engine)
            try:
                # Get the post to retrieve the round
                post = session.query(Post).filter_by(id=post_id).first()
                round_id = post.round if post else None

                mention = Mention(
                    id=str(uuid.uuid4()),
                    post_id=post_id,
                    user_id=mentioned_user_id,  # Model uses user_id, not mentioned_user_id
                    round=round_id,
                    answered=0,
                )
                session.add(mention)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error adding mention: {e}", extra={"extra_data": {"error": str(e)}})
            return False

    def add_mention_full(self, mention_data: Dict[str, Any]) -> bool:
        """Add a mention using full dict (old middleware signature)."""
        try:
            import uuid

            from YSimulator.YServer.classes.models import Mention

            session = Session(self.engine)
            try:
                # Prepare mention data with id if not present
                if "id" not in mention_data:
                    mention_data = dict(mention_data)  # Make a copy
                    mention_data["id"] = str(uuid.uuid4())

                mention = Mention(**mention_data)
                session.add(mention)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding mention (full): {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get unreplied mentions for a user."""
        try:
            from YSimulator.YServer.classes.models import Mention

            session = Session(self.engine)
            try:
                mentions = (
                    session.query(Mention)
                    .filter(
                        Mention.user_id == user_id,  # Model uses user_id, not mentioned_user_id
                        Mention.answered == 0,  # Model uses answered (0=unreplied, 1=replied)
                    )
                    .all()
                )

                return [
                    {
                        "id": mention.id,
                        "user_id": mention.user_id,
                        "post_id": mention.post_id,
                        "round": mention.round,
                        "answered": mention.answered,
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

    def get_users_with_unreplied_mentions(self, user_ids: List[str]) -> List[str]:
        """Return user IDs that have at least one unreplied mention."""
        try:
            from YSimulator.YServer.classes.models import Mention

            if not user_ids:
                return []

            session = Session(self.engine)
            try:
                rows = (
                    session.query(Mention.user_id)
                    .filter(
                        Mention.user_id.in_(list(user_ids)),
                        Mention.answered == 0,
                    )
                    .distinct()
                    .all()
                )
                return [str(row[0]) for row in rows if row and row[0] is not None]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting users with unreplied mentions: {e}",
                extra={"extra_data": {"error": str(e)}},
            )
            return []

    def get_mention_by_id(self, mention_id: str) -> Optional[Dict[str, Any]]:
        """Get mention by ID."""
        try:
            from YSimulator.YServer.classes.models import Mention

            session = Session(self.engine)
            try:
                mention = session.query(Mention).filter(Mention.id == mention_id).first()

                if not mention:
                    return None

                return {
                    "id": mention.id,
                    "user_id": mention.user_id,
                    "mentioned_user_id": mention.user_id,  # Alias for compatibility
                    "post_id": mention.post_id,
                    "round": mention.round,
                    "answered": mention.answered,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting mention by ID: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """Mark a mention as replied."""
        try:
            from YSimulator.YServer.classes.models import Mention

            max_attempts = 4
            for attempt in range(max_attempts):
                session = Session(self.engine)
                try:
                    mention = (
                        session.query(Mention)
                        .filter(
                            Mention.post_id == post_id,
                            Mention.user_id
                            == mentioned_user_id,  # Model uses user_id, not mentioned_user_id
                        )
                        .first()
                    )

                    if not mention:
                        return False

                    mention.answered = 1  # Model uses answered (0=unreplied, 1=replied)
                    session.commit()
                    return True
                except OperationalError as e:
                    session.rollback()
                    if "database is locked" not in str(e).lower() or attempt == max_attempts - 1:
                        raise
                    time.sleep(0.15 * (attempt + 1))
                except Exception:
                    session.rollback()
                    raise
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error marking mention replied: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def mark_mention_replied_by_id(self, mention_id: str) -> bool:
        """Mark a mention as replied by mention ID (old middleware signature)."""
        try:
            from YSimulator.YServer.classes.models import Mention

            session = Session(self.engine)
            try:
                mention = session.query(Mention).filter(Mention.id == mention_id).first()

                if not mention:
                    self.logger.warning(f"Mention {mention_id} not found")
                    return False

                mention.answered = 1  # Model uses answered (0=unreplied, 1=replied)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error marking mention replied by id: {e}", extra={"extra_data": {"error": str(e)}}
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
                    "action": follow_data.get("action", "follow"),
                    "round": follow_data.get("round") or follow_data.get("round_id"),
                }
                # Filter out None values
                mapped_data = {k: v for k, v in mapped_data.items() if v is not None}

                follow = Follow(**mapped_data)
                session.add(follow)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error adding follow: {e}", extra={"extra_data": {"error": str(e)}})
            return False

    def add_follow_full(self, follow_data: Dict[str, Any]) -> bool:
        """Add a follow relationship using full dict (alias for add_follow)."""
        return self.add_follow(follow_data)

    def add_follows_batch(self, follows_data: List[Dict[str, Any]]) -> int:
        """Add multiple follow relationships in a batch."""
        if not follows_data:
            return 0

        try:
            import uuid

            session = Session(self.engine)
            try:
                # Map field names for each follow (same logic as add_follow)
                mapped_follows = []
                for follow_data in follows_data:
                    mapped_data = {
                        "id": follow_data.get("id", str(uuid.uuid4())),
                        "user_id": follow_data.get("followee_id") or follow_data.get("user_id"),
                        "follower_id": follow_data.get("follower_id"),
                        "action": follow_data.get("action", "follow"),
                        "round": follow_data.get("round") or follow_data.get("round_id"),
                    }
                    # Filter out None values
                    mapped_data = {k: v for k, v in mapped_data.items() if v is not None}
                    mapped_follows.append(mapped_data)

                session.bulk_insert_mappings(Follow, mapped_follows)
                session.commit()
                return len(mapped_follows)
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

    def list_interests(self) -> List[Dict[str, Any]]:
        """Return all known interests/topics."""
        try:
            session = Session(self.engine)
            try:
                interests = session.query(Interest).all()
                return [{"iid": interest.iid, "interest": interest.interest} for interest in interests]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error listing interests: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    def add_or_get_interests_batch(self, interest_names: List[str]) -> Dict[str, str]:
        """
        Add multiple interests or get existing ones' IDs in batch.

        This method is optimized for bulk interest creation during agent registration.
        It performs a single query to check existing interests and inserts only new ones.

        Args:
            interest_names: List of interest/topic names

        Returns:
            Dict mapping interest names to their IDs
        """
        if not interest_names:
            return {}

        try:
            import uuid

            result = {}
            session = Session(self.engine)
            try:
                # Get all existing interests in one query
                existing_interests = (
                    session.query(Interest).filter(Interest.interest.in_(interest_names)).all()
                )

                # Map existing interests
                existing_map = {interest.interest: interest.iid for interest in existing_interests}
                result.update(existing_map)

                # Find new interests that need to be created
                new_interest_names = [name for name in interest_names if name not in existing_map]

                if new_interest_names:
                    # Create new interests with UUIDs
                    new_interests = []
                    for name in new_interest_names:
                        interest_id = str(uuid.uuid4())
                        new_interests.append({"iid": interest_id, "interest": name})
                        result[name] = interest_id

                    # Bulk insert new interests
                    session.bulk_insert_mappings(Interest, new_interests)
                    session.commit()

                return result
            except Exception as e:
                session.rollback()
                self.logger.error(
                    f"Error in batch interest creation: {e}",
                    extra={"extra_data": {"error": str(e), "count": len(interest_names)}},
                )
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error batch adding/getting interests: {e}",
                extra={"extra_data": {"error": str(e), "count": len(interest_names)}},
            )
            return {}

    def add_user_interest(self, user_id: str, interest_id: str, round_id: str) -> bool:
        """Add a user interest."""
        try:
            import uuid

            session = Session(self.engine)
            try:
                user_interest = UserInterest(
                    id=str(uuid.uuid4()),  # Generate UUID for id field
                    user_id=user_id,
                    interest_id=interest_id,
                    round_id=round_id,
                )
                session.add(user_interest)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding user interest: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_agent_opinion(
        self,
        agent_id: str,
        round_id: str,
        topic_id: str,
        opinion: float,
        id_interacted_with: Optional[str] = None,
        id_post: Optional[str] = None,
        stubborn: bool = False,
    ) -> bool:
        """Add an agent opinion on a topic."""
        try:
            import uuid

            session = Session(self.engine)
            try:
                latest_opinion = (
                    session.query(Agent_Opinion)
                    .filter_by(agent_id=agent_id, topic_id=topic_id)
                    .order_by(Agent_Opinion.tid.desc(), Agent_Opinion.id.desc())
                    .first()
                )
                effective_stubborn = bool(stubborn) or bool(
                    latest_opinion.stubborn if latest_opinion is not None else False
                )
                effective_opinion = (
                    float(latest_opinion.opinion)
                    if latest_opinion is not None and bool(latest_opinion.stubborn)
                    else opinion
                )
                # Agent_Opinion model uses 'tid' for round_id
                agent_opinion = Agent_Opinion(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    tid=round_id,  # Note: model uses 'tid' not 'round_id'
                    topic_id=topic_id,
                    opinion=effective_opinion,
                    id_interacted_with=id_interacted_with,
                    id_post=id_post,
                    stubborn=effective_stubborn,
                )
                session.add(agent_opinion)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding agent opinion: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def add_user_interests_batch(
        self, user_interests_data: List[Dict[str, str]], batch_size: int = 1000
    ) -> int:
        """
        Add multiple user interests in batch.

        This method is optimized for bulk insertion of user interests
        during agent registration. It uses SQLAlchemy bulk_insert_mappings
        for improved performance with large agent populations.

        Args:
            user_interests_data: List of dictionaries, each containing:
                - id: UUID for the user_interest entry
                - user_id: UUID of user
                - interest_id: UUID of interest/topic
                - round_id: UUID of round
            batch_size: Number of records to insert per transaction (default: 1000)

        Returns:
            int: Number of user interests successfully added
        """
        if not user_interests_data:
            return 0

        try:
            import uuid

            total_added = 0

            # Process in batches to avoid memory issues with large populations
            for i in range(0, len(user_interests_data), batch_size):
                batch = user_interests_data[i : i + batch_size]

                session = Session(self.engine)
                try:
                    # Use bulk_insert_mappings for performance
                    # Ensure all entries have UUIDs
                    for entry in batch:
                        if "id" not in entry or not entry["id"]:
                            entry["id"] = str(uuid.uuid4())

                    session.bulk_insert_mappings(UserInterest, batch)
                    session.commit()
                    total_added += len(batch)
                except Exception as e:
                    session.rollback()
                    self.logger.error(
                        f"Error in batch user interest insertion: {e}",
                        extra={"extra_data": {"error": str(e), "batch_size": len(batch)}},
                    )
                    raise
                finally:
                    session.close()

            return total_added
        except Exception as e:
            self.logger.error(
                f"Error batch adding user interests: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(user_interests_data)}},
            )
            return total_added

    def add_agent_opinions_batch(
        self, agent_opinions_data: List[Dict[str, Any]], batch_size: int = 1000
    ) -> int:
        """
        Add multiple agent opinions in batch.

        This method is optimized for bulk insertion of agent opinions
        during agent registration. It uses SQLAlchemy bulk_insert_mappings
        for improved performance with large agent populations.

        Args:
            agent_opinions_data: List of dictionaries, each containing:
                - id: UUID for the opinion entry
                - agent_id: UUID of agent
                - tid: UUID of round (note: model uses 'tid' not 'round_id')
                - topic_id: UUID of topic
                - opinion: Opinion value (float)
                - id_interacted_with: Optional UUID of agent interacted with
                - id_post: Optional UUID of post
            batch_size: Number of records to insert per transaction (default: 1000)

        Returns:
            int: Number of agent opinions successfully added
        """
        if not agent_opinions_data:
            return 0

        try:
            import uuid

            total_added = 0

            # Process in batches to avoid memory issues with large populations
            for i in range(0, len(agent_opinions_data), batch_size):
                batch = agent_opinions_data[i : i + batch_size]

                session = Session(self.engine)
                try:
                    # Use bulk_insert_mappings for performance
                    # Ensure all entries have UUIDs
                    for entry in batch:
                        if "id" not in entry or not entry["id"]:
                            entry["id"] = str(uuid.uuid4())
                        latest_opinion = (
                            session.query(Agent_Opinion)
                            .filter_by(agent_id=entry["agent_id"], topic_id=entry["topic_id"])
                            .order_by(Agent_Opinion.tid.desc(), Agent_Opinion.id.desc())
                            .first()
                        )
                        entry["stubborn"] = bool(entry.get("stubborn", False)) or bool(
                            latest_opinion.stubborn if latest_opinion is not None else False
                        )
                        if latest_opinion is not None and bool(latest_opinion.stubborn):
                            entry["opinion"] = float(latest_opinion.opinion)

                    session.bulk_insert_mappings(Agent_Opinion, batch)
                    session.commit()
                    total_added += len(batch)
                except Exception as e:
                    session.rollback()
                    self.logger.error(
                        f"Error in batch agent opinion insertion: {e}",
                        extra={"extra_data": {"error": str(e), "batch_size": len(batch)}},
                    )
                    raise
                finally:
                    session.close()

            return total_added
        except Exception as e:
            self.logger.error(
                f"Error batch adding agent opinions: {e}",
                extra={"extra_data": {"error": str(e), "batch_size": len(agent_opinions_data)}},
            )
            return total_added

    def get_latest_agent_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """Get latest agent opinion on a topic."""
        try:
            session = Session(self.engine)
            try:
                opinion = (
                    session.query(Agent_Opinion)
                    .filter_by(agent_id=agent_id, topic_id=topic_id)
                    .order_by(
                        Agent_Opinion.tid.desc(), Agent_Opinion.id.desc()
                    )  # Order by round then id for insertion order
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

    def get_user_interests_in_window_old(
        self, user_id: str, current_round_id: str, attention_window: int
    ) -> List[Dict[str, str]]:
        """
        Get user interests within attention window (old middleware signature).

        This method matches the old db_middleware.get_user_interests_in_window signature.
        It converts round_id to day/hour and calculates the sliding window.

        Args:
            user_id: User UUID
            current_round_id: Current round UUID
            attention_window: Number of rounds to look back

        Returns:
            List[Dict]: List of user interest records with interest_id and round_id
        """
        try:
            session = Session(self.engine)
            try:
                # Get current round details
                current_round = session.query(Round).filter(Round.id == current_round_id).first()
                if not current_round:
                    return []

                current_day = current_round.day
                current_hour = current_round.hour

                # Calculate the round number (day * 24 + hour)
                current_round_num = (current_day - 1) * 24 + current_hour
                cutoff_round_num = max(0, current_round_num - attention_window)

                # Calculate cutoff day and hour
                cutoff_day = (cutoff_round_num // 24) + 1
                cutoff_hour = cutoff_round_num % 24

                # Query user interests within the window
                user_interests = (
                    session.query(UserInterest, Round)
                    .join(Round, UserInterest.round_id == Round.id)
                    .filter(UserInterest.user_id == user_id)
                    .filter(
                        (Round.day > cutoff_day)
                        | ((Round.day == cutoff_day) & (Round.hour >= cutoff_hour))
                    )
                    .all()
                )

                return [
                    {"interest_id": ui.interest_id, "round_id": ui.round_id}
                    for ui, _ in user_interests
                ]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting user interests in window (old): {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id}},
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

    def get_round_info(self, round_id: str) -> Optional[Dict[str, int]]:
        """
        Get round information (day and hour) for a given round ID.

        Args:
            round_id: Round ID (UUID)

        Returns:
            Dictionary with 'day' and 'hour' keys, or None if round not found
        """
        try:
            session = Session(self.engine)
            try:
                round_obj = session.query(Round).filter_by(id=round_id).first()
                if round_obj:
                    return {"day": round_obj.day, "hour": round_obj.hour}
                return None
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting round info for {round_id}: {e}",
                extra={"extra_data": {"round_id": round_id, "error": str(e)}},
            )
            return None

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
            import uuid

            session = Session(self.engine)
            try:
                # Generate UUID if not provided
                website_id = website_data.get("id", str(uuid.uuid4()))

                # Check if website already exists by RSS URL
                rss = website_data.get("rss")
                if rss:
                    existing = session.query(Website).filter(Website.rss == rss).first()
                    if existing:
                        return existing.id

                # Create new website with all fields matching the model
                website = Website(
                    id=website_id,
                    name=website_data.get("name"),
                    rss=website_data.get("rss"),  # Model uses 'rss' not 'rss_url'
                    leaning=website_data.get("leaning"),
                    category=website_data.get("category"),
                    country=website_data.get("country"),
                    language=website_data.get("language"),
                    last_fetched=website_data.get("last_fetched", str(uuid.uuid4())),
                )
                session.add(website)
                session.commit()
                return website_id
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error adding website: {e}", extra={"extra_data": {"error": str(e)}})
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
                    row[0]
                    for row in session.query(Website.id).filter(Website.id.in_(website_ids)).all()
                }

            if rss_urls:
                existing_rss = {
                    row[0]
                    for row in session.query(Website.rss).filter(Website.rss.in_(rss_urls)).all()
                }

            # Filter out websites that already exist in database
            new_websites = [
                w
                for w in deduplicated
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
            import uuid

            session = Session(self.engine)
            try:
                article_id = article_data.get("id", str(uuid.uuid4()))

                # Article model fields: id, title, summary, website_id, fetched_on, link
                article = Article(
                    id=article_id,
                    title=article_data.get("title"),
                    summary=article_data.get("summary"),  # Model uses 'summary' not 'content'
                    website_id=article_data.get("website_id"),
                    fetched_on=article_data.get(
                        "fetched_on", str(uuid.uuid4())
                    ),  # Model uses 'fetched_on' not 'round_id'
                    link=article_data.get("link"),  # Model uses 'link' not 'url'
                )
                session.add(article)
                session.commit()
                return article_id
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error adding article: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get an article by ID."""
        try:
            session = Session(self.engine)
            try:
                article = session.query(Article).filter_by(id=article_id).first()
                if not article:
                    return None

                # Return dict with model field names
                return {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,  # Model uses 'summary' not 'content'
                    "website_id": article.website_id,
                    "fetched_on": article.fetched_on,  # Model uses 'fetched_on' not 'round_id'
                    "link": article.link,  # Model uses 'link' not 'url'
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
                # Model uses 'rss' not 'rss_url'
                website = session.query(Website).filter_by(rss=rss_url).first()
                if not website:
                    return None

                # Return dict with all model fields
                return {
                    "id": website.id,
                    "name": website.name,
                    "rss": website.rss,  # Model uses 'rss' not 'rss_url'
                    "leaning": website.leaning,
                    "category": website.category,
                    "country": website.country,
                    "language": website.language,
                    "last_fetched": website.last_fetched,
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
                topics = session.query(ArticleTopic.topic_id).filter_by(article_id=article_id).all()
                return [topic[0] for topic in topics]
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting article topics: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    @staticmethod
    def _round_slot_index(day: Any, hour: Any) -> Optional[int]:
        try:
            return int(day) * 24 + int(hour)
        except Exception:
            return None

    def select_page_article_for_sharing(
        self,
        website_id: str,
        current_round_id: str,
        feed_articles: List[Dict[str, Any]],
        cooldown_slots: int = 24,
    ) -> Optional[Dict[str, Any]]:
        """Select a feed or reusable article for a page according to cooldown rules."""
        try:
            session = Session(self.engine)
            try:
                current_round = session.query(Round).filter(Round.id == current_round_id).first()
                if not current_round:
                    return None

                current_slot_index = self._round_slot_index(current_round.day, current_round.hour)
                if current_slot_index is None:
                    return None

                posted_rows = (
                    session.query(
                        Article.id,
                        Article.title,
                        Article.summary,
                        Article.website_id,
                        Article.link,
                        Round.day,
                        Round.hour,
                    )
                    .join(Post, Post.news_id == Article.id)
                    .join(Round, Round.id == Post.round)
                    .filter(Article.website_id == website_id)
                    .all()
                )

                last_share_by_link: Dict[str, Dict[str, Any]] = {}
                for row in posted_rows:
                    link = (row.link or "").strip()
                    if not link:
                        continue
                    slot_index = self._round_slot_index(row.day, row.hour)
                    if slot_index is None:
                        continue
                    existing = last_share_by_link.get(link)
                    if existing is None or slot_index > existing["slot_index"]:
                        last_share_by_link[link] = {
                            "id": row.id,
                            "title": row.title,
                            "summary": row.summary,
                            "website_id": row.website_id,
                            "link": row.link,
                            "slot_index": slot_index,
                        }

                fresh_feed_articles: List[Dict[str, Any]] = []
                cooled_feed_articles: List[Dict[str, Any]] = []
                for article in feed_articles or []:
                    link = str(article.get("link") or "").strip()
                    if not link:
                        fresh_feed_articles.append(article)
                        continue
                    last_shared = last_share_by_link.get(link)
                    if last_shared is None:
                        fresh_feed_articles.append(article)
                        continue
                    if current_slot_index - last_shared["slot_index"] >= int(cooldown_slots):
                        cooled_feed_articles.append(article)

                if fresh_feed_articles:
                    return fresh_feed_articles[0]

                if cooled_feed_articles:
                    return cooled_feed_articles[0]

                reusable_articles = [
                    row
                    for row in last_share_by_link.values()
                    if current_slot_index - row["slot_index"] >= int(cooldown_slots)
                ]
                if not reusable_articles:
                    return None

                reusable_articles.sort(key=lambda row: row["slot_index"])
                selected = reusable_articles[0]
                return {
                    "title": selected.get("title"),
                    "summary": selected.get("summary"),
                    "website_id": selected.get("website_id"),
                    "link": selected.get("link"),
                    "image_urls": [],
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error selecting page article for sharing: {e}",
                extra={"extra_data": {"error": str(e), "website_id": website_id}},
            )
            return None

    def add_article_topic(self, article_id: str, topic_id: str) -> bool:
        """Add article topic association."""
        try:
            session = Session(self.engine)
            try:
                import uuid

                # Check if already exists
                existing = (
                    session.query(ArticleTopic)
                    .filter_by(article_id=article_id, topic_id=topic_id)
                    .first()
                )

                if existing:
                    return True  # Already exists

                # Create article topic record
                article_topic = ArticleTopic(
                    id=str(uuid.uuid4()), article_id=article_id, topic_id=topic_id
                )
                session.add(article_topic)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding article topic: {e}",
                extra={
                    "extra_data": {"error": str(e), "article_id": article_id, "topic_id": topic_id}
                },
            )
            return False


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
                    article_id=image_data.get("article_id"),
                )
                session.add(image)
                session.commit()
                return image_id
            finally:
                session.close()
        except Exception as e:
            self.logger.error(f"Error adding image: {e}", extra={"extra_data": {"error": str(e)}})
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

    def get_image_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get an image by its URL."""
        try:
            session = Session(self.engine)
            try:
                # Query for image with matching URL
                image = session.query(Image).filter(Image.url == url).first()
                if not image:
                    return None

                return {
                    "id": image.id,
                    "url": image.url,
                    "description": image.description,
                    "article_id": image.article_id,
                }
            finally:
                session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting image by URL: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None
