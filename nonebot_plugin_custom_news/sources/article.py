"""新闻原文抓取与正文提取（trafilatura）。"""

import trafilatura
from httpx import AsyncClient

from nonebot import logger

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 6000


async def fetch_article(url: str) -> str | None:
    """抓取新闻页面并提取正文，失败返回 None。"""
    try:
        async with AsyncClient(
            timeout=15.0,
            headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            if len(resp.content) > MAX_HTML_BYTES:
                return None
            html = resp.text
    except Exception as e:
        logger.debug(f"原文抓取失败 {url}: {e!r}")
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    if not text:
        return None
    text = text.strip()
    if len(text) < 120:  # 正文过短，可能是导航页/视频页
        return None
    return text[:MAX_TEXT_CHARS]
