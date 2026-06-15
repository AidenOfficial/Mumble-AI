"""倒计时 / 计时器技能。到点由 TimerService 触发，让 bot 主动开口提醒。"""

from __future__ import annotations

from .base import Skill, SkillContext


class TimerSkill(Skill):
    name = "set_timer"
    description = "设置一个倒计时/计时器。到点机器人会主动开口提醒。用于番茄钟、倒计时、定时提醒等。"
    parameters = {
        "type": "object",
        "properties": {
            "minutes": {"type": "number", "description": "多少分钟后提醒"},
            "label": {"type": "string", "description": "提醒内容，例如『番茄钟结束』『该喝水了』"},
        },
        "required": ["minutes"],
    }

    def run(self, args: dict, ctx: SkillContext) -> str:
        try:
            minutes = float(args.get("minutes", 0))
        except (TypeError, ValueError):
            return "时长无效。"
        if minutes <= 0:
            return "时长要大于 0 分钟。"
        label = (args.get("label") or "时间到了").strip()

        def fire():
            ctx.speak([f"{label}。{minutes:g}分钟到了。"], "timer")

        ctx.timers.schedule(minutes * 60.0, fire, label=f"timer:{label}")
        return f"已设置 {minutes:g} 分钟计时器（{label}），到点我会提醒。"
