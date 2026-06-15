"""Web 管理界面：Flask 守护线程 + JSON API。

只管 config.yaml 里的非密钥设置 + 运行时操作；密钥仍走 .env。可选 Bearer 密码鉴权。
werkzeug 简易服务器，homelab 量级够用。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)
_INDEX = Path(__file__).parent / "index.html"


def create_app(ctrl, password: str = ""):
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    def _auth_ok() -> bool:
        if not password:
            return True
        hdr = request.headers.get("Authorization", "")
        token = hdr[7:] if hdr.startswith("Bearer ") else request.headers.get("X-Auth", "")
        return token == password

    @app.before_request
    def _guard():
        if request.path == "/api/needauth":
            return None
        if request.path.startswith("/api/") and not _auth_ok():
            return jsonify({"error": "unauthorized"}), 401
        return None

    @app.get("/")
    def index():
        return app.response_class(_INDEX.read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/api/needauth")
    def needauth():
        return jsonify({"auth": bool(password)})

    @app.get("/api/state")
    def state():
        return jsonify(ctrl.snapshot_state())

    @app.get("/api/logs")
    def logs():
        after = request.args.get("after", 0, type=int)
        return jsonify({"lines": ctrl.get_logs(after, 600)})

    @app.get("/api/config")
    def get_config():
        return jsonify({"groups": ctrl.get_editable_config()})

    @app.post("/api/config")
    def post_config():
        patch = request.get_json(force=True, silent=True) or {}
        return jsonify(ctrl.apply_config(patch))

    @app.post("/api/test_speak")
    def test_speak():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": ctrl.test_speak(data.get("text", ""))})

    @app.post("/api/action/<name>")
    def action(name):
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": ctrl.action(name, data)})

    return app


def start_web(ctrl, cfg) -> None:
    web = cfg.web
    if not web.enabled:
        return
    try:
        app = create_app(ctrl, web.password)
    except Exception:
        log.exception("Web 界面启动失败（flask 未安装？）")
        return

    def run():
        try:
            from werkzeug.serving import make_server

            srv = make_server(web.host, web.port, app, threaded=True)
            log.info("Web 界面: http://%s:%s", web.host, web.port)
            srv.serve_forever()
        except Exception:
            log.exception("Web 服务器异常退出")

    threading.Thread(target=run, name="web", daemon=True).start()
