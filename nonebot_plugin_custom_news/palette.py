"""从背景图提取主题调色板（auto 模式）。

使用 colorthief 提取主色与候选色，再按 HSL 调和生成一整套配色，
并用 WCAG 对比度公式保证文字可读。
"""

import colorsys
from pathlib import Path

from colorthief import ColorThief
from PIL import Image

from .theme import PaletteColors

# ---------------------------------------------------------------- 色彩工具


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        round(_clamp(r, 0, 255)), round(_clamp(g, 0, 255)), round(_clamp(b, 0, 255))
    )


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h, s, l


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(_clamp(h), _clamp(l), _clamp(s))
    return round(r * 255), round(g * 255), round(b * 255)


def relative_luminance(r: int, g: int, b: int) -> float:
    def chan(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1 = relative_luminance(*rgb1)
    l2 = relative_luminance(*rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def ensure_contrast(
    fg_hex: str, bg_rgb: tuple[int, int, int], min_ratio: float = 4.5
) -> str:
    """在保持色相的前提下调整亮度，直到前景与背景对比度达标。"""
    r, g, b = hex_to_rgb(fg_hex)
    h, s, l = rgb_to_hsl(r, g, b)
    bg_lum = relative_luminance(*bg_rgb)
    # 背景偏亮则压暗前景，偏暗则提亮前景
    direction = -1 if bg_lum > 0.35 else 1
    for _ in range(60):
        if contrast_ratio((r, g, b), bg_rgb) >= min_ratio:
            break
        l = _clamp(l + direction * 0.02)
        r, g, b = hsl_to_rgb(h, s, l)
    return _rgb_to_hex(r, g, b)


def _mix(
    c1: tuple[int, int, int], c2: tuple[int, int, int], w2: float
) -> tuple[int, int, int]:
    w1 = 1 - w2
    return (
        round(c1[0] * w1 + c2[0] * w2),
        round(c1[1] * w1 + c2[1] * w2),
        round(c1[2] * w1 + c2[2] * w2),
    )


# ---------------------------------------------------------------- 主提取逻辑


def _composited_thumb(
    image_path: str | Path, overlay_mode: str, alpha: float
) -> "Image.Image":
    """生成叠加了遮罩的小尺寸副本，供取色与亮度统计使用。"""
    overlay_rgb = (255, 255, 255) if overlay_mode == "light" else (12, 14, 24)
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((420, 420))
    if alpha > 0.01:
        overlay = Image.new("RGB", img.size, overlay_rgb)
        img = Image.blend(img, overlay, alpha)
    return img


def _is_vivid(rgb: tuple[int, int, int]) -> bool:
    _, s, _ = rgb_to_hsl(*rgb)
    return s > 0.28


def extract_palette(
    image_path: str | Path,
    *,
    overlay_mode: str = "light",
    overlay_opacity: float = 0.35,
) -> PaletteColors:
    """从背景图（叠加遮罩后的等效效果）生成一整套配色（auto 模式）。

    遮罩会显著改变感知明暗：浅色遮罩提亮、深色遮罩压暗，
    因此先在 PIL 中合成遮罩，再以平均亮度判断深浅基调、提取主色。
    """
    effective_alpha = min(0.9, max(0.0, overlay_opacity)) * 0.8  # 渐变遮罩的平均等效值
    thumb = _composited_thumb(image_path, overlay_mode, effective_alpha)

    import io

    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    ct = ColorThief(buf)
    dominant = tuple(ct.get_color(quality=8))
    try:
        candidates = [tuple(c) for c in ct.get_palette(color_count=6, quality=8)]
    except Exception:
        candidates = []
    all_colors = [dominant, *candidates]

    # 深浅基调：用合成遮罩后的平均色判断（比主色单点更符合整体观感）。
    # WCAG 亮度对绿色权重过高（粉色被低估），因此直接用对比度判据：
    # 黑字对比度更高 → 浅色背景；白字对比度更高 → 深色背景
    from PIL import ImageStat

    stat = ImageStat.Stat(thumb)
    mean_rgb = (round(stat.mean[0]), round(stat.mean[1]), round(stat.mean[2]))
    is_light_bg = (
        contrast_ratio((0, 0, 0), mean_rgb) > contrast_ratio((255, 255, 255), mean_rgb)
    )

    # 主色：优先挑选饱和鲜艳的候选色（跳过接近纯黑/纯白的噪点色）
    vivid = [
        c
        for c in all_colors
        if _is_vivid(c) and 0.12 < relative_luminance(*c) < 0.92
    ]
    vivid.sort(
        key=lambda c: rgb_to_hsl(*c)[1] * (1.1 - abs(relative_luminance(*c) - 0.5)),
        reverse=True,
    )
    primary_rgb = vivid[0] if vivid else _mix(dominant, (128, 128, 138), 0.4)

    # 强调色：取第二个鲜艳色；若无或色相太接近则做色相旋转
    ph, ps, pl = rgb_to_hsl(*primary_rgb)
    if len(vivid) > 1:
        accent_rgb = vivid[1]
        ah, _, _ = rgb_to_hsl(*accent_rgb)
        if min(abs(ah - ph), 1 - abs(ah - ph)) < 0.12:
            accent_rgb = hsl_to_rgb(ph + 0.42, ps, _clamp(0.62 - 0.1 if is_light_bg else 0.68))
    else:
        accent_rgb = hsl_to_rgb(ph + 0.42, ps, 0.60 if is_light_bg else 0.68)

    # 按背景明暗决定文字基调（混入少量主色保持和谐）
    if is_light_bg:
        base_text = _mix((38, 38, 48), primary_rgb, 0.10)
        base_sub = _mix((96, 98, 112), primary_rgb, 0.10)
        card_bg = "rgba(255, 255, 255, 0.55)"
        card_border = "rgba(255, 255, 255, 0.70)"
        card_solid = _mix(dominant, (255, 255, 255), 0.62)
    else:
        base_text = _mix((242, 244, 250), primary_rgb, 0.10)
        base_sub = _mix((178, 184, 208), primary_rgb, 0.10)
        card_bg = "rgba(26, 30, 46, 0.45)"
        card_border = "rgba(255, 255, 255, 0.16)"
        card_solid = _mix(dominant, (20, 22, 34), 0.66)

    # 保证文字与卡片实际底色对比度
    text_hex = ensure_contrast(_rgb_to_hex(*base_text), card_solid, 7.0)
    sub_hex = ensure_contrast(_rgb_to_hex(*base_sub), card_solid, 4.6)

    # 榜单前三配色：由主色派生的暖色渐进；普通名次与热度用灰（同样保证可读）
    rank1 = hsl_to_rgb(ph, _clamp(ps + 0.15), 0.52 if is_light_bg else 0.62)
    rank2 = hsl_to_rgb(ph - 0.07, _clamp(ps + 0.10), 0.56 if is_light_bg else 0.66)
    rank3 = hsl_to_rgb(ph - 0.14, _clamp(ps + 0.05), 0.62 if is_light_bg else 0.72)
    rank1 = _ensure_vis((rank1, card_solid))
    rank2 = _ensure_vis((rank2, card_solid))
    rank3 = _ensure_vis((rank3, card_solid))

    if is_light_bg:
        rank_n_rgb = _mix((120, 126, 142), primary_rgb, 0.12)
        hot_rgb = _mix((108, 114, 132), primary_rgb, 0.10)
    else:
        rank_n_rgb = (158, 164, 190)
        hot_rgb = (168, 174, 200)
    rank_n_hex = ensure_contrast(_rgb_to_hex(*rank_n_rgb), card_solid, 3.2)
    hot_hex = ensure_contrast(_rgb_to_hex(*hot_rgb), card_solid, 3.2)

    return PaletteColors(
        primary=_rgb_to_hex(*primary_rgb),
        accent=_rgb_to_hex(*accent_rgb),
        text=text_hex,
        subtext=sub_hex,
        card_bg=card_bg,
        card_border=card_border,
        rank1=_rgb_to_hex(*rank1),
        rank2=_rgb_to_hex(*rank2),
        rank3=_rgb_to_hex(*rank3),
        rank_n=rank_n_hex,
        hot=hot_hex,
    )


def _ensure_vis(pair: tuple[tuple[int, int, int], tuple[int, int, int]]):
    fg, bg = pair
    if contrast_ratio(fg, bg) < 2.4:
        h, s, l = rgb_to_hsl(*fg)
        bg_lum = relative_luminance(*bg)
        l = _clamp(l - 0.12 if bg_lum > 0.35 else l + 0.12)
        return hsl_to_rgb(h, s, l)
    return fg
