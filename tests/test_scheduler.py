"""调度与配置写入的回归测试（对应本次核查发现的「击杀开关」）。"""

from __future__ import annotations

from nonebot_plugin_custom_news import scheduler as sched_mod


def _job_ids() -> set[str]:
    return {j.id for j in sched_mod.scheduler.get_jobs()}


def test_rebuild_jobs_registers_two_jobs_per_schedule(store, aps_shim) -> None:
    sched_mod.rebuild_jobs(store)
    ids = _job_ids()
    enabled = [s for s in store.config.schedules if s.enabled]
    assert len(ids) == 2 * len(enabled)
    for item in enabled:
        assert f"custom_news_push_{item.id}" in ids
        assert f"custom_news_pre_{item.id}" in ids


def test_invalid_timezone_keeps_existing_jobs(store, aps_shim, monkeypatch) -> None:
    """非法时区不能再让全部定时任务消失（原先先全删再重建，异常中断 → 任务数 0）。"""
    sched_mod.rebuild_jobs(store)
    before = _job_ids()
    assert before

    # 绕过 pydantic 校验直接写内存值，模拟「配置被外部改坏」
    monkeypatch.setattr(store.config.general, "timezone", "Not/AZone", raising=False)
    sched_mod.rebuild_jobs(store)

    assert _job_ids() == before, "非法时区不应清空已注册任务"


def test_pregen_filename_follows_configured_timezone(store) -> None:
    """预生成文件名必须按调度时区取日期（进程时区为 UTC 时也要命得中）。"""
    import os
    import time
    from datetime import datetime
    from zoneinfo import ZoneInfo

    store.config.general.timezone = "Asia/Shanghai"
    name = sched_mod._pregen_file(store, "morning").name
    expected_day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    assert expected_day in name

    # 模拟进程时区为 UTC：日期口径仍应跟随配置时区
    os.environ["TZ"] = "UTC"
    time.tzset()
    try:
        assert datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d") in (
            sched_mod._pregen_file(store, "morning").name
        )
    finally:
        os.environ.pop("TZ", None)
        time.tzset()


def test_job_id_prefixes_do_not_collide(store, aps_shim) -> None:
    """id 以 pre_ 开头的时段不得覆盖别的时段的推送任务（job id 全局唯一）。"""
    from nonebot_plugin_custom_news.store import ScheduleItem

    store.config.schedules = [
        ScheduleItem(id="pre_a", hour=9, minute=0, label="甲"),
        ScheduleItem(id="a", hour=10, minute=0, label="乙"),
    ]
    sched_mod.rebuild_jobs(store)

    push_a = sched_mod.scheduler.get_job("custom_news_push_a")
    pre_pre_a = sched_mod.scheduler.get_job("custom_news_pre_pre_a")
    assert push_a is not None, "id='a' 的推送任务被 id='pre_a' 的预生成覆盖了"
    assert push_a.func is sched_mod.scheduled_push
    assert pre_pre_a is not None and pre_pre_a.func is sched_mod.pre_generate_analysis


def test_pregen_day_of_week_wraps_with_time(store, aps_shim) -> None:
    """00:00-00:04 的时段：预生成回绕到前一天，星期必须同步前移。

    否则预生成被注册到「推送日 23:5x」——比推送晚约 24 小时，永远命不中，
    每周白烧一次 LLM 深读。
    """
    from nonebot_plugin_custom_news.store import ScheduleItem

    store.config.schedules = [ScheduleItem(id="midnight", hour=0, minute=2, weekdays=[0])]
    sched_mod.rebuild_jobs(store)

    pre = sched_mod.scheduler.get_job("custom_news_pre_midnight")
    push = sched_mod.scheduler.get_job("custom_news_push_midnight")
    assert pre is not None and push is not None
    # 周一(0) 00:02 的预生成应在周日(6) 23:57
    assert "day_of_week='6'" in str(pre.trigger)
    assert "day_of_week='0'" in str(push.trigger)


def test_schedule_id_pattern_rejects_path_like_ids(store) -> None:
    import pytest

    from nonebot_plugin_custom_news.store import ScheduleItem

    with pytest.raises(ValueError):
        ScheduleItem(id="../../etc/passwd")
    with pytest.raises(ValueError):
        ScheduleItem(id="a b")
