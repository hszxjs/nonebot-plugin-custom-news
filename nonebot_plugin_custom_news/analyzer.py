"""新闻深读：挑选新闻 → 抓原文 → LLM 解析 → 结构化结果。"""

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from nonebot import logger

from .fetcher import Digest
from .sources.article import fetch_article
from .store import Store

#: 参与深读挑选的卡片分类，按正文可得性排序（新闻页有正文，社交页多为视频/问答无正文）
_ANALYSIS_CATEGORY_PRIORITY = {"news": 0, "global": 1, "social": 2}

#: 内置深读 system prompt（通用风格）；人设/口吻请用配置项 llm_style_prompt 追加
_SYSTEM_PROMPT = (
    "你是一位资深新闻编辑，擅长把新闻原文提炼为客观、结构化的深度解读。"
    "只依据提供的原文内容分析，不编造事实，原文未提及的信息标注「原文未提及」。"
    "输出严格为 JSON（不要 markdown 代码块），字段："
    '{"event": "一句话事件概括(<=30字)", "background": "事件背景(80-140字)", '
    '"points": ["关键要点1", "关键要点2", "关键要点3"], '
    '"impact": "可能的影响(60-120字)", "remark": "一句话锐评(<=30字)"}。'
    "全部使用简体中文。"
)

#: 每条新闻轮换一种腔调，避免同一批深读读起来一个样（配置项 llm_style_prompt 可覆盖人设）
_STYLE_DICE = (
    "说书人腔：像在鱼塘边给群友讲古，把前因后果慢慢抖出来",
    "冷幽默腔：一本正经地点出最荒诞的地方，自己先不笑",
    "嘴替腔：替群友把心里那口吐槽先说了，再补正经分析",
    "拆解腔：当成拆机现场，一层层把门道扒开给群友看",
    "预言腔：重心放在「接下来会怎样」，敢下判断并讲清条件",
    "外行腔：用刚上岸的视角，把门槛高的事讲成大白话",
    "复盘腔：把这事当成一局打完的牌，讲清谁在哪个节点走错了",
    "短评腔：惜字如金，每句都往要害上砸",
)

#: 生成温度（太低会让每条深读都念同一套，推理模型尤其明显）
_TEMPERATURE = 0.85

#: 深读原文预算：超长文取「开头 + 结尾」，中段省略。
#: 控制输入 token 的同时提高前缀缓存命中占比（system 段可命中，原文是不可命中部分）。
_ANALYSIS_HEAD_CHARS = 2400
_ANALYSIS_TAIL_CHARS = 1000
_ELISION_MARK = "\n……（原文中段省略）……\n"

#: 最近一次深读调用的缓存用量（run_analysis 汇总落盘）。
_last_usage: dict[str, int] = {}


def _trim_for_analysis(text: str, budget: int | None = None) -> str:
    """把原文裁到分析预算内：短文原样，超长文保留开头与结尾（结论通常在尾段）。

    预算与 prompt 缓存命中率直接相关：可命中前缀只有 system 提示那段，
    正文越长分母越大。默认 2000 字符，可在 WebUI「设置」页用
    analysis_article_chars 调整（越大越详实、命中率与费用越差）。
    """
    total = int(budget or _ANALYSIS_HEAD_CHARS + _ANALYSIS_TAIL_CHARS)
    head = int(total * 0.68)
    tail = max(200, total - head)
    if len(text) <= head + tail:
        return text
    return text[:head] + _ELISION_MARK + text[-tail:]


def _system_prompt(general: Any) -> str:
    """内置 prompt + 用户自定义风格（配置项 llm_style_prompt）。

    自定义部分整段追加在内置规则之后：规则（只依据原文、JSON 字段）不可被覆盖，
    但口吻、人称、禁用词、切入角度都可以按频道口味改。
    """
    style = str(getattr(general, "llm_style_prompt", "") or "").strip()
    if not style:
        return _SYSTEM_PROMPT
    return f"{_SYSTEM_PROMPT}\n\n【本频道风格要求】\n{style}"


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
    cards = [c for c in digest.cards if c.category in _ANALYSIS_CATEGORY_PRIORITY and c.items]
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
                picked.append((card.name, card.emoji, item.title, item.url, item.alt_url))
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
    data["points"] = (
        [str(p).strip() for p in points if str(p).strip()][:4] if isinstance(points, list) else []
    )
    return data


def _chat_completions_url(base_url: str) -> str:
    """归一化 Base URL：兼容填到 /v1 或直接填完整 /chat/completions 端点两种习惯。"""
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _record_usage(usage: dict[str, Any]) -> None:
    """记录本次调用的前缀缓存命中/未命中（DeepSeek 的 prompt_cache_* 字段）。"""
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    prompt = int(usage.get("prompt_tokens") or (hit + miss))
    _last_usage.clear()
    _last_usage.update(
        hit=hit,
        miss=miss,
        prompt=prompt,
        completion=int(usage.get("completion_tokens") or 0),
    )
    if prompt:
        logger.info(
            f"深读 LLM 用量：prompt={prompt} 缓存命中={hit} 未命中={miss}（命中率 {hit / prompt:.0%}）"
        )


