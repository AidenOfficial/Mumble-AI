"""LLM 抽象接口。交互路径一律关思考（首音延迟铁律）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMClient(ABC):
    @abstractmethod
    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        """流式返回文本增量（供句级分块喂 TTS）。不带工具的简单回话路径用。"""

    @abstractmethod
    def json_verdict(self, system: str, user: str) -> dict:
        """一次性返回一个 JSON 对象（主动插话裁决用）。system/user 里需含 'json' 字样。"""

    def stream_chat(self, messages: list[dict], tools: list | None = None) -> Iterator[dict]:
        """工具调用流式（agentic 路径）。逐个 yield 事件 dict：
          {"type": "content", "text": "..."}                         # 文本增量
          {"type": "tool_calls", "tool_calls": [{"id","name","arguments"}]}  # 模型要调工具
        不支持工具的实现可只 yield content 事件（忽略 tools）。
        """
        raise NotImplementedError
