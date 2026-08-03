"""tests/test_chart_render_grammar.py — the TrendSpider-grade annotation grammar.

Covers the PR-A additions to ``engine/marketing/chart_render.render_chart_v2``
(masterplan: research/TRENDSPIDER_HARDENING_MASTERPLAN_BY_FABLE.md §3 PR-A):
real WEEKLY/MONTHLY timeframes, log scale, circle spotlights, zone bands,
trendlines, formation arcs, the measurement receipt box, right-axis level tags,
arbitrary SMA/EMA overlays, the streak and squeeze sub-panes, and the future
runway that the volume profile is drawn into.

TWO KINDS OF ASSERTION, on purpose:

  * The BACKWARD-COMPAT gate is byte-exact. ``legacy_baseline.svg`` was rendered
    from the pre-grammar renderer and is committed verbatim; a legacy call must
    still reproduce it byte for byte. That is the §0.1 acceptance gate and it is
    the one place where strictness is worth the maintenance.
  * Every other sample is asserted STRUCTURALLY (elements, colours, geometry,
    counts) against a freshly rendered SVG. Golden bytes for those would pin
    dozens of ``:.1f`` coordinates whose last digit can turn on a libm ULP, and
    a flaky guard is worse than a coarse one. The committed sample SVGs next to
    this file are the operator's VISUAL artifact (they are what the PR-body PNGs
    are rasterized from); ``CHART_GRAMMAR_REGEN=1 pytest tests/…`` rewrites
    them, and a staleness probe below fails when a sample no longer carries the
    primitive the fresh render produces.

The pinned fixture is an integer-cent LCG — no ``math.sin``, no ``random`` — so
every platform builds bit-identical doubles and the byte-exact golden cannot
drift on a libm difference.
"""
from __future__ import annotations

import math
import os
import pathlib
import re
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.marketing import chart_render as CR  # noqa: E402
from engine.marketing.chart_render import render_chart_v2  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "chart_render"
REGEN = os.environ.get("CHART_GRAMMAR_REGEN") == "1"

# Geometry the renderer hardcodes. Mirrored ONLY where a test cannot derive it
# from the output; everything pane-related is derived (see _price_pane) so a
# layout change fails loudly instead of silently invalidating a probe — the
# mirrored-constant rot that left test_chart_render_inline red on main for
# months after #3088 moved the MACD stroke.
PAD_L = 14
PAD_R = 72
DIVIDER = "#232A3D"


# ─────────────────────────────────────────────────────────────────────────────
# Pinned fixture
# ─────────────────────────────────────────────────────────────────────────────

_LCG_A, _LCG_C, _LCG_M = 1103515245, 12345, 0x7FFFFFFF


def pinned_ohlcv(n: int = 250, *, seed: int = 20260802, start: str = "2024-01-02"):
    """Deterministic weekday OHLCV built from integer cents (see module docstring)."""
    x = seed

    def nxt() -> int:
        nonlocal x
        x = (_LCG_A * x + _LCG_C) & _LCG_M
        return x

    d = date.fromisoformat(start)
    dates: list[str] = []
    o: list[float] = []
    h: list[float] = []
    l: list[float] = []
    c: list[float] = []
    v: list[float] = []
    close_c = 10_000
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        dates.append(d.isoformat())
        d += timedelta(days=1)
        open_c = close_c
        drift = 6 if (i // 40) % 3 != 1 else -9
        close_c = max(500, close_c + drift + (nxt() % 361) - 180)
        span = 40 + (nxt() % 120)
        o.append(open_c / 100.0)
        h.append((max(open_c, close_c) + span) / 100.0)
        l.append(max(100, min(open_c, close_c) - span) / 100.0)
        c.append(close_c / 100.0)
        v.append(float(900_000 + (nxt() % 1_400_000)))
    return dates, o, h, l, c, v


def running_vwap(h, l, c, v, anchor: int) -> list[float | None]:
    """Arithmetic-only anchored VWAP for the legacy avwap_overlay fixture."""
    out: list[float | None] = [None] * len(c)
    pv = vv = 0.0
    for i in range(anchor, len(c)):
        pv += ((h[i] + l[i] + c[i]) / 3.0) * v[i]
        vv += v[i]
        out[i] = pv / vv if vv else None
    return out


def _fake_profile(l, h, v, lo_i: int, bins: int = 24) -> dict:
    """A volume-by-price histogram over the visible window, without pandas.

    Mirrors engine.indicators_m2.volume_profile's OUTPUT shape (bin_edges /
    bin_volumes / poc / va_low / va_high) so the runway drawing path is
    exercised in the thin CI lane too.
    """
    lo = min(l[lo_i:])
    hi = max(h[lo_i:])
    step = (hi - lo) / bins
    edges = [lo + step * k for k in range(bins + 1)]
    vols = [0.0] * bins
    for i in range(lo_i, len(v)):
        tp = (h[i] + l[i] + (h[i] + l[i]) / 2.0) / 3.0
        k = min(bins - 1, max(0, int((tp - lo) / step))) if step else 0
        vols[k] += v[i]
    poc_i = max(range(bins), key=lambda k: vols[k])
    return {
        "poc": (edges[poc_i] + edges[poc_i + 1]) / 2.0,
        "va_low": edges[max(0, poc_i - 4)],
        "va_high": edges[min(bins, poc_i + 5)],
        "label": "POC",
        "bin_edges": edges,
        "bin_volumes": vols,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sample renders (the committed SVG fixtures + the PR-body PNGs come from these)
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        timeframe="DAILY", marker_index=210, highlight_index=210,
        pct_from_index=200, indicators=("volume", "macd"), warmup=60,
        volume_overlay=True, subpanel_h=120, company_name="Pinned Industries",
        width=1000, height=880,
        avwap_overlay={"values": running_vwap(h, l, c, v, 150),
                       "label": "AVWAP · Aug 01"},
        poc_overlay={"poc": c[-40], "va_low": min(l[-90:]), "va_high": max(h[-90:]),
                     "label": "POC"},
        level_overlay={"price": c[-1], "label": "cited level"},
    )


def _base_kwargs(**over) -> dict:
    kw = dict(
        timeframe="DAILY", indicators=("volume", "macd"), warmup=60,
        volume_overlay=True, subpanel_h=120, width=1000, height=880,
        company_name="Pinned Industries",
    )
    kw.update(over)
    return kw


def _spotlights_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(spotlights=[
            {"index": 100, "tense": "past", "label": "Feb 2024"},
            {"index": 168, "tense": "damage", "label": "the flush"},
            {"index": 245, "tense": "now", "label": "YOU ARE HERE"},
        ]),
    )


