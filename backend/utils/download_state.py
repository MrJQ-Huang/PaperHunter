from pathlib import Path

from ..database import get_papers, update_paper_download


async def sync_download_file_state(paper):
    if paper and paper.download_status == "done":
        if not paper.local_pdf_path or not Path(paper.local_pdf_path).exists():
            paper.local_pdf_path = None
            paper.download_status = "pending"
            await update_paper_download(paper.id, None, "pending")
    return paper


async def sync_download_file_states(papers):
    return [await sync_download_file_state(p) for p in papers]


async def sync_download_file_state_for_scope(task_id: str | None = None) -> None:
    papers, _ = await get_papers(task_id=task_id, per_page=10000, download_status="downloaded")
    await sync_download_file_states(papers)
