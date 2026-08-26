"""WebUI 挂载：API 路由 + 前端静态文件（需要 FastAPI driver）。"""

from pathlib import Path

from nonebot import logger, get_driver
from nonebot.drivers import ASGIMixin

from .api import router as api_router
from .api_music import router as api_music_router

DIST_DIR = Path(__file__).parent / "dist"
API_PREFIX = "/custom-news/api"
WEBUI_PREFIX = "/custom-news/webui"


def setup_webui() -> bool:
    """把 API 路由与前端静态文件挂到 NoneBot 的 ASGI 应用上。

    非 FastAPI driver 环境下仅禁用 WebUI，其余功能不受影响。
    """
    driver = get_driver()
    if not isinstance(driver, ASGIMixin):
        logger.warning("当前 driver 不支持 ASGI 服务端，WebUI 已禁用（其余功能正常）")
        return False

    try:
        from fastapi import FastAPI  # noqa: F401
        from fastapi.staticfiles import StaticFiles
    except ImportError:
        logger.warning("未安装 fastapi，WebUI 已禁用")
        return False

    app = driver.server_app
    app.include_router(api_router, prefix="")
    app.include_router(api_music_router, prefix="")

    if DIST_DIR.exists() and any(DIST_DIR.iterdir()):
        app.mount(
            WEBUI_PREFIX,
            StaticFiles(directory=DIST_DIR, html=True),
            name="custom-news-webui",
        )
        logger.info(f"全网热点日报 WebUI 已就绪: {WEBUI_PREFIX}/ （API: {API_PREFIX}/）")
    else:
        logger.warning(
            "WebUI 前端文件缺失（webui/dist 为空），仅提供 API 接口。"
            "如需完整后台界面请安装带 webui/dist 的发布包"
        )
    return True
