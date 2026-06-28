"""Repair invalid search plans into executable, source-specific plans."""

from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import call_llm


SOURCE_KEYS = ["arxiv", "semantic_scholar", "openalex", "crossref"]


async def repair_search_plan(
    research_text: str,
    bad_plan: dict[str, Any] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Create a safe execution plan from conversation-derived research text."""
    repaired = await _repair_with_llm(research_text, bad_plan, issues or [])
    if repaired:
        return _normalize_plan(repaired, research_text)
    fallback = _fallback_plan(research_text)
    fallback_query = str(fallback.get("query", ""))
    needs_translation = _cjk_ratio(fallback_query) > 0.2 or (
        len(fallback_query.split()) < 3 and _cjk_ratio(research_text) > 0.2
    )
    if needs_translation:
        try:
            from ..utils.query_translator import translate_query

            translated = await translate_query(research_text)
            translated = _clean_query(translated)
            if translated and _cjk_ratio(translated) <= 0.2:
                fallback["query"] = translated
                fallback["domain"] = translated
                fallback["core_concepts"] = translated.split()[:4]
                fallback["queries"] = _source_queries({}, translated)
                fallback["subtopics"] = _fallback_subtopics(translated)
        except Exception:
            pass
    return fallback


async def _repair_with_llm(
    research_text: str,
    bad_plan: dict[str, Any] | None,
    issues: list[str],
) -> dict[str, Any] | None:
    system = """You convert a user's paper-search conversation into an executable academic search plan.

Return strict JSON only. The plan must be domain-agnostic and source-specific.
Never copy raw Chinese user sentences into query fields. Queries must be English academic keywords.

JSON:
{
  "query": "short English search title",
  "task_title": "Chinese task title, <= 30 chars",
  "search_mode": "beginner_learning | authoritative_core | recent_sota | subtopic_deep_dive | broad_exploration",
  "goal": "Chinese goal summary",
  "domain": "English domain name",
  "sources": ["arxiv", "semantic_scholar", "openalex", "crossref"],
  "filters": {},
  "core_concepts": ["English concept"],
  "field_terms": ["English field term"],
  "exclude_terms": ["English ambiguity term"],
  "preferred_paper_types": ["survey", "foundation", "method", "benchmark", "system"],
  "subtopics": [
    {
      "name": "English subtopic name",
      "intent": "Chinese intent",
      "required_terms": ["English term"],
      "optional_terms": ["English synonym or representative system"],
      "queries": {
        "arxiv": "Boolean or keyword query",
        "semantic_scholar": "natural language keyword query",
        "openalex": "short keyword query",
        "crossref": "short keyword query"
      }
    }
  ],
  "queries": {
    "arxiv": "fallback query",
    "semantic_scholar": "fallback query",
    "openalex": "fallback query",
    "crossref": "fallback query"
  },
  "summary": "Chinese strategy summary",
  "warnings": []
}

Rules:
1. Create 2-5 subtopics unless the user explicitly asks for one narrow item.
2. For ambiguous abbreviations, add exclude_terms.
3. Crossref/OpenAlex queries must be short English keyword strings.
4. Do not include words like 我要, 帮我, 请你, 都包含, 开始检索 in any query."""

    try:
        content = await call_llm(
            [{
                "role": "user",
                "content": (
                    f"Research conversation:\n{research_text}\n\n"
                    f"Invalid plan issues: {issues}\n\n"
                    f"Invalid plan:\n{json.dumps(bad_plan or {}, ensure_ascii=False)[:4000]}\n\n"
                    "Return repaired JSON:"
                ),
            }],
            system=system,
            max_tokens=3072,
            timeout=25,
        )
        content = content.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)
        elif not content.startswith("{"):
            start, end = content.find("{"), content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end + 1]
        return json.loads(content)
    except Exception:
        return None


def _normalize_plan(plan: dict[str, Any], research_text: str) -> dict[str, Any]:
    query = _clean_query(str(plan.get("query") or _extract_keywords(research_text)))
    title = str(plan.get("task_title") or plan.get("domain") or query).strip()[:30]
    plan["query"] = query
    plan["task_title"] = title
    plan.setdefault("search_mode", "broad_exploration")
    plan.setdefault("goal", f"围绕 {title} 检索相关论文")
    plan.setdefault("domain", query)
    plan["sources"] = [s for s in plan.get("sources", SOURCE_KEYS) if s in SOURCE_KEYS] or SOURCE_KEYS
    plan.setdefault("filters", {})
    plan["core_concepts"] = _as_list(plan.get("core_concepts")) or query.split()[:3]
    plan["field_terms"] = _as_list(plan.get("field_terms"))
    plan["exclude_terms"] = _as_list(plan.get("exclude_terms"))
    plan.setdefault("preferred_paper_types", ["survey", "foundation", "method", "benchmark"])

    fallback_queries = plan.get("queries") if isinstance(plan.get("queries"), dict) else {}
    plan["queries"] = _source_queries(fallback_queries, query)

    subtopics = plan.get("subtopics") if isinstance(plan.get("subtopics"), list) else []
    normalized_subtopics = []
    for subtopic in subtopics[:5]:
        if not isinstance(subtopic, dict):
            continue
        name = _clean_query(str(subtopic.get("name") or query))[:80]
        required = _as_list(subtopic.get("required_terms")) or query.split()[:3]
        optional = _as_list(subtopic.get("optional_terms"))
        sub_queries = _source_queries(subtopic.get("queries") or {}, " ".join([name, *required, *optional]))
        normalized_subtopics.append({
            "name": name,
            "intent": str(subtopic.get("intent") or f"检索 {name} 相关论文"),
            "required_terms": required[:6],
            "optional_terms": optional[:10],
            "queries": sub_queries,
        })
    if not normalized_subtopics:
        normalized_subtopics = _fallback_subtopics(query)
    plan["subtopics"] = normalized_subtopics
    plan.setdefault("summary", f"围绕 {title} 生成多分支英文检索方案。")
    plan.setdefault("warnings", [])
    return plan


def _fallback_plan(research_text: str) -> dict[str, Any]:
    query = _extract_keywords(research_text)
    title = _title_from_text(research_text, query)
    return {
        "query": query,
        "task_title": title,
        "search_mode": "broad_exploration",
        "goal": f"围绕 {title} 检索代表性论文、基础论文和近期进展",
        "domain": query,
        "sources": SOURCE_KEYS,
        "filters": {},
        "core_concepts": query.split()[:4],
        "field_terms": [],
        "exclude_terms": [],
        "preferred_paper_types": ["survey", "foundation", "method", "benchmark"],
        "subtopics": _fallback_subtopics(query),
        "queries": _source_queries({}, query),
        "summary": "LLM 计划生成失败，已使用保守英文关键词方案。",
        "warnings": ["low_confidence_auto_repair"],
    }


def _fallback_subtopics(query: str) -> list[dict[str, Any]]:
    base = query.split()[:6]
    variants = [
        ("Foundational and Survey Papers", ["survey", "foundation", "review"]),
        ("Representative Methods and Systems", ["method", "system", "benchmark"]),
        ("Recent Advances", ["recent", "state of the art", "latest"]),
    ]
    return [
        {
            "name": name,
            "intent": f"检索 {name} 方向论文",
            "required_terms": base[:4],
            "optional_terms": extras,
            "queries": _source_queries({}, " ".join([query, *extras])),
        }
        for name, extras in variants
    ]


def _source_queries(queries: dict[str, Any], fallback: str) -> dict[str, str]:
    cleaned = _clean_query(fallback)
    result = {}
    for source in SOURCE_KEYS:
        value = _clean_query(str(queries.get(source) or cleaned))
        if source == "arxiv" and " " in value and " OR " not in value and " AND " not in value:
            value = " ".join(value.split()[:12])
        else:
            value = " ".join(value.split()[:12])
        result[source] = value or cleaned
    return result


def _extract_keywords(text: str) -> str:
    ascii_terms = re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", text)
    keep = []
    stop = {"the", "and", "for", "with", "from", "paper", "papers", "about"}
    for term in ascii_terms:
        low = term.lower()
        if low not in stop and low not in [t.lower() for t in keep]:
            keep.append(term)
    if "π" in text and "pi series" not in [t.lower() for t in keep]:
        keep.extend(["pi", "series"])
    for cn, en_terms in COMMON_TERM_MAP.items():
        if cn in text:
            for term in en_terms:
                if term.lower() not in [t.lower() for t in keep]:
                    keep.append(term)
    if len(keep) >= 3:
        return " ".join(keep[:10])
    cjk = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\s\-]", " ", text)
    cjk = re.sub("|".join(map(re.escape, USER_WORDS)), " ", cjk)
    return " ".join(cjk.split()[:8]) or "academic research"


USER_WORDS = ["我要", "我想", "帮我", "请你", "论文", "相关", "便于我", "都包含", "开始检索"]

COMMON_TERM_MAP = {
    "模型": ["model"],
    "版本": ["version"],
    "迭代": ["iteration"],
    "演进": ["evolution"],
    "改进": ["improvement"],
    "溯源": ["lineage"],
    "方法": ["method"],
    "理论": ["theory"],
    "综述": ["survey"],
    "基础": ["foundation"],
    "前沿": ["frontier"],
    "数据集": ["dataset"],
    "基准": ["benchmark"],
    "系统": ["system"],
}


def _title_from_text(text: str, query: str) -> str:
    cleaned = re.sub(r"[\r\n]+", " ", text)
    cleaned = re.sub("|".join(map(re.escape, USER_WORDS)), " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 35 and _cjk_ratio(cleaned) > 0.2:
        return (query[:30] or "论文检索任务")
    return (cleaned[:30] or query[:30] or "论文检索任务")


def _clean_query(query: str) -> str:
    query = re.sub(r"[\r\n]+", " ", query)
    for word in USER_WORDS:
        query = query.replace(word, " ")
    query = re.sub(r"\s+", " ", query).strip(" ,.;:，。")
    return query[:180]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk / max(len(text), 1)
