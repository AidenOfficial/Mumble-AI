"""技能注册表：聚合 specs 喂给 LLM，按名分发工具调用。"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, ctx):
        self._ctx = ctx
        self._skills: dict = {}

    def register(self, skill):
        self._skills[skill.name] = skill
        return self

    def specs(self) -> list | None:
        return [s.spec() for s in self._skills.values()] or None

    def dispatch(self, name: str, arguments) -> str:
        skill = self._skills.get(name)
        if skill is None:
            return f"未知技能：{name}"
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return "参数解析失败。"
        else:
            args = arguments or {}
        try:
            return skill.run(args, self._ctx) or "完成。"
        except Exception as e:
            log.exception("技能 %s 执行失败", name)
            return f"技能执行出错：{e}"
