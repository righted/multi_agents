"""用户表：SQLite 单表，够演示用"""

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "USER_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "users.db"),
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
            create table if not exists users (
                id integer primary key autoincrement,
                username text unique not null,
                password_hash text not null,
                created_at text not null
            )
            """
        )


def _to_dict(row: sqlite3.Row, with_password: bool = False) -> dict:
    data = {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}
    if with_password:
        data["password_hash"] = row["password_hash"]
    return data


def create_user(username: str, password_hash: str) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_connect()) as conn, conn:
        cursor = conn.execute(
            "insert into users (username, password_hash, created_at) values (?, ?, ?)",
            (username, password_hash, now),
        )
        user_id = cursor.lastrowid
    return {"id": user_id, "username": username, "created_at": now}


def get_user_by_username(username: str):
    with closing(_connect()) as conn:
        row = conn.execute("select * from users where username = ?", (username,)).fetchone()
    return _to_dict(row, with_password=True) if row else None


def get_user_by_id(user_id: int):
    with closing(_connect()) as conn:
        row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    return _to_dict(row) if row else None


def seed_users(accounts: dict[str, str], hash_password) -> None:
    """按「用户名 -> 明文密码」预置账号，已存在的跳过。"""
    for username, password in accounts.items():
        if not username or not password:
            continue
        if get_user_by_username(username):
            continue
        create_user(username, hash_password(password))


def delete_user(username: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("delete from users where username = ?", (username,))
