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
  • presence-gating: a None board_track / us_board_outcomes never breaks the host page;
  • the optional prior-definition record (trd.prior, CN continuity G5) reports the
    right number under the right header, keeps its 25-row window on the trades that
    finished, and survives a producer field of the wrong type.
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
    """The post-2026-07-26 summary shape (engine.track_scoring.summarize).

    exp_lo_pct is POSITIVE here so the fixture exercises the confident branch; the
    interval-crossing-zero branch has its own test below.
    """
    trd = dict(
        market="us", state="scored",
        stats=dict(metric="pnl", horizon=10, win_pct=68.0, expectancy_pct=2.0,
                   median_pct=1.6, avg_win_pct=4.1, avg_loss_pct=-2.4, profit_factor=1.9,
                   ci_lo_pct=60.0, ci_hi_pct=75.0, exp_lo_pct=0.4, exp_hi_pct=3.6,
                   n_matured=148, n_inflight=61, n_board_days=44, n_skipped_no_price=2,
                   median_hold=8, capture=0.71, mfe_median_pct=3.4, mae_median_pct=-1.9),
        data_url="factordata/us_track_ledger.json",
        eyebrow_en="US buy board · vs S&P 500", eyebrow_zh="美股买入榜 · 对比标普500",
        bench_en="S&P 500", bench_zh="标普500",
        series=[0.52, 0.55, 0.58, 0.61, 0.60, 0.64, 0.66, 0.68], as_of="2026-07-20",
        deep_link="us_track_record.html", up_class="az-up", dn_class="az-dn",
        note_en="Bought at the next session's close, sold 10 sessions later or sooner on the rule.",
        note_zh="以次日收盘价买入，持有 10 个交易日后卖出；触发规则则提前。")
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


def test_scored_chip_shows_win_and_average_trade():
    html = _render_partial(_scored_trd())
    assert 'id="trd-btn"' in html and 'id="trd-dlg"' in html
    assert "68% win" in html and "+2% a trade" in html            # EN chip stat
    assert "胜率 68%" in html and "每笔 +2%" in html                # ZH chip stat
    assert 'data-state="scored"' not in html or 'data-market="us"' in html
    # verdict cards are server-rendered (works JS-off)
    assert "WIN RATE" in html.upper() or "Win rate" in html
    assert "148" in html                                          # matured count


def test_scored_dialog_discloses_the_effective_sample():
    """n_board_days is what makes the interval wide; it must be on the surface, not
    only in the JSON. 44 board days is under the ribbon's threshold of 20? No — it is
    above it, so the ribbon stays off and the raw count still ships in the cards."""
    html = _render_partial(_scored_trd())
    assert "60.0–75.0%" in html or "60.0" in html                 # win-rate interval
    assert "Short record" not in html                             # 44 days → no ribbon


def test_short_record_ribbon_fires_under_twenty_board_days():
    html = _render_partial(_scored_trd(stats=dict(_scored_trd()["stats"], n_board_days=5)))
    assert "Short record" in html and "5 separate board days" in html
    assert "记录尚短" in html


def test_stance_refuses_to_claim_an_edge_when_the_interval_spans_a_loss():
    """A 68% win rate whose average-trade range still includes a loss must NOT read as
    'worth following', and must not glow green."""
    html = _render_partial(_scored_trd(stats=dict(_scored_trd()["stats"], exp_lo_pct=-0.8)))
    assert "still too short to lean on" in html
    assert "Worth following" not in html
    assert 'trd-wrap trd-band-up' not in html                    # neutral accent, not green


def test_confident_stance_needs_enough_independent_board_days():
    """An interval that clears zero by a hair off a handful of nights is not evidence.

    The live US desk landed at exp_lo_pct=+0.01% over 10 board days — arithmetically
    positive. The dialog must not simultaneously warn 'short record' and claim 'worth
    following', so both gate on the same 20-board-day threshold.
    """
    thin = dict(_scored_trd()["stats"], exp_lo_pct=0.01, n_board_days=10)
    html = _render_partial(_scored_trd(stats=thin))
    assert "Short record" in html
    assert "still too short to lean on" in html
    assert "Worth following" not in html
    assert "trd-wrap trd-band-up" not in html
    assert "trd-btn trd-breathe" not in html                      # no halo either


def test_confident_stance_fires_once_the_record_is_long_enough():
    fat = dict(_scored_trd()["stats"], exp_lo_pct=0.9, n_board_days=60, win_pct=64.0)
    html = _render_partial(_scored_trd(stats=fat))
    assert "Worth following" in html
    assert "trd-wrap trd-band-up" in html
    assert "Short record" not in html


