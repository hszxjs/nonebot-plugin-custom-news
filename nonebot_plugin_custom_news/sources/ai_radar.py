"""AI 大模型实时智商（codexradar 分布式雷达）。

数据源：https://deng.codexradar.com（社区众包 benchmark 看板）
接口：api.codexradar.com/api/v1/iq-history，每个模型一条按小时采样的
分数序列，取最新一点即为实时智商（equal-iq v2 口径）。
"""

import json
import time
from pathlib import Path
from typing import Any

import httpx

_IQ_API = "https://api.codexradar.com/api/v1/iq-history?v=20260815-equal-iq-v2"
_SITE = "https://deng.codexradar.com"
_TTL = 30 * 60  # 响应 1MB+，30 分钟磁盘缓存

#: 模型 id 分词 → 品牌写法（其余词首字母大写）
_BRAND = {
    "gpt": "GPT",
    "glm": "GLM",
    "ai": "AI",
    "x": "X",
    "o": "o",
    "v": "V",
    "r": "R",
    "se": "SE",
    "pro": "Pro",
    "flash": "Flash",
    "max": "Max",
    "mini": "Mini",
    "nano": "Nano",
    "thinking": "Thinking",
    "ultra": "Ultra",
}


def _pretty(model_id: str) -> str:
    """gpt-5.6-sol → GPT 5.6 Sol"""
    parts = model_id.split("@")[0].split("-")
    out = []
    for p in parts:
        if not p:
            continue
        if any(c.isdigit() or c == "." for c in p):
            out.append(p)  # 版本号 5.6 / 4o 原样
        else:
            out.append(_BRAND.get(p, p.capitalize()))
    return " ".join(out)


def _load_cache(cache_file: Path) -> Any | None:
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text("utf-8"))
        if time.time() - data.get("ts", 0) < _TTL:
            return data.get("items")
    except Exception:
        pass
    return None


async def fetch_ai_iq(cache_dir: Path, limit: int = 10) -> list[Any]:
    """实时智商 Top N。返回 HotItem 列表（延迟导入避免循环依赖）。"""
    from ..fetcher import HotItem

    cache_file = cache_dir / "ai_iq.json"
    cached = _load_cache(cache_file)
    if cached is not None:
        rows = cached
    else:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(_IQ_API)
            resp.raise_for_status()
            series_map = resp.json()
        rows = []
        for model, series in series_map.items():
            # 带 @low/@high 等推理档位后缀的是变体，只取主档
            if "@" in model or not isinstance(series, list) or not series:
                continue
            score = series[-1].get("score")
            if isinstance(score, (int, float)) and score > 0:
                rows.append({"model": model, "iq": float(score)})
        rows.sort(key=lambda r: -r["iq"])
        try:
            cache_file.write_text(
                json.dumps({"ts": time.time(), "items": rows}, ensure_ascii=False),
                "utf-8",
            )
        except Exception:
            pass

    items = [
        HotItem(
            title=_pretty(r["model"]),
            hot=int(round(r["iq"])),
            url=_SITE,
            alt_url=_SITE,
        )
        for r in rows[:limit]
    ]
    if not items:
        raise RuntimeError("codexradar 智商数据为空")
    return items
