"""编排：把累计转写 + 当前墙钟拼成 prompt，流式调 LLM，并按句切分喂 TTS（降首音延迟）。

模型据 system 里的当前时间算"刚刚/N分钟前"。LLM 输出按中文句末标点切块，逐句返回。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime

from .buffer import Utterance

_SENTENCE_END = "。！？!?…\n"
_DEFAULT_EMPTY_QUERY = "（有人叫了你的名字，但没说别的，自然地回应一句，简短。）"


def fmt_clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def format_transcript(window: list[Utterance]) -> str:
    return "\n".join(f"[{fmt_clock(u.t_end)}] {u.user}: {u.text}" for u in window)


def build_system_prompt(persona: str, now_ts: float, transcript: str) -> str:
    return (
        f"{persona}\n"
        f"现在时间 {fmt_clock(now_ts)}。下面是最近的频道对话，每行前为说话时间；"
        f"涉及时间用相对表述（刚刚 / N分钟前）。只用中文，口语化、简短，不要列要点、不要复述原文。\n\n"
        f"{transcript}"
    )


def pop_sentences(buf: str) -> tuple[list[str], str]:
    """从累计缓冲里切出已完成的句子，返回 (句子列表, 余下未完成部分)。"""
    sentences, start = [], 0
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_END:
            seg = buf[start:i + 1].strip()
            if seg:
                sentences.append(seg)
            start = i + 1
    return sentences, buf[start:]


class Orchestrator:
    def __init__(self, llm, store, *, window_sec: float, persona: str, clock=time.time,
                 registry=None, max_tool_rounds: int = 4):
        self._llm = llm
        self._store = store
        self._window = window_sec
        self._persona = persona
        self._clock = clock
        self._registry = registry          # SkillRegistry；None=无工具的简单回话
        self._max_rounds = max_tool_rounds

    def build_prompt(self, query: str, window: list[Utterance], now_ts: float | None = None) -> tuple[str, str]:
        now_ts = self._clock() if now_ts is None else now_ts
        system = build_system_prompt(self._persona, now_ts, format_transcript(window))
        user = query.strip() or _DEFAULT_EMPTY_QUERY
        return system, user

    def respond(self, query: str) -> Iterator[str]:
        """流式产出一句句中文，供 speaker 逐句合成。有 registry 时走 agentic 工具循环。"""
        window = self._store.recent(self._window)
        system, user = self.build_prompt(query, window)
        if self._registry is None:
            yield from self._respond_simple(system, user)
        else:
            yield from self._respond_agentic(system, user)

    def _respond_simple(self, system: str, user: str) -> Iterator[str]:
        buf = ""
        for delta in self._llm.complete_stream(system, user):
            buf += delta
            sentences, buf = pop_sentences(buf)
            yield from sentences
        if buf.strip():
            yield buf.strip()

    def _respond_agentic(self, system: str, user: str) -> Iterator[str]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(self._max_rounds):
            buf = ""
            tool_calls = None
            for ev in self._llm.stream_chat(messages, tools=self._registry.specs()):
                if ev.get("type") == "content":
                    buf += ev["text"]
                    sentences, buf = pop_sentences(buf)
                    yield from sentences
                elif ev.get("type") == "tool_calls":
                    tool_calls = ev["tool_calls"]
            if buf.strip():
                yield buf.strip()
            if not tool_calls:
                return
            # 回填 assistant 工具调用消息 + 各工具结果，进入下一轮
            messages.append({
                "role": "assistant",
                "content": buf or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in tool_calls
                ],
            })
            for c in tool_calls:
                result = self._registry.dispatch(c["name"], c["arguments"])
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
