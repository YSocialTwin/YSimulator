from dataclasses import dataclass
from typing import Literal, Optional, List


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