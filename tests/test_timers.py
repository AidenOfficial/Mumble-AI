from mumble_bot.timers import TimerService


def test_pop_due_fires_in_time_order():
    now = [100.0]
    ts = TimerService(clock=lambda: now[0])
    fired = []
    ts.schedule(10, lambda: fired.append("a"))   # 110
    ts.schedule(5, lambda: fired.append("b"))    # 105
    assert ts._pop_due(104.0) == []
    for _t, cb, _l in ts._pop_due(106.0):
        cb()
    assert fired == ["b"]
    for _t, cb, _l in ts._pop_due(120.0):
        cb()
    assert fired == ["b", "a"]


def test_cancel_prevents_fire():
    now = [0.0]
    ts = TimerService(clock=lambda: now[0])
    fired = []
    tid = ts.schedule(5, lambda: fired.append("x"))
    ts.cancel(tid)
    for _t, cb, _l in ts._pop_due(10.0):
        cb()
    assert fired == []


def test_list_pending():
    ts = TimerService(clock=lambda: 0.0)
    ts.schedule(30, lambda: None, "番茄钟")
    lst = ts.list()
    assert len(lst) == 1
    remaining, _tid, label = lst[0]
    assert label == "番茄钟" and abs(remaining - 30) < 1e-6
