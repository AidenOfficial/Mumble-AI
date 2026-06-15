"""隐私 / 闭嘴 状态。

- paused：暂停转写（连 STT 都不喂）。
- muted（闭嘴 N 分钟）：停一切主动输出（唤醒回话 + 主动插话）。
"""

from __future__ import annotations

import threading
import time


class PrivacyState:
    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._paused = False
        self._mute_until = 0.0

    # ---- 转写暂停 ----
    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    # ---- 闭嘴 ----
    def shutup(self, minutes: float) -> None:
        with self._lock:
            self._mute_until = self._clock() + minutes * 60.0

    def unmute(self) -> None:
        with self._lock:
            self._mute_until = 0.0

    def is_muted(self) -> bool:
        with self._lock:
            return self._clock() < self._mute_until

    def mute_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._mute_until - self._clock())
