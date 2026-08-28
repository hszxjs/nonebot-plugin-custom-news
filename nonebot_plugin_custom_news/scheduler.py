"""定时推送任务管理：按 config.schedules 动态注册/移除 APScheduler 任务。

深读联动：每个推送时段注册一个「提前 5 分钟」的预生成任务，
推送时刻直接发送已生成的深读图（失败回退为现场生成）。
"""

from datetime import date
from pathlib import Path

from nonebot import logger, require

require("nonebot_plugin_apscheduler")
scheduler = require("nonebot_plugin_apscheduler").scheduler

from .pusher import push_image_to_all
from .service import generate_digest_image
from .store import Store, get_store

_JOB_PREFIX = "custom_news_"
_PREGEN_PREFIX = "custom_news_pre_"
_PREGEN_LEAD_MINUTES = 5


def _pregen_file(store: Store, schedule_id: str) -> Path:
    return store.cache_dir / f"pregen_{schedule_id}_{date.today():%Y%m%d}.png"


def rebuild_jobs(store: Store | None = None) -> None:
    """按当前配置重建全部定时任务（配置变更后调用）。"""
    store = store or get_store()
    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            try:
                scheduler.remove_job(job.id)
            except Exception:
                pass

    for item in store.config.schedules:
        if not item.enabled:
            continue
        cron_days = ",".join(str(d) for d in item.weekdays) if item.weekdays else "*"
        scheduler.add_job(
            scheduled_push,
            trigger="cron",
            hour=item.hour,
            minute=item.minute,
            day_of_week=cron_days,
            id=f"{_JOB_PREFIX}{item.id}",
            replace_existing=True,
            timezone=store.config.general.timezone,
            args=[item.id],
        )
        # 预生成任务：推送时刻往前推 5 分钟（跨小时/跨日自动回绕）
        pre_total = (item.hour * 60 + item.minute - _PREGEN_LEAD_MINUTES) % (24 * 60)
        pre_h, pre_m = divmod(pre_total, 60)
        scheduler.add_job(
            pre_generate_analysis,
            trigger="cron",
            hour=pre_h,
            minute=pre_m,
            day_of_week=cron_days,
            id=f"{_PREGEN_PREFIX}{item.id}",
            replace_existing=True,
            timezone=store.config.general.timezone,
            args=[item.id],
        )
        logger.info(
            f"已注册定时推送 [{item.label}] "
            f"{item.hour:02d}:{item.minute:02d} weekdays={cron_days} "
            f"theme={item.theme_id or '默认'}（深读预生成 {pre_h:02d}:{pre_m:02d}）"
        )


async def pre_generate_analysis(schedule_id: str) -> None:
    """推送前 5 分钟预生成「今日深读」，落盘待推送任务取用。"""
    store = get_store()
    item = next(
        (s for s in store.config.schedules if s.id == schedule_id and s.enabled), None
    )
    if item is None:
        return
    if not store.config.general.llm_follow_digest or not store.config.general.llm_api_key.strip():
        return
    try:
        from .service import generate_analysis_image

        image, _ = await generate_analysis_image(store, theme_id=item.theme_id)
        # 清掉该时段旧文件后写入当日文件
        for old in store.cache_dir.glob(f"pregen_{schedule_id}_*.png"):
            old.unlink(missing_ok=True)
        _pregen_file(store, schedule_id).write_bytes(image)
        logger.info(f"[{item.label}] 深读预生成完成（{len(image) // 1024}KB）")
    except Exception as e:
        logger.warning(f"[{item.label}] 深读预生成失败（推送时将回退现场生成）: {e!r}")


async def scheduled_push(schedule_id: str) -> None:
    store = get_store()
    item = next(
        (s for s in store.config.schedules if s.id == schedule_id and s.enabled), None
    )
    if item is None:
        logger.warning(f"定时任务 {schedule_id} 已不存在或被禁用，跳过")
        return
    try:
        image, _ = await generate_digest_image(store, theme_id=item.theme_id)
        result = await push_image_to_all(store, image)
        logger.info(
            f"定时推送 [{item.label}] 完成: 成功 {result['ok']}/{result['total']}"
        )
        # 深读：优先发预生成图；无预生成（未开启/失败/过期）时现场生成兜底
        if store.config.general.llm_follow_digest and store.config.general.llm_api_key.strip():
            pregen = _pregen_file(store, schedule_id)
            try:
                if pregen.exists():
                    await push_image_to_all(store, pregen.read_bytes())
                    pregen.unlink(missing_ok=True)
                    logger.info(f"[{item.label}] 深读已随日报同步发送（预生成）")
                    return
                from .service import generate_analysis_image

                ana_img, _ = await generate_analysis_image(store, theme_id=item.theme_id)
                await push_image_to_all(store, ana_img)
            except Exception as e:
                logger.warning(f"[{item.label}] 深读发送失败: {e!r}")
    except Exception as e:
        logger.error(f"定时推送 [{item.label}] 失败: {e!r}")
