"""渲染管线：主题 + 数据 → HTML 模板 → PNG。

对 nonebot-plugin-htmlrender 做了兼容封装：
- 新版（0.8+）：render_template()
- 旧版（0.3~0.7）：template_to_pic()
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nonebot import logger

from .fetcher import Digest
from .palette import extract_palette
from .sources.dailyhot import format_hot
from .sources.wallpaper import get_daily_wallpaper
from .store import Store
from .theme import PaletteColors, Theme

TEMPLATE_DIR = Path(__file__).parent / "templates"
FONT_DIR = Path(__file__).parent / "fonts"
ASSETS_DIR = Path(__file__).parent / "assets"

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

#: 字体 data URI 缓存（字体文件不会变化）
_font_uri_cache: dict[str, str] = {}


def _data_uri(path: Path, mime: str, cache_key: str | None = None) -> str:
    """把本地文件编码为 data: URI（about:blank 页面下唯一可靠的资源方式）。"""
    if cache_key and cache_key in _font_uri_cache:
        return _font_uri_cache[cache_key]
    import base64

    uri = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    if cache_key:
        _font_uri_cache[cache_key] = uri
    return uri


class RenderError(Exception):
    pass


# ---------------------------------------------------------------- 资源解析


def resolve_background(store: Store, theme: Theme) -> Path:
    """同步解析本地背景路径（在线壁纸仅使用已缓存文件）。"""
    if theme.background.type == "wallpaper":
        return _resolve_wallpaper_sync(store)
    if theme.background.type == "upload":
        path = store.backgrounds_dir / Path(theme.background.value).name
        if path.exists():
            return path
        raise RenderError(f"上传背景图不存在: {theme.background.value}")
    path = ASSETS_DIR / "backgrounds" / f"{theme.background.value}.jpg"
    if path.exists():
        return path
    raise RenderError(f"预设背景图不存在: {theme.background.value}")


def _resolve_wallpaper_sync(store: Store) -> Path:
    """同步取今日壁纸缓存（渲染时优先使用已下载文件；不存在则阻塞下载）。"""
    import asyncio

    wdir = store.cache_dir / "wallpapers"
    today = datetime.now().strftime("%Y-%m-%d")
    cached = wdir / f"{today}.jpg"
    if cached.exists() and cached.stat().st_size > 10_000:
        return cached
    try:
        path, _ = asyncio.run(
            get_daily_wallpaper(store.cache_dir, store.config.general.wallpaper_url)
        )
        return path
    except Exception as e:
        if cached.exists():
            return cached
        raise RenderError(f"每日壁纸获取失败: {e!r}") from e


async def resolve_background_async(store: Store, theme: Theme) -> Path:
    """异步解析背景（在线壁纸需要网络请求），渲染前调用。"""
    if theme.background.type == "wallpaper":
        try:
            path, _ = await get_daily_wallpaper(
                store.cache_dir, store.config.general.wallpaper_url
            )
            return path
        except Exception as e:
            raise RenderError(f"每日壁纸获取失败: {e!r}") from e
    return resolve_background(store, theme)


# ---------------------------------------------------------------- 配色


def _palette_cache_path(store: Store) -> Path:
    return store.cache_dir / "palette_cache.json"


def resolve_colors(store: Store, theme: Theme, bg_path: Path) -> PaletteColors:
    """auto 模式下从背景图提取配色（带缓存），manual 直接用主题配色。"""
    if theme.palette.mode == "manual":
        return theme.palette.colors

    key = "|".join(
        [
            str(bg_path),
            str(bg_path.stat().st_mtime_ns),
            str(bg_path.stat().st_size),
            theme.background.overlay_mode,
            str(theme.background.overlay),
        ]
    )
    cache_file = _palette_cache_path(store)
    try:
        cache = json.loads(cache_file.read_text("utf-8"))
    except Exception:
        cache = {}
    if key in cache:
        return PaletteColors.model_validate(cache[key])

    colors = extract_palette(
        bg_path,
        overlay_mode=theme.background.overlay_mode,
        overlay_opacity=theme.background.overlay,
    )
    cache[key] = colors.model_dump()
    try:
        cache_file.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    return colors


# ---------------------------------------------------------------- 变量构建


def _card_rgb(card_bg: str) -> str:
    """从 palette.card_bg（rgba 或 hex）提取 "r, g, b"，供模板按不透明度重组。"""
    import re

    m = re.search(r"rgba?\(([^)]+)\)", card_bg)
    if m:
        parts = [x.strip() for x in m.group(1).split(",")]
        nums = [p for p in parts if re.fullmatch(r"\d+", p)]
        if len(nums) >= 3:
            return f"{nums[0]}, {nums[1]}, {nums[2]}"
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", card_bg.strip())
    if m:
        h = m.group(1)
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"
    m = re.fullmatch(r"#([0-9a-fA-F]{3})", card_bg.strip())
    if m:
        h = m.group(1)
        return f"{int(h[0]*2, 16)}, {int(h[1]*2, 16)}, {int(h[2]*2, 16)}"
    return "20, 24, 36"


def _overlay_rgb(mode: str, primary_hex: str) -> str:
    """遮罩基色（浅/深）混入 14% 主题主色，让整图带统一的色调渲染。

    这是「背景-卡片-标题融洽感」的关键：遮罩铺满全图，主色调随之
    浸润背景与卡片，避免纯白/纯黑遮罩与主题色割裂。
    """
    base = (255, 255, 255) if mode == "light" else (12, 14, 24)
    try:
        from .palette import hex_to_rgb

        pr, pg, pb = hex_to_rgb(primary_hex)
    except Exception:
        pr = pg = pb = 128
    mixed = tuple(round(b * 0.86 + p * 0.14) for b, p in zip(base, (pr, pg, pb)))
    return f"{mixed[0]}, {mixed[1]}, {mixed[2]}"


def build_variables(
    store: Store,
    theme: Theme,
    digest: Digest,
    bg_path: Path,
    colors: PaletteColors,
    width: int,
) -> dict:
    now = datetime.now(ZoneInfo(store.config.general.timezone))
    fmt = now.strftime("%Y年%m月%d日")
    date_text = f"{fmt} · {_WEEKDAYS[now.weekday()]}"
    time_text = now.strftime("%Y-%m-%d %H:%M")

    per_card = theme.per_card or {}
    max_items = theme.cards.items_per_card

    cards = []
    for cd in digest.cards:
        items = []
        for idx, item in enumerate(cd.items[:max_items]):
            hot_text = format_hot(item.hot) if theme.cards.show_hot else None
            items.append(
                {
                    "rank": idx + 1,
                    "rank_class": f"r{idx + 1}" if idx < 3 else "rn",
                    "title": item.title,
                    "hot_text": hot_text,
                }
            )
        cards.append(
            {
                "name": cd.name,
                "emoji": cd.emoji,
                "color": per_card.get(cd.source_id, colors.primary),
                "stale": cd.stale,
                "entries": items,
            }
        )

    return {
        "width": width,
        # htmlrender 0.8 通过 page.set_content 加载页面（about:blank 源），
        # file:// 子资源会被 Chromium 拦截，因此字体/背景一律内联为 data: URI
        "font_regular": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Regular.woff2", "font/woff2", "regular"
        ),
        "font_medium": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Medium.woff2", "font/woff2", "medium"
        ),
        "font_bold": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Bold.woff2", "font/woff2", "bold"
        ),
        "bg_url": _data_uri(bg_path, "image/jpeg"),
        "overlay_rgb": _overlay_rgb(theme.background.overlay_mode, colors.primary),
        "overlay_opacity": theme.background.overlay,
        "bg_blur": theme.background.blur,
        "palette": colors.model_dump(),
        "columns": theme.cards.columns,
        "border_radius": theme.cards.border_radius,
        "glass_blur": theme.cards.glass_blur,
        "glass_sat": theme.cards.glass_saturation,
        "card_rgb": _card_rgb(colors.card_bg),
        "card_opacity": theme.cards.card_opacity,
        "shadow_level": theme.cards.shadow,
        "show_hot": theme.cards.show_hot,
        "scale": theme.typography.scale,
        "title_weight": theme.typography.title_weight,
        "header": {
            "title": theme.header.title,
            "subtitle": theme.header.subtitle,
            "show_date": theme.header.show_date,
            "date_text": date_text,
        },
        "footer": {
            "custom_text": theme.footer.custom_text,
            "show_credit": theme.footer.show_credit,
            "time_text": time_text,
        },
        "cards": cards,
        "failed_names": "、".join(digest.failed) if digest.failed else "",
    }


# ---------------------------------------------------------------- 渲染


async def render_html(template_vars: dict, width: int) -> bytes:
    """调用 htmlrender 渲染模板为 PNG（新旧 API 兼容）。"""
    try:  # 新版 0.8+
        from nonebot_plugin_htmlrender import render_template  # type: ignore

        artifact = await render_template(
            str(TEMPLATE_DIR),
            "daily_digest.html",
            variables=template_vars,
            width=width,
            # pad 宽幅长图：1.5 倍采样在聊天清晰度与文件体积间取得平衡
            device_pixel_ratio=1.5,
        )
        return bytes(artifact)
    except ImportError:
        pass
    except Exception as e:
        raise RenderError(f"htmlrender 渲染失败（新版 API）: {e!r}") from e

    try:  # 旧版 0.3 ~ 0.7
        from nonebot_plugin_htmlrender import template_to_pic  # type: ignore

        return await template_to_pic(
            template_dir=str(TEMPLATE_DIR),
            template_name="daily_digest.html",
            templates=template_vars,
            pagesize={"width": width, "height": 800},
        )
    except ImportError as e:
        raise RenderError("未安装 nonebot-plugin-htmlrender") from e
    except Exception as e:
        raise RenderError(f"htmlrender 渲染失败（旧版 API）: {e!r}") from e


async def render_digest(store: Store, theme: Theme, digest: Digest) -> bytes:
    """完整渲染一张日报图。"""
    bg_path = await resolve_background_async(store, theme)
    colors = resolve_colors(store, theme, bg_path)
    variables = build_variables(
        store, theme, digest, bg_path, colors, store.config.general.render_width
    )
    data = await render_html(variables, store.config.general.render_width)
    _save_latest(store, data)
    logger.info(
        f"日报渲染完成: {len(data) // 1024}KB, "
        f"卡片 {len(digest.cards)} 张, 失败源 {len(digest.failed)} 个"
    )
    return data


def _save_latest(store: Store, data: bytes) -> None:
    latest = store.cache_dir / "latest_render.png"
    try:
        latest.write_bytes(data)
    except OSError:
        pass


def latest_render(store: Store) -> bytes | None:
    latest = store.cache_dir / "latest_render.png"
    if latest.exists():
        return latest.read_bytes()
    return None


def theme_signature(theme: Theme, bg_path: Path) -> str:
    """主题+背景指纹，用于 WebUI 缓存预览。"""
    raw = theme.model_dump_json() + str(bg_path)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- 新闻深读渲染

ANALYSIS_WIDTH = 840  # 手机聊天截图比例


def build_analysis_variables(
    store: Store, theme: Theme, analyses: list
) -> dict:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .sources.dailyhot import format_hot  # noqa: F401（保持导入一致性）

    colors = (
        theme.palette.colors
        if theme.palette.mode == "manual"
        else theme.palette.colors
    )
    now = datetime.now(ZoneInfo(store.config.general.timezone))
    is_dark = theme.background.overlay_mode == "dark"
    if is_dark:
        page_bg_top = "#0d1020"
        page_bg_bottom = "#0a0c16"
        # 深色页面上保证文字可读
        colors = colors.model_copy(
            update={
                "text": colors.text if _is_light_hex(colors.text) else "#eef0fa",
                "subtext": colors.subtext if _is_light_hex(colors.subtext) else "#aab0c8",
            }
        )
    else:
        page_bg_top = "#f2f4fa"
        page_bg_bottom = "#e9ecf5"
        colors = colors.model_copy(
            update={
                "text": colors.text if not _is_light_hex(colors.text) else "#2c2f3c",
                "subtext": colors.subtext if not _is_light_hex(colors.subtext) else "#66708c",
            }
        )

    news_list = [
        {
            "source": a.source_name,
            "emoji": a.emoji,
            "title": _truncate(a.title, 26),
            "ok": a.ok,
            "error": a.error,
            "event": a.event or a.title,
            "background": a.background,
            "points": a.points,
            "impact": a.impact,
            "remark": a.remark,
            "article_chars": a.article_chars,
        }
        for a in analyses
    ]
    model = store.config.general.llm_model
    return {
        "width": ANALYSIS_WIDTH,
        "font_regular": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Regular.woff2", "font/woff2", "regular"
        ),
        "font_medium": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Medium.woff2", "font/woff2", "medium"
        ),
        "font_bold": _data_uri(
            FONT_DIR / "HarmonyOS_Sans_SC_Bold.woff2", "font/woff2", "bold"
        ),
        "palette": colors.model_dump(),
        "page_bg_top": page_bg_top,
        "page_bg_bottom": page_bg_bottom,
        "date_text": now.strftime("%Y年%m月%d日") + " · " + _WEEKDAYS[now.weekday()],
        "news_list": news_list,
        "model_text": f"由 {model} 解析",
    }


def _is_light_hex(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r * 299 + g * 587 + b * 114) / 1000 > 140


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


async def render_analysis(store: Store, theme: Theme, analyses: list) -> bytes:
    """渲染「今日深读」聊天记录风格图片。"""
    variables = build_analysis_variables(store, theme, analyses)
    try:  # 新版 0.8+
        from nonebot_plugin_htmlrender import render_template  # type: ignore

        artifact = await render_template(
            str(TEMPLATE_DIR),
            "analysis_chat.html",
            variables=variables,
            width=ANALYSIS_WIDTH,
            device_pixel_ratio=1.5,
        )
        data = bytes(artifact)
    except ImportError:
        from nonebot_plugin_htmlrender import template_to_pic  # type: ignore

        data = await template_to_pic(
            template_dir=str(TEMPLATE_DIR),
            template_name="analysis_chat.html",
            templates=variables,
            pagesize={"width": ANALYSIS_WIDTH, "height": 800},
        )
    latest = store.cache_dir / "latest_analysis.png"
    try:
        latest.write_bytes(data)
    except OSError:
        pass
    logger.info(f"今日深读渲染完成: {len(data) // 1024}KB, {len(analyses)} 条新闻")
    return data


def latest_analysis(store: Store) -> bytes | None:
    latest = store.cache_dir / "latest_analysis.png"
    if latest.exists():
        return latest.read_bytes()
    return None