async def _chat(general: Any, user_prompt: str, style: str | None = None) -> str:
    """单次深读调用。

    system 段必须字节级稳定（内置规则 + 频道风格，不放任何按条变化的变量）：
    服务端前缀缓存按「从头开始的公共前缀」命中，把腔调这类变量放进 system 会让
    其后的内容全部算未命中。按条轮换的腔调因此挂在 user 段开头。
    """
    url = _chat_completions_url(general.llm_base_url)
    headers = {"Authorization": f"Bearer {general.llm_api_key.strip()}"}
    # 缓存要点：DeepSeek 等按「前缀完全一致」命中 prompt 缓存。
    # 腔调原本拼在 system 末尾，导致每条新闻的 system 前缀都不同、缓存几乎全失效
    # （实测命中率仅 29%）。把变量挪到 user 消息后，system 整段恒定，
    # 可命中的前缀直接覆盖整段 system（含人设与规则）。
    system_content = _system_prompt(general)
    user_content = user_prompt
    if style:
        user_content = f"【本条腔调】{style}（只影响措辞和切入角度，事实与规矩不变）\n\n{user_prompt}"
    payload = {
        "model": general.llm_model,
        "temperature": _TEMPERATURE,
        # 思考型模型（deepseek-flash 等）默认先把预算烧在 reasoning 上：深读是
        # 改写/结构化任务，思考链无价值却会成倍放大输出 tokens，默认关闭。
        # 端点不认识该参数（400）时下方自动去参重试。
        "thinking": {"type": "disabled"},
        # 上限而非计费：部分推理模型思考过程也计入，
        # 预算不足会截断正文导致 JSON 不完整（默认 8000）
        "max_tokens": int(getattr(general, "llm_max_tokens", 8000) or 8000),
        # 强制 JSON 输出，根治 GLM 系模型偶发的代码围栏/引号漂移；
        # 部分端点/模型不支持该参数（400），下方自动去参重试
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
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
            if resp.status_code == 400 and "thinking" in payload:
                # 端点/模型不认识 thinking：去掉参数重试（不再视为错误）
                payload.pop("thinking")
                logger.info("LLM 端点不支持 thinking 参数（400），去参重试")
                continue
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
                    last_error = RuntimeError(f"API 限流/服务波动({resp.status_code})，重试中")
                    continue
                raise RuntimeError(
                    f"API 限流/服务波动({resp.status_code}): {err_msg or '请稍后再试'}"
                )
            resp.raise_for_status()
            data = resp.json()
            _record_usage(data.get("usage") or {})
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
    dice = list(_STYLE_DICE)
    random.shuffle(dice)
    usage_totals = {"calls": 0, "hit": 0, "miss": 0, "prompt": 0}
    for idx, cand in enumerate(candidates):
        if len(results) >= n:
            break
        style = dice[idx % len(dice)]
        # 条目间隔，缓解免费档模型限流
        if idx and not mock_mode:
            import asyncio

            await asyncio.sleep(2.5)
        ana = Analysis(source_name=cand[0], emoji=cand[1], title=cand[2], url=cand[3])
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
                    logger.info(f"深读跳过（无正文）: [{cand[0]}] {cand[2][:24]}")
                    continue
                ana.article_chars = len(article)
                content = await _chat(
                    general,
                    f"新闻标题：{cand[2]}\n\n新闻原文：\n"
                    f"{_trim_for_analysis(article, getattr(general, 'analysis_article_chars', 2000))}",
                    style=style,
                )
                usage_totals["calls"] += 1
                for key in ("hit", "miss", "prompt"):
                    usage_totals[key] += _last_usage.get(key, 0)
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
    if usage_totals["calls"]:
        _flush_usage_stats(store, usage_totals)
    if not results and candidates:
        raise RuntimeError(f"全部候选解析失败（{len(candidates)} 个）：{last_error}")
    return results


def _flush_usage_stats(store: Store, totals: dict[str, int]) -> None:
    """把本轮深读的缓存用量并入当日统计（cache/llm_cache_stats.json，保留最近 30 天）。"""
    path = store.cache_dir / "llm_cache_stats.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    day = time.strftime("%Y-%m-%d")
    rec = data.get(day) or {}
    merged = {
        "calls": int(rec.get("calls") or 0) + int(totals.get("calls") or 0),
        "hit": int(rec.get("hit") or 0) + int(totals.get("hit") or 0),
        "miss": int(rec.get("miss") or 0) + int(totals.get("miss") or 0),
        "prompt": int(rec.get("prompt") or 0) + int(totals.get("prompt") or 0),
    }
    data = {**{k: v for k, v in data.items() if k != day}, day: merged}
    for old in sorted(data)[:-30]:
        data.pop(old, None)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return
    logger.info(
        f"深读缓存用量（今日 {merged['calls']} 次调用）："
        f"命中 {merged['hit']} / 未命中 {merged['miss']}"
        f"（命中率 {merged['hit'] / max(1, merged['prompt']):.0%}）"
    )
