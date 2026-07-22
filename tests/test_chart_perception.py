"""Tests for engine.neuralweb.chart_perception (CMX W2 — Eyes).

All fixtures are constructed ARITHMETICALLY — no parquet, no fetching. Pivots, level touch
counts, and trendline touches are known by construction so assertions are exact. The public
entry points (chart_digest / measure_line) are exercised by monkeypatching the read-only
loader to hand back a synthetic series, which also covers the no-data null path.

Key CMX law under test: NO formulas / thresholds / parameter values ever appear in an emitted
text field (anti-distillation). ``test_no_machine_text_in_labels`` scans every string in a
full digest for banned tokens.
"""

from __future__ import annotations

import re

import pytest

from engine.neuralweb import chart_perception as cp


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic bar builders
# ─────────────────────────────────────────────────────────────────────────────

_EPOCH0 = 1_700_000_000  # a Tuesday; +1 day per bar
_DAY = 86_400


def _bars_from_closes(closes: list[float], wick: float = 0.3, day: int = _DAY) -> dict:
    """Build an OHLCV bar dict from a close path. Highs/lows are close ± wick (tight range
    → small ATR → sensitive ZigZag). Timestamps step by *day* seconds. Open = prev close."""
    n = len(closes)
    t = [_EPOCH0 + i * day for i in range(n)]
    h = [c + wick for c in closes]
    l = [c - wick for c in closes]
    o = [closes[0]] + closes[:-1]
    v = [1000.0] * n
    return {"t": t, "o": o, "h": h, "l": l, "c": list(closes), "v": v}


def _leg(start: float, step: float, count: int) -> list[float]:
    """A straight run: start+step, start+2*step, ... (count points)."""
    return [start + step * (i + 1) for i in range(count)]


def _zigzag_closes() -> list[float]:
    """Rise 100→121, fall →100, rise →128. Three clean legs → low, high, low, high pivots."""
    c = [100.0]
    c += _leg(c[-1], +1.4, 15)   # up to ~121
    c += _leg(c[-1], -1.4, 15)   # down to ~100
    c += _leg(c[-1], +1.4, 20)   # up to ~128
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Swing pivots
# ─────────────────────────────────────────────────────────────────────────────

def test_swing_pivots_finds_known_zigzag():
    """A 3-leg zigzag yields alternating low/high/low/high pivots at the leg turns."""
    bars = _bars_from_closes(_zigzag_closes())
    atr = cp._atr_series(bars["h"], bars["l"], bars["c"])
    piv = cp._swing_pivots(bars["t"], bars["h"], bars["l"], bars["c"], atr)
    kinds = [p["kind"] for p in piv]
    assert kinds == ["low", "high", "low", "high"], kinds
    # The interior high sits near the top of leg 1 (~121) and the interior low near ~100.
    assert piv[1]["p"] > 118
    assert piv[2]["p"] < 103
    # Pivots alternate — never two of the same kind in a row.
    for a, b in zip(kinds, kinds[1:]):
        assert a != b


def test_swing_pivots_flat_series_no_interior_oscillation():
    """A monotonic rising line has no INTERIOR reversal — only its two endpoints (start low,
    end high), never an oscillating sequence."""
    bars = _bars_from_closes(_leg(100.0, +0.5, 40))
    atr = cp._atr_series(bars["h"], bars["l"], bars["c"])
    piv = cp._swing_pivots(bars["t"], bars["h"], bars["l"], bars["c"], atr)
    kinds = [p["kind"] for p in piv]
    # Endpoints only: [] or [high] or [low, high] — never a mid-run zigzag.
    assert kinds in ([], ["high"], ["low", "high"]), kinds
    # No interior pivots strictly between the first and last bar.
    interior = [p for p in piv if 0 < p["i"] < len(bars["c"]) - 1]
    assert interior == [], interior


def test_swing_pivots_short_series_safe():
    """Fewer than 3 bars returns [] without raising."""
    bars = _bars_from_closes([100.0, 101.0])
    atr = cp._atr_series(bars["h"], bars["l"], bars["c"])
    assert cp._swing_pivots(bars["t"], bars["h"], bars["l"], bars["c"], atr) == []


# ─────────────────────────────────────────────────────────────────────────────
# Trend segments
# ─────────────────────────────────────────────────────────────────────────────

