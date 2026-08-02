"""Unit tests for lib.illus (the ilx / Signal-Ink SSR renderer)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import re

from lib import illus as I


def _dates(n):
    return [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]


def test_line_basic_shape():
    n = 30
    out = I.illus({"dates": _dates(n), "vals": list(range(n))}, kind="line",
                  accent="var(--info)", unit_en="%", unit_zh="%")
    assert out.startswith("<figure class=\"ilx ilx-line\"")
    assert 'preserveAspectRatio="none"' in out
    assert "--ilx-len:" in out
    assert 'role="img"' in out
    assert "<script" not in out.lower()
    # end tag carries value + bilingual unit spans
    assert 'class="ilx-tag"' in out
    assert '<span class="l-en">%</span><span class="l-zh">%</span>' in out


def test_no_svg_text_element():
    # SVG must carry NO <text> (preserveAspectRatio=none would warp it).
    out = I.illus({"dates": _dates(20), "vals": [i * 1.5 for i in range(20)]},
                  kind="line", accent="var(--warn)", unit_en="亿")
    svg = out[out.index("<svg"):out.index("</svg>")]
    assert "<text" not in svg
    assert "<tspan" not in svg


def test_empty_series_null():
    out = I.illus({"dates": [], "vals": []}, kind="line")
    assert "ilx-null" in out
    assert '<span class="l-en">No history yet</span>' in out
    assert '<span class="l-zh">暂无历史</span>' in out
    # never a fabricated path
    assert 'class="ilx-path"' not in out


def test_short_series_null():
    out = I.illus({"dates": _dates(3), "vals": [1, 2, 3]}, kind="line")
    assert "ilx-null" in out


def test_none_and_nan_dropped_then_null():
    # 3 real points after cleaning -> still a null (need >=4)
    out = I.illus({"dates": _dates(5), "vals": [1, None, float("nan"), 4, None]},
                  kind="line")
    assert "ilx-null" in out


def test_downsample_preserves_extremes():
    # a spike in the middle of a long flat series must survive downsampling
    n = 2000
    vals = [0.0] * n
    spike_hi, spike_lo = 900, 1200
    vals[spike_hi] = 99.0
    vals[spike_lo] = -99.0
    pairs = list(zip(_dates(n), vals))
    kept = I._downsample(pairs, 220)
    assert len(kept) <= 260  # bounded
    kept_vals = [v for _d, v in kept]
    assert max(kept_vals) == 99.0, "positive spike lost in downsample"
    assert min(kept_vals) == -99.0, "negative spike lost in downsample"
    # endpoints preserved
    assert kept[0] == pairs[0]
    assert kept[-1] == pairs[-1]


def test_downsample_noop_when_short():
    pairs = list(zip(_dates(10), range(10)))
    assert I._downsample(pairs, 220) == pairs


def test_baseline_splits_up_down():
    # values crossing 0 with kind=baseline produce both up and down tinted paths
    vals = [-3, -1, 1, 3, 1, -2, -4, 2, 5]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="baseline",
                  baseline=0, unit_en="亿")
    assert "ilx-up" in out and "ilx-down" in out
    assert "ilx-water" in out          # dashed waterline present
    assert "var(--up)" in out and "var(--down)" in out  # bound directly for ZH swap
    # two clip paths, one per side
    assert out.count("<clipPath") == 2


def test_drawdown_underwater():
    vals = [0, -2, -8, -15, -6, -3, -20, -1]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="drawdown", unit_en="%")
    assert "ilx-drawdown" in out
    assert "var(--down)" in out
    assert "ilx-water-top" in out


def test_bars_signed_when_baseline():
    vals = [2, -1, 3, -4, 1, -2, 5, -3]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="bars",
                  baseline=0, unit_en="%")
    assert "ilx-bars" in out
    assert "ilx-bar-up" in out and "ilx-bar-down" in out
    assert "<rect" in out
    # per-bar stagger index emitted
    assert "--i:0" in out


def test_bars_unsigned_no_baseline():
    vals = [1, 2, 3, 4, 5, 6]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="bars")
    assert "ilx-bar-up" not in out and "ilx-bar-down" not in out
    assert out.count("<rect") == len(vals)


def test_unique_gradient_ids():
    # two area charts with different data must not share gradient ids (id collision
    # would make one steal the other's fill on a shared page)
    a = I.illus({"dates": _dates(20), "vals": list(range(20))}, kind="area")
    b = I.illus({"dates": _dates(20), "vals": list(range(20, 0, -1))}, kind="area")
    ids_a = set(re.findall(r'id="(ilxg-[0-9a-f]+)"', a))
    ids_b = set(re.findall(r'id="(ilxg-[0-9a-f]+)"', b))
    assert ids_a and ids_b
    assert ids_a.isdisjoint(ids_b), f"gradient id collision: {ids_a & ids_b}"


def test_baseline_unique_clip_ids():
    a = I.illus({"dates": _dates(20), "vals": [i - 10 for i in range(20)]}, kind="baseline", baseline=0)
    b = I.illus({"dates": _dates(20), "vals": [10 - i for i in range(20)]}, kind="baseline", baseline=0)
    ids_a = set(re.findall(r'id="(ilxc[tb]-[0-9a-f]+)"', a))
    ids_b = set(re.findall(r'id="(ilxc[tb]-[0-9a-f]+)"', b))
    assert ids_a.isdisjoint(ids_b)


def test_multi_end_chips():
    s = [
        {"label_en": "Growth", "label_zh": "增长", "color": "var(--up)",
         "dates": _dates(20), "vals": list(range(20))},
        {"label_en": "Inflation", "label_zh": "通胀", "color": "var(--down)",
         "dates": _dates(20), "vals": list(range(20, 0, -1))},
    ]
    out = I.illus(s, kind="multi")
    assert "ilx-multi" in out
    assert 'class="ilx-chip"' in out
    assert out.count('class="ilx-chip"') == 2
    assert '<span class="l-en">Growth</span><span class="l-zh">增长</span>' in out
    assert '<span class="l-en">Inflation</span><span class="l-zh">通胀</span>' in out
    # per-series colors applied to strokes
    assert "stroke:var(--up)" in out and "stroke:var(--down)" in out


def test_multi_empty_null():
    out = I.illus([], kind="multi")
    assert "ilx-null" in out


def test_multi_baseline_rule():
    # signed series (regime scores) with a zero baseline draw a dashed waterline;
    # without a baseline no rule is emitted (backward compatible).
    s = [
        {"label_en": "Growth", "label_zh": "增长", "color": "var(--info)",
         "dates": _dates(20), "vals": [i - 10 for i in range(20)]},
        {"label_en": "Inflation", "label_zh": "通胀", "color": "var(--orange)",
         "dates": _dates(20), "vals": [10 - i for i in range(20)]},
    ]
    with_base = I.illus(s, kind="multi", baseline=0)
    assert "ilx-water" in with_base           # dashed zero rule present
    assert with_base.count("ilx-water") == 1  # exactly one rule
    no_base = I.illus(s, kind="multi")
    assert "ilx-water" not in no_base          # none without a baseline


def test_bands_render():
    vals = [10, 30, 55, 72, 85, 40, 20, 15, 60, 78]
    bands = [
        {"hi": 100, "lo": 70, "tint": "color-mix(in srgb, var(--warn) 14%, transparent)",
         "label_en": "Euphoria", "label_zh": "亢奋", "pos": "top"},
        {"hi": 30, "lo": 0, "tint": "color-mix(in srgb, var(--info) 14%, transparent)",
         "label_en": "Fear", "label_zh": "恐惧", "pos": "bottom"},
    ]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="line",
                  accent="#c08bd8", bands=bands, height=160)
    assert "ilx-band" in out
    assert '<span class="l-en">Euphoria</span>' in out
    assert '<span class="l-en">Fear</span>' in out


def test_reference_level():
    vals = [95, 98, 101, 103, 99, 97, 102, 100]
    out = I.illus({"dates": _dates(len(vals)), "vals": vals}, kind="line",
                  accent="var(--orange)", reference=100, unit_en="")
    assert "ilx-ref" in out
    assert "ilx-reflab" in out
    assert ">100<" in out


def test_accent_on_root():
    out = I.illus({"dates": _dates(10), "vals": list(range(10))}, kind="line",
                  accent="#c08bd8")
    assert "color:#c08bd8" in out


def test_no_script_anywhere():
    # every kind must be script-free (SSR safety)
    for kind in ("line", "area", "bars", "baseline", "drawdown"):
        out = I.illus({"dates": _dates(12), "vals": [i - 6 for i in range(12)]},
                      kind=kind, baseline=0)
        assert "<script" not in out.lower()
        assert "javascript:" not in out.lower()
    multi = I.illus([{"label_en": "a", "dates": _dates(8), "vals": list(range(8))}],
                    kind="multi")
    assert "<script" not in multi.lower()


def test_value_fmt_applied():
    out = I.illus({"dates": _dates(8), "vals": [1234.567] * 8}, kind="line",
                  value_fmt="{:,.0f}", unit_en="亿")
    assert "1,235" in out


def test_html_escaped_in_labels():
    s = [{"label_en": "a<b>&", "dates": _dates(8), "vals": list(range(8))}]
    out = I.illus(s, kind="multi")
    assert "<b>" not in out
    assert "&lt;b&gt;" in out or "a&lt;b&gt;&amp;" in out


def test_regime_tape_renders_all_four_cockpit_forms():
    d0 = date(2024, 1, 1)
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(731)]
    prices = [40_000 + i * 55 + (i % 31) * 120 for i in range(len(dates))]
    alloc = [0.25 if i < 180 else 0.65 if i < 520 else 0.0 for i in range(len(dates))]
    out = I.regime_tape(
        {"dates": dates, "vals": prices},
        allocation={"dates": dates, "vals": alloc},
        regimes=[
            {"start": "2024-01-01", "end": "2024-08-01", "tone": "bull"},
            {"start": "2024-08-01", "end": "2025-03-01", "tone": "neutral"},
            {"start": "2025-03-01", "end": "2026-01-01", "tone": "bear"},
        ],
        events=[{"date": "2024-04-20", "label_en": "Fourth halving",
                 "label_zh": "第四次减半"}],
        projection={"start": "2025-12-01", "end": "2026-03-01",
                    "label_en": "Watch window", "label_zh": "观察窗口"},
        max_points=24,
    )
    assert out.startswith('<figure class="ilx ilx-regime-tape"')
    assert "ilx-regime-span" in out            # regime spans
    assert "ilx-alloc-step" in out             # step ribbon
    assert "ilx-event-tick" in out             # baseline event tick
    assert "ilx-projection-hatch" in out        # hatched forward span
    assert 'data-tip-en="Fourth halving"' in out
    assert '<span class="l-zh">观察窗口</span>' in out
    assert "<text" not in out                   # SVG remains path-only
    assert "<script" not in out.lower()


def test_regime_tape_event_x_uses_calendar_not_downsample_position():
    """Halving alignment cannot drift when a 2y daily tape is cut to 20 points."""
    d0 = date(2024, 1, 1)
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(731)]
    vals = [50_000 + i + (10_000 if i == 417 else 0) for i in range(len(dates))]
    out = I.regime_tape(
        {"dates": dates, "vals": vals},
        events=[{"date": "2024-04-20", "label_en": "Halving"}],
        max_points=20,
    )
    expected = I._date_x("2024-04-20", "2024-01-01", "2025-12-31")
    match = re.search(r'class="ilx-event-tick" x1="([0-9.]+)"', out)
    assert match, "event tick missing"
    assert abs(float(match.group(1)) - expected) < 0.01
    expected_pct = round(expected / I._VBW * 100, 2)
    assert f'--x:{expected_pct}%' in out


def test_regime_tape_mixes_datetime_history_with_iso_projection_dates():
    d0 = datetime(2024, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(731)]
    out = I.regime_tape(
        {"dates": dates, "vals": [50_000 + i for i in range(len(dates))]},
        projection={"start": "2026-01-01", "end": "2026-04-01"},
        max_points=20,
    )
    path = re.search(r'class="ilx-path ilx-tape-price" d="([^"]+)"', out)
    assert path is not None
    xs = [float(x) for x in re.findall(r"(?:M|L)([0-9.]+) ", path.group(1))]
    # Two years of history followed by a three-month projection should occupy
    # most of the canvas, not collapse under a mixed epoch/ordinal scale.
    assert xs[-1] > 480


# ═══════════════════════════════════════════════════════════════════════════════
# session_filmstrip — OIP W1 estate-wide signature (W1_DESIGN_SPEC.md §3)
# ═══════════════════════════════════════════════════════════════════════════════

def _record(**overrides):
    base = {
        "coverage": {
            "minutes": 300, "expected": 391,
            "quality_en": "the intraday record covers most of the session",
            "quality_zh": "盘中记录覆盖了大部分交易时段",
            "session_window_et": "09:30–16:00 ET",
        },
        "arc": [
            {"t": "09:30", "net": 0, "ncp": None, "npp": None},
            {"t": "11:00", "net": 500, "ncp": None, "npp": None},
            {"t": "13:00", "net": 1200, "ncp": None, "npp": None},
            {"t": "15:00", "net": 900, "ncp": None, "npp": None},
            {"t": "16:00", "net": 2000, "ncp": None, "npp": None},
        ],
        "events": [
            {"t": "12:15", "type": "flip_cross", "label_en": "price crossed the gamma flip level",
             "label_zh": "价格穿越 gamma 翻转价位"},
        ],
        "arc_shape_en": "built steadily in one direction and stayed",
        "arc_shape_zh": "全天单向累积并维持",
        "flip": {"crosses": 2, "last_side": "above"},
    }
    base.update(overrides)
    return base


def test_session_filmstrip_present_data_draws_ink_dot_and_ticks():
    out = I.session_filmstrip(_record())
    assert out.startswith('<figure class="ilx oew-film" role="img"')
    assert "oew-film-null" not in out
    assert 'class="oew-film-track"' in out
    assert 'class="oew-film-closecap"' in out
    # ink + dot carry BOTH the generic ilx reveal hook and the filmstrip-specific
    # static class — the reduced-motion / draw-on-reveal choreography is 100%
    # inherited from the shared .ilx-path/.ilx-dot rules, nothing bespoke here.
    assert 'class="ilx-path oew-film-ink"' in out
    assert 'class="ilx-dot oew-film-dot"' in out
    assert 'class="ilx-event-tick oew-film-tick"' in out
    assert 'class="ilx-event oew-film-ev"' in out
    assert out.count('class="ilx-event-tick oew-film-tick"') == 1
    assert out.count('class="ilx-event oew-film-ev"') == 1
    assert 'data-tip-en="price crossed the gamma flip level"' in out
    assert 'data-tip-zh="价格穿越 gamma 翻转价位"' in out
    # ink is ALWAYS --oew-accent, never --up/--down (masterplan §0.8/§0.5): the
    # arc's sign is not a sanctioned direction instrument.
    assert 'style="color:var(--oew-accent);' in out
    assert "--up" not in out and "--down" not in out
    # corner labels are bare mono spans (language-neutral figures — no .l-en/
    # .l-zh wrapper, matching the house _corner_labels() precedent for dates).
    assert '<span class="oew-film-d oew-film-d0 mono">09:30</span>' in out
    assert '<span class="oew-film-d oew-film-d1 mono">16:00</span>' in out
    assert "Session premium arrival, 1 event" in out


def test_session_filmstrip_pluralizes_event_count_in_aria_label():
    out = I.session_filmstrip(_record(events=[
        {"t": "10:00", "type": "premium_burst", "label_en": "a", "label_zh": "b"},
        {"t": "11:00", "type": "hot_pocket", "label_en": "c", "label_zh": "d"},
    ]))
    assert "Session premium arrival, 2 events" in out
    out0 = I.session_filmstrip(_record(events=[]))
    assert "Session premium arrival, 0 events" in out0


def test_session_filmstrip_honest_null_on_zero_minutes():
    """coverage.minutes === 0 -> no ink, no ticks, no dot (§3.3) — only the flat
    track and the session's own composed absence sentence, verbatim."""
    out = I.session_filmstrip(_record(coverage={
        "minutes": 0, "expected": 391,
        "quality_en": "no intraday record for this session",
        "quality_zh": "本交易日没有盘中记录",
        "session_window_et": "09:30–16:00 ET",
    }))
    assert 'class="ilx oew-film oew-film-null"' in out
    assert "oew-film-ink" not in out
    assert "oew-film-dot" not in out
    assert "oew-film-tick" not in out
    assert '<span class="l-en">no intraday record for this session</span>' in out
    assert '<span class="l-zh">本交易日没有盘中记录</span>' in out
    assert 'aria-label="no intraday record for this session"' in out
    # the close-cap still marks the session's own boundary independent of data
    # completeness — present in BOTH variants.
    assert 'class="oew-film-closecap"' in out