def _zones_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    lo = min(l[120:180])
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(zones=[
            {"lo": lo, "hi": lo * 1.05, "label": "prior supply"},
            {"lo": c[-1] * 0.995, "hi": c[-1] * 1.005,
             "start_index": 200, "end_index": 249, "label": "tight shelf"},
        ]),
    )


def _trendlines_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(trendlines=[
            {"from_idx": 70, "from_price": l[70], "to_idx": 175,
             "to_price": l[175], "style": "solid", "extend": True},
            {"from_idx": 95, "from_price": h[95], "to_idx": 200,
             "to_price": h[200], "style": "dotted"},
        ]),
    )


def _arcs_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        # Two genuine rounded bottoms in the pinned series (middle bar is the
        # low of each triple), so the sample shows a formation OUTLINE rather
        # than a curve that happens to trace the trend.
        **_base_kwargs(arcs=[
            {"indices": [99, 113, 127], "side": "under", "label": "LS"},
            {"indices": [161, 177, 193], "side": "under", "label": "H"},
        ]),
    )


def _measure_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(measure_box={"from_index": 205, "to_index": 240}),
    )


def _level_tags_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(
            mas=[{"kind": "ema", "length": 50}],
            level_tags=[{"price": max(h[180:]), "color": "#8FA6C8",
                         "label": "range high"},
                        {"price": min(l[180:]), "color": "#F5B301"}],
        ),
    )


def _mas_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(mas=[{"kind": "ema", "length": 200}]),
    )


def _panes_sample() -> str:
    dates, o, h, l, c, v = pinned_ohlcv(250)
    return render_chart_v2(
        "PINN", dates, o, h, l, c, v,
        **_base_kwargs(indicators=("volume", "streak", "squeeze"), subpanel_h=104),
    )


def _weekly_bars(n_daily: int = 1500):
    # An earlier start so ~6 years of weekdays land in the PAST — a review
    # artifact whose axis runs into 2029 reads as a rendering fault.
    dates, o, h, l, c, v = pinned_ohlcv(n_daily, start="2020-08-03")
    return CR.resample_bars(dates, o, h, l, c, v, "WEEKLY")


def _weekly_log_sample() -> str:
    wd, wo, wh, wl, wc, wv = _weekly_bars()
    return render_chart_v2(
        "PINN", wd, wo, wh, wl, wc, wv,
        **_base_kwargs(timeframe="WEEKLY", log_scale=True, warmup=40,
                       indicators=("volume", "rsi")),
    )


def _composite_sample() -> str:
    """The full TrendSpider-style card: WEEKLY + VbP + one MA + the grammar."""
    wd, wo, wh, wl, wc, wv = _weekly_bars()
    n = len(wc)
    return render_chart_v2(
        "PINN", wd, wo, wh, wl, wc, wv,
        **_base_kwargs(
            timeframe="WEEKLY", warmup=40, indicators=("volume", "macd"),
            runway_frac=0.18,
            mas=[{"kind": "sma", "length": 30}],
            poc_overlay=_fake_profile(wl, wh, wv, 40),
            spotlights=[
                {"index": n - 84, "tense": "past", "label": "same setup"},
                {"index": n - 1, "tense": "now", "label": "YOU ARE HERE"},
            ],
            zones=[{"lo": min(wl[n - 60:]), "hi": min(wl[n - 60:]) * 1.06,
                    "label": "demand"}],
            # Measures an EARLIER leg than the gold "now" disc, so the receipt
            # and the spotlight do not fight for the same corner.
            measure_box={"from_index": n - 62, "to_index": n - 40},
            level_tags=[{"price": max(wh[n - 60:]), "color": "#8FA6C8",
                         "label": "range high"}],
        ),
    )


SAMPLES: dict[str, callable] = {
    "legacy_baseline": _legacy_sample,
    "spotlights": _spotlights_sample,
    "zones": _zones_sample,
    "trendlines": _trendlines_sample,
    "arcs": _arcs_sample,
    "measure_box": _measure_sample,
    "level_tags": _level_tags_sample,
    "mas_ema": _mas_sample,
    "panes_streak_squeeze": _panes_sample,
    "weekly_log": _weekly_log_sample,
    "composite_weekly": _composite_sample,
}


