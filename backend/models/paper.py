from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class PaperSource(str, Enum):
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX = "openalex"
    CROSSREF = "crossref"
    GOOGLE_SCHOLAR = "google_scholar"


class Paper(BaseModel):
    id: str
    title: str
    authors: list[str] = []
    abstract: str = ""
    doi: str | None = None
    url: str = ""
    pdf_url: str | None = None
    source: PaperSource
    published_date: datetime | None = None
    citation_count: int | None = None
    venue: str | None = None
    is_open_access: bool = False
    topics: list[str] = []
    paper_type: str | None = None
    subtopics: list[str] = []
    learning_role: str | None = None
    difficulty: str | None = None
    method_tags: list[str] = []
    quality_tags: list[str] = []
    annotation_reason: str | None = None
    search_subtopic: str | None = None
    local_pdf_path: str | None = None
    download_status: str = "pending"
    relevance_score: float | None = None
    created_at: datetime = datetime.now()
    task_id: str | None = None
