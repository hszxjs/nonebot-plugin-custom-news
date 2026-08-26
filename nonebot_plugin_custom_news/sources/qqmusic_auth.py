"""QQ音乐扫码登录（ptlogin2 协议）+ 手动 Cookie 导入。

流程：ptqrshow 取 qrsig → hash33(qrsig) 算 ptqrtoken → 轮询 ptqrlogin
→ 成功后跟随 check_sig 重定向换取音乐域 cookie（qm_keyst/uin）。
若遇风控滑块，提示改用手动 Cookie 导入。
"""

import base64
import io
import re
import time
from typing import Any

import httpx

_PT_APPID = 716027612  # QQ音乐 Web
_DAID = 384
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class QQMusicAuthError(Exception):
    pass


def hash33(qrsig: str) -> int:
    """ptqrtoken 计算（与 ptlogin2 JS 一致）。"""
    e = 0
    for ch in qrsig:
        e = (e << 5) - e + ord(ch)
        e &= 0x7FFFFFFF
    return e


async def qr_create() -> tuple[str, bytes]:
    """获取二维码图片。Returns: (qrsig, png_bytes)"""
    url = (
        "https://ssl.ptlogin2.qq.com/ptqrshow"
        f"?appid={_PT_APPID}&e=2&l=M&s=3&d=72&v=4&daid={_DAID}"
        "&pt_3rd_aid=0&t=" + str(int(time.time() * 1000))
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "User-Agent": _UA,
                "Referer": "https://y.qq.com/",
            },
            follow_redirects=False,
        )
    qrsig = ""
    for kv in resp.headers.get_list("set-cookie"):
        if kv.startswith("qrsig="):
            qrsig = kv.split(";", 1)[0]
    if not qrsig or len(resp.content) < 100:
        raise QQMusicAuthError("ptqrshow 未返回二维码（可能被风控拦截）")
    return qrsig, resp.content


async def qr_check(qrsig: str) -> dict[str, Any]:
    """轮询扫码状态。

    Returns: {code: waiting/scanned/expired/success/risk, cookie, nickname}
    """
    u1 = "https%3A%2F%2Fy.qq.com%2F"
    url = (
        "https://ssl.ptlogin2.qq.com/ptqrlogin"
        f"?u1={u1}&ptqrtoken={hash33(qrsig.split('=', 1)[1])}"
        "&ptredirect=0&h=1&t=1&g=1&from_ui=1&ptlang=2052"
        f"&action=0-0-{int(time.time() * 1000)}"
        f"&aid={_PT_APPID}&daid={_DAID}"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={"User-Agent": _UA, "Referer": "https://y.qq.com/", "Cookie": qrsig},
        )
    text = resp.text
    # 形如 ptuiCB('0','0','https://...check_sig...','0','登录成功!', '昵称');
    m = re.search(
        r"ptuiCB\(\s*'(-?\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
        r"(?:\s*,\s*'([^']*)')?",
        text,
    )
    if not m:
        raise QQMusicAuthError(f"ptqrlogin 响应异常: {text[:120]}")
    code, _mid, redirect, _flag, _msg, nickname = m.groups()

    mapping = {
        "0": "success",
        "65": "waiting",
        "66": "scanned",
        "67": "expired",
        "68": "expired",
    }
    state = mapping.get(code, "risk")
    out: dict[str, Any] = {"code": state, "cookie": "", "nickname": nickname or ""}
    if state == "success" and redirect:
        cookie = await _exchange(redirect, qrsig)
        out["cookie"] = cookie
        out["nickname"] = await _fetch_nickname(cookie)
    return out


async def _exchange(check_sig_url: str, qrsig: str) -> str:
    """跟随 check_sig 重定向链，收集音乐域 cookie（uin/qm_keyst 等）。"""
    captured: dict[str, str] = {}

    async def record(response: httpx.Response) -> None:
        for kv in response.headers.get_list("set-cookie"):
            one = kv.split(";", 1)[0]
            if "=" in one:
                k, v = one.split("=", 1)
                if v:
                    captured[k.strip()] = v.strip()

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": _UA, "Referer": "https://y.qq.com/"},
        cookies=_parse_cookie(qrsig),
        event_hooks={"response": [record]},
    ) as client:
        try:
            await client.get(check_sig_url)
            # 登录成功后访问一次 y.qq.com 首页触发音乐域 cookie 下发
            await client.get("https://y.qq.com/")
        except httpx.HTTPError:
            pass

    keep = {k: v for k, v in captured.items() if k in ("uin", "qm_keyst", "__q__a")}
    if "qm_keyst" not in keep:
        # 音乐域 cookie 未下发：可能被风控，或需要 musicu 交换
        raise QQMusicAuthError(
            "未能获取 qm_keyst（可能触发风控滑块），请改用手动导入 Cookie"
        )
    return "; ".join(f"{k}={v}" for k, v in keep.items())


async def _fetch_nickname(cookie: str) -> str:
    """从 musicu 登录态接口取昵称（失败不影响登录）。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                params={"g_tk": "5381", "format": "json", "inCharset": "utf8"},
                headers={
                    "User-Agent": _UA,
                    "Referer": "https://y.qq.com/",
                    "Cookie": cookie,
                },
                json={
                    "comm": {"t": 0},
                    "req": {
                        "module": "music.musicasset.SongBaseInfoRead",
                        "method": "get_user_baseinfo",
                        "param": {},
                    },
                },
            )
            data = resp.json()
            return str(
                ((data.get("req") or {}).get("data") or {}).get("nick") or ""
            )
    except Exception:
        return ""


def parse_imported_cookie(raw: str) -> str:
    """解析用户手动粘贴的 Cookie（支持 "k=v; k2=v2" 或每行一个）。"""
    raw = raw.replace("\n", ";")
    kept: list[str] = []
    for one in raw.split(";"):
        one = one.strip()
        if "=" in one:
            kept.append(one)
    return "; ".join(dict.fromkeys(kept))


def validate_qq_cookie(cookie: str) -> bool:
    return "qm_keyst" in cookie and "uin" in cookie


def _parse_cookie(cookie_str: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for one in cookie_str.split(";"):
        if "=" in one:
            k, v = one.strip().split("=", 1)
            out[k] = v
    return out


def qr_image_base64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()