def _sample(name: str) -> str:
    """Render *name*, refreshing its committed SVG when CHART_GRAMMAR_REGEN=1."""
    svg = SAMPLES[name]()
    if REGEN:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / f"{name}.svg").write_text(svg, encoding="utf-8")
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# SVG probes
# ─────────────────────────────────────────────────────────────────────────────

_RECT_RE = re.compile(
    r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="(-?[\d.]+)" height="(-?[\d.]+)"[^>]*>'
)
_LINE_RE = re.compile(
    r'<line x1="(-?[\d.]+)" y1="(-?[\d.]+)" x2="(-?[\d.]+)" y2="(-?[\d.]+)"[^>]*>'
)
_CIRCLE_RE = re.compile(r'<circle cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="([\d.]+)"[^>]*>')


def _rects(svg: str) -> list[tuple[float, float, float, float, str]]:
    return [(float(m.group(1)), float(m.group(2)), float(m.group(3)),
             float(m.group(4)), m.group(0)) for m in _RECT_RE.finditer(svg)]


def _lines(svg: str) -> list[tuple[float, float, float, float, str]]:
    return [(float(m.group(1)), float(m.group(2)), float(m.group(3)),
             float(m.group(4)), m.group(0)) for m in _LINE_RE.finditer(svg)]


def _circles(svg: str) -> list[tuple[float, float, float, str]]:
    return [(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(0))
            for m in _CIRCLE_RE.finditer(svg)]


def _price_pane(svg: str) -> tuple[float, float]:
    """(top, bottom) of the price pane, DERIVED from the rendered SVG.

    top    = header band height + 12 (the renderer's PAD_TOP)
    bottom = the first sub-panel divider, minus its 8px gap.
    """
    hdr = next(r for r in _rects(svg) if r[0] == 0.0 and r[1] == 0.0)
    top = hdr[3] + 12
    dividers = [ln for ln in _lines(svg)
                if DIVIDER in ln[4] and abs(ln[1] - ln[3]) < 0.01]
    bottom = min(ln[1] for ln in dividers) - 8 if dividers else top
    return top, bottom


def _texts(svg: str) -> list[str]:
    return re.findall(r'>([^<>]*)</text>', svg)


# ─────────────────────────────────────────────────────────────────────────────
# §0.1 — backward compatibility (the gate)
# ─────────────────────────────────────────────────────────────────────────────

def test_legacy_render_is_byte_identical_to_pre_grammar_golden():
    """A legacy call must reproduce the pre-grammar SVG byte for byte.

    legacy_baseline.svg was generated from the renderer as it stood BEFORE the
    annotation grammar landed, exercising every pre-existing kwarg at once
    (marker, highlight, pct callout, warmup, volume overlay, AVWAP, POC + value
    area, cited level, logo-less ghost watermark, MACD sub-pane). If this fails,
    a call site that passes no new kwarg has changed its output — which is the
    one thing PR-A promised would not happen.
    """
    golden = (FIXTURES / "legacy_baseline.svg").read_text(encoding="utf-8")
    assert _sample("legacy_baseline") == golden, (
        "legacy render drifted from the committed pre-grammar golden"
    )


def test_every_new_kwarg_defaults_to_off():
    """Passing each new kwarg as None/False equals omitting it entirely."""
    dates, o, h, l, c, v = pinned_ohlcv(120)
    plain = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=30)
    explicit_off = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=30,
        log_scale=False, runway_frac=None, mas=None, spotlights=None,
        zones=None, trendlines=None, arcs=None, measure_box=None, level_tags=None,
    )
    assert plain == explicit_off


def test_empty_annotation_lists_emit_no_layer():
    """Empty lists must not even emit the layer comment (byte-identical)."""
    dates, o, h, l, c, v = pinned_ohlcv(120)
    plain = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=30)
    empties = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=30,
        spotlights=[], zones=[], trendlines=[], arcs=[], level_tags=[],
    )
    assert plain == empties
    assert "annotation grammar" not in plain


# ─────────────────────────────────────────────────────────────────────────────
# §1.1 house grammar invariants
# ─────────────────────────────────────────────────────────────────────────────

def test_price_pane_has_zero_gridlines():
    """No horizontal rules in the price pane except ones a caller asked for."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          volume_overlay=True, width=1000, height=880)
    top, bottom = _price_pane(svg)
    horizontals = [
        ln for ln in _lines(svg)
        if abs(ln[1] - ln[3]) < 0.01 and top < ln[1] < bottom
        and ln[0] <= PAD_L + 1 and ln[2] >= 1000 - PAD_R - 1
    ]
    assert not horizontals, f"price pane must be gridline-free, found {horizontals}"


def test_white_ink_is_reserved_for_annotation_primitives():
    """No pure-white STROKE inside the price pane until an annotation asks for it."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    plain = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                            volume_overlay=True, width=1000, height=880)
    top, bottom = _price_pane(plain)
    for ln in _lines(plain):
        if "#ffffff" in ln[4]:
            assert not (top < ln[1] < bottom), (
                f"data layer used annotation ink inside the price pane: {ln[4]}"
            )
    annotated = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=60, volume_overlay=True,
        width=1000, height=880,
        trendlines=[{"from_idx": 70, "from_price": l[70],
                     "to_idx": 140, "to_price": l[140]}],
    )
    assert any("#ffffff" in ln[4] and top < ln[1] < bottom
               for ln in _lines(annotated)), "a trendline must be white annotation ink"


