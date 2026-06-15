"""操作频道里的点歌/音乐机器人。

通过给频道发该 bot 的文字命令实现（botamusique 等都吃 `!play`/`!skip` 文字命令）。
命令模板在 config.external_bots.<bot_key>.commands 里配，`{query}` 会被替换为歌名/参数。
"""

from __future__ import annotations

from .base import Skill, SkillContext


class MusicControlSkill(Skill):
    name = "music_control"
    description = "操作频道里的点歌/音乐机器人：点歌、切歌、暂停、继续、调音量等（通过给频道发它的命令）。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型，如 play / skip / pause / resume / stop / volume / next / prev",
            },
            "query": {"type": "string", "description": "歌名/关键词/音量值等（可选）"},
        },
        "required": ["action"],
    }

    def __init__(self, bot_key: str = "music"):
        self._bot_key = bot_key

    def run(self, args: dict, ctx: SkillContext) -> str:
        action = (args.get("action") or "").strip()
        query = (args.get("query") or "").strip()
        spec = (ctx.external_bots or {}).get(self._bot_key)
        if not spec:
            return "还没配置音乐机器人（config 的 external_bots.music）。"
        templates = spec.get("commands", {}) or {}
        tmpl = templates.get(action)
        if not tmpl:
            return f"音乐机器人不支持操作：{action}。支持的有：{', '.join(templates) or '无'}"
        try:
            cmd = tmpl.format(query=query)
        except (KeyError, IndexError):
            cmd = tmpl
        ctx.send_channel(cmd)
        return f"已让点歌机器人执行：{cmd}"
