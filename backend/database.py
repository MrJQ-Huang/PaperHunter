import aiosqlite
import json
from datetime import datetime
from pathlib import Path

from .config import settings
from .models.paper import Paper, PaperSource
from .models.task import Task, TaskStatus
from .models.message import Message, MessageRole

DB_PATH = settings.db_path


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                abstract TEXT,
                doi TEXT UNIQUE,
                url TEXT NOT NULL,
                pdf_url TEXT,
                source TEXT NOT NULL,
                published_date TEXT,
                citation_count INTEGER,
                venue TEXT,
                is_open_access BOOLEAN DEFAULT 0,
                topics TEXT,
                local_pdf_path TEXT,
                download_status TEXT DEFAULT 'pending',
                relevance_score REAL,
                created_at TEXT NOT NULL,
                task_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
            CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
            CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                sources TEXT,
                filters TEXT,
                status TEXT DEFAULT 'pending',
                total_papers_found INTEGER DEFAULT 0,
                papers_after_filter INTEGER DEFAULT 0,
                papers_downloaded INTEGER DEFAULT 0,
                papers_failed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                suggestions TEXT,
                timestamp TEXT NOT NULL,
                agent_name TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);

            CREATE TABLE IF NOT EXISTS watch_list (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                sources TEXT,
                filters TEXT,
                check_frequency TEXT,
                auto_download BOOLEAN DEFAULT 0,
                last_checked_at TEXT,
                created_at TEXT NOT NULL
            );
        """)

        # 兼容旧数据库：先确保 task_id 列存在，再创建索引
        try:
            await db.execute("ALTER TABLE papers ADD COLUMN task_id TEXT")
        except Exception:
            pass  # 列已存在

        try:
            await db.execute("CREATE INDEX IF NOT EXISTS idx_papers_task ON papers(task_id)")
        except Exception:
            pass

        await db.commit()


def _paper_from_row(row) -> Paper:
    return Paper(
        id=row["id"],
        title=row["title"],
        authors=json.loads(row["authors"]) if row["authors"] else [],
        abstract=row["abstract"] or "",
        doi=row["doi"],
        url=row["url"],
        pdf_url=row["pdf_url"],
        source=PaperSource(row["source"]),
        published_date=datetime.fromisoformat(row["published_date"]) if row["published_date"] else None,
        citation_count=row["citation_count"],
        venue=row["venue"],
        is_open_access=bool(row["is_open_access"]),
        topics=json.loads(row["topics"]) if row["topics"] else [],
        local_pdf_path=row["local_pdf_path"],
        download_status=row["download_status"] or "pending",
        relevance_score=row["relevance_score"],
        created_at=datetime.fromisoformat(row["created_at"]),
        task_id=row["task_id"] if "task_id" in row.keys() else None,
    )


def _task_from_row(row) -> Task:
    return Task(
        id=row["id"],
        query=row["query"],
        sources=[PaperSource(s) for s in json.loads(row["sources"])] if row["sources"] else [],
        filters=json.loads(row["filters"]) if row["filters"] else {},
        status=TaskStatus(row["status"]),
        total_papers_found=row["total_papers_found"],
        papers_after_filter=row["papers_after_filter"],
        papers_downloaded=row["papers_downloaded"],
        papers_failed=row["papers_failed"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        error_message=row["error_message"],
    )


def _message_from_row(row) -> Message:
    return Message(
        id=row["id"],
        task_id=row["task_id"],
        role=MessageRole(row["role"]),
        content=row["content"],
        suggestions=json.loads(row["suggestions"]) if row["suggestions"] else [],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        agent_name=row["agent_name"],
    )


# ---- Paper CRUD ----

async def insert_paper(paper: Paper):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO papers
            (id, title, authors, abstract, doi, url, pdf_url, source,
             published_date, citation_count, venue, is_open_access, topics,
             local_pdf_path, download_status, relevance_score, created_at, task_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                paper.id, paper.title, json.dumps(paper.authors), paper.abstract,
                paper.doi, paper.url, paper.pdf_url, paper.source.value,
                paper.published_date.isoformat() if paper.published_date else None,
                paper.citation_count, paper.venue, paper.is_open_access,
                json.dumps(paper.topics), paper.local_pdf_path, paper.download_status,
                paper.relevance_score, paper.created_at.isoformat(), paper.task_id,
            ),
        )
        await db.commit()


async def insert_papers(papers: list[Paper]):
    async with aiosqlite.connect(DB_PATH) as db:
        for paper in papers:
            await db.execute(
                """INSERT OR REPLACE INTO papers
                (id, title, authors, abstract, doi, url, pdf_url, source,
                 published_date, citation_count, venue, is_open_access, topics,
                 local_pdf_path, download_status, relevance_score, created_at, task_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    paper.id, paper.title, json.dumps(paper.authors), paper.abstract,
                    paper.doi, paper.url, paper.pdf_url, paper.source.value,
                    paper.published_date.isoformat() if paper.published_date else None,
                    paper.citation_count, paper.venue, paper.is_open_access,
                    json.dumps(paper.topics), paper.local_pdf_path, paper.download_status,
                    paper.relevance_score, paper.created_at.isoformat(), paper.task_id,
                ),
            )
        await db.commit()


async def get_paper(paper_id: str) -> Paper | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)) as cur:
            row = await cur.fetchone()
            return _paper_from_row(row) if row else None


