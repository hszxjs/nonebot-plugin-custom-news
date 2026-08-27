"""音乐账号登录与新歌榜预览 API（独立路由，挂载于 /custom-news/api）。"""

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nonebot import logger

from ..sources import netease_auth, qqmusic_auth
from ..store import MusicAccount, Store, get_store
from .auth import require_auth

router = APIRouter(prefix="/custom-news/api")

_VALID_PLATFORMS = ("netease", "qq")
_QR_SESSIONS: dict[str, dict] = {}  # platform -> {key, created}
_SMS_COOLDOWN: dict[str, float] = {}


class QrCreateReq(BaseModel):
    platform: str


class SmsSendReq(BaseModel):
    phone: str


class SmsVerifyReq(BaseModel):
    phone: str
    code: str


class ImportReq(BaseModel):
    platform: str
    cookie: str


class LogoutReq(BaseModel):
    platform: str


def _normalize_cookie(raw: str) -> str:
    raw = raw.replace("\n", ";")
    kept = []
    for one in raw.split(";"):
        one = one.strip()
        if "=" in one:
            kept.append(one)
    return "; ".join(dict.fromkeys(kept))


def _save_account(store: Store, platform: str, cookie: str, nickname: str) -> None:
    store.config.music_accounts[platform] = MusicAccount(
        cookie=cookie,
        nickname=nickname,
        logged_at=datetime.now().isoformat(timespec="seconds"),
    )
    store.save_sync()
    logger.info(f"音乐账号已保存: {platform} ({nickname or '未知昵称'})")


# ---------------------------------------------------------------- 账号状态


@router.get("/music/login/state")
async def music_login_state(store: Store = Depends(require_auth)) -> dict:
    out = {}
    for platform in _VALID_PLATFORMS:
        account = store.config.music_accounts.get(platform)
        if not account or not account.cookie:
            out[platform] = {"logged": False, "nickname": "", "cookie_preview": ""}
            continue
        preview = account.cookie[:14] + "…" if len(account.cookie) > 16 else account.cookie
        entry = {
            "logged": True,
            "nickname": account.nickname,
            "cookie_preview": preview,
            "logged_at": account.logged_at,
        }
        if platform == "netease":
            state = await netease_auth.account_state(account.cookie)
            entry["valid"] = state["ok"]
            if state["ok"] and not entry["nickname"]:
                entry["nickname"] = state["nickname"]
        else:
            entry["valid"] = qqmusic_auth.validate_qq_cookie(account.cookie)
        out[platform] = entry
    return {"accounts": out}


# ---------------------------------------------------------------- 扫码登录


@router.post("/music/login/qr/create")
async def music_qr_create(req: QrCreateReq, store: Store = Depends(require_auth)) -> dict:
    if req.platform == "netease":
        unikey, content, session = await netease_auth.qr_create()
        _QR_SESSIONS["netease"] = {
            "key": unikey,
            "cookie": session,
            "created": time.time(),
        }
        return {"qr_img": netease_auth.qr_image_base64(content)}
    if req.platform == "qq":
        try:
            qrsig, png = await qqmusic_auth.qr_create()
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"QQ 二维码获取失败（{e}）。若持续失败请改用手动导入 Cookie",
            )
        _QR_SESSIONS["qq"] = {"key": qrsig, "created": time.time()}
        return {"qr_img": qqmusic_auth.qr_image_base64(png)}
    raise HTTPException(status_code=400, detail="platform 必须是 netease 或 qq")


