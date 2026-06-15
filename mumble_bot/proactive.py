"""主动插话：两级门控，默认闭嘴。

一级（免费启发式，全用 Mumble 信号 + 缓冲）：无人传输 & 冷却已过 & 静音够久 & 近窗有
"未应答提问"信号。任一不过直接 return。
二级（快模型 JSON 裁决，强偏向不说）：通过一级后才花一次 LLM 判断说不说；决定说之前再确认无人开口。
v1 触发信号只做"未应答提问"一条。
"""

from __future__ import annotations

import logging
import threading
import time

from .orchestrator import fmt_clock, format_transcript

log = logging.getLogger(__name__)

_QWORDS = ("有没有人", "谁知道", "怎么办", "怎么搞", "求助", "在吗", "有人吗", "咋办", "怎么弄")


def unanswered_question(window, now: float, threshold_sec: float, qwords=_QWORDS) -> bool:
    """最近一句是提问/求助，且其后已静默 >= 阈值（它是最后一句即代表无人应答）。"""
    if not window:
        return False
    last = window[-1]
    text = last.text
    is_q = ("?" in text) or ("？" in text) or any(w in text for w in qwords)
    if not is_q:
        return False
    return (now - last.t_end) >= threshold_sec


class ProactiveEvaluator:
    def __init__(self, store, llm, speaker, *, anyone_transmitting, silence_duration,
                 privacy, cfg, clock=time.time):
        self._store = store
        self._llm = llm
        self._speaker = speaker
        self._anyone = anyone_transmitting
        self._silence = silence_duration
        self._privacy = privacy
        self._cfg = cfg
        self._clock = clock
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="proactive", daemon=True)

    def start(self) -> None:
        if self._cfg.proactive_enabled:
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._cfg.proactive_tick_sec):
            try:
                self.tick()
            except Exception:
                log.exception("proactive tick 异常")

    def gate(self) -> bool:
        """一级廉价门控。"""
        c = self._cfg
        if not c.proactive_enabled:
            return False
        if self._privacy.is_muted() or self._privacy.is_paused():
            return False
        if self._speaker.is_speaking():
            return False
        now = self._clock()
        if now - self._speaker.last_spoke_ts < c.cooldown_sec:
            return False
        if self._anyone():
            return False
        if self._silence() < c.silence_gate_sec:
            return False
        window = self._store.recent(c.window_sec)
        return unanswered_question(window, now, c.unanswered_question_sec)

    def tick(self) -> None:
        if not self.gate():
            return
        window = self._store.recent(self._cfg.window_sec)
        system = (
            "判断现在是否值得主动插话。默认 speak=false。"
            "仅当有人明显在等回应、或你能明确帮上忙时才 true。"
            f"现在 {fmt_clock(self._clock())}。"
            '只输出 JSON：{"speak": true/false, "text": "要说的话", "reason": "原因"}。'
            "text 用中文、简短、口语化。"
        )
        user = format_transcript(window)
        try:
            verdict = self._llm.json_verdict(system, user)
        except Exception:
            log.exception("插话裁决失败")
            return
        if not verdict.get("speak"):
            return
        if self._anyone():  # 决定说之前再确认；有人开口就放弃
            return
        text = (verdict.get("text") or "").strip()
        if text:
            self._speaker.speak([text], source="proactive")

    def stop(self) -> None:
        self._stop.set()
