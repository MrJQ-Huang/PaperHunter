from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio

router = APIRouter()

# 连接管理
_connections: dict[str, set[WebSocket]] = {}  # task_id -> set of websockets


@router.websocket("/ws/chat/{task_id}")
async def websocket_chat(websocket: WebSocket, task_id: str):
    await websocket.accept()

    if task_id not in _connections:
        _connections[task_id] = set()
    _connections[task_id].add(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "user_command":
                # 广播给同任务的所有连接
                await broadcast_to_task(task_id, {
                    "type": "chat",
                    "from": "user",
                    "content": message.get("command", ""),
                    "timestamp": message.get("timestamp", ""),
                })
    except WebSocketDisconnect:
        _connections[task_id].discard(websocket)
        if not _connections[task_id]:
            del _connections[task_id]


async def broadcast_to_task(task_id: str, message: dict):
    if task_id not in _connections:
        return
    dead = set()
    for ws in _connections[task_id]:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    _connections[task_id] -= dead


async def broadcast_agent_status(task_id: str, agent: str, status: str, message: str, progress: int | None = None):
    await broadcast_to_task(task_id, {
        "type": "agent_status",
        "agent": agent,
        "status": status,
        "message": message,
        "progress": progress,
    })


async def broadcast_agent_log(task_id: str, agent: str, log_line: str):
    await broadcast_to_task(task_id, {
        "type": "agent_log",
        "agent": agent,
        "content": log_line,
    })


async def broadcast_search_graph_update(task_id: str, payload: dict):
    await broadcast_to_task(task_id, {
        "type": "search_graph_update",
        **payload,
    })
