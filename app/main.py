import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.wedding import build_agent
from app.api.v1 import auth, chat
from app.common.logger import setup_logging
from app.core.auth import hash_password
from app.db import cache_store, session_store, user_store

setup_logging()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 容器里用 WEDDING_DB 指到挂载卷；本地默认放在 app/db 下
DB_PATH = os.getenv("WEDDING_DB", os.path.join(BASE_DIR, "db", "wedding.db"))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建连接和 agent，整个服务期间共用；关服务时自动关闭。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    user_store.init_db()
    session_store.init_db()
    cache_store.init_db()
    cache_store.cleanup()
    user_store.seed_users(
        {
            os.getenv("ADMIN_USER", "admin"): os.getenv("ADMIN_PASSWORD", ""),
            os.getenv("TEST_USER", "test"): os.getenv("TEST_PASSWORD", ""),
        },
        hash_password,
    )

    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        app.state.agent = await build_agent(checkpointer)
        print(f"[启动] 数据库: {DB_PATH}")
        yield


app = FastAPI(title="婚礼多智能体", version="0.1.0", lifespan=lifespan)

# 1. 配置跨域资源共享 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 挂载路由
app.include_router(auth.router, prefix="/api/v1", tags=["认证"])
app.include_router(chat.router, prefix="/api/v1", tags=["对话"])

# 3. 挂载前端资源
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    # 页面改动频繁，禁用缓存，避免浏览器还跑旧版脚本
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


if __name__ == "__main__":
    import uvicorn

    # 启动命令：python -m app.main
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)
