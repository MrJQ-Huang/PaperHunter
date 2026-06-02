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
        """三层漏斗搜索：关键词搜索 → 引用链补充 → 去重"""
        from ..utils.query_translator import translate_query, generate_search_plan
        from ..tools.semantic_scholar_tool import find_paper_by_title, get_paper_references

        sources = self.task.sources or [PaperSource.ARXIV, PaperSource.SEMANTIC_SCHOLAR, PaperSource.OPENALEX, PaperSource.CROSSREF]
        original_query = self.task.query

        # 判断是否需要翻译
        ascii_ratio = sum(1 for c in original_query if ord(c) < 128) / max(len(original_query), 1)
        needs_translate = ascii_ratio < 0.7

        if needs_translate:
            await self._notify("search", "working", "正在翻译检索词...")
            await self._log("search", "正在翻译检索词...")
            translated = await translate_query(original_query)
            await self._log("search", f"✓ 检索词已翻译: {translated}")
            await self._send_chat(f"已将检索词翻译为：{translated}")
        else:
            translated = original_query
            await self._log("search", f"✓ 检索词已是英文，跳过翻译: {translated}")

        # LLM 生成结构化搜索方案
        await self._notify("search", "working", "正在制定搜索策略...")
        await self._log("search", "正在分析研究意图，制定搜索策略...")
        search_plan = await generate_search_plan(translated)

        core_concepts = search_plan.get("core_concepts", [])
        source_queries = search_plan.get("queries", {})
        field_terms = search_plan.get("field_terms", [])

        if core_concepts:
            await self._log("search", f"✓ 核心概念: {', '.join(core_concepts)}")
        if field_terms:
            await self._log("search", f"✓ 领域术语: {', '.join(field_terms[:5])}")

        await self._send_chat(f"搜索策略已制定，核心概念: {', '.join(core_concepts) if core_concepts else translated}")

        # ===== 第一层：关键词搜索 =====
        await self._notify("search", "working", "第一层：关键词搜索...")
        await self._log("search", "第一层：关键词搜索...")

        source_map = {
            PaperSource.ARXIV: search_arxiv,
            PaperSource.SEMANTIC_SCHOLAR: search_semantic_scholar,
            PaperSource.OPENALEX: search_openalex,
            PaperSource.CROSSREF: search_crossref,
            PaperSource.GOOGLE_SCHOLAR: search_google_scholar,
        }
        source_name_map = {
            PaperSource.ARXIV: "arxiv",
            PaperSource.SEMANTIC_SCHOLAR: "semantic_scholar",
            PaperSource.OPENALEX: "openalex",
            PaperSource.CROSSREF: "crossref",
            PaperSource.GOOGLE_SCHOLAR: "google_scholar",
        }

        default_query = translated
        search_funcs = []
        search_meta = []
        for source in sources:
            if source in source_map:
                q = source_queries.get(source_name_map.get(source, ""), default_query)
                search_funcs.append(source_map[source](q))
                search_meta.append((source, q))

        results = await asyncio.gather(*search_funcs, return_exceptions=True)

        all_papers = []
        for i, result in enumerate(results):
            source_name, query_used = search_meta[i]
            if isinstance(result, Exception):
                await self._log("search", f"✗ {source_name.value} 搜索失败: {str(result)}")
            else:
                all_papers.extend(result)
                await self._log("search", f"✓ {source_name.value}: 找到 {len(result)} 篇论文")

        layer1_count = len(all_papers)
        await self._log("search", f"第一层完成，收集 {layer1_count} 篇论文")

        # 去重
        deduplicated = deduplicate(all_papers)
        await self._log("search", f"去重后剩余 {len(deduplicated)} 篇")

        # ===== 第二层：引用链补充 =====
        # 从第一层结果中找高被引论文，获取其 references（基础性工作）
        if len(deduplicated) > 0:
            await self._notify("search", "working", "第二层：引用链补充...")
            await self._log("search", "第二层：引用链追踪...")

            # 按引用数排序，取 Top 5
            by_citations = sorted(deduplicated, key=lambda p: p.citation_count or 0, reverse=True)
            top_papers = by_citations[:5]
            top_ids = []

            for p in top_papers:
                if (p.citation_count or 0) >= 50:
                    # 通过标题在 Semantic Scholar 找到 paperId
                    pid = await find_paper_by_title(p.title)
                    if pid:
                        top_ids.append((pid, p.title[:40], p.citation_count or 0))

            if top_ids:
                await self._log("search", f"  追踪 {len(top_ids)} 篇高被引论文的引用链:")
                for pid, title, cites in top_ids:
                    await self._log("search", f"  → {title}... (被引 {cites})")

                # 并行获取所有 references
                ref_tasks = [get_paper_references(pid, limit=20) for pid, _, _ in top_ids]
                ref_results = await asyncio.gather(*ref_tasks, return_exceptions=True)

                chain_papers = []
                for i, refs in enumerate(ref_results):
                    if isinstance(refs, Exception):
                        await self._log("search", f"  ✗ 引用链获取失败: {str(refs)}")
                    else:
                        # 只保留高被引的 references（引用数 > 100 的更可能是基础性工作）
                        high_cited = [r for r in refs if (r.citation_count or 0) >= 50]
                        chain_papers.extend(high_cited)
                        await self._log("search", f"  ✓ {top_ids[i][1][:30]}... 的引用链: {len(refs)} 篇, 高被引 {len(high_cited)} 篇")

                if chain_papers:
                    before = len(deduplicated)
                    deduplicated = deduplicate(deduplicated + chain_papers)
                    await self._log("search", f"引用链补充 {len(chain_papers)} 篇, 去重后: {before} → {len(deduplicated)}")
            else:
                await self._log("search", "  无高被引论文，跳过引用链追踪")

        layer2_total = len(deduplicated)
        await self._log("search", f"✓ 搜索完成，共 {layer2_total} 篇论文（关键词 {layer1_count} + 引用链补充 {layer2_total - layer1_count}）")
        await self._send_chat(f"搜索完成：关键词 {layer1_count} 篇 + 引用链补充 {layer2_total - layer1_count} 篇 = 共 {layer2_total} 篇")

        # 保存核心概念到 task.filters，供 filter 阶段使用
        if core_concepts:
            self.task.filters["_core_concepts"] = core_concepts

        return deduplicated

    async def _filter_phase(self, papers: list[Paper]) -> list[Paper]:
        """两阶段智能筛选：规则快筛 + LLM 精排"""
        import math
        from ..utils.llm_scorer import llm_score_papers

        filters = self.task.filters

        # ===== 第一阶段：规则快筛 =====
        await self._log("filter", "第一阶段：规则快筛...")
        filtered = papers

        # 硬性条件过滤
        if filters.get("year_min"):
            year_min = filters["year_min"]
            before = len(filtered)
            filtered = [p for p in filtered if p.published_date and p.published_date.year >= year_min]
            await self._log("filter", f"  年份过滤: {before} → {len(filtered)}")

        if filters.get("citations_min"):
            cit_min = filters["citations_min"]
            before = len(filtered)
            filtered = [p for p in filtered if (p.citation_count or 0) >= cit_min]
            await self._log("filter", f"  引用过滤: {before} → {len(filtered)}")

        if filters.get("only_oa"):
            before = len(filtered)
            filtered = [p for p in filtered if p.is_open_access]
            await self._log("filter", f"  OA过滤: {before} → {len(filtered)}")

        # 关键词硬匹配：标题/摘要必须包含至少一个核心概念
        core_concepts = filters.get("_core_concepts", [])
        if not core_concepts:
            # 兜底：用查询词本身
            core_concepts = [w for w in self.task.query.lower().split() if len(w) >= 3]

        if core_concepts:
            core_lower = [c.lower() for c in core_concepts]
            before = len(filtered)
            keyword_matched = []
            for p in filtered:
                title_lower = p.title.lower()
                abstract_lower = (p.abstract or "").lower()
                if any(c in title_lower or c in abstract_lower for c in core_lower):
                    keyword_matched.append(p)
            # 如果关键词过滤后还有论文，用过滤结果；否则回退（避免误杀）
            if keyword_matched:
                filtered = keyword_matched
                await self._log("filter", f"  关键词匹配: {before} → {len(filtered)}")

        # 规则评分（用于排序，不用于截断）
        max_citations = max((p.citation_count or 0) for p in filtered) if filtered else 1
        now = datetime.now()

        for paper in filtered:
            score = 0.0
            pub_date = paper.published_date.replace(tzinfo=None) if paper.published_date and paper.published_date.tzinfo else paper.published_date

            # 引用数 (20%)
            cit = paper.citation_count or 0
            cit_score = math.log10(cit + 1) / math.log10(max_citations + 1) * 10 if max_citations > 0 else 0
            score += cit_score * 0.2

            # 时效性 (15%)
            if pub_date:
                age = (now - pub_date).days / 365
                if age <= 1: time_score = 10
                elif age <= 3: time_score = 8
                elif age <= 5: time_score = 6
                else: time_score = 4
            else:
                time_score = 5
            score += time_score * 0.15

            # 可获取性 (15%)
            if paper.is_open_access: oa_score = 10
            elif paper.pdf_url: oa_score = 7
            else: oa_score = 3
            score += oa_score * 0.15

            # 来源可信度 (10%)
            if paper.venue and any(kw in (paper.venue or "").lower() for kw in ["nature", "science", "ieee", "acm", "springer"]):
                venue_score = 10
            elif paper.source == PaperSource.ARXIV: venue_score = 5
            else: venue_score = 7
            score += venue_score * 0.10

            paper.relevance_score = round(score, 2)

        filtered.sort(key=lambda p: p.relevance_score or 0, reverse=True)

        await self._log("filter", f"第一阶段完成，剩余 {len(filtered)} 篇论文")

        # ===== 第二阶段：LLM 语义精排 =====
        if len(filtered) <= 10:
            # 论文数量少，跳过 LLM 评分
            await self._log("filter", "论文数量较少，跳过 LLM 精排")
        else:
            await self._notify("filter", "working", "正在进行 LLM 语义评分...")
            await self._log("filter", f"第二阶段：LLM 语义评分（{len(filtered)} 篇）...")

            llm_scores = await llm_score_papers(self.task.query, filtered)

            # 合并 LLM 评分到论文
            score_map = {s["paper_id"]: s for s in llm_scores}
            for paper in filtered:
                llm_result = score_map.get(paper.id)
                if llm_result:
                    # 综合评分 = 规则分 × 0.4 + LLM 语义分 × 0.6
                    rule_score = paper.relevance_score or 0
                    llm_score = llm_result["relevance"]
                    paper.relevance_score = round(rule_score * 0.4 + llm_score * 0.6, 2)
                    paper._llm_relevant = llm_result.get("is_relevant", True)
                    paper._llm_reason = llm_result.get("reason", "")
                else:
                    paper._llm_relevant = True
                    paper._llm_reason = ""

            # 丢弃 LLM 判定为无关的论文
            before = len(filtered)
            filtered = [p for p in filtered if getattr(p, "_llm_relevant", True)]
            await self._log("filter", f"  LLM 无关判定丢弃: {before} → {len(filtered)}")

            # 按综合评分重排
            filtered.sort(key=lambda p: p.relevance_score or 0, reverse=True)

            # 打印 top 论文的 LLM 评分理由
            for p in filtered[:5]:
                reason = getattr(p, "_llm_reason", "")
                if reason:
                    await self._log("filter", f"  ★ {p.title[:50]}... — {reason}")

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