def test_session_filmstrip_degrades_on_missing_or_zero_coverage():
    assert "oew-film-null" in I.session_filmstrip({})
    assert "oew-film-null" in I.session_filmstrip(_record(coverage=None))
    assert "oew-film-null" in I.session_filmstrip(_record(coverage={"minutes": None}))


def test_session_filmstrip_degrades_on_unparseable_session_window():
    """A malformed/missing session_window_et must fall back to the honest-null
    variant rather than crash or misrepresent the geometry — defensive beyond
    the spec's literal minutes==0 check, since there is no valid time axis to
    plot points against."""
    out = I.session_filmstrip(_record(coverage={
        "minutes": 300, "expected": 391, "quality_en": "q", "quality_zh": "q2",
        "session_window_et": None,
    }))
    assert "oew-film-null" in out


def test_session_filmstrip_degrades_on_too_few_arc_points():
    out = I.session_filmstrip(_record(arc=[{"t": "09:30", "net": 1, "ncp": None, "npp": None}]))
    assert "oew-film-null" in out
    out2 = I.session_filmstrip(_record(arc=[]))
    assert "oew-film-null" in out2


def test_session_filmstrip_x_is_elapsed_time_not_index_position():
    """x = (minutes since open) / (session length) * 560 — NOT array-index
    spacing, so an uneven-interval arc (a mid-session gap) reads as compressed
    time rather than a lie about when the gap happened."""
    out = I.session_filmstrip(_record(arc=[
        {"t": "09:30", "net": 0, "ncp": None, "npp": None},   # elapsed 0 / 390 -> x=0
        {"t": "12:45", "net": 100, "ncp": None, "npp": None}, # elapsed 195 / 390 -> x=280
        {"t": "16:00", "net": 200, "ncp": None, "npp": None}, # elapsed 390 / 390 -> x=560
    ]))
    path = re.search(r'class="ilx-path oew-film-ink" d="([^"]+)"', out)
    assert path is not None
    xs = [float(x) for x in re.findall(r"(?:M|L)([0-9.]+) ", path.group(1))]
    assert xs == [0.0, 280.0, 560.0]


