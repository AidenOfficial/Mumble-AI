from mumble_bot.skills.base import SkillContext
from mumble_bot.skills.music_skill import MusicControlSkill
from mumble_bot.skills.mute_ears_skill import MuteEarsSkill
from mumble_bot.skills.registry import SkillRegistry
from mumble_bot.skills.timer_skill import TimerSkill


class FakeTimers:
    def __init__(self):
        self.scheduled = []

    def schedule(self, delay, cb, label=""):
        self.scheduled.append((delay, cb, label))
        return len(self.scheduled)


class FakePrivacy:
    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def make_ctx(external_bots=None):
    spoken, sent = [], []
    timers, priv = FakeTimers(), FakePrivacy()
    ctx = SkillContext(
        speak=lambda sents, src="skill": spoken.append((list(sents), src)),
        send_channel=lambda t: sent.append(t),
        timers=timers, privacy=priv, store=None,
        external_bots=external_bots or {}, clock=lambda: 0.0,
    )
    return ctx, spoken, sent, timers, priv


def test_registry_specs_and_unknown():
    ctx, *_ = make_ctx()
    reg = SkillRegistry(ctx).register(TimerSkill())
    assert any(s["function"]["name"] == "set_timer" for s in reg.specs())
    assert "未知技能" in reg.dispatch("nope", "{}")


def test_timer_skill_schedules_and_fires():
    ctx, spoken, _, timers, _ = make_ctx()
    reg = SkillRegistry(ctx).register(TimerSkill())
    out = reg.dispatch("set_timer", '{"minutes":2,"label":"番茄钟结束"}')
    assert "2" in out and len(timers.scheduled) == 1
    delay, cb, _label = timers.scheduled[0]
    assert delay == 120.0
    cb()
    assert spoken and "番茄钟结束" in spoken[0][0][0]


def test_timer_skill_rejects_nonpositive():
    ctx, *_ = make_ctx()
    reg = SkillRegistry(ctx).register(TimerSkill())
    assert "大于" in reg.dispatch("set_timer", '{"minutes":0}')


def test_music_control_sends_formatted_command():
    bots = {"music": {"commands": {"play": "!play {query}", "skip": "!skip"}}}
    ctx, _, sent, _, _ = make_ctx(bots)
    reg = SkillRegistry(ctx).register(MusicControlSkill())
    reg.dispatch("music_control", '{"action":"play","query":"周杰伦 晴天"}')
    assert sent == ["!play 周杰伦 晴天"]
    reg.dispatch("music_control", '{"action":"skip"}')
    assert sent[-1] == "!skip"


def test_music_control_unknown_action():
    bots = {"music": {"commands": {"play": "!play {query}"}}}
    ctx, _, sent, _, _ = make_ctx(bots)
    reg = SkillRegistry(ctx).register(MusicControlSkill())
    out = reg.dispatch("music_control", '{"action":"volume","query":"50"}')
    assert "不支持" in out and sent == []


def test_music_control_no_config():
    ctx, _, sent, _, _ = make_ctx({})
    reg = SkillRegistry(ctx).register(MusicControlSkill())
    assert "还没配置" in reg.dispatch("music_control", '{"action":"play","query":"x"}')


def test_mute_ears_pauses_and_schedules_resume_and_remind():
    ctx, spoken, _, timers, priv = make_ctx()
    reg = SkillRegistry(ctx).register(MuteEarsSkill())
    reg.dispatch("mute_ears", '{"minutes":10}')
    assert priv.paused is True
    labels = [l for _d, _cb, l in timers.scheduled]
    assert "mute-remind" in labels and "mute-resume" in labels
    resume_cb = next(cb for _d, cb, l in timers.scheduled if l == "mute-resume")
    resume_cb()
    assert priv.paused is False
    assert any("恢复" in s[0][0] for s in spoken)


def test_mute_ears_short_no_remind():
    ctx, _, _, timers, _ = make_ctx()
    reg = SkillRegistry(ctx).register(MuteEarsSkill())
    reg.dispatch("mute_ears", '{"minutes":1}')   # 60s <= 90 → 只排 resume
    labels = [l for _d, _cb, l in timers.scheduled]
    assert "mute-resume" in labels and "mute-remind" not in labels
