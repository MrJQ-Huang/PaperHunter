from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid

from ..models.task import Task, TaskStatus
from ..models.paper import PaperSource
from ..models.message import Message, MessageRole
from ..database import insert_task, get_task, get_tasks, update_task, delete_task, insert_message
from ..crew.paper_crew import PaperCrew

router = APIRouter()

# 运行中的 Crew 实例（用于终止）
_running_crews: dict[str, PaperCrew] = {}


class CreateTaskRequest(BaseModel):
    query: str
    sources: list[str] = ["arxiv", "semantic_scholar", "openalex", "crossref"]
    filters: dict = {}


@router.post("/tasks")
async def create_task(req: CreateTaskRequest):
    """创建任务，但不自动执行，等待用户确认"""
    # 先提取纯研究主题（去掉客套话）
    clean_query = await _extract_topic(req.query)

    task = Task(
        id=str(uuid.uuid4()),
        query=clean_query,
        sources=[PaperSource(s) for s in req.sources],
        filters=req.filters,
        status=TaskStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    await insert_task(task)

    # 用 LLM 生成有针对性的欢迎消息（传入原始输入和提取后的主题）
    welcome_content, suggestions = await _generate_welcome(clean_query)

    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task.id,
        role=MessageRole.AGENT,
        content=welcome_content,
        suggestions=suggestions,
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)

    return task.model_dump()


async def _extract_topic(user_input: str) -> str:
    """从用户的自然语言中提取纯研究主题，去掉客套话和指令性语句"""
    import aiohttp
    from ..config import settings

    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 128,
        "system": "从用户的输入中提取核心研究主题关键词，去掉客套话和指令性语句。只输出研究主题本身，不要解释。\n\n示例：\n输入：请你帮我检索 时域天线测量以及探头补偿的相关论文\n输出：时域天线测量 探头补偿\n\n输入：找一下transformer在NLP中的应用\n输出：transformer NLP 应用\n\n输入：search for papers about deep learning in medical imaging\n输出：deep learning medical imaging",
        "messages": [
            {"role": "user", "content": user_input}
        ],
    }

    url = f"{settings.llm_base_url}/v1/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return user_input
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        result = content.strip().strip('"').strip("'")
        return result if result else user_input

    except Exception:
        return user_input


async def _generate_welcome(query: str) -> tuple[str, list[str]]:
    """用 LLM 分析用户查询，生成有针对性的欢迎消息"""
    import json
    import aiohttp
    from ..config import settings

    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "system": """你是 PaperHunter 的学术搜索助手。用户输入了一个论文检索需求，你需要：

1. 理解并用专业的学术语言复述用户的研究需求
2. 拆解出 2-3 个具体的子研究方向
3. 给出搜索策略建议（时间范围、文献类型等）
4. 提供 2-4 个贴合该研究主题的快捷回复选项

回复格式（严格遵守）：
先写正文（150字以内，中文），然后换行写：
[SUGGESTIONS: ["选项1", "选项2", "选项3"]]""",
        "messages": [
            {"role": "user", "content": f"我的论文检索需求：{query}"}
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
                    raise Exception(f"API error {resp.status}")
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        # 提取建议
        import re
        suggestions = []
        match = re.search(r'\[SUGGESTIONS?:\s*(\[.*\])\s*\]', content, re.IGNORECASE)
        if match:
            try:
                suggestions = json.loads(match.group(1))
            except json.JSONDecodeError:
                raw = match.group(1).strip("[]")
                suggestions = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()]
        else:
            match = re.search(r'\[SUGGESTIONS?:\s*(.+?)\]', content, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                if not raw.startswith("["):
                    suggestions = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()]
        content = re.sub(r'\[SUGGESTIONS?:\s*\[.*?\]\s*\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[SUGGESTIONS?:\s*.*?\]', '', content, flags=re.IGNORECASE)
        content = content.strip()

        if not suggestions:
            suggestions = ["搜索最新3年的研究", "需要高引用经典论文", "全面搜索，不限条件", "只看开放获取的论文"]

        return content, suggestions

    except Exception:
        return (
            f"收到！你想要搜索关于「{query}」的论文。\n\n"
            "请告诉我你的具体需求：重点关注哪些方向？时间范围？需要经典文献还是最新前沿？\n"
            "确认后我会开始全面搜索。",
            ["搜索最新3年的研究", "搜索高引用经典论文", "全面搜索，不限条件", "只看开放获取的论文"],
        )


