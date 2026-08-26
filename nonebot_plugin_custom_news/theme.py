"""主题模型与预设主题。

主题是纯数据（可 JSON 序列化），同时驱动后端渲染模板（CSS 变量）与
WebUI 前端实时预览（React 使用同一套变量体系）。
"""

from typing import Literal

from pydantic import BaseModel, Field


class BackgroundConfig(BaseModel):
    """日报背景图配置。"""

    type: Literal["preset", "upload", "wallpaper"] = "preset"
    #: preset: 预设背景 id；upload: 上传文件名；wallpaper: 忽略（每日在线壁纸）
    value: str = "sakura"
    #: 遮罩层透明度 0~1，用于保证文字可读性
    overlay: float = 0.35
    #: 遮罩颜色：light 白色遮罩（适合浅色主题）/ dark 黑色遮罩（适合深色主题）
    overlay_mode: Literal["light", "dark"] = "light"
    #: 背景图高斯模糊半径 px
    blur: float = 0


class PaletteColors(BaseModel):
    """手动配色（mode=manual 时生效；auto 时由背景图提取）。"""

    primary: str = "#e8739a"
    accent: str = "#6db7e8"
    text: str = "#33333f"
    subtext: str = "#6f6f82"
    card_bg: str = "rgba(255, 255, 255, 0.55)"
    card_border: str = "rgba(255, 255, 255, 0.70)"
    rank1: str = "#ff5d5d"
    rank2: str = "#ff9f43"
    rank3: str = "#ffc94d"
    rank_n: str = "#9aa0b0"
    hot: str = "#8d92a6"


class PaletteConfig(BaseModel):
    mode: Literal["auto", "manual"] = "auto"
    colors: PaletteColors = PaletteColors()


class CardStyleConfig(BaseModel):
    """卡片样式。"""

    #: 每行卡片数 1~4
    columns: int = Field(default=2, ge=1, le=4)
    #: 每张卡片最多显示条数 1~20
    items_per_card: int = Field(default=10, ge=1, le=20)
    #: 卡片圆角 px
    border_radius: int = 24
    #: 毛玻璃模糊强度 px（0 关闭）
    glass_blur: int = 18
    #: 毛玻璃饱和度增强倍率
    glass_saturation: float = 1.4
    #: 卡片阴影强度 0~3（0 关闭）
    shadow: int = 2
    #: 是否显示每条热点右侧的热度数值
    show_hot: bool = True


class TypographyConfig(BaseModel):
    scale: float = Field(default=1.0, gt=0.5, le=1.8)
    title_weight: int = 700


class HeaderConfig(BaseModel):
    title: str = "今日热点速递"
    subtitle: str = "全网热点 · 一图速览"
    show_date: bool = True


class FooterConfig(BaseModel):
    custom_text: str = ""
    show_credit: bool = True


class Theme(BaseModel):
    """一套完整主题。"""

    id: str
    name: str
    background: BackgroundConfig = BackgroundConfig()
    palette: PaletteConfig = PaletteConfig()
    cards: CardStyleConfig = CardStyleConfig()
    typography: TypographyConfig = TypographyConfig()
    header: HeaderConfig = HeaderConfig()
    footer: FooterConfig = FooterConfig()
    #: 按源 id 覆写卡片主色（标题/横线），如 {"weibo": "#ff6b6b"}
    per_card: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# 预设主题
# --------------------------------------------------------------------------

