"""入口：装配所有组件、起线程、连接 Mumble、阻塞运行。

线程模型见计划 §A：pymumble 回调线程只入队；STT per-session worker + 看门狗；
speaker 单条输出 worker；proactive ~1Hz tick；timers 心跳线程。本函数只做装配与生命周期。
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time

from .buffer import TranscriptStore
from .commands import CommandHandler
from .config import load_config, missing_keys
from .controller import BotController
from .db import Database
from .identity import IdentityResolver
from .llm.factory import build_llm
from .orchestrator import Orchestrator
from .privacy import PrivacyState
from .proactive import ProactiveEvaluator
from .skills.base import SkillContext
from .skills.music_skill import MusicControlSkill
from .skills.mute_ears_skill import MuteEarsSkill
from .skills.registry import SkillRegistry
from .skills.timer_skill import TimerSkill
from .speaker import Speaker
from .stt.dashscope_paraformer import make_dashscope_factory
from .stt.manager import STTManager
from .timers import TimerService
from .tts.fish_s2 import FishS2TTS
from .wake import WakeMatcher
from .web.server import start_web

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    miss = missing_keys(cfg)
    if miss:
        log.warning("缺少密钥：%s（相关链路会失败）", ", ".join(miss))

    # --- 持久化与纯逻辑组件 ---
    os.makedirs(cfg.behavior.data_dir, exist_ok=True)
    db = Database(os.path.join(cfg.behavior.data_dir, "bot.db"))
    resolver = IdentityResolver(db=db, exclude_names=[cfg.mumble.username])
    store = TranscriptStore(db=db, window_sec=cfg.behavior.window_sec)
    wake = WakeMatcher(cfg.behavior.wake_regex, cfg.behavior.wake_fuzzy_threshold, cfg.behavior.wake_fuzzy_terms)
    privacy = PrivacyState()

    # --- 云服务客户端 ---
    llm = build_llm(cfg)
    tts = FishS2TTS(cfg.fish.api_key, cfg.fish.voice_id, cfg.fish.model,
                    cfg.fish.output_format, cfg.fish.sample_rate)

    # client 用 holder 延迟引用（打破 speaker/skills/proactive ↔ client 的循环）
    holder: dict = {}
    def anyone_transmitting() -> bool:
        c = holder.get("client")
        return c.anyone_transmitting() if c else False
    def silence_duration() -> float:
        c = holder.get("client")
        return c.silence_duration() if c else 1e9
    def audio_sink(pcm: bytes) -> None:
        c = holder.get("client")
        if c:
            c.add_sound(pcm)
    def send_channel(text: str) -> None:
        c = holder.get("client")
        if c:
            c.send_channel(text)

    speaker = Speaker(tts, audio_sink, anyone_transmitting)

    # --- 技能 / 工具 ---
    timers = TimerService()
    def speak_cb(sentences, source="skill"):
        speaker.speak(sentences, source)
    ctx = SkillContext(
        speak=speak_cb, send_channel=send_channel, timers=timers,
        privacy=privacy, store=store, external_bots=cfg.external_bots, clock=time.time,
    )
    registry = SkillRegistry(ctx)
    registry.register(TimerSkill())
    registry.register(MusicControlSkill())
    registry.register(MuteEarsSkill())

    orchestrator = Orchestrator(
        llm, store, window_sec=cfg.behavior.window_sec,
        persona=cfg.behavior.persona, registry=registry,
    )

    # --- 控制器：桥接 Web 界面与运行中组件；on_utterance 也在它身上（用 controller.wake 便于热换唤醒词） ---
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    controller = BotController(
        cfg, config_path, wake=wake, speaker=speaker, orchestrator=orchestrator,
        store=store, privacy=privacy, resolver=resolver, timers=timers,
    )

    stt_factory = make_dashscope_factory(
        cfg.dashscope.api_key, cfg.dashscope.model, cfg.dashscope.sample_rate, cfg.dashscope.region
    )
    stt_manager = STTManager(
        stt_factory, controller.on_utterance,
        in_rate=48000, out_rate=cfg.dashscope.sample_rate,
        close_silence=cfg.behavior.stt_close_silence_sec,
    )
    controller.stt_manager = stt_manager

    proactive = ProactiveEvaluator(
        store, llm, speaker,
        anyone_transmitting=anyone_transmitting, silence_duration=silence_duration,
        privacy=privacy, cfg=cfg.behavior,
    )
    controller.proactive = proactive

    # --- Mumble 客户端 + 命令处理器（先建 client 再注入 handler） ---
    from .mumble_client import MumbleClient
    client = MumbleClient(cfg, resolver=resolver, stt_manager=stt_manager, privacy=privacy)
    holder["client"] = client
    controller.client = client
    cmd = CommandHandler(
        resolver=resolver, privacy=privacy, admin_keys=cfg.behavior.admin_keys,
        list_users=client.list_users, reply=client.send_channel,
        reply_private=client.send_private, speaker=speaker,
        prefix=cfg.behavior.command_prefix,
    )
    client.set_command_handler(cmd)
    controller.command_handler = cmd

    # --- 启动 ---
    timers.start()
    stt_manager.start()
    speaker.start()
    start_web(controller, cfg)            # Web 管理界面（守护线程）
    log.info("连接 Mumble %s:%s ...", cfg.mumble.host, cfg.mumble.port)
    client.connect()
    proactive.start()
    log.info("已就绪。")

    # --- 阻塞直到收到停止信号 ---
    stop = threading.Event()
    def _handle_signal(signum, frame):
        log.info("收到信号 %s，退出中...", signum)
        stop.set()
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass

    try:
        while not stop.wait(1.0):
            pass
    finally:
        log.info("清理中...")
        proactive.stop()
        speaker.stop()
        stt_manager.stop()
        timers.stop()
        client.stop()
        db.close()


if __name__ == "__main__":
    main()
