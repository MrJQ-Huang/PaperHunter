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
        "max_tokens": 2048,
        "system": """你是一个学术搜索策略专家。根据用户的研究主题，生成精准的搜索方案。

你必须返回纯 JSON，格式如下：
{
  "search_mode": "beginner_learning | authoritative_core | recent_sota | subtopic_deep_dive | broad_exploration",
  "goal": "用户想通过这次检索完成的研究目标",
  "domain": "英文领域名称",
  "core_concepts": ["核心概念1", "核心概念2"],
  "field_terms": ["领域术语1", "领域术语2"],
  "exclude_terms": ["容易混淆但应排除的术语"],
  "preferred_paper_types": ["survey", "foundation", "benchmark", "method", "system"],
  "subtopics": [
    {
      "name": "子方向英文名",
      "intent": "该子方向要找什么论文",
      "required_terms": ["必须相关的术语"],
      "optional_terms": ["同义词或相关术语"],
      "queries": {
        "arxiv": "arXiv 布尔查询",
        "semantic_scholar": "自然语言查询",
        "openalex": "简洁关键词查询",
        "crossref": "简洁关键词查询"
      }
    }
  ],
  "queries": {
    "arxiv": "兜底总查询",
    "semantic_scholar": "兜底总查询",
    "openalex": "兜底总查询",
    "crossref": "兜底总查询"
  },
  "annotation_policy": {
    "paper_types": ["survey", "benchmark", "dataset", "method", "system", "application", "theory"],
    "learning_roles": ["field_overview", "foundation", "representative_method", "recent_frontier", "benchmark_or_dataset", "implementation_reference"]
  }
}

字段说明：
- core_concepts: 该领域最核心的 2-3 个概念词，论文中大概率会包含这些词（如 "vision language action"、"robot"）
- field_terms: 该领域论文中自然会出现的术语，即使论文标题不含核心概念，摘要也会包含这些词
  例如 VLA 领域的 field_terms: ["embodied AI", "robot manipulation", "policy learning", "end-to-end control", "foundation model", "imitation learning", "visual grounding"]
  这些词不是核心概念的同义词，而是该领域论文必然会使用的术语

规则：
1. 如果主题很模糊或用户是新手，search_mode 优先 beginner_learning 或 broad_exploration，并覆盖综述、基础论文、代表方法、benchmark、近期前沿。
2. 不要强迫每条 query 都包含缩写词；要覆盖同义表达、上位概念和代表系统名。
3. 对有歧义的缩写必须给 exclude_terms，例如 VLA 要排除 radio astronomy / Very Large Array / telescope。
4. subtopics 生成 4-7 个，每个子方向 query 要不同，避免重复搜索同一批标题。
5. arXiv 支持 AND/OR 布尔语法，其他源用简洁自然语言关键词。
6. 只返回 JSON，不要其他内容""",
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

        return _normalize_plan(plan, query)

    except Exception:
        return _fallback_plan(query)


def _normalize_plan(plan: dict, query: str) -> dict:
    """补齐新版搜索计划字段，同时兼容旧版 JSON。"""
    if not isinstance(plan, dict):
        return _fallback_plan(query)
    if not plan.get("queries"):
        plan["queries"] = {
            "arxiv": query,
            "semantic_scholar": query,
            "openalex": query,
            "crossref": query,
        }
    if not plan.get("core_concepts"):
        plan["core_concepts"] = query.split()[:3]
    plan.setdefault("search_mode", "broad_exploration")
    plan.setdefault("goal", f"Search papers about {query}")
    plan.setdefault("domain", query)
    plan.setdefault("field_terms", [])
    plan.setdefault("exclude_terms", [])
    plan.setdefault("preferred_paper_types", ["survey", "foundation", "method", "benchmark"])
    plan.setdefault("annotation_policy", {
        "paper_types": ["survey", "benchmark", "dataset", "method", "system", "application", "theory"],
        "learning_roles": [
            "field_overview", "foundation", "representative_method",
            "recent_frontier", "benchmark_or_dataset", "implementation_reference",
        ],
    })
    if not plan.get("subtopics"):
        plan["subtopics"] = [
            {
                "name": plan.get("domain") or query,
                "intent": plan.get("goal") or f"Search papers about {query}",
                "required_terms": plan.get("core_concepts", []),
                "optional_terms": plan.get("field_terms", []),
                "queries": plan["queries"],
            }
        ]
    return plan


def _fallback_plan(query: str) -> dict:
    """LLM 调用失败时的兜底方案"""
    return {
        "search_mode": "broad_exploration",
        "goal": f"Search papers about {query}",
        "domain": query,
        "core_concepts": query.split()[:3],
        "field_terms": [],
        "exclude_terms": [],
        "preferred_paper_types": ["survey", "foundation", "method", "benchmark"],
        "subtopics": [
            {
                "name": query,
                "intent": "Broad exploration",
                "required_terms": query.split()[:3],
                "optional_terms": [],
                "queries": {
                    "arxiv": query,
                    "semantic_scholar": query,
                    "openalex": query,
                    "crossref": query,
                },
            }
        ],
        "queries": {
            "arxiv": query,
            "semantic_scholar": query,
            "openalex": query,
            "crossref": query,
        },
        "annotation_policy": {
            "paper_types": ["survey", "benchmark", "dataset", "method", "system", "application", "theory"],
            "learning_roles": ["field_overview", "foundation", "representative_method", "recent_frontier"],
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
