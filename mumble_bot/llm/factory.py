"""按 config 选 LLM 实现。具体 SDK 在各实现里局部导入，这里 import 安全。

默认 openrouter：路由 deepseek-v4-flash 到指定的快速 Western provider（Fireworks→DeepInfra→…），
reasoning 关思考。也可切 deepseek 直连或 gemini 兜底。
"""

from __future__ import annotations

from .base import LLMClient


def build_llm(cfg) -> LLMClient:
    provider = cfg.behavior.llm_provider

    if provider == "gemini":
        from .gemini import GeminiClient

        return GeminiClient(cfg.gemini.api_key, cfg.gemini.model, cfg.gemini.thinking_level)

    if provider == "deepseek":
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
