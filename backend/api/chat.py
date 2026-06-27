from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
import uuid
import json
import re
import aiohttp

from ..models.message import Message, MessageRole
from ..models.task import Task, TaskStatus
from ..models.paper import PaperSource
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


def _is_greeting_or_control(text: str) -> bool:
    """过滤不应作为检索主题的短消息。"""
    cleaned = re.sub(r"[\s？！?!。,.，~～]", "", text.strip().lower())
    if not cleaned:
        return True
    greetings = {"你好", "您好", "hi", "hello", "hey", "在吗"}
    if cleaned in greetings:
        return True
    if _detect_start_intent(text):
        return True
    quick_options = [
        "搜索最新3年的研究", "只要高引用论文", "全面搜索", "不限条件",
        "只看oa论文", "只看开放获取", "查看进度",
    ]
    return any(opt in text.lower() for opt in quick_options)


def _conversation_research_text(history: list[Message]) -> str:
    """从对话历史中提取真实研究需求，避免使用首次问候作为任务 query。"""
    user_texts = [
        m.content.strip()
        for m in history
        if m.role == MessageRole.USER and not _is_greeting_or_control(m.content)
    ]
    if not user_texts:
        return ""
    return "\n".join(user_texts[-8:])


def _embodied_brain_trace_plan(research_text: str) -> dict | None:
    """对当前高频需求给出确定性三分支方案，避免 LLM 失败时退回问候语。"""
    text = research_text.lower()
    has_embodied = any(k in research_text for k in ["具身", "机器人", "大脑"]) or "embodied" in text
    has_vla = "vla" in text or "视觉" in research_text or "vision-language-action" in text
    has_world_model = "世界模型" in research_text or "world model" in text
    has_hierarchy = any(k in research_text for k in ["分层", "层级", "长时域", "任务规划", "tamp"]) or "hierarchical" in text
    if not (has_embodied and (has_vla or has_world_model or has_hierarchy)):
        return None

    return {
        "query": "embodied AI brain vision language action world models hierarchical decision making robotics",
        "task_title": "具身智能大脑三类方法论文溯源",
        "search_mode": "subtopic_deep_dive",
        "goal": "追溯具身智能大脑中 VLA、世界模型、分层决策框架三类方法的起源、基础工作、经典里程碑和最新英文论文",
        "domain": "Embodied AI brain architectures",
        "clarifying_questions": [],
        "sources": ["arxiv", "semantic_scholar", "openalex", "crossref"],
        "filters": {},
        "core_concepts": ["embodied AI", "robotics", "agent architecture"],
        "field_terms": [
            "robot learning", "foundation models", "planning", "control",
            "manipulation", "long-horizon tasks", "policy learning",
        ],
        "exclude_terms": ["Very Large Array", "radio astronomy", "telescope"],
        "preferred_paper_types": ["survey", "foundation", "benchmark", "method", "system"],
        "subtopics": [
            {
                "name": "Vision-Language-Action Models",
                "intent": "VLA 在机器人中的起源、基础模型、端到端动作生成和代表系统",
                "required_terms": ["vision language action", "robotics"],
                "optional_terms": ["VLA", "embodied AI", "robot manipulation", "RT-1", "RT-2", "OpenVLA", "PaLM-E"],
                "queries": {
                    "arxiv": '(("vision language action" OR VLA OR "vision-language-action" OR "robot foundation model") AND (robot OR robotics OR manipulation))',
                    "semantic_scholar": "vision language action models robotics RT-1 RT-2 OpenVLA PaLM-E embodied AI",
                    "openalex": "vision language action robotics embodied AI robot foundation model",
                    "crossref": "vision language action robotics embodied AI robot foundation model",
                },
            },
            {
                "name": "World Models for Robotics",
                "intent": "世界模型在智能体和机器人中的动力学表征、预测、规划与决策溯源",
                "required_terms": ["world model", "robotics"],
                "optional_terms": ["model-based reinforcement learning", "latent dynamics", "planning", "Dreamer", "MuZero"],
                "queries": {
                    "arxiv": '(("world model" OR "latent dynamics" OR "model-based reinforcement learning") AND (robot OR robotics OR embodied OR planning))',
                    "semantic_scholar": "world models robotics model-based reinforcement learning latent dynamics planning embodied agents",
                    "openalex": "world models robotics model based reinforcement learning planning embodied agents",
                    "crossref": "world models robotics model based reinforcement learning planning embodied agents",
                },
            },
            {
                "name": "Hierarchical Decision Making and TAMP",
                "intent": "分层决策、任务与运动规划、长时域动作规划在机器人中的经典框架和学习结合方法",
                "required_terms": ["hierarchical decision making", "robotics"],
                "optional_terms": ["task and motion planning", "TAMP", "long-horizon planning", "hierarchical reinforcement learning"],
                "queries": {
                    "arxiv": '(("hierarchical decision making" OR "task and motion planning" OR TAMP OR "long-horizon planning") AND (robot OR robotics OR embodied))',
                    "semantic_scholar": "hierarchical decision making task and motion planning TAMP long-horizon robot planning",
                    "openalex": "hierarchical decision making task motion planning TAMP robotics long horizon planning",
                    "crossref": "hierarchical decision making task motion planning TAMP robotics long horizon planning",
                },
            },
        ],
        "queries": {
            "arxiv": '("embodied AI" AND (robot OR robotics) AND ("vision language action" OR "world model" OR "task and motion planning" OR TAMP))',
            "semantic_scholar": "embodied AI robotics VLA world models hierarchical decision making task and motion planning",
            "openalex": "embodied AI robotics vision language action world models hierarchical decision making",
            "crossref": "embodied AI robotics vision language action world models hierarchical decision making",
        },
        "summary": "按 VLA、世界模型、分层决策/TAMP 三个分支做英文论文溯源，覆盖奠基论文、经典进展和最新代表工作。",
    }


