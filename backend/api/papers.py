from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from ..database import (
    get_paper, get_papers, update_paper_download, update_paper,
    delete_paper, delete_all_papers, count_papers,
)
from ..config import settings

router = APIRouter()


class UpdatePaperRequest(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    citation_count: int | None = None
    is_open_access: bool | None = None
    relevance_score: float | None = None


@router.get("/papers")
async def list_papers(
    task_id: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("relevance", pattern="^(relevance|date)$"),
    search: str | None = None,
):
    papers, total = await get_papers(task_id, page, per_page, sort, search)
    return {
        "papers": [p.model_dump() for p in papers],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.delete("/papers")
async def clear_papers(task_id: str | None = None):
    """清空论文（可按 task_id 过滤）"""
    papers, _ = await get_papers(task_id=task_id, page=1, per_page=10000)
    for p in papers:
        if p.local_pdf_path:
            path = Path(p.local_pdf_path)
            if path.exists():
                path.unlink()
    await delete_all_papers(task_id)
    return {"message": "All papers deleted", "count": len(papers)}


@router.get("/papers/stats/overview")
async def papers_stats():
    total = await count_papers()
    return {"total": total}


@router.get("/papers/{paper_id}")
async def get_paper_detail(paper_id: str):
    paper = await get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper.model_dump()


@router.put("/papers/{paper_id}")
async def update_paper_info(paper_id: str, req: UpdatePaperRequest):
    paper = await get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.authors is not None:
        import json
        updates["authors"] = json.dumps(req.authors)
    if req.abstract is not None:
        updates["abstract"] = req.abstract
    if req.doi is not None:
        updates["doi"] = req.doi
    if req.url is not None:
        updates["url"] = req.url
    if req.pdf_url is not None:
        updates["pdf_url"] = req.pdf_url
    if req.venue is not None:
        updates["venue"] = req.venue
    if req.citation_count is not None:
        updates["citation_count"] = req.citation_count
    if req.is_open_access is not None:
        updates["is_open_access"] = req.is_open_access
    if req.relevance_score is not None:
        updates["relevance_score"] = req.relevance_score

    if updates:
        await update_paper(paper_id, **updates)

    updated = await get_paper(paper_id)
    return updated.model_dump()


@router.post("/papers/{paper_id}/download")
async def trigger_download(paper_id: str):
    paper = await get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {"message": "Download triggered", "paper_id": paper_id}


@router.get("/papers/{paper_id}/pdf")
async def get_pdf(paper_id: str):
    paper = await get_paper(paper_id)
    if not paper or not paper.local_pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    path = Path(paper.local_pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.delete("/papers/{paper_id}")
async def remove_paper(paper_id: str):
    paper = await get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.local_pdf_path:
        path = Path(paper.local_pdf_path)
        if path.exists():
            path.unlink()
    await delete_paper(paper_id)
    return {"message": "Paper deleted"}
