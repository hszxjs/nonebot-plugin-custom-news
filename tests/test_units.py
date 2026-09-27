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


# ---------------------------------------------------------------- 配置降级（P0 回归）


def test_salvage_keeps_other_sections_when_one_is_invalid(tmp_path, monkeypatch) -> None:
    """校验失败只能修「坏掉的那个分区」，不得整份重建。

    历史场景：旧版本允许把 timezone 写成 'UTC+8'，升级后新校验器会判它非法。
    若失败即整份重建，会静默丢掉 LLM Key、推送目标、自定义主题、音乐 cookie，
    并重新生成 WebUI 密码与 secret（旧 Token 全废，不可撤销）。
    """
    import json

    from nonebot_plugin_custom_news import store as store_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 3,
                "general": {
                    "timezone": "UTC+8",  # 旧版本写进去的非法值
                    "llm_api_key": "sk-keep-me",
                    "render_width": 2000,
                },
                "schedules": [
                    {"id": "custom1", "label": "我的时段", "hour": 7, "minute": 30}
                ],
                "webui": {"username": "admin", "password_sha": "a" * 64, "secret": "s" * 64},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store_mod, "get_plugin_data_dir", lambda: data_dir)
    monkeypatch.setattr(store_mod, "get_plugin_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(store_mod, "_store", None)

    cfg = store_mod.get_store().config

    assert cfg.general.timezone == "Asia/Shanghai", "非法时区应落回默认值"
    assert cfg.general.llm_api_key == "sk-keep-me", "LLM Key 被整份重建丢掉了"
    assert cfg.general.render_width == 2000, "同分区里的合法字段也被重置了"
    assert [s.id for s in cfg.schedules] == ["custom1"], "推送时段被整份重建丢掉了"
    assert cfg.webui.secret == "s" * 64, "secret 被轮换，旧 Token 会全部失效"
    assert cfg.webui.password_sha == "a" * 64
    assert (data_dir / "config.json.bak").exists(), "原文件应留备份"


def test_env_out_of_range_does_not_break_store(tmp_path, monkeypatch) -> None:
    """.env 越界值必须收敛，不能让 Store 初始化抛错（否则全接口 500 且重启不自愈）。"""
    from nonebot_plugin_custom_news.store import Store

    class _Cfg:
        custom_news_dailyhot_api_url = "https://api-hot.imsyy.top"
        custom_news_render_width = 5000  # 越界
        custom_news_cache_ttl = 1800
        custom_news_timezone = "UTC+8"  # 非 IANA
        custom_news_webui_password = None

    monkeypatch.setattr(
        Store, "__init__",
        lambda self, cfg: (
            setattr(self, "plugin_config", cfg),
            setattr(self, "data_dir", tmp_path / "d"),
            setattr(self, "cache_dir", tmp_path / "c"),
            setattr(self, "backgrounds_dir", tmp_path / "d" / "bg"),
            setattr(self, "config_path", tmp_path / "d" / "config.json"),
            (tmp_path / "d").mkdir(parents=True, exist_ok=True),
            (tmp_path / "c").mkdir(parents=True, exist_ok=True),
            (tmp_path / "d" / "bg").mkdir(parents=True, exist_ok=True),
        )[-1],
    )
    store_obj = Store.__new__(Store)
    Store.__init__(store_obj, _Cfg())  # type: ignore[misc]
    store_obj.config = store_obj._default_config()  # type: ignore[attr-defined]

    assert store_obj.config.general.render_width == 4096
    assert store_obj.config.general.timezone == "Asia/Shanghai"


def test_load_ttl_cache_non_object_root(tmp_path: Path) -> None:
    """合法 JSON 但根不是对象时按未命中处理（旧实现抛 AttributeError → 该源永久失败）。"""
    f = tmp_path / "c.json"
    f.write_text("[1, 2, 3]", "utf-8")
    assert load_ttl_cache(f, ttl=60) is None


def test_rows_to_items_limit_non_positive() -> None:
    from nonebot_plugin_custom_news.sources.music import rows_to_items

    rows = [{"song": "a", "artists": "b", "jump_url": "u"}]
    assert rows_to_items(rows, 0) == []
    assert rows_to_items(rows, -3) == []


# ---------------------------------------------------------------- 安全加固（2026-09-27 审计）


def test_ssrf_guard_blocks_private_targets() -> None:
    from nonebot_plugin_custom_news.sources.article import is_public_http_url

    for bad in (
        "http://127.0.0.1:6688/",
        "http://localhost:8080/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "",
    ):
        assert not is_public_http_url(bad), bad
    # 字面公网 IP 不需要 DNS，保证测试可离线运行
    assert is_public_http_url("https://93.184.216.34/news/1")


def test_preset_background_must_be_known_id(tmp_path, monkeypatch) -> None:
    """preset 只能取预设 id：绝对路径/`..` 曾能读本机任意 *.jpg 并内联进渲染图。"""
    import pytest

    from nonebot_plugin_custom_news.renderer import RenderError, resolve_background
    from nonebot_plugin_custom_news.theme import PRESET_BACKGROUNDS, BackgroundConfig

    class _Theme:
        def __init__(self, value: str) -> None:
            self.background = BackgroundConfig(type="preset", value=value)

    # 合法预设 id 正常解析
    ok_id = PRESET_BACKGROUNDS[0]["id"]
    path = resolve_background(None, _Theme(ok_id))  # type: ignore[arg-type]
    assert path.parent.name == "backgrounds"

    # 路径穿越/绝对路径一律拒绝（旧实现只做 exists()，能读走本机任意 *.jpg）
    for bad in ("/Users/x/Pictures/secret", "../../../etc/passwd", "..%2fsecret"):
        with pytest.raises(RenderError):
            resolve_background(None, _Theme(bad))  # type: ignore[arg-type]


def test_password_hash_scrypt_and_legacy_upgrade(store) -> None:
    import hashlib

    from nonebot_plugin_custom_news.webui.auth import _hash_password, _verify_hash, verify_password

    store.config.webui.username = "admin"
    store.config.webui.password_sha = hashlib.sha256(b"legacy-pass").hexdigest()
    # 旧的无盐 SHA-256 仍可登录，且登录成功后被透明重写为 scrypt
    assert verify_password(store, "admin", "legacy-pass")
    assert store.config.webui.password_sha.startswith("scrypt$")
    assert _verify_hash(_hash_password("新口令"), "新口令")
    assert not _verify_hash(_hash_password("新口令"), "别的口令")


def test_password_change_rotates_secret_with_grace(store) -> None:
    from nonebot_plugin_custom_news.webui.auth import (
        _check_token,
        change_password,
        issue_token,
    )

    store.config.webui.secret = "old-secret"
    token = issue_token(store, "admin")
    assert _check_token(store, token)

    change_password(store, "new-password-123")
    assert store.config.webui.secret != "old-secret", "改密码必须轮换 secret"
    # 宽限期内旧 Token 仍可用（不打断正在使用的会话），且新 Token 也可用
    assert _check_token(store, token)
    assert _check_token(store, issue_token(store, "admin"))

    # 宽限期过后旧 Token 失效
    store.config.webui.secret_rotated_at -= 3601
    assert not _check_token(store, token)


def test_login_failure_backoff(store) -> None:
    import pytest
    from fastapi import HTTPException

    from nonebot_plugin_custom_news.webui.auth import (
        note_login_failure,
        note_login_success,
        verify_login_allowed,
    )

    for _ in range(5):
        note_login_failure("admin")
    with pytest.raises(HTTPException) as exc:
        verify_login_allowed("admin")
    assert exc.value.status_code == 429
    note_login_success("admin")
    verify_login_allowed("admin")  # 成功后计数清零


def test_today_command_cooldown_dimensions() -> None:
    """用户与群两个维度各自计时。"""
    from nonebot_plugin_custom_news import matcher

    class _Ev:
        group_id = 123
        user_id = 456

    ev = _Ev()
    matcher._last_trigger.clear()
    assert matcher.cooldown_remaining(ev) == 0
    matcher.mark_triggered(ev)
    assert matcher.cooldown_remaining(ev) > 0
    # 同群换个人：群维度仍然拦住
    class _Other(_Ev):
        user_id = 999
    assert matcher.cooldown_remaining(_Other()) > 0


# ---------------------------------------------------------------- 状态写入竞态


def test_fetch_status_concurrent_updates_do_not_clobber(store) -> None:
    """并发抓取时，状态文件的读-改-写必须串行化。

    原实现是「读全量 → 改一项 → 整体覆写」，后写者覆盖先写者，
    结果状态文件只留最后一个完成的源，WebUI 的「数据源健康」大面积显示无状态。
    """
    import asyncio

    from nonebot_plugin_custom_news.fetcher import _load_fetch_status, _update_fetch_status

    async def burst() -> None:
        await asyncio.gather(
            *[_update_fetch_status(store, f"src{i}", {"items": i}) for i in range(8)]
        )

    asyncio.run(burst())
    status = _load_fetch_status(store)
    assert sorted(k for k in status if k.startswith("src")) == [f"src{i}" for i in range(8)]