@router.post("/tasks/{task_id}/generate-plan")
async def generate_plan(task_id: str):
    """从对话历史生成结构化搜索方案"""
    import json
    import aiohttp
    from ..config import settings
    from ..database import get_messages

    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.PAUSED):
        raise HTTPException(status_code=400, detail=f"Task status is {task.status.value}, cannot generate plan")

    # 读取对话历史
    history = await get_messages(task_id, page=1, per_page=50)
    conversation = []
    for msg in history:
        role = "用户" if msg.role == MessageRole.USER else "助手"
        conversation.append(f"{role}: {msg.content}")
    conversation_text = "\n".join(conversation)

    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": settings.llm_model,
        "max_tokens": 512,
        "system": """你是学术搜索方案分析师。根据用户和助手的对话历史，提取结构化的搜索方案。

你必须输出纯 JSON，不要输出任何其他内容。格式如下：
{
  "query": "核心搜索关键词，英文，用空格分隔，不超过8个词",
  "sources": ["arxiv", "semantic_scholar", "openalex", "crossref"],
  "filters": {
    "year_min": null,
    "only_oa": false
  },
  "summary": "一句话描述搜索策略，中文，30字以内"
}

规则：
- query 必须是英文关键词，适合直接提交给学术数据库 API
- 如果用户说了中文，翻译为英文
- sources 默认四个全选，除非用户明确排除
- filters 中 year_min 为 null 表示不限年份，only_oa 为 true 表示只要开放获取
- summary 用中文简述搜索策略""",
        "messages": [
            {"role": "user", "content": f"对话历史：\n{conversation_text}\n\n请提取结构化搜索方案（纯JSON）："}
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
                    raise Exception(f"LLM API error {resp.status}")
                data = await resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        # 提取 JSON
        content = content.strip()
        # 尝试从 markdown code block 中提取
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        elif not content.startswith('{'):
            # 尝试找到第一个 { 到最后一个 }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]

        plan = json.loads(content)

        # 验证必需字段
        if not plan.get("query"):
            raise Exception("LLM 返回的方案缺少 query 字段")

        # 存入 task
        task.search_plan = plan
        task.updated_at = datetime.now()
        await update_task(task)

        # 发送方案消息给用户
        sources_str = ", ".join(plan.get("sources", []))
        filters_desc = []
        if plan.get("filters", {}).get("year_min"):
            filters_desc.append(f"{plan['filters']['year_min']}年至今")
        if plan.get("filters", {}).get("only_oa"):
            filters_desc.append("仅开放获取")
        filters_str = "、".join(filters_desc) if filters_desc else "无特殊限制"

        msg = Message(
            id=str(uuid.uuid4()),
            task_id=task_id,
            role=MessageRole.AGENT,
            content=f"搜索方案已生成：\n\n"
                    f"搜索词：{plan['query']}\n"
                    f"数据源：{sources_str}\n"
                    f"筛选条件：{filters_str}\n"
                    f"策略说明：{plan.get('summary', '')}",
            suggestions=["确认搜索", "调整方案"],
            timestamp=datetime.now(),
            agent_name="Chat Agent",
        )
        await insert_message(msg)

        return task.model_dump()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成方案失败: {str(e)}")


@router.post("/tasks/{task_id}/reset-plan")
async def reset_plan(task_id: str):
    """清除搜索方案，回到对话状态"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.search_plan = None
    task.updated_at = datetime.now()
    await update_task(task)

    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content="方案已清除。请继续告诉我你的搜索需求，准备好了再生成新方案。",
        suggestions=["生成搜索方案"],
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)

    return task.model_dump()


@router.post("/tasks/{task_id}/confirm")
async def confirm_task(task_id: str):
    """用户确认后启动 Agent 搜索流程"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.PAUSED):
        raise HTTPException(status_code=400, detail=f"Task status is {task.status.value}, cannot start")

    # 如果有搜索方案，用方案中的 query 覆盖
    if task.search_plan:
        plan = task.search_plan
        if plan.get("query"):
            task.query = plan["query"]
        if plan.get("filters"):
            merged_filters = dict(task.filters)
            merged_filters.update(plan["filters"])
            task.filters = merged_filters
        if plan.get("sources"):
            task.sources = [PaperSource(s) for s in plan["sources"]]
        await update_task(task)

    # 发送确认消息
    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=f"好的，以「{task.query}」为主题开始搜索论文！请稍候...",
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)

    # 启动 CrewAI 流程
    crew = PaperCrew(task)
    _running_crews[task_id] = crew
    import asyncio
    asyncio.create_task(_run_crew(task_id, crew))

    return {"message": "Task started", "task_id": task_id}


async def _run_crew(task_id: str, crew: PaperCrew):
    """运行 Crew 并清理"""
    try:
        await crew.run()
    finally:
        _running_crews.pop(task_id, None)


