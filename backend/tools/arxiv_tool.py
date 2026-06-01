import arxiv
import uuid
from datetime import datetime

from ..models.paper import Paper, PaperSource


async def search_arxiv(query: str, max_results: int = 50) -> list[Paper]:
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    papers = []
    for result in client.results(search):
        paper = Paper(
            id=str(uuid.uuid4()),
            title=result.title.strip().replace("\n", " "),
            authors=[a.name for a in result.authors],
            abstract=result.summary.strip(),
            doi=result.entry_id,
            url=result.entry_id,
            pdf_url=result.pdf_url,
            source=PaperSource.ARXIV,
            published_date=result.published,
            citation_count=None,
            venue=result.primary_category,
            is_open_access=True,
            topics=[t.lower() for t in result.categories],
            created_at=datetime.now(),
        )
        papers.append(paper)

    return papers