def _vla_trace_plan(research_text: str) -> dict | None:
    """Vision-Language-Action / π 系列溯源需求的确定性方案。"""
    text = research_text.lower()
    has_vla = "vla" in text or "vision-language-action" in text or "视觉" in research_text
    has_robot = any(k in research_text for k in ["具身", "机器人", "动作", "模型"]) or any(
        k in text for k in ["robot", "robotics", "embodied", "action"]
    )
    if not (has_vla and has_robot):
        return None

    wants_pi = "π" in research_text or "pi0" in text or "physical intelligence" in text
    title = "VLA关键论文与π系列模型溯源" if wants_pi else "VLA关键论文时间线溯源"
    return {
        "query": "vision language action models robotics pi0 OpenVLA RT-2 Octo diffusion policy",
        "task_title": title,
        "search_mode": "subtopic_deep_dive",
        "goal": "按时间线追溯 Vision-Language-Action 领域关键论文，覆盖π系列模型、其他代表性VLA模型及底层方法论来源",
        "domain": "Vision-Language-Action models for robotics",
        "clarifying_questions": [],
        "sources": ["arxiv", "semantic_scholar", "openalex", "crossref"],
        "filters": {},
        "core_concepts": ["vision-language-action", "robotics", "action generation"],
        "field_terms": [
            "embodied AI", "robot foundation model", "robot manipulation",
            "imitation learning", "diffusion policy", "large-scale robot data",
        ],
        "exclude_terms": ["Very Large Array", "radio astronomy", "telescope"],
        "preferred_paper_types": ["survey", "foundation", "method", "system", "benchmark"],
        "subtopics": [
            {
                "name": "Physical Intelligence π Series",
                "intent": "π0、π0.5 等π系列模型及其技术报告、架构和训练范式",
                "required_terms": ["Physical Intelligence", "pi0"],
                "optional_terms": ["π0", "pi-zero", "vision language action", "robot foundation model"],
                "queries": {
                    "arxiv": '("Physical Intelligence" OR pi0 OR "pi zero" OR "π0") AND (robot OR robotics OR "vision language action")',
                    "semantic_scholar": "Physical Intelligence pi0 pi-zero vision language action robot foundation model",
                    "openalex": "Physical Intelligence pi0 vision language action robot foundation model",
                    "crossref": "Physical Intelligence pi0 vision language action robot foundation model",
                },
            },
            {
                "name": "Representative VLA Models",
                "intent": "RT-1、RT-2、OpenVLA、Octo、PaLM-E 等代表性VLA/机器人基础模型",
                "required_terms": ["vision language action", "robotics"],
                "optional_terms": ["RT-1", "RT-2", "OpenVLA", "Octo", "PaLM-E", "RoboCat"],
                "queries": {
                    "arxiv": '(RT-1 OR RT-2 OR OpenVLA OR Octo OR PaLM-E OR RoboCat OR "vision language action") AND (robot OR robotics)',
                    "semantic_scholar": "RT-1 RT-2 OpenVLA Octo PaLM-E RoboCat vision language action robotics",
                    "openalex": "RT-1 RT-2 OpenVLA Octo PaLM-E vision language action robotics",
                    "crossref": "RT-1 RT-2 OpenVLA Octo PaLM-E vision language action robotics",
                },
            },
            {
                "name": "Action Generation and Diffusion Policies",
                "intent": "VLA 和π系列依赖的动作生成、扩散策略、模仿学习和行为克隆方法源头",
                "required_terms": ["diffusion policy", "robot"],
                "optional_terms": ["behavior cloning", "imitation learning", "action chunking", "ACT"],
                "queries": {
                    "arxiv": '("diffusion policy" OR "action chunking" OR "behavior cloning" OR "imitation learning") AND (robot OR robotics OR manipulation)',
                    "semantic_scholar": "diffusion policy action chunking behavior cloning imitation learning robot manipulation",
                    "openalex": "diffusion policy action chunking imitation learning robot manipulation",
                    "crossref": "diffusion policy behavior cloning imitation learning robot manipulation",
                },
            },
            {
                "name": "Vision-Language and Robot Data Foundations",
                "intent": "VLA 的视觉语言预训练、大规模机器人数据集和泛化能力来源",
                "required_terms": ["vision language", "robot"],
                "optional_terms": ["CLIP", "VLM", "multimodal pretraining", "Open X-Embodiment", "robot dataset"],
                "queries": {
                    "arxiv": '("vision-language" OR CLIP OR VLM OR "multimodal pretraining" OR "Open X-Embodiment") AND (robot OR robotics OR embodied)',
                    "semantic_scholar": "vision language pretraining CLIP VLM Open X-Embodiment robot dataset embodied AI",
                    "openalex": "vision language pretraining Open X-Embodiment robot dataset embodied AI",
                    "crossref": "vision language pretraining robot dataset embodied AI",
                },
            },
        ],
        "queries": {
            "arxiv": '("vision language action" OR VLA OR OpenVLA OR RT-2 OR Octo OR pi0 OR "diffusion policy") AND (robot OR robotics)',
            "semantic_scholar": "vision language action VLA robotics pi0 OpenVLA RT-2 Octo diffusion policy",
            "openalex": "vision language action robotics pi0 OpenVLA RT-2 Octo diffusion policy",
            "crossref": "vision language action robotics pi0 OpenVLA RT-2 Octo diffusion policy",
        },
        "summary": "围绕π系列、代表性VLA模型、动作生成方法和视觉语言/机器人数据基础做时间线溯源。",
    }


