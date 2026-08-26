"""DailyHotApi（今日热榜）客户端。

接口约定（https://github.com/imsyy/DailyHotApi）：
GET {base}/{route}?limit=N →
{
  "code": 200, "name": "哔哩哔哩", "subtitle": "热门榜", "total": 50, ...
  "data": [ {"id": "...", "title": "...", "hot": 123, "url": "...",
             "mobileUrl": "...", "desc": "...", "cover": "..."} ]
}
各源字段略有差异（hot/score、cover/pic），此处做容错解析。
"""

import re
from dataclasses import dataclass

import httpx

from nonebot import logger

#: 上游偶发返回的垃圾标题（本地文件名/纯链接/占位文本等）
_JUNK_TITLE_PATTERNS = (
    re.compile(r"^[a-zA-Z]:[\/]"),          # Windows 路径
    re.compile(r"^file://", re.I),
    re.compile(r"^https?://\S+$"),            # 纯链接
    re.compile(r"\.(html?|php|jsp|asp|md|txt)$", re.I),
    re.compile(r"^(本地文件|网页文件|文档|新建文档|untitled|无标题|标题|test)\s*$", re.I),
)


def is_junk_title(title: str) -> bool:
    if len(title.strip()) < 2:
        return True
    return any(p.search(title.strip()) for p in _JUNK_TITLE_PATTERNS)


@dataclass
class HotItem:
    title: str
    hot: int | None = None
    url: str | None = None
    #: 备用链接（url 为主链接时此为另一版本，深读抓原文时兜底重试）
    alt_url: str | None = None


class DailyHotError(Exception):
    pass


def format_hot(hot: int | None) -> str | None:
    """3456789 → '345.6万'；2317230000 → '23.2亿'；45600 → '4.6万'。"""
    if hot is None or hot <= 0:
        return None
    if hot >= 100_000_000:
        v = hot / 100_000_000
        text = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{text}亿"
    if hot >= 10_000:
        v = hot / 10_000
        text = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{text}万"
    return str(hot)


class DailyHotClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch(self, route: str, limit: int = 10) -> list[HotItem]:
        url = f"{self.base_url}/{route.lstrip('/')}"
        params: dict[str, int | str] = {"limit": max(1, min(limit, 50))}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.TimeoutException as e:
            raise DailyHotError(f"请求超时: {url}") from e
        except Exception as e:
            raise DailyHotError(f"请求失败: {url} ({e!r})") from e

        if not isinstance(payload, dict) or payload.get("code") not in (200, None):
            raise DailyHotError(
                f"接口返回异常: {payload.get('code') if isinstance(payload, dict) else type(payload)}"
            )
        data = payload.get("data")
        if not isinstance(data, list):
            raise DailyHotError("接口返回缺少 data 数组")

        items: list[HotItem] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title or is_junk_title(title):
                continue
            hot = raw.get("hot") or raw.get("score") or raw.get("views")
            try:
                hot_val = int(hot) if hot is not None else None
            except (TypeError, ValueError):
                hot_val = None
            pc = raw.get("url")
            mob = raw.get("mobileUrl")
            link = pc or mob  # PC 版页面更利于正文提取
            alt = mob if (mob and link == pc) else pc
            items.append(
                HotItem(
                    title=title,
                    hot=hot_val,
                    url=str(link) if link else None,
                    alt_url=str(alt) if alt else None,
                )
            )
            if len(items) >= limit:
                break
        if not items:
            raise DailyHotError(f"{route} 未解析到任何条目")
        return items


async def check_available(base_url: str) -> bool:
    """探测 DailyHotApi 实例可用性。"""
    try:
        client = DailyHotClient(base_url, timeout=8.0)
        items = await client.fetch("/weibo", limit=1)
        return bool(items)
    except Exception:
        return False
