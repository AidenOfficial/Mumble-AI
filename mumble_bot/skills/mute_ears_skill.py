"""自我屏蔽：捂耳朵 N 分钟。

停止收听/转写（privacy.pause→收音回调直接丢弃，连 STT 都不喂），到点自动恢复，
时长>90s 时在结束前 1 分钟提醒。语音触发——有人对机器人说"蒙住耳朵十分钟"，LLM 调本技能。
"""

from __future__ import annotations

from .base import Skill, SkillContext


class MuteEarsSkill(Skill):
    name = "mute_ears"
    description = (
        "暂时捂住耳朵：在指定分钟数内停止收听和转写所有语音（保护隐私），到点自动恢复，"
        "并在快结束时提醒。当有人说『蒙住耳朵/捂耳朵/别听了/暂停听 N 分钟』之类时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {"minutes": {"type": "number", "description": "捂耳朵多少分钟"}},
        "required": ["minutes"],
    }

    def run(self, args: dict, ctx: SkillContext) -> str:
        try:
            minutes = float(args.get("minutes", 0))
        except (TypeError, ValueError):
            return "时长无效。"
        if minutes <= 0:
            return "时长要大于 0 分钟。"
        secs = minutes * 60.0
        ctx.privacy.pause()

        if secs > 90:
            ctx.timers.schedule(
                secs - 60.0,
                lambda: ctx.speak(["还有一分钟我就恢复听力了。"], "mute"),
                label="mute-remind",
            )

        def resume():
            ctx.privacy.resume()
            ctx.speak(["我恢复听力了。"], "mute")

        ctx.timers.schedule(secs, resume, label="mute-resume")
        return f"好，我捂耳朵 {minutes:g} 分钟，期间不听不转写，到点自动恢复。"
