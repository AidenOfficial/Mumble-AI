import ssl

import pytest

from mumble_bot._ssl_compat import install_ssl_wrap_socket_shim


@pytest.fixture
def without_wrap_socket():
    """模拟 Python 3.12：临时移除 ssl.wrap_socket，测完恢复，避免污染其他用例。"""
    had = hasattr(ssl, "wrap_socket")
    orig = getattr(ssl, "wrap_socket", None)
    if had:
        del ssl.wrap_socket
    try:
        yield
    finally:
        if had:
            ssl.wrap_socket = orig
        elif hasattr(ssl, "wrap_socket"):
            del ssl.wrap_socket


class FakeCtx:
    """记录 SSLContext 上的设置，免去真 socket。模拟 PROTOCOL_TLS_CLIENT 的默认（校验+查主机名）。"""
    last = None

    def __init__(self, protocol):
        FakeCtx.last = self
        self.protocol = protocol
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self.calls = []

    def load_default_certs(self):
        self.calls.append(("load_default_certs",))

    def load_verify_locations(self, path):
        self.calls.append(("load_verify_locations", path))

    def load_cert_chain(self, certfile, keyfile=None):
        self.calls.append(("load_cert_chain", certfile, keyfile))

    def set_ciphers(self, c):
        self.calls.append(("set_ciphers", c))

    def wrap_socket(self, sock, **kw):
        self.wrap_kw = kw
        return ("wrapped", sock)


def test_installs_when_missing_and_marks_itself(without_wrap_socket):
    assert install_ssl_wrap_socket_shim() is True
    assert callable(ssl.wrap_socket)
    assert getattr(ssl.wrap_socket, "_mumble_shim", False) is True


def test_leaves_native_wrap_socket_untouched():
    # <3.12 才有原生实现；本解释器(3.12+)无则跳过
    if not hasattr(ssl, "wrap_socket") or getattr(ssl.wrap_socket, "_mumble_shim", False):
        pytest.skip("本解释器无原生 ssl.wrap_socket（3.12+）")
    native = ssl.wrap_socket
    assert install_ssl_wrap_socket_shim() is False
    assert ssl.wrap_socket is native


def test_default_is_no_verify(without_wrap_socket, monkeypatch):
    install_ssl_wrap_socket_shim()                       # verify 默认 False
    monkeypatch.setattr(ssl, "SSLContext", FakeCtx)
    out = ssl.wrap_socket("SOCK", certfile=None, keyfile=None, ssl_version=ssl.PROTOCOL_TLS)
    ctx = FakeCtx.last
    assert out == ("wrapped", "SOCK")
    assert ctx.protocol == ssl.PROTOCOL_TLS_CLIENT
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE
    assert "server_hostname" not in ctx.wrap_kw          # 不校验就不传主机名


def test_verify_true_uses_system_ca_and_hostname(without_wrap_socket, monkeypatch):
    install_ssl_wrap_socket_shim(verify=True, server_hostname="mumble.example.com")
    monkeypatch.setattr(ssl, "SSLContext", FakeCtx)
    ssl.wrap_socket("SOCK", certfile=None, keyfile=None)
    ctx = FakeCtx.last
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ("load_default_certs",) in ctx.calls          # 无自带 CA → 系统 CA
    assert ctx.wrap_kw.get("server_hostname") == "mumble.example.com"


def test_verify_true_with_custom_ca(without_wrap_socket, monkeypatch):
    install_ssl_wrap_socket_shim(verify=True, ca_certs="/app/certs/ca.pem", server_hostname="h")
    monkeypatch.setattr(ssl, "SSLContext", FakeCtx)
    ssl.wrap_socket("SOCK")
    ctx = FakeCtx.last
    assert ("load_verify_locations", "/app/certs/ca.pem") in ctx.calls
    assert ("load_default_certs",) not in ctx.calls      # 给了自带 CA 就不用系统的


def test_loads_combined_pem_when_certfile_given(without_wrap_socket, monkeypatch):
    install_ssl_wrap_socket_shim()
    monkeypatch.setattr(ssl, "SSLContext", FakeCtx)
    ssl.wrap_socket("SOCK", certfile="/app/certs/bot.pem", keyfile=None)
    ctx = FakeCtx.last
    assert ("load_cert_chain", "/app/certs/bot.pem", None) in ctx.calls
