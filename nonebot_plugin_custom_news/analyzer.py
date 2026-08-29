"""新闻深读：挑选新闻 → 抓原文 → LLM 解析 → 结构化结果。"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from nonebot import logger

from .fetcher import Digest
from .sources.article import fetch_article
from .store import Store

#: 参与深读挑选的卡片分类，按正文可得性排序（新闻页有正文，社交页多为视频/问答无正文）
_ANALYSIS_CATEGORY_PRIORITY = {"news": 0, "global": 1, "social": 2}

_SYSTEM_PROMPT = (
    "你是一位资深新闻编辑，擅长把新闻原文提炼为客观、结构化的深度解读。"
    "只依据提供的原文内容分析，不编造事实，原文未提及的信息标注「原文未提及」。"
    "输出严格为 JSON（不要 markdown 代码块），字段："
    '{"event": "一句话事件概括(<=30字)", "background": "事件背景(80-140字)", '
    '"points": ["关键要点1", "关键要点2", "关键要点3"], '
    '"impact": "可能的影响(60-120字)", "remark": "一句话锐评(<=30字)"}。'
    "全部使用简体中文。"
)


@dataclass
class Analysis:
    source_name: str
    emoji: str
    title: str
    url: str | None
    event: str = ""
    background: str = ""
    points: list[str] = field(default_factory=list)
    impact: str = ""
    remark: str = ""
    article_chars: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.error


def llm_ready(general: Any) -> bool:
    return bool(general.llm_api_key.strip())


def pick_candidates(
    digest: Digest, count: int
) -> list[tuple[str, str, str, str | None, str | None]]:
    """构建候选池：新闻类源优先，跨源轮询保证多样性。

    Returns: [(source_name, emoji, title, url, alt_url), ...]
    """
    cards = [
        c
        for c in digest.cards
        if c.category in _ANALYSIS_CATEGORY_PRIORITY and c.items
    ]
    cards.sort(key=lambda c: _ANALYSIS_CATEGORY_PRIORITY[c.category])

    picked: list[tuple[str, str, str, str | None, str | None]] = []
    round_idx = 0
    while len(picked) < count and round_idx < 4:
        progressed = False
        for card in cards:
            if len(picked) >= count:
                break
            if round_idx < len(card.items):
                item = card.items[round_idx]
                picked.append(
                    (card.name, card.emoji, item.title, item.url, item.alt_url)
                )
                progressed = True
        if not progressed:
            break
        round_idx += 1
    return picked


def _mock_analysis(title: str) -> dict[str, Any]:
    return {
        "event": "示例事件：这是演示数据",
        "background": (
            "当前尚未配置大模型接口，此条为样式演示内容。配置 LLM 后，"
            "这里将基于新闻原文生成真实的事件背景介绍，帮助读者快速理解来龙去脉。"
        ),
        "points": [
            "演示要点一：插件会自动抓取新闻原文并交给大模型解析",
            "演示要点二：解读基于正文而非标题，避免断章取义",
            "演示要点三：解析结果以聊天记录样式图片推送",
        ],
        "impact": "演示影响：配置 LLM 接口后即可获得真实的深度解读内容。",
        "remark": "去设置页填上 API Key 即可解锁 ✨",
    }


def _parse_llm_json(content: str) -> dict[str, Any]:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM 未返回 JSON")
    data = json.loads(content[start : end + 1])
    for key in ("event", "background", "impact", "remark"):
        data[key] = str(data.get(key) or "").strip()
    points = data.get("points")
    data["points"] = [str(p).strip() for p in points if str(p).strip()][:4] if isinstance(points, list) else []
    return data


def _chat_completions_url(base_url: str) -> str:
    """归一化 Base URL：兼容填到 /v1 或直接填完整 /chat/completions 端点两种习惯。"""
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


async def _chat(general: Any, user_prompt: str) -> str:
    url = _chat_completions_url(general.llm_base_url)
    headers = {"Authorization": f"Bearer {general.llm_api_key.strip()}"}
    payload = {
        "model": general.llm_model,
        "temperature": 0.3,
        # 上限而非计费：推理模型（GLM/DeepSeek-R1 等）思考过程也计入，
        # 预算不足会截断正文导致 JSON 不完整（默认 8000）
        "max_tokens": int(getattr(general, "llm_max_tokens", 8000) or 8000),
        # 强制 JSON 输出，根治 GLM 系模型偶发的代码围栏/引号漂移；
        # 部分端点/模型不支持该参数（400），下方自动去参重试
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    import asyncio

    # 429/5xx 指数退避重试（免费档模型限流较严）
    backoffs = (0, 6, 14)
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt, wait in enumerate(backoffs):
            if wait:
                await asyncio.sleep(wait)
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 400 and "response_format" in payload:
                # 端点/模型不支持 json_object 模式：去掉参数重试（不再视为错误）
                payload.pop("response_format")
                logger.info("LLM 端点不支持 response_format（400），回退普通模式重试")
                continue
            if resp.status_code == 404:
                raise RuntimeError(
                    f"接口 404，请检查 Base URL（当前: {url}；"
                    "通常填到 .../v1 这一级即可，无需包含 /chat/completions）"
                )
            if resp.status_code in (429, 500, 502, 503, 504):
                # 透传服务商返回的具体原因（如 1113 余额不足，重试无意义）
                try:
                    err_msg = resp.json().get("error", {}).get("message", "")
                except Exception:
                    err_msg = ""
                if err_msg and "balance" in err_msg.lower():
                    raise RuntimeError(f"LLM 接口拒绝: {err_msg}")
                if attempt < len(backoffs) - 1:
                    last_error = RuntimeError(
                        f"API 限流/服务波动({resp.status_code})，重试中"
                    )
                    continue
                raise RuntimeError(
                    f"API 限流/服务波动({resp.status_code}): {err_msg or '请稍后再试'}"
                )
            resp.raise_for_status()
            data = resp.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if not content:
                # 兼容推理模型把内容放在 reasoning_content 的返回结构
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get(
                    "reasoning_content"
                )
            if not content:
                raise RuntimeError(f"模型返回为空: {str(data)[:200]}")
            return content
    raise last_error or RuntimeError("LLM 请求失败")


async def run_analysis(store: Store, count: int | None = None) -> list[Analysis]:
    """完整深读流程：取缓存数据 → 挑选 → 抓原文 → LLM 解析。"""
    from .fetcher import fetch_digest

    general = store.config.general
    n = max(1, min(count or general.analysis_count, 6))
    digest = await fetch_digest(store)
    # 备选池放大 3 倍：抖音/知乎等链接抓不到正文时自动跳到下一个候选
    candidates = pick_candidates(digest, count=n * 3)
    if not candidates:
        return []

    mock_mode = general.llm_api_key.strip().lower().startswith("mock")
    results: list[Analysis] = []
    last_error = "无可用正文或全部调用失败"
    for idx, cand in enumerate(candidates):
        if len(results) >= n:
            break
        # 条目间隔，缓解免费档模型限流
        if idx and not mock_mode:
            import asyncio

            await asyncio.sleep(2.5)
        ana = Analysis(
            source_name=cand[0], emoji=cand[1], title=cand[2], url=cand[3]
        )
        try:
            if mock_mode:
                data = _mock_analysis(cand[2])
                ana.article_chars = 1200
            else:
                # 双链接重试：PC 版失败换移动版
                article = None
                for link in (cand[3], cand[4] if len(cand) > 4 else None):
                    if not link:
                        continue
                    article = await fetch_article(link)
                    if article:
                        break
                if not article:
                    logger.info(
                        f"深读跳过（无正文）: [{cand[0]}] {cand[2][:24]}"
                    )
                    continue
                ana.article_chars = len(article)
                content = await _chat(
                    general, f"新闻标题：{cand[2]}\n\n新闻原文：\n{article}"
                )
                data = _parse_llm_json(content)
            ana.event = data.get("event", "")
            ana.background = data.get("background", "")
            ana.points = data.get("points", [])
            ana.impact = data.get("impact", "")
            ana.remark = data.get("remark", "")
            if not (ana.background or ana.points):
                logger.info(f"深读跳过（解析为空）: {cand[2][:24]}")
                continue
        except Exception as e:
            last_error = str(e)
            logger.warning(f"新闻深读失败 [{cand[2][:20]}]: {e!r}")
            continue
        results.append(ana)
    if not results and candidates:
        raise RuntimeError(f"全部候选解析失败（{len(candidates)} 个）：{last_error}")
    return results
