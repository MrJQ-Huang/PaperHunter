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

    return _parse_papers(data.get("data", []))


async def get_paper_references(paper_id: str, limit: int = 30) -> list[Paper]:
    """获取某篇论文的参考文献（它引用了谁）— 用于发现基础性工作"""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params = {
        "fields": FIELDS,
        "limit": min(limit, 50),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/paper/{paper_id}/references",
            params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    papers = []
    for item in data.get("data", []):
        cited = item.get("citedPaper", {})
        if cited and cited.get("title"):
            papers.append(cited)

    return _parse_papers(papers)


async def get_paper_citations(paper_id: str, limit: int = 30) -> list[Paper]:
    """获取引用了某篇论文的后续工作"""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params = {
        "fields": FIELDS,
        "limit": min(limit, 50),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/paper/{paper_id}/citations",
            params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    papers = []
    for item in data.get("data", []):
        citing = item.get("citingPaper", {})
        if citing and citing.get("title"):
            papers.append(citing)

    return _parse_papers(papers)


async def find_paper_by_title(title: str) -> str | None:
    """通过标题搜索论文，返回 Semantic Scholar paper ID"""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params = {
        "query": title,
        "limit": 3,
        "fields": "title,citationCount",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/paper/search", params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    results = data.get("data", [])
    if not results:
        return None

    # 找标题最相似的那个
    title_lower = title.lower().strip()
    best = None
    best_score = 0
    for r in results:
        r_title = (r.get("title") or "").lower().strip()
        # 简单相似度：共同单词数 / 较长标题的单词数
        words_a = set(title_lower.split())
        words_b = set(r_title.split())
        if not words_a or not words_b:
            continue
        overlap = len(words_a & words_b)
        score = overlap / max(len(words_a), len(words_b))
        if score > best_score:
            best_score = score
            best = r

    if best and best_score > 0.5:
        return best.get("paperId")
    return None


def _parse_papers(items: list) -> list[Paper]:
    """将 Semantic Scholar API 返回的 item 列表转为 Paper 列表"""
    papers = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        authors = [a.get("name", "") for a in item.get("authors", [])]
        ext_ids = item.get("externalIds", {}) or {}
        pdf_info = item.get("openAccessPdf")

        paper = Paper(
            id=str(uuid.uuid4()),
            title=title,
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
