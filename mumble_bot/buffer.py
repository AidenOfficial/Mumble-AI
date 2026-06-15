"""转写滚动缓冲。

内存 deque（按 t_end 淘汰超窗）做实时查询；SQLite 兜底崩溃恢复与超窗召回。
墙钟时间戳由 STT 层在 ingest 时打（见计划"时间戳铁律"）：t_start=首个 interim 时刻，
t_end=finalize 时刻；召回/相对时间一律用 t_end。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class Utterance:
    id: str
    user: str
    text: str
    t_start: float   # 墙钟：收到首个 interim 的时刻
    t_end: float     # 墙钟：该句 finalize 的时刻（召回/相对时间用这个）
    conf: float | None = None


class TranscriptStore:
    """线程安全：pymumble/STT 结果线程写，编排/插话线程读。

    clock 可注入，便于测试控制时间；实际写入的 t_start/t_end 仍是 STT 层传入的真墙钟。
    """

    def __init__(self, db=None, window_sec: float = 3600.0, clock=time.time):
        self._db = db
        self._window = window_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._buf: deque[Utterance] = deque()
        if db is not None:
            self._load_recent()

    def _load_recent(self) -> None:
        cutoff = self._clock() - self._window
        rows = self._db.query(
            "SELECT id, user, text, t_start, t_end, conf FROM utterances "
            "WHERE t_end >= ? ORDER BY t_end",
            (cutoff,),
        )
        for r in rows:
            self._buf.append(Utterance(*r))

    def append(self, u: Utterance) -> None:
        with self._lock:
            self._buf.append(u)
            self._evict_locked()
            if self._db is not None:
                self._db.execute(
                    "INSERT OR REPLACE INTO utterances(id, user, text, t_start, t_end, conf) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (u.id, u.user, u.text, u.t_start, u.t_end, u.conf),
                )

    def _evict_locked(self) -> None:
        cutoff = self._clock() - self._window
        while self._buf and self._buf[0].t_end < cutoff:
            self._buf.popleft()

    def recent(self, window_sec: float | None = None) -> list[Utterance]:
        """返回窗口内的快照（默认整窗）。"""
        with self._lock:
            self._evict_locked()
            if window_sec is None:
                return list(self._buf)
            cutoff = self._clock() - window_sec
            return [u for u in self._buf if u.t_end >= cutoff]

    def last(self) -> Utterance | None:
        with self._lock:
            return self._buf[-1] if self._buf else None

    def set_window(self, window_sec: float) -> None:
        with self._lock:
            self._window = window_sec

    def recall(self, since: float | None = None, until: float | None = None,
               contains: str | None = None, limit: int = 200) -> list[Utterance]:
        """超窗召回走 SQLite（按 t_end 升序）。"""
        if self._db is None:
            return []
        sql = "SELECT id, user, text, t_start, t_end, conf FROM utterances WHERE 1=1"
        params: list = []
        if since is not None:
            sql += " AND t_end >= ?"; params.append(since)
        if until is not None:
            sql += " AND t_end <= ?"; params.append(until)
        if contains:
            sql += " AND text LIKE ?"; params.append(f"%{contains}%")
        sql += " ORDER BY t_end LIMIT ?"; params.append(limit)
        return [Utterance(*r) for r in self._db.query(sql, tuple(params))]
