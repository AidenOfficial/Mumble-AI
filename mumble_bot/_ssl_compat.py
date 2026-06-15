"""Python 3.12 兼容 shim：补回被移除的 ssl.wrap_socket。

`ssl.wrap_socket()` 3.7 弃用、3.12 移除，而 pymumble 1.6.1（已停维）在 connect() 里仍调用它，
导致 Python 3.12 上一连接就 AttributeError。这里用现代 SSLContext 复刻该调用。

证书校验默认**关闭**（Mumble 用证书做身份/TOFU，服务器普遍自签，旧 wrap_socket 默认 cert_reqs=CERT_NONE
也是如此）。若你的 Mumble 服务器用 CA 签发的证书，可经 mumble.tls_verify=true 打开校验（可选自带 CA）。

纯 ssl，不依赖 pymumble，可在任意机器单测；须在 pymumble 真正建 socket（connect）之前调用。
"""

from __future__ import annotations

import ssl


def install_ssl_wrap_socket_shim(verify: bool = False, ca_certs: str | None = None,
                                 server_hostname: str | None = None) -> bool:
    """缺 ssl.wrap_socket（3.12+）时补一个等价实现。

    verify=False（默认）：不校验服务器证书 —— 与 pymumble 旧行为/官方 Mumble 客户端一致。
    verify=True：校验证书链（系统 CA，或 ca_certs 指定的 PEM）+ 主机名（若给了 server_hostname）。

    返回 True=本次安装/替换了 shim；False=已有**原生** wrap_socket（<3.12），不动它。
    """
    existing = getattr(ssl, "wrap_socket", None)
    if existing is not None and not getattr(existing, "_mumble_shim", False):
        return False  # <3.12 原生实现，保持不变

    # 捕获到独立名字，避免被内层 wrap_socket 的同名参数（ca_certs，旧 API 兼容位）遮蔽。
    _verify, _ca, _host = verify, ca_certs, server_hostname

    def wrap_socket(sock, keyfile=None, certfile=None, server_side=False,
                    cert_reqs=None, ssl_version=None, ca_certs=None,
                    do_handshake_on_connect=True, suppress_ragged_eofs=True, ciphers=None):
        # 忽略传入的 ssl_version（旧代码常塞 PROTOCOL_TLS/TLSv1）；用 PROTOCOL_TLS_CLIENT 自动协商最优版本。
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server_side else ssl.PROTOCOL_TLS_CLIENT)
        handshake_kw = {}
        if not server_side:
            if _verify:
                ctx.verify_mode = ssl.CERT_REQUIRED
                ctx.check_hostname = bool(_host)             # 没主机名就只校验链、不校验 hostname
                if _ca:
                    ctx.load_verify_locations(_ca)
                else:
                    ctx.load_default_certs()                 # 系统 CA（裸 SSLContext 不会自动加载）
                if _host:
                    handshake_kw["server_hostname"] = _host
            else:
                ctx.check_hostname = False                   # 必须先关，再设 CERT_NONE 才不报错
                ctx.verify_mode = ssl.CERT_NONE
        if certfile:
            ctx.load_cert_chain(certfile, keyfile or None)   # 合并 pem：私钥也在 certfile 里
        if ciphers:
            ctx.set_ciphers(ciphers)
        return ctx.wrap_socket(
            sock, server_side=server_side,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs, **handshake_kw,
        )

    wrap_socket._mumble_shim = True  # type: ignore[attr-defined]  # 标记“是我们的”，便于重配/识别
    ssl.wrap_socket = wrap_socket    # type: ignore[attr-defined]
    return True
