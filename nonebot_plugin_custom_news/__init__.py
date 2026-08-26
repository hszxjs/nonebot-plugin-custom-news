"""nonebot-plugin-custom-news：全网热点日报。"""

from nonebot import require, get_driver

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

from pathlib import Path

from nonebot import logger
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .config import Config

_PLUGIN_ID = "nonebot_plugin_custom_news"


def _inject_htmlrender_allowed_paths() -> None:
    """为本插件预配置 htmlrender：默认 provider 与本地资源白名单。

    必须在 require("nonebot_plugin_htmlrender") 之前执行：
    htmlrender 0.8+ 在插件导入时读取 driver.config.render 配置。
    - 未配置 provider 时默认 playwright（本插件依赖 [playwright] extra）
    - 把模板/字体/背景目录并入 local_access.allowed_paths（合并，不覆盖用户配置）
    """
    from nonebot_plugin_localstore import BASE_CACHE_DIR, BASE_DATA_DIR

    package_dir = Path(__file__).parent
    roots = [
        package_dir / "templates",
        package_dir / "fonts",
        package_dir / "assets" / "backgrounds",
        BASE_DATA_DIR / _PLUGIN_ID,  # 用户上传背景
        BASE_CACHE_DIR / _PLUGIN_ID,  # 每日壁纸/渲染缓存
    ]

    try:
        cfg = get_driver().config
        render = getattr(cfg, "render", None)
        render = dict(render) if isinstance(render, dict) else {}
        render.setdefault("provider", "playwright")
        # pad 宽幅长图（1280×~4500 CSS）在高倍采样下会超过默认 16M 像素上限
        html = dict(render.get("html") or {})
        html.setdefault("max_pixels", 33_554_432)
        render["html"] = html
        resources = dict(render.get("resources") or {})
        local = dict(resources.get("local_access") or {})
        allowed = list(local.get("allowed_paths") or [])
        for root in roots:
            text = str(root)
            if text not in allowed:
                allowed.append(text)
        local["allowed_paths"] = allowed
        resources["local_access"] = local
        render["resources"] = resources
        cfg.render = render
        logger.debug(f"已为 htmlrender 预配置: provider={render['provider']}, 白名单={allowed}")
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"预配置 htmlrender 失败（渲染可能无法访问字体/背景）: {e!r}"
        )


_inject_htmlrender_allowed_paths()
require("nonebot_plugin_htmlrender")

__plugin_meta__ = PluginMetadata(
    name="全网热点日报",
    description=(
        "每日聚合 B站/微博/新闻/科技/全球等全网热点，渲染为高自定义主题卡片日报图"
        "（背景图+自动取色+毛玻璃卡片），定时推送到群/私聊，"
        "并附带 HeroUI 打造的 WebUI 可视化后台"
    ),
    usage=(
        "发送「今日热点」立即获取日报图；\n"
        "发送「订阅热点 / 退订热点」管理本会话定时推送；\n"
        "WebUI：浏览器打开 http://bot-host:port/custom-news/webui/"
    ),
    type="application",
    homepage="https://github.com/hszxjs/nonebot-plugin-custom-news",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "author": "hszxjs",
        "version": "0.1.0",
        # PicMenu Next 菜单声明
        "pmn": {
            "hidden": False,
            "template": "default",
        },
        "menu_data": [
            {
                "func": "今日热点",
                "trigger_method": "`今日热点`",
                "trigger_condition": "发送命令（无需@）",
                "brief_des": "生成今日全网热点日报图（B站/新闻/科技/全球/新歌榜）",
                "detail_des": (
                    "聚合启用的数据源，按当前主题渲染成卡片日报图发送。"
                    "别名：今日热榜 / 热点日报 / 全网热点 / 热点速递。"
                    "主题可在 WebUI「主题工坊」自定义（背景图+自动取色+毛玻璃卡片）"
                ),
            },
            {
                "func": "订阅热点",
                "trigger_method": "`订阅热点`",
                "trigger_condition": "在群聊或私聊中发送",
                "brief_des": "将本会话加入定时推送列表",
                "detail_des": "订阅后每个定时时段都会收到日报图；别名：热点订阅。推送时段在 WebUI「推送管理」配置。",
            },
            {
                "func": "退订热点",
                "trigger_method": "`退订热点`",
                "trigger_condition": "在已订阅的会话中发送",
                "brief_des": "取消本会话的定时推送",
                "detail_des": "别名：取消订阅热点 / 热点退订",
            },
            {
                "func": "热点解析",
                "trigger_method": "`热点解析`",
                "trigger_condition": "发送命令（需在 WebUI 配置 LLM）",
                "brief_des": "AI 深读：抓新闻原文生成聊天记录风格解读图",
                "detail_des": (
                    "挑选新闻类头条，抓取原文交给大模型解析，输出「今日深读」聊天记录风格图片"
                    "（事件/背景/要点/影响/锐评）。配置 LLM 后日报发送也会自动跟随。"
                    "别名：新闻解析 / 今日深读"
                ),
            },
            {
                "func": "新歌榜",
                "trigger_method": "`新歌榜`",
                "trigger_condition": "发送命令",
                "brief_des": "网易云/QQ音乐新歌榜聊天记录（可播放卡片+热评）",
                "detail_des": (
                    "两个平台各发一条 QQ 合并转发聊天记录：Top10 文字榜单 + "
                    "每首歌可播放音乐卡片 + 热评 Top3。"
                    "别名：音乐榜 / 新歌速递。登录音乐账号（WebUI「音乐账号」页）后卡片可内嵌试听直链"
                ),
            },
            {
                "func": "热点帮助",
                "trigger_method": "`热点帮助`",
                "trigger_condition": "发送命令",
                "brief_des": "查看本插件全部命令",
                "detail_des": "别名：热点指令。WebUI 管理后台：浏览器打开 /custom-news/webui/",
            },
        ],
    },
)

driver = get_driver()


@driver.on_startup
async def _startup() -> None:
    """运行期初始化：加载配置、注册定时任务（此时插件注册已完成）。"""
    try:
        from .scheduler import rebuild_jobs
        from .store import get_store

        store = get_store()
        rebuild_jobs(store)
        logger.info("全网热点日报初始化完成")
    except Exception as e:  # noqa: BLE001
        logger.error(f"全网热点日报初始化失败: {e!r}")


# 挂载 WebUI（FastAPI driver 环境下生效；只注册路由/静态文件，不触碰 store）
try:
    from .webui import setup_webui

    setup_webui()
except Exception as e:  # noqa: BLE001
    logger.error(f"全网热点日报 WebUI 挂载失败: {e!r}")

# 注册命令
from . import matcher  # noqa: E402, F401
