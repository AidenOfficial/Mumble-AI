"""STT 流管理：每个活跃说话人一条流 + 静音看门狗（VAD 门控 / 成本门控）。

- feed(session, canonical, pcm48k)：复用或新开该 session 的流；48k→16k 重采样后喂入。
- 看门狗每 100ms 巡检：某 session 超过 close_silence 秒没来音频 → 关流收尾（不传输不喂 STT）。
- final 结果在此打**墙钟**生成 Utterance（t_start=该句首帧时刻，t_end=finalize 时刻）。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from ..audio import StreamResampler
from ..buffer import Utterance
from .base import MakeStream, STTResult

log = logging.getLogger(__name__)


class _SessionStream:
    def __init__(self, session, canonical, make_stream: MakeStream, in_rate, out_rate, on_utterance, clock):
        self.session = session
        self.canonical = canonical
        self._on_utterance = on_utterance
        self._clock = clock
        self._resampler = StreamResampler(in_rate, out_rate)
        self._t_start: float | None = None
        self.last_audio_ts = clock()
        self._stream = make_stream(self._on_result)

    def _on_result(self, res: STTResult) -> None:
        if self._t_start is None:
            self._t_start = self._clock()
        if res.is_final and res.text.strip():
            u = Utterance(
                id=uuid.uuid4().hex,
                user=self.canonical,
                text=res.text.strip(),
                t_start=self._t_start,
                t_end=self._clock(),
                conf=res.confidence,
            )
            self._t_start = None  # 下一句重新起算
            try:
                self._on_utterance(u)
            except Exception:
                log.exception("on_utterance 回调异常")

    def feed(self, pcm48k: bytes, now: float) -> None:
        self.last_audio_ts = now
        if self._t_start is None:
            self._t_start = now
        data = self._resampler.process(pcm48k)
        if data:
            self._stream.feed(data)

    def close(self) -> None:
        try:
            tail = self._resampler.process(b"", last=True)
            if tail:
                self._stream.feed(tail)
        except Exception:
            pass
        try:
            self._stream.close()
        except Exception:
            log.exception("STT 流关闭异常")


class STTManager:
    def __init__(self, make_stream: MakeStream, on_utterance, *,
                 in_rate=48000, out_rate=16000, close_silence=0.8, clock=time.time):
        self._make = make_stream
        self._on_utt = on_utterance
        self._in, self._out = in_rate, out_rate
        self._close = close_silence
        self._clock = clock
        self._sessions: dict[int, _SessionStream] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wd = threading.Thread(target=self._watch, name="stt-watchdog", daemon=True)

    def start(self) -> None:
        self._wd.start()

    def set_close_silence(self, seconds: float) -> None:
        self._close = seconds

    def feed(self, session: int, canonical: str, pcm48k: bytes) -> None:
        now = self._clock()
        with self._lock:
            ss = self._sessions.get(session)
            if ss is None:
                try:
                    ss = _SessionStream(session, canonical, self._make, self._in, self._out,
                                        self._on_utt, self._clock)
                except Exception:
                    log.exception("开 STT 流失败 session=%s", session)
                    return
                self._sessions[session] = ss
            ss.feed(pcm48k, now)

    def _watch(self) -> None:
        while not self._stop.wait(0.1):
            now = self._clock()
            dead = []
            with self._lock:
                for s in list(self._sessions):
                    if now - self._sessions[s].last_audio_ts > self._close:
                        dead.append(self._sessions.pop(s))
            for ss in dead:
                ss.close()

    def close_session(self, session: int) -> None:
        with self._lock:
            ss = self._sessions.pop(session, None)
        if ss:
            ss.close()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for ss in sessions:
            ss.close()
