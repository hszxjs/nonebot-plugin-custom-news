"""定时推送任务管理：按 config.schedules 动态注册/移除 APScheduler 任务。

深读联动：每个推送时段注册一个「提前 5 分钟」的预生成任务，
推送时刻直接发送已生成的深读图（失败回退为现场生成）。
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nonebot import logger, require

require("nonebot_plugin_apscheduler")
scheduler = require("nonebot_plugin_apscheduler").scheduler

from .pusher import push_image_to_all, push_text_to_all
from .service import generate_digest_image
from .store import Store, get_store

#: 清理用的统一前缀
_JOB_PREFIX = "custom_news_"
#: 两类任务用**互相不嵌套**的前缀：此前推送是 "custom_news_<id>"、预生成是
#: "custom_news_pre_<id>"，于是 id='pre_x' 的预生成会覆盖 id='x' 的推送任务
#: （jobs 按 id 全局唯一），该时段的日报就永远不推了
_PUSH_PREFIX = "custom_news_push_"
_PREGEN_PREFIX = "custom_news_pre_"
_PREGEN_LEAD_MINUTES = 5


def _today(store: Store) -> date:
    """按配置时区取「今天」。

    预生成文件名必须与调度时区同一口径：若进程时区是 UTC 而调度时区是 +08，
    06:00 的推送会去找前一日算出的文件名，预生成永远命不中（每次现场生成）。
    """
    try:
        tz = ZoneInfo(store.config.general.timezone)
    except Exception:
        return date.today()
    return datetime.now(tz).date()


def _pregen_file(store: Store, schedule_id: str) -> Path:
    return store.cache_dir / f"pregen_{schedule_id}_{_today(store):%Y%m%d}.png"


def rebuild_jobs(store: Store | None = None) -> None:
    """按当前配置重建全部定时任务（配置变更后调用）。

    本函数是「先全删再重建」，因此任何异常中断都会让全部定时任务消失且无声。
    时区先校验、单个时段单独兜底：坏配置只影响它自己，不拖垮其它时段。
    """
    store = store or get_store()
    tz = store.config.general.timezone
    try:
        ZoneInfo(tz)
    except Exception as e:
        logger.error(f"时区配置非法（{tz!r}），保留现有定时任务不重建: {e!r}")
        return

    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            try:
                scheduler.remove_job(job.id)
            except Exception as e:
                logger.warning(f"移除旧定时任务 {job.id} 失败: {e!r}")

    registered = 0
    for item in store.config.schedules:
        if not item.enabled:
            continue
        cron_days = ",".join(str(d) for d in item.weekdays) if item.weekdays else "*"
        # 预生成任务：推送时刻往前推 5 分钟，跨小时/跨日都要回绕
        raw = item.hour * 60 + item.minute - _PREGEN_LEAD_MINUTES
        pre_total = raw % (24 * 60)
        pre_h, pre_m = divmod(pre_total, 60)
        # 跨日回绕时星期也必须前移一天，否则 00:00-00:04 的时段会把预生成注册到
        # 「推送日 23:5x」——比推送晚约 24 小时，永远命不中，每周白烧一次 LLM
        pre_days = cron_days
        if raw < 0 and item.weekdays:
            pre_days = ",".join(str((d - 1) % 7) for d in item.weekdays)
        try:
            scheduler.add_job(
                scheduled_push,
                trigger="cron",
                hour=item.hour,
                minute=item.minute,
                day_of_week=cron_days,
                id=f"{_PUSH_PREFIX}{item.id}",
                replace_existing=True,
                timezone=tz,
                misfire_grace_time=300,
                coalesce=True,
                args=[item.id],
            )
            scheduler.add_job(
                pre_generate_analysis,
                trigger="cron",
                hour=pre_h,
                minute=pre_m,
                day_of_week=pre_days,
                id=f"{_PREGEN_PREFIX}{item.id}",
                replace_existing=True,
                timezone=tz,
                misfire_grace_time=300,
                coalesce=True,
                args=[item.id],
            )
        except Exception as e:
            logger.error(f"注册定时任务 [{item.label}] 失败，跳过该时段: {e!r}")
            continue
        registered += 1
        logger.info(
            f"已注册定时推送 [{item.label}] "
            f"{item.hour:02d}:{item.minute:02d} weekdays={cron_days} "
            f"theme={item.theme_id or '默认'}（深读预生成 {pre_h:02d}:{pre_m:02d}）"
        )
    if registered == 0:
        logger.warning("没有任何定时任务注册成功，请检查「推送管理」里的时段配置")


async def pre_generate_analysis(schedule_id: str) -> None:
    """推送前 5 分钟预生成「今日深读」，落盘待推送任务取用。"""
    store = get_store()
    item = next((s for s in store.config.schedules if s.id == schedule_id and s.enabled), None)
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
    item = next((s for s in store.config.schedules if s.id == schedule_id and s.enabled), None)
    if item is None:
        logger.warning(f"定时任务 {schedule_id} 已不存在或被禁用，跳过")
        return
    try:
        image, _ = await generate_digest_image(store, theme_id=item.theme_id)
        result = await push_image_to_all(store, image)
        logger.info(f"定时推送 [{item.label}] 完成: 成功 {result['ok']}/{result['total']}")
        # 深读：优先发预生成图；无预生成（未开启/失败/过期）时现场生成兜底；
        # 任何失败都向推送目标发文字提示，绝不能静默断更
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
                try:
                    await push_text_to_all(
                        store,
                        f"⚠️ 今日深读未能生成：{str(e)[:120]}\n"
                        "可在 WebUI「设置」页用「测试连接」排查 LLM 配置。",
                    )
                except Exception as notify_err:
                    logger.warning(f"[{item.label}] 深读失败提示也发送失败: {notify_err!r}")
    except Exception as e:
        logger.error(f"定时推送 [{item.label}] 失败: {e!r}")
        try:
            await push_text_to_all(
                store,
                "⚠️ 今日热点日报生成失败，详情见机器人日志。\n"
                "可在 WebUI「数据源」页查看各源抓取状态。",
            )
        except Exception as notify_err:
            logger.warning(f"[{item.label}] 日报失败提示也发送失败: {notify_err!r}")
