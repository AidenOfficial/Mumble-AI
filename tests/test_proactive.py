from mumble_bot.buffer import Utterance
from mumble_bot.config import BehaviorConfig
from mumble_bot.proactive import ProactiveEvaluator, unanswered_question


def U(text, t_end):
    return Utterance("i", "A", text, t_end, t_end)


# ---------- 纯函数：未应答提问 ----------
def test_unanswered_question_true():
    assert unanswered_question([U("有人吗？", 100.0)], now=110.0, threshold_sec=8.0)


def test_unanswered_question_too_recent():
    assert not unanswered_question([U("有人吗？", 100.0)], now=102.0, threshold_sec=8.0)


def test_unanswered_question_not_a_question():
    assert not unanswered_question([U("今天吃了饭", 100.0)], now=200.0, threshold_sec=8.0)


def test_unanswered_question_helpword():
    assert unanswered_question([U("有没有人知道怎么弄", 100.0)], now=120.0, threshold_sec=8.0)


def test_unanswered_empty():
    assert not unanswered_question([], now=100.0, threshold_sec=8.0)


# ---------- 门控 + tick ----------
class FakeSpeaker:
    def __init__(self):
        self.last_spoke_ts = 0.0
        self.spoken = []
        self._speaking = False

    def is_speaking(self):
        return self._speaking

    def speak(self, sentences, source="proactive"):
        self.spoken.append((list(sentences), source))


class FakeStore:
    def __init__(self, w):
        self._w = w

    def recent(self, window_sec=None):
        return self._w


class FakePrivacy:
    muted = False
    paused = False

    def is_muted(self):
        return self.muted

    def is_paused(self):
        return self.paused


class FakeLLM:
    def __init__(self, verdict):
        self._v = verdict

    def json_verdict(self, system, user):
        return self._v

    def complete_stream(self, system, user):
        yield ""


def make_eval(window, *, anyone=False, silence=10.0, verdict=None, clock=1000.0):
    cfg = BehaviorConfig()  # cooldown 180, silence_gate 2.5, unanswered 8, window 3600
    sp = FakeSpeaker()
    ev = ProactiveEvaluator(
        FakeStore(window), FakeLLM(verdict or {"speak": False}), sp,
        anyone_transmitting=lambda: anyone, silence_duration=lambda: silence,
        privacy=FakePrivacy(), cfg=cfg, clock=lambda: clock,
    )
    return ev, sp


def test_gate_blocks_when_transmitting():
    ev, _ = make_eval([U("有人吗？", 100.0)], anyone=True)
    assert not ev.gate()


def test_gate_blocks_short_silence():
    ev, _ = make_eval([U("有人吗？", 990.0)], silence=1.0)
    assert not ev.gate()


def test_gate_passes_then_tick_speaks():
    ev, sp = make_eval([U("有人吗？", 980.0)], verdict={"speak": True, "text": "我在"})
    assert ev.gate()
    ev.tick()
    assert sp.spoken and sp.spoken[0][0] == ["我在"]


def test_tick_respects_verdict_false():
    ev, sp = make_eval([U("有人吗？", 980.0)], verdict={"speak": False})
    ev.tick()
    assert not sp.spoken