def _plan_seems_generic(plan: dict | None) -> bool:
    if not isinstance(plan, dict):
        return True
    subtopics = plan.get("subtopics") or []
    query = str(plan.get("query") or "")
    if len(subtopics) <= 1 and len(query) > 80:
        return True
    if "检索相关论文" in str(plan.get("goal") or "") and len(query) > 60:
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


async def _ensure_search_plan(task: Task) -> Task:
    """确保任务有可执行搜索方案。LLM 结构化失败时使用兜底方案，避免启动链路卡死。"""
    from .tasks import _build_search_plan, _extract_topic

    history = await get_messages(task.id, page=1, per_page=100)
    research_text = _conversation_research_text(history)
    deterministic_plan = _vla_trace_plan(research_text) or _embodied_brain_trace_plan(research_text)
    if deterministic_plan and (not task.search_plan or _plan_seems_generic(task.search_plan)):
        task.search_plan = deterministic_plan
        task.query = deterministic_plan["task_title"]
        task.sources = [PaperSource(s) for s in deterministic_plan["sources"]]
        task.updated_at = datetime.now()
        await update_task(task)
        return task

    if task.search_plan:
        return task

    if research_text:
        extracted_topic = await _extract_topic(research_text)
        if extracted_topic and not _is_greeting_or_control(extracted_topic):
            task.query = extracted_topic

    try:
        task, _ = await _build_search_plan(task, insert_plan_message=False)
        if task.search_plan and task.search_plan.get("task_title"):
            task.query = str(task.search_plan["task_title"]).strip()
        return task
    except Exception:
        fallback_query = (research_text or task.query).strip() or "academic paper search"
        if len(fallback_query) > 220:
            fallback_query = fallback_query[-220:]
        fallback_title = await _extract_topic(fallback_query)
        if not fallback_title or _is_greeting_or_control(fallback_title):
            fallback_title = "论文检索任务"
        task.search_plan = {
            "query": fallback_query,
            "task_title": fallback_title[:30],
            "search_mode": "broad_exploration",
            "goal": f"围绕 {fallback_query} 检索相关论文",
            "domain": fallback_title,
            "clarifying_questions": [],
            "sources": [s.value if hasattr(s, "value") else str(s) for s in task.sources] or [
                "arxiv", "semantic_scholar", "openalex", "crossref"
            ],
            "filters": {},
            "core_concepts": [fallback_query],
            "field_terms": [],
            "exclude_terms": [],
            "preferred_paper_types": ["survey", "foundation", "method", "benchmark"],
            "subtopics": [{
                "name": fallback_query,
                "intent": f"检索 {fallback_query} 的代表性论文、基础论文和近期进展",
                "required_terms": [fallback_query],
                "optional_terms": [],
                "queries": {
                    "arxiv": fallback_query,
                    "semantic_scholar": fallback_query,
                    "openalex": fallback_query,
                    "crossref": fallback_query,
                },
            }],
            "queries": {
                "arxiv": fallback_query,
                "semantic_scholar": fallback_query,
                "openalex": fallback_query,
                "crossref": fallback_query,
            },
            "summary": "已使用兜底方案启动检索，后续可在论文库中继续筛选。",
        }
        task.query = fallback_title[:30]
        task.updated_at = datetime.now()
        await update_task(task)
        return task


async def _trigger_workflow(task: Task, reply_content: str | None = None) -> dict:
    """直接触发 Agent 工作流"""
    import asyncio
    from ..crew.paper_crew import PaperCrew
    from .tasks import _running_crews, _run_crew

    task_id = task.id

    task = await _ensure_search_plan(task)

    # 如果有搜索方案，把完整研究意图放入 filters，保留原始 task.query。
    if task.search_plan:
        task.filters = {**dict(task.filters), "_research_intent": task.search_plan}
        if task.search_plan.get("task_title"):
            task.query = str(task.search_plan["task_title"]).strip()
        if task.search_plan.get("sources"):
            task.sources = [PaperSource(s) for s in task.search_plan["sources"]]
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
