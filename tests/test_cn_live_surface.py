"""CN live runtime surface: contextual chips only, never a page-level viewport strip."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = (ROOT / "templates" / "china.html.j2").read_text(encoding="utf-8")
JS = (ROOT / "templates" / "cn_prophet_live.js").read_text(encoding="utf-8")
SITE_JS = (ROOT / "site" / "cn_prophet_live.js").read_text(encoding="utf-8")

BANNED = ("fired", "confirmed", "triggered", "refuted", "falsifier",
          "validated", "证伪", "已触发", "已确认")


def _nc(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def test_js_pair_is_byte_identical() -> None:
    assert JS == SITE_JS


def test_script_is_stocks_mode_only() -> None:
    assert "{% if mode == 'stocks' %}<script src=\"cn_prophet_live.js\"></script>{% endif %}" in TPL
    header = TPL[TPL.index("A-SHARE STOCK DASHBOARD HEADER"):TPL.index("_china_act_now_board.html.j2")]
    assert 'id="cn-prophet-live"' in header


def test_hidden_session_sentinel_is_wired_before_the_action_board() -> None:
    assert 'id="cn-prophet-live"' in TPL
    assert "data-cn-session=" in TPL
    assert ".cnpl[hidden]{display:none!important}" in TPL
    assert TPL.index('id="cn-prophet-live"') < TPL.index("_china_act_now_board.html.j2")


def test_runtime_can_never_reveal_the_page_level_intraday_strip() -> None:
    """Viewport telemetry must stay contextual to cards, not become a top-level block."""
    js = _nc(JS)
    assert "function keepSentinelHidden" in js
    assert "keepSentinelHidden();" in js
    assert "sentinel.hidden = true" in js
    assert "strip.hidden = false" not in js
    assert "sentinel.hidden = false" not in js
    assert "function paintStrip" not in js
    assert "cnpl-phase" not in js
    assert "cnpl-cov" not in js
    assert "cnpl-asof" not in js
    assert "cnpl-close" not in js


def test_polls_the_gated_artifact_without_cache() -> None:
    js = _nc(JS)
    assert 'live/cn_prophet_live.json' in js
    assert "cache: \"no-store\"" in js or "cache:'no-store'" in js
    assert "120000" in js
    assert "cn_prophet_live.states/v1" in js


def test_feed_floor_refuses_an_older_session() -> None:
    js = _nc(JS)
    assert "function feedIsCurrent" in js
    assert "s >= floor" in js
    assert "tearDown" in js


def test_401_and_stale_age_tear_the_live_layer_down() -> None:
    js = _nc(JS)
    assert "status === 401" in js
    assert "900000" in js
    assert "tearDown" in js
    assert 'el.className = "pv-live"' in js


def test_glance_copy_is_bilingual_and_has_no_settled_fact_words() -> None:
    js = _nc(JS)
    for table in ("STATE", "STATUS"):
        assert "var %s =" % table in JS
    for word in BANNED:
        assert word not in js.lower() and word not in js
    assert "盘中暂歇" in JS
    assert "一字涨停" in JS
    assert "停牌" in JS
    assert "暂无行情" in JS
    assert "windows, not certainties" in JS
    assert "窗口，不是定论" in JS


def test_no_client_side_scoring() -> None:
    js = _nc(JS)
    for token in ("prophet_score", "rankNames", "sort(", ".score ="):
        assert token not in js
    assert "d.names" in js


def test_limit_lock_uses_direction_tokens_not_hardcoded_green_red() -> None:
    css = TPL[TPL.index(".cnpl{"):TPL.index("</style>", TPL.index(".cnpl{"))]
    assert "--up" in css and "--down" in css
    assert "#0" not in css and "green" not in css.lower() and "red" not in css.lower()
