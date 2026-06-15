from mumble_bot.buffer import TranscriptStore, Utterance
from mumble_bot.db import Database


def U(id, t_end, text="x", user="A"):
    return Utterance(id=id, user=user, text=text, t_start=t_end, t_end=t_end)


def test_evict_outside_window():
    now = [100.0]
    store = TranscriptStore(window_sec=60, clock=lambda: now[0])
    store.append(U("1", t_end=10))
    now[0] = 100  # cutoff = 40，旧句应被淘汰
    store.append(U("2", t_end=95))
    assert [u.id for u in store.recent()] == ["2"]


def test_recent_subwindow_filter():
    now = [1000.0]
    store = TranscriptStore(window_sec=3600, clock=lambda: now[0])
    store.append(U("1", t_end=900))
    store.append(U("2", t_end=995))
    assert [u.id for u in store.recent(window_sec=10)] == ["2"]  # 仅 t_end>=990


def test_last():
    store = TranscriptStore(window_sec=3600, clock=lambda: 1000.0)
    assert store.last() is None
    store.append(U("1", t_end=900))
    store.append(U("2", t_end=950))
    assert store.last().id == "2"


def test_persist_and_recall():
    db = Database(":memory:")
    store = TranscriptStore(db=db, window_sec=3600, clock=lambda: 1000.0)
    store.append(Utterance("1", "A", "找到我", t_start=10, t_end=10))
    store.append(Utterance("2", "B", "别的话", t_start=20, t_end=20))
    res = store.recall(contains="找到")
    assert [u.id for u in res] == ["1"]


def test_reload_from_db():
    db = Database(":memory:")
    s1 = TranscriptStore(db=db, window_sec=3600, clock=lambda: 1000.0)
    s1.append(Utterance("1", "A", "持久", t_start=990, t_end=990))
    s2 = TranscriptStore(db=db, window_sec=3600, clock=lambda: 1000.0)
    assert [u.id for u in s2.recent()] == ["1"]
