# models.py
from dataclasses import dataclass
from typing import List, Literal, Optional
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# --- Database Schema ---
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