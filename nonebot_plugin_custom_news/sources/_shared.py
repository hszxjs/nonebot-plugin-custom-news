"""sources 包内的公用小工具：TTL 缓存、UA、文本截断。

这些逻辑原先在多个源里各写一遍（缓存 3 套 schema、同一 UA 写 4 处、
截断函数逐字节重复），改一处口径就要改多处，漏一处就是「一个入口正常、
另一个静默空榜」。统一到本模块。

放在 sources 包内而非顶层，是为了让源模块只往下依赖，不反向 import 上层。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nonebot import logger

#: 抓取用 UA（iPhone Safari：社交/新闻站点对移动端更宽容）
UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

#: 统一的磁盘缓存格式：{"ts": <epoch 秒 float>, "<key>": <payload>}
_CACHE_TS_KEY = "ts"


def load_ttl_cache(cache_file: Path, ttl: float, key: str = "items") -> Any | None:
    """读 TTL 缓存：过期 / 损坏 / 缺失一律返回 None（由调用方回源）。"""
    if key == _CACHE_TS_KEY:
        raise ValueError("缓存键不能叫 ts")
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text("utf-8"))
    except Exception as e:
        logger.debug(f"缓存读取失败（按未命中处理）{cache_file.name}: {e!r}")
        return None
    if not isinstance(data, dict):
        # 合法 JSON 但根不是对象（列表/字符串/数字）：旧实现在这里抛 AttributeError，
        # 且因发生在请求之前，会让该源「永久失败」直到有人手动删缓存
        logger.debug(f"缓存 {cache_file.name} 结构不是对象，按未命中处理")
        return None
    try:
        age = time.time() - float(data.get(_CACHE_TS_KEY) or 0)
    except (TypeError, ValueError):
        return None
    if age >= ttl:
        return None
    return data.get(key)


def save_ttl_cache(cache_file: Path, payload: Any, key: str = "items") -> None:
    """写 TTL 缓存。失败只告警不影响本次结果，但必须可见（原先静默 pass）。"""
    if key == _CACHE_TS_KEY:
        raise ValueError("缓存键不能叫 ts")
    try:
        cache_file.write_text(
            json.dumps({_CACHE_TS_KEY: time.time(), key: payload}, ensure_ascii=False),
            "utf-8",
        )
    except Exception as e:
        logger.warning(f"缓存写入失败（不影响本次结果）{cache_file.name}: {e!r}")


def truncate(text: str, n: int) -> str:
    """按字符数截断并加省略号。"""
    return text if len(text) <= n else text[: n - 1] + "…"
