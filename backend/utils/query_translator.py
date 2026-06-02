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
        "core_concepts": ["视觉语言动作模型", ...],   # 核心概念（必须包含）
        "synonyms": ["visual-language-action", ...],    # 同义词/缩写展开
        "sub_directions": ["robot manipulation", ...],  # 相关子方向
        "queries": {
            "arxiv": "all:VLA AND all:robot AND all:manipulation",
            "semantic_scholar": "VLA robot manipulation policy learning",
            "openalex": "VLA robot manipulation",
            "crossref": "VLA robot manipulation",
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
  "synonyms": ["同义词1", "同义词2"],
  "sub_directions": ["子方向1", "子方向2"],
  "queries": {
    "arxiv": "arXiv格式的布尔查询",
    "semantic_scholar": "自然语言查询",
    "openalex": "简洁关键词查询",
    "crossref": "简洁关键词查询"
  }
}

规则：
1. core_concepts 是最核心的概念词，搜索结果必须包含至少一个
2. queries 中每个查询都必须包含 core_concepts 中的词
3. arXiv 支持 AND/OR 布尔语法，其他用空格分隔关键词
4. 不要生成过于宽泛的查询
5. 只返回 JSON，不要其他内容""",
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
        "synonyms": [],
        "sub_directions": [],
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
