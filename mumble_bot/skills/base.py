"""Skill（工具）抽象 + 执行上下文。

每个 Skill 暴露一个 OpenAI function-calling 规格（spec），LLM 据此决定何时调用。
依赖通过 SkillContext 的 callable 注入，避免技能直接耦合具体组件，便于单测。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class SkillContext:
    speak: Callable[[list, str], None]   # (句子列表, source) -> 让 bot 开口
    send_channel: Callable[[str], None]  # (text) -> 发频道文字（操作其他 bot）
    timers: object                       # TimerService
    privacy: object                      # PrivacyState
    store: object                        # TranscriptStore
    external_bots: dict                  # 可控外部 bot 配置
    clock: Callable[[], float]


class Skill(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}}

    def spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def run(self, args: dict, ctx: SkillContext) -> str:
        """执行技能，返回给 LLM 的结果字符串（模型据此自然地口头确认）。"""
