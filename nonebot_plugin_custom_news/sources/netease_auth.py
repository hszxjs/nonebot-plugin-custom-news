"""网易云音乐登录（纯 Python，无需外部服务）。

- weapi 加密：双重 AES-128-CBC + 教科书 RSA（协议参数与 NeteaseCloudMusicApi 一致）
- 扫码登录：unikey → 二维码 → 轮询（801等待/802已扫/803成功/800过期）
- 手机验证码：sms/captcha/sent → login/cellphone
- 已知坑：轮询只回带 MUSIC_U + __csrf，否则可能卡 802（NeteaseCloudMusicApi #1744）
"""

import base64
import io
import json
import secrets
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_PRESET_KEY = b"0CoJUm6Qyw8W8jud"
_IV = b"0102030405060708"
_RSA_MODULUS = int(
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf6952801"
    "04e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee25593257"
    "5cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece"
    "0462db0a22b8e7",
    16,
)
_RSA_EXP = 0x10001

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _pkcs7_pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def _aes_cbc(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def weapi(payload: dict[str, Any], csrf_token: str = "") -> dict[str, str]:
    """网易云 weapi 请求体加密。"""
    text = json.dumps({**payload, "csrf_token": csrf_token}, separators=(",", ":"))
    secret_key = "".join(secrets.choice(_BASE62) for _ in range(16)).encode()
    b64 = base64.b64encode(_aes_cbc(_PRESET_KEY, text.encode()))
    params = base64.b64encode(_aes_cbc(secret_key, b64)).decode()
    m = int.from_bytes(secret_key[::-1].rjust(128, b"\x00"), "big")
    enc_sec_key = format(pow(m, _RSA_EXP, _RSA_MODULUS), "0256x")
    return {"params": params, "encSecKey": enc_sec_key}


class NeteaseAuthError(Exception):
    pass


def _anon_cookies() -> str:
    rnd = secrets.token_hex(16)
    return f"__remember_me=true; NMTID={rnd}; _ntes_nuid={rnd}"


async def _weapi_post(url: str, payload: dict[str, Any], cookie: str = "") -> httpx.Response:
    csrf = ""
    for part in cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "__csrf":
            csrf = v
    headers = {
        "User-Agent": _UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://music.163.com/",
        "Cookie": cookie or _anon_cookies(),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.post(url, data=weapi(payload, csrf), headers=headers)


# ---------------------------------------------------------------- 扫码登录


async def qr_create() -> tuple[str, str, str]:
    """生成登录 key 与二维码内容。

    Returns: (unikey, qr_content, session_cookie)
    注意：unikey 与本次响应的会话 cookie 绑定，轮询必须携带同一 cookie，
    否则扫码确认后服务端无法匹配会话（表现为状态异常）。
    """
    resp = await _weapi_post(
        "https://music.163.com/weapi/login/qrcode/unikey", {"type": 3}
    )
    session_cookie = "; ".join(
        one.split(";")[0] for one in resp.headers.get_list("set-cookie")
    )
    try:
        data = resp.json()
    except Exception as e:
        raise NeteaseAuthError(f"unikey 响应异常: {resp.status_code}") from e
    unikey = data.get("unikey") or (data.get("data") or {}).get("unikey")
    if not unikey:
        raise NeteaseAuthError(f"unikey 未返回: {str(data)[:120]}")
    return unikey, f"https://music.163.com/login?codekey={unikey}", session_cookie


async def qr_check(unikey: str, session_cookie: str = "") -> dict[str, Any]:
    """轮询扫码状态（必须传 qr_create 返回的会话 cookie）。

    Returns: {code: 800过期/801等待/802已扫待确认/803成功, cookie, nickname}
    """
    resp = await _weapi_post(
        "https://music.163.com/weapi/login/qrcode/client/login",
        {"key": unikey, "type": 3},
        cookie=session_cookie,
    )
    try:
        data = resp.json()
    except Exception as e:
        raise NeteaseAuthError(f"轮询响应异常: {resp.status_code}") from e
    raw_code = data.get("code")
    if raw_code is None:
        raw_code = (data.get("data") or {}).get("code")
    try:
        code = int(raw_code or 0)
    except (TypeError, ValueError):
        code = 0
    out: dict[str, Any] = {"code": code, "cookie": "", "nickname": ""}
    if code == 803:
        # 只保留必要 cookie（MUSIC_U/__csrf），规避 802 卡死与响应头过大问题
        kept: list[str] = []
        for kv in data.get("cookie", "") or resp.headers.get_list("set-cookie") or []:
            for one in kv.split(";"):
                # data.cookie 形如 "k=v; k2=v2"，set-cookie 是单条
                name = one.strip().split("=", 1)[0]
                if name in ("MUSIC_U", "__csrf") and "=" in one:
                    kept.append(one.strip())
        out["cookie"] = "; ".join(kept)
        profile = data.get("profile") or {}
        out["nickname"] = profile.get("nickname", "")
    return out


# ---------------------------------------------------------------- 手机验证码


async def sms_send(phone: str, ctcode: str = "86") -> None:
    resp = await _weapi_post(
        "https://music.163.com/weapi/sms/captcha/sent",
        {"cellphone": phone.strip(), "ctcode": ctcode},
    )
    data = resp.json()
    if data.get("code") not in (200, 0) and data.get("data") is not True:
        raise NeteaseAuthError(f"验证码发送失败: {str(data)[:150]}")


async def sms_login(phone: str, captcha: str, ctcode: str = "86") -> dict[str, Any]:
    """验证码登录。Returns: {cookie, nickname}"""
    resp = await _weapi_post(
        "https://music.163.com/weapi/login/cellphone",
        {
            "phone": phone.strip(),
            "countrycode": ctcode,
            "captcha": captcha.strip(),
            "rememberLogin": "true",
        },
        cookie="os=pc; appver=2.10.5;",
    )
    data = resp.json()
    code = data.get("code")
    if code != 200:
        hint = {502: "验证码错误", 400: "参数/密码错误"}.get(code, f"code={code}")
        raise NeteaseAuthError(f"登录失败: {hint}")
    kept = []
    for kv in data.get("cookie", "") or resp.headers.get_list("set-cookie") or []:
        for one in kv.split(";"):
            name = one.strip().split("=", 1)[0]
            if name in ("MUSIC_U", "__csrf") and "=" in one:
                kept.append(one.strip())
    profile = data.get("profile") or {}
    return {"cookie": "; ".join(kept), "nickname": profile.get("nickname", "")}


# ---------------------------------------------------------------- 账号状态


async def account_state(cookie: str) -> dict[str, Any]:
    """校验登录态。Returns: {ok, nickname, user_id}"""
    resp = await _weapi_post(
        "https://music.163.com/weapi/w/nuser/account/get", {}, cookie=cookie
    )
    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "nickname": "", "user_id": 0}
    profile = data.get("profile") or {}
    return {
        "ok": data.get("code") == 200 and bool(profile),
        "nickname": profile.get("nickname", ""),
        "user_id": profile.get("userId", 0),
    }


def qr_image_base64(qr_content: str) -> str:
    """qrcode 库生成二维码 PNG（base64 data URI）。"""
    import qrcode

    img = qrcode.make(qr_content, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
