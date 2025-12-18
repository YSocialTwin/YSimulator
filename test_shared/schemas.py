from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AgentConfig:
    uuid: str
    name: str
    behavior_type: str
    status: str = "active"
    ip_address: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class ContentPost:
    agent_uuid: str
    iteration: int
    content_body: str

    def to_dict(self):
        return asdict(self)


@dataclass
class LikeAction:
    agent_uuid: str
    post_id: int
    iteration: int
    action_type: str  # "like" or "dislike"

    def to_dict(self):
        return asdict(self)