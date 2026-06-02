from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
import uuid
import json
import re
import aiohttp

from ..models.message import Message, MessageRole
from ..models.task import Task, TaskStatus
from ..database import insert_message, get_messages, get_task, update_task
from ..config import settings

router = APIRouter()


# 用户表达"开始执行"意图的关键词（必须包含明确的"启动/确认"语义，不能匹配描述需求的句子）
_START_KEYWORDS = [
    "开始搜索", "开始搜", "开始检索", "搜索吧", "搜吧",
    "确认搜索", "确认，开始", "确认开始", "开始吧",
    "可以搜了", "可以开始", "可以了", "就这样搜",
    "go", "start", "开始执行", "启动搜索", "启动吧",
    "就这样", "就这些", "没问题了", "开搜",
]


class SendMessageRequest(BaseModel):
    content: str
    agent_name: str | None = None


def _detect_start_intent(text: str) -> bool:
    """检测用户是否有"开始搜索"的意图
    只对短消息（<15字）做关键词匹配，长消息视为需求描述，不触发"""
    text_clean = text.strip()
    text_lower = text_clean.lower()

    # 长消息（超过15个字）视为需求描述，不触发
    if len(text_clean) > 15:
        return False

    for kw in _START_KEYWORDS:
        if kw in text_lower:
            return True
    return False


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

    # 如果用户表达了"开始搜索"意图且任务处于待确认状态，直接触发工作流
    if task.status in (TaskStatus.PENDING, TaskStatus.PAUSED) and _detect_start_intent(latest_user_msg):
        return await _trigger_workflow(task)

    # 否则走 LLM 对话
    messages = [
        {
            "role": "system",
            "content": f"""你是 PaperHunter 的学术搜索助手，负责与用户讨论论文搜索方案。

当前搜索主题: "{task.query}"
任务状态: {task.status.value}

你的职责：
1. 理解用户的研究需求，用专业学术语言复述和分析
2. 建议搜索策略（时间范围、文献类型、子方向等）
3. 引导用户确认搜索方案

重要规则：
- 你只负责讨论和分析，不要自己执行搜索、不要编造论文列表、不要模拟搜索结果
- 当用户说"开始搜索"之类的话时，回复"好的，正在启动搜索流程！"并加上 [READY] 标记
- 不要输出关键词列表或搜索方案的结构化内容，这些由系统自动生成
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
    if "[READY]" in reply_content or _detect_start_intent(reply_content):
        reply_content = re.sub(r'\[READY\]', '', reply_content).strip()

        # 如果有搜索方案，用方案中的 query
        from .tasks import _running_crews, _run_crew
        from ..crew.paper_crew import PaperCrew
        if task.search_plan and task.search_plan.get("query"):
            task.query = task.search_plan["query"]
            await update_task(task)

        reply_msg = Message(
            id=str(uuid.uuid4()),
            task_id=task_id,
            role=MessageRole.AGENT,
            content=reply_content or f"好的，以「{task.query}」为主题启动搜索！",
            suggestions=["查看进度"],
            timestamp=datetime.now(),
            agent_name="Chat Agent",
        )
        await insert_message(reply_msg)
        # 异步触发工作流
        import asyncio
        if task.status in (TaskStatus.PENDING, TaskStatus.PAUSED):
            crew = PaperCrew(task)
            _running_crews[task_id] = crew
            asyncio.create_task(_run_crew(task_id, crew))
        return reply_msg.model_dump()

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


async def _trigger_workflow(task: Task) -> dict:
    """直接触发 Agent 工作流"""
    import asyncio
    from ..crew.paper_crew import PaperCrew
    from .tasks import _running_crews, _run_crew

    task_id = task.id

    # 如果有搜索方案，用方案中的 query
    if task.search_plan and task.search_plan.get("query"):
        task.query = task.search_plan["query"]
        await update_task(task)

    reply_msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=f"好的，以「{task.query}」为主题启动搜索！即将开始多源检索、智能筛选和自动下载。",
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
    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "messages": [],
    }

    system_msg = ""
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            body["messages"].append(msg)

    if system_msg:
        body["system"] = system_msg

    url = f"{settings.llm_base_url}/v1/messages"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=body, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"LLM API error {resp.status}: {error_text}")
            data = await resp.json()

    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")

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