def test_subpanes_are_hard_capped_at_two():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=60, subpanel_h=90,
        indicators=("macd", "rsi", "streak", "squeeze"),
    )
    labels = [t for t in _texts(svg)
              if t in ("MACD", "RSI", "STREAK", "SQUEEZE", "VOLUME")]
    assert labels == ["MACD", "RSI"], f"expected 2 panes, got {labels}"


# ─────────────────────────────────────────────────────────────────────────────
# Timeframe resampling
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_timeframe():
    assert CR.normalize_timeframe("weekly") == "WEEKLY"
    assert CR.normalize_timeframe("W") == "WEEKLY"
    assert CR.normalize_timeframe("m") == "MONTHLY"
    assert CR.normalize_timeframe(None) == "DAILY"
    assert CR.normalize_timeframe("5MIN") == "DAILY"


def test_weekly_resample_labels_are_w_fri_and_ohlc_is_correct():
    """W-FRI labels + open/high/low/close/volume aggregation, per weinstein_stage."""
    dates, o, h, l, c, v = pinned_ohlcv(60)
    wd, wo, wh, wl, wc, wv = CR.resample_bars(dates, o, h, l, c, v, "WEEKLY")
    assert all(date.fromisoformat(d).weekday() == 4 for d in wd), (
        "every weekly bucket must be labelled by its Friday"
    )
    # First bucket: every daily bar whose Friday label matches the first weekly bar.
    first = [i for i in range(len(dates))
             if CR._bucket_label(dates[i], "WEEKLY") == wd[0]]
    assert wo[0] == o[first[0]]
    assert wc[0] == c[first[-1]]
    assert wh[0] == max(h[i] for i in first)
    assert wl[0] == min(l[i] for i in first)
    assert wv[0] == pytest.approx(sum(v[i] for i in first))
    assert sum(wv) == pytest.approx(sum(v)), "resampling must conserve volume"


def test_monthly_resample_labels_are_month_end():
    dates, o, h, l, c, v = pinned_ohlcv(400)
    md, mo, mh, ml, mc, mv = CR.resample_bars(dates, o, h, l, c, v, "MONTHLY")
    for d in md:
        dd = date.fromisoformat(d)
        nxt = date(dd.year + (dd.month == 12), (dd.month % 12) + 1, 1)
        assert dd == nxt - timedelta(days=1), f"{d} is not a month end"
    assert 17 <= len(md) <= 21, f"400 weekdays ≈ 19 months, got {len(md)}"
    assert sum(mv) == pytest.approx(sum(v))


def test_daily_resample_is_the_identity():
    bars = pinned_ohlcv(40)
    assert CR.resample_bars(*bars, "DAILY") == bars
    assert CR.resample_bars(*bars, "5MIN") == bars


def test_resample_keeps_the_forming_bucket():
    """A chart shows the live bar; only signal code drops the partial week."""
    dates, o, h, l, c, v = pinned_ohlcv(48)  # ends mid-week by construction
    wd, *_ = CR.resample_bars(dates, o, h, l, c, v, "WEEKLY")
    assert CR._bucket_label(dates[-1], "WEEKLY") == wd[-1]


def test_weekly_header_prints_log_suffix():
    svg = _sample("weekly_log")
    assert "WEEKLY (LOG)" in _texts(svg)


def test_log_scale_declines_on_non_positive_prices():
    dates, o, h, l, c, v = pinned_ohlcv(60)
    l2 = list(l)
    l2[40] = -1.0  # inside the VISIBLE window, so it reaches the axis math
    svg = render_chart_v2("TEST", dates, o, h, l2, c, v, warmup=20, log_scale=True)
    assert "(LOG)" not in "".join(_texts(svg))
    assert svg.startswith("<svg"), "a log request on bad data degrades, never raises"


def test_log_axis_is_geometric_not_linear():
    """On a log axis, equal SCREEN gaps mean equal RATIOS between tick prices."""
    svg = _sample("weekly_log")
    ticks = sorted(
        float(t.replace(",", "")) for t in _texts(svg)
        if re.fullmatch(r"[\d,]+\.\d\d", t or "")
    )
    ticks = [t for t in ticks if t > 1]
    assert len(ticks) >= 4
    ratios = [ticks[i + 1] / ticks[i] for i in range(len(ticks) - 1)]
    # The last-price pill shares this text shape, so allow one odd ratio.
    tidy = sorted(ratios)[: len(ratios) - 1] if len(ratios) > 3 else ratios
    assert max(tidy) / min(tidy) < 1.35, f"tick ratios not geometric: {ratios}"


# ─────────────────────────────────────────────────────────────────────────────
# Spotlights / zones / trendlines / arcs
# ─────────────────────────────────────────────────────────────────────────────

