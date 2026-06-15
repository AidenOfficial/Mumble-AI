"""阿里 DashScope paraformer-realtime-v2 流式识别。

输入 16kHz PCM（Mumble 48k 已由上层重采样）。interim + final 都会回调；
词/句级时间戳由 DashScope 提供，但我们不用它当墙钟（见计划"时间戳铁律"），只取文本与 final 标志。
"""

from __future__ import annotations

from collections.abc import Callable

from .base import STTResult, STTStream


# region -> (http endpoint, websocket endpoint)
_ENDPOINTS = {
    "cn": ("https://dashscope.aliyuncs.com/api/v1",
           "wss://dashscope.aliyuncs.com/api-ws/v1/inference"),
    "intl": ("https://dashscope-intl.aliyuncs.com/api/v1",
             "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"),
}


def make_dashscope_factory(api_key: str, model: str, sample_rate: int, region: str = "cn"):
    """返回 MakeStream 工厂。region: cn=国内 / intl=国际(Singapore)。

    在此设置 SDK 全局 api_key 与 endpoint（按 region）；流对象只负责开流。
    """
    import dashscope

    dashscope.api_key = api_key
    http, ws = _ENDPOINTS.get(region, _ENDPOINTS["cn"])
    dashscope.base_http_api_url = http
    dashscope.base_websocket_api_url = ws

    def factory(on_result: Callable[[STTResult], None]) -> STTStream:
        return _DashScopeStream(on_result, model=model, sample_rate=sample_rate)

    return factory


class _DashScopeStream(STTStream):
    def __init__(self, on_result, *, model, sample_rate):
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        class _CB(RecognitionCallback):
            def on_event(self, result):
                try:
                    sentence = result.get_sentence()
                except Exception:
                    return
                if not sentence:
                    return
                text = sentence.get("text") if isinstance(sentence, dict) else getattr(sentence, "text", None)
                if not text:
                    return
                try:
                    is_final = RecognitionResult.is_sentence_end(sentence)
                except Exception:
                    is_final = False
                on_result(STTResult(text=text, is_final=is_final))

            def on_error(self, result):  # noqa: D401
                pass

            def on_complete(self):
                pass

            def on_close(self):
                pass

        # language_hints 仅部分模型支持，老 SDK 不认就退回不带
        common = dict(model=model, format="pcm", sample_rate=sample_rate, callback=_CB())
        try:
            self._rec = Recognition(language_hints=["zh"], **common)
        except TypeError:
            self._rec = Recognition(**common)
        self._rec.start()

    def feed(self, pcm16k: bytes) -> None:
        self._rec.send_audio_frame(pcm16k)

    def close(self) -> None:
        try:
            self._rec.stop()
        except Exception:
            pass
