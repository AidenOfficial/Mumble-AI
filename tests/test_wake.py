from mumble_bot.config import BehaviorConfig
from mumble_bot.wake import WakeMatcher

DEFAULT = BehaviorConfig().wake_regex


def test_match_with_query():
    ok, q = WakeMatcher(DEFAULT).match("嘿小特 今天天气怎么样")
    assert ok and q == "今天天气怎么样"


def test_match_bare_name_no_query():
    ok, q = WakeMatcher(DEFAULT).match("小特")
    assert ok and q == ""


def test_match_nickname():
    ok, q = WakeMatcher(DEFAULT).match("特特你好")
    assert ok and q == "你好"


def test_no_match():
    ok, q = WakeMatcher(DEFAULT).match("今天去哪吃饭")
    assert not ok and q == ""


def test_query_strips_punctuation():
    ok, q = WakeMatcher(DEFAULT).match("小特，帮我查个天气")
    assert ok and q == "帮我查个天气"


def test_fuzzy_optional():
    w = WakeMatcher(r"小特", fuzzy_threshold=80, fuzzy_terms=["小特"])
    ok, _ = w.match("小特")
    assert ok