def test_spotlight_discs_are_tense_coloured_and_labelled():
    svg = _sample("spotlights")
    top, bottom = _price_pane(svg)
    for tense, color in CR._SPOTLIGHT_COLORS.items():
        discs = [ci for ci in _circles(svg)
                 if f'fill="{color}"' in ci[3] and top < ci[1] < bottom]
        assert len(discs) == 1, f"expected exactly one '{tense}' disc, got {len(discs)}"
        assert discs[0][2] >= 16.0, "a spotlight must read as a disc, not a dot"
    texts = _texts(svg)
    assert "YOU ARE HERE" in texts and "Feb 2024" in texts and "the flush" in texts
    gold = CR._SPOTLIGHT_COLORS["now"]
    assert re.search(rf'fill="{gold}"[^>]*>YOU ARE HERE<', svg), (
        "the label must print in the disc's own colour"
    )


def test_spotlight_in_the_warmup_leadin_is_dropped():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          spotlights=[{"index": 10, "tense": "now"}])
    assert CR._SPOTLIGHT_COLORS["now"] not in svg


def test_zone_bands_are_bands_never_hairlines():
    svg = _sample("zones")
    bands = [r for r in _rects(svg)
             if f'fill="{CR._ZONE_INK}"' in r[4] and r[2] > 40]
    assert len(bands) == 2
    for b in bands:
        assert b[3] >= CR._ZONE_MIN_PX - 0.01, f"zone collapsed to {b[3]}px"
    # The index-scoped band must be narrower than the full-width one.
    assert min(b[2] for b in bands) < max(b[2] for b in bands)
    assert "prior supply" in _texts(svg) and "tight shelf" in _texts(svg)


def test_zone_outside_the_bar_range_widens_the_axis():
    """A caller's zone is never half-clipped off the panel."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    far = max(h) * 1.25
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          zones=[{"lo": far, "hi": far * 1.02}])
    top, bottom = _price_pane(svg)
    bands = [r for r in _rects(svg) if f'fill="{CR._ZONE_INK}"' in r[4]]
    assert bands and all(top <= b[1] and b[1] + b[3] <= bottom + 0.5 for b in bands)


def test_trendlines_are_white_and_style_aware():
    svg = _sample("trendlines")
    top, bottom = _price_pane(svg)
    tls = [ln for ln in _lines(svg)
           if '#ffffff' in ln[4] and 'stroke-width="1.4"' in ln[4]]
    assert len(tls) == 2
    assert sum('stroke-dasharray' in ln[4] for ln in tls) == 1, (
        "dotted = diagnostic, solid = structural; exactly one of each here"
    )
    extended = max(tls, key=lambda ln: ln[2])
    assert extended[2] >= 1000 - PAD_R - 1, "extend=True must reach the right edge"
    for ln in tls:
        assert top - 0.5 <= ln[1] <= bottom + 0.5
        assert top - 0.5 <= ln[3] <= bottom + 0.5


def test_extended_trendline_is_clipped_at_the_pane_edge():
    """A steep projection stops at the pane, never bleeds into the sub-panes."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=60, width=1000, height=880,
        trendlines=[{"from_idx": 70, "from_price": max(h), "to_idx": 80,
                     "to_price": min(l), "extend": True}],
    )
    top, bottom = _price_pane(svg)
    tls = [ln for ln in _lines(svg) if '#ffffff' in ln[4] and 'width="1.4"' in ln[4]]
    assert tls and all(top - 0.5 <= ln[3] <= bottom + 0.5 for ln in tls)


def test_arcs_are_smooth_curves_not_polylines():
    svg = _sample("arcs")
    paths = re.findall(r'<path d="([^"]+)" fill="none" stroke="#ffffff"[^>]*>', svg)
    assert len(paths) == 2
    for d in paths:
        assert " C " in d or " Q " in d, f"arc must be a bezier, got {d[:40]}"
        assert "L " not in d, "a formation outline is a curve, not a polyline"
    assert "LS" in _texts(svg) and "H" in _texts(svg)


def test_arc_side_flips_the_curve():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    idx = [90, 110, 130]
    under = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                            arcs=[{"indices": idx, "side": "under"}])
    over = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                           arcs=[{"indices": idx, "side": "over"}])

    def _first_y(svg: str) -> float:
        d = re.search(r'<path d="M [\d.]+ ([\d.]+)', svg)
        return float(d.group(1))

    assert _first_y(under) > _first_y(over), "'under' must sit below 'over'"


# ─────────────────────────────────────────────────────────────────────────────
# Measure box + callout clamping
# ─────────────────────────────────────────────────────────────────────────────

def test_measure_box_shows_its_arithmetic():
    svg = _sample("measure_box")
    texts = _texts(svg)
    receipt = [t for t in texts if re.fullmatch(r"[+-][\d,]+\.\d\d \([+-][\d.]+%\)", t)]
    assert len(receipt) == 1, f"expected one Δ (Δ%) receipt, got {receipt}"
    elapsed = [t for t in texts if re.fullmatch(r"\d+ bars \(\d+ \w+\)", t)]
    assert len(elapsed) == 1, f"expected one 'N bars (elapsed)' line, got {elapsed}"
    assert "35 bars" in elapsed[0], elapsed[0]
    assert re.search(r'<marker id="measure_\d+"', svg), "arrow needs its own marker"
    assert re.search(r'marker-end="url\(#measure_\d+\)"', svg)


