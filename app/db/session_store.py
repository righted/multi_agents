"""会话索引：记录每个用户有哪些对话、标题和最后更新时间"""

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "SESSION_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "sessions.db"),
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            create table if not exists sessions (
                user_id integer not null,
                thread_id text not null,
                title text not null,
                updated_at text not null,
                primary key (user_id, thread_id)
            )
            """
        )


def touch(user_id: int, thread_id: str, title: str | None = None) -> None:
    """记录一次对话：不存在就新建，存在就更新时间和标题（标题只补空）。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    title = (title or "新对话").strip()[:40]

    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "select title from sessions where user_id = ? and thread_id = ?",
            (user_id, thread_id),
        ).fetchone()
        if row is None:
            conn.execute(
                "insert into sessions (user_id, thread_id, title, updated_at) values (?, ?, ?, ?)",
                (user_id, thread_id, title, now),
            )
        else:
            conn.execute(
                "update sessions set updated_at = ?, title = ? where user_id = ? and thread_id = ?",
                (now, row["title"] or title, user_id, thread_id),
            )


def list_sessions(user_id: int, limit: int = 50) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "select thread_id, title, updated_at from sessions where user_id = ? "
            "order by updated_at desc limit ?",
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_session(user_id: int, thread_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "delete from sessions where user_id = ? and thread_id = ?", (user_id, thread_id)
        )