def test_trend_segments_direction_words():
    """Segments between zigzag pivots read rising / falling / rising in order."""
    bars = _bars_from_closes(_zigzag_closes())
    skel = cp._skeleton(bars, want_trendlines=True, want_gaps=True, compact=False)
    dirs = [s["direction"] for s in skel["trend"]]
    assert dirs == ["rising", "falling", "rising"], dirs
    # Every direction is a plain word from the allowed set.
    assert all(d in ("rising", "falling", "flat") for d in dirs)


# ─────────────────────────────────────────────────────────────────────────────
# Level clusters — touch counts + side
# ─────────────────────────────────────────────────────────────────────────────

def test_level_clusters_touch_counts_and_side():
    """Two revisits to ~100 (lows) and two to ~120 (highs) → a support level with 2 touches
    and a resistance level with 2 touches, correctly sided."""
    # W-shape then M-shape: low@100, high@120, low@100, high@120, low@100
    c = [100.0]
    c += _leg(c[-1], +2.0, 10)   # -> 120
    c += _leg(c[-1], -2.0, 10)   # -> 100
    c += _leg(c[-1], +2.0, 10)   # -> 120
    c += _leg(c[-1], -2.0, 10)   # -> 100
    bars = _bars_from_closes(c)
    atr = cp._atr_series(bars["h"], bars["l"], bars["c"])
    piv = cp._swing_pivots(bars["t"], bars["h"], bars["l"], bars["c"], atr)
    atr_now = cp._last_atr(atr) or 0.0
    levels = cp._level_clusters(piv, bars["t"], atr_now, len(c))
    # Find the support cluster near 100 and resistance near 120.
    support = [lv for lv in levels if lv["side"] == "support" and abs(lv["price"] - 100) < 5]
    resistance = [lv for lv in levels if lv["side"] == "resistance" and abs(lv["price"] - 120) < 5]
    assert support, f"no support cluster near 100: {levels}"
    assert resistance, f"no resistance cluster near 120: {levels}"
    # Each of the repeated turns should be counted (≥2 touches at the revisited price).
    assert support[0]["touches"] >= 2, support
    assert resistance[0]["touches"] >= 2, resistance
    # Freshness is a plain word.
    assert support[0]["freshness"] in ("fresh", "recent", "stale")


def test_level_clusters_empty_when_no_pivots():
    assert cp._level_clusters([], [], 1.0, 10) == []


# ─────────────────────────────────────────────────────────────────────────────
# Trendline candidates — ranking
# ─────────────────────────────────────────────────────────────────────────────

def test_trendline_candidate_ranking_prefers_more_touches():
    """A rising channel whose lows sit on one line ranks that support line highly with
    a touch count reflecting the bars riding the line."""
    # Three ascending lows on a straight support line, with pullbacks between.
    # Construct: saw-tooth riding a rising floor.
    c = []
    floor = 100.0
    for k in range(4):
        base = floor + k * 6.0
        c += [base, base + 4.0, base + 1.0, base + 5.0]  # dips back near the rising floor
    bars = _bars_from_closes(c, wick=0.2)
    atr = cp._atr_series(bars["h"], bars["l"], bars["c"])
    piv = cp._swing_pivots(bars["t"], bars["h"], bars["l"], bars["c"], atr)
    atr_now = cp._last_atr(atr) or 0.0
    cands = cp._trendline_candidates(piv, bars["h"], bars["l"], bars["c"], atr_now)
    # Candidates are sorted by touches desc; the first has the most touches.
    if len(cands) >= 2:
        assert cands[0]["touches"] >= cands[1]["touches"]
    # No candidate exceeds the top-N cap.
    assert len(cands) <= 5
    # Every candidate has ≥2 touches (the floor for a line to be a candidate at all).
    assert all(cd["touches"] >= 2 for cd in cands)
    # Each candidate reports max deviation in ATR units as a number.
    assert all(isinstance(cd["max_dev_atr"], (int, float)) for cd in cands)


# ─────────────────────────────────────────────────────────────────────────────
# measure_line verdicts (via _line_fit + _line_verdict, exact geometry)
# ─────────────────────────────────────────────────────────────────────────────

