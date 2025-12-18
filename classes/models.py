from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


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

