import numpy as np

from mumble_bot.audio import (
    StreamResampler,
    pcm_duration_sec,
    resample_pcm16,
)


def _sine(rate: int, secs: float, freq: int = 440) -> bytes:
    t = np.arange(int(rate * secs))
    x = (0.3 * 32767 * np.sin(2 * np.pi * freq * t / rate)).astype(np.int16)
    return x.tobytes()


def test_duration():
    pcm = _sine(48000, 1.0)
    assert abs(pcm_duration_sec(pcm, 48000) - 1.0) < 1e-6


def test_resample_48k_to_16k_length():
    out = resample_pcm16(_sine(48000, 1.0), 48000, 16000)
    n = len(out) // 2
    assert abs(n - 16000) < 50  # 约 1/3 长度


def test_passthrough_and_empty():
    pcm = _sine(16000, 0.1)
    assert resample_pcm16(pcm, 16000, 16000) == pcm
    assert resample_pcm16(b"", 48000, 16000) == b""


def test_stream_resampler_total_length():
    pcm = _sine(48000, 0.5)
    rs = StreamResampler(48000, 16000)
    chunk = int(48000 * 0.02) * 2  # 20ms 一块
    out = b"".join(rs.process(pcm[i:i + chunk]) for i in range(0, len(pcm), chunk))
    out += rs.process(b"", last=True)
    n = len(out) // 2
    assert abs(n - 8000) < 200  # 0.5s @16k ≈ 8000 样本


def test_stream_resampler_passthrough():
    rs = StreamResampler(48000, 48000)
    pcm = _sine(48000, 0.05)
    assert rs.process(pcm) == pcm
