"""BotController：Web 界面与运行中 bot 之间的桥。

持有所有 live 组件引用；提供状态快照、可编辑配置的读/写（热应用 + 写回 yaml）、
试听、以及暂停/绑定等操作。on_utterance 也在这里（用 self.wake，便于热换唤醒词）。
"""

from __future__ import annotations

import json
import logging

from .config import save_config
from .orchestrator import fmt_clock
from .tts.fish_s2 import FishS2TTS
from .wake import WakeMatcher

log = logging.getLogger(__name__)


# 可编辑配置 schema：驱动 UI 表单 + 校验 + 应用。hot=True 即时生效，False 需重启。
SCHEMA = [
    # 音色
    {"path": "fish.voice_id", "group": "音色", "label": "音色 Model ID", "type": "str", "hot": True,
     "hint": "fish.audio 音色页 URL 里的 ID"},
    {"path": "fish.model", "group": "音色", "label": "模型档", "type": "enum", "hot": True,
     "options": ["s2-pro", "s1", "speech-1.6", "speech-1.5"]},
    {"path": "fish.sample_rate", "group": "音色", "label": "采样率", "type": "int", "hot": True},
    # 人设 / 对话
    {"path": "behavior.persona", "group": "人设/对话", "label": "人设", "type": "text", "hot": True},
    {"path": "behavior.announce_on_join", "group": "人设/对话", "label": "进频道公告", "type": "text", "hot": True},
    {"path": "behavior.window_sec", "group": "人设/对话", "label": "记忆窗口(秒)", "type": "float", "hot": True},
    # 唤醒 / 命令
    {"path": "behavior.wake_regex", "group": "唤醒/命令", "label": "唤醒词正则", "type": "str", "hot": True},
    {"path": "behavior.command_prefix", "group": "唤醒/命令", "label": "命令前缀", "type": "str", "hot": True},
    {"path": "behavior.admin_keys", "group": "唤醒/命令", "label": "管理员键(逗号分隔)", "type": "list", "hot": True},
    # 主动插话
    {"path": "behavior.proactive_enabled", "group": "主动插话", "label": "启用主动插话", "type": "bool", "hot": True},
    {"path": "behavior.cooldown_sec", "group": "主动插话", "label": "冷却(秒)", "type": "float", "hot": True},
    {"path": "behavior.silence_gate_sec", "group": "主动插话", "label": "静音门槛(秒)", "type": "float", "hot": True},
    {"path": "behavior.unanswered_question_sec", "group": "主动插话", "label": "未应答阈值(秒)", "type": "float", "hot": True},
    # 外部 bot
    {"path": "external_bots", "group": "外部bot", "label": "外部bot命令(JSON)", "type": "json", "hot": True},
    # LLM（需重启）
    {"path": "behavior.llm_provider", "group": "LLM", "label": "主 LLM", "type": "enum", "hot": False,
     "options": ["openrouter", "deepseek", "gemini"]},
    {"path": "behavior.llm_fallback", "group": "LLM", "label": "兜底", "type": "str", "hot": False},
    {"path": "openrouter.model", "group": "LLM", "label": "OpenRouter 模型", "type": "str", "hot": False},
    {"path": "openrouter.tool_model", "group": "LLM", "label": "工具模型(可空)", "type": "str", "hot": False},
    # STT（需重启）
    {"path": "dashscope.region", "group": "STT", "label": "DashScope 区域", "type": "enum", "hot": False,
     "options": ["cn", "intl"]},
    {"path": "dashscope.model", "group": "STT", "label": "STT 模型", "type": "str", "hot": False},
    # Mumble（需重启）
    {"path": "mumble.host", "group": "Mumble", "label": "服务器地址", "type": "str", "hot": False},
    {"path": "mumble.port", "group": "Mumble", "label": "端口", "type": "int", "hot": False},
    {"path": "mumble.username", "group": "Mumble", "label": "bot 名字", "type": "str", "hot": False},
    {"path": "mumble.channel", "group": "Mumble", "label": "频道(空=根)", "type": "str", "hot": False},
]
_BY_PATH = {m["path"]: m for m in SCHEMA}


def _get(cfg, path):
    obj = cfg
    for p in path.split("."):
        obj = getattr(obj, p)
    return obj


def _set(cfg, path, value):
    parts = path.split(".")
    obj = cfg
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)


def _coerce(value, t):
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    if t == "bool":
        return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    if t == "list":
        return value if isinstance(value, list) else [s.strip() for s in str(value).split(",") if s.strip()]
    if t == "json":
        return value if isinstance(value, (dict, list)) else json.loads(value or "{}")
    return str(value)


