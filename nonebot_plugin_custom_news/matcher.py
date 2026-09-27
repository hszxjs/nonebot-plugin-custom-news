"""命令处理：今日热点 / 订阅热点 / 退订热点 / 热点帮助。"""

import time

from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher

from nonebot_plugin_alconna import UniMessage, get_target

from .pusher import add_target, remove_target
from .service import generate_digest_image
from .store import get_store

today_cmd = on_command(
    "今日热点",
    aliases={"今日热榜", "热点日报", "全网热点", "热点速递"},
    priority=20,
    block=True,
)
subscribe_cmd = on_command(
    "订阅热点", aliases={"热点订阅"}, priority=20, block=True
)
unsubscribe_cmd = on_command(
    "退订热点", aliases={"取消订阅热点", "热点退订"}, priority=20, block=True
)
help_cmd = on_command("热点帮助", aliases={"热点指令"}, priority=20, block=True)
music_cmd = on_command(
    "新歌榜", aliases={"音乐榜", "新歌速递"}, priority=20, block=True
)

_HELP_TEXT = (
    "📖 全网热点日报指令：\n"
    "· 今日热点 —— 立即生成今日全网热点日报图\n"
    "· 订阅热点 —— 将本会话加入定时推送列表\n"
    "· 退订热点 —— 取消本会话的定时推送\n"
    "· 热点帮助 —— 查看本帮助\n"
    "🎨 后台管理：浏览器打开 /custom-news/webui/ 可自定义主题、数据源与推送时间"
)

_FOLLOW_HINT = "（在 WebUI 设置页配置 LLM 接口后可用）"


#: 「今日热点」冷却：用户与群两个维度各自计时，避免连发打满内存
#: （单张渲染峰值可达 GB 级，另有全局渲染信号量兜底）
_COOLDOWN_SECONDS = 60
_last_trigger: dict[str, float] = {}


def _cooldown_keys(event: object) -> list[str]:
    keys: list[str] = []
    gid = getattr(event, "group_id", None)
    uid = getattr(event, "user_id", None)
    if gid is not None:
        keys.append(f"group:{gid}")
    if uid is not None:
        keys.append(f"user:{uid}")
    return keys


def cooldown_remaining(event: object, now: float | None = None) -> int:
    """还有多少秒才能再次触发（0 表示可触发）。纯函数，便于测试。"""
    now = time.time() if now is None else now
    waits = [
        _COOLDOWN_SECONDS - (now - _last_trigger.get(k, 0.0))
        for k in _cooldown_keys(event)
    ]
    remaining = max([w for w in waits if w > 0], default=0.0)
    return int(remaining)


def mark_triggered(event: object, now: float | None = None) -> None:
    now = time.time() if now is None else now
    for k in _cooldown_keys(event):
        _last_trigger[k] = now


@today_cmd.handle()
async def handle_today(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    wait = cooldown_remaining(event)
    if wait:
        await matcher.finish(f"刚给你发过啦，{wait} 秒后再试～")
    mark_triggered(event)
    await matcher.send("正在为你收集全网热点，请稍候…")
    try:
        image, _digest = await generate_digest_image(store)
        await UniMessage.image(raw=image).send()
    except Exception as e:
        logger.error(f"日报生成失败: {e!r}")
        await matcher.finish("日报生成失败，稍后再试（细节见机器人日志）")
    await matcher.finish()


@subscribe_cmd.handle()
async def handle_subscribe(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    target = get_target(event, bot)
    if target is None:
        await matcher.finish("当前平台/会话暂不支持订阅，可在 WebUI 中手动添加推送目标")
    added, label = await add_target(store, target)
    if added:
        await matcher.finish(f"✅ 订阅成功！「{label}」将在每个定时时段收到热点日报")
    await matcher.finish(f"本会话已在订阅列表中（已重新启用），无需重复订阅")


@unsubscribe_cmd.handle()
async def handle_unsubscribe(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    target = get_target(event, bot)
    if target is None:
        await matcher.finish("当前平台/会话无法识别订阅目标")
    removed, _label = await remove_target(store, target)
    if removed:
        await matcher.finish("已取消订阅，后续将不再收到定时热点日报")
    await matcher.finish("本会话不在订阅列表中")


@help_cmd.handle()
async def handle_help(matcher: Matcher) -> None:
    await matcher.finish(_HELP_TEXT)


@music_cmd.handle()
async def handle_music(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    await matcher.send("🎵 正在整理网易云/QQ音乐新歌榜（榜单、卡片、热评打包成聊天记录）…")

    from .music_chat import send_music_chats

    async def send_one(msg) -> None:
        await msg.send(fallback=True)

    result = await send_music_chats(store, send_one)
    if result["fail"]:
        await matcher.finish(f"部分榜单发送失败：{'、'.join(result['fail'])}")
    await matcher.finish("🎧 两张新歌榜聊天记录已送达，点击卡片即可播放")
