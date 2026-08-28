"""AI 大模型实时智商（codexradar 分布式雷达）。

数据源：https://deng.codexradar.com（社区众包 benchmark 看板）
接口：api.codexradar.com/api/v1/iq-history，每个模型一条按小时采样的
分数序列，取最新一点即为实时智商（equal-iq v2 口径）。

榜单口径：各家模型本就经由其专属 coding 环境订阅测得（client_contract），
展示时在模型名后标注专属环境（GPT·Codex / GLM·ZCode / DeepSeek·DSH…），
并对同族变体（-preview/-work/-15t 等）去重——每族只保留主档一条，
避免「同一模型两个版本」误导读者。
"""

import json
import time
from pathlib import Path
from typing import Any

import httpx

_IQ_API = "https://api.codexradar.com/api/v1/iq-history?v=20260815-equal-iq-v2"
_SITE = "https://deng.codexradar.com"
_TTL = 30 * 60  # 响应 1MB+，30 分钟磁盘缓存

#: 模型家族 → 专属 coding 环境（标题标注用）
_HARNESS = {
    "gpt": "Codex",
    "claude": "Claude Code",
    "deepseek": "DSH",
    "glm": "ZCode",
    "gemini": "Antigravity",
    "grok": "Grok",
    "kimi": "Kimi Code",
    "k3": "Kimi Code",
    "qwen": "Qwen Code",
}

#: 同族变体后缀：命中其一则归并到基础模型（每族只保留一条）
_VARIANT_SUFFIXES = ("-preview", "-work", "-15t", "-stable", "-latest", "-thinking")

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
    "ultra": "Ultra",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "k3": "Kimi K3",
    "qwen": "Qwen",
    "grok": "Grok",
    "claude": "Claude",
    "gemini": "Gemini",
    "sonnet": "Sonnet",
    "opus": "Opus",
    "haiku": "Haiku",
    "sol": "Sol",
    "terra": "Terra",
    "luna": "Luna",
    "build": "Build",
    "chat": "Chat",
}


def _normalize(model_id: str) -> str:
    """去掉 latest: 前缀与内嵌 harness 前缀（dsh-），返回干净模型 id。"""
    raw = model_id.split("@")[0]
    if raw.lower().startswith("latest:"):
        raw = raw[7:]
    low = raw.lower()
    for pref in ("dsh-",):
        if low.startswith(pref):
            raw = raw[len(pref):]
            break
    return raw


def _pretty(model_id: str) -> str:
    """gpt-5.6-sol → GPT 5.6 Sol；latest:gpt-5.6-sol → GPT 5.6 Sol"""
    parts = _normalize(model_id).split("-")
    out = []
    for p in parts:
        if not p:
            continue
        if p in _BRAND:
            out.append(_BRAND[p])
        elif any(c.isdigit() or c == "." for c in p):
            out.append(p)  # 版本号 5.6 / 4o 原样
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _base_key(model_id: str) -> str:
    """latest:gpt-5.6-sol / gpt-5.5-work → gpt-5.6-sol / gpt-5.5（变体归并键）"""
    mid = _normalize(model_id)
    for suf in _VARIANT_SUFFIXES:
        if mid.endswith(suf):
            return mid[: -len(suf)]
    return mid


def _harness_of(model_id: str) -> str:
    fam = _normalize(model_id).split("-")[0].lower()
    return _HARNESS.get(fam, "")


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


def dedupe_family(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同族变体去重：优先保留与基础 id 完全同名的主档，其次取族内最高分。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(_base_key(r["model"]), []).append(r)
    picked: list[dict[str, Any]] = []
    for _base, group in groups.items():
        if len(group) == 1:
            picked.append(group[0])
            continue
        exact = next(
            (g for g in group if g["model"].split("@")[0] == _base), None
        )
        picked.append(exact or max(group, key=lambda g: g["iq"]))
    picked.sort(key=lambda r: -r["iq"])
    return picked


async def fetch_ai_iq(cache_dir: Path, limit: int = 10) -> list[Any]:
    """实时智商 Top N（同族去重 + 专属环境标注）。返回 HotItem 列表。"""
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

    rows = dedupe_family(rows)
    items = []
    for r in rows[:limit]:
        title = _pretty(r["model"])
        harness = _harness_of(r["model"])
        if harness:
            title = f"{title}（{harness}）"
        items.append(
            HotItem(title=title, hot=int(round(r["iq"])), url=_SITE, alt_url=_SITE)
        )
    if not items:
        raise RuntimeError("codexradar 智商数据为空")
    return items
