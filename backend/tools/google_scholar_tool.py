import uuid
import asyncio
import random
from datetime import datetime

from ..models.paper import Paper, PaperSource
from ..config import settings


async def search_google_scholar(query: str, max_results: int = 20) -> list[Paper]:
    """使用 scholarly 库搜索 Google Scholar（同步包装为异步）"""
    try:
        from scholarly import scholarly
    except ImportError:
        return []

    # scholarly 是同步的，放到线程池执行
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search_sync, query, max_results)


def _search_sync(query: str, max_results: int) -> list[Paper]:
    from scholarly import scholarly

    papers = []
    search_results = scholarly.search_pubs(query)

    for i, result in enumerate(search_results):
        if i >= max_results:
            break

        bib = result.get("bib", {})
        title = bib.get("title", "").strip()
        if not title:
            continue

        # 随机延迟避免被封
        if i > 0:
            delay = random.uniform(settings.google_scholar_delay_min, settings.google_scholar_delay_max)
            import time
            time.sleep(delay)

        authors = bib.get("author", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(" and ")]

        pub_year = bib.get("pub_year")
        pub_date = None
        if pub_year:
            try:
                pub_date = datetime(int(pub_year), 1, 1)
            except (ValueError, TypeError):
                pass

        paper = Paper(
            id=str(uuid.uuid4()),
            title=title,
            authors=authors,
            abstract=bib.get("abstract", ""),
            doi=result.get("pub_id"),
            url=result.get("pub_url", ""),
            pdf_url=result.get("eprint_url"),
            source=PaperSource.GOOGLE_SCHOLAR,
            published_date=pub_date,
            citation_count=result.get("num_citations"),
            venue=bib.get("venue"),
            is_open_access=bool(result.get("eprint_url")),
            created_at=datetime.now(),
        )
        papers.append(paper)

    return papers
