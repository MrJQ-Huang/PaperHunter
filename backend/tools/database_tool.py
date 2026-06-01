from ..database import insert_paper, insert_papers, get_paper, get_papers, update_paper_download


async def save_paper(paper):
    await insert_paper(paper)


async def save_papers(papers: list):
    await insert_papers(papers)


async def query_paper(paper_id: str):
    return await get_paper(paper_id)


async def query_papers(task_id: str | None = None, page: int = 1, per_page: int = 20, sort: str = "relevance"):
    return await get_papers(task_id, page, per_page, sort)


async def mark_downloaded(paper_id: str, local_path: str):
    await update_paper_download(paper_id, local_path, "done")


async def mark_failed(paper_id: str):
    await update_paper_download(paper_id, None, "failed")
