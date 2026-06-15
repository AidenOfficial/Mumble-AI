import pytest

# 需要 fishaudio SDK（venv/CI 有）；缺失则跳过
pytest.importorskip("fishaudio")

from mumble_bot.tts.fish_s2 import FishS2TTS


def test_constructs_with_pcm_config():
    t = FishS2TTS(api_key="dummy", voice_id="some_model_id",
                  model="s2-pro", output_format="pcm", sample_rate=48000)
    assert t.sample_rate == 48000
    assert t._config.sample_rate == 48000
    assert t._config.format == "pcm"
    assert t._model == "s2-pro"
    assert t._voice_id == "some_model_id"


def test_empty_voice_id_becomes_none():
    t = FishS2TTS(api_key="dummy", voice_id="", sample_rate=48000)
    assert t._voice_id is None
