# models.py
from dataclasses import dataclass, field
from typing import List, Literal, Optional
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# --- Database Schema ---
class User_mgmt(Base):
    """
    User management model for experiment participants.
    
    Stores user profile information including personality traits (Big Five),
    demographic information, preferences, and activity settings. Used in
    experimental simulations to represent both human and AI-driven agents.
    """
    __tablename__ = 'user_mgmt'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(15), nullable=False, unique=True)
    email = Column(String(50), nullable=True, default="")
    password = Column(String(80), nullable=False)
    leaning = Column(String(10), default="neutral")
    user_type = Column(String(10), nullable=False, default="user")
    age = Column(Integer, default=0)
    # Big Five personality traits
    oe = Column(String(50))  # Openness to Experience
    co = Column(String(50))  # Conscientiousness
    ex = Column(String(50))  # Extraversion
    ag = Column(String(50))  # Agreeableness
    ne = Column(String(50))  # Neuroticism
    recsys_type = Column(String(50), default="default")
    frecsys_type = Column(String(50), default="default")
    language = Column(String(10), default="en")
    owner = Column(String(10), default=None)
    education_level = Column(String(10), default=None)
    joined_on = Column(Integer, nullable=False)
    gender = Column(String(10), default=None)
    nationality = Column(String(15), default=None)
    round_actions = Column(Integer, default=3)
    toxicity = Column(String(10), default="no")
    is_page = Column(Integer, default=0)
    left_on = Column(Integer, default=None)
    daily_activity_level = Column(Integer, default=1)
    profession = Column(String(50), default="")
    activity_profile = Column(String(50), default="Always On")
    archetype = Column(String(50), nullable=True, default=None)

class PostModel(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer)
    cluster_id = Column(Integer)
    content = Column(String)
    day = Column(Integer)
    slot = Column(Integer)

class InteractionModel(Base):
    __tablename__ = 'interactions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer)
    post_id = Column(Integer)
    type = Column(String)
    content = Column(String, nullable=True)

# --- Ray Data Objects ---
@dataclass
class AgentProfile:
    """
    Agent profile data class for passing agent information between Ray actors.
    Maps to User_mgmt database model.
    """
    id: int
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
    agent_id: int
    cluster_id: int
    action_type: Literal['POST', 'LIKE', 'COMMENT']
    content: Optional[str] = None
    target_post_id: Optional[int] = None

@dataclass
class SimulationInstruction:
    status: Literal['WAIT', 'PROCEED']
    day: int = 0
    slot: int = 0
    recent_post_ids: List[int] = None