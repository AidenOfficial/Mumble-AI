import pytest

# 需要 dashscope SDK（venv/CI 有）；缺失则跳过，保持纯逻辑测试可独立运行
dashscope = pytest.importorskip("dashscope")

from mumble_bot.stt.dashscope_paraformer import make_dashscope_factory


def test_region_intl_sets_intl_endpoint():
    make_dashscope_factory("k", "paraformer-realtime-v2", 16000, region="intl")
    assert "dashscope-intl.aliyuncs.com" in dashscope.base_websocket_api_url
    assert "dashscope-intl.aliyuncs.com" in dashscope.base_http_api_url


def test_region_cn_sets_domestic_endpoint():
    make_dashscope_factory("k", "paraformer-realtime-v2", 16000, region="cn")
    assert dashscope.base_websocket_api_url == "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    assert "dashscope-intl" not in dashscope.base_http_api_url


def test_region_unknown_falls_back_to_cn():
    make_dashscope_factory("k", "paraformer-realtime-v2", 16000, region="bogus")
    assert dashscope.base_websocket_api_url == "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
