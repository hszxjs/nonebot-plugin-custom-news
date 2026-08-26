"""音乐榜单富数据：封面 / 热评 / 可播放链接（网易云 + QQ音乐），带 TTL 缓存。"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from nonebot import logger

from . import netease_auth, qqmusic_auth

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
CACHE_TTL = 30 * 60  # 榜单/评论/播放链接 30 分钟

NETEASE_NEW_LIST = 3779629
QQ_NEW_TOPLIST = 27


@dataclass
class SongComment:
    nick: str
    text: str
    likes: int


@dataclass
class SongMeta:
    platform: str  # netease / qq
    song: str
    artists: str
    album: str
    cover: str  # 图片 URL
    jump_url: str  # 歌曲页
    audio_url: str  # 可播放直链（探测降级后）
    song_ref: str  # netease: 歌曲id；qq: songmid
    comments: list[SongComment] = field(default_factory=list)


class MusicMetaError(Exception):
    pass


# ---------------------------------------------------------------- 工具


def _cache_dir(store_dir: Path) -> Path:
    d = store_dir / "music"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_cache(path: Path, ttl: int) -> Any | None:
    try:
        data = json.loads(path.read_text("utf-8"))
        if (datetime.now() - datetime.fromisoformat(data["ts"])).total_seconds() < ttl:
            return data["payload"]
    except Exception:
        pass
    return None


def _save_cache(path: Path, payload: Any) -> None:
    try:
        path.write_text(
            json.dumps(
                {"ts": datetime.now().isoformat(timespec="seconds"), "payload": payload},
                ensure_ascii=False,
            ),
            "utf-8",
        )
    except OSError:
        pass


def _clean_comment(text: str) -> str:
    text = re.sub(r"\[em\]e?\d+\[/em\]", "", text)  # QQ 表情码
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(text.split())


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------- 网易云


async def netease_chart(cache_dir: Path, cookie: str = "", limit: int = 10) -> list[dict]:
    """云音乐新歌榜（富字段），带缓存。"""
    path = _cache_dir(cache_dir) / "netease_chart.json"
    if (cached := _load_cache(path, CACHE_TTL)) is not None:
        return cached[:limit]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://music.163.com/api/playlist/detail",
                params={"id": NETEASE_NEW_LIST},
                headers={"User-Agent": _UA, "Referer": "https://music.163.com/"},
            )
            resp.raise_for_status()
            tracks = (resp.json().get("result") or {}).get("tracks") or []
    except Exception as e:
        raise MusicMetaError(f"网易云榜单获取失败: {e!r}") from e

    payload = []
    for t in tracks:
        album = t.get("album") or {}
        payload.append(
            {
                "song": str(t.get("name") or ""),
                "artists": "/".join(a.get("name", "") for a in t.get("artists") or []),
                "album": album.get("name", ""),
                "cover": album.get("picUrl", ""),
                "jump_url": f"https://music.163.com/song?id={t.get('id')}",
                "song_ref": str(t.get("id") or ""),
            }
        )
    if not payload:
        raise MusicMetaError("网易云新歌榜为空")
    _save_cache(path, payload)
    return payload[:limit]


async def netease_comments(song_id: str, cookie: str = "") -> list[SongComment]:
    """歌曲热评（免登录可用，带 cookie 更稳）。"""
    url = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}"
    headers = {"User-Agent": _UA, "Referer": "https://music.163.com/"}
    if cookie:
        headers["Cookie"] = cookie
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params={"limit": 20}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.debug(f"网易云评论获取失败 {song_id}: {e!r}")
        return []

    out = []
    for c in (data.get("hotComments") or []) + (data.get("comments") or []):
        text = _clean_comment(str(c.get("content") or ""))
        if len(text) < 2:
            continue
        out.append(
            SongComment(
                nick=_short(str((c.get("user") or {}).get("nickname") or "网友"), 12),
                text=text,
                likes=int(c.get("likedCount") or c.get("likeCount") or 0),
            )
        )
        if len(out) >= 3:
            break
    return out


async def netease_play_url(song_id: str, cookie: str = "") -> str:
    """可播放直链：outer url 探测（非 VIP 302 到真实 mp3），失败回退歌曲页。"""
    outer = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.head(
                outer, headers={"User-Agent": _UA, "Range": "bytes=0-1"}
            )
            if resp.status_code in (200, 206):
                return outer
            if resp.status_code in (301, 302, 303, 307):
                location = resp.headers.get("location", "")
                if location and "404" not in location:
                    return outer
    except Exception:
        pass
    return f"https://music.163.com/song?id={song_id}"


# ---------------------------------------------------------------- QQ音乐


def qq_cover_url(albummid: str) -> str:
    return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"


async def qq_chart(cache_dir: Path, limit: int = 10) -> list[dict]:
    """QQ音乐新歌榜（富字段），带缓存。"""
    path = _cache_dir(cache_dir) / "qq_chart.json"
    if (cached := _load_cache(path, CACHE_TTL)) is not None:
        return cached[:limit]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg",
                params={
                    "topid": QQ_NEW_TOPLIST,
                    "type": "top",
                    "song_begin": 0,
                    "song_num": 30,
                    "format": "json",
                },
                headers={"User-Agent": _UA, "Referer": "https://y.qq.com/"},
            )
            resp.raise_for_status()
            songlist = resp.json().get("songlist") or []
    except Exception as e:
        raise MusicMetaError(f"QQ音乐榜单获取失败: {e!r}") from e

    payload = []
    for entry in songlist:
        d = entry.get("data") or {}
        mid = d.get("songmid") or ""
        if not mid:
            continue
        payload.append(
            {
                "song": str(d.get("songname") or ""),
                "artists": "/".join(s.get("name", "") for s in d.get("singer") or []),
                "album": d.get("albumname", ""),
                "cover": qq_cover_url(d.get("albummid") or ""),
                "jump_url": f"https://y.qq.com/n/ryqq/songDetail/{mid}",
                "song_ref": mid,
                "songid": str(d.get("songid") or ""),
            }
        )
    if not payload:
        raise MusicMetaError("QQ音乐新歌榜为空")
    _save_cache(path, payload)
    return payload[:limit]


async def qq_comments(songid: str) -> list[SongComment]:
    """歌曲热评（cmd=9 热评优先，失败回退 cmd=8 最新），免登录。"""
    headers = {"User-Agent": _UA, "Referer": "https://y.qq.com/"}
    for cmd in (9, 8):
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(
                    "https://c.y.qq.com/base/fcgi-bin/fcg_global_comment_h5.fcg",
                    params={
                        "cid": 205360772,
                        "reqtype": 2,
                        "biztype": 1,
                        "topid": songid,
                        "cmd": cmd,
                        "needmusiccrit": 1,
                        "pagenum": 0,
                        "pagesize": 10,
                        "outjson": 1,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                commentlist = ((resp.json().get("comment") or {}).get("commentlist")) or []
        except Exception as e:
            logger.debug(f"QQ评论获取失败 cmd={cmd} {songid}: {e!r}")
            continue

        out = []
        for c in commentlist:
            text = _clean_comment(str(c.get("rootcommentcontent") or ""))
            nick = str(c.get("rootcommentnick") or "网友")
            if nick.startswith("@"):
                nick = nick[1:]
            if len(text) < 2:
                continue
            out.append(
                SongComment(
                    nick=_short(nick, 12), text=text, likes=int(c.get("praisenum") or 0)
                )
            )
            if len(out) >= 3:
                break
        if out:
            return out
    return []


async def qq_play_url(songmid: str, cookie: str = "") -> str:
    """登录态下取试听直链（vkey），失败回退歌曲页。"""
    if not cookie:
        return f"https://y.qq.com/n/ryqq/songDetail/{songmid}"
    try:
        guid = "1234567890"
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                params={"format": "json", "inCharset": "utf8"},
                headers={
                    "User-Agent": _UA,
                    "Referer": "https://y.qq.com/",
                    "Cookie": cookie,
                },
                json={
                    "comm": {"t": 0, "uin": "", "format": "json", "ct": 19, "cv": 0},
                    "req": {
                        "module": "vkey.GetVkeyServerBlock",
                        "method": "CgiGetVkey",
                        "param": {
                            "guid": guid,
                            "songmid": [songmid],
                            "songtype": [0],
                            "uin": "",
                            "loginflag": 1,
                            "platform": "20",
                        },
                    },
                },
            )
            data = resp.json()
            midurlinfo = ((data.get("req") or {}).get("data") or {}).get("midurlinfo") or []
            sip = (((data.get("req") or {}).get("data") or {}).get("sip") or [""])[0]
            purl = (midurlinfo[0] or {}).get("purl") if midurlinfo else ""
            if sip and purl:
                return sip + purl
    except Exception as e:
        logger.debug(f"QQ vkey 获取失败 {songmid}: {e!r}")
    return f"https://y.qq.com/n/ryqq/songDetail/{songmid}"


# ---------------------------------------------------------------- 统一入口


async def get_platform_songs(
    platform: str, store, limit: int = 10
) -> list[SongMeta]:
    """获取某平台新歌榜（含封面/热评/播放链接），全部降级保证卡片可用。"""
    accounts = getattr(store.config, "music_accounts", None)
    ne_cookie = (accounts.netease.cookie if accounts and accounts.netease else "") or ""
    qq_cookie = (accounts.qq.cookie if accounts and accounts.qq else "") or ""

    if platform == "netease":
        chart = await netease_chart(store.cache_dir, cookie=ne_cookie, limit=limit)
        songs: list[SongMeta] = []
        for row in chart[:limit]:
            songs.append(
                SongMeta(
                    platform="netease",
                    song=row["song"],
                    artists=row["artists"],
                    album=row["album"],
                    cover=row["cover"],
                    jump_url=row["jump_url"],
                    audio_url="",  # 后面统一探测
                    song_ref=row["song_ref"],
                    comments=await netease_comments(row["song_ref"], ne_cookie),
                )
            )
        # 播放链接逐首探测（outer url 失败自动回退歌曲页）
        for s in songs:
            s.audio_url = await netease_play_url(s.song_ref, ne_cookie)
        return songs

    if platform == "qq":
        chart = await qq_chart(store.cache_dir, limit=limit)
        songs = []
        for row in chart[:limit]:
            songs.append(
                SongMeta(
                    platform="qq",
                    song=row["song"],
                    artists=row["artists"],
                    album=row["album"],
                    cover=row["cover"],
                    jump_url=row["jump_url"],
                    audio_url="",
                    song_ref=row["song_ref"],
                    comments=await qq_comments(row.get("songid", "")),
                )
            )
        for s in songs:
            s.audio_url = await qq_play_url(s.song_ref, qq_cookie)
        return songs

    raise MusicMetaError(f"未知平台: {platform}")


def song_to_dict(s: SongMeta) -> dict:
    d = asdict(s)
    return d
