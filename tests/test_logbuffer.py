import logging

from mumble_bot.logbuffer import RingLogHandler


def _logger(name, h):
    lg = logging.getLogger(name)
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    return lg


def test_captures_levels_and_cursor():
    h = RingLogHandler(50)
    lg = _logger("t.ring1", h)
    lg.info("hello")
    lg.warning("careful")
    rows = h.get()
    assert [r["msg"] for r in rows] == ["hello", "careful"]
    assert rows[1]["level"] == "WARNING"
    after = rows[-1]["seq"]
    lg.error("boom")
    new = h.get(after=after)
    assert len(new) == 1 and new[0]["level"] == "ERROR" and new[0]["msg"] == "boom"


def test_capacity_caps():
    h = RingLogHandler(3)
    lg = _logger("t.ring2", h)
    for i in range(5):
        lg.info("m%d", i)
    assert [r["msg"] for r in h.get()] == ["m2", "m3", "m4"]


def test_exception_traceback_included():
    h = RingLogHandler()
    lg = _logger("t.ring3", h)
    try:
        raise ValueError("xx")
    except Exception:
        lg.exception("oops")
    msg = h.get()[-1]["msg"]
    assert "oops" in msg and "ValueError" in msg and "Traceback" in msg
