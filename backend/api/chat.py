from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
import uuid
import json
import re

from ..models.message import Message, MessageRole
from ..models.task import Task, TaskStatus
from ..database import insert_message, get_messages, get_task, update_task
from ..services.search_planning_service import prepare_search_execution
from ..utils.llm_client import call_llm

router = APIRouter()


# 用户表达"开始执行"意图的关键词（必须包含明确的"启动/确认"语义，不能匹配描述需求的句子）
_START_KEYWORDS = [
    "开始搜索", "开始搜", "开始检索", "搜索吧", "搜吧",
    "确认搜索", "确认，开始", "确认开始", "开始吧",
    "可以搜了", "可以开始", "可以了", "就这样搜",
    "go", "start", "开始执行", "启动搜索", "启动吧",
    "就这样", "就这些", "没问题了", "开搜",
    "开始查", "开始找", "执行搜索", "执行检索", "启动检索",
    "进入检索", "进入搜索", "开始运行", "运行吧",
    "启动agent", "启动 agent", "启动工作流", "开始工作流",
    "下发任务", "下发检索", "按这个方案搜", "按这个方案检索",
    "继续检索", "继续搜索",
]


class SendMessageRequest(BaseModel):
    content: str
    agent_name: str | None = None


def _detect_start_intent(text: str) -> bool:
    """检测用户是否有"开始搜索"的意图
    对较短的确认句和包含明确执行动词的长句生效，避免把需求描述误判为启动。"""
    text_clean = text.strip()
    text_lower = text_clean.lower()

    if not text_clean:
        return False

    negative_markers = ["不要开始", "先别开始", "暂不开始", "不要搜", "先别搜", "别启动", "不要启动"]
    if any(marker in text_lower for marker in negative_markers):
        return False

    for kw in _START_KEYWORDS:
        if kw in text_lower:
            return True

    # 允许自然语言确认，例如“方案可以，直接开始检索论文吧”。
    if len(text_clean) <= 80:
        has_confirm = any(w in text_lower for w in ["确认", "可以", "没问题", "就这样", "按这个", "同意", "ok"])
        has_action = any(w in text_lower for w in ["开始", "启动", "执行", "检索", "搜索", "运行", "下发"])
        if has_confirm and has_action:
            return True

    return False


def _detect_progress_intent(text: str) -> bool:
    cleaned = re.sub(r"[\s？！?!。,.，~～]", "", text.strip().lower())
    return cleaned in {"查看进度", "进度", "看进度", "当前进度", "任务进度"}


@router.get("/messages/{task_id}")
async def list_messages(
    task_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    messages = await get_messages(task_id, page, per_page)
    return [m.model_dump() for m in messages]


@router.post("/messages/{task_id}")
async def send_message(task_id: str, req: SendMessageRequest):
    message = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.USER,
        content=req.content,
        timestamp=datetime.now(),
        agent_name=req.agent_name,
    )
    await insert_message(message)
    return message.model_dump()


@router.post("/messages/{task_id}/reply")
async def agent_reply(task_id: str):
    """让 Chat Agent 根据对话历史生成回复，或在用户确认时触发工作流"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 获取最新用户消息，检测意图
    history = await get_messages(task_id, page=1, per_page=50)
    user_msgs = [m for m in history if m.role == MessageRole.USER]
    latest_user_msg = user_msgs[-1].content if user_msgs else ""

    # “查看进度”是状态查询，不允许在 pending 状态下触发检索工作流。
    if _detect_progress_intent(latest_user_msg):
        return await _progress_reply(task)

    # 如果用户表达了"开始搜索"意图且任务处于待确认状态，直接触发工作流
    if task.status in (TaskStatus.PENDING, TaskStatus.PAUSED) and _detect_start_intent(latest_user_msg):
        return await _trigger_workflow(task)

    # 已完成/失败/取消的任务：基于论文上下文对话
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return await _paper_chat(task, history)

    # 否则走 LLM 对话
    messages = [
        {
            "role": "system",
            "content": f"""你是 PaperHunter 的学术搜索助手，负责与用户讨论论文搜索方案。

当前搜索主题: "{task.query}"
任务状态: {task.status.value}

