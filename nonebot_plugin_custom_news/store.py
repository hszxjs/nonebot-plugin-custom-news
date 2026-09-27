"""运行时配置存取：localstore 数据目录中的 config.json（WebUI 可热更新）。"""

import asyncio
import hashlib
import json
import os
import secrets
import string
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from nonebot import logger, require

require("nonebot_plugin_localstore")
from nonebot_plugin_localstore import get_plugin_cache_dir, get_plugin_data_dir

from .config import Config
from .sources import BUILTIN_SOURCES
from .theme import PRESET_THEMES, Theme


class GeneralSettings(BaseModel):
    dailyhot_api_url: str = "https://api-hot.imsyy.top"
    render_width: int = Field(default=1280, ge=640, le=4096)
    cache_ttl: int = 1800
    timezone: str = "Asia/Shanghai"
    #: 自定义每日壁纸直链（留空使用必应每日壁纸）
    wallpaper_url: str = ""
    #: 新闻深读（LLM）：OpenAI 兼容接口，DeepSeek/智谱/Ollama 均可
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    #: 生成上限（推理模型思考过程计入，太小会截断 JSON；GLM/DeepSeek-R1 建议 8000 起）
    llm_max_tokens: int = 8000
    #: 日报发送后自动跟随解析图
    llm_follow_digest: bool = True
    #: 每次解析的新闻条数
    analysis_count: int = 3
    #: 深读风格指令（人设/口吻，追加到内置 system prompt 之后；留空用内置通用风格）
    llm_style_prompt: str = ""
    #: 深读图里的署名
    analysis_bot_name: str = "热点解读员"
    #: 深读图的头像：data URI / http(s) 链接 / 本地图片路径；留空用内置 emoji 头像
    analysis_avatar: str = ""

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, v: str) -> str:
        """时区必须能被 ZoneInfo 解析。

        非法时区会让 rebuild_jobs 的 add_job 抛异常，而它是「先全删再重建」，
        会在写坏配置的瞬间让全部定时任务消失 —— 这里挡住入口。
        """
        from zoneinfo import ZoneInfo as _ZoneInfo

        try:
            _ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"非法时区 {v!r}：{e}") from e
        return v


class SourceSetting(BaseModel):
    enabled: bool = False
    limit: int = 10


class CustomSourceDef(BaseModel):
    """用户自定义的 DailyHotApi 路由源。"""

    id: str
    name: str
    route: str
    category: str = "fun"
    emoji: str = "📌"
    limit: int = 8
    enabled: bool = True


class ScheduleItem(BaseModel):
    """一个定时推送时段。"""

    #: 会被拼进 APScheduler 的 job id（custom_news_pre_<id>），因此限制字符集：
    #: id='pre_x' 与 id='x' 会互相覆盖，导致某时段的日报永远不推
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    label: str = "每日推送"
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    #: 星期（0=周一 … 6=周日），空列表等同每天
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    #: 使用的主题 id；留空使用当前激活主题
    theme_id: str | None = None
    enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def _check_weekdays(cls, v: list[int]) -> list[int]:
        """0-6 之外的值会变成非法 cron 表达式（如 day_of_week=7），先在这里挡掉。"""
        bad = [d for d in v if not 0 <= d <= 6]
        if bad:
            raise ValueError(f"weekdays 只允许 0-6（0=周一），收到 {bad}")
        return sorted(set(v))


class PushTargetItem(BaseModel):
    """一个推送目标（uniseg Target 序列化存储，跨适配器）。"""

    id: str
    label: str
    enabled: bool = True
    target: dict[str, Any]
    added_at: str = ""


class MusicAccount(BaseModel):
    """音乐平台登录态（cookie 存本机，WebUI 展示脱敏）。"""
    cookie: str = ""
    nickname: str = ""
    logged_at: str = ""


class MusicChatSettings(BaseModel):
    #: 每平台展示歌曲数（卡片+热评）
    count: int = 10
    #: 使用合并转发（关闭则逐条发送）
    forward: bool = True
    #: 卡片后附热评
    comments: bool = True


class WebUIAuth(BaseModel):
    username: str = "admin"
    #: 口令哈希：scrypt 自描述串，或旧版无盐 SHA-256（登录成功后透明重写）
    password_sha: str = ""
    secret: str = ""
    #: 改密码时轮换：旧 secret 保留一段时间，让在用会话平滑过渡
    secret_prev: str = ""
    secret_rotated_at: float = 0.0


class RuntimeConfig(BaseModel):
    general: GeneralSettings = GeneralSettings()
    sources: dict[str, SourceSetting] = Field(default_factory=dict)
    custom_sources: list[CustomSourceDef] = Field(default_factory=list)
    schedules: list[ScheduleItem] = Field(default_factory=list)
    push_targets: list[PushTargetItem] = Field(default_factory=list)
    themes: dict[str, Theme] = Field(default_factory=dict)
    active_theme_id: str = "sakura"
    webui: WebUIAuth = WebUIAuth()
    music_accounts: dict[str, MusicAccount] = Field(default_factory=dict)
    music_chat: MusicChatSettings = MusicChatSettings()
    #: 配置结构版本（用于自动迁移；缺失该字段的旧配置视为 1）
    version: int = 1

