import pytest

pytest.importorskip("flask")

from mumble_bot.web.server import create_app


class FakeCtrl:
    def __init__(self):
        self.applied = None

    def snapshot_state(self):
        return {"connected": True, "users": [], "transcript": [], "timers": []}

    def get_editable_config(self):
        return [{"path": "fish.voice_id", "group": "音色", "label": "音色", "type": "str", "hot": True, "value": "v"}]

    def apply_config(self, patch):
        self.applied = patch
        return {"changed": list(patch), "needs_restart": [], "errors": {}}

    def test_speak(self, t):
        return bool(t)

    def action(self, name, data):
        return True

    def get_logs(self, after, limit):
        return [{"seq": 1, "level": "INFO", "logger": "x", "msg": "hi", "clock": "00:00:00"}]


def _client(password=""):
    return create_app(FakeCtrl(), password).test_client()


def test_index_served():
    r = _client().get("/")
    assert r.status_code == 200 and b"<html" in r.data.lower()


def test_state_and_config():
    cl = _client()
    assert cl.get("/api/state").get_json()["connected"] is True
    assert cl.get("/api/config").get_json()["groups"][0]["path"] == "fish.voice_id"


def test_post_config_calls_apply():
    r = _client().post("/api/config", json={"fish.voice_id": "abc"})
    assert r.get_json()["changed"] == ["fish.voice_id"]


def test_logs_route():
    r = _client().get("/api/logs?after=0")
    assert r.get_json()["lines"][0]["msg"] == "hi"


def test_test_speak_and_action():
    cl = _client()
    assert cl.post("/api/test_speak", json={"text": "hi"}).get_json()["ok"] is True
    assert cl.post("/api/action/pause", json={}).get_json()["ok"] is True


def test_auth_required_when_password_set():
    cl = _client("secret")
    assert cl.get("/api/state").status_code == 401
    assert cl.get("/api/needauth").get_json()["auth"] is True   # 探测端点放行
    assert cl.get("/api/state", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_no_auth_when_no_password():
    cl = _client("")
    assert cl.get("/api/state").status_code == 200
    assert cl.get("/api/needauth").get_json()["auth"] is False
