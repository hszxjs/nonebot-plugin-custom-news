"""静态配置（.env / .env.* 文件中的配置项）。"""

from pydantic import BaseModel, ConfigDict


class Config(BaseModel):
    """插件静态配置，所有项均可通过 .env 文件以 custom_news_ 前缀覆盖。"""

    model_config = ConfigDict(extra="ignore")

    #: DailyHotApi 实例地址，建议自部署（README 提供 Docker 一行命令）
    custom_news_dailyhot_api_url: str = "https://api-hot.imsyy.top"
    #: WebUI 登录密码；不设置则首次启动自动生成随机密码并打印到日志
    custom_news_webui_password: str | None = None
    #: 日报图渲染宽度（像素，pad 比例）
    custom_news_render_width: int = 1280
    #: 数据源磁盘缓存 TTL（秒）
    custom_news_cache_ttl: int = 1800
    #: 定时任务时区
    custom_news_timezone: str = "Asia/Shanghai"