@router.post("/tasks/{task_id}/terminate")
async def terminate_task(task_id: str):
    """终止正在运行的任务"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 终止 Crew
    crew = _running_crews.get(task_id)
    if crew:
        crew.terminate()
        _running_crews.pop(task_id, None)

    task.status = TaskStatus.CANCELLED
    task.updated_at = datetime.now()
    await update_task(task)

    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content="任务已终止。你可以重新开始或调整搜索条件。",
        suggestions=["重新搜索", "修改条件后搜索"],
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)

    return {"message": "Task terminated", "task_id": task_id}


@router.post("/tasks/{task_id}/reset")
async def reset_task(task_id: str):
    """重置任务，回到待确认状态"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 先终止正在运行的 Crew
    crew = _running_crews.get(task_id)
    if crew:
        crew.terminate()
        _running_crews.pop(task_id, None)

    task.status = TaskStatus.PENDING
    task.total_papers_found = 0
    task.papers_after_filter = 0
    task.papers_downloaded = 0
    task.papers_failed = 0
    task.error_message = None
    task.updated_at = datetime.now()
    await update_task(task)

    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=f"已重置任务「{task.query}」。请告诉我新的搜索要求，确认后重新开始。",
        suggestions=["按原条件重新搜索", "扩大搜索范围", "缩小搜索范围"],
        timestamp=datetime.now(),
        agent_name="Chat Agent",
    )
    await insert_message(msg)

    return {"message": "Task reset", "task_id": task_id}


@router.get("/tasks")
async def list_tasks():
    tasks = await get_tasks()
    return [t.model_dump() for t in tasks]


@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: str):
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 从 papers 表实时统计，和 Settings 页面用同一个数据源
    from ..database import get_paper_stats_for_task
    stats = await get_paper_stats_for_task(task_id)
    if stats["total"] > 0:
        task.total_papers_found = stats["total"]
        task.papers_downloaded = stats["downloaded"]
        task.papers_failed = stats["failed"]

    result = task.model_dump()
    # 附加 Agent 状态（根据任务状态推导，刷新页面后恢复）
    result["agent_statuses"] = _derive_agent_statuses(task.status.value)
    return result


def _derive_agent_statuses(task_status: str) -> dict:
    """根据任务状态推导各 Agent 的状态"""
    if task_status == "running":
        return {
            "search": {"agent": "search", "status": "working", "message": "搜索中..."},
            "filter": {"agent": "filter", "status": "idle", "message": "等待搜索完成"},
            "download": {"agent": "download", "status": "idle", "message": "等待筛选完成"},
            "chat": {"agent": "chat", "status": "working", "message": "任务执行中"},
        }
    elif task_status == "completed":
        return {
            "search": {"agent": "search", "status": "done", "message": "搜索完成"},
            "filter": {"agent": "filter", "status": "done", "message": "筛选完成"},
            "download": {"agent": "download", "status": "done", "message": "下载完成"},
            "chat": {"agent": "chat", "status": "done", "message": "任务完成"},
        }
    elif task_status == "failed":
        return {
            "search": {"agent": "search", "status": "error", "message": "任务失败"},
            "filter": {"agent": "filter", "status": "error", "message": "任务失败"},
            "download": {"agent": "download", "status": "error", "message": "任务失败"},
            "chat": {"agent": "chat", "status": "error", "message": "任务失败"},
        }
    elif task_status == "cancelled":
        return {
            "search": {"agent": "search", "status": "idle", "message": "已取消"},
            "filter": {"agent": "filter", "status": "idle", "message": "已取消"},
            "download": {"agent": "download", "status": "idle", "message": "已取消"},
            "chat": {"agent": "chat", "status": "idle", "message": "已取消"},
        }
    else:  # pending, paused
        return {
            "search": {"agent": "search", "status": "idle", "message": "等待中..."},
            "filter": {"agent": "filter", "status": "idle", "message": "等待中..."},
            "download": {"agent": "download", "status": "idle", "message": "等待中..."},
            "chat": {"agent": "chat", "status": "idle", "message": "等待中..."},
        }


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = TaskStatus.PAUSED
    await update_task(task)
    return task.model_dump()


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = TaskStatus.RUNNING
    await update_task(task)
    return task.model_dump()


@router.delete("/tasks/{task_id}")
async def remove_task(task_id: str):
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 终止正在运行的 Crew
    crew = _running_crews.pop(task_id, None)
    if crew:
        crew.terminate()

    # 删除关联消息
    from ..database import delete_task_messages
    await delete_task_messages(task_id)

    # 删除任务
    await delete_task(task_id)
    return {"message": "Task deleted", "task_id": task_id}
