"""主流大模型上新监控（models.dev 聚合各家官方模型目录）。

原理：models.dev/api.json 汇总各厂商官方模型清单（含 released 发布日期），
与本地基线（已见过的 provider/model 键集合）对比，新出现的键即为「上新」。
- 首次运行只建立基线，不播报（避免一次性轰炸全目录）
- 只播报近 60 天内发布的模型（防目录重构把老模型当新模型）
- 每个模型只播报一次（基线取并集持久化）
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

_API = "https://models.dev/api.json"
_TTL = 30 * 60  # 响应数 MB，30 分钟磁盘缓存
_ANNOUNCE_WINDOW_DAYS = 60

#: 主流厂商的 models.dev provider id（只用官方主 id，跳过 -vertex/-coding-plan 等镜像）
_MAINSTREAM = (
    "openai",
    "anthropic",
    "google",
    "deepseek",
    "zai",
    "zhipuai",
    "moonshotai",
    "minimax",
    "xai",
    "mistral",
    "meta",
    "alibaba",
)


def _load_cache(cache_file: Path) -> Any | None:
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text("utf-8"))
        if time.time() - data.get("ts", 0) < _TTL:
            return data.get("catalog")
    except Exception:
        pass
    return None


def _build_catalog(raw: dict[str, Any]) -> dict[str, dict[str, str]]:
    """provider/model 键 → {provider, name, released}"""
    catalog: dict[str, dict[str, str]] = {}
    for pid in _MAINSTREAM:
        provider = raw.get(pid) or {}
        pname = provider.get("name") or pid.upper()
        for mid, m in (provider.get("models") or {}).items():
            catalog[f"{pid}/{mid}"] = {
                "provider": pname,
                "name": m.get("name") or mid,
                # models.dev 字段为 release_date（部分模型缺省）
                "released": m.get("release_date") or m.get("released") or "",
            }
    return catalog


async def fetch_ai_models(store: Any, limit: int = 10) -> list[Any]:
    """新模型检测。无新模型时返回空列表（卡片整体隐藏）。"""
    from ..fetcher import HotItem

    cache_file = store.cache_dir / "ai_models.json"
    catalog = _load_cache(cache_file)
    if catalog is None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(_API)
            resp.raise_for_status()
            catalog = _build_catalog(resp.json())
        try:
            cache_file.write_text(
                json.dumps({"ts": time.time(), "catalog": catalog}, ensure_ascii=False),
                "utf-8",
            )
        except Exception:
            pass

    baseline_file: Path = store.data_dir / "ai_models_baseline.json"
    try:
        baseline: list[str] = json.loads(baseline_file.read_text("utf-8"))
    except Exception:
        baseline = []
    seen = set(baseline)

    if not seen:
        # 首次运行：只建立基线
        baseline_file.write_text(
            json.dumps(sorted(catalog.keys()), ensure_ascii=False), "utf-8"
        )
        return []

    cutoff = (date.today() - timedelta(days=_ANNOUNCE_WINDOW_DAYS)).isoformat()
    fresh = [
        (key, info)
        for key, info in catalog.items()
        if key not in seen and info["released"] and info["released"] >= cutoff
    ]
    # 无论是否播报，本次见过的都记入基线（并集）
    merged = sorted(seen | set(catalog.keys()))
    baseline_file.write_text(json.dumps(merged, ensure_ascii=False), "utf-8")

    fresh.sort(key=lambda kv: kv[1]["released"], reverse=True)
    items = []
    for _key, info in fresh[:limit]:
        released = info["released"]
        try:
            pretty_date = datetime.strptime(released, "%Y-%m-%d").strftime("%m-%d")
        except ValueError:
            pretty_date = released
        items.append(
            HotItem(
                title=f"{info['provider']} {info['name']} · {pretty_date} 上新",
                hot=0,  # 热度列隐藏（format_hot 对 0 返回 None），日期已并入标题
                url="https://models.dev",
                alt_url="https://models.dev",
            )
        )
    return items
