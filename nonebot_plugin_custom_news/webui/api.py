"""WebUI REST API（挂载于 /custom-news/api）。"""

import asyncio
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from nonebot import logger

from ..fetcher import fetch_digest
from ..palette import extract_palette
from ..pusher import push_image_to_all
from ..renderer import (
    RenderError,
    latest_render,
    render_digest,
    resolve_background_async,
)
from ..service import generate_digest_image
from ..sources import BUILTIN_SOURCES, CATEGORY_LABELS
from ..store import (
    CustomSourceDef,
    GeneralSettings,
    PushTargetItem,
    ScheduleItem,
    SourceSetting,
    Store,
    get_store,
)
from ..theme import PRESET_BACKGROUNDS, PRESET_THEMES, BackgroundConfig, Theme
from .auth import change_password, issue_token, require_auth, verify_password

router = APIRouter(prefix="/custom-news/api")

_ASSETS_BG_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# ---------------------------------------------------------------- 模型


class LoginReq(BaseModel):
    username: str
    password: str


class PasswordReq(BaseModel):
    old_password: str
    new_password: str


class ConfigUpdate(BaseModel):
    general: GeneralSettings | None = None
    sources: dict[str, SourceSetting] | None = None
    custom_sources: list[CustomSourceDef] | None = None
    schedules: list[ScheduleItem] | None = None
    push_targets: list[PushTargetItem] | None = None
    active_theme_id: str | None = None


class RenderPreviewReq(BaseModel):
    theme: Theme | None = None
    theme_id: str | None = None
    force_refresh: bool = False


class PushNowReq(BaseModel):
    theme_id: str | None = None


class PaletteReq(BaseModel):
    background: BackgroundConfig


class AnalyzeReq(BaseModel):
    count: int | None = None
    theme_id: str | None = None


# ---------------------------------------------------------------- 认证


