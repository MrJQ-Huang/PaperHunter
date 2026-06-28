"""Validate search plans before they are handed to search execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


USER_PHRASES = [
    "我要", "我想", "帮我", "请你", "便于我", "都包含", "不清楚",
    "给我", "找找", "看看", "开始检索", "开始搜索",
]


@dataclass
class PlanValidationResult:
    valid: bool
    blocking: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_search_plan(plan: dict[str, Any] | None) -> PlanValidationResult:
    issues: list[str] = []
    warnings: list[str] = []

    if not isinstance(plan, dict):
        return PlanValidationResult(False, True, ["plan_missing"])

    query = str(plan.get("query") or "").strip()
    title = str(plan.get("task_title") or plan.get("title") or "").strip()
    goal = str(plan.get("goal") or "").strip()
    subtopics = plan.get("subtopics") or []
    queries = plan.get("queries") or {}

    if not query:
        issues.append("query_missing")
    if _looks_like_raw_user_text(query):
        issues.append("query_is_raw_user_text")
    if _looks_like_raw_user_text(title):
        issues.append("title_is_raw_user_text")
    if "检索相关论文" in goal and _cjk_ratio(goal) > 0.25:
        issues.append("goal_is_generic_fallback")
    if not isinstance(subtopics, list) or not subtopics:
        issues.append("subtopics_missing")
    elif len(subtopics) == 1:
        only = subtopics[0] if isinstance(subtopics[0], dict) else {}
        name = str(only.get("name") or "")
        subquery = " ".join(str(v) for v in (only.get("queries") or {}).values())
        if _looks_like_raw_user_text(name) or _looks_like_raw_user_text(subquery):
            issues.append("single_subtopic_is_raw_user_text")

    source_queries = []
    for source, q in queries.items():
        q = str(q or "").strip()
        source_queries.append(q)
        if not q:
            issues.append(f"{source}_query_missing")
        elif _looks_like_raw_user_text(q):
            issues.append(f"{source}_query_is_raw_user_text")

    for subtopic in subtopics if isinstance(subtopics, list) else []:
        if not isinstance(subtopic, dict):
            issues.append("subtopic_not_object")
            continue
        name = str(subtopic.get("name") or "").strip()
        if not name:
            issues.append("subtopic_name_missing")
        elif _looks_like_raw_user_text(name):
            issues.append("subtopic_name_is_raw_user_text")
        sub_queries = subtopic.get("queries") or {}
        if not isinstance(sub_queries, dict) or not sub_queries:
            issues.append(f"subtopic_{name or 'unknown'}_queries_missing")
            continue
        for source, q in sub_queries.items():
            q = str(q or "").strip()
            if not q:
                issues.append(f"subtopic_{name}_{source}_query_missing")
            elif _looks_like_raw_user_text(q):
                issues.append(f"subtopic_{name}_{source}_query_is_raw_user_text")

    unique_queries = {q.lower() for q in source_queries if q}
    if len(source_queries) >= 3 and len(unique_queries) == 1:
        warnings.append("source_queries_are_identical")
    if len(subtopics) > 7:
        warnings.append("too_many_subtopics")

    blocking_prefixes = (
        "query_", "title_", "goal_", "subtopics_", "single_subtopic_", "subtopic_",
        "arxiv_", "semantic_scholar_", "openalex_", "crossref_",
    )
    blocking = any(issue.startswith(blocking_prefixes) for issue in issues)
    return PlanValidationResult(not blocking, blocking, issues, warnings)


def _looks_like_raw_user_text(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if "\n" in text and _cjk_ratio(text) > 0.15:
        return True
    if len(text) > 20 and _cjk_ratio(text) > 0.2:
        return True
    if len(text) > 80 and _cjk_ratio(text) > 0.2:
        return True
    if any(phrase in text for phrase in USER_PHRASES) and _cjk_ratio(text) > 0.15:
        return True
    return False


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk / max(len(text), 1)
