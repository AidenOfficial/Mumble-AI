"""音频工具：PCM 时长计算 + soxr 重采样。

Mumble 收发都是 48kHz / 16-bit / mono；paraformer 只吃 16kHz；Fish TTS 输出按其规格
（常见 44.1k/24k）再回到 48k。统一用 soxr 重采样（不用 audioop——它在 3.13 被移除）。

提供两种：
- resample_pcm16(): 一次性重采样（整段，测试与短音频用）。
- StreamResampler:  有状态分块重采样（连续流用，避免逐块独立重采样的边界杂音）。
"""

from __future__ import annotations

import numpy as np
import soxr

MUMBLE_RATE = 48000   # pymumble 收发固定采样率
SAMPLE_WIDTH = 2      # int16 = 2 bytes


def pcm_duration_sec(pcm: bytes, rate: int) -> float:
    """int16 mono PCM 字节流的时长（秒）。"""
    return len(pcm) / SAMPLE_WIDTH / rate


def resample_pcm16(pcm: bytes, in_rate: int, out_rate: int) -> bytes:
    """一次性重采样 int16 mono PCM。in==out 或空数据时原样返回。"""
    if in_rate == out_rate or not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16)
    out = soxr.resample(samples, in_rate, out_rate)
    return _to_int16_bytes(out)


def _to_int16_bytes(arr: np.ndarray) -> bytes:
    if arr.dtype != np.int16:
        arr = np.clip(np.rint(arr), -32768, 32767).astype(np.int16)
    return arr.tobytes()


class StreamResampler:
    """连续流的有状态重采样器（单声道 int16）。

    用法：
        rs = StreamResampler(48000, 16000)
        for chunk in stream:
            out = rs.process(chunk)
        tail = rs.process(b"", last=True)   # 收尾，吐出残留样本
    """

    def __init__(self, in_rate: int, out_rate: int):
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._passthrough = in_rate == out_rate
        self._st = None
        if not self._passthrough:
            self._st = soxr.ResampleStream(in_rate, out_rate, 1, dtype="int16")

    def process(self, pcm: bytes, last: bool = False) -> bytes:
        if self._passthrough:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16) if pcm else np.empty(0, dtype=np.int16)
        y = self._st.resample_chunk(x, last=last)
        return _to_int16_bytes(y)
