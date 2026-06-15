from mumble_bot.llm.failover import FailoverLLM


class Boom:
    """主路：建连即抛（流在首个 next 抛错）。"""

    def complete_stream(self, system, user):
        raise RuntimeError("down")
        yield  # noqa: 使其成为生成器

    def stream_chat(self, messages, tools=None):
        raise RuntimeError("down")
        yield

    def json_verdict(self, system, user):
        raise RuntimeError("down")


class Good:
    def __init__(self):
        self.called = 0

    def complete_stream(self, system, user):
        self.called += 1
        yield "兜底"
        yield "回答"

    def stream_chat(self, messages, tools=None):
        self.called += 1
        yield {"type": "content", "text": "兜底"}

    def json_verdict(self, system, user):
        self.called += 1
        return {"speak": False, "via": "fallback"}


def test_complete_stream_failover():
    fb = Good()
    f = FailoverLLM(Boom(), fb)
    assert list(f.complete_stream("s", "u")) == ["兜底", "回答"]
    assert fb.called == 1


def test_stream_chat_failover():
    fb = Good()
    f = FailoverLLM(Boom(), fb)
    assert list(f.stream_chat([], None)) == [{"type": "content", "text": "兜底"}]
    assert fb.called == 1


def test_json_verdict_failover():
    fb = Good()
    f = FailoverLLM(Boom(), fb)
    assert f.json_verdict("s", "u")["via"] == "fallback"


def test_primary_success_skips_fallback():
    class Primary:
        def complete_stream(self, system, user):
            yield "主路"

        def stream_chat(self, messages, tools=None):
            yield {"type": "content", "text": "主路"}

        def json_verdict(self, system, user):
            return {"ok": 1}

    fb = Good()
    f = FailoverLLM(Primary(), fb)
    assert list(f.complete_stream("s", "u")) == ["主路"]
    assert f.json_verdict("s", "u") == {"ok": 1}
    assert fb.called == 0


def test_mid_stream_break_truncates_no_restart():
    class MidBreak:
        def complete_stream(self, system, user):
            yield "一"
            raise RuntimeError("mid")

        def stream_chat(self, messages, tools=None):
            yield {}

        def json_verdict(self, system, user):
            return {}

    fb = Good()
    f = FailoverLLM(MidBreak(), fb)
    # 已吐 "一" 才断 → 截断，不重启兜底
    assert list(f.complete_stream("s", "u")) == ["一"]
    assert fb.called == 0
