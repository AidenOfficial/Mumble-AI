"""Fish Audio OpenAudio s2-pro 流式 TTS。

固定角色音用预先克隆好的 reference_id(voice_id)；情感可在文本里用自由标签（如 [laugh]）。
请求 PCM；理想情况直接请求 48k（注入 Mumble 免重采样）。⚠️ Fish 是否真按请求采样率输出
需用真实 key 核对——若变调，把 config.fish.sample_rate 改成实际值，speaker 会负责重采样。
"""

from __future__ import annotations

from collections.abc import Iterator

from .base import TTSEngine


class FishS2TTS(TTSEngine):
    def __init__(self, api_key: str, voice_id: str, model: str = "s2-pro",
                 output_format: str = "pcm", sample_rate: int = 48000):
        from fish_audio_sdk import Session, TTSRequest

        self._Session = Session
        self._TTSRequest = TTSRequest
        self._session = Session(api_key)
        self._voice_id = voice_id or None
        self._model = model
        self._format = output_format
        self.sample_rate = sample_rate

    def _build_request(self, text: str):
        kwargs = dict(text=text, reference_id=self._voice_id, format=self._format)
        # sample_rate 字段随 SDK 版本可能不存在
        try:
            return self._TTSRequest(sample_rate=self.sample_rate, **kwargs)
        except TypeError:
            return self._TTSRequest(**kwargs)

    def synthesize_stream(self, text: str) -> Iterator[bytes]:
        text = text.strip()
        if not text:
            return
        req = self._build_request(text)
        # backend 选模型版本（s2-pro）；老 SDK 不认就退回默认
        try:
            gen = self._session.tts(req, backend=self._model)
        except TypeError:
            gen = self._session.tts(req)
        for chunk in gen:
            if chunk:
                yield chunk
