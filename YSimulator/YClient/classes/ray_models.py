from dataclasses import dataclass
from typing import Literal, Optional, List


@dataclass
class AgentProfile:
    """
    Agent profile data class for passing agent information between Ray actors.
    Maps to User_mgmt database model.
    """
    id: str
    username: str
    email: str = ""
    password: str = "default_password"
    leaning: str = "neutral"
    user_type: str = "user"
    age: int = 0
    # Big Five personality traits
    oe: Optional[str] = None  # Openness to Experience
    co: Optional[str] = None  # Conscientiousness
    ex: Optional[str] = None  # Extraversion
    ag: Optional[str] = None  # Agreeableness
    ne: Optional[str] = None  # Neuroticism
    recsys_type: str = "default"
    frecsys_type: str = "default"
    language: str = "en"
    owner: Optional[str] = None
    education_level: Optional[str] = None
    joined_on: int = 0
    gender: Optional[str] = None
    nationality: Optional[str] = None
    round_actions: int = 3
    toxicity: str = "no"
    is_page: int = 0
    left_on: Optional[int] = None
    daily_activity_level: int = 1
    profession: str = ""
    activity_profile: str = "Always On"
    archetype: Optional[str] = None
    # Simulation-specific fields
    cluster: int = 0
    llm: bool = False


@dataclass
class ActionDTO:
    """Action data transfer object for agent actions."""
    agent_id: str
    cluster_id: int
    action_type: Literal['POST', 'LIKE', 'COMMENT']
    content: Optional[str] = None
    target_post_id: Optional[str] = None  # UUID string


@dataclass
class SimulationInstruction:
    """
    Instruction from server to client for simulation coordination.
    
    Server provides current state (day/slot) and coordination status.
    Client handles its own progress tracking and completion logic.
    """
    status: Literal['WAIT', 'PROCEED']  # COMPLETE removed - client handles completion
    day: int = 0
    slot: int = 0
    recent_post_ids: List[str] = None  # UUID strings


# ================================================
# SOCIAL ACTION DTOs (UUID-based)
# ================================================


@dataclass
class FollowDTO:
    """Follow/unfollow action between users."""
    id: str  # UUID
    user_id: str
    follower_id: str
    action: str  # 'follow' or 'unfollow'
    round: str


@dataclass
class ReactionDTO:
    """User reaction to a post (like, love, laugh, etc.)."""
    id: str  # UUID
    user_id: int
    post_id: str  # Post UUID
    type: str  # Reaction type (like, love, laugh, angry, sad, etc.)
    round: str


@dataclass
class MentionDTO:
    """User mention in a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    user_id: str
    round: str
    answered: int = 0


@dataclass
class RecommendationDTO:
    """Content recommendation for a user."""
    id: str  # UUID
    user_id: int
    post_ids: str  # Comma-separated or JSON list of post UUIDs
    round: str


@dataclass
class VotingDTO:
    """User voting/preference data."""
    vid: str  # UUID (primary key)
    user_id: str
    preference: str
    content_type: str
    content_id: str
    round: str


@dataclass
class UserInterestDTO:
    """User interest association."""
    id: str  # UUID
    user_id: str
    interest_id: str
    round_id: str


# ================================================
# CONTENT METADATA DTOs
# ================================================


@dataclass
class PostEmotionDTO:
    """Emotional tag for a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    emotion_id: str


@dataclass
class PostHashtagDTO:
    """Hashtag association for a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    hashtag_id: str


@dataclass
class PostSentimentDTO:
    """Sentiment analysis data for a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    user_id: str
    topic_id: str
    round: str
    neg: Optional[float] = None
    pos: Optional[float] = None
    neu: Optional[float] = None
    compound: Optional[float] = None
    sentiment_parent: Optional[str] = None
    is_post: int = 0
    is_comment: int = 0
    is_reaction: int = 0


@dataclass
class PostTopicDTO:
    """Topic association for a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    topic_id: str


@dataclass
class PostToxicityDTO:
    """Toxicity analysis data for a post."""
    id: str  # UUID
    post_id: str  # Post UUID
    toxicity: float = 0.0
    severe_toxicity: float = 0.0
    identity_attack: float = 0.0
    insult: float = 0.0
    profanity: float = 0.0
    threat: float = 0.0
    sexually_explicit: float = 0.0
    flirtation: float = 0.0