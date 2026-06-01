from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Message(BaseModel):
    id: str
    task_id: str
    role: MessageRole
    content: str
    suggestions: list[str] = []
    timestamp: datetime = datetime.now()
    agent_name: str | None = None
