"""共用工具、配置校验与深读 prompt 的确定性单测。

这些都是纯函数/纯模型：不需要网络，是重构时最该被钉住的行为。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from nonebot_plugin_custom_news.analyzer import (
    _STYLE_DICE,
    _chat_completions_url,
    _parse_llm_json,
    _system_prompt,
)
from nonebot_plugin_custom_news.sources._shared import (
    load_ttl_cache,
    save_ttl_cache,
    truncate,
)
from nonebot_plugin_custom_news.store import GeneralSettings, ScheduleItem

# ---------------------------------------------------------------- 共用缓存


def test_ttl_cache_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "c.json"
    save_ttl_cache(f, [{"a": 1}])
    assert load_ttl_cache(f, ttl=60) == [{"a": 1}]


def test_ttl_cache_expiry(tmp_path: Path) -> None:
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"ts": time.time() - 3600, "items": [1]}), "utf-8")
    assert load_ttl_cache(f, ttl=60) is None


def test_ttl_cache_corrupt_and_missing(tmp_path: Path) -> None:
    f = tmp_path / "c.json"
    f.write_text("{ not json", "utf-8")
    assert load_ttl_cache(f, ttl=60) is None
    assert load_ttl_cache(tmp_path / "nope.json", ttl=60) is None


def test_ttl_cache_rejects_ts_as_payload_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_ttl_cache(tmp_path / "c.json", [1], key="ts")


def test_truncate_keeps_short_text_intact() -> None:
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdef", 4) == "abc…"
    assert len(truncate("abcdef", 4)) == 4


# ---------------------------------------------------------------- 配置校验


def test_timezone_validator_rejects_garbage() -> None:
    assert GeneralSettings(timezone="Asia/Shanghai").timezone == "Asia/Shanghai"
    with pytest.raises(ValueError):
        GeneralSettings(timezone="Not/AZone")


def test_weekdays_validator_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        ScheduleItem(id="x", weekdays=[0, 7])


def test_weekdays_validator_dedupes_and_sorts() -> None:
    assert ScheduleItem(id="x", weekdays=[3, 1, 1, 2]).weekdays == [1, 2, 3]


def test_render_width_bounds() -> None:
    with pytest.raises(ValueError):
        GeneralSettings(render_width=99_999)


# ---------------------------------------------------------------- 深读 prompt


class _G:
    def __init__(self, style: str = "") -> None:
        self.llm_style_prompt = style


def test_system_prompt_without_style_is_builtin() -> None:
    from nonebot_plugin_custom_news.analyzer import _SYSTEM_PROMPT

    assert _system_prompt(_G()) == _SYSTEM_PROMPT


def test_system_prompt_appends_style_after_rules() -> None:
    out = _system_prompt(_G("你是深海胖鱼，短句口语"))
    from nonebot_plugin_custom_news.analyzer import _SYSTEM_PROMPT

    assert out.startswith(_SYSTEM_PROMPT)
    assert "你是深海胖鱼" in out
    # 规则必须仍在自定义风格之前，避免被风格覆盖掉 JSON 约束
    assert out.index("输出严格为 JSON") < out.index("你是深海胖鱼")


def test_style_dice_non_empty_and_unique() -> None:
    assert len(_STYLE_DICE) >= 4
    assert len(set(_STYLE_DICE)) == len(_STYLE_DICE)


def test_chat_completions_url_normalization() -> None:
    assert (
        _chat_completions_url("https://api.deepseek.com/v1")
        == "https://api.deepseek.com/v1/chat/completions"
    )
    assert (
        _chat_completions_url("https://api.deepseek.com/v1/chat/completions")
        == "https://api.deepseek.com/v1/chat/completions"
    )
    assert (
        _chat_completions_url("https://x/v1/ ")
        == "https://x/v1/chat/completions"
    )


def test_parse_llm_json_tolerates_wrapping_text() -> None:
    assert _parse_llm_json('前置话 {"event": "e"} 后置话')["event"] == "e"


def test_parse_llm_json_fills_missing_fields_and_caps_points() -> None:
    d = _parse_llm_json('{"points": ["1", "2", "3", "4", "5"], "impact": null}')
    assert d["points"] == ["1", "2", "3", "4"]
    assert d["impact"] == ""
    assert d["event"] == ""


def test_parse_llm_json_raises_on_non_json() -> None:
    with pytest.raises(ValueError):
        _parse_llm_json("模型今天不想输出 JSON")


# ---------------------------------------------------------------- 配置脱敏


def test_redact_config_hides_secrets(store) -> None:
    from nonebot_plugin_custom_news.webui.api import SECRET_MASK, _redact_config

    store.config.general.llm_api_key = "sk-real-key"
    store.config.webui.secret = "hmac-secret"
    store.config.webui.password_sha = "deadbeef"

    red = _redact_config(store)
    assert red["general"]["llm_api_key"] == SECRET_MASK
    assert set(red["webui"]) == {"username"}
    assert "secret" not in json.dumps(red)
    assert "deadbeef" not in json.dumps(red)


def test_config_update_accepts_music_chat() -> None:
    from nonebot_plugin_custom_news.webui.api import ConfigUpdate

    m = ConfigUpdate.model_validate({"music_chat": {"count": 5}})
    assert m.music_chat is not None
    assert m.music_chat.count == 5


# ---------------------------------------------------------------- 榜单投影


def test_rows_to_items_builds_titles_and_links() -> None:
    from nonebot_plugin_custom_news.sources.music import rows_to_items

    rows = [
        {"song": " 歌名 ", "artists": "歌手A/歌手B", "jump_url": "https://x/1"},
        {"song": "独唱", "artists": "", "jump_url": ""},
        {"song": "", "artists": "幽灵歌手", "jump_url": "https://x/3"},
    ]
    items = rows_to_items(rows, limit=10)
    assert [i.title for i in items] == ["歌名 - 歌手A/歌手B", "独唱"]
    assert items[0].url == "https://x/1"
    assert items[1].url is None  # 空 URL 归一为 None，避免模板渲染出空链接


def test_rows_to_items_respects_limit() -> None:
    from nonebot_plugin_custom_news.sources.music import rows_to_items

    rows = [{"song": f"s{i}", "artists": "a", "jump_url": "u"} for i in range(20)]
    assert len(rows_to_items(rows, limit=3)) == 3


# ---------------------------------------------------------------- 渲染尺寸收敛


def test_resolve_render_size_caps_raster_width() -> None:
    """3000px 宽是本次核查发现的病灶（实测峰值内存 4.35GB），必须被收敛。"""
    from nonebot_plugin_custom_news.renderer import resolve_render_size

    css, dpr = resolve_render_size(3000, 1.5)
    assert css == 2000
    assert dpr == 1.0
    assert css * dpr <= 2000


def test_resolve_render_size_keeps_default_untouched() -> None:
    """默认 1280×1.5=1920 在上限内，不应被改动（避免无谓的行为变化）。"""
    from nonebot_plugin_custom_news.renderer import resolve_render_size

    assert resolve_render_size(1280, 1.5) == (1280, 1.5)


def test_resolve_render_size_never_goes_below_dpr_floor() -> None:
    """dpr 不得低于 1.0：低于 1 是把文字降采样，清晰度白送。"""
    from nonebot_plugin_custom_news.renderer import resolve_render_size

    for width in (1600, 2000, 2400, 4000):
        _, dpr = resolve_render_size(width, 1.0)
        assert dpr >= 1.0


def test_resolve_render_size_clamps_absurd_width_and_floor() -> None:
    from nonebot_plugin_custom_news.renderer import resolve_render_size

    assert resolve_render_size(99_999, 1.5)[0] == 2000
    assert resolve_render_size(10, 1.5)[0] == 320  # 下限，避免 0/负值


def test_resolve_render_size_pixels_decrease_monotonically() -> None:
    """宽度越大，光栅像素数不得反而更多（收敛必须单调）。"""
    from nonebot_plugin_custom_news.renderer import resolve_render_size

    pixels = [w * d for w, d in (resolve_render_size(x, 1.5) for x in (640, 1280, 1600, 2000, 3000))]
    assert pixels == sorted(pixels), pixels
