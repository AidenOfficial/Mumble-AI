from mumble_bot.stt.base import STTResult
from mumble_bot.stt.manager import STTManager


class FakeStream:
    """feed 即吐一个 final，便于验证 manager 的墙钟打戳与回调。"""

    def __init__(self, on_result):
        self._on_result = on_result
        self.closed = False

    def feed(self, pcm16k):
        self._on_result(STTResult(text="你好", is_final=True))

    def close(self):
        self.closed = True


class FakeInterimThenFinal:
    def __init__(self, on_result):
        self._on_result = on_result

    def feed(self, pcm16k):
        self._on_result(STTResult(text="半句", is_final=False))  # interim 不应落库

    def close(self):
        pass


def test_emits_utterance_with_wallclock():
    got = []
    clock = [1000.0]
    m = STTManager(lambda cb: FakeStream(cb), got.append,
                   in_rate=16000, out_rate=16000, close_silence=999, clock=lambda: clock[0])
    m.feed(session=1, canonical="A", pcm48k=b"\x00\x00" * 160)
    assert len(got) == 1
    u = got[0]
    assert u.user == "A" and u.text == "你好"
    assert u.t_start == 1000.0 and u.t_end == 1000.0


def test_interim_not_persisted():
    got = []
    m = STTManager(lambda cb: FakeInterimThenFinal(cb), got.append,
                   in_rate=16000, out_rate=16000, close_silence=999, clock=lambda: 5.0)
    m.feed(session=1, canonical="A", pcm48k=b"\x00\x00" * 160)
    assert got == []


def test_close_session_closes_stream():
    streams = []

    def factory(cb):
        s = FakeStream(cb)
        streams.append(s)
        return s

    m = STTManager(factory, lambda u: None,
                   in_rate=16000, out_rate=16000, close_silence=999, clock=lambda: 1.0)
    m.feed(session=1, canonical="A", pcm48k=b"\x00\x00" * 160)
    m.close_session(1)
    assert streams[0].closed
