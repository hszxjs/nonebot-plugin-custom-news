"""每日在线壁纸（默认必应每日壁纸，支持自定义直链）。"""

import json
from datetime import datetime
from pathlib import Path

import httpx

from nonebot import logger

BING_API = "https://cn.bing.com/HPImageArchive.aspx"
BING_BASE = "https://cn.bing.com"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class WallpaperError(Exception):
    pass


def _wallpaper_dir(cache_dir: Path) -> Path:
    d = cache_dir / "wallpapers"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def get_daily_wallpaper(cache_dir: Path, custom_url: str = "") -> tuple[Path, str]:
    """获取今日壁纸（带当日磁盘缓存）。

    Returns:
        (图片路径, 版权说明文案)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    wdir = _wallpaper_dir(cache_dir)
    img_path = wdir / f"{today}.jpg"
    meta_path = wdir / f"{today}.json"

    if img_path.exists() and img_path.stat().st_size > 10_000 and meta_path.exists():
        try:
            return img_path, json.loads(meta_path.read_text("utf-8")).get("copyright", "")
        except Exception:
            pass

    async with httpx.AsyncClient(
        timeout=20.0, headers={"User-Agent": _UA}, follow_redirects=True
    ) as client:
        if custom_url:
            image_url, copyright_text = custom_url, "自定义壁纸源"
        else:
            try:
                resp = await client.get(
                    BING_API,
                    params={"format": "js", "idx": 0, "n": 1, "mkt": "zh-CN"},
                )
                resp.raise_for_status()
                images = resp.json().get("images") or []
                if not images:
                    raise WallpaperError("必应接口未返回壁纸")
                urlbase = images[0].get("urlbase", "")
                copyright_text = images[0].get("copyright", "Bing 每日壁纸")
                if not urlbase:
                    raise WallpaperError("必应接口缺少 urlbase")
                image_url = f"{BING_BASE}{urlbase}_UHD.jpg"
            except Exception as e:
                raise WallpaperError(f"获取必应壁纸失败: {e!r}") from e

        try:
            resp = await client.get(image_url)
            resp.raise_for_status()
            data = resp.content
            if len(data) < 10_000:
                raise WallpaperError("壁纸文件过小，疑似下载异常")
            img_path.write_bytes(data)
            meta_path.write_text(
                json.dumps({"date": today, "copyright": copyright_text}, ensure_ascii=False),
                "utf-8",
            )
            logger.debug(f"已下载每日壁纸: {img_path.name} ({len(data) // 1024}KB)")
            return img_path, copyright_text
        except WallpaperError:
            raise
        except Exception as e:
            raise WallpaperError(f"壁纸下载失败: {e!r}") from e
