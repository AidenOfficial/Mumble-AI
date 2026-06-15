"""Gemini 3.5 Flash 兜底。交互路径用 thinking_level=low/minimal（<5s TTFT）。

注：Gemini 不能完全关思考，minimal 也可能极少推理；low/minimal 已足够低延迟。
SDK（google-genai）的 thinking 字段名随版本演进——这里防御性设置，失败则降级为默认。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from .base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str, thinking_level: str = "low"):
        from google import genai  # 局部导入

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._thinking_level = thinking_level

    def _config(self, system: str, json_mode: bool = False):
        from google.genai import types

        kwargs = {"system_instruction": system}
        # thinking 字段名随 SDK 版本可能不同，容错处理
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self._thinking_level)
        except (TypeError, AttributeError):
            pass
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(**kwargs)

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        stream = self._client.models.generate_content_stream(
            model=self._model, contents=user, config=self._config(system)
        )
        for chunk in stream:
            if getattr(chunk, "text", None):
                yield chunk.text

    def json_verdict(self, system: str, user: str) -> dict:
        resp = self._client.models.generate_content(
            model=self._model, contents=user, config=self._config(system, json_mode=True)
        )
        try:
            return json.loads(resp.text or "{}")
        except json.JSONDecodeError:
            return {}

    def stream_chat(self, messages, tools=None):
        """兜底不支持工具调用：把 messages 拍平成 system + 对话，仅流式内容。"""
        system = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system" and m.get("content")
        )
        convo = "\n".join(
            f'{m["role"]}: {m.get("content", "")}'
            for m in messages
            if m.get("role") in ("user", "assistant", "tool") and m.get("content")
        )
        for delta in self.complete_stream(system, convo):
            yield {"type": "content", "text": delta}
