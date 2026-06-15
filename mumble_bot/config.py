"""配置加载：config.yaml + 环境变量 → Config dataclass。

约定：所有 API key / 密码走环境变量（见 .env.example），不写进 yaml；
env 覆盖 yaml。未知字段忽略，缺省走 dataclass 默认值。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class MumbleConfig:
    host: str = "localhost"
    port: int = 64738
    username: str = "豆沙"
    password: str = ""
    certfile: str | None = None
    channel: str = ""
    tls_verify: bool = False    # 默认不校验服务器证书：Mumble 用证书做身份(TOFU)、服务器多自签，开校验反而连不上
    tls_ca_certs: str = ""      # 可选 CA 证书(PEM)路径；空=系统默认 CA。仅 tls_verify=true 生效


@dataclass
class DashScopeConfig:
    api_key: str = ""
    model: str = "paraformer-realtime-v2"
    sample_rate: int = 16000
    region: str = "cn"   # cn=国内(dashscope.aliyuncs.com) / intl=国际(dashscope-intl，Singapore)


@dataclass
class FishConfig:
    api_key: str = ""
    voice_id: str = ""
    model: str = "s2-pro"
    output_format: str = "pcm"
    sample_rate: int = 48000   # 请求 Fish 直接输出 48k（注入 Mumble 免重采样）。
    # ⚠️ 若 Fish 实际不按此采样率输出，注入会变调——上线前用真实 key 核对，必要时改这里并由 speaker 重采样。


@dataclass
class OpenRouterConfig:
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "deepseek/deepseek-v4-flash"
    tool_model: str = ""   # 空=同 model；可设 deepseek/deepseek-v4-pro 给工具/复杂路径用更强的模型
    provider_order: list[str] = field(default_factory=lambda: ["fireworks", "deepinfra", "parasail", "novita"])
    provider_sort: str = ""   # 空=按 order 有序回退；可设 throughput/latency/price 让 OpenRouter 自动排
    allow_fallbacks: bool = True
    referer: str = ""          # OpenRouter 可选 HTTP-Referer
    title: str = "mumble-ai-bot"


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


@dataclass
class GeminiConfig:
    api_key: str = ""
    model: str = "gemini-3.5-flash"
    thinking_level: str = "low"


@dataclass
class BehaviorConfig:
    window_sec: float = 3600.0
    cooldown_sec: float = 180.0
    silence_gate_sec: float = 2.5
    stt_close_silence_sec: float = 0.8
    transmit_active_sec: float = 0.3
    wake_regex: str = r"(?:嘿|哎|喂)?\s*豆沙"
    wake_fuzzy_threshold: int = 80
    wake_fuzzy_terms: list[str] = field(default_factory=list)
    wake_followup_timeout_sec: float = 4.0
    proactive_enabled: bool = True
    proactive_tick_sec: float = 1.0
    unanswered_question_sec: float = 8.0
    llm_provider: str = "openrouter"   # openrouter（主）/ deepseek（直连）/ gemini
    llm_fallback: str = "gemini"       # 主路失败时自动落它；仅当该 provider 有 key 时启用，"" 关闭
    data_dir: str = "./data"
    admin_keys: list[str] = field(default_factory=list)
    command_prefix: str = ","   # 文字命令前缀；用 , 避开点歌bot 等 ! 命令的冲突
    persona: str = "你是频道里一个有点意思的伙伴，说话自然、简短、有点性格，别像客服。"
    announce_on_join: str = "（豆沙已上线，会转写本频道对话；说「豆沙」可以叫我，发 ,pause 可暂停转写。）"


@dataclass
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"   # 容器内绑全网卡；对外暴露由 compose 端口映射 + password 控制
    port: int = 8080
    password: str = ""       # 设了才要求登录（Bearer）；留空=无鉴权（仅限可信网络/本机）


@dataclass
class Config:
    mumble: MumbleConfig = field(default_factory=MumbleConfig)
    dashscope: DashScopeConfig = field(default_factory=DashScopeConfig)
    fish: FishConfig = field(default_factory=FishConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    web: WebConfig = field(default_factory=WebConfig)
    external_bots: dict = field(default_factory=dict)   # 可控外部 bot：{key: {commands: {action: 模板}}}


def _section(dc_type, data):
    """从 dict 构造一个 section dataclass，忽略未知键。"""
    data = data or {}
    known = {f.name for f in fields(dc_type)}
    return dc_type(**{k: v for k, v in data.items() if k in known})


def load_config(path: str | os.PathLike | None = None) -> Config:
    """读取 yaml（默认 ./config.yaml，可被 CONFIG_PATH 覆盖）并叠加环境变量。

    yaml 不存在时返回全默认值 + env（便于纯逻辑测试）。
    """
    path = Path(path or os.environ.get("CONFIG_PATH", "config.yaml"))
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    cfg = Config(
        mumble=_section(MumbleConfig, raw.get("mumble")),
        dashscope=_section(DashScopeConfig, raw.get("dashscope")),
        fish=_section(FishConfig, raw.get("fish")),
        openrouter=_section(OpenRouterConfig, raw.get("openrouter")),
        deepseek=_section(DeepSeekConfig, raw.get("deepseek")),
        gemini=_section(GeminiConfig, raw.get("gemini")),
        behavior=_section(BehaviorConfig, raw.get("behavior")),
        web=_section(WebConfig, raw.get("web")),
        external_bots=raw.get("external_bots") or {},
    )
    _apply_env(cfg)
    return cfg


def _apply_env(cfg: Config) -> None:
    """环境变量覆盖（密钥与连接信息）。"""
    env = os.environ
    if v := env.get("MUMBLE_HOST"):
        cfg.mumble.host = v
    if v := env.get("MUMBLE_PORT"):
        cfg.mumble.port = int(v)
    if v := env.get("MUMBLE_USERNAME"):
        cfg.mumble.username = v
    if v := env.get("MUMBLE_PASSWORD"):
        cfg.mumble.password = v
    if v := env.get("DASHSCOPE_API_KEY"):
        cfg.dashscope.api_key = v
    if v := env.get("FISH_API_KEY"):
        cfg.fish.api_key = v
    if v := env.get("OPENROUTER_API_KEY"):
        cfg.openrouter.api_key = v
    if v := env.get("DEEPSEEK_API_KEY"):
        cfg.deepseek.api_key = v
    if v := env.get("GEMINI_API_KEY"):
        cfg.gemini.api_key = v
    if v := env.get("WEB_PASSWORD"):
        cfg.web.password = v


def missing_keys(cfg: Config) -> list[str]:
    """返回缺失的关键密钥名（供 main 启动时告警；不抛异常以便部分链路调试）。"""
    out = []
    if not cfg.dashscope.api_key:
        out.append("DASHSCOPE_API_KEY")
    if not cfg.fish.api_key:
        out.append("FISH_API_KEY")
    if cfg.behavior.llm_provider == "openrouter" and not cfg.openrouter.api_key:
        out.append("OPENROUTER_API_KEY")
    if cfg.behavior.llm_provider == "deepseek" and not cfg.deepseek.api_key:
        out.append("DEEPSEEK_API_KEY")
    if cfg.behavior.llm_provider == "gemini" and not cfg.gemini.api_key:
        out.append("GEMINI_API_KEY")
    return out


_SECRET_FIELDS = {
    "mumble": ("password",),
    "dashscope": ("api_key",),
    "fish": ("api_key",),
    "openrouter": ("api_key",),
    "deepseek": ("api_key",),
    "gemini": ("api_key",),
    "web": ("password",),
}


def to_yaml_dict(cfg: Config) -> dict:
    """导出为可写回 config.yaml 的 dict（剔除密钥——密钥只走环境变量/.env）。"""
    d = asdict(cfg)
    for section, secrets in _SECRET_FIELDS.items():
        for k in secrets:
            d.get(section, {}).pop(k, None)
    return d


def save_config(cfg: Config, path: str | os.PathLike) -> None:
    """把当前配置写回 config.yaml（不含密钥），供 Web 改动持久化。"""
    path = Path(path)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(to_yaml_dict(cfg), allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")
