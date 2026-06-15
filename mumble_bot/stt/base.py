"""STT 抽象接口。一条流式识别 = 一个活跃说话人的一段连续语音。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class STTResult:
    text: str
    is_final: bool
    confidence: float | None = None


class STTStream(ABC):
    """构造时即开始（连上云端流）；feed 喂 16k PCM；close 收尾出最后 final。

    结果通过构造时传入的 on_result 回调吐出（会在 SDK 自己的线程上触发）。
    """

    @abstractmethod
    def feed(self, pcm16k: bytes) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


# 工厂：给定 on_result 回调，返回一个已开始的 STTStream。
MakeStream = Callable[[Callable[[STTResult], None]], STTStream]
