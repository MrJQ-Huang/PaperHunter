import aiohttp
import uuid
from datetime import datetime

from ..models.paper import Paper, PaperSource
from ..config import settings

BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,authors,abstract,externalIds,url,openAccessPdf,publicationDate,citationCount,venue"


async def search_semantic_scholar(query: str, limit: int = 50) -> list[Paper]:
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": FIELDS,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/paper/search", params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    papers = []
    for item in data.get("data", []):
        authors = [a.get("name", "") for a in item.get("authors", [])]
        ext_ids = item.get("externalIds", {}) or {}
        pdf_info = item.get("openAccessPdf")

        paper = Paper(
            id=str(uuid.uuid4()),
            title=(item.get("title") or "").strip(),
            authors=authors,
            abstract=(item.get("abstract") or "").strip(),
            doi=ext_ids.get("DOI"),
            url=item.get("url", ""),
            pdf_url=pdf_info.get("url") if pdf_info else None,
            source=PaperSource.SEMANTIC_SCHOLAR,
            published_date=_parse_date(item.get("publicationDate")),
            citation_count=item.get("citationCount"),
            venue=item.get("venue"),
            is_open_access=pdf_info is not None,
            created_at=datetime.now(),
        )
        papers.append(paper)

    return papers


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
