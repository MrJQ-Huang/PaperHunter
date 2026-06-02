import aiohttp
import json
from ..config import settings


async def translate_query(chinese_query: str) -> str:
    """将中文研究需求翻译为英文检索词"""
    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 256,
        "system": "你是学术搜索助手。将用户的中文研究需求翻译为适合学术数据库检索的英文关键词。只输出英文检索词，不要解释。用 AND/OR 组合多个关键词，保持简洁精准。",
        "messages": [
            {"role": "user", "content": f"翻译为英文检索词：{chinese_query}"}
        ],
    }

    url = f"{settings.llm_base_url}/v1/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return chinese_query
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        translated = content.strip().strip('"').strip("'")
        return translated if translated else chinese_query

    except Exception:
        return chinese_query


async def generate_search_plan(query: str) -> dict:
    """LLM 分析研究意图，生成结构化搜索方案。

    返回：
    {
        "core_concepts": ["vision language action", "VLA"],
        "field_terms": ["embodied AI", "robot manipulation", "policy learning", ...],
        "queries": {
            "arxiv": "...",
            "semantic_scholar": "...",
            "openalex": "...",
            "crossref": "..."
        }
    }
    """
    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "system": """你是一个学术搜索策略专家。根据用户的研究主题，生成精准的搜索方案。

你必须返回纯 JSON，格式如下：
{
  "core_concepts": ["核心概念1", "核心概念2"],
  "field_terms": ["领域术语1", "领域术语2", ...],
  "queries": {
    "arxiv": "arXiv格式的布尔查询",
    "semantic_scholar": "自然语言查询",
    "openalex": "简洁关键词查询",
    "crossref": "简洁关键词查询"
  }
}

字段说明：
- core_concepts: 该领域最核心的 2-3 个概念词，论文中大概率会包含这些词（如 "vision language action"、"robot"）
- field_terms: 该领域论文中自然会出现的术语，即使论文标题不含核心概念，摘要也会包含这些词
  例如 VLA 领域的 field_terms: ["embodied AI", "robot manipulation", "policy learning", "end-to-end control", "foundation model", "imitation learning", "visual grounding"]
  这些词不是核心概念的同义词，而是该领域论文必然会使用的术语

规则：
1. core_concepts 中的词必须出现在每个 queries 中
2. arXiv 支持 AND/OR 布尔语法，其他用空格分隔
3. field_terms 要尽量全面（5-10 个），覆盖该领域的不同表述
4. 只返回 JSON，不要其他内容""",
        "messages": [
            {"role": "user", "content": f"研究主题：{query}"}
        ],
    }

    url = f"{settings.llm_base_url}/v1/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status != 200:
                    return _fallback_plan(query)
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        # 解析 JSON
        content = content.strip()
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        plan = json.loads(content)

        # 校验必要字段
        if not plan.get("queries"):
            return _fallback_plan(query)
        if not plan.get("core_concepts"):
            plan["core_concepts"] = query.split()[:3]

        return plan

    except Exception:
        return _fallback_plan(query)


def _fallback_plan(query: str) -> dict:
    """LLM 调用失败时的兜底方案"""
    return {
        "core_concepts": query.split()[:3],
        "field_terms": [],
        "queries": {
            "arxiv": query,
            "semantic_scholar": query,
            "openalex": query,
            "crossref": query,
        },
    }


async def expand_query(query: str) -> list[str]:
    """扩展检索词：生成多个相关查询变体（保留兼容性）"""
    plan = await generate_search_plan(query)

    # 从 plan 中提取所有查询变体
    queries = list(plan.get("queries", {}).values())
    # 加入原始查询
    if query not in queries:
        queries.insert(0, query)

    return queries