@router.post("/auth/login")
async def login(req: LoginReq) -> dict:
    store = get_store()
    if not verify_password(store, req.username, req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": issue_token(store, req.username), "username": req.username}


@router.get("/auth/me")
async def me(store: Store = Depends(require_auth)) -> dict:
    return {"username": store.config.webui.username}


@router.put("/auth/password")
async def update_password(req: PasswordReq, store: Store = Depends(require_auth)) -> dict:
    if not verify_password(store, store.config.webui.username, req.old_password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    try:
        change_password(store, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# ---------------------------------------------------------------- 配置


@router.get("/config")
async def get_config(store: Store = Depends(require_auth)) -> dict:
    return {
        "config": store.config.model_dump(),
        "builtin_sources": [
            {
                "id": s.id,
                "name": s.name,
                "route": s.route,
                "category": s.category,
                "category_label": CATEGORY_LABELS.get(s.category, s.category),
                "emoji": s.emoji,
            }
            for s in BUILTIN_SOURCES
        ],
        "category_labels": CATEGORY_LABELS,
        "preset_theme_ids": list(PRESET_THEMES.keys()),
    }


@router.put("/config")
async def update_config(req: ConfigUpdate, store: Store = Depends(require_auth)) -> dict:
    cfg = store.config
    if req.general is not None:
        cfg.general = req.general
    if req.sources is not None:
        cfg.sources = req.sources
    if req.custom_sources is not None:
        cfg.custom_sources = req.custom_sources
    if req.schedules is not None:
        cfg.schedules = req.schedules
    if req.push_targets is not None:
        cfg.push_targets = req.push_targets
    if req.active_theme_id is not None:
        if req.active_theme_id not in cfg.themes:
            raise HTTPException(status_code=400, detail="激活主题不存在")
        cfg.active_theme_id = req.active_theme_id
    await store.save()

    from ..scheduler import rebuild_jobs  # 局部导入避免循环

    rebuild_jobs(store)
    return {"ok": True}


# ---------------------------------------------------------------- 主题


@router.get("/themes")
async def list_themes(store: Store = Depends(require_auth)) -> dict:
    return {
        "themes": [
            {
                "id": t.id,
                "name": t.name,
                "preset": t.id in PRESET_THEMES,
                "active": t.id == store.config.active_theme_id,
            }
            for t in store.config.themes.values()
        ],
        "active_theme_id": store.config.active_theme_id,
    }


@router.get("/themes/{theme_id}")
async def get_theme(theme_id: str, store: Store = Depends(require_auth)) -> dict:
    theme = store.config.themes.get(theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="主题不存在")
    return theme.model_dump()


@router.put("/themes/{theme_id}")
async def upsert_theme(
    theme_id: str, theme: Theme, store: Store = Depends(require_auth)
) -> dict:
    if theme.id != theme_id:
        raise HTTPException(status_code=400, detail="主题 id 不一致")
    store.config.themes[theme_id] = theme
    await store.save()
    return {"ok": True}


@router.delete("/themes/{theme_id}")
async def delete_theme(theme_id: str, store: Store = Depends(require_auth)) -> dict:
    if theme_id in PRESET_THEMES:
        raise HTTPException(status_code=400, detail="预设主题不可删除")
    if theme_id == store.config.active_theme_id:
        raise HTTPException(status_code=400, detail="不能删除当前激活主题")
    if theme_id not in store.config.themes:
        raise HTTPException(status_code=404, detail="主题不存在")
    del store.config.themes[theme_id]
    await store.save()
    return {"ok": True}


@router.post("/themes/{theme_id}/activate")
async def activate_theme(theme_id: str, store: Store = Depends(require_auth)) -> dict:
    if theme_id not in store.config.themes:
        raise HTTPException(status_code=404, detail="主题不存在")
    store.config.active_theme_id = theme_id
    await store.save()
    return {"ok": True}


@router.post("/themes/{theme_id}/duplicate")
async def duplicate_theme(theme_id: str, store: Store = Depends(require_auth)) -> dict:
    src = store.config.themes.get(theme_id)
    if src is None:
        raise HTTPException(status_code=404, detail="主题不存在")
    new_id = f"{src.id}_copy{uuid.uuid4().hex[:4]}"
    copy = src.model_copy(deep=True)
    copy.id = new_id
    copy.name = f"{src.name} 副本"
    store.config.themes[new_id] = copy
    await store.save()
    return {"ok": True, "id": new_id}


# ---------------------------------------------------------------- 背景图


@router.get("/backgrounds")
async def list_backgrounds(store: Store = Depends(require_auth)) -> dict:
    preset = [
        {"id": b["id"], "name": b["name"], "url": f"/custom-news/api/backgrounds/preset/{b['id']}"}
        for b in PRESET_BACKGROUNDS
    ]
    uploaded = []
    for p in store.backgrounds_dir.iterdir():
        if p.is_file() and p.suffix.lower() in _ALLOWED_EXT:
            uploaded.append(
                {"name": p.name, "url": f"/custom-news/api/backgrounds/file/{p.name}"}
            )
    return {"preset": preset, "uploaded": uploaded}


@router.get("/backgrounds/preset/{bg_id}")
async def get_preset_background(bg_id: str) -> FileResponse:
    if not all(c.isalnum() or c in "-_" for c in bg_id):
        raise HTTPException(status_code=400, detail="非法 id")
    path = _ASSETS_BG_DIR / f"{bg_id}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="背景图不存在")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/backgrounds/file/{filename}")
async def get_uploaded_background(filename: str) -> FileResponse:
    # 与预设背景端点一致免鉴权：图片经 <img>/CSS url() 加载无法携带 token，
    # 鉴权会导致主题工坊预览里自定义背景 401 不显示
    from ..store import get_store

    store = get_store()
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = store.backgrounds_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)


@router.post("/upload/background")
async def upload_background(
    file: UploadFile = File(...), store: Store = Depends(require_auth)
) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"仅支持 {'/'.join(_ALLOWED_EXT)} 格式")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 20MB")
    # 预缩放：超大背景图会让渲染产物膨胀（46MB PNG 实测拖垮 NapCat WS），
    # 宽超 2560px 一律缩到 2560 并转 JPEG
    try:
        import io as _io

        from PIL import Image

        im = Image.open(_io.BytesIO(data))
        if im.width > 2560:
            h = int(im.height * 2560 / im.width)
            im = im.convert("RGB").resize((2560, h), Image.LANCZOS)
            out = _io.BytesIO()
            im.save(out, "JPEG", quality=90, optimize=True)
            data = out.getvalue()
            ext = ".jpg"
    except Exception:
        pass
    name = f"bg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    (store.backgrounds_dir / name).write_bytes(data)
    return {"ok": True, "filename": name, "url": f"/custom-news/api/backgrounds/file/{name}"}


@router.post("/palette/extract")
async def palette_extract(req: PaletteReq, store: Store = Depends(require_auth)) -> dict:
    try:
        bg_path = await resolve_background_async(store, _theme_with_bg(req.background))
    except RenderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    colors = extract_palette(
        bg_path,
        overlay_mode=req.background.overlay_mode,
        overlay_opacity=req.background.overlay,
    )
    return {"colors": colors.model_dump()}


def _theme_with_bg(bg: BackgroundConfig) -> Theme:
    theme = Theme(id="__tmp__", name="tmp")
    theme.background = bg
    return theme


# ---------------------------------------------------------------- 渲染与推送


@router.post("/render/preview")
async def render_preview(req: RenderPreviewReq, store: Store = Depends(require_auth)) -> dict:
    theme = req.theme or store.theme_by_id(req.theme_id)
    try:
        digest = await fetch_digest(store, force_refresh=req.force_refresh)
        if not digest.cards:
            raise HTTPException(status_code=502, detail="没有可用数据，请先在数据源页启用并刷新")
        image = await render_digest(store, theme, digest)
    except HTTPException:
        raise
    except RenderError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"预览渲染失败: {e!r}")
        raise HTTPException(status_code=500, detail=f"渲染失败: {e!r}")
    return {
        "image": base64.b64encode(image).decode(),
        "cards": [
            {"name": c.name, "emoji": c.emoji, "count": len(c.items), "stale": c.stale}
            for c in digest.cards
        ],
        "failed": digest.failed,
    }