@router.get("/music/login/qr/status")
async def music_qr_status(platform: str, store: Store = Depends(require_auth)) -> dict:
    session = _QR_SESSIONS.get(platform)
    if not session or time.time() - session["created"] > 240:
        return {"code": "expired", "message": "二维码已过期，请重新生成"}
    try:
        if platform == "netease":
            r = await netease_auth.qr_check(session["key"], session.get("cookie", ""))
            raw = r.get("code")
            code = {
                800: "expired",
                801: "waiting",
                802: "scanned",
                803: "success",
                8821: "risk",
            }.get(raw, "error")
            message = {
                "waiting": "等待扫码",
                "scanned": "已扫码，请在手机上确认",
                "expired": "二维码已过期，请重新生成",
                "success": "登录成功",
                "risk": "扫码被风控拦截（需行为验证 8821）：请改用手机验证码登录，"
                "或在浏览器登录 music.163.com 后手动导入 Cookie",
            }.get(code, f"状态异常（接口 code={raw}），请重新生成二维码")
            if code == "success" and r.get("cookie"):
                _save_account(store, "netease", r["cookie"], r.get("nickname", ""))
        elif platform == "qq":
            r = await qqmusic_auth.qr_check(session["key"])
            code = r["code"]
            message = {
                "waiting": "等待扫码",
                "scanned": "已扫码，请在手机上确认",
                "expired": "二维码已过期，请重新生成",
                "success": "登录成功",
                "risk": "触发风控，请改用手动导入 Cookie",
            }.get(code, "状态异常")
            if code == "success" and r.get("cookie"):
                _save_account(store, "qq", r["cookie"], r.get("nickname", ""))
        else:
            raise HTTPException(status_code=400, detail="platform 非法")
        if code not in ("waiting", "scanned", "success"):
            logger.warning(f"网易云扫码轮询异常: raw={r}")
        return {"code": code, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        return {"code": "error", "message": f"轮询失败: {e}"}


# ---------------------------------------------------------------- 手机验证码（网易云）


@router.post("/music/login/sms/send")
async def music_sms_send(req: SmsSendReq, store: Store = Depends(require_auth)) -> dict:
    phone = req.phone.strip()
    if not phone.isdigit() or len(phone) != 11:
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    last = _SMS_COOLDOWN.get(phone, 0)
    if time.time() - last < 60:
        remain = int(60 - (time.time() - last)) + 1
        raise HTTPException(status_code=429, detail=f"发送太频繁，请 {remain} 秒后再试")
    try:
        await netease_auth.sms_send(phone)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    _SMS_COOLDOWN[phone] = time.time()
    return {"ok": True, "message": "验证码已发送"}


@router.post("/music/login/sms/verify")
async def music_sms_verify(req: SmsVerifyReq, store: Store = Depends(require_auth)) -> dict:
    try:
        r = await netease_auth.sms_login(req.phone.strip(), req.code.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not r.get("cookie"):
        raise HTTPException(status_code=502, detail="登录成功但未取到 cookie")
    _save_account(store, "netease", r["cookie"], r.get("nickname", ""))
    return {"ok": True, "nickname": r.get("nickname", "")}


# ---------------------------------------------------------------- 手动导入 / 退出


@router.post("/music/login/import")
async def music_login_import(req: ImportReq, store: Store = Depends(require_auth)) -> dict:
    if req.platform not in _VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail="platform 必须是 netease 或 qq")
    cookie = _normalize_cookie(req.cookie)
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie 内容为空")
    if req.platform == "qq":
        if not qqmusic_auth.validate_qq_cookie(cookie):
            raise HTTPException(status_code=400, detail="缺少关键字段（需要 uin 与 qm_keyst）")
        _save_account(store, "qq", cookie, "手动导入")
        return {"ok": True}
    if "MUSIC_U" not in cookie:
        raise HTTPException(status_code=400, detail="缺少关键字段 MUSIC_U")
    state = await netease_auth.account_state(cookie)
    _save_account(store, "netease", cookie, state.get("nickname") or "手动导入")
    return {"ok": True, "valid": state.get("ok", False)}


@router.post("/music/login/logout")
async def music_login_logout(req: LogoutReq, store: Store = Depends(require_auth)) -> dict:
    store.config.music_accounts.pop(req.platform, None)
    store.save_sync()
    return {"ok": True}


# ---------------------------------------------------------------- 新歌榜预览


@router.post("/music/preview")
async def music_preview(store: Store = Depends(require_auth)) -> dict:
    """新歌榜预览数据（WebUI 模拟聊天记录展示，取前 3 首示意）。"""
    from ..music_chat import PLATFORM_LABEL, _fmt_chart_text, _fmt_comments_text
    from ..sources.music_meta import get_platform_songs

    out = []
    for platform in _VALID_PLATFORMS:
        try:
            songs = await get_platform_songs(platform, store, limit=3)
            out.append(
                {
                    "platform": platform,
                    "label": PLATFORM_LABEL[platform],
                    "chart_text": _fmt_chart_text(platform, songs),
                    "songs": [
                        {
                            "song": s.song,
                            "artists": s.artists,
                            "album": s.album,
                            "cover": s.cover,
                            "audio": s.audio_url,
                            "jump": s.jump_url,
                            "comments_text": _fmt_comments_text(s),
                        }
                        for s in songs
                    ],
                }
            )
        except Exception as e:
            out.append(
                {"platform": platform, "label": PLATFORM_LABEL.get(platform, platform), "error": str(e)}
            )
    return {"platforms": out}
