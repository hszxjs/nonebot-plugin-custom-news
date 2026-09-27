"""pytest 公共夹具。

插件是 NoneBot 插件，包入口（`__init__.py`）会调用 require()、
inherit_supported_adapters() 等依赖真实插件加载流程的 API。单测只关心子模块，
因此这里用「合成包」占位：`nonebot_plugin_custom_news` 在 sys.modules 里指向真实
目录但不执行包入口，子模块照常导入。

代价：本套测试不覆盖包入口（插件元数据与命令注册），那部分靠实机启动验证。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import nonebot
import pytest

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()


class _APSchedulerShim:
    """require("nonebot_plugin_apscheduler") 的替身。"""

    def __init__(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


_SHIM = _APSchedulerShim()
nonebot.require = lambda name: _SHIM if "apscheduler" in name else None  # type: ignore[assignment]

_PKG_DIR = Path(__file__).resolve().parents[1] / "nonebot_plugin_custom_news"
if "nonebot_plugin_custom_news" not in sys.modules:
    _pkg = types.ModuleType("nonebot_plugin_custom_news")
    _pkg.__path__ = [str(_PKG_DIR)]  # type: ignore[attr-defined]
    _pkg.__file__ = str(_PKG_DIR / "__init__.py")
    sys.modules["nonebot_plugin_custom_news"] = _pkg


@pytest.fixture(scope="session")
def aps_shim() -> _APSchedulerShim:
    return _SHIM


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """指向临时目录的 Store（不碰真实 config.json 与缓存）。"""
    from nonebot_plugin_custom_news import store as store_mod

    monkeypatch.setattr(store_mod, "get_plugin_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(store_mod, "get_plugin_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(store_mod, "_store", None)
    return store_mod.get_store()
