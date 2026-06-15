import yaml

from mumble_bot.config import load_config
from mumble_bot.controller import BotController
from mumble_bot.wake import WakeMatcher


class FakeSpeaker:
    def __init__(self):
        self.tts = None
        self.spoken = []

    def set_tts(self, t):
        self.tts = t

    def is_speaking(self):
        return False

    def speak(self, sents, source="x"):
        self.spoken.append(source)


class FakeOrch:
    def __init__(self):
        self.persona = None
        self.window = None

    def set_persona(self, p):
        self.persona = p

    def set_window(self, w):
        self.window = w

    def respond(self, q):
        yield "回应"


class FakeStore:
    def __init__(self):
        self.appended = []
        self.win = None

    def append(self, u):
        self.appended.append(u)

    def set_window(self, w):
        self.win = w

    def recent(self, w=None):
        return []


class FakePrivacy:
    def __init__(self):
        self._m = self._p = False

    def is_muted(self):
        return self._m

    def is_paused(self):
        return self._p

    def mute_remaining(self):
        return 0

    def pause(self):
        self._p = True

    def resume(self):
        self._p = False

    def shutup(self, m):
        self._m = True

    def unmute(self):
        self._m = False


class FakeResolver:
    def resolve(self, u):
        return u.get("name")

    def is_unbound(self, u):
        return True

    def stable_key(self, u):
        return "k"

    def bind_session(self, s, n):
        self.bound = (s, n)

    def archive(self, k, n):
        self.arch = (k, n)

    def exclude(self, k, save=False):
        self.excl = (k, save)

    def clear_session(self, s):
        pass


class FakeTimers:
    def list(self):
        return []


class FakeHandler:
    def __init__(self):
        self.prefix = None
        self.admin = None

    def set_prefix(self, p):
        self.prefix = p

    def set_admin_keys(self, k):
        self.admin = k


class FakeTTS:
    def __init__(self, *a, **k):
        self.args = a


def make(tmp_path, monkeypatch):
    monkeypatch.setattr("mumble_bot.controller.FishS2TTS", FakeTTS)
    cfg = load_config(tmp_path / "none.yaml")
    sp, orch, store, priv = FakeSpeaker(), FakeOrch(), FakeStore(), FakePrivacy()
    c = BotController(
        cfg, str(tmp_path / "config.yaml"), wake=WakeMatcher(cfg.behavior.wake_regex),
        speaker=sp, orchestrator=orch, store=store, privacy=priv,
        resolver=FakeResolver(), timers=FakeTimers(),
    )
    c.command_handler = FakeHandler()
    return c, sp, orch, store, priv


def test_editable_config_lists_fields(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    paths = [f["path"] for f in c.get_editable_config()]
    assert "fish.voice_id" in paths and "behavior.persona" in paths


def test_apply_voice_hot_rebuilds_tts(tmp_path, monkeypatch):
    c, sp, *_ = make(tmp_path, monkeypatch)
    res = c.apply_config({"fish.voice_id": "newid"})
    assert c.cfg.fish.voice_id == "newid"
    assert isinstance(sp.tts, FakeTTS)
    assert res["needs_restart"] == []


def test_apply_persona_and_window(tmp_path, monkeypatch):
    c, sp, orch, store, _ = make(tmp_path, monkeypatch)
    c.apply_config({"behavior.persona": "新人设", "behavior.window_sec": "123"})
    assert orch.persona == "新人设" and orch.window == 123 and store.win == 123


def test_apply_wake_swaps_matcher(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    old = c.wake
    c.apply_config({"behavior.wake_regex": "豆沙"})
    assert c.wake is not old
    ok, _ = c.wake.match("豆沙在吗")
    assert ok


def test_apply_prefix_and_proactive_threshold(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    c.apply_config({"behavior.command_prefix": ";", "behavior.cooldown_sec": "99"})
    assert c.command_handler.prefix == ";"
    assert c.cfg.behavior.cooldown_sec == 99   # proactive 读同一 cfg.behavior 实例


def test_apply_external_bots_in_place(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    d = c.cfg.external_bots
    c.apply_config({"external_bots": '{"music":{"commands":{"play":"!p {query}"}}}'})
    assert c.cfg.external_bots is d            # 原地改，skill ctx 持有的引用不变
    assert d["music"]["commands"]["play"] == "!p {query}"


def test_restart_fields_flagged(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    res = c.apply_config({"mumble.host": "h2", "dashscope.region": "intl"})
    assert set(res["needs_restart"]) == {"mumble.host", "dashscope.region"}
    assert c.cfg.mumble.host == "h2"


def test_persist_excludes_secrets(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    c.cfg.fish.api_key = "SECRET"
    c.apply_config({"fish.voice_id": "vid"})
    d = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert d["fish"]["voice_id"] == "vid"
    assert "api_key" not in d["fish"]


def test_on_utterance_wake_triggers_speak(tmp_path, monkeypatch):
    c, sp, *_ = make(tmp_path, monkeypatch)

    class U:
        text = "豆沙你好"

    c.on_utterance(U())
    assert sp.spoken


def test_snapshot_includes_username(tmp_path, monkeypatch):
    c, *_ = make(tmp_path, monkeypatch)
    assert c.snapshot_state()["username"] == "豆沙"


def test_test_speak_and_actions(tmp_path, monkeypatch):
    c, sp, _, _, priv = make(tmp_path, monkeypatch)
    assert c.test_speak("hi") and sp.spoken
    assert c.action("pause") and priv.is_paused()
    assert c.action("shutup", {"minutes": 3}) and priv.is_muted()
    assert c.action("unknown") is False