def test_measure_box_colour_follows_the_sign():
    dates, o, h, l, c, v = pinned_ohlcv(150)

    def _box_fill(i0: int, i1: int) -> str:
        svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                              measure_box={"from_index": i0, "to_index": i1})
        m = re.search(r'<rect x="[\d.]+" y="[\d.]+" width="\d+" height="40" rx="4" '
                      r'fill="(#[0-9A-Fa-f]{6})" opacity="0.94"', svg)
        return m.group(1)

    lo = min(range(70, 149), key=lambda i: c[i])
    hi = max(range(70, 149), key=lambda i: c[i])
    assert _box_fill(min(lo, hi), max(lo, hi)) in ("#4CAF50", "#E23B3B")
    assert _box_fill(lo, hi) == ("#4CAF50" if c[hi] >= c[lo] else "#E23B3B")


def test_measure_box_stays_inside_the_canvas_at_the_right_edge():
    """The clamp is the fix for a receipt half off-frame (masterplan §3 PR-A 6)."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=60, width=520, height=620,
        measure_box={"from_index": 140, "to_index": 149},
    )
    boxes = [r for r in _rects(svg) if r[3] == 40.0 and 'rx="4"' in r[4]]
    assert boxes
    for b in boxes:
        assert b[0] >= 0 and b[0] + b[2] <= 520, f"box escaped the canvas: {b}"
        assert b[1] >= 0 and b[1] + b[3] <= 620


def test_pct_callout_is_clamped_inside_a_narrow_canvas():
    """The pre-existing callout gets the same clamp — no more edge overhang."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          width=200, height=520, pct_from_index=100)
    for r in _rects(svg):
        if r[2] == 132.0 and r[3] == 40.0:
            assert r[0] >= 0 and r[0] + r[2] <= 200, f"callout escaped: {r}"
            assert r[1] >= 0 and r[1] + r[3] <= 520


def test_clamp_box_preserves_int_geometry():
    """Ints in, ints out — this is what keeps the legacy callout byte-identical."""
    x, y = CR._clamp_box(792, 86, 132, 40, 1000, 880, 76, 618)
    assert (x, y) == (792, 86) and isinstance(x, int) and isinstance(y, int)


def test_elapsed_phrase_units():
    assert CR._elapsed_phrase("2026-01-05", "2026-01-06") == "1 day"
    assert CR._elapsed_phrase("2026-01-05", "2026-01-12") == "7 days"
    assert CR._elapsed_phrase("2026-01-05", "2026-01-19") == "2 weeks"
    assert CR._elapsed_phrase("2026-01-05", "2026-06-05") == "5 months"
    assert CR._elapsed_phrase("2020-01-05", "2026-01-05") == "6.0 years"
    assert CR._elapsed_phrase("nope", "2026-01-05") == ""
    assert CR._elapsed_phrase("2026-01-05", "2026-01-05") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Level tags + moving averages
# ─────────────────────────────────────────────────────────────────────────────

def test_level_tags_ride_the_right_axis_in_their_own_colour():
    svg = _sample("level_tags")
    tags = [r for r in _rects(svg) if r[3] == 16.0 and 'rx="2"' in r[4]]
    assert len(tags) == 2, f"expected two axis tags, got {len(tags)}"
    assert any('fill="#8FA6C8"' in t[4] for t in tags)
    assert any('fill="#F5B301"' in t[4] for t in tags)
    pill = next(r for r in _rects(svg) if r[3] == 18.0 and 'rx="2"' in r[4])
    for t in tags:
        assert t[0] <= pill[0], "tags ride the last-price pill's axis lane"
        assert t[0] + t[2] <= 1000, f"tag {t[:4]} clipped at the canvas edge"
        assert abs(t[1] - pill[1]) > 8, "a tag must never overprint the price pill"
    # A price-only tag fits the axis gutter exactly; a worded one is pulled left.
    assert min(t[0] for t in tags) < pill[0]
    assert "range high" in _texts(svg)


def test_level_tag_outside_the_axis_range_is_dropped():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          level_tags=[{"price": max(h) * 3, "color": "#8FA6C8"}])
    assert 'fill="#8FA6C8"' not in svg


def test_mas_replaces_the_legacy_pair_and_labels_inline():
    svg = _sample("mas_ema")
    texts = _texts(svg)
    assert "200 EMA" in texts
    assert "50 SMA" not in texts and "200 SMA" not in texts, (
        "an explicit `mas` list replaces the legacy 50/200 default"
    )
    curves = re.findall(r'<polyline points="[^"]+" fill="none" stroke="(#[0-9A-Fa-f]{6})" '
                        r'stroke-width="1.6" opacity="0.92"', svg)
    assert len(curves) == 1, f"exactly one MA curve expected, got {curves}"
    assert "stroke-dasharray" not in svg.split("<!-- M2 overlays")[0], (
        "a named single MA draws SOLID; the dashed hairline is the legacy pair"
    )


def test_legacy_sma_pair_still_draws_when_mas_is_omitted():
    dates, o, h, l, c, v = pinned_ohlcv(250)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=50)
    assert "50 SMA" in _texts(svg) and "200 SMA" in _texts(svg)


def test_ema_and_sma_of_the_same_length_differ():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    sma = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          mas=[{"kind": "sma", "length": 50}])
    ema = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          mas=[{"kind": "ema", "length": 50}])
    assert "50 SMA" in _texts(sma) and "50 EMA" in _texts(ema)
    assert sma != ema, "an EMA must not render the same path as an SMA"


