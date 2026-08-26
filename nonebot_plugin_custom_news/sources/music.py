"""音乐新歌榜：网易云音乐 + QQ音乐（公开接口，无需登录）。

- 网易云「云音乐新歌榜」：官方歌单 3779629，老版 playlist 接口
- QQ音乐「新歌榜」：fcg toplist 接口 topid=27
"""

import httpx

from nonebot import logger

from .dailyhot import HotItem

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

NETEASE_NEW_SONG_LIST = 3779629  # 云音乐新歌榜
QQ_NEW_SONG_TOPLIST = 27  # QQ音乐新歌榜


class MusicSourceError(Exception):
    pass


def _clean(text: str) -> str:
    return " ".join(text.split())


async def fetch_netease_new(limit: int = 10) -> list[HotItem]:
    """网易云新歌榜：标题 = 歌名 - 歌手。"""
    url = "https://music.163.com/api/playlist/detail"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                params={"id": NETEASE_NEW_SONG_LIST},
                headers={"User-Agent": _UA, "Referer": "https://music.163.com/"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        raise MusicSourceError(f"网易云接口请求失败: {e!r}") from e

    tracks = (payload.get("result") or {}).get("tracks") or []
    if not tracks:
        raise MusicSourceError("网易云接口未返回曲目")

    items: list[HotItem] = []
    for t in tracks:
        name = _clean(str(t.get("name") or ""))
        artists = "/".join(
            _clean(str(a.get("name") or "")) for a in (t.get("artists") or []) if a.get("name")
        )
        if not name:
            continue
        title = f"{name} - {artists}" if artists else name
        sid = t.get("id")
        link = f"https://music.163.com/song?id={sid}" if sid else None
        items.append(HotItem(title=title, hot=None, url=link))
        if len(items) >= limit:
            break
    if not items:
        raise MusicSourceError("网易云新歌榜解析为空")
    return items


async def fetch_qq_new(limit: int = 10) -> list[HotItem]:
    """QQ音乐新歌榜：标题 = 歌名 - 歌手。"""
    url = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                params={
                    "topid": QQ_NEW_SONG_TOPLIST,
                    "type": "top",
                    "song_begin": 0,
                    "song_num": max(limit, 30),
                    "format": "json",
                },
                headers={"User-Agent": _UA, "Referer": "https://y.qq.com/"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        raise MusicSourceError(f"QQ音乐接口请求失败: {e!r}") from e

    songlist = payload.get("songlist") or []
    if not songlist:
        raise MusicSourceError("QQ音乐接口未返回曲目")

    items: list[HotItem] = []
    for entry in songlist:
        d = entry.get("data") or {}
        name = _clean(str(d.get("songname") or ""))
        singers = "/".join(
            _clean(str(s.get("name") or "")) for s in (d.get("singer") or []) if s.get("name")
        )
        if not name:
            continue
        title = f"{name} - {singers}" if singers else name
        mid = d.get("songmid")
        link = f"https://y.qq.com/n/ryqq/songDetail/{mid}" if mid else None
        items.append(HotItem(title=title, hot=None, url=link))
        if len(items) >= limit:
            break
    if not items:
        raise MusicSourceError("QQ音乐新歌榜解析为空")
    return items
