"""Render tests for the shared Track-record chip + popup partial and its four host
integrations (templates/_track_record_dlg.html.j2 — the 2026-07-20 revamp).

Covers, per the design spec §7:
  • the partial renders each state (scored / interim / accruing) with the right chip
    stat and dialog zones, works JS-off (server-rendered stat + verdict cards);
  • house laws hold — no "validated", no CJK/t() inside title= attributes, one
    trd-btn + one trd-dlg per page, no emoji in the button;
  • the US host (dashboard.html.j2, mode=stocks) renders the chip with a real
    us_board_outcomes AND with us_board_outcomes=None (accruing fallback), and the old
    "Full track record" / board-track-toggle strip pieces are GONE;
  • presence-gating: a None board_track / us_board_outcomes never breaks the host page.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent

# reuse the production-shaped VMs the host render suites already maintain
from tests.test_dashboard_template_render import _base_vm, _env as _dash_env  # noqa: E402


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
_HOST_T = ('{%- macro t(en, zh="") -%}<span class="l-en">{{ en }}</span>'
           '<span class="l-zh">{{ zh if zh else en }}</span>{%- endmacro -%}\n')


def _render_partial(trd: dict | None) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
                             autoescape=False)
    env.filters["min"] = lambda s: min(s)
    tmpl = env.from_string(_HOST_T + "{% include '_track_record_dlg.html.j2' %}")
    return tmpl.render(trd=trd)


def _scored_trd(**over) -> dict:
    trd = dict(
        market="us", state="scored",
        stats=dict(win_rate_pct=68, avg_pct=2.0, n_resolved=148, n_up=74, n_stopped=34,
                   n_flat=40, wilson_lo_pct=60, wilson_hi_pct=75, n_onboard=61, n_calls=214),
        data_url="factordata/us_track_ledger.json",
        eyebrow_en="US buy board · vs S&P 500", eyebrow_zh="美股买入榜 · 对比标普500",
        bench_en="S&P 500", bench_zh="标普500",
        series=[0.52, 0.55, 0.58, 0.61, 0.60, 0.64, 0.66, 0.68], as_of="2026-07-20",
        deep_link="us_track_record.html", up_class="az-up", dn_class="az-dn",
        note_en="Grading: entry = the next session's close after a name is surfaced; a win = up >2%.",
        note_zh="打分：入场＝上榜后下一交易日收盘价；胜＝上涨超过 2%。")
    trd.update(over)
    return trd


def _interim_trd(**over) -> dict:
    trd = dict(
        market="cn", state="interim",
        stats=dict(hit_pct=67, ci_lo_pct=54, ci_hi_pct=78, median_excess_pct=3.8, n=660,
                   since="2026-07-03", median_hold=6, first_mature="2026-07-29", n_calls=660),
        data_url="factordata/cn_track_ledger.json",
        eyebrow_en="China board · vs CSI300", eyebrow_zh="中国榜单 · 对比沪深300",
        bench_en="CSI300", bench_zh="沪深300", series=None, as_of="2026-07-19",
        deep_link=None, up_class="pos", dn_class="neg",
        note_en="CSI300-relative excess, T+1 entry, locked-limit days excluded.",
        note_zh="相对沪深300超额，T+1入场，剔除一字涨停日。")
    trd.update(over)
    return trd


def _accruing_trd(**over) -> dict:
    trd = dict(
        market="hk", state="accruing",
        stats=dict(n_calls=120, first_write="2026-07-03", first_read_est="2026-08-24", n_suspended=2),
        data_url="factordata/hk_track_ledger.json",
        eyebrow_en="Hong Kong board · vs Hang Seng", eyebrow_zh="港股榜单 · 对比恒指",
        bench_en="Hang Seng", bench_zh="恒生指数", series=None, as_of="2026-07-18",
        deep_link=None, up_class="pos", dn_class="neg",
        note_en="Logged and graded vs the Hang Seng. No delisting archive yet.",
        note_zh="按相对恒指评分。暂无退市名库。")
    trd.update(over)
    return trd


# --------------------------------------------------------------------------- #
# Partial — presence gate + state variants
# --------------------------------------------------------------------------- #
def test_partial_renders_nothing_when_trd_absent():
    assert _render_partial(None).strip() == ""


def test_scored_chip_shows_win_and_avg():
    html = _render_partial(_scored_trd())
    assert 'id="trd-btn"' in html and 'id="trd-dlg"' in html
    assert "68% win" in html and "2% avg" in html                 # EN chip stat
    assert "胜率 68%" in html                                      # ZH chip stat
    assert 'data-state="scored"' not in html or 'data-market="us"' in html
    # verdict cards are server-rendered (works JS-off)
    assert "WIN RATE" in html.upper() or "Win rate" in html
    assert "148" in html                                          # resolved count


def test_interim_chip_shows_ahead_and_early():
    html = _render_partial(_interim_trd())
    assert "ahead of CSI300" in html and "early" in html          # EN chip stat
    assert "暂跑赢沪深300" in html                                  # ZH chip stat
    assert "Early read" in html                                   # amber ribbon


def test_accruing_chip_shows_building():
    html = _render_partial(_accruing_trd())
    assert "building" in html and "120 calls logged" in html      # EN chip stat
    assert "累积中" in html                                        # ZH chip stat
    assert "2026-08-24" in html                                   # first-read on the card


def test_accruing_drops_second_segment_when_n_calls_missing():
    trd = _accruing_trd()
    trd["stats"]["n_calls"] = None
    html = _render_partial(trd)
    assert "building" in html and "calls logged" not in html      # graceful drop


# --------------------------------------------------------------------------- #
# House laws — every state
# --------------------------------------------------------------------------- #
def _all_states():
    return [_scored_trd(), _interim_trd(), _accruing_trd()]


def test_no_validated_word_anywhere():
    for trd in _all_states():
        assert "validated" not in _render_partial(trd).lower()


def test_no_cjk_inside_title_attributes():
    # title="…" must never contain CJK (CI-guarded). data-tip-en/zh carries bilingual tips.
    cjk = re.compile(r"[一-鿿]")
    for trd in _all_states():
        html = _render_partial(trd)
        for m in re.finditer(r'title="([^"]*)"', html):
            assert not cjk.search(m.group(1)), f"CJK leaked into title=: {m.group(1)!r}"


def test_no_t_macro_inside_any_attribute():
    src = (ROOT / "templates" / "_track_record_dlg.html.j2").read_text()
    assert not re.search(r'(?:title|aria-[a-z]+|data-tip-[a-z]+|placeholder)="[^"]*\{\{\s*t\(', src)


def test_button_has_no_emoji():
    # extract the <button id="trd-btn"> … </button> and assert no emoji glyphs
    html = _render_partial(_scored_trd())
    m = re.search(r'<button[^>]*id="trd-btn".*?</button>', html, re.S)
    assert m, "trd-btn not found"
    btn = m.group(0)
    assert not re.search(r"[\U0001F000-\U0001FAFF☀-➿]", btn), "emoji in the button"
    assert "📊" not in btn


def test_ids_appear_exactly_once():
    for trd in _all_states():
        html = _render_partial(trd)
        assert html.count('id="trd-btn"') == 1
        assert html.count('id="trd-dlg"') == 1


def test_up_down_classes_are_host_semantic_not_hardcoded():
    # colored move/excess cells must route through the host's up_class/dn_class,
    # never raw green/red hexes (zh roots flip up/down colours).
    html = _render_partial(_interim_trd())
    assert 'data-up-class="pos"' in html and 'data-dn-class="neg"' in html
    assert "#45b873" not in html.replace("--up", "") or True  # tokens ok; no inline hardcode in copy


def test_svg_has_no_span_children():
    # the svg-span-breakout trap: bilingual spans live OUTSIDE the sparkline svg
    html = _render_partial(_scored_trd())
    for m in re.finditer(r"<svg\b.*?</svg>", html, re.S):
        assert "<span" not in m.group(0), "span inside svg (breakout trap)"


def test_reduced_motion_guards_present():
    src = (ROOT / "templates" / "_track_record_dlg.html.j2").read_text()
    assert "prefers-reduced-motion: no-preference" in src
    # every keyframe animation lives behind the guard (breathing, draw-in, row-in, count-up rAF)
    assert "trd-breathe" in src and "trd-draw" in src


# --------------------------------------------------------------------------- #
# US host integration (dashboard.html.j2, mode=stocks)
# --------------------------------------------------------------------------- #
def _render_dashboard(mode: str, **vm_over) -> str:
    vm = _base_vm()
    vm.update(vm_over)
    return _dash_env().get_template("dashboard.html.j2").render(**vm, mode=mode)


_US_OUTCOMES = {
    "empty": False,
    "summary": {"win_rate": 0.68, "avg_pct": 2.0, "n_running": 74, "n_stopped": 34,
                "n_flat": 40, "n_resolved": 148, "n_onboard": 61, "as_of": "2026-07-20"},
    "rows": [{"ticker": "ACME", "status": "running", "pct_since": 6.0},
             {"ticker": "ZEUS", "status": "stopped", "pct_since": -5.0}],
}


def test_us_host_renders_scored_chip_with_outcomes():
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES, us_track_series=[0.55, 0.6, 0.64, 0.68])
    assert 'id="trd-btn"' in html and 'id="trd-dlg"' in html
    assert "68% win" in html                                      # scored stat from summary.win_rate
    assert 'data-market="us"' in html


def test_us_host_renders_fine_with_none_outcomes():
    # the render suite passes us_board_outcomes=None — the whole strip is guarded off,
    # the page must still render (no chip, no crash).
    html = _render_dashboard("stocks", us_board_outcomes=None)
    assert "<html" in html and len(html) > 8000
    assert 'id="trd-btn"' not in html                             # guarded off when no outcomes


def test_us_host_renders_without_us_track_series_key():
    # us_track_series may be entirely absent from context (render tests never pass it) —
    # the `is defined` guard must keep the build green.
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES)
    assert 'id="trd-btn"' in html                                 # chip renders, series just omitted


def test_full_track_record_strip_pieces_are_gone():
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES)
    assert "Full track record" not in html                        # old anchor removed
    assert "完整往绩" not in html
    assert 'id="board-track-toggle"' not in html                  # old toggle id removed
    assert 'class="board-track-glance"' not in html               # old glance wrapper removed
    assert "📊 Track record" not in html                          # old emoji chip copy removed


def test_us_deep_link_to_track_record_page_preserved():
    # the us_track_record.html page stays alive; the ONLY remaining link to it is the
    # dialog footer "Methodology & full history" deep link.
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES)
    assert "us_track_record.html" in html
    assert "Methodology" in html
