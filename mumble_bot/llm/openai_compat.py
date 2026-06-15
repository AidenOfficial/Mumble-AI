"""OpenAI 兼容 LLM 客户端（DeepSeek 直连 / OpenRouter / 任意 OpenAI 兼容端点）。

extra_body 透传供应商参数：
- DeepSeek 直连关思考：{"thinking": {"type": "disabled"}}
- OpenRouter 关思考 + provider 路由：{"reasoning": {"enabled": false}, "provider": {...}}
tool_model 可与 model 不同（agentic/工具路径用更强的模型，如 deepseek-v4-pro）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from .base import LLMClient


class OpenAICompatLLM(LLMClient):
    def __init__(self, api_key, base_url, model, *, extra_body=None,
                 default_headers=None, tool_model=None):
        from openai import OpenAI  # 局部导入：纯逻辑测试无需安装 openai

        # 必须设超时：默认 10min，卡住的 provider 会让唯一的 speaker 线程哑掉很久，
        # 且连接挂起不抛异常 → FailoverLLM 不触发。短超时 + 少重试 = 卡了就快速落兜底。
        self._client = OpenAI(api_key=api_key, base_url=base_url,
                              default_headers=default_headers or None,
                              timeout=30.0, max_retries=1)
        self._model = model
        self._tool_model = tool_model or model
        self._extra = extra_body or {}

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            stream=True,
            extra_body=self._extra,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def json_verdict(self, system: str, user: str) -> dict:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            stream=False,
            response_format={"type": "json_object"},
            extra_body=self._extra,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    def stream_chat(self, messages: list[dict], tools: list | None = None) -> Iterator[dict]:
        kwargs = dict(model=self._tool_model, messages=messages, stream=True, extra_body=self._extra)
        if tools:
            kwargs["tools"] = tools
        stream = self._client.chat.completions.create(**kwargs)
        tool_acc: dict[int, dict] = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield {"type": "content", "text": delta.content}
            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if fn.name:
                        slot["name"] = fn.name
                    if fn.arguments:
                        slot["arguments"] += fn.arguments
        if tool_acc:
            yield {"type": "tool_calls", "tool_calls": [tool_acc[i] for i in sorted(tool_acc)]}
