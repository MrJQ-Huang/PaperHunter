import aiohttp
import uuid
from datetime import datetime

from ..models.paper import Paper, PaperSource


async def search_crossref(query: str, rows: int = 50) -> list[Paper]:
    params = {
        "query": query,
        "rows": min(rows, 100),
        "sort": "relevance",
        "order": "desc",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.crossref.org/works",
            params=params,
            headers={"User-Agent": "PaperHunter/0.1 (mailto:researcher@example.com)"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    papers = []
    for item in data.get("message", {}).get("items", []):
        title_parts = item.get("title", [])
        title = title_parts[0].strip() if title_parts else ""
        if not title:
            continue

        # 作者
        authors = []
        for auth in item.get("author", []):
            name_parts = []
            if auth.get("given"):
                name_parts.append(auth["given"])
            if auth.get("family"):
                name_parts.append(auth["family"])
            if name_parts:
                authors.append(" ".join(name_parts))

        # 日期
        pub_date = None
        date_parts = item.get("published-print", item.get("published-online", {}))
        if date_parts:
            parts = date_parts.get("date-parts", [[]])[0]
            if parts and len(parts) >= 1:
                year = parts[0]
                month = parts[1] if len(parts) > 1 else 1
                day = parts[2] if len(parts) > 2 else 1
                try:
                    pub_date = datetime(year, month, day)
                except (ValueError, TypeError):
                    pub_date = datetime(year, 1, 1)

        # 期刊
        venue_parts = item.get("container-title", [])
        venue = venue_parts[0] if venue_parts else None

        # PDF 链接
        pdf_url = None
        for link in item.get("link", []):
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL")
                break

        # OA 状态
        is_oa = False
        license_list = item.get("license", [])
        for lic in license_list:
            if "creativecommons" in (lic.get("URL") or ""):
                is_oa = True
                break

        paper = Paper(
            id=str(uuid.uuid4()),
            title=title,
            authors=authors,
            abstract=(item.get("abstract") or "").strip(),
            doi=item.get("DOI"),
            url=item.get("URL", ""),
            pdf_url=pdf_url,
            source=PaperSource.CROSSREF,
            published_date=pub_date,
            citation_count=item.get("is-referenced-by-count"),
            venue=venue,
            is_open_access=is_oa,
            created_at=datetime.now(),
        )
        papers.append(paper)

    return papers
