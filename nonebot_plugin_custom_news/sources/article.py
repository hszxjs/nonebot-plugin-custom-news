"""新闻原文抓取与正文提取（trafilatura）。"""

import trafilatura
from httpx import AsyncClient
from nonebot import logger

from ._shared import UA_IPHONE as _UA

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 6000


def is_public_http_url(url: str) -> bool:
    """是否 http/https 且解析到的**所有**地址都是公网 IP。

    新闻条目 URL 来自上游聚合接口（非本插件可控），原先直接 GET：
    可被指向 http://127.0.0.1:6688、NapCat 的本地口，云上还能打到
    169.254.169.254 元数据；抓到什么就交给 LLM 摘要画进图推给所有群，
    盲 SSRF 会升级成可读外泄。这里拒绝私网/回环/链路本地/保留地址。
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url or "")
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def fetch_article(url: str) -> str | None:
    """抓取新闻页面并提取正文，失败返回 None。"""
    if not is_public_http_url(url):
        logger.warning(f"跳过非公网地址的正文抓取（SSRF 防护）: {url!r}")
        return None
    try:
        async with AsyncClient(
            timeout=15.0,
            headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            # 重定向后也要复核：否则可用公网地址 302 到内网绕过前置校验
            if not is_public_http_url(str(resp.url)):
                logger.warning(f"重定向到非公网地址，放弃抓取: {resp.url!r}")
                return None
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