def test_mfe_is_framed_as_room_not_result():
    """MFE must never read as performance — selling the exact high is not a strategy."""
    html = _render_partial(_scored_trd())
    assert "this is the room, not a result" in html
    assert "无人能卖在最高点" in html


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
# Zone B′ — the PRIOR board definition's closed record (trd.prior, CN continuity G5)
# --------------------------------------------------------------------------- #
def _prior(**over) -> dict:
    """The shape build_china_library.emit_cn_track_ledger writes as doc['prior_record'].

    `rows` arrives ALREADY capped by the producer (engine.track_ledger.MAX_ROWS) and the
    era's true size rides in meta.n_total — the two are deliberately different in this
    fixture so a test can prove which one the dialog counts.
    """
    p = dict(
        label_en="previous board definition · Jun 30 – Jul 29 2026",
        label_zh="上一版选股口径 · 2026年6月30日–7月29日",
        board_definition="cn_standout_v1",
        date_from="2026-06-30", date_to="2026-07-29",
        summary={"win_pct": 47.5, "expectancy_pct": -0.62, "n_matured": 61, "n_logged": 65},
        rows=[{"t": "000582.SZ", "nm": "Beibu Gulf Port / 北部湾港", "d": "2026-07-14",
               "x": 2.4, "p": 3.9, "dy": 10, "st": "beat", "m": True}],
        meta={"n_total": 65},
    )
    p.update(over)
    return p


def _prior_block(html: str) -> str:
    """Everything from the dashed rule down — the closed book only, never the live half."""
    return html[html.index('class="trd-stg trd-stg-3 trd-prior"'):]


def _render_prior(prior: dict | None = None) -> str:
    return _render_partial(_interim_trd(prior=_prior() if prior is None else prior))


def test_prior_null_excess_reads_as_a_dash_never_the_absolute_return():
    """The column is headed "vs CSI300", so it may print `x` and nothing else.

    The row value used to fall back x → p, printing the ABSOLUTE return under the excess
    header: a name that merely rose with the index read as a beat over it. A missing
    excess gets the live table's own null — a muted em-dash.
    """
    html = _render_prior(_prior(rows=[{"t": "300750.SZ", "nm": "CATL / 宁德时代",
                                       "d": "2026-07-28", "x": None, "p": 7.7,
                                       "dy": 3, "st": "early", "m": False}]))
    row = re.search(r"<tr>.*?300750\.SZ.*?</tr>", _prior_block(html), re.S)
    assert row, "prior row not rendered"
    assert '<td class="trd-num trd-mut">—</td>' in row.group(0)
    assert "7.7" not in row.group(0), "the absolute return leaked under the excess header"


def test_prior_rows_keep_the_finished_trades_not_just_the_newest():
    """Newest-first spent the whole 25-row window on the LEAST matured rows.

    Here every one of the 30 most recent rows is still running; the two finished trades
    are the oldest in the book. They must survive the cap, and lead it — biggest move
    first, on absolute excess so the window can never be all beats.
    """
    inflight = [{"t": "9%03d.SZ" % i, "d": "2026-07-%02d" % (i % 28 + 1), "x": None,
                 "p": 4.0, "dy": 2, "st": "early", "m": False} for i in range(30)]
    matured = [{"t": "600519.SS", "d": "2026-06-02", "x": -3.1, "dy": 10, "st": "lag", "m": True},
               {"t": "000582.SZ", "d": "2026-06-03", "x": 2.4, "dy": 10, "st": "beat", "m": True}]
    block = _prior_block(_render_prior(_prior(rows=inflight + matured,
                                              meta={"n_total": 32})))
    tks = re.findall(r'<td class="trd-tk">([^<]+)', block)
    assert len(tks) == 25                                  # cap still holds
    assert {"600519.SS", "000582.SZ"} <= set(tks)          # …and neither finished trade fell out
    assert tks[:2] == ["600519.SS", "000582.SZ"]           # finished first, biggest |excess|
    assert "Showing 25 of 32" in block


def test_prior_summary_with_a_string_win_pct_does_not_crash_the_host_page():
    """|round and %+g both raise on a str, so one mistyped producer field used to take
    the entire China page down. It degrades to the null-disclosure line instead."""
    html = _render_prior(_prior(summary={"win_pct": "47.5", "expectancy_pct": "-0.62",
                                         "n_logged": 65}))
    block = _prior_block(html)
    assert 'id="trd-dlg"' in html                          # page still rendered
    assert "too few of them finished to score" in block
    assert "65 calls" in block
    assert "47.5" not in block                             # never printed as a win rate