@router.post("/push/now")
async def push_now(req: PushNowReq, store: Store = Depends(require_auth)) -> dict:
    if not [t for t in store.config.push_targets if t.enabled]:
        raise HTTPException(status_code=400, detail="没有启用的推送目标")

    async def _job() -> None:
        try:
            image, _ = await generate_digest_image(store, theme_id=req.theme_id)
            result = await push_image_to_all(store, image)
            logger.info(f"手动推送完成: {result['ok']}/{result['total']}")
        except Exception as e:
            logger.error(f"手动推送失败: {e!r}")

    asyncio.create_task(_job())
    return {"ok": True, "message": "推送任务已开始，请查看机器人日志确认结果"}


@router.get("/data/latest")
async def get_latest(store: Store = Depends(require_auth)) -> dict:
    data = latest_render(store)
    if data is None:
        raise HTTPException(status_code=404, detail="还没有渲染记录")
    return {"image": base64.b64encode(data).decode()}


@router.get("/digest/cards")
async def get_digest_cards(store: Store = Depends(require_auth)) -> dict:
    digest = await fetch_digest(store)
    return {
        "cards": [
            {
                "source_id": c.source_id,
                "name": c.name,
                "emoji": c.emoji,
                "category": c.category,
                "stale": c.stale,
                "items": [
                    {"rank": i + 1, "title": it.title, "hot": it.hot}
                    for i, it in enumerate(c.items)
                ],
            }
            for c in digest.cards
        ],
        "failed": digest.failed,
        "generated_at": digest.generated_at.isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- 数据源状态


@router.get("/sources/status")
async def sources_status(store: Store = Depends(require_auth)) -> dict:
    import json

    status: dict[str, Any] = {}
    p = store.cache_dir / "fetch_status.json"
    if p.exists():
        try:
            status = json.loads(p.read_text("utf-8"))
        except Exception:
            status = {}
    # 只返回当前仍存在于配置中的源，历史残留（已删除的自定义源等）不展示
    known = set(store.config.sources.keys()) | {c.id for c in store.config.custom_sources}
    status = {k: v for k, v in status.items() if k in known}
    return {
        "status": status,
        "dailyhot_api_url": store.config.general.dailyhot_api_url,
    }


@router.post("/sources/refresh")
async def sources_refresh(store: Store = Depends(require_auth)) -> dict:
    digest = await fetch_digest(store, force_refresh=True)
    return {
        "ok": len(digest.cards) > 0,
        "cards": [
            {"name": c.name, "count": len(c.items), "stale": c.stale}
            for c in digest.cards
        ],
        "failed": digest.failed,
    }


@router.post("/llm/test")
async def llm_test(store: Store = Depends(require_auth)) -> dict:
    """用当前 LLM 配置发一条最小请求，验证端点/Key/模型可用性。"""
    from ..analyzer import _chat, _chat_completions_url

    g = store.config.general
    if not g.llm_api_key.strip():
        raise HTTPException(status_code=400, detail="尚未配置 API Key")
    try:
        reply = await _chat(g, "回复两个字：正常")
    except Exception as e:
        return {"ok": False, "url": _chat_completions_url(g.llm_base_url),
                "model": g.llm_model, "error": str(e)[:300]}
    return {"ok": True, "url": _chat_completions_url(g.llm_base_url),
            "model": g.llm_model, "reply": (reply or "")[:60]}


@router.post("/llm/analyze")
async def llm_analyze(req: AnalyzeReq, store: Store = Depends(require_auth)) -> dict:
    """生成「今日深读」解析图（未配置 key 时给出友好提示）。"""
    key = store.config.general.llm_api_key.strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="尚未配置 LLM 接口：请在「设置」页填写 OpenAI 兼容的 "
            "Base URL / API Key / 模型名（API Key 填 mock 可预览样式）",
        )
    from ..analyzer import run_analysis
    from ..renderer import render_analysis

    try:
        theme = store.theme_by_id(req.theme_id)
        analyses = await run_analysis(store, req.count)
        if not analyses:
            raise HTTPException(
                status_code=502,
                detail="一条都没解析成功：常见原因是 LLM 接口限流（429，稍后再试或换模型）或候选新闻均无法抓取正文，详情见机器人日志",
            )
        image = await render_analysis(store, theme, analyses)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"深读渲染失败: {e!r}")
        raise HTTPException(status_code=500, detail=f"深读生成失败: {e}")
    return {
        "image": base64.b64encode(image).decode(),
        "items": [
            {
                "title": a.title,
                "source": a.source_name,
                "ok": a.ok,
                "error": a.error,
            }
            for a in analyses
        ],
    }


@router.get("/data/latest_analysis")
async def get_latest_analysis(store: Store = Depends(require_auth)) -> dict:
    from ..renderer import latest_analysis

    data = latest_analysis(store)
    if data is None:
        raise HTTPException(status_code=404, detail="还没有深读渲染记录")
    return {"image": base64.b64encode(data).decode()}
