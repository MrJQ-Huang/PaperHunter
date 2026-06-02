import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from crewai import Crew, Process

from ..models.task import Task, TaskStatus
from ..models.paper import Paper, PaperSource
from ..models.message import Message, MessageRole
from ..agents.search_agent import create_search_agent
from ..agents.filter_agent import create_filter_agent
from ..agents.download_agent import create_download_agent
from ..agents.chat_agent import create_chat_agent
from .workflows import (
    create_search_task,
    create_filter_task,
    create_download_task,
    create_chat_summary_task,
)
from ..tools.arxiv_tool import search_arxiv
from ..tools.semantic_scholar_tool import search_semantic_scholar
from ..tools.openalex_tool import search_openalex
from ..tools.crossref_tool import search_crossref
from ..tools.google_scholar_tool import search_google_scholar
from ..tools.pdf_download_tool import download_pdf
from ..utils.dedup import deduplicate
from ..database import (
    insert_task, update_task, insert_papers, insert_message,
    get_paper, update_paper_download, update_task_download_stats,
)
from ..api.websocket import broadcast_agent_status, broadcast_agent_log
from ..config import settings


class PaperCrew:
    """主编排器：协调 4 个 Agent 完成论文搜索-筛选-下载流程"""

    def __init__(self, task: Task):
        self.task = task
        self._terminated = False

    def terminate(self):
        """终止执行"""
        self._terminated = True

    async def _check_terminated(self) -> bool:
        """检查是否被终止"""
        if self._terminated:
            self.task.status = TaskStatus.CANCELLED
            await update_task(self.task)
            await self._notify("chat", "idle", "任务已终止")
            return True
        return False

    async def run(self):
        """执行完整工作流"""
        try:
            # 更新任务状态
            self.task.status = TaskStatus.RUNNING
            await update_task(self.task)
            await self._notify("chat", "working", "任务开始执行...")

            # Step 1: 搜索
            await self._notify("search", "working", "正在多源搜索论文...")
            papers = await self._search_phase()
            if await self._check_terminated():
                return
            self.task.total_papers_found = len(papers)
            await update_task(self.task)
            await self._notify("search", "done", f"搜索完成，找到 {len(papers)} 篇论文", 100)

            if not papers:
                await self._send_chat("未找到相关论文，请尝试调整搜索关键词。")
                self.task.status = TaskStatus.COMPLETED
                await update_task(self.task)
                return

            # 保存搜索结果到数据库（关联当前任务）
            for p in papers:
                p.task_id = self.task.id
            await insert_papers(papers)

            # Step 2: 筛选
            if await self._check_terminated():
                return
            await self._notify("filter", "working", "正在智能筛选论文...")
            await self._log("filter", "开始智能筛选...")
            filtered_papers = await self._filter_phase(papers)
            self.task.papers_after_filter = len(filtered_papers)
            await update_task(self.task)
            await self._log("filter", f"✓ 筛选完成，推荐 {len(filtered_papers)} 篇论文")
            await self._notify("filter", "done", f"筛选完成，推荐 {len(filtered_papers)} 篇论文", 100)

            # 向用户展示筛选结果
            await self._send_chat(
                f"筛选完成！从 {len(papers)} 篇论文中推荐了 {len(filtered_papers)} 篇高质量论文。",
                suggestions=["全部下载", "只下载前10篇", "查看推荐列表", "终止任务"],
            )

            # Step 3: 下载
            if await self._check_terminated():
                return
            await self._notify("download", "working", "正在下载论文 PDF...")
            await self._log("download", f"开始下载 {len(filtered_papers)} 篇论文 PDF...")
            download_results = await self._download_phase(filtered_papers)
            self.task.papers_downloaded = download_results["success"]
            self.task.papers_failed = download_results["failed"]
            await update_task(self.task)
            await self._notify("download", "done", f"下载完成: {download_results['success']} 成功, {download_results['failed']} 失败", 100)

            # Step 4: 汇报
            await self._send_chat(
                f"任务完成！\n"
                f"- 搜索到 {self.task.total_papers_found} 篇论文\n"
                f"- 推荐 {self.task.papers_after_filter} 篇\n"
                f"- 成功下载 {self.task.papers_downloaded} 篇\n"
                f"- 下载失败 {self.task.papers_failed} 篇",
                suggestions=["查看论文库", "开始新搜索"],
            )

            self.task.status = TaskStatus.COMPLETED
            await update_task(self.task)

        except Exception as e:
            self.task.status = TaskStatus.FAILED
            self.task.error_message = str(e)
            await update_task(self.task)
            await self._notify("chat", "error", f"任务执行失败: {str(e)}")
            await self._send_chat(f"抱歉，任务执行过程中出现错误: {str(e)}")

    async def _search_phase(self) -> list[Paper]:
        """多源并行搜索"""
        from ..utils.query_translator import translate_query, expand_query

        sources = self.task.sources or [PaperSource.ARXIV, PaperSource.SEMANTIC_SCHOLAR, PaperSource.OPENALEX, PaperSource.CROSSREF]
        original_query = self.task.query

        # 判断是否需要翻译：如果已经是英文关键词，跳过翻译
        ascii_ratio = sum(1 for c in original_query if ord(c) < 128) / max(len(original_query), 1)
        needs_translate = ascii_ratio < 0.7  # 超过 70% 是 ASCII 则视为英文

        if needs_translate:
            await self._notify("search", "working", "正在翻译检索词...")
            await self._log("search", "正在翻译检索词...")
            translated = await translate_query(original_query)
            await self._log("search", f"✓ 检索词已翻译: {translated}")
            await self._send_chat(f"已将检索词翻译为：{translated}")
        else:
            translated = original_query
            await self._log("search", f"✓ 检索词已是英文，跳过翻译: {translated}")

        # 扩展为多个查询变体
        queries = await expand_query(translated)
        if len(queries) > 1:
            await self._log("search", f"✓ 扩展为 {len(queries)} 组检索词")
            await self._send_chat(f"扩展了 {len(queries)} 组检索词以提高覆盖率")

        # 用所有查询变体并行搜索
        source_map = {
            PaperSource.ARXIV: search_arxiv,
            PaperSource.SEMANTIC_SCHOLAR: search_semantic_scholar,
            PaperSource.OPENALEX: search_openalex,
            PaperSource.CROSSREF: search_crossref,
            PaperSource.GOOGLE_SCHOLAR: search_google_scholar,
        }

        search_funcs = []
        search_meta = []  # 记录每个搜索的来源和查询
        for q in queries:
            for source in sources:
                if source in source_map:
                    search_funcs.append(source_map[source](q))
                    search_meta.append((source, q))

        # 并行执行
        results = await asyncio.gather(*search_funcs, return_exceptions=True)

        all_papers = []
        for i, result in enumerate(results):
            source_name, query_used = search_meta[i]
            if isinstance(result, Exception):
                await self._log("search", f"✗ {source_name.value} 搜索失败: {str(result)}")
                await self._send_chat(f"⚠️ {source_name.value} 搜索失败: {str(result)}")
            else:
                all_papers.extend(result)
                await self._log("search", f"✓ {source_name.value}: 找到 {len(result)} 篇论文")

        await self._log("search", f"共收集 {len(all_papers)} 篇论文，正在去重...")
        await self._send_chat(f"共收集 {len(all_papers)} 篇论文，正在去重...")

        # 去重
        deduplicated = deduplicate(all_papers)
        await self._log("search", f"✓ 去重完成，剩余 {len(deduplicated)} 篇论文")
        return deduplicated

    async def _filter_phase(self, papers: list[Paper]) -> list[Paper]:
        """智能筛选"""
        filters = self.task.filters

        # 先按硬性条件过滤
        filtered = papers

        if filters.get("year_min"):
            year_min = filters["year_min"]
            filtered = [p for p in filtered if p.published_date and p.published_date.year >= year_min]

        if filters.get("citations_min"):
            cit_min = filters["citations_min"]
            filtered = [p for p in filtered if (p.citation_count or 0) >= cit_min]

        if filters.get("only_oa"):
            filtered = [p for p in filtered if p.is_open_access]

        # 计算综合评分
        max_citations = max((p.citation_count or 0) for p in filtered) if filtered else 1
        now = datetime.now()

        for paper in filtered:
            score = 0.0

            # 统一去除时区信息，避免 offset-naive/aware 冲突
            pub_date = paper.published_date.replace(tzinfo=None) if paper.published_date and paper.published_date.tzinfo else paper.published_date

            # 引用数评分 (20%)
            import math
            cit = paper.citation_count or 0
            cit_score = math.log10(cit + 1) / math.log10(max_citations + 1) * 10 if max_citations > 0 else 0
            score += cit_score * 0.2

            # 时效性 (15%)
            if pub_date:
                age = (now - pub_date).days / 365
                if age <= 1:
                    time_score = 10
                elif age <= 3:
                    time_score = 8
                elif age <= 5:
                    time_score = 6
                else:
                    time_score = 4
            else:
                time_score = 5
            score += time_score * 0.15

            # 可获取性 (15%)
            if paper.is_open_access:
                oa_score = 10
            elif paper.pdf_url:
                oa_score = 7
            else:
                oa_score = 3
            score += oa_score * 0.15

            # 来源可信度 (10%)
            if paper.venue and any(kw in (paper.venue or "").lower() for kw in ["nature", "science", "ieee", "acm", "springer"]):
                venue_score = 10
            elif paper.source == PaperSource.ARXIV:
                venue_score = 5
            else:
                venue_score = 7
            score += venue_score * 0.10

            # 语义相关性 (40%) - 简化版：基于标题关键词匹配
            query_words = set(self.task.query.lower().split())
            title_words = set(paper.title.lower().split())
            abstract_words = set(paper.abstract.lower().split()) if paper.abstract else set()
            overlap = len(query_words & (title_words | abstract_words))
            rel_score = min(10, overlap * 2.5)
            score += rel_score * 0.4

            paper.relevance_score = round(score, 2)

        # 按评分排序
        filtered.sort(key=lambda p: p.relevance_score or 0, reverse=True)

        # 更新数据库中的评分
        for paper in filtered:
            await update_paper_download(paper.id, paper.local_pdf_path or "", paper.download_status)

        return filtered

    async def _download_phase(self, papers: list[Paper]) -> dict:
        """批量下载 PDF"""
        success = 0
        failed = 0
        total = len(papers)
        lock = asyncio.Lock()

        # 最多 3 个并发下载
        semaphore = asyncio.Semaphore(3)

        async def _download_one(paper: Paper):
            nonlocal success, failed
            async with semaphore:
                local_path, error = await download_pdf(paper)
                if local_path:
                    paper.local_pdf_path = local_path
                    paper.download_status = "done"
                    await update_paper_download(paper.id, local_path, "done")
                else:
                    paper.download_status = "failed"
                    await update_paper_download(paper.id, None, "failed")

                # 加锁更新计数 + 轻量写入数据库
                async with lock:
                    if local_path:
                        success += 1
                    else:
                        failed += 1
                    self.task.papers_downloaded = success
                    self.task.papers_failed = failed
                    await update_task_download_stats(self.task.id, success, failed)
                    done = success + failed
                    status_icon = "✓" if local_path else "✗"
                    paper_title = paper.title[:40] + "..." if len(paper.title) > 40 else paper.title
                    await self._log("download", f"{status_icon} [{done}/{total}] {paper_title}")
                    await self._notify(
                        "download", "working",
                        f"下载进度: {done}/{total} (成功 {success}, 失败 {failed})",
                        int(done / total * 100),
                    )

        tasks_list = [_download_one(p) for p in papers]
        await asyncio.gather(*tasks_list)

        return {"success": success, "failed": failed}

    async def _notify(self, agent: str, status: str, message: str, progress: int | None = None):
        """发送 Agent 状态通知"""
        try:
            await broadcast_agent_status(self.task.id, agent, status, message, progress)
        except Exception:
            pass  # WebSocket 可能未连接

    async def _log(self, agent: str, log_line: str):
        """发送 Agent 日志行（显示在终端风格气泡中）"""
        try:
            await broadcast_agent_log(self.task.id, agent, log_line)
        except Exception:
            pass

    async def _send_chat(self, content: str, suggestions: list[str] | None = None):
        """发送聊天消息"""
        msg = Message(
            id=str(uuid.uuid4()),
            task_id=self.task.id,
            role=MessageRole.AGENT,
            content=content,
            suggestions=suggestions or [],
            timestamp=datetime.now(),
            agent_name="PaperHunter",
        )
        await insert_message(msg)
        try:
            from ..api.websocket import broadcast_to_task
            await broadcast_to_task(self.task.id, {
                "type": "chat",
                "from": "agent",
                "content": content,
                "timestamp": msg.timestamp.isoformat(),
                "suggestions": suggestions or [],
            })
        except Exception:
            pass
