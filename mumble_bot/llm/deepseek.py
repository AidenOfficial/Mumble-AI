"""DeepSeek V4 直连（OpenAI 兼容）。现为 OpenAICompatLLM 的薄壳，关思考。

注：默认走 OpenRouter（见 factory）；这个直连客户端仅在 llm_provider=deepseek 时用。
"""

from __future__ import annotations

from .openai_compat import OpenAICompatLLM


class DeepSeekClient(OpenAICompatLLM):
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(api_key=api_key, base_url=base_url, model=model,
                         extra_body={"thinking": {"type": "disabled"}})
