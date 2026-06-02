from pydantic import BaseModel
from datetime import datetime
from enum import Enum

from .paper import PaperSource


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEWING = "reviewing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    id: str
    query: str
    sources: list[PaperSource] = []
    filters: dict = {}
    status: TaskStatus = TaskStatus.PENDING
    total_papers_found: int = 0
    papers_after_filter: int = 0
    papers_downloaded: int = 0
    papers_failed: int = 0
    search_plan: dict | None = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    error_message: str | None = None