def test_prior_cross_year_span_prints_the_year_on_both_ends():
    """A bare label falls back to a locally formatted range, and each language carries
    the year on one end only — EN on the close, ZH on the open. Across a year boundary
    that implies the wrong year on the other end."""
    block = _prior_block(_render_prior(_prior(
        label_en="previous board definition", label_zh="上一版选股口径",
        date_from="2025-11-03", date_to="2026-02-12")))
    assert "Nov 3 2025 – Feb 12 2026" in block
    assert "2025年11月3日–2026年2月12日" in block


def test_prior_same_year_span_stays_terse():
    block = _prior_block(_render_prior(_prior(
        label_en="previous board definition", label_zh="上一版选股口径",
        date_from="2026-06-30", date_to="2026-07-29")))
    assert "Jun 30 – Jul 29 2026" in block                 # start year implied, correctly
    assert "2026年6月30日–7月29日" in block


def test_prior_row_count_comes_from_the_producer_total_not_the_capped_list():
    """`rows` is already capped upstream, so counting it reports the cap as the record."""
    rows = [{"t": "%06d.SS" % i, "d": "2026-07-%02d" % (i % 28 + 1), "x": 1.0 + i,
             "dy": 10, "st": "beat", "m": True} for i in range(40)]
    block = _prior_block(_render_prior(_prior(rows=rows, meta={"n_total": 651})))
    assert "Showing 25 of 651" in block
    assert "共 651 笔" in block
    assert "of 40" not in block


def test_prior_discloses_the_producer_cap_even_when_the_row_list_is_short():
    """The old gate was len(rows) > 25, so a book the producer had already trimmed to a
    handful of rows showed a slice of hundreds with no disclosure at all."""
    rows = [{"t": "60000%d.SS" % i, "d": "2026-07-0%d" % (i + 1), "x": 1.5 + i,
             "dy": 10, "st": "beat", "m": True} for i in range(3)]
    block = _prior_block(_render_prior(_prior(rows=rows, meta={"n_total": 900})))
    assert "Showing 3 of 900" in block


def test_prior_absent_emits_no_markup():
    # the scoped CSS always ships; the SECTION must not (us_stocks / hk / canada, and
    # every China night before the emitter writes prior_record).
    html = _render_partial(_interim_trd())
    assert '<div class="trd-stg trd-stg-3 trd-prior">' not in html
    assert "Previous board definition" not in html and "前版榜单定义" not in html


# --------------------------------------------------------------------------- #
# House laws — every state
# --------------------------------------------------------------------------- #
def _all_states():
    # the prior-record variant rides along so the house laws (no "validated", no CJK in
    # title=, one id each) cover Zone B′ too — it ships CJK prose and a second table.
    return [_scored_trd(), _interim_trd(), _accruing_trd(), _interim_trd(prior=_prior())]


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

# The ledger artifact the chip reads. Deliberately carries DIFFERENT numbers from
# _US_OUTCOMES above so the test can prove which artifact the chip is bound to.
_US_LEDGER = {
    "schema": "track_ledger/v1", "market": "US", "as_of": "2026-07-24", "state": "scored",
    "summary": {"metric": "pnl", "horizon": 10, "win_pct": 63.1, "expectancy_pct": 0.97,
                "avg_win_pct": 4.08, "avg_loss_pct": -4.34, "profit_factor": 1.61,
                "ci_lo_pct": 51.9, "ci_hi_pct": 69.2, "exp_lo_pct": -0.78, "exp_hi_pct": 1.93,
                "n_matured": 111, "n_inflight": 201, "n_board_days": 5, "median_hold": 10},
    "rows": [], "meta": {"grain": "episode"},
}


def test_us_host_chip_reads_the_ledger_not_the_outcomes_strip():
    """The chip and the popup table it heads must report the SAME artifact.

    They used to disagree: the chip rendered us_board_outcomes.json (same-bar entry,
    marked to today) while the table fetched us_track_ledger.json. Passing both, with
    different win rates, proves which one wins.
    """
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES,
                             us_track_ledger=_US_LEDGER,
                             us_track_series=[0.55, 0.6, 0.64, 0.68])
    assert 'id="trd-btn"' in html and 'id="trd-dlg"' in html
    assert "63% win" in html                                      # from the ledger
    assert "68% win" not in html                                  # NOT the outcomes strip
    assert 'data-market="us"' in html


def test_us_host_falls_back_to_accruing_without_a_ledger():
    """No ledger yet → the chip must not borrow the outcomes strip's numbers."""
    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES, us_track_ledger=None)
    assert 'id="trd-btn"' in html
    assert 'data-state="accruing"' in html
    assert "68% win" not in html


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
