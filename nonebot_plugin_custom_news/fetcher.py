"""并发抓取全部启用的数据源：磁盘 TTL 缓存 + 失败降级到最近缓存。"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from nonebot import logger

from .sources import BUILTIN_SOURCES, CATEGORY_LABELS, SourceDef
from .sources.dailyhot import DailyHotClient, HotItem
from .store import Store

#: 卡片排序：按分类固定顺序展示
_CATEGORY_ORDER = list(CATEGORY_LABELS.keys())


@dataclass
class CardData:
    source_id: str
    name: str
    emoji: str
    category: str
    items: list[HotItem] = field(default_factory=list)
    stale: bool = False


@dataclass
class Digest:
    cards: list[CardData] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    failed: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.cards)


def _sources_cache_dir(store: Store) -> Path:
    d = store.cache_dir / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_fetch_status(store: Store) -> dict[str, Any]:
    p = store.cache_dir / "fetch_status.json"
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}


def _save_fetch_status(store: Store, status: dict[str, Any]) -> None:
    p = store.cache_dir / "fetch_status.json"
    try:
        p.write_text(json.dumps(status, ensure_ascii=False, indent=2), "utf-8")
    except OSError:
        pass


async def _fetch_one(
    store: Store, sd: SourceDef, limit: int, force_refresh: bool
) -> CardData | None:
    cache_file = _sources_cache_dir(store) / f"{sd.id}.json"
    ttl = store.config.general.cache_ttl
    now = datetime.now()

    cached: dict[str, Any] | None = None
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text("utf-8"))
        except Exception:
            cached = None

    if not force_refresh and cached:
        fetched_at = datetime.fromisoformat(cached.get("fetched_at", "1970-01-01"))
        if (now - fetched_at).total_seconds() < max(ttl, 0):
            items = [HotItem(**i) for i in cached.get("items", [])]
            if items:
                return CardData(
                    sd.id, sd.name, sd.emoji, sd.category, items, stale=False
                )

    status = _load_fetch_status(store)
    try:
        if sd.fetcher == "netease_music":
            from .sources.music import fetch_netease_new

            items = await fetch_netease_new(limit)
        elif sd.fetcher == "qq_music":
            from .sources.music import fetch_qq_new

            items = await fetch_qq_new(limit)
        elif sd.fetcher == "ai_iq":
            from .sources.ai_radar import fetch_ai_iq

            items = await fetch_ai_iq(store.cache_dir, limit)
        elif sd.fetcher == "ai_models":
            from .sources.ai_models import fetch_ai_models

            items = await fetch_ai_models(store, limit)
        else:
            client = DailyHotClient(store.config.general.dailyhot_api_url)
            items = await client.fetch(sd.route, limit)
        cache_file.write_text(
            json.dumps(
                {
                    "fetched_at": now.isoformat(timespec="seconds"),
                    "items": [
                        {
                            "title": i.title,
                            "hot": i.hot,
                            "url": i.url,
                            "alt_url": i.alt_url,
                        }
                        for i in items
                    ],
                },
                ensure_ascii=False,
            ),
            "utf-8",
        )
        status[sd.id] = {
            "last_ok": now.isoformat(timespec="seconds"),
            "items": len(items),
            "last_error": None,
        }
        _save_fetch_status(store, status)
        return CardData(sd.id, sd.name, sd.emoji, sd.category, items, stale=False)
    except Exception as e:
        logger.warning(f"数据源 {sd.name}({sd.route}) 抓取失败: {e}")
        status[sd.id] = {
            "last_ok": status.get(sd.id, {}).get("last_ok"),
            "items": 0,
            "last_error": str(e),
        }
        _save_fetch_status(store, status)
        if cached and cached.get("items"):
            items = [HotItem(**i) for i in cached["items"]]
            return CardData(sd.id, sd.name, sd.emoji, sd.category, items[:limit], stale=True)
        return None


async def fetch_digest(store: Store, force_refresh: bool = False) -> Digest:
    """抓取所有启用源，返回按分类排序的卡片数据。"""
    cfg = store.config
    enabled: list[tuple[SourceDef, int]] = []
    for s in BUILTIN_SOURCES:
        setting = cfg.sources.get(s.id)
        if setting and setting.enabled:
            enabled.append((s, setting.limit))
    for cs in cfg.custom_sources:
        if cs.enabled:
            enabled.append(
                (
                    SourceDef(
                        cs.id, cs.name, cs.route, cs.category, cs.emoji, True, cs.limit
                    ),
                    cs.limit,
                )
            )

    results = await asyncio.gather(
        *(_fetch_one(store, sd, limit, force_refresh) for sd, limit in enabled),
        return_exceptions=True,
    )

    cards: list[CardData] = []
    failed: list[str] = []
    for (sd, _limit), result in zip(enabled, results):
        if isinstance(result, BaseException):
            logger.error(f"数据源 {sd.name} 抓取异常: {result!r}")
            failed.append(sd.name)
        elif result is None:
            failed.append(sd.name)
        elif not result.items:
            pass  # 空数据（如「大模型上新」无新模型时）静默隐藏，不算失败
        else:
            cards.append(result)

    # 分类固定顺序 + 源声明顺序
    cat_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    cards.sort(key=lambda c: (cat_rank.get(c.category, 99), c.source_id))
    return Digest(cards=cards, generated_at=datetime.now(), failed=failed)
