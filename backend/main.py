from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db
from .api import tasks, papers, websocket, chat, settings as settings_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="PaperHunter",
    description="AI Agent 团队论文搜索系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(settings_api.router, prefix="/api", tags=["settings"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "PaperHunter"}


@app.get("/api/stats")
async def stats():
    from .database import get_stats
    return await get_stats()


@app.get("/api/config")
async def config():
    from .config import settings
    return {
        "llm_api_type": settings.llm_api_type,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "has_llm_api_key": bool(settings.llm_api_key and settings.llm_api_key != "tp-placeholder"),
        "download_dir": settings.download_dir,
    }
