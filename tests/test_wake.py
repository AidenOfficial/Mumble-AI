from mumble_bot.config import BehaviorConfig
from mumble_bot.wake import WakeMatcher

DEFAULT = BehaviorConfig().wake_regex


def test_match_with_query():
    ok, q = WakeMatcher(DEFAULT).match("嘿豆沙 今天天气怎么样")
    assert ok and q == "今天天气怎么样"


def test_match_bare_name_no_query():
    ok, q = WakeMatcher(DEFAULT).match("豆沙")
    assert ok and q == ""


def test_match_with_greeting():
    ok, q = WakeMatcher(DEFAULT).match("喂豆沙在吗")
    assert ok and q == "在吗"


def test_no_match():
    ok, q = WakeMatcher(DEFAULT).match("今天去哪吃饭")
    assert not ok and q == ""


def test_query_strips_punctuation():
    ok, q = WakeMatcher(DEFAULT).match("豆沙，帮我查个天气")
    assert ok and q == "帮我查个天气"


def test_fuzzy_optional():
    w = WakeMatcher(r"豆沙", fuzzy_threshold=80, fuzzy_terms=["豆沙"])
    ok, _ = w.match("豆沙")
    assert ok
