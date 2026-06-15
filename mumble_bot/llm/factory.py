"""按 config 选 LLM 实现，并按需包一层故障转移。

默认 openrouter（路由 deepseek-v4-flash 到快速 Western provider，reasoning 关思考）主，
gemini 兜底（仅当配了 GEMINI_API_KEY 时启用）。具体 SDK 在各实现里局部导入，这里 import 安全。
"""

from __future__ import annotations

from .base import LLMClient


def _build_one(cfg, name: str) -> LLMClient:
    if name == "gemini":
        from .gemini import GeminiClient

        return GeminiClient(cfg.gemini.api_key, cfg.gemini.model, cfg.gemini.thinking_level)

    if name == "deepseek":
        from .deepseek import DeepSeekClient

        return DeepSeekClient(cfg.deepseek.api_key, cfg.deepseek.base_url, cfg.deepseek.model)

    # 默认：OpenRouter
    from .openai_compat import OpenAICompatLLM

    o = cfg.openrouter
    prov: dict = {"allow_fallbacks": o.allow_fallbacks}
    if o.provider_sort:
        prov["sort"] = o.provider_sort           # throughput/latency/price 自动排
    elif o.provider_order:
        prov["order"] = list(o.provider_order)   # 有序回退（TTFT 优先）
    extra = {"reasoning": {"enabled": False}, "provider": prov}
    headers = {}
    if o.referer:
        headers["HTTP-Referer"] = o.referer
    if o.title:
        headers["X-Title"] = o.title
    return OpenAICompatLLM(
        o.api_key, o.base_url, o.model,
        extra_body=extra, default_headers=headers or None,
        tool_model=o.tool_model or o.model,
    )


def _has_key(cfg, name: str) -> bool:
    return bool({
        "openrouter": cfg.openrouter.api_key,
        "deepseek": cfg.deepseek.api_key,
        "gemini": cfg.gemini.api_key,
    }.get(name))


def build_llm(cfg) -> LLMClient:
    primary = _build_one(cfg, cfg.behavior.llm_provider)
    fb = cfg.behavior.llm_fallback
    # 仅当兜底与主路不同、且兜底确有 key 时才包故障转移（否则构造兜底会因缺 key 失败）
    if fb and fb != cfg.behavior.llm_provider and _has_key(cfg, fb):
        from .failover import FailoverLLM

        return FailoverLLM(primary, _build_one(cfg, fb))
    return primary
