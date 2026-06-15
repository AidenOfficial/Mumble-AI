"""定时调度（heartbeat）。到点触发回调——通常是让 bot 开口（倒计时到了 / 恢复听力）。

后台线程用条件变量等到最近一个 fire 时刻（封顶 30s 作心跳），到点弹出执行。
_pop_due(now) 是纯逻辑、可单测，不依赖线程。
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time

log = logging.getLogger(__name__)


class TimerService:
    def __init__(self, clock=time.time):
        self._clock = clock
        self._heap: list = []                 # (fire_ts, tid, callback, label)
        self._counter = itertools.count()
        self._cancelled: set = set()
        self._cv = threading.Condition()
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="timers", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def schedule(self, delay_sec: float, callback, label: str = "") -> int:
        fire = self._clock() + max(0.0, float(delay_sec))
        with self._cv:
            tid = next(self._counter)
            heapq.heappush(self._heap, (fire, tid, callback, label))
            self._cv.notify()
        return tid

    def cancel(self, tid: int) -> bool:
        with self._cv:
            self._cancelled.add(tid)
            self._cv.notify()
        return True

    def list(self) -> list:
        """返回 [(剩余秒, tid, label)]，按剩余时间升序。"""
        now = self._clock()
        with self._cv:
            return sorted(
                (max(0.0, fire - now), tid, label)
                for fire, tid, _cb, label in self._heap
                if tid not in self._cancelled
            )

    def _pop_due(self, now: float) -> list:
        """弹出所有到点(未取消)的回调；纯逻辑、可单测。"""
        due = []
        with self._cv:
            while self._heap and self._heap[0][0] <= now:
                _fire, tid, cb, label = heapq.heappop(self._heap)
                if tid in self._cancelled:
                    self._cancelled.discard(tid)
                    continue
                due.append((tid, cb, label))
        return due

    def _run(self) -> None:
        while True:
            with self._cv:
                if self._stop:
                    return
                while self._heap and self._heap[0][1] in self._cancelled:
                    _f, tid, _cb, _l = heapq.heappop(self._heap)
                    self._cancelled.discard(tid)
                if not self._heap:
                    self._cv.wait()
                    continue
                wait = self._heap[0][0] - self._clock()
                if wait > 0:
                    self._cv.wait(timeout=min(wait, 30.0))
                    continue
            for _tid, cb, label in self._pop_due(self._clock()):
                try:
                    cb()
                except Exception:
                    log.exception("定时回调失败 label=%s", label)

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()
