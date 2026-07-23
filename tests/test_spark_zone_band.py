"""Prophet-card buy-zone spark band — E1 phase 2 of the flagship card redesign
(the band drawn ON the card sparkline by the board builders, PR follow-up to #3256).

Contract locked here, shared by all five *_library._spark_svg generators and
build_site._mini_svg:

  * NO zone args -> output byte-identical to the historical band-less render
    (this code runs in the nightly; absent args must be a provable no-op);
  * ACTIVE zone  -> one low-opacity rect over the right 40% of the plot plus two
    1px dashed edge lines at the band's price edges;
  * PENDING zone -> the two dashed edge lines only, no rect;
  * band edges use the SAME lo/hi/pad normalization as the polyline and are
    price-clamped into the plotted window; a zone wholly outside the window (or
    a non-positive price — 0 = MISSING for equity prices) draws nothing;
  * the dashed lines carry NO fill attribute and the rect keeps its fill-opacity
    ATTRIBUTE — templates/_prophet_card.html.j2's hue-override CSS
    (`stroke` on `*`, `fill` on `[fill]:not([fill="none"])`) depends on exactly
    this split to recolor the band without flattening it;
  * _spark_zone maps a row's entry_signal -> band kwargs: priced-zone gate on
    buy_zone.high, filled while status is buy/near (window open or imminent),
    hollow otherwise.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# the five per-board generators share one drawing contract; build_stock_library,
# build_china_library, build_hk_library and build_canada_library also ship the
# _spark_zone mapper (INTL has no entry gauge — generator parity only).
GEN_MODULES = ["build_stock_library", "build_china_library", "build_hk_library",
               "build_canada_library", "build_intl_library"]
MAPPER_MODULES = GEN_MODULES[:4]

VALS = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]


def _spark(mod: str):
    return importlib.import_module(f"scripts.{mod}")._spark_svg


def _legacy_spark(vals, color="var(--link)", w=240, h=42):
    """The pre-band generator, verbatim — the byte-identity golden."""
    vals = [float(v) for v in vals if v is not None and v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n, pad = len(vals), h * 0.12

    def xy(i, v):
        return (i / (n - 1) * w, (h - pad) - ((v - lo) / rng) * (h - 2 * pad) + pad)

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(vals)))
    lx, ly = xy(n - 1, vals[-1])
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'width="100%" height="{h}">'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


def _y(price: float, lo=10.0, hi=20.0, h=42, pad=42 * 0.12) -> float:
    """The polyline's price->y map (what the band edges must match)."""
    return (h - pad) - ((price - lo) / (hi - lo)) * (h - 2 * pad) + pad


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_no_zone_args_byte_identical(mod):
    fn = _spark(mod)
    out = fn(VALS, color="var(--up)")
    assert out == _legacy_spark(VALS, color="var(--up)")
    assert "<rect" not in out and "stroke-dasharray" not in out


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_active_zone_draws_rect_plus_dashed_edges(mod):
    out = _spark(mod)(VALS, color="var(--up)", zone_lo=12.0, zone_hi=14.0,
                      zone_state="active")
    rects = re.findall(r"<rect[^>]*>", out)
    lines = re.findall(r"<line[^>]*>", out)
    assert len(rects) == 1 and len(lines) == 2
    r = rects[0]
    # right ~40% of the 240px plot, low-opacity fill in the caller's color token
    assert 'x="144.0"' in r and 'width="96.0"' in r
    assert 'fill-opacity="0.09"' in r and 'fill="var(--up)"' in r and 'stroke="none"' in r
    # rect spans exactly the polyline-normalized zone edges
    assert f'y="{_y(14.0):.1f}"' in r
    assert f'height="{_y(12.0) - _y(14.0):.1f}"' in r
    for ln in lines:
        assert 'stroke-dasharray="4 3"' in ln and 'stroke-width="1"' in ln
        assert "fill" not in ln  # the template stroke-hue override must keep matching
    assert f'y1="{_y(14.0):.1f}"' in lines[0] and f'y1="{_y(12.0):.1f}"' in lines[1]
    # band renders under the price line: before the area polyline
    assert out.index("<rect") < out.index("<polyline")


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_pending_zone_dashed_edges_only(mod):
    out = _spark(mod)(VALS, color="var(--up)", zone_lo=12.0, zone_hi=14.0,
                      zone_state="pending")
    assert "<rect" not in out
    assert len(re.findall(r"<line[^>]*>", out)) == 2


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_zone_clamped_into_viewbox(mod):
    # zone extends above the plotted range -> top edge clamps to the hi-price y
    out = _spark(mod)(VALS, zone_lo=15.0, zone_hi=999.0, zone_state="active")
    assert f'y1="{_y(20.0):.1f}"' in out and f'y1="{_y(15.0):.1f}"' in out
    for y in (float(m) for m in re.findall(r'y1="([-0-9.]+)"', out)):
        assert 0.0 <= y <= 42.0


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_zone_outside_window_or_unpriced_draws_nothing(mod):
    fn = _spark(mod)
    for kw in ({"zone_lo": 990.0, "zone_hi": 999.0},   # wholly above
               {"zone_lo": 1.0, "zone_hi": 2.0},        # wholly below
               {"zone_lo": 0.0, "zone_hi": 0.0},        # 0 = missing, never a price
               {"zone_lo": None, "zone_hi": None}):
        out = fn(VALS, zone_state="active", **kw)
        assert "<rect" not in out and "stroke-dasharray" not in out
        assert out == _legacy_spark(VALS)


@pytest.mark.parametrize("mod", GEN_MODULES)
def test_single_price_zone_collapses_to_level_line(mod):
    out = _spark(mod)(VALS, zone_lo=14.0, zone_hi=14.0, zone_state="active")
    assert 'height="0.0"' in out                        # rect collapses
    assert len(re.findall(r"<line[^>]*>", out)) == 2    # edges overlap at one y


@pytest.mark.parametrize("mod", MAPPER_MODULES)
def test_spark_zone_mapper_contract(mod):
    zf = importlib.import_module(f"scripts.{mod}")._spark_zone
    assert zf(None) == {}
    assert zf({"status": "buy_now"}) == {}                                # no zone
    assert zf({"status": "buy_now", "buy_zone": {"low": 1, "high": None}}) == {}
    for st in ("buy_now", "partial", "buy_soon", "await_confluence"):
        got = zf({"status": st, "buy_zone": {"low": 12.0, "high": 14.0}})
        assert got == {"zone_lo": 12.0, "zone_hi": 14.0, "zone_state": "active"}
    for st in ("hold", "topping", "wait_pullback", "watch", "extended", "exit",
               "avoid", None):
        got = zf({"status": st, "buy_zone": {"low": 12.0, "high": 14.0}})
        assert got["zone_state"] == "pending"
    # one-sided zone: low may be None; high alone still bands (template parity)
    got = zf({"status": "buy_now", "buy_zone": {"low": None, "high": 14.0}})
    assert got == {"zone_lo": None, "zone_hi": 14.0, "zone_state": "active"}


def test_mini_svg_band_parity():
    from scripts.build_site import _mini_svg
    base = _mini_svg(VALS, color="var(--up)", w=240, h=42)
    assert "<rect" not in base and "fill-opacity" not in base
    out = _mini_svg(VALS, color="var(--up)", w=240, h=42,
                    zone_lo=12.0, zone_hi=14.0, zone_state="active")
    assert 'fill-opacity="0.09"' in out and 'stroke-dasharray="4 3"' in out
    assert 'x="144.0"' in out and 'width="96.0"' in out