def test_unusable_ma_specs_are_skipped_not_fatal():
    dates, o, h, l, c, v = pinned_ohlcv(80)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v, warmup=20,
        mas=[{"kind": "ema", "length": 5000}, {"length": 0}, {"kind": "sma"},
             {"kind": "ema", "length": 20}],
    )
    assert "20 EMA" in _texts(svg)
    assert svg.startswith("<svg") and "<script" not in svg


# ─────────────────────────────────────────────────────────────────────────────
# Streak / squeeze sub-panes
# ─────────────────────────────────────────────────────────────────────────────

def test_streak_series_counts_consecutive_same_colour_candles():
    o = [10, 10, 10, 10, 10, 10]
    c = [11, 12, 13, 9, 8, 14]          # up, up, up, down, down, up
    assert CR._streak_series(o, c) == [1, 2, 3, -1, -2, 1]


def test_streak_pane_draws_the_streak_as_its_y_unit():
    svg = _sample("panes_streak_squeeze")
    assert "STREAK" in _texts(svg)
    last = [t for t in _texts(svg) if re.fullmatch(r"[+-]\d+", t or "")]
    assert last, "the streak pane prints its current run on the right axis"
    dates, o, h, l, c, v = pinned_ohlcv(250)
    expected = CR._streak_series(o, c)[-1]
    assert f"{expected:+d}" in last


def test_squeeze_series_flags_compression_and_release():
    """A flat stretch compresses the bands inside the channel; a shock releases."""
    n = 90
    c = [100.0] * 60 + [100.0 + 4.0 * (i + 1) for i in range(n - 60)]
    o = [c[0]] + c[:-1]
    h = [x + 0.05 for x in c]
    l = [x - 0.05 for x in c]
    on, mom = CR._squeeze_series(h, l, c)
    assert on[:20] == [None] * 20, "no state before the window is full"
    assert on[55] is True, "a dead-flat tape must read as compressed"
    assert on[-1] is False, "a sharp expansion must release the squeeze"
    assert mom[-1] is not None and mom[-1] > 0


def test_squeeze_pane_draws_state_dots_and_momentum():
    svg = _sample("panes_streak_squeeze")
    assert "SQUEEZE" in _texts(svg)
    dots = [ci for ci in _circles(svg) if ci[2] <= 2.2]
    assert len(dots) > 30, "one state dot per visible bar"
    assert any('fill="#F5B301"' in d[3] for d in dots) or \
           any('fill="#54607d"' in d[3] for d in dots)
    assert any(t in ("ON", "OFF") for t in _texts(svg))


def test_rsi_pane_is_reachable():
    """The RSI pane was fully built and never selected by any caller (dead code)."""
    dates, o, h, l, c, v = pinned_ohlcv(150)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                          indicators=("volume", "rsi"), volume_overlay=True)
    assert "RSI" in _texts(svg)
    assert 'stroke="#9C27B0"' in svg, "the RSI curve must actually be drawn"


# ─────────────────────────────────────────────────────────────────────────────
# Runway + volume profile
# ─────────────────────────────────────────────────────────────────────────────

def test_runway_leaves_the_right_of_the_frame_empty():
    dates, o, h, l, c, v = pinned_ohlcv(150)
    full = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60, width=1000)
    runway = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60, width=1000,
                             runway_frac=0.20)
    plot_right = 1000 - PAD_R

    def _last_candle_x(svg: str) -> float:
        return max(float(m.group(1)) for m in
                   re.finditer(r'<line x1="([\d.]+)" y1="[\d.]+" x2="\1" ', svg))

    assert _last_candle_x(full) > plot_right - 12
    assert _last_candle_x(runway) < plot_right - 0.18 * (plot_right - PAD_L)


def test_volume_profile_only_draws_inside_a_runway():
    """No reserved space ⇒ no profile: it must never paint over the candles."""
    dates, o, h, l, c, v = pinned_ohlcv(250)
    prof = _fake_profile(l, h, v, 60)
    no_runway = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                                width=1000, poc_overlay=prof)
    with_runway = render_chart_v2("TEST", dates, o, h, l, c, v, warmup=60,
                                  width=1000, runway_frac=0.18, poc_overlay=prof)
    bars_off = [r for r in _rects(no_runway) if 'fill="#54607d"' in r[4]]
    bars_on = [r for r in _rects(with_runway) if 'fill="#54607d"' in r[4]
               or ('fill="#5b9dff"' in r[4] and 'fill-opacity="0.50"' in r[4])]
    assert not bars_off, "a profile without a runway would occlude the tape"
    assert len(bars_on) >= 8, "the profile must draw into the runway"
    plot_right = 1000 - PAD_R
    runway_left = plot_right - 0.18 * (plot_right - PAD_L)
    for b in bars_on:
        assert b[0] >= runway_left - 1, f"profile bar {b[:4]} spilled onto the candles"
        assert b[0] + b[2] <= plot_right + 0.5


def test_build_m2_overlays_carries_the_profile_bins():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("numpy")
    dates, o, h, l, c, v = pinned_ohlcv(150)
    out = CR.build_m2_overlays("TEST", dates, o, h, l, c, v, pathlib.Path("."))
    poc = out.get("poc_overlay")
    if poc is None:
        pytest.skip("indicators_m2.volume_profile unavailable in this env")
    assert "bin_edges" in poc and "bin_volumes" in poc
    assert len(poc["bin_edges"]) == len(poc["bin_volumes"]) + 1
    assert pd is not None


