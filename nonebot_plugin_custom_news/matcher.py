"""命令处理：今日热点 / 订阅热点 / 退订热点 / 热点帮助。"""

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
analysis_cmd = on_command(
    "热点解析", aliases={"新闻解析", "今日深读"}, priority=20, block=True
)
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


@today_cmd.handle()
async def handle_today(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    await matcher.send("正在为你收集全网热点，请稍候…")
    try:
        image, _digest = await generate_digest_image(store)
        await UniMessage.image(raw=image).send()
    except Exception as e:
        await matcher.finish(f"日报生成失败：{e}")
    await _try_follow_analysis(store, matcher)
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


def _llm_ready(store) -> bool:
    key = store.config.general.llm_api_key.strip()
    return bool(key)


async def _try_follow_analysis(store, matcher: Matcher) -> None:
    """日报发送后自动跟随深读图（失败静默，不影响日报）。"""
    if not store.config.general.llm_follow_digest or not _llm_ready(store):
        return
    try:
        from .service import generate_analysis_image

        image, _ = await generate_analysis_image(store)
        await UniMessage.image(raw=image).send()
    except Exception as e:
        from nonebot import logger

        logger.warning(f"深读跟随发送失败: {e!r}")


@analysis_cmd.handle()
async def handle_analysis(bot: Bot, event: Event, matcher: Matcher) -> None:
    store = get_store()
    if not _llm_ready(store):
        await matcher.finish(f"尚未配置大模型接口{_FOLLOW_HINT}")
    await matcher.send("正在抓取新闻原文并深度解读，约需半分钟…")
    try:
        from .service import generate_analysis_image

        image, analyses = await generate_analysis_image(store)
        await UniMessage.image(raw=image).send()
        ok = sum(1 for a in analyses if a.ok)
        await matcher.finish(f"📖 今日深读完成：成功解析 {ok}/{len(analyses)} 条新闻")
    except Exception as e:
        await matcher.finish(f"深读生成失败：{e}")


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
