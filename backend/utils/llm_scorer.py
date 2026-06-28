"""LLM 批量语义评分 — 用于 Filter Agent 第二阶段精排"""

import asyncio
import json
import logging
import re
from ..models.paper import Paper
from .llm_client import call_llm


async def llm_score_papers(
    query: str,
    papers: list[Paper],
    batch_size: int = 10,
) -> list[dict]:
    """批量调用 LLM 评估论文与研究主题的语义相关性。

    返回列表，每个元素：
    {
        "paper_id": str,
        "relevance": int,       # 0-10
        "is_relevant": bool,    # 是否与主题直接相关
        "reason": str,          # 一句话理由
        "paper_type": str,
        "learning_role": str,
        "difficulty": str,
        "subtopics": list[str],
        "method_tags": list[str],
        "quality_tags": list[str],
    }
    """
    semaphore = asyncio.Semaphore(3)

    async def score_limited(batch: list[Paper]) -> list[dict]:
        async with semaphore:
            return await _score_batch(query, batch)

    batches = []
    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        batches.append(batch)

    gathered = await asyncio.gather(
        *(score_limited(batch) for batch in batches),
        return_exceptions=True,
    )

    results = []
    for batch, batch_result in zip(batches, gathered):
        if isinstance(batch_result, Exception):
            results.extend(_default_scores(batch, "评分调用失败"))
        else:
            results.extend(batch_result)
    return results


def _default_scores(papers: list[Paper], reason: str, relevance: int = 2) -> list[dict]:
    return [
        {
            "paper_id": p.id,
            "relevance": relevance,
            "is_relevant": relevance >= 5,
            "reason": reason,
            "paper_type": "unknown",
            "learning_role": "niche_detail",
            "difficulty": "intermediate",
            "subtopics": p.subtopics,
            "method_tags": [],
            "quality_tags": [],
        }
        for p in papers
    ]


async def _score_batch(query: str, papers: list[Paper]) -> list[dict]:
    """对一批论文（≤10篇）调用 LLM 评分"""

    # 构造论文列表文本
    paper_lines = []
    for idx, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:3]) if p.authors else "未知"
        abstract = (p.abstract or "")[:300]
        paper_lines.append(
            f"{idx}. [ID:{p.id}] {p.title}\n"
            f"   作者: {authors}\n"
            f"   摘要: {abstract}"
        )
    papers_text = "\n\n".join(paper_lines)

    system = """你是一个学术论文评审专家。你需要严格评估每篇论文是否与用户的研究主题直接相关。

评分标准：
- 9-10: 完全匹配，论文核心内容就是该主题
- 7-8: 高度相关，论文主要研究方向与主题一致
- 5-6: 部分相关，论文涉及主题的某个子方向或应用
- 3-4: 弱相关，论文只是略微提及或边缘涉及
- 0-2: 无关，论文与主题没有实质关联

重要：如果论文与研究主题没有直接关联，即使它在其他方面很优秀，也必须给低分。

同时请给论文做入库标注，便于用户筛选和学习路径构建。

返回 JSON 数组，每个元素包含:
- id: 论文 ID（原样返回）
- relevance: 0-10 的整数
- is_relevant: true（relevance>=5）或 false（relevance<5）
- reason: 一句话说明评分理由（15字以内）
- paper_type: survey | benchmark | dataset | method | system | application | theory | unknown
- learning_role: field_overview | foundation | representative_method | recent_frontier | benchmark_or_dataset | implementation_reference | niche_detail
- difficulty: beginner | intermediate | advanced
- subtopics: 1-3 个英文子方向标签
- method_tags: 1-5 个英文方法/技术标签
- quality_tags: 0-4 个质量标签，如 highly_cited, top_venue, open_access, benchmark, open_source, recent

只返回 JSON 数组，不要其他内容。"""

    try:
        content = await call_llm(
            [{"role": "user", "content": f"研究主题：{query}\n\n请评估以下论文的相关性：\n\n{papers_text}"}],
            system=system,
            max_tokens=2048,
            timeout=30,
        )

        scores = _parse_score_response(content)

        # 构建 ID 到论文的映射
        id_map = {p.id: p for p in papers}
        result = []
        for item in scores:
            pid = item.get("id", "")
            if pid in id_map:
                result.append(
                    {
                        "paper_id": pid,
                        "relevance": min(10, max(0, int(item.get("relevance", 5)))),
                        "is_relevant": bool(item.get("is_relevant", True)),
                        "reason": str(item.get("reason", "")),
                        "paper_type": str(item.get("paper_type", "unknown")),
                        "learning_role": str(item.get("learning_role", "niche_detail")),
                        "difficulty": str(item.get("difficulty", "intermediate")),
                        "subtopics": _as_str_list(item.get("subtopics", []))[:3],
                        "method_tags": _as_str_list(item.get("method_tags", []))[:5],
                        "quality_tags": _as_str_list(item.get("quality_tags", []))[:4],
                    }
                )

        # 补充 LLM 未返回的论文
        scored_ids = {r["paper_id"] for r in result}
        for p in papers:
            if p.id not in scored_ids:
                result.append(
                    {
                        "paper_id": p.id,
                        "relevance": 5,
                        "is_relevant": True,
                        "reason": "未获评分",
                        "paper_type": "unknown",
                        "learning_role": "niche_detail",
                        "difficulty": "intermediate",
                        "subtopics": p.subtopics,
                        "method_tags": [],
                        "quality_tags": [],
                    }
                )

        return result

    except Exception as e:
        logging.warning("LLM score parse failed: %s", e)
        # 解析失败，返回默认分数
        return _default_scores(papers, "评分解析失败")


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _parse_score_response(content: str) -> list[dict]:
    """Parse score JSON from models that may wrap strict JSON in prose/code fences."""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty score response")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    candidates = [text]
    array_text = _extract_balanced(text, "[", "]")
    if array_text and array_text not in candidates:
        candidates.append(array_text)
    object_text = _extract_balanced(text, "{", "}")
    if object_text and object_text not in candidates:
        candidates.append(object_text)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(_strip_json_comments(candidate))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                for key in ("scores", "results", "papers", "items", "data"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return [item for item in value if isinstance(item, dict)]
        except Exception as e:
            last_error = e

    raise ValueError(f"unable to parse score JSON: {last_error}; preview={text[:200]}")


def _extract_balanced(text: str, open_char: str, close_char: str) -> str | None:
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def _strip_json_comments(text: str) -> str:
    # Conservative cleanup for common LLM artifacts.
    text = text.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text
