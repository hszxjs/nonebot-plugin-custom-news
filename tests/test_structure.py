"""冒烟测试：所有模块都能导入。

这条看起来“没用”，但它挡住的是最贵的一类回归：重构时改了函数名/漏了 import，
静态检查不报、只有运行时某条数据源链路才炸（本次核查就出现过一次：
ai_models 的 load_ttl_cache 漏 import，症状是「大模型上新」从空数据变成失败）。
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import nonebot_plugin_custom_news


def _all_modules() -> list[str]:
    mods = [nonebot_plugin_custom_news.__name__]
    for info in pkgutil.walk_packages(
        nonebot_plugin_custom_news.__path__, prefix=f"{nonebot_plugin_custom_news.__name__}."
    ):
        if "webui.dist" in info.name:
            continue
        mods.append(info.name)
    return sorted(set(mods))


@pytest.mark.parametrize("modname", _all_modules())
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_no_reverse_dependency_from_sources_to_upper_layers() -> None:
    """sources/ 只允许向下依赖：不得 import fetcher/analyzer/renderer（消除反向依赖）。"""
    from pathlib import Path

    import nonebot_plugin_custom_news

    sources_dir = Path(nonebot_plugin_custom_news.__file__).parent / "sources"
    forbidden = ("..fetcher", "..analyzer", "..renderer", "..service", "..pusher")
    offenders = [
        f"{p.name}: {line.strip()}"
        for p in sources_dir.glob("*.py")
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.startswith(("from ", "import "))
        and any(token in line for token in forbidden)
    ]
    assert not offenders, f"sources/ 出现反向依赖：{offenders}"


def test_sources_package_has_no_duplicate_ua_or_truncate() -> None:
    """UA 与截断函数应只有一份实现（原先 4 处 UA、3 处截断各写一遍）。"""
    from pathlib import Path

    import nonebot_plugin_custom_news

    sources_dir = Path(nonebot_plugin_custom_news.__file__).parent / "sources"
    dup_ua = [
        p.name
        for p in sources_dir.glob("*.py")
        if p.name != "_shared.py" and "Mozilla/5.0 (iPhone" in p.read_text(encoding="utf-8")
    ]
    assert not dup_ua, f"UA 常量重复定义于：{dup_ua}"
