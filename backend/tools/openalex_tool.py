import aiohttp
import uuid
from datetime import datetime

from ..models.paper import Paper, PaperSource


async def search_openalex(query: str, per_page: int = 50) -> list[Paper]:
    params = {
        "search": query,
        "per_page": min(per_page, 100),
        "sort": "relevance_score:desc",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.openalex.org/works",
            params=params,
            headers={"User-Agent": "PaperHunter/0.1 (mailto:researcher@example.com)"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    papers = []
    for item in data.get("results", []):
        title = (item.get("title") or "").strip()
        if not title:
            continue

        authors = []
        for auth in item.get("authorships", []):
            name = auth.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        # 发表日期
        pub_date = None
        pub_year = item.get("publication_year")
        if pub_year:
            pub_date = datetime(pub_year, 1, 1)

        # PDF 链接
        pdf_url = None
        oa = item.get("open_access", {})
        if oa.get("oa_url"):
            pdf_url = oa["oa_url"]

        # 来源/期刊
        venue = None
        source_info = item.get("primary_location", {})
        if source_info and source_info.get("source"):
            venue = source_info["source"].get("display_name")

        paper = Paper(
            id=str(uuid.uuid4()),
            title=title,
            authors=authors,
            abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
            doi=item.get("doi", "").replace("https://doi.org/", "") if item.get("doi") else None,
            url=item.get("id", ""),
            pdf_url=pdf_url,
            source=PaperSource.OPENALEX,
            published_date=pub_date,
            citation_count=item.get("cited_by_count"),
            venue=venue,
            is_open_access=oa.get("is_oa", False),
            created_at=datetime.now(),
        )
        papers.append(paper)

    return papers


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    # OpenAlex 用反转索引存储摘要，需要重建
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)