def test_session_filmstrip_y_is_a_shape_not_an_absolute_axis():
    """net scaled to its OWN min/max within [10, 54] — the pinned geometry
    contract (W1_DESIGN_SPEC.md §3.3), not the generic ilx _PAD_T/_PAD_B."""
    out = I.session_filmstrip(_record(arc=[
        {"t": "09:30", "net": -50, "ncp": None, "npp": None},   # min -> y=54 (bottom)
        {"t": "12:45", "net": 0, "ncp": None, "npp": None},
        {"t": "16:00", "net": 50, "ncp": None, "npp": None},    # max -> y=10 (top)
    ]))
    path = re.search(r'class="ilx-path oew-film-ink" d="([^"]+)"', out)
    ys = [float(y) for y in re.findall(r"(?:M|L)[0-9.]+ ([0-9.]+)", path.group(0))]
    assert ys[0] == 54.0
    assert ys[-1] == 10.0
    assert all(10.0 <= y <= 54.0 for y in ys)


def test_session_filmstrip_flat_series_does_not_crash():
    out = I.session_filmstrip(_record(arc=[
        {"t": "09:30", "net": 5, "ncp": None, "npp": None},
        {"t": "12:00", "net": 5, "ncp": None, "npp": None},
        {"t": "16:00", "net": 5, "ncp": None, "npp": None},
    ]))
    assert "oew-film-ink" in out


