"""LLM 故障转移：主客户端（OpenRouter）失败时自动落兜底（Gemini）。

策略：在流的**首个元素**处判定主路可用性——主路建连/首 token 抛错就整段切兜底；
若已经吐了内容才中途断开，则截断收尾（不重启，避免重复），把局面交给上层。
json_verdict 是非流式，直接 try 主→兜底。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from .base import LLMClient

log = logging.getLogger(__name__)


class FailoverLLM(LLMClient):
    def __init__(self, primary: LLMClient, fallback: LLMClient):
        self._primary = primary
        self._fallback = fallback

    def complete_stream(self, system: str, user: str) -> Iterator[str]:
        yield from self._failover_stream(
            lambda: self._primary.complete_stream(system, user),
            lambda: self._fallback.complete_stream(system, user),
        )

    def stream_chat(self, messages: list[dict], tools: list | None = None) -> Iterator[dict]:
        yield from self._failover_stream(
            lambda: self._primary.stream_chat(messages, tools),
            lambda: self._fallback.stream_chat(messages, tools),
        )

    def json_verdict(self, system: str, user: str) -> dict:
        try:
            return self._primary.json_verdict(system, user)
        except Exception:
            log.warning("主 LLM json_verdict 失败，落兜底", exc_info=True)
            try:
                return self._fallback.json_verdict(system, user)
            except Exception:
                log.exception("兜底 LLM json_verdict 也失败")
                return {}

    @staticmethod
    def _failover_stream(primary_fn, fallback_fn) -> Iterator:
        try:
            gen = primary_fn()
            first = next(gen)
        except StopIteration:
            return                       # 主路正常但无输出
        except Exception:
            log.warning("主 LLM 流失败，落兜底", exc_info=True)
            try:
                yield from fallback_fn()
            except Exception:
                log.exception("兜底 LLM 流也失败")
            return
        # 主路可用：吐首元素 + 其余；中途断则截断
        yield first
        try:
            yield from gen
        except Exception:
            log.warning("主 LLM 流中途断开，已截断", exc_info=True)
