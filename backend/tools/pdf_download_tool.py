import aiohttp
import asyncio
from pathlib import Path
import re

from ..models.paper import Paper
from ..config import settings


async def download_pdf(paper: Paper, task_name: str | None = None) -> tuple[str | None, str | None]:
    """
    尝试下载论文 PDF。
    返回 (local_path, error_message)。
    成功时 error_message 为 None，失败时 local_path 为 None。
    """
    # 按优先级尝试不同来源
    urls = _get_download_urls(paper)

    for url in urls:
        local_path, error = await _try_download(url, paper, task_name)
        if local_path:
            return local_path, None

    return None, "所有下载源均失败"


def _get_download_urls(paper: Paper) -> list[str]:
    """按优先级排列下载 URL"""
    urls = []

    # 1. arXiv 直链
    if paper.source.value == "arxiv" and paper.pdf_url:
        urls.append(paper.pdf_url)

    # 2. 已知 PDF 链接
    if paper.pdf_url and paper.pdf_url not in urls:
        urls.append(paper.pdf_url)

    # 3. Unpaywall API
    if paper.doi:
        urls.append(f"https://api.unpaywall.org/v2/{paper.doi}?email={settings.unpaywall_email}")

    # 4. DOI 直链尝试
    if paper.doi:
        urls.append(f"https://doi.org/{paper.doi}")

    return urls


async def _try_download(url: str, paper: Paper, task_name: str | None = None) -> tuple[str | None, str | None]:
    """尝试从单个 URL 下载"""
    # 如果是 Unpaywall API URL，先查询再下载
    if "unpaywall.org" in url:
        return await _download_via_unpaywall(url, paper, task_name)

    return await _download_file(url, paper, task_name)


async def _download_via_unpaywall(api_url: str, paper: Paper, task_name: str | None = None) -> tuple[str | None, str | None]:
    """通过 Unpaywall API 查找 OA 版本并下载"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None, "Unpaywall API 请求失败"
                data = await resp.json()

        # 查找最佳 OA 链接
        best_oa = data.get("best_oa_location", {})
        if not best_oa:
            return None, "Unpaywall 未找到 OA 版本"

        pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
        if not pdf_url:
            return None, "Unpaywall 无 PDF 链接"

        return await _download_file(pdf_url, paper, task_name)

    except Exception as e:
        return None, f"Unpaywall 查询异常: {str(e)}"


async def _download_file(url: str, paper: Paper, task_name: str | None = None) -> tuple[str | None, str | None]:
    """下载文件并验证为 PDF"""
    try:
        # 代理配置
        proxy = settings.proxy_url if settings.proxy_url else None

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"User-Agent": "PaperHunter/0.1"},
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return None, f"HTTP {resp.status}"

                content = await resp.read()

                # 验证 PDF
                if not content.startswith(b"%PDF"):
                    return None, "非 PDF 文件"

                # 保存文件
                local_path = _build_path(paper, task_name)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content)

                return str(local_path), None

    except asyncio.TimeoutError:
        return None, "下载超时"
    except Exception as e:
        return None, f"下载异常: {str(e)}"


def _build_path(paper: Paper, task_name: str | None = None) -> Path:
    """Build local PDF path: {task_name}/{author}_{year}_{title}_{paper_id}.pdf."""
    task_dir = _safe_path_part(task_name or (paper.topics[0] if paper.topics else "general"), "general", max_len=80)

    author = paper.authors[0].split()[-1] if paper.authors else "unknown"
    author = _safe_path_part(author, "unknown", max_len=40)

    year = str(paper.published_date.year) if paper.published_date else "unknown"

    title_slug = _safe_path_part(paper.title[:60], "paper", max_len=80)

    paper_id = _safe_path_part(paper.id[:8], "paper", max_len=12)
    filename = f"{author}_{year}_{title_slug}_{paper_id}.pdf"
    return Path(settings.download_dir) / task_dir / filename


def _safe_path_part(value: str, fallback: str, max_len: int = 80) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "")
    value = re.sub(r"\s+", "_", value).strip("._ ")
    value = re.sub(r"_+", "_", value)
    return (value[:max_len].strip("._ ") or fallback)
