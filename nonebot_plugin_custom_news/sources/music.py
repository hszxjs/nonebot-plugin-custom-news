"""新歌榜轻量抓取（日报卡片用）：只做字段投影，实现复用 music_meta。

历史上这里有一套独立实现：自己声明歌单 id / topid 并重写一遍解析，
与 music_meta（聊天记录走的富数据版）并存 —— 榜单 id 或接口字段一改就要改两处，
漏一处就是「一个入口正常、另一个空榜」。

现在端点、解析与缓存都只有 music_meta 一份，本模块只负责投影成 HotItem。
（两个接口都是官方公开接口，无需登录。）
"""

from __future__ import annotations

from pathlib import Path

from .dailyhot import HotItem
from .music_meta import netease_chart, qq_chart


class MusicSourceError(Exception):
    """新歌榜数据不可用。"""


def rows_to_items(rows: list[dict], limit: int) -> list[HotItem]:
    """把榜单行投影成日报卡片用的 HotItem（标题 = 歌名 - 歌手）。"""
    items: list[HotItem] = []
    for row in rows:
        name = " ".join(str(row.get("song") or "").split())
        if not name:
            continue
        artists = " ".join(str(row.get("artists") or "").split())
        title = f"{name} - {artists}" if artists else name
        items.append(HotItem(title=title, hot=None, url=row.get("jump_url") or None))
        if len(items) >= limit:
            break
    return items


async def fetch_netease_new(cache_dir: Path, limit: int = 10) -> list[HotItem]:
    """网易云新歌榜。"""
    rows = await netease_chart(cache_dir, limit=max(limit, 10))
    items = rows_to_items(rows, limit)
    if not items:
        raise MusicSourceError("网易云新歌榜解析为空")
    return items


async def fetch_qq_new(cache_dir: Path, limit: int = 10) -> list[HotItem]:
    """QQ音乐新歌榜。"""
    rows = await qq_chart(cache_dir, limit=max(limit, 10))
    items = rows_to_items(rows, limit)
    if not items:
        raise MusicSourceError("QQ音乐新歌榜解析为空")
    return items
