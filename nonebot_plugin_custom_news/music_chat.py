"""新歌榜 QQ 聊天记录：组装消息节点 → 合并转发发送（自动降级逐条）。

节点结构（每平台一条合并转发）：
  1. 文字版 Top N 榜单
  2. 每首歌：可播放音乐卡片（MusicShare/custom）+ 热评文字
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import logger

# 显式导入以注册 MusicShare 的跨适配器导出器
from nonebot_plugin_alconna.builtins.uniseg.music_share import (  # noqa: F401
    MusicShare,
    MusicShareKind,
)
from nonebot_plugin_alconna.uniseg import CustomNode, Reference, UniMessage

from .sources.music_meta import SongMeta, get_platform_songs
from .store import Store

PLATFORM_LABEL = {"netease": "网易云新歌榜", "qq": "QQ音乐新歌榜"}
_BOT_NAME = "热点日报酱"
_BOT_UID = "10000"


def _fmt_chart_text(platform: str, songs: list[SongMeta]) -> str:
    lines = [f"🎵 {PLATFORM_LABEL[platform]} · {datetime.now().strftime('%m月%d日')}", ""]
    for i, s in enumerate(songs, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lines.append(f"{medal} {s.song} - {s.artists}")
    lines.append("")
    lines.append("👇 每首歌的音乐卡片和热评在下面，点击卡片即可播放")
    return "\n".join(lines)


def _fmt_comments_text(s: SongMeta) -> str:
    if not s.comments:
        return f"💬《{s.song}》热评：评论区暂无声浪"
    lines = [f"💬《{s.song}》热评 Top{len(s.comments)}"]
    for c in s.comments:
        text = c.text if len(c.text) <= 80 else c.text[:79] + "…"
        lines.append(f"{c.nick}：{text}（👍{c.likes}）")
    return "\n".join(lines)


def _music_card(s: SongMeta) -> MusicShare:
    return MusicShare(
        kind=MusicShareKind.Custom,
        title=s.song,
        content=f"{s.artists} · {s.album}" if s.album else s.artists,
        url=s.jump_url,
        audio=s.audio_url,
        thumbnail=s.cover,
        summary="每日新歌",
    )


async def build_platform_chat(
    store: Store, platform: str, limit: int | None = None
) -> tuple[UniMessage, list[SongMeta]]:
    """组装一个平台的聊天记录消息。Returns: (UniMessage(Reference), songs)"""
    cfg = store.config.music_chat
    n = limit or cfg.count
    songs = await get_platform_songs(platform, store, limit=n)

    nodes: list[CustomNode] = [
        CustomNode(uid=_BOT_UID, name=_BOT_NAME, content=_fmt_chart_text(platform, songs))
    ]
    for s in songs:
        nodes.append(
            CustomNode(
                uid=_BOT_UID,
                name=_BOT_NAME,
                content=UniMessage(_music_card(s)),
            )
        )
        if cfg.comments:
            nodes.append(
                CustomNode(uid=_BOT_UID, name=_BOT_NAME, content=_fmt_comments_text(s))
            )
    return UniMessage(Reference(nodes=nodes)), songs


async def send_music_chats(
    store: Store,
    send_one,  # async Callable[[UniMessage], Awaitable[None]]
) -> dict:
    """生成并发送两个平台的聊天记录。

    Args:
        send_one: 发送单条消息的回调（matcher 上下文传 UniMessage.send；推送传 target.send）
    """
    cfg = store.config.music_chat
    result: dict = {"ok": 0, "fail": []}
    for platform in ("netease", "qq"):
        try:
            msg, songs = await build_platform_chat(store, platform)
            if cfg.forward:
                try:
                    await send_one(msg)
                except Exception as e:
                    # 合并转发失败 → 逐条降级
                    logger.warning(f"{platform} 合并转发失败，降级逐条: {e!r}")
                    await _send_flat(send_one, platform, songs)
            else:
                await _send_flat(send_one, platform, songs)
            result["ok"] += 1
            logger.info(f"{PLATFORM_LABEL[platform]}聊天记录已发送（{len(songs)} 首）")
        except Exception as e:
            result["fail"].append(PLATFORM_LABEL[platform])
            logger.error(f"{PLATFORM_LABEL[platform]}发送失败: {e!r}")
    return result


async def _send_flat(send_one, platform: str, songs: list[SongMeta]) -> None:
    """逐条降级发送。"""
    cfg = store.config.music_chat
    await send_one(UniMessage.text(_fmt_chart_text(platform, songs)))
    for s in songs:
        try:
            await send_one(UniMessage(_music_card(s)))
        except Exception as e:
            logger.warning(f"音乐卡片发送失败 {s.song}: {e!r}，降级文字")
            await send_one(
                UniMessage.text(f"🎵 {s.song} - {s.artists}\n{s.jump_url}")
            )
        if cfg.comments:
            await send_one(UniMessage.text(_fmt_comments_text(s)))