async def get_papers(
    task_id: str | None = None,
    page: int = 1,
    per_page: int = 20,
    sort: str = "relevance",
    search: str | None = None,
) -> tuple[list[Paper], int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = (page - 1) * per_page

        conditions = []
        params: list = []
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if search:
            conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
            kw = f"%{search}%"
            params.extend([kw, kw, kw])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # 查询总数
        count_sql = f"SELECT COUNT(*) as cnt FROM papers {where}"
        async with db.execute(count_sql, params) as cur:
            row = await cur.fetchone()
            total = row["cnt"]

        # 排序
        order = "relevance_score DESC" if sort == "relevance" else "published_date DESC"
        sql = f"SELECT * FROM papers {where} ORDER BY {order} LIMIT ? OFFSET ?"
        async with db.execute(sql, params + [per_page, offset]) as cur:
            rows = await cur.fetchall()
            papers = [_paper_from_row(r) for r in rows]

        return papers, total


async def update_paper_download(paper_id: str, local_path: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE papers SET local_pdf_path = ?, download_status = ? WHERE id = ?",
            (local_path, status, paper_id),
        )
        await db.commit()


async def update_paper(paper_id: str, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values())
    vals.append(paper_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE papers SET {sets} WHERE id = ?", vals)
        await db.commit()


async def delete_paper(paper_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        await db.commit()


async def delete_all_papers(task_id: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if task_id:
            await db.execute("DELETE FROM papers WHERE task_id = ?", (task_id,))
        else:
            await db.execute("DELETE FROM papers")
        await db.commit()


async def count_papers(task_id: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if task_id:
            async with db.execute("SELECT COUNT(*) FROM papers WHERE task_id = ?", (task_id,)) as cur:
                row = await cur.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM papers") as cur:
                row = await cur.fetchone()
        return row[0] if row else 0


# ---- Task CRUD ----

async def insert_task(task: Task):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tasks
            (id, query, sources, filters, status, total_papers_found,
             papers_after_filter, papers_downloaded, papers_failed,
             created_at, updated_at, error_message)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task.id, task.query, json.dumps([s.value for s in task.sources]),
                json.dumps(task.filters), task.status.value, task.total_papers_found,
                task.papers_after_filter, task.papers_downloaded, task.papers_failed,
                task.created_at.isoformat(), task.updated_at.isoformat(),
                task.error_message,
            ),
        )
        await db.commit()


async def get_task(task_id: str) -> Task | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            return _task_from_row(row) if row else None


async def get_tasks() -> list[Task]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tasks ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
            return [_task_from_row(r) for r in rows]


async def update_task(task: Task):
    async with aiosqlite.connect(DB_PATH) as db:
        task.updated_at = datetime.now()
        await db.execute(
            """UPDATE tasks SET status=?, total_papers_found=?,
            papers_after_filter=?, papers_downloaded=?, papers_failed=?,
            updated_at=?, error_message=? WHERE id=?""",
            (
                task.status.value, task.total_papers_found, task.papers_after_filter,
                task.papers_downloaded, task.papers_failed, task.updated_at.isoformat(),
                task.error_message, task.id,
            ),
        )
        await db.commit()


async def update_task_download_stats(task_id: str, downloaded: int, failed: int):
    """轻量级更新：只更新下载计数，不碰其他字段，避免并发覆盖"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET papers_downloaded=?, papers_failed=?, updated_at=? WHERE id=?",
            (downloaded, failed, datetime.now().isoformat(), task_id),
        )
        await db.commit()


async def delete_task(task_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()


async def delete_task_messages(task_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE task_id = ?", (task_id,))
        await db.commit()


# ---- Message CRUD ----

async def insert_message(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO messages (id, task_id, role, content, suggestions, timestamp, agent_name)
            VALUES (?,?,?,?,?,?,?)""",
            (
                message.id, message.task_id, message.role.value, message.content,
                json.dumps(message.suggestions), message.timestamp.isoformat(),
                message.agent_name,
            ),
        )
        await db.commit()


async def get_messages(task_id: str, page: int = 1, per_page: int = 50) -> list[Message]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        offset = (page - 1) * per_page
        async with db.execute(
            "SELECT * FROM messages WHERE task_id = ? ORDER BY timestamp ASC LIMIT ? OFFSET ?",
            (task_id, per_page, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [_message_from_row(r) for r in rows]


# ---- Stats ----

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM papers") as cur:
            row = await cur.fetchone()
            total_papers = row[0]
        async with db.execute("SELECT COUNT(*) as cnt FROM papers WHERE download_status = 'done'") as cur:
            row = await cur.fetchone()
            downloaded = row[0]
        async with db.execute("SELECT COUNT(*) as cnt FROM tasks") as cur:
            row = await cur.fetchone()
            total_tasks = row[0]
        return {
            "total_papers": total_papers,
            "downloaded_papers": downloaded,
            "total_tasks": total_tasks,
        }


async def get_paper_stats_for_task(task_id: str) -> dict:
    """实时统计某任务下论文的数量和下载状态，和 Settings 页面同一个数据源"""
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {"total": 0, "downloaded": 0, "failed": 0}
        async with db.execute(
            "SELECT download_status, COUNT(*) FROM papers WHERE task_id = ? GROUP BY download_status",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
            for row in rows:
                status, count = row[0], row[1]
                stats["total"] += count
                if status == "done":
                    stats["downloaded"] = count
                elif status == "failed":
                    stats["failed"] = count
        return stats
