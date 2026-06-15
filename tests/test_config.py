from mumble_bot.config import Config, load_config, missing_keys


def test_defaults_when_file_missing(tmp_path, monkeypatch):
    for k in ("DASHSCOPE_API_KEY", "FISH_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, Config)
    assert cfg.mumble.port == 64738
    assert cfg.dashscope.model == "paraformer-realtime-v2"
    assert cfg.deepseek.model == "deepseek-v4-flash"


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k1")
    monkeypatch.setenv("MUMBLE_PASSWORD", "pw")
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg.dashscope.api_key == "k1"
    assert cfg.mumble.password == "pw"


def test_yaml_load_and_unknown_keys_ignored(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "mumble:\n  host: h\n  port: 9\n  bogus: 1\n"
        "behavior:\n  window_sec: 10\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.mumble.host == "h" and cfg.mumble.port == 9
    assert cfg.behavior.window_sec == 10


def test_missing_keys_reports(tmp_path, monkeypatch):
    for k in ("DASHSCOPE_API_KEY", "FISH_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(tmp_path / "nope.yaml")
    miss = missing_keys(cfg)
    assert "DASHSCOPE_API_KEY" in miss and "FISH_API_KEY" in miss
