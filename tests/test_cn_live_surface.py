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
    assert header.count('id="stocks-header"') == 1


def test_session_floor_lives_on_existing_stocks_header() -> None:
    """The settled-session floor belongs to an existing semantic node, not an auxiliary box."""
    m = re.search(r'<div class="panel span12" id="stocks-header"[^>]*>', TPL)
    assert m, "stocks header opening tag not found"
    assert 'data-cn-session="{{ _cn_through or \'\' }}"' in m.group(0)
    assert TPL.count("data-cn-session=") == 1


def test_retired_page_level_strip_is_absent_from_template() -> None:
    """No dormant DOM/CSS path may resurrect the retired Tier-1 telemetry module."""
    for token in (
        'id="cn-prophet-live"',
        'id="cnpl-phase"',
        'id="cnpl-cov"',
        'id="cnpl-asof"',
        'id="cnpl-close"',
        '.cnpl{',
        '.cnpl[hidden]',
        '.cnpl-k{',
        '.cnpl.is-close',
        '.cnpl-banner{',
    ):
        assert token not in TPL, f"retired page-level CN live surface still ships: {token}"


def test_runtime_reads_header_floor_and_has_no_strip_carrier_path() -> None:
    js = _nc(JS)
    page = js[js.index("function pageSession") : js.index("function feedIsCurrent")]
    assert 'document.getElementById("stocks-header")' in page
    assert 'getAttribute("data-cn-session")' in page
    assert "cn-prophet-live" not in js
    assert "detachSessionCarrier" not in js

    arm = js[js.index("function arm()") : js.index('if (document.readyState')]
    assert arm.index('document.getElementById("stocks-header")') < arm.index("pageSession();") < arm.index("tick(true);")


def test_runtime_has_no_page_level_reveal_or_telemetry_paint_path() -> None:
    js = _nc(JS)
    assert "function paintStrip" not in js
    assert "strip.hidden = false" not in js
    assert "cnpl-phase" not in js
    assert "cnpl-cov" not in js
    assert "cnpl-asof" not in js
    assert "cnpl-close" not in js
    assert "market_phase" not in js
    assert "coverage_pct" not in js
    assert "close_provisional" not in js


def test_polls_the_gated_artifact_without_cache() -> None:
    js = _nc(JS)
    assert 'live/cn_prophet_live.json' in js
    assert "cache: \"no-store\"" in js or "cache:'no-store'" in js
    assert "120000" in js
    assert "cn_prophet_live.states/v1" in js


def test_feed_floor_refuses_an_older_session_after_header_read() -> None:
    js = _nc(JS)
    assert "function pageSession" in js
    assert "_bakedSession" in js
    assert "function feedIsCurrent" in js
    assert "s >= floor" in js
    assert "tearDown" in js


def test_401_and_stale_age_tear_the_live_layer_down() -> None:
    js = _nc(JS)
    assert "status === 401" in js
    assert "900000" in js
    assert "tearDown" in js
    assert 'el.className = "pv-live"' in js
    teardown = js[js.index("function tearDown()") : js.index("function paintChip")]
    assert 'querySelectorAll(".pvcard[data-ticker] .pv-live")' in teardown


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
    for selector, token in (
        (r"\.pv-live\.cnpl-up", "var(--up)"),
        (r"\.pv-live\.cnpl-down", "var(--down)"),
        (r"\.pv-live\.cnpl-break", "var(--muted)"),
    ):
        m = re.search(selector + r"\{([^}]*)\}", TPL)
        assert m, f"missing card-local style for {selector}"
        body = m.group(1)
        assert token in body
        assert "#0" not in body and "green" not in body.lower() and "red" not in body.lower()
