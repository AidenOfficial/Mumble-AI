"""SQLite(WAL) 连接与建表。

单连接 + 锁（pymumble 回调线程、STT 结果线程、命令线程都会碰它）。
表：utterances（转写记录）、identity_map（身份存档）、excludes（除名）。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS utterances (
        id      TEXT PRIMARY KEY,
        user    TEXT NOT NULL,
        text    TEXT NOT NULL,
        t_start REAL NOT NULL,
        t_end   REAL NOT NULL,
        conf    REAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_utt_tend ON utterances(t_end)",
    """CREATE TABLE IF NOT EXISTS identity_map (
        stable_key TEXT PRIMARY KEY,
        canonical  TEXT NOT NULL
    )""",
    "CREATE TABLE IF NOT EXISTS excludes (key TEXT PRIMARY KEY)",
]


class Database:
    """线程安全的薄封装。所有读写走同一连接 + 锁。"""

    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            for stmt in _SCHEMA:
                self._conn.execute(stmt)
            self._conn.commit()

    def execute(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