class BotController:
    def __init__(self, cfg, config_path, *, wake, speaker, orchestrator, store, privacy,
                 resolver, timers):
        self.cfg = cfg
        self.config_path = config_path
        self.wake = wake                 # 可热换
        self.speaker = speaker
        self.orchestrator = orchestrator
        self.store = store
        self.privacy = privacy
        self.resolver = resolver
        self.timers = timers
        # 这些在 main 里构造好后回填
        self.client = None
        self.command_handler = None
        self.stt_manager = None
        self.proactive = None
        self.log_buffer = None           # RingLogHandler，供 Web 日志面板

    def get_logs(self, after: int = 0, limit: int = 600) -> list:
        return self.log_buffer.get(after, limit) if self.log_buffer is not None else []

    # ---------- 通路1 final 回调（用 self.wake，便于热换） ----------
    def on_utterance(self, u) -> None:
        self.store.append(u)
        if self.privacy.is_muted():
            return
        matched, query = self.wake.match(u.text)
        if matched:
            log.info("唤醒命中：%s", u.text)
            self.speaker.speak(self.orchestrator.respond(query), source="wake")

    # ---------- 状态 ----------
    def snapshot_state(self) -> dict:
        users = []
        if self.client:
            try:
                for i, u in enumerate(self.client.list_users()):
                    canon = self.resolver.resolve(u)
                    users.append({
                        "idx": i, "raw": u.get("name"),
                        "name": canon if canon else u.get("name"),
                        "status": "除名" if canon is None else ("未绑定" if self.resolver.is_unbound(u) else "已绑定"),
                    })
            except Exception:
                pass
        transcript = []
        try:
            for x in self.store.recent(self.cfg.behavior.window_sec)[-40:]:
                transcript.append({"user": x.user, "text": x.text, "clock": fmt_clock(x.t_end)})
        except Exception:
            pass
        timers = []
        try:
            for r, _tid, label in self.timers.list():
                timers.append({"label": label, "remaining": round(r)})
        except Exception:
            pass
        return {
            "connected": bool(self.client and self.client.is_connected()),
            "channel": self.client.current_channel() if self.client else None,
            "paused": self.privacy.is_paused(),
            "muted": self.privacy.is_muted(),
            "mute_remaining": round(self.privacy.mute_remaining()),
            "speaking": self.speaker.is_speaking(),
            "users": users,
            "transcript": transcript,
            "timers": timers,
            "username": self.cfg.mumble.username,
            "voice_id": self.cfg.fish.voice_id,
            "llm_provider": self.cfg.behavior.llm_provider,
            "keys": {
                "openrouter": bool(self.cfg.openrouter.api_key),
                "dashscope": bool(self.cfg.dashscope.api_key),
                "fish": bool(self.cfg.fish.api_key),
                "gemini": bool(self.cfg.gemini.api_key),
            },
        }

    # ---------- 配置读 ----------
    def get_editable_config(self) -> list:
        out = []
        for m in SCHEMA:
            val = self.cfg.external_bots if m["path"] == "external_bots" else _get(self.cfg, m["path"])
            out.append({**m, "value": val})
        return out

    # ---------- 配置写（热应用 + 持久化） ----------
    def apply_config(self, patch: dict) -> dict:
        changed = []
        bad = {}
        for path, raw in patch.items():
            meta = _BY_PATH.get(path)
            if not meta:
                continue
            try:
                value = _coerce(raw, meta["type"])
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                bad[path] = str(e)
                continue
            if path == "external_bots":
                self.cfg.external_bots.clear()
                self.cfg.external_bots.update(value or {})
            else:
                _set(self.cfg, path, value)
            changed.append(path)
        self._hot_apply(changed)
        try:
            save_config(self.cfg, self.config_path)
        except Exception:
            log.exception("写回 config 失败")
        needs_restart = sorted({p for p in changed if not _BY_PATH[p]["hot"]})
        return {"changed": changed, "needs_restart": needs_restart, "errors": bad}

    def _hot_apply(self, changed) -> None:
        b = self.cfg.behavior
        if any(c.startswith("fish.") for c in changed):
            try:
                self.speaker.set_tts(FishS2TTS(
                    self.cfg.fish.api_key, self.cfg.fish.voice_id, self.cfg.fish.model,
                    self.cfg.fish.output_format, self.cfg.fish.sample_rate))
            except Exception:
                log.exception("重建 TTS 失败")
        if "behavior.persona" in changed:
            self.orchestrator.set_persona(b.persona)
        if "behavior.window_sec" in changed:
            self.orchestrator.set_window(b.window_sec)
            self.store.set_window(b.window_sec)
        if "behavior.wake_regex" in changed:
            self.wake = WakeMatcher(b.wake_regex, b.wake_fuzzy_threshold, b.wake_fuzzy_terms)
        if "behavior.command_prefix" in changed and self.command_handler:
            self.command_handler.set_prefix(b.command_prefix)
        if "behavior.admin_keys" in changed and self.command_handler:
            self.command_handler.set_admin_keys(b.admin_keys)
        # proactive 阈值：proactive 持有的就是 cfg.behavior 这个实例，改字段即时生效

    # ---------- 试听 ----------
    def test_speak(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        self.speaker.speak([text], source="web")
        return True

    # ---------- 操作 ----------
    def action(self, name: str, params: dict | None = None) -> bool:
        p = params or {}
        if name == "pause":
            self.privacy.pause()
        elif name == "resume":
            self.privacy.resume()
        elif name == "shutup":
            self.privacy.shutup(float(p.get("minutes", 5)))
        elif name == "comeback":
            self.privacy.unmute()
        elif name in ("bind", "exclude") and self.client:
            users = self.client.list_users()
            idx = int(p.get("idx", -1))
            if not (0 <= idx < len(users)):
                return False
            u = users[idx]
            if name == "bind":
                cn = (p.get("name") or "").strip()
                if not cn:
                    return False
                self.resolver.bind_session(u.get("session"), cn)
                if p.get("save"):
                    self.resolver.archive(self.resolver.stable_key(u), cn)
            else:
                self.resolver.exclude(self.resolver.stable_key(u), save=bool(p.get("save")))
                self.resolver.clear_session(u.get("session"))
        else:
            return False
        return True
