import re
from difflib import SequenceMatcher

from ..models.paper import Paper


def normalize_title(title: str) -> str:
    """标题规范化：小写、去标点、去多余空格"""
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title


def _title_similarity(t1: str, t2: str) -> float:
    """计算两个标题的相似度"""
    return SequenceMatcher(None, t1, t2).ratio()


def _first_author(paper: Paper) -> str:
    """获取第一作者姓氏（小写）"""
    if not paper.authors:
        return ""
    name = paper.authors[0].split()[-1].lower()
    return re.sub(r'[^\w]', '', name)


def merge_paper(existing: Paper, new: Paper):
    """将新论文的元数据合并到已有论文中"""
    # 保留更完整的摘要
    if not existing.abstract and new.abstract:
        existing.abstract = new.abstract

    # 补充 DOI
    if not existing.doi and new.doi:
        existing.doi = new.doi

    # 补充 PDF 链接
    if not existing.pdf_url and new.pdf_url:
        existing.pdf_url = new.pdf_url

    # 保留更高的引用数
    if new.citation_count is not None:
        if existing.citation_count is None or new.citation_count > existing.citation_count:
            existing.citation_count = new.citation_count

    # 补充期刊信息
    if not existing.venue and new.venue:
        existing.venue = new.venue

    # 合并来源（标记为多源验证）
    if existing.source.value != new.source.value:
        if new.source.value not in existing.topics:
            existing.topics.append(f"also_from:{new.source.value}")

    for subtopic in new.subtopics:
        if subtopic and subtopic not in existing.subtopics:
            existing.subtopics.append(subtopic)
    if not existing.search_subtopic and new.search_subtopic:
        existing.search_subtopic = new.search_subtopic
    for tag in new.method_tags:
        if tag and tag not in existing.method_tags:
            existing.method_tags.append(tag)
    for tag in new.quality_tags:
        if tag and tag not in existing.quality_tags:
            existing.quality_tags.append(tag)

    # 更新 OA 状态
    if new.is_open_access and not existing.is_open_access:
        existing.is_open_access = True


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """
    三优先级去重：
    1. DOI 精确匹配
    2. 标题规范化匹配
    3. 模糊标题匹配（相似度 > 0.92）+ 第一作者匹配
    """
    seen_doi: dict[str, int] = {}
    seen_title: dict[str, int] = {}
    result: list[Paper] = []

    for paper in papers:
        # 优先级 1: DOI 匹配
        if paper.doi and paper.doi in seen_doi:
            merge_paper(result[seen_doi[paper.doi]], paper)
            continue

        # 优先级 2: 标题规范化匹配
        norm_title = normalize_title(paper.title)
        if norm_title in seen_title:
            merge_paper(result[seen_title[norm_title]], paper)
            continue

        # 优先级 3: 模糊匹配
        matched = False
        first_author = _first_author(paper)
        for idx, existing in enumerate(result):
            existing_norm = normalize_title(existing.title)
            sim = _title_similarity(norm_title, existing_norm)
            if sim > 0.92 and first_author and first_author == _first_author(existing):
                merge_paper(existing, paper)
                matched = True
                break

        if matched:
            continue

        # 新论文
        if paper.doi:
            seen_doi[paper.doi] = len(result)
        seen_title[norm_title] = len(result)
        result.append(paper)

    return result
