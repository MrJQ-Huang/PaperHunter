from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid
import json

from ..models.task import Task, TaskStatus
from ..models.paper import PaperSource
from ..models.message import Message, MessageRole
from ..database import insert_task, get_task, get_tasks, update_task, delete_task, insert_message
from ..crew.paper_crew import PaperCrew
from ..services.search_planning_service import prepare_search_execution

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

    user_msg = Message(
        id=str(uuid.uuid4()),
        task_id=task.id,
        role=MessageRole.USER,
        content=req.query,
        suggestions=[],
        timestamp=datetime.now(),
    )
    await insert_message(user_msg)

    # 用 LLM 生成有针对性的欢迎消息（传入原始输入和提取后的主题）
    welcome_content, suggestions = await _generate_welcome(clean_query, req.query)

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
    from ..utils.llm_client import call_llm

    try:
        content = await call_llm(
            [{"role": "user", "content": user_input}],
            system="从用户输入中提取论文检索主题。去掉客套话和纯操作话，但必须保留研究对象、已给出的子方向、时间/排序要求，以及“忘了/不确定/帮我想/待确认”这类补全线索。只输出适合作为任务标题的短语，不要解释。\n\n示例：\n输入：请你帮我检索 时域天线测量以及探头补偿的相关论文\n输出：时域天线测量 探头补偿\n\n输入：找一下transformer在NLP中的应用\n输出：transformer NLP 应用\n\n输入：你好 我想找具身智能领域的大脑的三个大类的论文，一个是VLA 一个是世界模型 还有一个我忘了。按起始时间到现在的顺序来找\n输出：具身智能大脑 VLA 世界模型 第三方向待确认 时间线论文\n\n输入：search for papers about deep learning in medical imaging\n输出：deep learning medical imaging",
            max_tokens=128,
            timeout=10,
        )

        result = content.strip().strip('"').strip("'")
        return result if result else user_input

    except Exception:
        return user_input


async def _generate_welcome(query: str, original_input: str | None = None) -> tuple[str, list[str]]:
    """用 LLM 分析用户查询，生成有针对性的欢迎消息"""
    import json
    from ..utils.llm_client import call_llm

    system = """你是 PaperHunter 的学术搜索助手。用户刚开始一个新的论文检索任务，你需要处理好首轮复杂输入。

1. 理解并用专业的学术语言复述用户的研究需求
2. 拆解出 2-4 个具体的子研究方向
3. 给出搜索策略建议（时间范围、文献类型等）
4. 提供 2-4 个贴合该研究主题的快捷回复选项
5. 如果用户说“忘了/不确定/你帮我想/还有一个想不起来”，不要只反问；要给出 3-5 个高概率候选方向，并说明推荐默认候选
6. 如果输入中已经有明确方向，要复述“已确认方向”和“待确认方向”，不要把待确认方向当作已经确认
7. 对首轮输入要尽量友好地帮助用户补全，而不是让用户重新解释第一句话
8. 如果用户要“按起始时间到现在/发展脉络/时间线”检索，要明确会覆盖奠基论文、综述论文和最新代表工作

回复格式（严格遵守）：
先写正文（150字以内，中文），然后换行写：
[SUGGESTIONS: ["选项1", "选项2", "选项3"]]"""

    try:
        content = await call_llm(
            [{"role": "user", "content": f"原始输入：{original_input or query}\n\n提取后的主题：{query}"}],
            system=system,
            max_tokens=1024,
            timeout=20,
        )

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


class UpdateTaskRequest(BaseModel):
    query: str | None = None


@router.patch("/tasks/{task_id}")
async def update_task_fields(task_id: str, req: UpdateTaskRequest):
    """更新任务的部分字段（如 query）"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if req.query:
        task.query = req.query.strip()
    task.updated_at = datetime.now()
    await update_task(task)
    return task.model_dump()


@router.post("/tasks/{task_id}/generate-plan")
async def generate_plan(task_id: str):
    """从对话历史生成结构化搜索方案"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.PAUSED):
        raise HTTPException(status_code=400, detail=f"Task status is {task.status.value}, cannot generate plan")
    if task.search_plan:
        return task.model_dump()

    try:
        task, plan = await _build_search_plan(task, insert_plan_message=True)
        return task.model_dump()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回的内容无法解析为 JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成方案失败: {str(e)}")


