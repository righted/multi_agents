from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.agents.wedding import chat_stream, clear_messages, get_messages
from app.core.auth import get_current_user
from app.db import session_store, step_store
from app.models.schemas import ChatRequest

router = APIRouter()


@router.post("/chat/stream")
async def chat_endpoint(body: ChatRequest, request: Request, user: dict = Depends(get_current_user)):
    """流式对话（需要登录）"""
    agent = request.app.state.agent
    thread_id = f"u{user['id']}-{body.thread_id}"   # 会话 id 按用户隔离
    session_store.touch(user["id"], body.thread_id, body.message)
    return StreamingResponse(
        chat_stream(agent, body.message, thread_id),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/chat/sessions")
async def list_chat_sessions(user: dict = Depends(get_current_user)):
    """左侧历史会话列表"""
    return {"sessions": session_store.list_sessions(user["id"])}


@router.get("/chat/messages")
async def get_chat_messages(thread_id: str, request: Request, user: dict = Depends(get_current_user)):
    """获取历史消息（需要登录）"""
    full_id = f"u{user['id']}-{thread_id}"
    messages = await get_messages(request.app.state.checkpointer, full_id)

    steps_map = step_store.load(full_id)      # 把每轮的工具步骤挂到对应的助手消息上
    turn = 0
    for msg in messages:
        if msg["role"] == "assistant":
            turn += 1
            msg["steps"] = steps_map.get(turn, [])

    return {"messages": messages}


@router.delete("/chat/messages")
async def clear_chat_messages(thread_id: str, request: Request, user: dict = Depends(get_current_user)):
    """清空历史消息（需要登录）"""
    full_id = f"u{user['id']}-{thread_id}"
    await clear_messages(request.app.state.checkpointer, full_id)
    step_store.delete_thread(full_id)
    session_store.delete_session(user["id"], thread_id)
    return {"success": True}