# ─────────────────────────────────────────────────────────────────────────────
# The composite card + committed-sample staleness probe
# ─────────────────────────────────────────────────────────────────────────────

def test_composite_carries_every_primitive_at_once():
    svg = _sample("composite_weekly")
    texts = _texts(svg)
    assert "WEEKLY" in texts, "the header discloses the horizon, not the caption"
    assert "30 SMA" in texts                       # one MA, inline-labelled
    assert "YOU ARE HERE" in texts                 # gold spotlight
    assert "same setup" in texts                   # blue-grey precedent spotlight
    assert "demand" in texts                       # zone band
    assert "range high" in texts                   # right-axis level tag
    assert any(re.fullmatch(r"\d+ bars \(\d+ \w+\)", t) for t in texts)  # measure box
    assert any(f'fill="{CR._ZONE_INK}"' in r[4] and r[3] >= CR._ZONE_MIN_PX
               for r in _rects(svg))
    assert svg.startswith("<svg") and "<script" not in svg
    assert len(svg) < 200_000


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_committed_sample_matches_what_the_renderer_now_draws(name: str):
    """The committed SVGs are the PR's visual artifact — they must not go stale.

    Compared on SHAPE (element-name histogram + every text string) rather than
    bytes: that catches "this sample no longer contains its primitive" while
    staying immune to a one-ULP coordinate difference. Refresh with
    ``CHART_GRAMMAR_REGEN=1 python -m pytest tests/test_chart_render_grammar.py``.
    """
    path = FIXTURES / f"{name}.svg"
    assert path.exists(), f"missing committed sample {path.name} (run with REGEN=1)"
    committed = path.read_text(encoding="utf-8")
    fresh = _sample(name)

    def _shape(svg: str) -> tuple:
        tags = re.findall(r"<(\w+)[ />]", svg)
        return (tuple(sorted((t, tags.count(t)) for t in set(tags))),
                tuple(_texts(svg)))

    assert _shape(fresh) == _shape(committed), (
        f"{name}.svg is stale — re-run with CHART_GRAMMAR_REGEN=1"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Loader seam (data-dependent — runs in the chart-render-data lane)
# ─────────────────────────────────────────────────────────────────────────────

def test_load_ohlcv_timeframe_resamples_the_daily_parquet(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    dates, o, h, l, c, v = pinned_ohlcv(1500)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                      index=pd.to_datetime(dates))
    dest = tmp_path / "data" / "baskets" / "ohlcv"
    dest.mkdir(parents=True)
    df.to_parquet(dest / "PINN.parquet")

    daily = CR.load_ohlcv_timeframe("PINN", tmp_path, timeframe="DAILY")
    assert daily is not None
    (d_dates, *_), d_warm = daily
    assert len(d_dates) - d_warm == CR.MKT_VIS

    weekly = CR.load_ohlcv_timeframe("PINN", tmp_path, timeframe="WEEKLY")
    assert weekly is not None
    (w_dates, w_o, w_h, w_l, w_c, w_v), w_warm = weekly
    assert len(w_dates) - w_warm == CR.TIMEFRAME_VIS["WEEKLY"]
    assert w_warm > 0, "warm-up must survive the resample (SMA/MACD stay warm)"
    assert all(date.fromisoformat(d).weekday() == 4 for d in w_dates)
    assert all(w_h[i] >= w_l[i] for i in range(len(w_c)))

    short = CR.load_ohlcv_timeframe("PINN", tmp_path, timeframe="WEEKLY",
                                    lookback_bars=52, warm=10)
    assert short is not None
    (s_dates, *_), s_warm = short
    assert len(s_dates) - s_warm == 52

    monthly = CR.load_ohlcv_timeframe("PINN", tmp_path, timeframe="MONTHLY")
    assert monthly is not None
    (m_dates, *_), _ = monthly
    assert len(m_dates) >= 12
    assert CR.load_ohlcv_timeframe("NOPE", tmp_path, timeframe="WEEKLY") is None


def test_weekly_render_from_the_loader_is_a_real_weekly_chart(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    dates, o, h, l, c, v = pinned_ohlcv(1500)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                      index=pd.to_datetime(dates))
    dest = tmp_path / "data" / "baskets" / "ohlcv"
    dest.mkdir(parents=True)
    df.to_parquet(dest / "PINN.parquet")
    bars, warm = CR.load_ohlcv_timeframe("PINN", tmp_path, timeframe="WEEKLY")
    svg = render_chart_v2("PINN", *bars, timeframe="WEEKLY", warmup=warm,
                          volume_overlay=True, log_scale=True,
                          mas=[{"kind": "ema", "length": 30}])
    assert "WEEKLY (LOG)" in _texts(svg)
    assert "30 EMA" in _texts(svg)
    # 156 visible weekly bars ⇒ the drawn date span is ~3 years, not ~7 months.
    axis_dates = [t for t in _texts(svg) if re.fullmatch(r"\d{4}-\d\d-\d\d", t or "")]
    span = (date.fromisoformat(max(axis_dates)) - date.fromisoformat(min(axis_dates)))
    assert span.days > 900, f"weekly window collapsed to {span.days} days"
    assert math.isfinite(span.days)
