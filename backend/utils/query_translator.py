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


async def expand_query(query: str) -> list[str]:
    """扩展检索词：生成多个相关查询变体"""
    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 512,
        "system": """你是学术搜索助手。根据用户的研究主题，生成 3-5 个不同的英文检索词组合，覆盖该主题的不同角度。
返回 JSON 数组格式，例如: ["query1", "query2", "query3"]
只返回 JSON 数组，不要其他内容。""",
        "messages": [
            {"role": "user", "content": f"研究主题：{query}"}
        ],
    }

    url = f"{settings.llm_base_url}/v1/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return [query]
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        # 解析 JSON 数组
        content = content.strip()
        if content.startswith("["):
            queries = json.loads(content)
            return queries if queries else [query]
        return [query]

    except Exception:
        return [query]