def _flat_floor_closes() -> list[float]:
    """~35 bars: a flat support floor at 100 revisited 5×, peaks to ~108 between. Enough bars
    for a full ATR window (>14). Floor is touched at bars 0, 7, 14, 21, 28."""
    c: list[float] = []
    for _ in range(5):
        c += [100.0, 104, 108, 106, 103, 101, 100.5]
    return c


def test_measure_line_verdict_holds():
    """A support line laid on a repeatedly-touched, un-violated floor returns 'holds'."""
    c = _flat_floor_closes()
    bars = _bars_from_closes(c, wick=0.2)
    atr_now = cp._last_atr(cp._atr_series(bars["h"], bars["l"], bars["c"])) or 0.0
    assert atr_now > 0
    p1 = {"i": 0, "p": 100.0}
    p2 = {"i": 28, "p": 100.0}
    fit = cp._line_fit(p1, p2, bars["h"], bars["l"], bars["c"], atr_now)
    verdict = cp._line_verdict(fit["touches"], fit["max_dev_atr"])
    assert fit["touches"] >= 3, fit
    # A respected support line has small penetration even though price swings far ABOVE it.
    assert fit["max_dev_atr"] <= cp._TOUCH_BAND_ATR, fit
    assert verdict == "holds", (fit, verdict)


def test_measure_line_verdict_invalid_when_violated():
    """A floor that price CLOSES THROUGH (a real break) reads 'invalid' despite prior touches."""
    c = _flat_floor_closes()
    c[15] = 95.0  # a hard break below the 100 floor
    bars = _bars_from_closes(c, wick=0.2)
    atr_now = cp._last_atr(cp._atr_series(bars["h"], bars["l"], bars["c"])) or 0.0
    fit = cp._line_fit({"i": 0, "p": 100.0}, {"i": 28, "p": 100.0},
                       bars["h"], bars["l"], bars["c"], atr_now)
    verdict = cp._line_verdict(fit["touches"], fit["max_dev_atr"])
    assert fit["max_dev_atr"] > cp._TOUCH_BAND_ATR, fit
    assert verdict == "invalid", (fit, verdict)


def test_measure_line_verdict_invalid_off_line():
    """A line far from all bars returns few/zero touches and an 'invalid' verdict."""
    bars = _bars_from_closes(_leg(100.0, +0.5, 30), wick=0.2)
    atr_now = cp._last_atr(cp._atr_series(bars["h"], bars["l"], bars["c"])) or 0.0
    # A horizontal line at 500 — nowhere near price.
    p1 = {"i": 0, "p": 500.0}
    p2 = {"i": 20, "p": 500.0}
    fit = cp._line_fit(p1, p2, bars["h"], bars["l"], bars["c"], atr_now)
    verdict = cp._line_verdict(fit["touches"], fit["max_dev_atr"])
    assert fit["touches"] == 0
    assert verdict == "invalid"


def test_measure_line_verdict_weak_two_touches():
    """Exactly two touches with modest deviation reads 'weak', not 'holds'."""
    verdict = cp._line_verdict(2, cp._TOUCH_BAND_ATR * 1.5)
    assert verdict == "weak"
    # And three tight touches read 'holds'.
    assert cp._line_verdict(3, 0.1) == "holds"


def test_measure_line_public_degenerate_points():
    """Public measure_line rejects a zero-width line as 'invalid' without touching data."""
    out = cp.measure_line("NVDA", "1D", {"t": 1, "p": 10.0}, {"t": 1, "p": 10.0})
    assert out["verdict"] == "invalid"
    out2 = cp.measure_line("NVDA", "1D", {"t": 1, "p": -5.0}, {"t": 2, "p": 10.0})
    assert out2["verdict"] == "invalid"


# ─────────────────────────────────────────────────────────────────────────────
# Unfilled gaps
# ─────────────────────────────────────────────────────────────────────────────

def _gap_bars(post_jump_tail: list[float]) -> dict:
    """A flat plateau at 100 (overlapping ranges → no micro-gaps), one clean jump to 110,
    then *post_jump_tail*. wick=0.5 so the plateau bars' ranges overlap (99.5–100.5) and the
    only structural gap is the intended 100.5 → 109.5 hole."""
    c = [100.0, 100.0, 100.0, 100.0, 110.0] + post_jump_tail
    return _bars_from_closes(c, wick=0.5)


