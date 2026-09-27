"""主动推送：遍历推送目标，逐个发送日报图（跨适配器）。"""

import asyncio
import json
from datetime import datetime

from nonebot import get_bots, logger
from nonebot_plugin_alconna import Target, UniMessage

from .store import PushTargetItem, Store


def target_key(data: dict) -> str:
    """推送目标去重键。"""
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def make_label(target: Target) -> str:
    try:
        platform = getattr(target, "platform", "") or "unknown"
        tid = getattr(target, "id", "") or ""
        return f"{platform}:{tid}" if tid else platform
    except Exception:
        return "未知目标"


async def add_target(store: Store, target: Target) -> tuple[bool, str]:
    """订阅当前会话。返回 (是否新增, 标签)。"""
    data = target.dump()
    key = target_key(data)
    label = make_label(target)
    for item in store.config.push_targets:
        if target_key(item.target) == key:
            if not item.enabled:
                item.enabled = True
                await store.save()
            return False, label
    store.config.push_targets.append(
        PushTargetItem(
            id=key[:32],
            label=label,
            enabled=True,
            target=data,
            added_at=datetime.now().isoformat(timespec="seconds"),
        )
    )
    await store.save()
    return True, label


async def remove_target(store: Store, target: Target) -> tuple[bool, str]:
    """退订当前会话。返回 (是否移除, 标签)。"""
    data = target.dump()
    key = target_key(data)
    label = make_label(target)
    before = len(store.config.push_targets)
    store.config.push_targets = [
        t for t in store.config.push_targets if target_key(t.target) != key
    ]
    if len(store.config.push_targets) != before:
        await store.save()
        return True, label
    return False, label


async def _send_with_retry(
    make_coro, *, label: str, attempts: int = 2, backoff: float = 2.0
) -> None:
    """发送失败重试一次：单次抖动（网络/风控）不该直接丢掉一条推送。

    每个目标此前只试一次，一次抖动就永久丢一条日报，且失败目标只在日志里出现。
    """
    for i in range(attempts):
        try:
            await make_coro()
            return
        except Exception:
            if i == attempts - 1:
                raise
            logger.warning(f"推送目标「{label}」第 {i + 1} 次失败，{backoff:g}s 后重试")
            await asyncio.sleep(backoff)


async def push_image_to_all(store: Store, image: bytes) -> dict:
    """向全部启用的推送目标发送图片。"""
    targets = [t for t in store.config.push_targets if t.enabled]
    if not targets:
        logger.warning("没有启用的推送目标，跳过推送")
        return {"ok": 0, "fail": [], "total": 0}

    ok, fails = 0, []
    for item in targets:
        sent, last_err = False, None
        try:
            target = Target.load(item.target)
        except Exception as e:
            fails.append((item.label, f"目标解析失败: {e!r}"))
            continue
        for bot in get_bots().values():
            try:
                await _send_with_retry(
                    lambda t=target, b=bot: UniMessage.image(raw=image).send(target=t, bot=b),
                    label=item.label,
                )
                sent = True
                break
            except Exception as e:
                last_err = e
                continue
        if sent:
            ok += 1
            logger.info(f"日报已推送至 {item.label}")
        else:
            fails.append((item.label, repr(last_err)))
            logger.warning(f"日报推送失败 {item.label}: {last_err!r}")

    return {"ok": ok, "fail": fails, "total": len(targets)}


async def push_text_to_all(store: Store, text: str) -> dict:
    """向全部启用的推送目标发送文字（用于深读失败提示等运维通知）。"""
    targets = [t for t in store.config.push_targets if t.enabled]
    if not targets:
        return {"ok": 0, "fail": [], "total": 0}
    ok, fails = 0, []
    for item in targets:
        try:
            target = Target.load(item.target)
        except Exception as e:
            fails.append((item.label, f"目标解析失败: {e!r}"))
            continue
        sent = False
        for bot in get_bots().values():
            try:
                await _send_with_retry(
                    lambda t=target, b=bot: UniMessage.text(text).send(target=t, bot=b),
                    label=item.label,
                )
                sent = True
                break
            except Exception:
                continue
        if sent:
            ok += 1
    return {"ok": ok, "fail": fails, "total": len(targets)}