#: 当前配置结构版本
CONFIG_VERSION = 3


class Store:
    """配置单例：负责 config.json 读写与各数据子目录。"""

    def __init__(self, plugin_config: Config) -> None:
        self.plugin_config = plugin_config
        self.data_dir: Path = get_plugin_data_dir()
        self.cache_dir: Path = get_plugin_cache_dir()
        self.backgrounds_dir: Path = self.data_dir / "backgrounds"
        self.backgrounds_dir.mkdir(parents=True, exist_ok=True)
        self.config_path: Path = self.data_dir / "config.json"
        self._lock = asyncio.Lock()
        self.config: RuntimeConfig = self._load_or_create()
        # .env 显式配置优先于 store 内历史值（否则改 .env 永远不生效且无提示）
        env_url = (self.plugin_config.custom_news_dailyhot_api_url or "").strip()
        default_url = "https://api-hot.imsyy.top"
        if env_url and env_url != default_url and self.config.general.dailyhot_api_url != env_url:
            old = self.config.general.dailyhot_api_url
            self.config.general.dailyhot_api_url = env_url
            self._write(self.config)
            logger.info(
                f"dailyhot_api_url 已由 .env 接管: {old} → {env_url}"
            )

    # ------------------------------------------------------------ 读写

    def _default_config(self) -> RuntimeConfig:
        # .env 是外部输入：越界值在这里收敛并告警，不能让 Store 初始化直接抛错
        # （否则 _store 永远为 None，WebUI 与命令全 500，且重启也不自愈）
        env_width = self.plugin_config.custom_news_render_width
        if not 640 <= env_width <= 4096:
            logger.warning(
                f".env 的 custom_news_render_width={env_width} 超出 640-4096，已收敛"
            )
            env_width = min(max(env_width, 640), 4096)
        env_tz = self.plugin_config.custom_news_timezone
        try:
            from zoneinfo import ZoneInfo as _ZI

            _ZI(env_tz)
        except Exception:
            logger.warning(f".env 的 custom_news_timezone={env_tz!r} 非法，回退 Asia/Shanghai")
            env_tz = "Asia/Shanghai"
        cfg = RuntimeConfig(
            version=CONFIG_VERSION,
            general=GeneralSettings(
                dailyhot_api_url=self.plugin_config.custom_news_dailyhot_api_url,
                render_width=env_width,
                cache_ttl=self.plugin_config.custom_news_cache_ttl,
                timezone=env_tz,
            ),
            sources={
                s.id: SourceSetting(enabled=s.default_enabled, limit=s.default_limit)
                for s in BUILTIN_SOURCES
            },
            schedules=[
                ScheduleItem(id="morning", label="晨间热点", hour=8, minute=0),
            ],
            themes={k: v.model_copy(deep=True) for k, v in PRESET_THEMES.items()},
            active_theme_id="sakura",
            webui=self._init_webui_auth(),
        )
        return cfg

    def _init_webui_auth(self) -> WebUIAuth:
        env_pwd = self.plugin_config.custom_news_webui_password
        if env_pwd:
            password = env_pwd
            logger.info("WebUI 密码使用 .env 中的 custom_news_webui_password")
        else:
            alphabet = string.ascii_letters + string.digits
            password = "".join(secrets.choice(alphabet) for _ in range(8))
            logger.warning(
                "「全网热点日报」WebUI 初始账号 admin，初始密码: "
                f"{password} （登录后请尽快在 WebUI 设置页修改，"
                "或在 .env 中配置 custom_news_webui_password）"
            )
        return WebUIAuth(
            username="admin",
            password_sha=hashlib.sha256(password.encode("utf-8")).hexdigest(),
            secret=secrets.token_hex(32),
        )

    def _load_or_create(self) -> RuntimeConfig:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text("utf-8"))
                cfg = RuntimeConfig.model_validate(data)
                # 兜底：保证新增内置源/预设主题在升级后补齐
                changed = False
                for s in BUILTIN_SOURCES:
                    if s.id not in cfg.sources:
                        cfg.sources[s.id] = SourceSetting(
                            enabled=s.default_enabled, limit=s.default_limit
                        )
                        changed = True
                for tid, theme in PRESET_THEMES.items():
                    if tid not in cfg.themes:
                        cfg.themes[tid] = theme.model_copy(deep=True)
                        changed = True
                if cfg.active_theme_id not in cfg.themes:
                    cfg.active_theme_id = next(iter(cfg.themes))
                    changed = True
                # v2: pad 宽度；v3: 双列布局（用户自定义宽度保留，预设主题刷新为新默认值）
                if cfg.version < CONFIG_VERSION:
                    if cfg.version < 2 and cfg.general.render_width == 1080:
                        cfg.general.render_width = 1280
                    cfg.version = CONFIG_VERSION
                    for tid, fresh in PRESET_THEMES.items():
                        if tid in cfg.themes:
                            keep_id = cfg.themes[tid].id
                            cfg.themes[tid] = fresh.model_copy(deep=True)
                            cfg.themes[tid].id = keep_id
                    changed = True
                if changed:
                    self._write(cfg)
                return cfg
            except Exception as e:
                # 校验失败 ≠ 文件损坏：逐个分区降级修复，绝不整份重建
                logger.error(f"config.json 校验失败，按分区修复: {e!r}")
                return self._salvage(data)
        # 只有 JSON 本身解析不了时才走重建（此时确实没有可救的内容）
        logger.error("config.json 无法解析，备份后重建默认配置")
        self._backup()
        cfg = self._default_config()
        self._write(cfg)
        return cfg

    def _backup(self) -> None:
        try:
            os.replace(self.config_path, self.config_path.with_suffix(".json.bak"))
        except OSError:
            pass

    def _repair(self, model_cls: Any, raw: object, label: str) -> Any:
        """先整体校验；失败则**逐字段**校验，只把非法字段落回默认值。"""
        if not isinstance(raw, dict):
            logger.error(f"[降级] {label} 不是对象，使用默认值")
            return model_cls()
        try:
            return model_cls.model_validate(raw)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[降级] {label} 校验失败，改为逐字段修复: {e!r}")

        # 注意：必须用「模型本身」逐字段校验，不能按 field.annotation 单独校验——
        # 那样会绕过 @field_validator（时区校验就在校验器里，注解只是 str）。
        # 单字段构造 {fname: value} 其余走默认值，既隔离字段又不跳过校验器。
        values: dict[str, Any] = {}
        for fname in model_cls.model_fields:
            if fname not in raw:
                continue
            try:
                values[fname] = getattr(model_cls.model_validate({fname: raw[fname]}), fname)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[降级] 字段 {label}.{fname} 非法，落回默认值: {e!r}")
        return model_cls().model_copy(update=values)

    def _salvage(self, data: object) -> RuntimeConfig:
        """校验失败时的降级路径：逐分区、必要时逐字段修复，**绝不整份重建**。

        背景：校验器（时区/宽度/weekdays 等）会让「旧版本自己写进去的历史值」在升级后
        首次加载时失败。若失败即整份重建，会静默丢掉 LLM Key、推送目标、自定义主题、
        音乐 cookie，并重新生成 WebUI 密码与签名 secret（旧 Token 全废、不可撤销）。
        粒度必须到**字段**：只有一个 timezone 非法时，同分区里的 LLM Key 必须留住。
        """
        from pydantic import BaseModel, TypeAdapter

        self._backup()
        base = self._default_config()
        if not isinstance(data, dict):
            logger.error("[降级] 配置根不是对象，使用默认配置（原文件已备份为 .bak）")
            self._write(base)
            return base

        values: dict[str, Any] = {}
        for name, field in RuntimeConfig.model_fields.items():
            if name not in data:
                continue
            ann = field.annotation
            try:
                if isinstance(ann, type) and issubclass(ann, BaseModel):
                    # 结构化分区（general/webui/...）：坏了也只修坏字段，不重生成其余
                    values[name] = self._repair(ann, data[name], label=name)
                else:
                    values[name] = TypeAdapter(ann).validate_python(data[name])
            except Exception as e:  # noqa: BLE001
                logger.error(f"[降级] 分区 {name} 无法修复，落回默认值: {e!r}")

        cfg = base.model_copy(update=values)
        self._write(cfg)
        logger.warning("[降级] 配置已按分区/字段修复并写回（原文件备份为 config.json.bak）")
        return cfg

    def _write(self, cfg: RuntimeConfig) -> None:
        tmp = self.config_path.with_suffix(".json.tmp")
        tmp.write_text(cfg.model_dump_json(indent=2), "utf-8")
        try:
            os.chmod(tmp, 0o600)  # 内含 LLM Key、签名 secret、音乐 cookie
        except OSError:
            pass
        os.replace(tmp, self.config_path)

    async def save(self, cfg: RuntimeConfig | None = None) -> None:
        async with self._lock:
            self._write(cfg if cfg is not None else self.config)

    def save_sync(self, cfg: RuntimeConfig | None = None) -> None:
        self._write(cfg if cfg is not None else self.config)

    # ------------------------------------------------------------ 便捷访问

    def active_theme(self) -> Theme:
        theme = self.config.themes.get(self.config.active_theme_id)
        if theme is None:
            theme = next(iter(self.config.themes.values()))
        return theme

    def theme_by_id(self, theme_id: str | None) -> Theme:
        if theme_id and theme_id in self.config.themes:
            return self.config.themes[theme_id]
        return self.active_theme()


_store: Store | None = None


def get_store(plugin_config: Config | None = None) -> Store:
    global _store
    if _store is None:
        from nonebot import get_plugin_config  # noqa: PLC0415

        cfg = plugin_config or get_plugin_config(Config)
        _store = Store(cfg)
    return _store
