from mumble_bot.commands import CommandHandler
from mumble_bot.identity import IdentityResolver
from mumble_bot.privacy import PrivacyState


class Reply:
    def __init__(self):
        self.msgs = []
        self.priv = []

    def __call__(self, text):
        self.msgs.append(text)


def setup(admin_keys=(), prefix="!"):
    r = IdentityResolver()
    p = PrivacyState()
    reply = Reply()
    users = [
        {"session": 10, "name": "raw1", "user_id": None, "hash": "h1"},
        {"session": 20, "name": "raw2", "user_id": 7, "hash": None},
    ]
    h = CommandHandler(
        resolver=r, privacy=p, admin_keys=list(admin_keys),
        list_users=lambda: users, reply=reply,
        reply_private=lambda u, t: reply.priv.append((u, t)),
        prefix=prefix,
    )
    return h, r, p, reply, users


def test_me_binds_session():
    h, r, _, _, users = setup()
    assert h.handle(users[0], "!me 小明")
    assert r.resolve(users[0]) == "小明"


def test_bind_requires_admin():
    h, r, _, reply, users = setup(admin_keys=[])
    assert h.handle(users[0], "!bind 1 老王")
    assert any("管理员" in m for m in reply.msgs)
    assert r.resolve(users[1]) == "raw2"  # 未改


def test_bind_admin_ok():
    h, r, _, _, users = setup(admin_keys=["h1"])  # users[0] 的稳定键是 h1
    assert h.handle(users[0], "!bind 1 老王")
    assert r.resolve(users[1]) == "老王"


def test_bind_save_archives():
    h, r, _, _, users = setup(admin_keys=["h1"])
    h.handle(users[0], "!bind 1 老王 --save")
    # 存档按稳定键 reg:7，换 session 仍生效
    assert r.resolve({"session": 999, "name": "x", "user_id": 7, "hash": None}) == "老王"


def test_exclude_by_name():
    h, r, _, _, users = setup(admin_keys=["h1"])
    h.handle(users[0], "!exclude MusicBot --save")
    assert r.is_excluded("MusicBot")


def test_exclude_by_index():
    h, r, _, _, users = setup(admin_keys=["h1"])
    h.handle(users[0], "!exclude 1")
    assert r.resolve(users[1]) is None


def test_who_lists_header():
    h, _, _, reply, users = setup()
    h.handle(users[0], "!who")
    assert reply.msgs and "序号" in reply.msgs[-1]


def test_whoami_private():
    h, _, _, reply, users = setup()
    h.handle(users[0], "!whoami")
    assert reply.priv and "h1" in reply.priv[-1][1]


def test_shutup_and_comeback():
    h, _, p, _, users = setup()
    h.handle(users[0], "!shutup 1")
    assert p.is_muted()
    h.handle(users[0], "!comeback")
    assert not p.is_muted()


def test_pause_requires_admin():
    h, _, p, _, users = setup(admin_keys=[])
    h.handle(users[0], "!pause")
    assert not p.is_paused()


def test_unknown_not_handled():
    h, _, _, _, users = setup()
    assert not h.handle(users[0], "!nope")
    assert not h.handle(users[0], "随便说点啥")


def test_comma_prefix_works():
    h, _, p, _, users = setup(prefix=",")
    assert h.handle(users[0], ",shutup 1")
    assert p.is_muted()


def test_music_bot_bang_commands_not_intercepted():
    # 点歌bot 的 ! 命令一律不被我们接管（避免 !pause/!help 双响应）
    h, _, p, _, users = setup(admin_keys=["h1"], prefix=",")
    for music_cmd in ("!pause", "!play 晴天", "!skip", "!help", "!stop"):
        assert h.handle(users[0], music_cmd) is False
    assert not p.is_paused()


def test_usage_strings_use_prefix_not_hardcoded_bang():
    # 用法提示要跟随实际前缀，别写死 ! —— 否则用户被告知去敲会被点歌bot抢走的命令
    h, _, _, reply, users = setup(prefix=",")
    h.handle(users[0], ",me")                       # 非管理员命令，无参 → 用法
    assert any(",me" in m for m in reply.msgs)
    assert not any("!me" in m for m in reply.msgs)
    h2, _, _, reply2, users2 = setup(admin_keys=["h1"], prefix=",")
    h2.handle(users2[0], ",bind")                   # 管理员命令，参数不足 → 用法
    assert any(",bind" in m for m in reply2.msgs)
    assert not any("!bind" in m for m in reply2.msgs)
