"""网易云音乐登录（纯 Python，无需外部服务）。

协议对齐 NeteaseCloudMusicApiEnhanced/api-enhanced（2025-09 登录修复版）：
- weapi：双重 AES-128-CBC + 教科书 RSA
- 匿名会话：尽力通过 xeapi 密钥交换 → /api/register/anonimous 换 MUSIC_A；
  该端点 2026-08 起对全新设备返回 400（增强 fork 同样失败），失败时回退为
  空 MUSIC_A + 完整客户端身份 cookie（os/appver/WNMCID/NMTID...）——
  fork 用户正是以该形态正常扫码；身份 cookie 残缺/随机伪造才会被风控拦截，
  表现为扫码确认后轮询返回 8821「需要行为验证码验证」
- 扫码：unikey(type=3) → 轮询 client/login(type=3)；803 只保留 MUSIC_U/__csrf
- 验证码：sms/captcha/sent 需 secrete=music_middleuser_pclogin；
  登录端点为 /weapi/w/login/cellphone（type/https/remember/secureCaptcha），
  旧端点 /weapi/login/cellphone 会报 10004「登录存在安全风险」
"""

import asyncio
import base64
import gzip
import hashlib
import hmac
import io
import json
import secrets
import time
import urllib.parse
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)

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

_UA_WEBAPI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
)
_UA_ANDROID = (
    "NeteaseMusic/9.5.61.260802021928(9005061);Dalvik/2.1.0 "
    "(Linux; U; Android 12; HBN-AL00 Build/cd737a2.0)"
)

# xeapi 常量（fork util/crypto.js）
_XEAPI_STATIC_KEY = bytes.fromhex(
    "ab1d5a430f6bb04a3f01e81ddd72bd916d5ce591248ac128714806d7f8fb1b84"
)
_XEAPI_SIGN_KEY = (
    "mUHCwVNWJbunMqAHf5MImuirT6plvs6VSFW62MGHstFQxhBGdEoIhLItH3djc4"
    "+FB/OKty3+lL2rGeoFBpVe5g=="
)
_EAPI_KEY = b"e82ckenh8dichen8"
_ID_XOR_KEY = "3go8&$8*3*3h0k(2)2"

_API_DOMAIN = "https://interface.music.163.com"
_XEAPI_DOMAIN = "https://interface3.music.163.com"


class NeteaseAuthError(Exception):
    pass


# ---------------------------------------------------------------- 基础加密


def _pkcs7_pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    n = data[-1]
    if not (1 <= n <= 16):
        return data
    return data[:-n]


