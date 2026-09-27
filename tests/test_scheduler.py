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
        assert f"custom_news_{item.id}" in ids
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
