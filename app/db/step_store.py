"""每轮的工具步骤存档：回看历史时能把调用过程一起显示出来"""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "STEP_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "steps.db"),
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
            create table if not exists steps (
                thread_id text not null,
                turn_no integer not null,
                payload text not null,
                created_at text not null,
                primary key (thread_id, turn_no)
            )
            """
        )


def save(thread_id: str, turn_no: int, steps: list[dict]) -> None:
    if not steps:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(steps, ensure_ascii=False)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "insert into steps (thread_id, turn_no, payload, created_at) values (?, ?, ?, ?) "
            "on conflict(thread_id, turn_no) do update set payload = excluded.payload",
            (thread_id, turn_no, payload, now),
        )


def load(thread_id: str) -> dict[int, list[dict]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "select turn_no, payload from steps where thread_id = ?", (thread_id,)
        ).fetchall()
    result: dict[int, list[dict]] = {}
    for row in rows:
        try:
            result[row["turn_no"]] = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
    return result


def delete_thread(thread_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("delete from steps where thread_id = ?", (thread_id,))