def _aes_cbc(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _aes_ecb_enc(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _aes_ecb_dec(key: bytes, ciphertext: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return _pkcs7_unpad(decryptor.update(ciphertext) + decryptor.finalize())


def weapi(payload: dict[str, Any], csrf_token: str = "") -> dict[str, str]:
    """网易云 weapi 请求体加密。"""
    text = json.dumps({**payload, "csrf_token": csrf_token}, separators=(",", ":"))
    secret_key = "".join(secrets.choice(_BASE62) for _ in range(16)).encode()
    b64 = base64.b64encode(_aes_cbc(_PRESET_KEY, text.encode()))
    params = base64.b64encode(_aes_cbc(secret_key, b64)).decode()
    m = int.from_bytes(secret_key[::-1].rjust(128, b"\x00"), "big")
    enc_sec_key = format(pow(m, _RSA_EXP, _RSA_MODULUS), "0256x")
    return {"params": params, "encSecKey": enc_sec_key}


# ---------------------------------------------------------------- xeapi（匿名会话）


def _xeapi_sign(timestamp: str, nonce: str) -> str:
    digest = hmac.new(
        _XEAPI_SIGN_KEY.encode(), (timestamp + nonce).encode(), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def _cloudmusic_dll_encode_id(device_id: str) -> str:
    xored = "".join(
        chr(ord(ch) ^ ord(_ID_XOR_KEY[i % len(_ID_XOR_KEY)]))
        for i, ch in enumerate(device_id)
    )
    md5_raw = hashlib.md5(xored.encode()).digest()
    return base64.b64encode(md5_raw).decode()


def _encode_device_username(device_id: str) -> str:
    raw = f"{device_id} {_cloudmusic_dll_encode_id(device_id)}"
    return base64.b64encode(raw.encode()).decode()


async def _xeapi_fetch_public_key(device_id: str) -> dict[str, Any]:
    """gorilla 反爬密钥交换：换取服务端 X25519 公钥。"""
    nonce = "".join(secrets.choice("0123456789") for _ in range(16))
    timestamp = str(int(time.time() * 1000))
    data = {
        "appVersion": "9.5.61",
        "currentKeyVersion": "",
        "deviceId": device_id,
        "nonce": nonce,
        "os": "android",
        "requestType": "active",
        "signature": _xeapi_sign(timestamp, nonce),
        "t1": "",
        "t2": "",
        "timestamp": timestamp,
        "uid": "",
    }
    headers = {
        "User-Agent": _UA_ANDROID,
        "Cookie": f"deviceId={urllib.parse.quote(device_id)}",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_API_DOMAIN}/api/gorilla/anti/crawler/security/key/get",
            data=data,
            headers=headers,
        )
    try:
        payload = resp.json()
    except Exception as e:
        raise NeteaseAuthError(f"xeapi 密钥交换响应异常: {resp.status_code}") from e
    info = (payload.get("data") or {}) if payload.get("code") == 200 else {}
    encrypted = info.get("encryptedData") or ""
    if not encrypted:
        raise NeteaseAuthError(f"xeapi 公钥未返回: {str(payload)[:120]}")
    if info.get("signature") and info.get("timestamp"):
        expect = _xeapi_sign(str(info["timestamp"]), nonce)
        if expect != info["signature"]:
            raise NeteaseAuthError("xeapi 公钥响应签名不匹配")
    plain = _aes_ecb_dec(_XEAPI_STATIC_KEY, base64.b64decode(encrypted))
    key_state = json.loads(plain)
    if not key_state.get("sk"):
        raise NeteaseAuthError("xeapi 公钥响应缺少 sk")
    return key_state


def _xeapi_mid_transform(ciphertext: bytes) -> bytes:
    rand = secrets.token_bytes(16)
    xored = bytes(ciphertext[i] ^ rand[i & 0x0F] for i in range(len(ciphertext)))
    b64 = base64.b64encode(xored)
    rot = (rand[0] & 0x0F) % len(b64) if b64 else 0
    return rand + b64[rot:] + b64[:rot]


def _build_xeapi_plaintext(uri: str, data: dict[str, Any]) -> str:
    fields: dict[str, Any] = {}
    body = {k: v for k, v in data.items() if k != "e_r"}
    encoded = urllib.parse.urlencode(body)
    fields["body"] = base64.b64encode(encoded.encode()).decode()
    fields["queryString"] = "e_r=true"
    return json.dumps(fields, separators=(",", ":"))


def _xeapi_encrypt(
    uri: str, data: dict[str, Any], key_state: dict[str, Any]
) -> dict[str, str]:
    dynamic_key = secrets.token_bytes(16)
    plaintext = _build_xeapi_plaintext(uri, data).encode()

    mid = _xeapi_mid_transform(_aes_ecb_enc(_XEAPI_STATIC_KEY, plaintext))
    b = base64.b64encode(_aes_ecb_enc(dynamic_key, mid)).decode()

    peer = X25519PublicKey.from_public_bytes(base64.b64decode(key_state["publicKey"]))
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(peer)
    eph_pub = eph.public_key().public_bytes_raw()
    prk = hmac.new(b"\x00" * 32, shared, hashlib.sha256).digest()
    aes_key = hmac.new(prk, eph_pub + b"\x01", hashlib.sha256).digest()[:16]
    iv = secrets.token_bytes(12)
    s_plain = f"{base64.b64encode(dynamic_key).decode()}|android|{key_state.get('sk', '')}"
    ct = AESGCM(aes_key).encrypt(iv, s_plain.encode(), None)
    s = base64.b64encode(eph_pub + iv + ct).decode()

    r_plain = f"{key_state.get('version', '')}|"
    r = base64.b64encode(_aes_ecb_enc(_XEAPI_STATIC_KEY, r_plain.encode())).decode()
    return {"B": b, "S": s, "R": r}


def _xeapi_res_decrypt(body: bytes) -> dict[str, Any]:
    plain = _aes_ecb_dec(_EAPI_KEY, body)
    if plain[:2] == b"\x1f\x8b":
        plain = gzip.decompress(plain)
    return json.loads(plain)


# ---------------------------------------------------------------- 会话身份（进程级缓存）


_SESSION_LOCK = asyncio.Lock()
_ANON: dict[str, str] = {}


def _base_cookie() -> dict[str, str]:
    """进程级稳定身份 cookie（fork processCookieObject 的 pc 形态）。"""
    if "nuid" not in _ANON:
        # CryptoJS WordArray.random(32) → 32 字节 = 64 位 hex
        nuid = secrets.token_hex(32)
        now = str(int(time.time() * 1000))
        wn = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6))
        _ANON.update(
            {
                "nuid": nuid,
                "nnid": f"{nuid},{now}",
                "wnmcid": f"{wn}.{now}.01.0",
                "device_id": "".join(secrets.choice("0123456789ABCDEF") for _ in range(52)),
            }
        )
    cookie = {
        "__remember_me": "true",
        "ntes_kaola_ad": "1",
        "_ntes_nuid": _ANON["nuid"],
        "_ntes_nnid": _ANON["nnid"],
        "WNMCID": _ANON["wnmcid"],
        "WEVNSM": "1.0.0",
        "osver": "Microsoft-Windows-10-Professional-build-19045-64bit",
        "deviceId": _ANON["device_id"],
        "os": "pc",
        "channel": "netease",
        "appver": "3.1.17.204416",
        "NMTID": "00O" + secrets.token_hex(19),
    }
    if _ANON.get("music_a"):
        cookie["MUSIC_A"] = _ANON["music_a"]
    else:
        # fork 恒发送 MUSIC_A（可能为空串）
        cookie["MUSIC_A"] = ""
    return cookie


async def _ensure_anonymous() -> None:
    """xeapi 游客注册换 MUSIC_A（失败静默降级为纯身份 cookie）。"""
    if _ANON.get("music_a") or _ANON.get("anon_failed"):
        return
    async with _SESSION_LOCK:
        if _ANON.get("music_a") or _ANON.get("anon_failed"):
            return
        try:
            base = _base_cookie()
            device_id = base["deviceId"]
            key_state = await _xeapi_fetch_public_key(device_id)
            username = _encode_device_username(device_id)
            body = _xeapi_encrypt(
                "/api/register/anonimous", {"username": username}, key_state
            )
            headers = {
                "User-Agent": _UA_ANDROID,
                "X-Client-Enc-State": "ENCRYPTED",
                "x-aeapi": "true",
                "content-type": "application/x-www-form-urlencoded;charset=utf-8",
                "x-deviceid": device_id,
                "x-os": "android",
                "x-osver": "16",
                "x-appver": "9.1.65",
                "x-sdeviceid": device_id,
                "x-buildver": str(int(time.time())),
            }
            cookie = dict(base)
            cookie.update(
                {
                    "os": "android",
                    "osver": "16",
                    "appver": "9.1.65",
                    "buildver": str(int(time.time())),
                    "sDeviceId": device_id,
                }
            )
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookie.items())
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{_XEAPI_DOMAIN}/xeapi/register/anonimous",
                    data=body,
                    headers=headers,
                )
            data = _xeapi_res_decrypt(resp.content)
            music_a = ""
            for one in resp.headers.get_list("set-cookie"):
                kv = one.split(";")[0]
                if kv.startswith("MUSIC_A="):
                    music_a = kv.split("=", 1)[1]
            if data.get("code") == 200 and music_a:
                _ANON["music_a"] = music_a
            else:
                _ANON["anon_failed"] = "1"
        except Exception:
            _ANON["anon_failed"] = "1"


