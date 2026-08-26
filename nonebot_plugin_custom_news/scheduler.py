"""定时推送任务管理：按 config.schedules 动态注册/移除 APScheduler 任务。"""

from nonebot import logger, require

require("nonebot_plugin_apscheduler")
scheduler = require("nonebot_plugin_apscheduler").scheduler

from .pusher import push_image_to_all
from .service import generate_digest_image
from .store import Store, get_store

_JOB_PREFIX = "custom_news_"


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
        logger.info(
            f"已注册定时推送 [{item.label}] "
            f"{item.hour:02d}:{item.minute:02d} weekdays={cron_days} "
            f"theme={item.theme_id or '默认'}"
        )


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
        # 自动跟随「今日深读」
        if store.config.general.llm_follow_digest and store.config.general.llm_api_key.strip():
            try:
                from .service import generate_analysis_image

                ana_img, _ = await generate_analysis_image(store, theme_id=item.theme_id)
                await push_image_to_all(store, ana_img)
            except Exception as e:
                logger.warning(f"[{item.label}] 深读跟随失败: {e!r}")
    except Exception as e:
        logger.error(f"定时推送 [{item.label}] 失败: {e!r}")