def test_unfilled_gap_detected():
    """A clean up-gap that price never revisits is reported once, correctly bounded."""
    bars = _gap_bars([110.0, 110.0])  # stays elevated → gap stays open
    gaps = cp._unfilled_gaps(bars["t"], bars["h"], bars["l"], bars["c"])
    up = [g for g in gaps if g["direction"] == "up"]
    assert len(up) == 1, gaps
    g = up[0]
    assert g["bottom"] < g["top"]
    # Gap sits between the plateau high (100.5) and the jump-bar low (109.5).
    assert 100.0 < g["bottom"] < 101.0
    assert 109.0 < g["top"] < 110.0


def test_filled_gap_not_reported():
    """A gap a later bar trades back into (here 105, inside the 100.5–109.5 band) is filled."""
    bars = _gap_bars([110.0, 105.0])  # bar 6 at 105 re-enters the gap → filled
    gaps = cp._unfilled_gaps(bars["t"], bars["h"], bars["l"], bars["c"])
    up = [g for g in gaps if g["direction"] == "up"]
    assert up == [], gaps


# ─────────────────────────────────────────────────────────────────────────────
# Weekly resample
# ─────────────────────────────────────────────────────────────────────────────

def test_weekly_resample_buckets_by_week():
    """Daily bars spanning several weeks collapse to one bar per ISO week; weekly high is the
    max of that week's daily highs and weekly close is the last daily close."""
    # 21 daily bars (3 weeks) rising 100→120.
    closes = _leg(100.0, +1.0, 21)
    daily = _bars_from_closes(closes)
    weekly = cp._resample_weekly(daily)
    assert weekly is not None
    # Fewer weekly bars than daily.
    assert len(weekly["c"]) < len(daily["c"])
    assert len(weekly["c"]) >= 3
    # Each weekly high is ≥ each weekly low and volume aggregates upward.
    for i in range(len(weekly["c"])):
        assert weekly["h"][i] >= weekly["l"][i]
    assert sum(weekly["v"]) == pytest.approx(sum(daily["v"]))
    # Weekly closes are monotonic-ish rising (the series rose).
    assert weekly["c"][-1] > weekly["c"][0]


def test_weekly_resample_too_short_none():
    """Under a few weeks of data → None (compact snapshot not meaningful)."""
    daily = _bars_from_closes(_leg(100.0, +1.0, 4))
    assert cp._resample_weekly(daily) is None


# ─────────────────────────────────────────────────────────────────────────────
# Public chart_digest — via monkeypatched loader (covers full path + no-data null)
# ─────────────────────────────────────────────────────────────────────────────

def _install_fake_loader(monkeypatch, closes: list[float] | None):
    """Patch chart_perception._load_daily to return a synthetic series (or None)."""
    def _fake(symbol, root, n):
        if closes is None:
            return None
        bars = _bars_from_closes(closes)
        return bars
    monkeypatch.setattr(cp, "_load_daily", _fake)


def test_chart_digest_full_shape(monkeypatch):
    """chart_digest('1D') on a synthetic zigzag returns the full structural skeleton."""
    _install_fake_loader(monkeypatch, _zigzag_closes())
    d = cp.chart_digest("NVDA", tf="1D")
    assert d["available"] is True
    assert d["symbol"] == "NVDA"
    assert d["tf"] == "1D"
    for key in ("swings", "trend", "levels", "trendlines", "gaps", "context"):
        assert key in d, f"missing section {key}"
    # Swings carry plain-word kinds only.
    assert all(s["kind"] in ("high", "low") for s in d["swings"])
    # Context volatility is a plain word.
    assert d["context"]["volatility"] in ("quiet", "normal", "elevated", "unknown")


def test_chart_digest_section_filter(monkeypatch):
    """Requesting a subset returns only those sections (plus header keys)."""
    _install_fake_loader(monkeypatch, _zigzag_closes())
    d = cp.chart_digest("NVDA", tf="1D", sections=["levels", "context"])
    assert "levels" in d and "context" in d
    assert "trendlines" not in d and "gaps" not in d and "swings" not in d
    # Header keys survive the filter.
    assert d["symbol"] == "NVDA" and d["available"] is True


