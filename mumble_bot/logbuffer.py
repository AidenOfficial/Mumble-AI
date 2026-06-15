"""内存环形日志缓冲：挂到 root logger，供 Web 日志面板增量拉取排错。

线程安全；每条带递增 seq，Web 用 ?after=<seq> 只取新行。异常带 traceback。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

_EXC_FMT = logging.Formatter()


class RingLogHandler(logging.Handler):
    def __init__(self, capacity: int = 600):
        super().__init__()
        self._buf: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + _EXC_FMT.formatException(record.exc_info)
        except Exception:
            return
        with self._lock:
            self._seq += 1
            self._buf.append({
                "seq": self._seq,
                "level": record.levelname,
                "logger": record.name,
                "msg": msg,
                "clock": time.strftime("%H:%M:%S", time.localtime(record.created)),
            })

    def get(self, after: int = 0, limit: int = 600) -> list:
        with self._lock:
            rows = [r for r in self._buf if r["seq"] > after]
        return rows[-limit:]
