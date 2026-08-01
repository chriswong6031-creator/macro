"""Tests for the CBBC (W1) freshness banner in templates/hk.html.j2.

`engine.hk_cbbc.run()` has always built `snap["banner"]`, but no template ever
rendered it — the freshness disclosure shipped DARK: a stale or missing
leverage store still drew a confident-looking leverage row with no caveat.
This suite pins the wiring on both surfaces (the "Overnight & Leverage" glance
card and the dlg-overnight dialog) plus the plain-word engine copy.

Covers:
  (1)  Banner en/zh text renders in BOTH surfaces, with l-en/l-zh spans.
  (2)  banner=None → no banner text anywhere.
  (3)  Engine-crash shape (bellwethers=[] WITH a banner) still renders it —
       the reason the block sits OUTSIDE the bellwethers gate.
  (4)  Stale read is dimmed (opacity:.55) on the kv row and the bull/bear bar.
  (5)  leverage_state='no_data' never renders as "Balanced" / 均衡.
  (6)  State mapping: the engine emits bull_skew/bear_skew_froth/balanced —
       never the 'bullish'/'bearish' the template used to test for.
  (7)  Grep-level anti-dark pin: `cbbc_map.banner` is referenced in the
       template source (independent of the render harness).
  (8)  No CJK inside title= attributes (CI-guarded house law).
  (9)  Engine copy: _w1_banner never leaks the raw freshness verdict.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bellwether(leverage_state: str = "balanced",
                     bull_outstanding: int | None = 600,
                     bear_outstanding: int | None = 400) -> dict:
    """One bellwether entry as engine.hk_cbbc._aggregate_for_ticker emits it.

    The template reads only name_en / name_zh / leverage_state /
    bull_outstanding / bear_outstanding; ticker + is_index are carried so the
    fixture keeps the real row shape.
    """
    return {
        "ticker": "9988.HK",
        "name_en": "Alibaba",
        "name_zh": "阿里巴巴",
        "is_index": False,
        "leverage_state": leverage_state,
        "bull_outstanding": bull_outstanding,
        "bear_outstanding": bear_outstanding,
    }


def _make_cbbc_map(banner: dict | None = None,
                   bellwethers: list[dict] | None = None) -> dict:
    """Build a synthetic cbbc_map snap (engine.hk_cbbc.run() output shape)."""
    if bellwethers is None:
        bellwethers = [_make_bellwether()]
    return {
        "as_of_trade_date": "20260730",
        "freshness": "stale" if banner else "fresh",
        "bellwethers": bellwethers,
        "banner": banner,
        "cbbc_total_contracts": 1234,
        "dw_total_contracts": 567,
        "sld_call_levels_in_store": 0,
        "display_only": True,
    }


_BANNER = {
    "en": "Leverage data is out of date — showing the last good read",
    "zh": "杠杆数据已过期，显示最近一次有效读数",
}


# ---------------------------------------------------------------------------
# Slice helpers — LIVE sentinels, hard-asserted at BOTH ends
# ---------------------------------------------------------------------------
#
# A `find` that returns -1 must fail loudly. The HKRV-W3 suite lost its scoping
# exactly this way (see tests/test_hkrv_w3_banner.py::_banner_block): a deleted
# end marker plus an `end if end != -1 else None` fallback silently widened the
# slice to the rest of the page, and every `assert X in block` below it kept
# passing on a match anywhere downstream. Never widen — assert.

def _glance_slice(html: str) -> str:
    """The 'Overnight & Leverage' glance card (card open → next rack row)."""
    start = html.find("hkxOpenDlg('hkx-dlg-overnight')")
    assert start != -1, "glance-card start sentinel hkxOpenDlg('hkx-dlg-overnight') not found"
    end = html.find("hkx-rack3", start)
    assert end != -1, "glance-card end sentinel 'hkx-rack3' not found after the card"
    return html[start:end]


def _dialog_slice(html: str) -> str:
    """The dlg-overnight dialog (its id → the next dialog's id)."""
    start = html.find('id="hkx-dlg-overnight"')
    assert start != -1, 'dialog start sentinel id="hkx-dlg-overnight" not found'
    end = html.find('id="hkx-dlg-news"', start)
    assert end != -1, 'dialog end sentinel id="hkx-dlg-news" not found after the dialog'
    return html[start:end]


def _enclosing_div(block: str, needle: str) -> str:
    """The <div>…</div> that encloses `needle` (hard-asserted at both ends)."""
    idx = block.find(needle)
    assert idx != -1, f"{needle!r} not found in block"
    start = block.rfind("<div", 0, idx)
    assert start != -1, f"no opening <div> before {needle!r}"
    end = block.find("</div>", idx)
    assert end != -1, f"no closing </div> after {needle!r}"
    return block[start:end + len("</div>")]


# ---------------------------------------------------------------------------
# Render harness (vm scaffold mirrors tests/test_hkrv_w3_banner.py)
# ---------------------------------------------------------------------------

def _make_setups() -> dict:
    return {
        "leadership": None,
        "health": [],
        "buy": [],
        "watch": [],
        "laggards": [],
        "southbound_summary": None,
        "liquidity_regime": None,
        "dispersion_regime": None,
        "washout_watch": None,
        "context_chips": None,
        "board_track": None,
    }


def _make_actions() -> dict:
    return {
        "buy_now": [],
        "buy_soon": [],
        "on_the_run": [],
        "take_profits": [],
        "hold": [],
        "avoid": [],
    }


def _render(cbbc_map: dict | None) -> str:
    """Render hk.html.j2 with a minimal vm plus cbbc_map, return the HTML."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    from markupsafe import Markup

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    env.globals["help"] = lambda en, zh="": Markup("")

    tmpl = env.get_template("hk.html.j2")
    vm = {
        # NOT 'stocks': the whole mx5 hkx surface (glance racks + dialogs, and
        # therefore both CBBC regions) lives behind `{% if mode != 'stocks' %}`.
        # test_hkrv_w3_banner.py renders the stocks mode because its banner
        # lives on that side of the gate.
        "mode": "macro",
        "latest": {
            "date": "2026-07-10",
            "quad_name": "Goldilocks",
            "quad": "Q1",
            "liquidity_overlay": "neutral",
            "pending_quad": None,
        },
        "actions": _make_actions(),
        "setups": _make_setups(),
        "cbbc_map": cbbc_map,
        "gv": None,
        "market_state": None,
        "hk_scoreboard": None,
        "sectors_by_ticker": {},
        "velocity_desk": None,
        "built": "2026-07-10T00:00:00Z",
        "hk_breadth": None,
        "hk_full_breadth": None,
        "benchmark": None,
        "hk_sectors": [],
        "hk_flow": None,
        "track_record": None,
        "hk_ab": None,
        "hk_dispersion": None,
        "hk_cycles": None,
        "hk_indicators": None,
        "state_display_json": "{}",
        "washout_desk": None,
        "freshness": None,
        "hk_history": None,
        "hk_news": None,
        "hk_policy": None,
        "hk_macro": None,
        "hk_property": None,
        "hk_alerts": None,
        "hk_market_drivers": None,
        "hk_conditions": None,
        "hk_signal_stack": None,
        "hk_event_calendar": None,
        "hk_context_chips": None,
        "velocity_desk_picks": None,
        "hk_lab_button": None,
    }
    return tmpl.render(**vm)


# ---------------------------------------------------------------------------
# (1) Banner renders on BOTH surfaces, bilingually
# ---------------------------------------------------------------------------

def test_banner_renders_in_both_surfaces():
    """Banner en AND zh text must render in the glance card and the dialog."""
    html = _render(_make_cbbc_map(banner=_BANNER))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        assert _BANNER["en"] in block, f"EN banner text missing from {name} surface"
        assert _BANNER["zh"] in block, f"ZH banner text missing from {name} surface"


def test_banner_div_is_bilingual():
    """Each rendered banner div must carry both l-en and l-zh spans."""
    html = _render(_make_cbbc_map(banner=_BANNER))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        div = _enclosing_div(block, _BANNER["en"])
        assert 'class="l-en"' in div, f"{name} banner div missing l-en span"
        assert 'class="l-zh"' in div, f"{name} banner div missing l-zh span"


# ---------------------------------------------------------------------------
# (2) Absent when banner is None
# ---------------------------------------------------------------------------

def test_banner_absent_when_none():
    """No banner copy anywhere when cbbc_map.banner is None."""
    html = _render(_make_cbbc_map(banner=None))
    assert _BANNER["en"] not in html, "EN banner text must be absent when banner is None"
    assert _BANNER["zh"] not in html, "ZH banner text must be absent when banner is None"
    assert "Leverage data unavailable" not in html
    assert "杠杆数据不可用" not in html


# ---------------------------------------------------------------------------
# (3) Engine-crash shape: bellwethers=[] WITH a banner
# ---------------------------------------------------------------------------

def test_banner_renders_with_empty_bellwethers():
    """The engine-crash path returns bellwethers=[] WITH a banner.

    That is the case a reader most needs told, so the banner block must sit
    OUTSIDE the `{% if cbbc_map.bellwethers %}` gate on both surfaces. If it is
    ever moved back inside, the disclosure goes dark exactly when the data does.
    """
    crash = _make_cbbc_map(banner={"en": "Leverage data unavailable",
                                   "zh": "杠杆数据不可用"},
                           bellwethers=[])
    html = _render(crash)
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        assert "Leverage data unavailable" in block, (
            f"banner must still render on the {name} surface with bellwethers=[]"
        )
        assert "杠杆数据不可用" in block, f"ZH banner missing from {name} surface"


# ---------------------------------------------------------------------------
# (4) Dimming the stale read
# ---------------------------------------------------------------------------

def test_stale_read_is_dimmed():
    """Banner set → the leverage kv row and bull/bear bar are dimmed."""
    html = _render(_make_cbbc_map(banner=_BANNER))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        assert "opacity:.55" in block, f"{name} surface must dim the stale leverage read"


def test_fresh_read_is_not_dimmed():
    """Banner None → nothing is dimmed on either surface."""
    html = _render(_make_cbbc_map(banner=None))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        assert "opacity:.55" not in block, f"{name} surface must not dim a fresh read"


# ---------------------------------------------------------------------------
# (5) no_data honesty
# ---------------------------------------------------------------------------

def test_no_data_state_never_reads_balanced():
    """leverage_state='no_data' must not be dressed up as "Balanced" / 均衡.

    The old class/label expression tested for 'bearish'/'bullish' — states the
    engine never emits — so EVERY state, no_data included, fell through to the
    "Balanced" else-branch and a missing store rendered as a confident read.
    """
    html = _render(_make_cbbc_map(
        banner=_BANNER,
        bellwethers=[_make_bellwether(leverage_state="no_data",
                                      bull_outstanding=None,
                                      bear_outstanding=None)],
    ))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        assert "均衡" not in block, f"no_data must not render as 均衡 on the {name} surface"
        assert ">Balanced" not in block, (
            f"no_data must not render as Balanced on the {name} surface"
        )


# ---------------------------------------------------------------------------
# (6) State-mapping pins (real engine vocabulary)
# ---------------------------------------------------------------------------

def test_bull_skew_reads_lean_bullish():
    """bull_skew → 'Lean bullish' / 偏多 with the ok (up) colour class."""
    html = _render(_make_cbbc_map(bellwethers=[_make_bellwether(leverage_state="bull_skew")]))
    block = _glance_slice(html)
    assert "Lean bullish" in block
    assert "偏多" in block
    assert 'class="hkx-stword ok"' in block, "bull skew must use the ok colour class"


def test_bear_skew_froth_reads_lean_bearish():
    """bear_skew_froth → 'Lean bearish' / 偏空 with the bad (down) colour class."""
    html = _render(_make_cbbc_map(
        bellwethers=[_make_bellwether(leverage_state="bear_skew_froth")]))
    block = _glance_slice(html)
    assert "Lean bearish" in block
    assert "偏空" in block
    assert 'class="hkx-stword bad"' in block, "bear froth must use the bad colour class"


def test_balanced_state_reads_balanced():
    """balanced → 'Balanced' / 均衡 with the neutral warn class."""
    html = _render(_make_cbbc_map(bellwethers=[_make_bellwether(leverage_state="balanced")]))
    block = _glance_slice(html)
    assert "Balanced" in block
    assert "均衡" in block
    assert 'class="hkx-stword warn"' in block, "balanced must use the neutral colour class"


def test_dialog_state_mapping():
    """The dialog rows map the same engine states (its own shorter wording)."""
    html = _render(_make_cbbc_map(bellwethers=[_make_bellwether(leverage_state="bull_skew")]))
    block = _dialog_slice(html)
    assert "Bullish" in block
    assert "偏多" in block
    assert 'class="hkx-stword ok"' in block


# ---------------------------------------------------------------------------
# (7) Grep-level anti-dark presence pin (harness-independent)
# ---------------------------------------------------------------------------

def test_template_source_references_banner_twice():
    """`cbbc_map.banner` must be referenced in the template source.

    Deliberately independent of the render harness: if _render or the vm
    scaffold is ever refactored into a vacuous pass, this still fails when the
    banner is deleted from the template. Two rendering sites are required —
    the glance card and the dlg-overnight dialog.
    """
    src = (ROOT / "templates" / "hk.html.j2").read_text(encoding="utf-8")
    assert src.count("cbbc_map.banner") >= 2, (
        "cbbc_map.banner must be referenced on both the glance card and the dialog"
    )
    assert src.count("cbbc_map.banner.en") >= 2, (
        "both surfaces must actually PRINT the banner, not merely branch on it"
    )
    assert src.count("cbbc_map.banner.zh") >= 2, (
        "both surfaces must print the ZH banner copy"
    )


# ---------------------------------------------------------------------------
# (8) No CJK in title= attributes (CI-guarded house law)
# ---------------------------------------------------------------------------

_CJK_IN_TITLE = re.compile(r'title=["\'][^"\']*[一-鿿㐀-䶿][^"\']*["\']')


def test_no_cjk_in_title_attrs():
    """No CJK characters inside title= attributes on either surface."""
    html = _render(_make_cbbc_map(banner=_BANNER))
    for name, block in (("glance", _glance_slice(html)), ("dialog", _dialog_slice(html))):
        bad = _CJK_IN_TITLE.findall(block)
        assert not bad, f"CJK found in title= attrs on the {name} surface: {bad}"


# ---------------------------------------------------------------------------
# (9) Engine copy: plain words, never the raw freshness verdict
# ---------------------------------------------------------------------------

def test_w1_banner_stale_copy_is_plain_words():
    """'stale' → out-of-date copy that never leaks the internal token."""
    from engine.hk_cbbc import _w1_banner
    out = _w1_banner("stale", False)
    assert isinstance(out, dict), "stale store must produce a banner"
    assert "out of date" in out["en"]
    assert "stale" not in out["en"], "internal state token leaked into user copy"
    assert "stale" not in out["zh"]


def test_w1_banner_dead_and_empty_use_unavailable_copy():
    """'dead' and an empty store both read 'Leverage data unavailable'."""
    from engine.hk_cbbc import _w1_banner
    for freshness, store_empty in (("dead", False), ("fresh", True)):
        out = _w1_banner(freshness, store_empty)
        assert isinstance(out, dict), f"({freshness!r}, {store_empty}) must produce a banner"
        assert out["en"] == "Leverage data unavailable"
        assert out["zh"] == "杠杆数据不可用"
        assert "dead" not in out["en"], "internal state token leaked into user copy"


def test_w1_banner_none_when_healthy():
    """'fresh' and 'slow' with a populated store produce no banner."""
    from engine.hk_cbbc import _w1_banner
    assert _w1_banner("fresh", False) is None
    assert _w1_banner("slow", False) is None


def test_w1_banner_shape():
    """Every returned banner has exactly en+zh keys, both non-empty strings."""
    from engine.hk_cbbc import _w1_banner
    for freshness, store_empty in (("stale", False), ("dead", False), ("fresh", True)):
        out = _w1_banner(freshness, store_empty)
        assert set(out.keys()) == {"en", "zh"}, f"unexpected keys: {sorted(out)}"
        for k in ("en", "zh"):
            assert isinstance(out[k], str) and out[k].strip(), f"{k} must be a non-empty string"


# ---------------------------------------------------------------------------
# Template parse sanity
# ---------------------------------------------------------------------------

def test_template_parses_without_syntax_error():
    """hk.html.j2 must still parse after the banner wiring."""
    from jinja2 import Environment
    src = (ROOT / "templates" / "hk.html.j2").read_text(encoding="utf-8")
    Environment(autoescape=False).parse(src)