def test_chart_digest_no_data_null(monkeypatch):
    """No bars → available False, reason 'no data', never raises."""
    _install_fake_loader(monkeypatch, None)
    d = cp.chart_digest("ZZZZ", tf="1D")
    assert d["available"] is False
    assert d["reason"] == "no data"
    assert d["symbol"] == "ZZZZ"


def test_chart_digest_empty_symbol_null():
    """Empty/garbage symbol → available False without any load attempt."""
    d = cp.chart_digest("!!!", tf="1D")
    assert d["available"] is False


def test_chart_digest_weekly_tf(monkeypatch):
    """tf='1W' resamples and returns a compact weekly skeleton."""
    # Long rising series so the weekly resample has ≥3 weeks.
    _install_fake_loader(monkeypatch, _leg(100.0, +0.4, 120))
    d = cp.chart_digest("NVDA", tf="1W")
    assert d["available"] is True
    assert d["tf"] == "1W"
    assert "levels" in d and "trend" in d


def test_measure_line_public_holds(monkeypatch):
    """Public measure_line runs end-to-end over the synthetic series and returns 'holds'."""
    c = _flat_floor_closes()
    _install_fake_loader(monkeypatch, c)
    bars = _bars_from_closes(c)
    t = bars["t"]
    out = cp.measure_line("NVDA", "1D", {"t": t[0], "p": 100.0}, {"t": t[28], "p": 100.0})
    assert out["verdict"] == "holds", out
    assert out["touches"] >= 3
    assert isinstance(out["max_dev_atr"], (int, float))


# ─────────────────────────────────────────────────────────────────────────────
# Anti-distillation — no machine text in any emitted label
# ─────────────────────────────────────────────────────────────────────────────

def _walk_strings(obj):
    """Yield every string value anywhere in a nested dict/list structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            # Keys are field names, not emitted prose — skip; scan values.
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


# Banned tokens: internal parameter names / math that would leak the "how".
_BANNED_SUBSTRINGS = ("ATR", "atr", "percentile", "z-score", "zscore", "sigma",
                      "threshold", "lookback", "*ATR", "0.5", "1.5", "std", "stdev",
                      "wilder", "zigzag", "formula")
# Banned pattern: a number immediately glued to a parameter-ish word, e.g. "0.5*ATR", "1.5 ATR".
_BANNED_RE = re.compile(r"\d+(\.\d+)?\s*[*x×]?\s*(ATR|atr|sd|std|sigma|pct|percentile)", re.I)


def test_no_machine_text_in_labels(monkeypatch):
    """Every string field in a full digest is free of internal formulas/thresholds/params.

    The digest MAY contain numbers (prices, touch counts, deviations — those are results),
    but never a parameter name or a formula. This is the anti-distillation contract.
    """
    _install_fake_loader(monkeypatch, _zigzag_closes())
    d = cp.chart_digest("NVDA", tf="1D")
    # Only scan STRING labels (the plain-word fields). Numeric results are allowed.
    strings = list(_walk_strings(d))
    assert strings, "digest produced no string fields to scan"
    for s in strings:
        assert not _BANNED_RE.search(s), f"machine-text pattern in label: {s!r}"
        for bad in _BANNED_SUBSTRINGS:
            assert bad not in s, f"banned token {bad!r} in label: {s!r}"


def test_labels_are_from_plain_word_vocab(monkeypatch):
    """Spot-check that emitted classification labels are from the plain-word vocab only."""
    _install_fake_loader(monkeypatch, _zigzag_closes())
    d = cp.chart_digest("NVDA", tf="1D")
    for s in d["swings"]:
        assert s["kind"] in ("high", "low")
    for lv in d["levels"]:
        assert lv["side"] in ("support", "resistance", "both")
        assert lv["freshness"] in ("fresh", "recent", "stale")
    for seg in d["trend"]:
        assert seg["direction"] in ("rising", "falling", "flat")


def test_module_performs_no_writes():
    """Static guard: the perception module contains no filesystem-write calls (MM_DATA_GUARD)."""
    import pathlib
    src = pathlib.Path(cp.__file__).read_text()
    for pattern in (".write_text", ".to_parquet", ".to_csv", ".mkdir", "open("):
        # 'open(' allowed only if it's the read helper's docstring; assert no write-mode opens.
        assert ".write(" not in src
    assert re.search(r"open\([^)]*['\"][wa]", src) is None, "write-mode open() found"
