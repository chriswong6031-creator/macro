"""Unit tests for lib.illus (the ilx / Signal-Ink SSR renderer)."""
from __future__ import annotations

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
