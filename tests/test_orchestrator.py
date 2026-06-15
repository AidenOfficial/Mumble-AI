from mumble_bot.buffer import Utterance
from mumble_bot.orchestrator import (
    Orchestrator,
    build_system_prompt,
    fmt_clock,
    format_transcript,
    pop_sentences,
)


def U(user, text, t_end):
    return Utterance("i", user, text, t_end, t_end)


class FakeLLM:
    def __init__(self, deltas):
        self._d = deltas

    def complete_stream(self, system, user):
        yield from self._d

    def json_verdict(self, system, user):
        return {}


class FakeStore:
    def __init__(self, w):
        self._w = w

    def recent(self, window_sec=None):
        return self._w


def test_format_transcript():
    s = format_transcript([U("A", "你好", 100.0), U("B", "在吗", 160.0)])
    assert "A: 你好" in s and "B: 在吗" in s
    assert f"[{fmt_clock(100.0)}]" in s


def test_build_system_prompt_contains_now_and_transcript():
    s = build_system_prompt("人设X", 500.0, "转写内容")
    assert "人设X" in s and fmt_clock(500.0) in s and "转写内容" in s


def test_pop_sentences():
    sents, rest = pop_sentences("你好。在吗？嗯")
    assert sents == ["你好。", "在吗？"] and rest == "嗯"


def test_pop_sentences_no_end():
    sents, rest = pop_sentences("还没说完")
    assert sents == [] and rest == "还没说完"


def test_respond_yields_sentences():
    llm = FakeLLM(["你好", "，", "在吗", "？", "嗯嗯", "。"])
    o = Orchestrator(llm, FakeStore([]), window_sec=3600, persona="P", clock=lambda: 0.0)
    assert list(o.respond("q")) == ["你好，在吗？", "嗯嗯。"]


def test_build_prompt_empty_query_uses_default():
    o = Orchestrator(FakeLLM([]), FakeStore([]), window_sec=10, persona="P", clock=lambda: 0.0)
    _, user = o.build_prompt("", [])
    assert user
    _, user2 = o.build_prompt("具体问题", [])
    assert user2 == "具体问题"
