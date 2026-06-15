"""TTS 抽象接口。流式吐 PCM 块，sample_rate 标明引擎输出采样率（供注入前重采样到 48k）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class TTSEngine(ABC):
    sample_rate: int = 48000  # 引擎输出采样率

    @abstractmethod
    def synthesize_stream(self, text: str) -> Iterator[bytes]:
        """流式返回 int16 mono PCM 块（采样率 = self.sample_rate）。"""
