from mumble_bot.db import Database
from mumble_bot.identity import IdentityResolver


def U(session=1, name="raw", user_id=None, hash=None):
    return {"session": session, "name": name, "user_id": user_id, "hash": hash}


def test_stable_key_registered():
    assert IdentityResolver().stable_key(U(user_id=7)) == "reg:7"


def test_stable_key_guest_hash():
    assert IdentityResolver().stable_key(U(hash="abc123")) == "abc123"


def test_stable_key_guest_no_hash_falls_back_to_session():
    assert IdentityResolver().stable_key(U(session=9)) == "session:9"


def test_resolve_fallback_name():
    assert IdentityResolver().resolve(U(name="Alice")) == "Alice"


def test_resolve_session_bind():
    r = IdentityResolver()
    r.bind_session(5, "小明")
    assert r.resolve(U(session=5, name="raw")) == "小明"


def test_resolve_archive_takes_priority_over_name():
    r = IdentityResolver()
    r.archive("reg:7", "老王")
    assert r.resolve(U(session=2, name="raw", user_id=7)) == "老王"


def test_exclude_by_key_and_name():
    r = IdentityResolver()
    r.exclude("reg:7")
    assert r.resolve(U(user_id=7)) is None
    r.exclude("MusicBot")
    assert r.resolve(U(name="MusicBot")) is None


def test_include_cancels_exclude():
    r = IdentityResolver()
    r.exclude("x")
    r.include("x")
    assert not r.is_excluded("x")


def test_forget_name_removes_all_matching_archives():
    r = IdentityResolver()
    r.archive("reg:1", "A")
    r.archive("reg:2", "A")
    r.archive("reg:3", "B")
    assert r.forget_name("A") == 2
    assert r.resolve(U(user_id=1)) != "A"
    assert r.resolve(U(user_id=3)) == "B"


def test_is_admin():
    r = IdentityResolver()
    assert r.is_admin(U(user_id=7), ["reg:7"])
    assert r.is_admin(U(name="boss"), ["boss"])
    assert not r.is_admin(U(user_id=8, name="x"), ["reg:7"])


def test_persistence_roundtrip():
    db = Database(":memory:")
    r = IdentityResolver(db=db)
    r.archive("reg:7", "老王")
    r.exclude("MusicBot", save=True)

    r2 = IdentityResolver(db=db)  # 从同一 db 重新加载
    assert r2.resolve(U(user_id=7)) == "老王"
    assert r2.resolve(U(name="MusicBot")) is None


def test_exclude_without_save_is_not_persisted():
    db = Database(":memory:")
    r = IdentityResolver(db=db)
    r.exclude("temp")  # save=False
    r2 = IdentityResolver(db=db)
    assert not r2.is_excluded("temp")
