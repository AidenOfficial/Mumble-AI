"""单条 TTS 输出 worker。

pymumble 只有一个 sound_output，所有回话必须串行。逐句合成、注入；任一时刻发现有人
开口（anyone_transmitting）就放弃后续，规避盖话。last_spoke_ts 供冷却/被无视判断。
"""

from __future__ import annotations

import logging
import queue
import threading
import time

from .audio import MUMBLE_RATE, StreamResampler

log = logging.getLogger(__name__)


class Speaker:
    def __init__(self, tts, audio_sink, anyone_transmitting, *,
                 out_rate: int = MUMBLE_RATE, clock=time.time, on_finish=None):
        """audio_sink(pcm48k_bytes)->None；anyone_transmitting()->bool。"""
        self._tts = tts
        self._sink = audio_sink
        self._anyone = anyone_transmitting
        self._out = out_rate
        self._clock = clock
        self._on_finish = on_finish
        self._q: queue.Queue = queue.Queue()
        self._speaking = threading.Event()
        self.last_spoke_ts = 0.0
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def set_tts(self, tts) -> None:
        """热替换 TTS 引擎（换音色/模型时用）。下一句生效。"""
        self._tts = tts

    def speak(self, sentences, source: str = "wake") -> None:
        """sentences: 可迭代中文句子（orchestrator.respond 的流，或 [单句]）。"""
        self._q.put((sentences, source))

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self._speak_one(*item)

    def _speak_one(self, sentences, source: str) -> None:
        self._speaking.set()
        ducked = False
        try:
            rs = StreamResampler(self._tts.sample_rate, self._out)
            for sentence in sentences:
                if not sentence:
                    continue
                if self._anyone():  # 有人开口 → 放弃后续
                    ducked = True
                    break
                try:
                    for pcm in self._tts.synthesize_stream(sentence):
                        if self._anyone():
                            ducked = True
                            break
                        out = rs.process(pcm)
                        if out:
                            self._sink(out)
                except Exception:
                    log.exception("TTS 合成/注入异常")
                if ducked:
                    break
            if not ducked:
                tail = rs.process(b"", last=True)
                if tail:
                    self._sink(tail)
        finally:
            self._speaking.clear()
            self.last_spoke_ts = self._clock()
            if self._on_finish:
                try:
                    self._on_finish(source, ducked)
                except Exception:
                    log.exception("on_finish 异常")

    def stop(self) -> None:
        self._q.put(None)
