"""上下文压缩的纪要存档：每个会话只保留一份，滚动更新"""

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "SUMMARY_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "summaries.db"),
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
            create table if not exists summaries (
                thread_id text primary key,
                content text not null,
                covered integer not null,
                updated_at text not null
            )
            """
        )


def get(thread_id: str) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "select content from summaries where thread_id = ?", (thread_id,)
        ).fetchone()
    return row["content"] if row else None


def save(thread_id: str, content: str, covered: int) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_connect()) as conn, conn:
        conn.execute(
            "insert into summaries (thread_id, content, covered, updated_at) values (?, ?, ?, ?) "
            "on conflict(thread_id) do update set content = excluded.content, "
            "covered = covered + excluded.covered, updated_at = excluded.updated_at",
            (thread_id, content, covered, now),
        )


def delete(thread_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("delete from summaries where thread_id = ?", (thread_id,))