_JS_SAFE = "!*'()*-._~"


def _cookie_str(cookie: dict[str, str]) -> str:
    """按 encodeURIComponent 规则序列化（fork cookieObjToString）。"""
    return "; ".join(
        f"{urllib.parse.quote(k, safe=_JS_SAFE)}="
        f"{urllib.parse.quote(v, safe=_JS_SAFE)}"
        for k, v in cookie.items()
    )


def _merge_setcookie(cookie: dict[str, str], resp: httpx.Response) -> None:
    for one in resp.headers.get_list("set-cookie"):
        kv = one.split(";")[0]
        if "=" in kv:
            k, v = kv.split("=", 1)
            cookie[k.strip()] = v.strip()


async def _weapi_post(
    url: str,
    payload: dict[str, Any],
    session_cookie: str = "",
    include_anon: bool = True,
) -> httpx.Response:
    """weapi 请求：合并匿名身份 + 流程内 Set-Cookie 会话。"""
    await _ensure_anonymous()
    cookie = _base_cookie() if include_anon else {}
    for part in session_cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k and v:
            cookie[k] = v
    if cookie.get("MUSIC_U"):
        cookie.pop("MUSIC_A", None)
    csrf = cookie.get("__csrf", "")
    headers = {
        "User-Agent": _UA_WEBAPI,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://music.163.com/",
        "Cookie": _cookie_str(cookie),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.post(url, data=weapi({**payload, "e_r": False}, csrf), headers=headers)


# ---------------------------------------------------------------- 扫码登录


async def qr_create() -> tuple[str, str, str]:
    """生成登录 key 与二维码内容。

    Returns: (unikey, qr_content, session_cookie)
    unikey 与创建会话绑定，轮询必须回传同一 cookie（含匿名身份）。
    """
    resp = await _weapi_post(
        "https://music.163.com/weapi/login/qrcode/unikey", {"type": 3}
    )
    flow: dict[str, str] = {}
    _merge_setcookie(flow, resp)
    try:
        data = resp.json()
    except Exception as e:
        raise NeteaseAuthError(f"unikey 响应异常: {resp.status_code}") from e
    unikey = data.get("unikey") or (data.get("data") or {}).get("unikey")
    if not unikey:
        raise NeteaseAuthError(f"unikey 未返回: {str(data)[:120]}")
    return unikey, f"https://music.163.com/login?codekey={unikey}", _cookie_str(flow)


async def qr_check(unikey: str, session_cookie: str = "") -> dict[str, Any]:
    """轮询扫码状态（必须传 qr_create 返回的会话 cookie）。

    Returns: {code, cookie, nickname, message}
    code: 800过期/801等待/802已扫待确认/803成功/8821风控(需行为验证)
    """
    resp = await _weapi_post(
        "https://music.163.com/weapi/login/qrcode/client/login",
        {"key": unikey, "type": 3},
        session_cookie=session_cookie,
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
    out: dict[str, Any] = {
        "code": code,
        "cookie": "",
        "nickname": "",
        "message": data.get("message") or "",
    }
    if code == 803:
        merged: dict[str, str] = {}
        for kv in data.get("cookie", "") or resp.headers.get_list("set-cookie") or []:
            for one in kv.split(";"):
                name = one.strip().split("=", 1)[0]
                if name in ("MUSIC_U", "__csrf") and "=" in one:
                    merged[name] = one.strip().split("=", 1)[1]
        out["cookie"] = _cookie_str(merged)
        profile = data.get("profile") or {}
        out["nickname"] = profile.get("nickname", "")
    return out


# ---------------------------------------------------------------- 手机验证码


async def sms_send(phone: str, ctcode: str = "86") -> None:
    await _ensure_anonymous()
    resp = await _weapi_post(
        "https://music.163.com/weapi/sms/captcha/sent",
        {
            "cellphone": phone.strip(),
            "ctcode": ctcode,
            "secrete": "music_middleuser_pclogin",
        },
    )
    data = resp.json()
    if data.get("code") not in (200, 0):
        raise NeteaseAuthError(f"验证码发送失败: {str(data)[:150]}")


async def sms_login(phone: str, captcha: str, ctcode: str = "86") -> dict[str, Any]:
    """验证码登录。Returns: {cookie, nickname}"""
    await _ensure_anonymous()
    resp = await _weapi_post(
        "https://music.163.com/weapi/w/login/cellphone",
        {
            "type": "1",
            "https": "true",
            "phone": phone.strip(),
            "countrycode": ctcode,
            "captcha": captcha.strip(),
            "remember": "true",
            "secureCaptcha": "",
        },
    )
    data = resp.json()
    code = data.get("code")
    if code != 200:
        hints = {
            502: "验证码错误",
            400: "参数/密码错误",
            10004: "触发安全风控，请稍后再试或改用扫码/手动导入",
            8821: "需要行为验证，请改用扫码或手动导入",
        }
        hint = hints.get(code, f"code={code} {data.get('message', '')}")[:120]
        raise NeteaseAuthError(f"登录失败: {hint}")
    merged: dict[str, str] = {}
    for kv in data.get("cookie", "") or resp.headers.get_list("set-cookie") or []:
        for one in kv.split(";"):
            name = one.strip().split("=", 1)[0]
            if name in ("MUSIC_U", "__csrf") and "=" in one:
                merged[name] = one.strip().split("=", 1)[1]
    profile = data.get("profile") or {}
    return {"cookie": _cookie_str(merged), "nickname": profile.get("nickname", "")}


# ---------------------------------------------------------------- 账号状态


async def account_state(cookie: str) -> dict[str, Any]:
    """校验登录态。Returns: {ok, nickname, user_id}"""
    resp = await _weapi_post(
        "https://music.163.com/weapi/w/nuser/account/get",
        {},
        session_cookie=cookie,
        include_anon="MUSIC_U" not in cookie,
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
