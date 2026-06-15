"""pymumble 装配：收音回调（只入队，不阻塞）、文字命令路由、注音回灌、身份/传输信号。

回调跑在 pymumble 内部线程，handler 必须快：on_sound 只做 resolve + 转交 STTManager（其内部
再丢给 per-session worker），绝不在这里做网络/STT。
"""

from __future__ import annotations

import logging
import re
import threading
import time

import pymumble_py3 as pymumble
from pymumble_py3.constants import (
    PYMUMBLE_CLBK_SOUNDRECEIVED,
    PYMUMBLE_CLBK_TEXTMESSAGERECEIVED,
    PYMUMBLE_CLBK_USERREMOVED,
)

log = logging.getLogger(__name__)
_TAG = re.compile(r"<[^>]+>")  # Mumble 文字消息可能带 HTML 标签


class MumbleClient:
    def __init__(self, cfg, *, resolver, stt_manager, privacy, command_handler=None, clock=time.time):
        self._cfg = cfg
        self._resolver = resolver
        self._stt = stt_manager
        self._privacy = privacy
        self._cmd = command_handler
        self._clock = clock
        self._my_sess = None
        self._last_tx: dict[int, float] = {}   # session -> 最近收到音频时刻（所有人，含被除名）
        self._tx_lock = threading.Lock()

        m = cfg.mumble
        self.mumble = pymumble.Mumble(
            m.host, m.username, port=m.port, password=m.password,
            certfile=m.certfile or None, reconnect=True,
        )
        self.mumble.set_receive_sound(True)
        self.mumble.callbacks.set_callback(PYMUMBLE_CLBK_SOUNDRECEIVED, self._on_sound)
        self.mumble.callbacks.set_callback(PYMUMBLE_CLBK_TEXTMESSAGERECEIVED, self._on_text)
        self.mumble.callbacks.set_callback(PYMUMBLE_CLBK_USERREMOVED, self._on_user_removed)

    def set_command_handler(self, handler) -> None:
        self._cmd = handler

    # ---------- 连接 ----------
    def connect(self) -> None:
        self.mumble.start()
        self.mumble.is_ready()  # 阻塞直到连上
        m = self._cfg.mumble
        if m.channel:
            try:
                self.mumble.channels.find_by_name(m.channel).move_in()
            except Exception:
                log.warning("找不到频道 %s，留在默认频道", m.channel)
        self._assert_hash()
        if self._cfg.behavior.announce_on_join:
            self.send_channel(self._cfg.behavior.announce_on_join)

    def _my_session(self):
        if self._my_sess is None:
            try:
                self._my_sess = self.mumble.users.myself["session"]
            except Exception:
                return None
        return self._my_sess

    def _assert_hash(self) -> None:
        """启动断言：身份/管理员判定依赖 user['hash']（未文档化）。缺失则告警，不崩。"""
        unverifiable = [
            u.get("name") for u in list(self.mumble.users.values())
            if not u.get("hash") and u.get("user_id") is None
        ]
        if unverifiable:
            log.warning("这些用户无 hash 也非注册（游客）：%s —— 他们需 !me 自报或在服务器注册", unverifiable)

    # ---------- 回调 ----------
    def _on_sound(self, user, soundchunk) -> None:
        now = self._clock()
        session = user["session"]
        with self._tx_lock:
            self._last_tx[session] = now
        if session == self._my_session():
            return
        if self._privacy.is_paused():
            return
        canonical = self._resolver.resolve(user)
        if canonical is None:  # 被除名：连流都不开
            return
        self._stt.feed(session, canonical, soundchunk.pcm)

    def _on_text(self, message) -> None:
        if self._cmd is None:
            return
        try:
            actor = self.mumble.users[message.actor]
        except Exception:
            return
        text = _TAG.sub("", message.message or "").strip()
        if text:
            self._cmd.handle(actor, text)

    def _on_user_removed(self, user, *rest) -> None:
        session = user.get("session")
        if session is None:
            return
        self._resolver.clear_session(session)
        self._stt.close_session(session)
        with self._tx_lock:
            self._last_tx.pop(session, None)

    # ---------- 供 speaker / proactive / commands ----------
    def add_sound(self, pcm48k: bytes) -> None:
        self.mumble.sound_output.add_sound(pcm48k)

    def anyone_transmitting(self, within: float | None = None) -> bool:
        within = self._cfg.behavior.transmit_active_sec if within is None else within
        now = self._clock()
        my = self._my_session()
        with self._tx_lock:
            return any(now - ts <= within for s, ts in self._last_tx.items() if s != my)

    def silence_duration(self) -> float:
        now = self._clock()
        my = self._my_session()
        with self._tx_lock:
            ts = [t for s, t in self._last_tx.items() if s != my]
        return (now - max(ts)) if ts else 1e9

    def list_users(self) -> list:
        my = self._my_session()
        users = [u for s, u in self.mumble.users.items() if s != my]
        return sorted(users, key=lambda u: u.get("session", 0))

    def send_channel(self, text: str) -> None:
        try:
            self.mumble.my_channel().send_text_message(text)
        except Exception:
            log.exception("发送频道消息失败")

    def send_private(self, user, text: str) -> None:
        try:
            user.send_text_message(text)
        except Exception:
            log.exception("发送私信失败")

    def stop(self) -> None:
        try:
            self.mumble.stop()
        except Exception:
            pass
