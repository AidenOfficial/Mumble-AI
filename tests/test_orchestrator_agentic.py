from mumble_bot.orchestrator import Orchestrator
from mumble_bot.skills.base import SkillContext
from mumble_bot.skills.registry import SkillRegistry
from mumble_bot.skills.timer_skill import TimerSkill


class FakeStore:
    def recent(self, window_sec=None):
        return []


class FakeTimers:
    def __init__(self):
        self.scheduled = []

    def schedule(self, delay, cb, label=""):
        self.scheduled.append((delay, cb, label))
        return 1


class FakeToolLLM:
    """按预设脚本逐轮 yield 事件；记录每轮收到的 messages。"""

    def __init__(self, rounds):
        self.rounds = rounds
        self.calls = []

    def stream_chat(self, messages, tools=None):
        self.calls.append(list(messages))
        yield from self.rounds[len(self.calls) - 1]


def make_registry():
    spoken = []
    ctx = SkillContext(
        speak=lambda s, src="skill": spoken.append(list(s)),
        send_channel=lambda t: None, timers=FakeTimers(), privacy=None,
        store=None, external_bots={}, clock=lambda: 0.0,
    )
    return SkillRegistry(ctx).register(TimerSkill()), spoken


def test_agentic_no_tool_streams_sentences():
    reg, _ = make_registry()
    llm = FakeToolLLM([[{"type": "content", "text": "你好。"},
                        {"type": "content", "text": "在的。"}]])
    o = Orchestrator(llm, FakeStore(), window_sec=3600, persona="P", clock=lambda: 0.0, registry=reg)
    assert list(o.respond("hi")) == ["你好。", "在的。"]


def test_agentic_tool_then_reply():
    reg, _ = make_registry()
    rounds = [
        [{"type": "tool_calls", "tool_calls": [
            {"id": "c1", "name": "set_timer", "arguments": '{"minutes":1,"label":"喝水"}'}]}],
        [{"type": "content", "text": "好，"},
         {"type": "content", "text": "一分钟后提醒你喝水。"}],
    ]
    llm = FakeToolLLM(rounds)
    o = Orchestrator(llm, FakeStore(), window_sec=3600, persona="P", clock=lambda: 0.0, registry=reg)
    out = list(o.respond("一分钟后提醒我喝水"))
    assert out == ["好，一分钟后提醒你喝水。"]
    # 第二轮 messages 应回填了 assistant(tool_calls) 与 tool 结果
    second = llm.calls[1]
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in second)
    assert any(m.get("role") == "tool" for m in second)


def test_agentic_stops_at_max_rounds():
    reg, _ = make_registry()
    # 每轮都要工具 → 应在 max_tool_rounds 后停止，不无限循环
    tool_round = [{"type": "tool_calls", "tool_calls": [
        {"id": "c", "name": "set_timer", "arguments": '{"minutes":1}'}]}]
    llm = FakeToolLLM([tool_round] * 10)
    o = Orchestrator(llm, FakeStore(), window_sec=3600, persona="P",
                     clock=lambda: 0.0, registry=reg, max_tool_rounds=3)
    list(o.respond("x"))
    assert len(llm.calls) == 3