def test_session_filmstrip_never_raises_on_garbage_input():
    for bad in (None, {}, {"coverage": "not a dict"}, {"arc": "nope"}, {"events": 5},
                {"coverage": {"minutes": "not a number"}}):
        out = I.session_filmstrip(bad)
        assert out.startswith("<figure")


def test_session_filmstrip_close_cap_always_at_track_end():
    """The close-cap is a static mark at x=560 always present — it marks the
    session boundary independent of how much of the track the ink covers."""
    partial = I.session_filmstrip(_record(coverage={
        "minutes": 120, "expected": 391, "quality_en": "the intraday record covers only part of the session",
        "quality_zh": "盘中记录仅覆盖部分交易时段", "session_window_et": "09:30–16:00 ET",
    }, arc=[
        {"t": "09:30", "net": 0, "ncp": None, "npp": None},
        {"t": "11:30", "net": 10, "ncp": None, "npp": None},
    ]))
    assert 'class="oew-film-closecap" x1="560" y1="14" x2="560" y2="50"' in partial
    # the ink itself must NOT reach x=560 — a stopped-early tape leaves bare
    # track after the dot, which IS the coverage disclosure (no separate hatch).
    path = re.search(r'class="ilx-path oew-film-ink" d="([^"]+)"', partial)
    xs = [float(x) for x in re.findall(r"(?:M|L)([0-9.]+) ", path.group(1))]
    assert xs[-1] < 560.0


def test_session_filmstrip_ilx_css_carries_the_new_static_rules_only():
    """The filmstrip must add ZERO bespoke @keyframes / animation-* rules of its
    own — it inherits the shared .ilx-path/.ilx-dot/.ilx-event/.ilx-event-tick
    reveal + reduced-motion choreography entirely (templates/illus.css's single
    `@media (prefers-reduced-motion: reduce)` block already covers every ilx
    figure on the site, this one included, via those shared classes)."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "templates" / "illus.css").read_text()
    film_block = css[css.index(".oew-film {"):css.index("/* ── honest null")]
    assert "@keyframes" not in film_block
    assert "animation:" not in film_block
    assert "animation-name" not in film_block
    # the two local token-fallback declarations exist so gex.html (no .oew
    # ancestor) still resolves --oew-accent/--oew-stamp/--hair correctly.
    assert "--oew-accent: #8e97c8;" in film_block
    assert "--oew-accent: #4c55a8;" in css[css.index('html[data-theme="light"] .oew-film'):]