PRESET_THEMES: dict[str, Theme] = {
    "sakura": Theme(
        id="sakura",
        name="樱粉",
        background=BackgroundConfig(
            type="preset", value="sakura", overlay=0.42, overlay_mode="light"
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#e882a8",
                accent="#7ab8e8",
                text="#3a3340",
                subtext="#7a7080",
                card_bg="rgba(255, 255, 255, 0.55)",
                card_border="rgba(255, 255, 255, 0.70)",
            ),
        ),
        cards=CardStyleConfig(),
        per_card={"weibo": "#f56c6c", "bilibili": "#7ab8e8"},
    ),
    "starry": Theme(
        id="starry",
        name="星夜",
        background=BackgroundConfig(
            type="preset", value="starry", overlay=0.38, overlay_mode="dark", blur=2
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#9db8ff",
                accent="#e8a8d8",
                text="#f0f2fa",
                subtext="#b8bfd8",
                card_bg="rgba(30, 34, 54, 0.45)",
                card_border="rgba(255, 255, 255, 0.16)",
                rank1="#ff7b72",
                rank2="#ffa657",
                rank3="#ffe08a",
                rank_n="#7f87a8",
                hot="#8f97b8",
            ),
        ),
        cards=CardStyleConfig(glass_blur=20, glass_saturation=1.5),
        per_card={"weibo": "#ff7b72", "bilibili": "#8cc8ff"},
    ),
    "ocean": Theme(
        id="ocean",
        name="海空",
        background=BackgroundConfig(
            type="preset", value="ocean", overlay=0.30, overlay_mode="light"
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#2f8fd8",
                accent="#39b8c8",
                text="#22344a",
                subtext="#5b7390",
                card_bg="rgba(255, 255, 255, 0.55)",
                card_border="rgba(255, 255, 255, 0.70)",
            ),
        ),
        per_card={"weibo": "#f56c6c", "bilibili": "#4aa8e8"},
    ),
    "dusk": Theme(
        id="dusk",
        name="暮金",
        background=BackgroundConfig(
            type="preset", value="dusk", overlay=0.42, overlay_mode="dark"
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#f0b860",
                accent="#e8887a",
                text="#faf3e8",
                subtext="#d0c0a8",
                card_bg="rgba(45, 32, 28, 0.45)",
                card_border="rgba(255, 235, 200, 0.20)",
                rank1="#ff8a5c",
                rank2="#ffc86b",
                rank3="#ffe3a0",
                rank_n="#a89880",
                hot="#b8a890",
            ),
        ),
        per_card={"weibo": "#ff7b6b", "bilibili": "#8ab8e8"},
    ),
    "mint": Theme(
        id="mint",
        name="薄荷",
        background=BackgroundConfig(
            type="preset", value="mint", overlay=0.32, overlay_mode="light"
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#3aa88a",
                accent="#7ac8b8",
                text="#2a3f38",
                subtext="#5f7a70",
                card_bg="rgba(255, 255, 255, 0.58)",
                card_border="rgba(255, 255, 255, 0.72)",
            ),
        ),
        per_card={"weibo": "#f56c6c", "bilibili": "#4aa8e8"},
    ),
    "ink": Theme(
        id="ink",
        name="墨白",
        background=BackgroundConfig(
            type="preset", value="ink", overlay=0.10, overlay_mode="light", blur=6
        ),
        palette=PaletteConfig(
            mode="auto",
            colors=PaletteColors(
                primary="#2a2a32",
                accent="#8a8a96",
                text="#22222a",
                subtext="#6a6a76",
                card_bg="rgba(255, 255, 255, 0.72)",
                card_border="rgba(0, 0, 0, 0.06)",
                rank1="#d84a4a",
                rank2="#e8823a",
                rank3="#d8a83a",
                rank_n="#a0a0aa",
                hot="#909098",
            ),
        ),
        cards=CardStyleConfig(glass_blur=8, shadow=1),
    ),
}

#: 预设背景图（文件位于 assets/backgrounds/）
PRESET_BACKGROUNDS: list[dict[str, str]] = [
    {"id": "sakura", "name": "樱色云霞"},
    {"id": "starry", "name": "星夜"},
    {"id": "ocean", "name": "海空"},
    {"id": "dusk", "name": "暮金"},
    {"id": "mint", "name": "薄荷"},
    {"id": "ink", "name": "墨白"},
]
