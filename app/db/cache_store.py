"""查询结果缓存：SQLite 单表 + TTL"""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

DB_PATH = os.getenv(
    "CACHE_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "cache.db"),
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
            create table if not exists cache (
                key text primary key,
                value text not null,
                created_at text not null
            )
            """
        )


def get(key: str, ttl_seconds: int) -> str | None:
    """命中且未过期就返回值，否则返回 None。"""
    with closing(_connect()) as conn:
        row = conn.execute("select value, created_at from cache where key = ?", (key,)).fetchone()
    if not row:
        return None

    try:
        created = datetime.fromisoformat(row["created_at"])
    except ValueError:
        return None

    if datetime.now(timezone.utc) - created > timedelta(seconds=ttl_seconds):
        return None
    return row["value"]


def put(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "insert into cache (key, value, created_at) values (?, ?, ?) "
            "on conflict(key) do update set value = excluded.value, created_at = excluded.created_at",
            (key, payload, now),
        )


def cleanup(keep_days: int = 7) -> None:
    """顺手清理老记录，避免表无限增长。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    with closing(_connect()) as conn, conn:
        conn.execute("delete from cache where created_at < ?", (cutoff,))
