"""Fish Audio OpenAudio TTS（官方 `fishaudio` SDK，对齐 docs.fish.audio）。

用 client.tts.stream —— 官方的 HTTP 流式：整句文本进、音频块流式出、低首音延迟，
正好配合 orchestrator 的句级分块（每出一句就合成播放，同时 LLM 还在生成下一句）。

- model: speech-1.5/1.6/s1/s2-pro（我们用 s2-pro）。
- reference_id: 音色的 Model ID（在 fish.audio 音色页拿，或克隆后得到；填 config.fish.voice_id）。
- sample_rate/format 在 TTSConfig 里；请求 48k PCM，注入 Mumble 免重采样。
  ⚠️ Fish 是否真按请求采样率输出需实测，不对就把 config.fish.sample_rate 改成实际值，speaker 会重采样。

更激进的 client.tts.stream_websocket（边产 token 边出声）留作后续首音优化。
"""

from __future__ import annotations

from collections.abc import Iterator

from .base import TTSEngine


class FishS2TTS(TTSEngine):
    def __init__(self, api_key: str, voice_id: str, model: str = "s2-pro",
                 output_format: str = "pcm", sample_rate: int = 48000):
        from fishaudio import FishAudio
        from fishaudio.types.tts import TTSConfig

        self._client = FishAudio(api_key=api_key, timeout=30.0)  # 默认 240s，太长会拖死 speaker
        self._voice_id = voice_id or None
        self._model = model
        self.sample_rate = sample_rate
        # latency=balanced 偏流式低首音；sample_rate/format 只能经 TTSConfig 传
        self._config = TTSConfig(format=output_format, sample_rate=sample_rate, latency="balanced")

    def synthesize_stream(self, text: str) -> Iterator[bytes]:
        text = text.strip()
        if not text:
            return
        for chunk in self._client.tts.stream(
            text=text,
            reference_id=self._voice_id,
            model=self._model,
            config=self._config,
        ):
            if chunk:
                yield chunk
