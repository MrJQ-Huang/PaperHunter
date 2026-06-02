"""LLM 批量语义评分 — 用于 Filter Agent 第二阶段精排"""

import aiohttp
import json
from ..config import settings
from ..models.paper import Paper


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
    }
    """
    results = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        batch_result = await _score_batch(query, batch)
        results.extend(batch_result)

    return results


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

    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-17",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "system": """你是一个学术论文评审专家。你需要严格评估每篇论文是否与用户的研究主题直接相关。

评分标准：
- 9-10: 完全匹配，论文核心内容就是该主题
- 7-8: 高度相关，论文主要研究方向与主题一致
- 5-6: 部分相关，论文涉及主题的某个子方向或应用
- 3-4: 弱相关，论文只是略微提及或边缘涉及
- 0-2: 无关，论文与主题没有实质关联

重要：如果论文与研究主题没有直接关联，即使它在其他方面很优秀，也必须给低分。

返回 JSON 数组，每个元素包含:
- id: 论文 ID（原样返回）
- relevance: 0-10 的整数
- is_relevant: true（relevance>=5）或 false（relevance<5）
- reason: 一句话说明评分理由（15字以内）

只返回 JSON 数组，不要其他内容。""",
        "messages": [
            {
                "role": "user",
                "content": f"研究主题：{query}\n\n请评估以下论文的相关性：\n\n{papers_text}",
            }
        ],
    }

    url = f"{settings.llm_base_url}/v1/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    # LLM 调用失败，返回默认中等分数
                    return [
                        {
                            "paper_id": p.id,
                            "relevance": 5,
                            "is_relevant": True,
                            "reason": "LLM评分失败，默认通过",
                        }
                        for p in papers
                    ]
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        # 解析 JSON
        content = content.strip()
        # 尝试提取 JSON 数组（LLM 可能包裹在 markdown 代码块中）
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        scores = json.loads(content)

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
                    }
                )

        return result

    except Exception:
        # 解析失败，返回默认分数
        return [
            {
                "paper_id": p.id,
                "relevance": 5,
                "is_relevant": True,
                "reason": "评分解析失败",
            }
            for p in papers
        ]