async def _build_search_plan(task: Task, insert_plan_message: bool = True) -> tuple[Task, dict]:
    """从对话生成计划并写入 task。供显式按钮和聊天确认自动启动共用。"""
    import json
    from ..database import get_messages
    from ..utils.llm_client import call_llm
    from ..utils.plan_repairer import repair_search_plan
    from ..utils.plan_validator import validate_search_plan

    # 读取对话历史（只取最近 6 条，每条截断 100 字，减少 token 用量）
    history = await get_messages(task.id, page=1, per_page=50)
    recent = history[-10:] if len(history) > 10 else history
    conversation = []
    for msg in recent:
        role = "用户" if msg.role == MessageRole.USER else "助手"
        text = msg.content[:300] if len(msg.content) > 300 else msg.content
        conversation.append(f"{role}: {text}")
    conversation_text = "\n".join(conversation)

    system = """从对话中提取论文检索方案，输出纯 JSON。不要只生成一个短关键词，要构建可执行的研究意图画像。

JSON 格式：
{
  "query": "保留用户核心主题的英文检索标题，不限制 6 词",
  "task_title": "适合显示在任务栏的中文标题，30字以内",
  "search_mode": "beginner_learning | authoritative_core | recent_sota | subtopic_deep_dive | broad_exploration",
  "goal": "用户本次检索的真实目标",
  "domain": "英文领域名称",
  "clarifying_questions": ["如果仍缺信息，后续最应该问用户的问题"],
  "sources": ["arxiv","semantic_scholar","openalex","crossref"],
  "filters": {"year_min": null, "only_oa": false},
  "core_concepts": ["核心概念"],
  "field_terms": ["领域术语"],
  "exclude_terms": ["歧义排除词"],
  "preferred_paper_types": ["survey","foundation","benchmark","method","system"],
  "subtopics": [
    {
      "name": "子方向英文名",
      "intent": "该子方向要召回什么",
      "required_terms": ["必须相关术语"],
      "optional_terms": ["同义词/相关术语/代表系统"],
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
  "summary": "面向用户的简短策略说明",
  "annotation_policy": {
    "paper_types": ["survey","benchmark","dataset","method","system","application","theory"],
    "learning_roles": ["field_overview","foundation","representative_method","recent_frontier","benchmark_or_dataset","implementation_reference"]
  }
}

策略要求：
1. 如果用户说自己是新手、想入门、想了解某领域，search_mode 用 beginner_learning，优先综述、基础论文、代表系统、benchmark、近年前沿。
2. 如果用户只给模糊缩写或宽泛领域，clarifying_questions 给出 3 个主动追问，但仍要生成一个可先执行的模糊探索方案。
3. 不要强迫所有 query 都包含缩写词；要覆盖同义表达、上位概念和代表系统名。
4. 对缩写歧义要给 exclude_terms，例如 VLA 排除 Very Large Array、radio astronomy、telescope。
5. subtopics 生成 4-7 个，每个 query 尽量互补。
6. 只输出 JSON。"""

    try:
        content = await call_llm(
            [{"role": "user", "content": f"对话：\n{conversation_text}\n\n输出JSON："}],
            system=system,
            max_tokens=4096,
            timeout=60,
        )

        if not content.strip():
            # 打印完整响应帮助调试
            import logging
            logging.warning("LLM 返回空内容")
            raise Exception("LLM 返回空内容")

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
        plan.setdefault("task_title", plan.get("domain") or plan["query"])
        plan.setdefault("sources", ["arxiv", "semantic_scholar", "openalex", "crossref"])
        plan.setdefault("filters", {})
        plan.setdefault("search_mode", "broad_exploration")
        plan.setdefault("goal", plan.get("summary") or f"检索 {plan['query']} 相关论文")
        plan.setdefault("domain", plan["query"])
        plan.setdefault("core_concepts", plan["query"].split()[:3])
        plan.setdefault("field_terms", [])
        plan.setdefault("exclude_terms", [])
        plan.setdefault("preferred_paper_types", ["survey", "foundation", "method", "benchmark"])
        plan.setdefault("clarifying_questions", [])
        if not plan.get("queries"):
            plan["queries"] = {
                "arxiv": plan["query"],
                "semantic_scholar": plan["query"],
                "openalex": plan["query"],
                "crossref": plan["query"],
            }
        if not plan.get("subtopics"):
            plan["subtopics"] = [{
                "name": plan["query"],
                "intent": plan["goal"],
                "required_terms": plan.get("core_concepts", []),
                "optional_terms": plan.get("field_terms", []),
                "queries": plan["queries"],
            }]

        validation = validate_search_plan(plan)
        if validation.blocking:
            plan = await repair_search_plan(conversation_text, plan, validation.issues)
            validation = validate_search_plan(plan)
            if validation.blocking:
                raise Exception(f"搜索方案无法安全执行: {', '.join(validation.issues)}")
            if validation.warnings:
                plan.setdefault("warnings", [])
                for warning in validation.warnings:
                    if warning not in plan["warnings"]:
                        plan["warnings"].append(warning)

        # 存入 task
        task.search_plan = plan
        if plan.get("task_title"):
            task.query = str(plan["task_title"]).strip()
        task.updated_at = datetime.now()
        await update_task(task)

        # 发送方案消息给用户
        if insert_plan_message:
            sources_str = ", ".join(plan.get("sources", []))
            filters_desc = []
            if plan.get("filters", {}).get("year_min"):
                filters_desc.append(f"{plan['filters']['year_min']}年至今")
            if plan.get("filters", {}).get("only_oa"):
                filters_desc.append("仅开放获取")
            filters_str = "、".join(filters_desc) if filters_desc else "无特殊限制"

            msg = Message(
                id=str(uuid.uuid4()),
                task_id=task.id,
                role=MessageRole.AGENT,
                content=f"搜索方案已生成：\n\n"
                        f"标题：{task.query}\n"
                        f"目标：{plan.get('goal', plan['query'])}\n"
                        f"模式：{plan.get('search_mode', 'broad_exploration')}\n"
                        f"子方向：{', '.join([s.get('name', '') for s in plan.get('subtopics', [])[:5] if s.get('name')])}\n"
                        f"排除歧义：{', '.join(plan.get('exclude_terms', [])[:5]) or '无'}\n"
                        f"数据源：{sources_str}\n"
                        f"筛选条件：{filters_str}\n"
                        f"策略说明：{plan.get('summary', '')}",
                suggestions=["确认搜索", "调整方案"],
                timestamp=datetime.now(),
                agent_name="Chat Agent",
            )
            await insert_message(msg)

        return task, plan

    except json.JSONDecodeError as e:
        raise
    except Exception as e:
        raise


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
        content="方案已清除。请继续告诉我你的搜索需求，准备好了可以直接说“开始搜索”。",
        suggestions=["继续补充需求", "开始搜索"],
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

    try:
        task, _ = await prepare_search_execution(task, plan_builder=_build_search_plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"搜索方案无法安全执行: {str(e)}")

    task.status = TaskStatus.RUNNING
    task.updated_at = datetime.now()
    await update_task(task)

    # 发送确认消息
    msg = Message(
        id=str(uuid.uuid4()),
        task_id=task_id,
        role=MessageRole.AGENT,
        content=f"任务已启动：{task.query}\n正在构建检索图谱并按分支搜索论文。",
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
    from ..utils.download_state import sync_download_file_state_for_scope
    await sync_download_file_state_for_scope(task_id)
    stats = await get_paper_stats_for_task(task_id)
    if stats["total"] > 0:
        task.total_papers_found = stats["total"]
        task.papers_downloaded = stats["downloaded"]
        task.papers_failed = stats["failed"]

    result = task.model_dump()
    # 附加 Agent 状态（根据任务状态推导，刷新页面后恢复）
    result["agent_statuses"] = _derive_agent_statuses(task)
    return result


def _derive_agent_statuses(task: Task) -> dict:
    """根据任务状态推导各 Agent 的状态"""
    task_status = task.status.value
    found = task.total_papers_found or 0
    annotated = task.papers_after_filter or 0

    if task_status == "running":
        if found > 0:
            filter_done = annotated > 0
            return {
                "search": {"agent": "search", "status": "done", "message": f"已入库 {found} 篇论文", "progress": 100},
                "filter": {
                    "agent": "filter",
                    "status": "done" if filter_done else "working",
                    "message": f"语义标注完成 {annotated} 篇" if filter_done else "后台语义标注中，论文已可查看",
                    "progress": 100 if filter_done else None,
                },
                "download": {"agent": "download", "status": "idle", "message": "等待用户筛选"},
                "chat": {
                    "agent": "chat",
                    "status": "working",
                    "message": "论文已入库，可先筛选；后台处理中" if not filter_done else "等待筛选",
                },
            }
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
    elif task_status == "reviewing":
        return {
            "search": {
                "agent": "search",
                "status": "done",
                "message": f"搜索完成，已入库 {found} 篇" if found else "搜索完成",
                "progress": 100,
            },
            "filter": {
                "agent": "filter",
                "status": "done" if annotated else "idle",
                "message": f"标注完成 {annotated} 篇，等待筛选" if annotated else "等待用户筛选",
                "progress": 100 if annotated else None,
            },
            "download": {"agent": "download", "status": "idle", "message": "等待用户确认"},
            "chat": {"agent": "chat", "status": "idle", "message": "待筛选"},
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


class DownloadRequest(BaseModel):
    paper_ids: list[str] | None = None


@router.post("/tasks/{task_id}/download")
async def download_task_papers(task_id: str, body: DownloadRequest | None = None):
    """下载该任务的论文（全部或指定 ID 列表）"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from ..database import get_papers, get_paper
    from ..utils.download_state import sync_download_file_state, sync_download_file_states

    if body and body.paper_ids:
        # 下载指定论文
        papers = []
        for pid in body.paper_ids:
            p = await get_paper(pid)
            p = await sync_download_file_state(p)
            if p and p.download_status in ("pending", "failed"):
                papers.append(p)
    else:
        # 下载该任务所有待下载的论文
        all_papers, _ = await get_papers(task_id=task_id, per_page=10000)
        all_papers = await sync_download_file_states(all_papers)
        papers = [p for p in all_papers if p.download_status in ("pending", "failed")]

    if not papers:
        raise HTTPException(status_code=400, detail="没有需要下载的论文")

    # 异步启动下载
    crew = PaperCrew(task)
    _running_crews[task_id] = crew
    import asyncio
    asyncio.create_task(_run_download(task_id, crew, papers))

    return {"message": f"开始下载 {len(papers)} 篇论文", "count": len(papers)}


async def _run_download(task_id: str, crew: PaperCrew, papers):
    """运行下载并清理"""
    try:
        await crew.download_selected(papers)
    finally:
        _running_crews.pop(task_id, None)


@router.post("/tasks/{task_id}/agent-filter")
async def agent_filter(task_id: str):
    """让 Agent 对该任务的论文做 LLM 评分排序（不删除任何论文）"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from ..database import get_papers, update_paper_download
    from ..utils.llm_scorer import llm_score_papers

    papers, total = await get_papers(task_id=task_id, per_page=10000)
    if not papers:
        raise HTTPException(status_code=400, detail="该任务没有论文")

    # LLM 评分
    import json
    intent = task.filters.get("_execution_plan") or task.search_plan or task.filters.get("_research_intent") or {"query": task.query}
    scoring_query = json.dumps(intent, ensure_ascii=False) if isinstance(intent, dict) else task.query
    scores = await llm_score_papers(scoring_query, papers)
    score_map = {s["paper_id"]: s for s in scores}

    updated = 0
    for p in papers:
        result = score_map.get(p.id)
        if result:
            new_score = result["relevance"]
            await update_paper_download(p.id, p.local_pdf_path or "", p.download_status or "pending")
            # 更新 relevance_score 和标注标签
            from ..database import update_paper
            subtopics = result.get("subtopics") or p.subtopics
            method_tags = result.get("method_tags") or p.method_tags
            quality_tags = result.get("quality_tags") or p.quality_tags
            await update_paper(
                p.id,
                relevance_score=new_score,
                paper_type=result.get("paper_type") or p.paper_type,
                subtopics=json.dumps(subtopics, ensure_ascii=False),
                learning_role=result.get("learning_role") or p.learning_role,
                difficulty=result.get("difficulty") or p.difficulty,
                method_tags=json.dumps(method_tags, ensure_ascii=False),
                quality_tags=json.dumps(quality_tags, ensure_ascii=False),
                annotation_reason=result.get("reason") or p.annotation_reason,
            )
            updated += 1

    return {"message": f"已对 {updated} 篇论文完成评分", "count": updated}


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