你的职责：
1. 理解用户的研究需求，用专业学术语言复述和分析
2. 主动追问用户尚未说明但会显著影响检索质量的信息
3. 建议搜索策略（时间范围、文献类型、子方向等）
4. 引导用户确认搜索方案

重要规则：
- 你只负责讨论和分析，不要自己执行搜索、不要编造论文列表、不要模拟搜索结果
- 当用户说"开始搜索"之类的话时，回复"好的，正在启动搜索流程！"并加上 [READY] 标记
- 不要输出关键词列表或搜索方案的结构化内容，这些由系统自动生成
- 任务未启动时，不要建议"查看进度"；如果方案已足够清晰，建议用户说"开始检索"
- 如果用户只给出缩写、宽泛领域或一句很模糊的话，要主动问 2-3 个最关键澄清问题
- 如果用户是新手或表达"入门/了解/学习/权威/基础论文"，要建议新手学习模式：综述、基础论文、代表方法、benchmark、近期前沿
- 对容易歧义的缩写要提醒确认领域，例如 VLA 可能是 Vision-Language-Action 也可能是 Very Large Array
- 简洁专业，中文回复，150字以内

回复格式（严格遵守）：
先写正文，然后换行写：
[SUGGESTIONS: ["建议1", "建议2", "建议3"]]
如果用户确认开始，正文末尾加 [READY]""",
        }
    ]

    for msg in history:
        role = "user" if msg.role == MessageRole.USER else "assistant"
        messages.append({"role": role, "content": msg.content})

    try:
        reply_content, suggestions = await _call_llm(messages)
    except Exception as e:
        reply_content = f"抱歉，AI 服务暂时不可用: {str(e)}"
        suggestions = ["重试", "直接开始搜索"]

    # 如果 LLM 回复中包含 [READY]，也触发工作流
    if "[READY]" in reply_content:
        reply_content = re.sub(r'\[READY\]', '', reply_content).strip()
        return await _trigger_workflow(task, reply_content=reply_content)

    # 普通对话回复
    reply_msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=reply_content,
        suggestions=suggestions,
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(reply_msg)
    return reply_msg.model_dump()


async def _progress_reply(task: Task) -> dict:
    status_text = {
        TaskStatus.PENDING: "当前任务还没有启动。你可以继续补充检索条件，确认后直接说“开始检索”。",
        TaskStatus.PAUSED: "当前任务已暂停。确认继续时可以说“继续检索”或“开始检索”。",
        TaskStatus.RUNNING: "当前任务正在运行中，检索图谱和论文库会持续更新。",
        TaskStatus.REVIEWING: "检索已完成，当前进入论文库筛选阶段。",
        TaskStatus.COMPLETED: "任务已完成。",
        TaskStatus.FAILED: f"任务失败：{task.error_message or '未知错误'}",
        TaskStatus.CANCELLED: "任务已终止。你可以调整条件后重新开始。",
    }.get(task.status, f"当前任务状态：{task.status.value}")

    suggestions = ["开始检索", "继续补充条件"] if task.status in (TaskStatus.PENDING, TaskStatus.PAUSED) else ["查看论文库"]
    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task.id,
        role=MessageRole.AGENT,
        content=status_text,
        suggestions=suggestions,
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)
    return msg.model_dump()


async def _trigger_workflow(task: Task, reply_content: str | None = None) -> dict:
    """直接触发 Agent 工作流"""
    import asyncio
    from ..crew.paper_crew import PaperCrew
    from .tasks import _running_crews, _run_crew, _build_search_plan

    task_id = task.id

    try:
        task, _ = await prepare_search_execution(task, plan_builder=_build_search_plan)
    except Exception as exc:
        reply_msg = Message(
            id=str(uuid.uuid4()),
            task_id=task_id,
            role=MessageRole.AGENT,
            content=f"当前搜索方案还不能安全下发给检索 Agent：{str(exc)}\n请再补充研究领域、关键术语或目标论文类型后重新开始。",
            suggestions=["继续补充条件", "重新说明研究目标"],
            timestamp=datetime.now(),
            agent_name="Chat Agent",
        )
        await insert_message(reply_msg)
        return reply_msg.model_dump()

    task.status = TaskStatus.RUNNING
    task.updated_at = datetime.now()
    await update_task(task)

    reply_msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=reply_content or f"任务已启动：{task.query}\n正在构建检索图谱并按分支搜索论文。",
        suggestions=["查看进度"],
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(reply_msg)

    crew = PaperCrew(task)
    _running_crews[task_id] = crew
    asyncio.create_task(_run_crew(task_id, crew))

    return reply_msg.model_dump()


async def _call_llm(messages: list[dict]) -> tuple[str, list[str]]:
    """调用 LLM 获取回复"""
    system_msg = ""
    llm_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            llm_messages.append(msg)

    content = await call_llm(
        llm_messages,
        system=system_msg or None,
        max_tokens=1024,
        timeout=30,
    )
    suggestions = _extract_suggestions(content)
    content = _clean_content(content)

    return content, suggestions


def _extract_suggestions(text: str) -> list[str]:
    """从回复中提取快捷建议"""
    # 匹配 [SUGGESTIONS: [...]] 格式，处理嵌套括号
    match = re.search(r'\[SUGGESTIONS?:\s*(\[.*\])\s*\]', text, re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            raw = match.group(1).strip("[]")
            return [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()]

    # 匹配 [SUGGESTIONS: a, b, c] 格式（无方括号）
    match = re.search(r'\[SUGGESTIONS?:\s*(.+?)\]', text, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        if not raw.startswith("["):
            return [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()]

    if "[READY]" in text:
        return ["确认，开始搜索！", "再调整一下条件", "扩大搜索范围"]
    return ["搜索最新3年的研究", "只要高引用论文", "全面搜索，不限条件", "只看OA论文"]


def _clean_content(text: str) -> str:
    """清理回复中的标记，保留正文"""
    # 移除 [SUGGESTIONS: ...] 及其变体
    text = re.sub(r'\[SUGGESTIONS?:\s*\[.*?\]\s*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[SUGGESTIONS?:\s*.*?\]', '', text, flags=re.IGNORECASE)
    # 移除 [READY]
    text = re.sub(r'\[READY\]', '', text)
    return text.strip()


async def _paper_chat(task: Task, history: list) -> dict:
    """已完成任务的论文交互对话"""
    from ..database import get_papers

    papers, total = await get_papers(task_id=task.id, per_page=30, sort="relevance")

    papers_context = ""
    if papers:
        lines = []
        for i, p in enumerate(papers, 1):
            authors = ", ".join(p.authors[:3]) if p.authors else "未知"
            score = f"{p.relevance_score:.1f}" if p.relevance_score else "N/A"
            cite = p.citation_count or 0
            abstract = (p.abstract or "")[:150]
            lines.append(f"{i}. {p.title}\n   作者: {authors} | 来源: {p.source} | 引用: {cite} | 相关度: {score}\n   摘要: {abstract}")
        papers_context = "\n".join(lines)

    system = f"""你是 PaperHunter 的学术助手。用户之前搜索了关于「{task.query}」的论文，共找到 {task.total_papers_found} 篇。

以下是相关论文列表（按相关度排序）：
{papers_context}

你可以帮用户：
1. 总结这些论文的主要研究方向和发现
2. 根据用户需求推荐最相关的论文
3. 回答关于这些论文内容的问题
4. 比较不同论文的方法和贡献
5. 分析研究趋势和热点

简洁专业，中文回复，200字以内。
回复格式：
先写正文，然后换行写：
[SUGGESTIONS: ["建议1", "建议2", "建议3"]]"""

    messages = [{"role": "system", "content": system}]
    for msg in history:
        role = "user" if msg.role == MessageRole.USER else "assistant"
        messages.append({"role": role, "content": msg.content})

    try:
        reply_content, suggestions = await _call_llm(messages)
    except Exception as e:
        reply_content = f"抱歉，AI 服务暂时不可用: {str(e)}"
        suggestions = ["重试"]

    reply_msg = Message(
        id=str(uuid.uuid4()),
        task_id=task.id,
        role=MessageRole.AGENT,
        content=reply_content,
        suggestions=suggestions,
        timestamp=datetime.now(),
        agent_name="Paper Agent",
    )
    await insert_message(reply_msg)
    return reply_msg.model_dump()
