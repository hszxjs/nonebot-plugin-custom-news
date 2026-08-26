"""业务编排：抓取数据 + 渲染日报图（命令、定时推送、WebUI 共用入口）。"""

from nonebot import logger

from .fetcher import Digest, fetch_digest
from .renderer import RenderError, render_digest
from .store import Store
from .theme import Theme


async def generate_digest_image(
    store: Store,
    theme_id: str | None = None,
    theme_override: Theme | None = None,
    force_refresh: bool = False,
) -> tuple[bytes, Digest]:
    """生成一张日报图。

    Args:
        theme_id: 指定主题（空则用激活主题）
        theme_override: 直接传入主题对象（WebUI 预览用，优先级高于 theme_id）
        force_refresh: 强制刷新数据源缓存
    """
    theme = theme_override or store.theme_by_id(theme_id)
    digest = await fetch_digest(store, force_refresh=force_refresh)
    if not digest.cards:
        raise RenderError(
            "未能获取到任何数据源内容，请检查 DailyHotApi 地址或稍后再试"
        )
    image = await render_digest(store, theme, digest)
    logger.info(
        f"日报图生成成功: 主题={theme.name}, 卡片={len(digest.cards)}, 失败={digest.failed}"
    )
    return image, digest


async def generate_analysis_image(
    store: Store,
    theme_id: str | None = None,
    count: int | None = None,
) -> tuple[bytes, list]:
    """生成「今日深读」聊天记录风格解析图。"""
    from .analyzer import run_analysis
    from .renderer import render_analysis

    theme = store.theme_by_id(theme_id)
    analyses = await run_analysis(store, count)
    if not analyses:
        raise RenderError("没有可解析的新闻（请先在数据源页启用新闻类源并刷新数据）")
    image = await render_analysis(store, theme, analyses)
    return image, analyses
