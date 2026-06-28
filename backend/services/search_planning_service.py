"""Build, validate, and repair executable search plans."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from ..database import get_messages, update_task
from ..models.message import Message, MessageRole
from ..models.paper import PaperSource
from ..models.task import Task
from ..utils.plan_repairer import repair_search_plan
from ..utils.plan_validator import validate_search_plan


PlanBuilder = Callable[[Task, bool], Awaitable[tuple[Task, dict[str, Any]]]]


async def prepare_search_execution(
    task: Task,
    plan_builder: PlanBuilder | None = None,
) -> tuple[Task, dict[str, Any]]:
    """Return a validated execution plan and persist it on the task.

    This is the single protocol bridge between Chat Agent and Search Agent.
    Search execution should consume filters["_execution_plan"], not raw chat text.
    """
    history = await get_messages(task.id, page=1, per_page=100)
    research_text = conversation_research_text(history) or task.query

    plan = task.search_plan
    validation = validate_search_plan(plan)

    if (not plan or validation.blocking) and plan_builder is not None:
        try:
            task, plan = await plan_builder(task, False)
            validation = validate_search_plan(plan)
        except Exception:
            plan = task.search_plan
            validation = validate_search_plan(plan)

    if not plan or validation.blocking:
        plan = await repair_search_plan(research_text, plan, validation.issues)
        validation = validate_search_plan(plan)

    if validation.blocking:
        # Last-resort repair should almost never fail, but keep task executable.
        plan = await repair_search_plan(research_text, None, validation.issues)
        validation = validate_search_plan(plan)
    if validation.blocking:
        raise RuntimeError(f"Search plan is not executable: {', '.join(validation.issues)}")

    plan.setdefault("warnings", [])
    for warning in validation.warnings:
        if warning not in plan["warnings"]:
            plan["warnings"].append(warning)

    task.search_plan = plan
    task.query = str(plan.get("task_title") or plan.get("domain") or plan.get("query") or task.query).strip()
    if plan.get("sources"):
        task.sources = [PaperSource(s) for s in plan["sources"] if s in PaperSource._value2member_map_]
    task.filters = {
        **dict(task.filters),
        "_research_intent": {
            "conversation": research_text,
            "domain": plan.get("domain"),
            "goal": plan.get("goal"),
            "core_concepts": plan.get("core_concepts", []),
            "preferred_paper_types": plan.get("preferred_paper_types", []),
        },
        "_execution_plan": plan,
    }
    task.updated_at = datetime.now()
    await update_task(task)
    return task, plan


def conversation_research_text(history: list[Message]) -> str:
    user_texts = [
        m.content.strip()
        for m in history
        if m.role == MessageRole.USER and not _is_control_message(m.content)
    ]
    return "\n".join(user_texts[-10:])


def _is_control_message(text: str) -> bool:
    cleaned = "".join(ch for ch in text.strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    if not cleaned:
        return True
    if cleaned in {"你好", "您好", "hi", "hello", "hey", "在吗", "查看进度", "进度"}:
        return True
    controls = ["开始检索", "开始搜索", "确认搜索", "确认开始", "查看进度", "终止当前任务"]
    quick_options = ["搜索最新3年的研究", "只要高引用论文", "全面搜索", "只看oa论文", "只看开放获取"]
    return any(c in text.lower() for c in controls + quick_options)
