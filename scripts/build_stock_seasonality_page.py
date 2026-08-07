"""Build the Calendar Clock PAGE -> site/stock_seasonality.html.

Named `..._page` because scripts/build_stock_seasonality.py is the ARTIFACT
producer (the nightly engine lane). Two scripts by design: the artifacts run
nightly-only, this page renders in the render lanes.

Lane 2 of the seasonality docket: one instrument's own recurring calendar
structure, drawn as every historical year's thread with the median as ink over
them and a draggable window gate — plus the window fan, the same years re-anchored
to zero at the window's first day at the window's own scale. Implements
research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md exactly (§13: two pictures, two
scales; the year field carries no in-gate lighting and there is no dot row).

The page SERVER-RENDERS its default view (default symbol, full shipped panel,
the symbol's own strongest window) so first paint is honest and indexable, and
embeds that entity payload so the gate is draggable with NO network round-trip
(spec §0 gate 2). templates/stock_seasonality.js then owns interaction, the
Raw / Vs market / Detrended lenses, the lookback, and symbol switching — the
latter is the only thing that fetches.

Input is the entity artifact produced by the seasonality lane. When that
artifact does not exist yet the page renders from the committed worked example
(tests/fixtures/seasonality/SPY.entity.json, computed from committed adjusted
closes) and says so on the page — never a blank chart, never an invented one.

Usage: python -m scripts.build_stock_seasonality
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_stock_seasonality")

# ── strand-field geometry (spec §4) ─────────────────────────────────────────
X0 = 44.0
Y0, Y1 = 16.0, 296.0
RAIL_Y = 330.0
SLOTS = 365
# Plot box x in [44, 940] (spec §4). The spec's parenthetical "896px over 366 day
# slots" predates the settled contract, which ships 365 slots indexed doy-1; 365
# slots of 896/365 fill the same box. Points sit at their slot's left edge.
PX = 896.0 / 365.0
MAX_POINTS = 183                        # every second calendar day
MONTH_INITIALS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
NONLEAP = 2001                          # any non-leap year — the calendar basis

# ── copy (spec §3, verbatim) ────────────────────────────────────────────────
SEASON_EN = {1: "Deep-winter", 2: "Early-spring", 3: "Early-summer",
             4: "Late-summer", 5: "Autumn", 6: "Year-end"}
SEASON_ZH = {1: "深冬", 2: "早春", 3: "初夏", 4: "盛夏", 5: "秋季", 6: "年末"}
DIR_EN = {True: "strength", False: "weakness"}
DIR_ZH = {True: "走强", False: "走弱"}

MONTH_ZH = ["1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月"]
WEEKDAY_EN = ["M", "T", "W", "T", "F"]
WEEKDAY_ZH = ["一", "二", "三", "四", "五"]


def doy_to_date(doy: int) -> date:
    return date(NONLEAP, 1, 1) + timedelta(days=max(1, min(SLOTS, doy)) - 1)


def md_en(doy: int) -> str:
    d = doy_to_date(doy)
    return f"{d.strftime('%b')} {d.day}"


def md_zh(doy: int) -> str:
    d = doy_to_date(doy)
    return f"{d.month}月{d.day}日"


def md_iso(doy: int) -> str:
    return doy_to_date(doy).strftime("%m-%d")


def season_bucket(a: int, b: int) -> int:
    """Bucket from the window midpoint's month: Jan-Feb .. Nov-Dec (1..6)."""
    mid = doy_to_date(max(1, (a + b) // 2))
    return (mid.month - 1) // 2 + 1


# ── the statistics the client is also allowed to compute (spec §9) ──────────
def window_stats(cums, a: int, b: int, scale: float = 1e-5) -> dict:
    """Per-year window log return, then mean / median / share up / sd / |t|.

    `calendar.window_convention`, verbatim: start_doy/end_doy are 1-based
    day-of-year; cum index = doy - 1; window log return =
    cum[end_doy - 1] - cum[start_doy - 1]. The off-by-one here is silent and
    plausible-looking — on SPY's registered window the wrong convention returns
    |t| 5.60 against a shipped 7.25, both of which look like real numbers."""
    r = [(row[b - 1] - row[a - 1]) * scale for row in cums]
    n = len(r)
    mean = sum(r) / n if n else 0.0
    srt = sorted(r)
    median = 0.0 if not n else (srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2)
    var = sum((v - mean) ** 2 for v in r) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    return {"returns": r, "n": n, "mean": mean, "median": median,
            "up": sum(1 for v in r if v > 0), "sd": sd,
            "abs_t": abs(mean) / (sd / math.sqrt(n)) if sd > 0 and n else 0.0}


def cum_scale(ent: dict) -> float:
    """Declared by the producer at calendar.cum_scale (1e-05)."""
    try:
        return float((ent.get("calendar") or {}).get("cum_scale") or 1e-5)
    except (TypeError, ValueError):
        return 1e-5


def q95_of(null: dict | None) -> float | None:
    v = ((null or {}).get("max_abs_t_quantiles") or {}).get("0.95")
    return float(v) if v is not None else None


def null_for(fam: dict, n: int, cov: dict) -> dict | None:
    """The null computed on THIS year count, or nothing.

    Comparing a 10-year |t| against a 25-year null is the quiet dishonesty this
    page exists to avoid, so a lookback with no matching null gets no verdict.
    `family.null.n_years` is the producer's own statement of what it was run on.
    """
    by = fam.get("null_by_lookback") or {}
    if str(n) in by:
        return by[str(n)]
    base = fam.get("null")
    if not base:
        return None
    on = base.get("n_years", cov.get("n_years_complete"))
    return base if on is None or int(on) == n else None


def derive_state(n: int, raw_t: float, raw_null: dict | None,
                 neu_t: float | None, neu_null: dict | None,
                 neutral_panel: bool = False) -> str:
    """own / market / fails / thin (spec §3, four-state chip 4).

    `own` requires the window to clear on BOTH the raw and the market-neutral
    residual panel; `market` is raw-only — a real finding, just not this name's.
    """
    if n < 6:
        return "thin"
    raw_q = q95_of(raw_null)
    if raw_q is None:
        return "nonull"
    if raw_t < raw_q:
        return "fails"
    if not neutral_panel:
        return "market"          # no residual to test: the benchmark itself
    neu_q = q95_of(neu_null)
    if neu_q is None or neu_t is None:
        return "nonull"          # a panel exists but no null for this year count
    return "own" if neu_t >= neu_q else "market"


def _grid(null: dict | None) -> list[tuple[float, float]]:
    """(cdf, |t|) rungs, from the producer's 101-rung ladder when it is shipped,
    otherwise from the three §9 quantiles. Nothing here is interpolated into
    existence — every rung is a number the server computed."""
    ladder = (null or {}).get("max_abs_t_quantile_ladder")
    if isinstance(ladder, list) and len(ladder) >= 2:
        n = len(ladder) - 1
        try:
            return [(i / n, float(v)) for i, v in enumerate(ladder)]
        except (TypeError, ValueError):
            pass
    return sorted(((float(k), float(v))
                   for k, v in (null or {}).get("max_abs_t_quantiles", {}).items()),
                  key=lambda kv: kv[0])


def exceedance(abs_t: float, null: dict | None) -> dict:
    """Share of shuffles whose best window was at least this strong.

    Reads the shipped ladder ONLY — the client never builds a null distribution
    of its own (spec §9). Outside the ladder the honest form is a bound, not a
    number.
    """
    grid = _grid(null)
    if not grid:
        return {"form": "none"}
    if abs_t >= grid[-1][1]:
        return {"form": "lt", "pct": 1, "cdf": grid[-1][0]}
    if abs_t < grid[0][1]:
        return {"form": "gt", "pct": int(round(100 * (1 - grid[0][0]))), "cdf": grid[0][0]}
    for (q_lo, t_lo), (q_hi, t_hi) in zip(grid, grid[1:]):
        if t_lo <= abs_t < t_hi:
            frac = (abs_t - t_lo) / (t_hi - t_lo) if t_hi > t_lo else 0.0
            p = q_lo + frac * (q_hi - q_lo)
            return from_pct(100 * (1 - p), p)
    return {"form": "none"}


def from_pct(pct_raw: float, cdf: float | None = None) -> dict:
    """Whole number, floored at 1 — with B=2,000 the honest floor is 'under 1%'."""
    r = int(round(pct_raw))
    if r < 1:
        return {"form": "lt", "pct": 1, "cdf": cdf if cdf is not None else 0.99}
    return {"form": "exact", "pct": r, "cdf": cdf if cdf is not None else 1 - pct_raw / 100.0}


def chance_track(abs_t: float, null: dict | None) -> dict | None:
    """A |t| axis: a soft ink ramp where the shuffles concentrate, one tick at the
    observed statistic. Every position is a server-shipped rung (spec §3)."""
    grid = _grid(null)
    if len(grid) < 3:
        return None
    at = {round(c, 2): t for c, t in grid}

    def rung(c: float) -> float | None:
        if c in at:
            return at[c]
        below = [t for q, t in grid if q <= c]
        return below[-1] if below else None

    top = rung(0.99) or grid[-1][1]
    xmax = max(top, abs_t) * 1.08 or 1.0
    pos = lambda t: round(max(0.0, min(100.0, 100.0 * t / xmax)), 2)   # noqa: E731
    stops = [(pos(v), o) for v, o in
             ((rung(0.10), 20), (rung(0.25), 40), (rung(0.50), 55),
              (rung(0.75), 40), (rung(0.90), 18), (rung(0.99), 6))
             if v is not None]
    return {"tick": pos(abs_t), "stops": stops} if stops else None


# ── geometry ────────────────────────────────────────────────────────────────
def sample_indices(*must: int) -> list[int]:
    """<=183 cum indices (every second calendar day), always carrying `must`."""
    last = SLOTS - 1
    keep = {max(0, min(last, m)) for m in must} | {0, last}
    out = sorted(set(range(0, last, 2)) | keep)
    i = 1
    while len(out) > MAX_POINTS and i < len(out) - 1:
        if out[i] in keep:
            i += 1
        else:
            out.pop(i)
    return out


def xpos(i: int) -> float:
    return X0 + i * PX


class YScale:
    """Linear over the 5th..95th percentile envelope of the rebased paths, padded
    4% of range and clamped so the 100 baseline is always inside (spec §4)."""

    def __init__(self, cums, scale: float = 1e-5):
        self.scale = scale
        lo, hi = 0.0, 0.0
        n = len(cums)
        for i in range(len(cums[0])):
            col = sorted(row[i] * self.scale for row in cums)
            lo = min(lo, col[max(0, int(0.05 * (n - 1)))])
            hi = max(hi, col[min(n - 1, int(math.ceil(0.95 * (n - 1))))])
        pad = 0.04 * max(hi - lo, 1e-6)
        self.lo, self.hi = lo - pad, hi + pad

    def y(self, v: float) -> float:
        return Y1 - (v - self.lo) / (self.hi - self.lo or 1.0) * (Y1 - Y0)


def _pts(row, scale: YScale, idx):
    return [(xpos(i), scale.y(row[i] * scale.scale)) for i in idx]


def _d(pts) -> str:
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _len(pts) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def col_stat(cums, i: int, kind: str, scale: float = 1e-5) -> float:
    col = sorted(row[i] * scale for row in cums)
    n = len(col)
    if kind == "median":
        return col[n // 2] if n % 2 else (col[n // 2 - 1] + col[n // 2]) / 2
    if kind == "p20":
        return col[int(0.2 * (n - 1))]
    return col[int(math.ceil(0.8 * (n - 1)))]


# ── the window fan (spec §5/§13 — THE signature) ────────────────────────────
FAN_X0, FAN_X1, FAN_DOT_X = 10.0, 450.0, 454.0
FAN_Y0, FAN_Y1 = 10.0, 180.0


def window_fan(cums, years, a: int, b: int, scale: float = 1e-5) -> dict:
    """Every year re-anchored to zero at the window's first day, drawn at the
    WINDOW's own y-scale. The year field answers "when in the year"; this answers
    "how much, how consistently, and how many" — and its end-dot column is the
    countable sample the removed dot row used to carry."""
    span = max(1, b - a)
    if span < 1 or not cums:
        return {"paths": [], "median": "", "zero": (FAN_Y0 + FAN_Y1) / 2, "dots": [], "up": 0}
    step = (FAN_X1 - FAN_X0) / span
    rel = [[(row[i] - row[a - 1]) * scale for i in range(a - 1, b)] for row in cums]
    flat = [v for row in rel for v in row]
    hi, lo = max(flat + [0.0]) * 1.08, min(flat + [0.0]) * 1.08
    rng = (hi - lo) or 1.0
    y = lambda v: FAN_Y0 + (hi - v) / rng * (FAN_Y1 - FAN_Y0)   # noqa: E731

    paths, dots = [], []
    for row, meta in zip(rel, years):
        up = row[-1] > 0
        paths.append({
            "d": "M" + "L".join(f"{FAN_X0 + j * step:.1f},{y(v):.1f}" for j, v in enumerate(row)),
            "up": up,
            "title": f"{int(meta['year'])}: {math.expm1(row[-1]) * 100:+.2f}%",
        })
        dots.append({"cy": round(y(row[-1]), 1), "up": up})
    med = []
    for j in range(span + 1):
        col = sorted(row[j] for row in rel)
        n = len(col)
        med.append(col[n // 2] if n % 2 else (col[n // 2 - 1] + col[n // 2]) / 2)
    return {
        "paths": paths, "dots": dots,
        "median": "M" + "L".join(f"{FAN_X0 + j * step:.1f},{y(v):.1f}" for j, v in enumerate(med)),
        "zero": round(y(0.0), 1),
        "up": sum(1 for d in dots if d["up"]),
    }


def month_rules() -> list[dict]:
    """Rules at each month start. `xpos` takes a cum INDEX, so a day-of-year d
    sits at xpos(d - 1)."""
    out = []
    for m in range(1, 13):
        start = (date(NONLEAP, m, 1) - date(NONLEAP, 1, 1)).days + 1
        nxt = SLOTS + 1 if m == 12 else (date(NONLEAP, m + 1, 1) - date(NONLEAP, 1, 1)).days + 1
        out.append({"x": round(xpos(start - 1), 1),
                    "cx": round((xpos(start - 1) + xpos(nxt - 1)) / 2, 1),
                    "label": MONTH_INITIALS[m - 1]})
    return out


# ── small multiples ─────────────────────────────────────────────────────────
def sm_panel(rows, labels_en, labels_zh, width: float = 320.0) -> dict:
    if not rows:
        return {"bars": [], "zero": 46.0, "w": width}
    vmax = max((abs(float(r.get("mean") or 0.0)) for r in rows), default=0.0) or 1.0
    slot = (width - 12) / len(rows)
    bars = []
    for j, r in enumerate(rows):
        mean = float(r.get("mean") or 0.0)
        h = max(1.5, abs(mean) / vmax * 32)
        cx = 6 + slot * (j + 0.5)
        bars.append({
            "x": round(cx - min(11.0, slot * 0.36), 1), "w": round(min(22.0, slot * 0.72), 1),
            "y": round(46 - h if mean >= 0 else 46, 1), "h": round(h, 1),
            "up": mean >= 0, "cx": round(cx, 1),
            "lab_en": labels_en[j] if j < len(labels_en) else str(r.get("k", j)),
            "lab_zh": labels_zh[j] if j < len(labels_zh) else str(r.get("k", j)),
            "mean": mean, "median": float(r.get("median") or 0.0),
            "up_share": float(r.get("up_share") or 0.0), "n": int(r.get("n") or 0),
        })
    return {"bars": bars, "zero": 46.0, "w": width}


# ── Catalyst mode: the evidence boundary (W2C/W3) ───────────────────────────
# There is no event data. No BioCatalyst source is connected and the producer
# contract does not exist yet, so Catalyst mode ships as an honest UNAVAILABLE
# surface: it states the exact boundary of the evidence rather than reserving
# space for data that will appear later. Nothing below invents an event, a date,
# or a probability — every row is driven by the availability block of
# site/seasonalitydata/methodology.json, and a field that is missing renders NOT
# CONNECTED. `is True` is deliberate: a null, a string, or an absent key is not
# a live feed.
#
# THREE STATES, NOT TWO (adversarial review 2026-08-07). The first cut counted
# five rows and printed "3 not connected", which reads at a glance as "this page
# is 40% built". It is not: exactly ONE source is missing. `Forecasts` and
# `Symbol screening` are not feeds we lack — their own why-clauses say we chose
# never to build them. A design choice wearing the state word NOT CONNECTED is a
# false gap, and the rail (the mode's one non-verbal encoding) was counting it.
# So rows carry a `state`:
#   "on"    — a source we have          (solid rail, CONNECTED)
#   "off"   — a source we want, lack    (dashed rail, NOT CONNECTED)
#   "never" — a thing we chose not to do (no rail at all — it is not on the
#             evidence axis, so it must not be marked on it)
# The counts and the rail now describe SOURCES only, and the ledger can actually
# reach all-connected.
#
# The clause for the event row names the event families the methodology itself
# declares (clocks.event). Slugs never reach the page — an unmapped one folds
# into one plain-word "other event feeds" phrase (doctrine Law 2), so a producer
# adding a clock can never leak `clinical_trial` into the copy.
EVENT_CLOCK_EN = {
    "fda": "regulatory decisions",
    "clinical_trial": "trial readouts",
    "conference": "medical conferences",
    "financing": "financing",
    "commercial": "product launches",
}
# ZH is written for a Chinese reader, not transliterated from the EN (memory:
# zh-copy-was-english-shaped-not-wrong). `试验读数` was "readout" carried across
# letter by letter — 读数 is a meter reading. `上市销售` alone reads as an IPO on
# a stock page, so the product sense is spelled out.
EVENT_CLOCK_ZH = {
    "fda": "监管决定",
    "clinical_trial": "试验结果公布",
    "conference": "医学会议",
    "financing": "融资",
    "commercial": "产品上市",
}
OTHER_CLOCK_EN = "other event feeds"
OTHER_CLOCK_ZH = "其他事件数据源"

# (availability key, name EN, name ZH, why EN, why ZH, is_source). The event
# row's clause is built from the artifact, so it carries None and is filled in
# below. is_source=False marks the two deliberate non-features.
AVAIL_ROWS = [
    ("live_calendar_clock", "Calendar clock", "日历时钟",
     "Every complete year drawn from adjusted closing prices.",
     "以复权收盘价绘制每一个完整年份。", True),
    ("live_selection_correction", "Search accounting", "搜索校正",
     "Counts every window tried before calling one of them strong.",
     "在判定某个窗口是否强势前，计入所有测试过的窗口。", True),
    ("live_event_graph", "Event calendar", "事件日历", None, None, True),
    ("live_forecasts", "Forecasts", "预测",
     "This page reports what past years did. It predicts nothing.",
     "本页只记录过往年份的表现，不做任何预测。", False),
    ("live_screener", "Symbol screening", "跨标的筛选",
     "One symbol at a time. No list here puts names in order.",
     "这里每次只看一个标的，不提供任何排序名单。", False),
]


def event_clock_clause(meth: dict, live: bool = False) -> tuple[str, str]:
    """Name, in plain words, exactly which event feeds the method declares — and
    whether they are connected. The `live` branch is not decoration: an
    unconditional absence clause once rendered "No feed is connected for …"
    underneath the state word CONNECTED (adversarial review 2026-08-07)."""
    keys = ((meth.get("clocks") or {}).get("event")) or []
    en, zh, other = [], [], False
    for k in keys:
        if k in EVENT_CLOCK_EN:
            en.append(EVENT_CLOCK_EN[k])
            zh.append(EVENT_CLOCK_ZH[k])
        else:
            other = True
    if other:
        en.append(OTHER_CLOCK_EN)
        zh.append(OTHER_CLOCK_ZH)
    if not en:
        if live:
            return ("An event feed is connected; this page does not draw it yet.",
                    "已接入事件数据源，但本页尚未绘制。")
        return ("No clinical or regulatory event feed is connected.",
                "尚未接入任何临床或监管事件数据源。")
    listed = en[0] if len(en) == 1 else ", ".join(en[:-1]) + ", or " + en[-1]
    if live:
        return (f"Dates are connected for {listed}; this page does not draw them yet.",
                "、".join(zh) + "，均已接入数据源，但本页尚未绘制。")
    return (f"No feed is connected for {listed}.", "、".join(zh) + "，均无数据源接入。")


def _asof_parts(iso: str) -> date | None:
    """A plain YYYY-MM-DD calendar date, or None.

    STRICT on purpose. The as-of stamp used to be folded through the seasonal
    clock's 365-slot day-of-year helper, which returns slot 1 on any parse
    failure — so an ordinary ISO *timestamp* from a producer ("2026-08-06T00:00:00Z")
    rendered the chip "Through Jan 1", a date computed from nothing, on the one
    surface whose whole thesis is that no figure appears unless an artifact
    produced it (adversarial review 2026-08-07). Availability already fails
    closed; the date must too. Leap day is also correct here — the 365-slot fold
    is a clock convention, and this is a wall-clock date."""
    try:
        return datetime.strptime((iso or "").strip(), "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


def build_catalyst(meth: dict) -> dict:
    """The availability ledger, computed from the methodology artifact only."""
    meth = meth or {}
    avail = meth.get("availability")
    meth_ok = isinstance(avail, dict) and bool(avail)
    avail = avail if isinstance(avail, dict) else {}
    rows = []
    for key, en, zh, w_en, w_zh, is_source in AVAIL_ROWS:
        live = avail.get(key) is True
        if key == "live_event_graph":
            w_en, w_zh = event_clock_clause(meth, live)
        rows.append({"key": key, "en": en, "zh": zh, "why_en": w_en, "why_zh": w_zh,
                     "live": live, "source": is_source,
                     "state": ("on" if live else "off") if is_source else "never"})
    sources = [r for r in rows if r["source"]]
    asof = _asof_parts(meth.get("as_of") or "")
    return {
        "rows": rows,
        # counts describe SOURCES only — a thing we chose not to build is not a gap
        "n_live": sum(1 for r in sources if r["live"]),
        "n_dark": sum(1 for r in sources if not r["live"]),
        "n_never": len(rows) - len(sources),
        "meth_ok": meth_ok,
        "event_live": avail.get("live_event_graph") is True,
        "clock_live": avail.get("live_calendar_clock") is True,
        "correction_live": avail.get("live_selection_correction") is True,
        # The year is carried, and the idiom differs from the price-coverage
        # chip's "Through Aug 5": two bare month-day stamps in one masthead, in
        # the same words the seasonal window chips use, is ambiguous on a
        # 25-year page and a two-year-stale method looked identical to today's.
        "asof_en": f"{asof.strftime('%b')} {asof.day}, {asof.year}" if asof else "",
        "asof_zh": f"{asof.year}年{asof.month}月{asof.day}日" if asof else "",
    }


def load_methodology(root: Path) -> dict:
    """The published method contract. Unreadable or absent -> {}, which renders
    every source NOT CONNECTED and says so as a fact about the METHOD FILE, never
    as a claim about the page: the calendar mode is drawn from the entity
    artifact and keeps drawing whatever this file says (adversarial review
    2026-08-07 — the old copy read "Nothing on this page is connected right now"
    one click away from 25 drawn years and a verdict)."""
    path = root / "site" / "seasonalitydata" / "methodology.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("seasonalitydata/methodology.json unreadable: %s", exc)
        return {}


# ── entity loading ──────────────────────────────────────────────────────────
def load_entity(root: Path) -> tuple[dict, dict | None, bool]:
    """(entity, index, is_example). Prefers the nightly artifact; falls back to the
    committed worked example so the page is never blank before the producer lands."""
    sdir = root / "site" / "seasonalitydata"
    index = None
    if (sdir / "index.json").is_file():
        try:
            index = json.loads((sdir / "index.json").read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("seasonalitydata/index.json unreadable: %s", exc)
    symbol = (index or {}).get("default_symbol", "SPY")
    epath = sdir / "entities" / f"{symbol}.json"
    if epath.is_file():
        try:
            return json.loads(epath.read_text()), index, False
        except Exception as exc:  # noqa: BLE001
            log.warning("%s unreadable (%s) — falling back to the worked example", epath, exc)
    fdir = root / "tests" / "fixtures" / "seasonality"
    ent = json.loads((fdir / "SPY.entity.json").read_text())
    if index is None and (fdir / "index.json").is_file():
        index = json.loads((fdir / "index.json").read_text())
    return ent, index, True


def _doy_of_iso(iso: str) -> int:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return 1
    doy = d.timetuple().tm_yday
    leap = (d.year % 4 == 0 and d.year % 100 != 0) or d.year % 400 == 0
    return doy - 1 if leap and doy >= 60 else doy


def build_view(ent: dict, index: dict | None, is_example: bool,
               methodology: dict | None = None) -> dict:
    cov = ent.get("coverage") or {}
    scale = cum_scale(ent)
    years_all = ent.get("years") or []
    lookback = len(years_all)          # the default view is the whole shipped panel
    sel = years_all
    cums = [y["cum"] for y in sel]
    n = len(sel)

    dw = ent.get("default_window") or {}
    a = int(dw.get("start_doy") or 1)
    b = int(dw.get("end_doy") or min(SLOTS, a + 30))
    stats = window_stats(cums, a, b, scale)

    fam = ent.get("family") or {}
    null = null_for(fam, n, cov)

    mkt = ((ent.get("neutral") or {}).get("market")) or None
    neu_t, neu_null = None, None
    if mkt and mkt.get("years"):
        nyears = [y["cum"] for y in mkt["years"]]
        neu_t = window_stats(nyears, a, b, scale)["abs_t"]
        neu_null = null_for(mkt.get("family") or {}, len(nyears), cov)

    # The registered window's state is the SERVER's (spec §12.6); only a window the
    # user drags is derived client-side from the same shipped quantiles.
    state = dw.get("state") if dw.get("state") in ("own", "market", "fails", "thin") else None
    if state is None:
        state = derive_state(n, stats["abs_t"], null, neu_t, neu_null, bool(mkt))

    # Spec §16: for the market benchmark the residual is empty BY CONSTRUCTION, so
    # the engine's honest `market` becomes circular copy — "this is really the
    # market's calendar" about the symbol that IS the market. Override the words,
    # never the state: the artifact keeps saying `market`.
    self_benchmark = dw.get("neutral_basis") == "self_benchmark"

    if dw.get("null_max_exceedance_pct") is not None:
        exc = from_pct(float(dw["null_max_exceedance_pct"]))
    else:
        exc = exceedance(stats["abs_t"], null)

    bucket = season_bucket(a, b)
    rising = stats["median"] >= 0
    season_en = f"{SEASON_EN[bucket]} {DIR_EN[rising]}"
    season_zh = f"{SEASON_ZH[bucket]}{DIR_ZH[rising]}"

    yscale = YScale(cums, scale)
    idx = sample_indices(0, a - 1, b - 1, SLOTS - 1)

    strands, rows = [], []
    vmax = max((abs(v) for v in stats["returns"]), default=0.0) or 1.0
    for row, meta, ret in zip(cums, sel, stats["returns"]):
        strands.append(_d(_pts(row, yscale, idx)))
        simple = math.expm1(ret)
        rows.append({"year": int(meta["year"]), "ret": simple, "up": simple > 0,
                     "w": round(abs(ret) / vmax * 100, 1)})

    med_pts = [(xpos(i), yscale.y(col_stat(cums, i, "median", scale))) for i in idx]
    top = [(xpos(i), yscale.y(col_stat(cums, i, "p80", scale))) for i in idx]
    bot = [(xpos(i), yscale.y(col_stat(cums, i, "p20", scale))) for i in idx]

    cur = ent.get("current_year") or None
    cur_path, today_x = None, None
    if cur and cur.get("cum") and len(cur["cum"]) > 2:
        last = int(cur.get("last_index") if cur.get("last_index") is not None
                   else len(cur["cum"]) - 1)
        last = max(0, min(last, len(cur["cum"]) - 1))
        cidx = [i for i in sample_indices(0, last) if i <= last]
        if len(cidx) > 1:
            cur_path = _d(_pts(cur["cum"], yscale, cidx))
            today_x = round(xpos(last), 1)

    views = ent.get("views") or {}
    tdom = views.get("trading_day_of_month") or []
    tlab = [str(r.get("k", i + 1)) for i, r in enumerate(tdom)]

    entities = (index or {}).get("entities") or [
        {"symbol": ent.get("symbol"), "name": ent.get("name"),
         "n_years_panel": cov.get("n_years_complete")}]
    rates = (index or {}).get("program_rates") or {}
    raw_rate = rates.get("raw") or {}

    return {
        "symbol": ent.get("symbol", ""), "name": ent.get("name", ""),
        "asof": ent.get("asof", ""),
        "asof_en": md_en(_doy_of_iso(ent.get("asof", ""))) if ent.get("asof") else "",
        "asof_zh": md_zh(_doy_of_iso(ent.get("asof", ""))) if ent.get("asof") else "",
        "is_example": is_example, "n": n, "lookback": lookback,
        "coverage": cov, "price_source": ent.get("price_source") or {},
        "has_neutral": bool(mkt and mkt.get("years")),
        "self_benchmark": self_benchmark,
        "win": {"a": a, "b": b, "a_en": md_en(a), "b_en": md_en(b),
                "a_zh": md_zh(a), "b_zh": md_zh(b),
                "a_iso": md_iso(a), "b_iso": md_iso(b),
                "source": dw.get("source", "registered")},
        "stats": stats, "median_simple": math.expm1(stats["median"]),
        "state": state, "exc": exc,
        "track": chance_track(stats["abs_t"], null),
        "stability": (dw.get("stability") or {}).get("survives")
                     if isinstance(dw.get("stability"), dict) else None,
        "season_en": season_en, "season_zh": season_zh,
        "geom": {
            "strands": strands,
            "band": _d(top) + "L" + "L".join(f"{x:.1f},{y:.1f}" for x, y in reversed(bot)) + "Z",
            "median": _d(med_pts), "median_len": int(_len(med_pts)) + 8,
            "baseline_y": round(yscale.y(0.0), 1),
            "gate_x1": round(xpos(a - 1), 1), "gate_x2": round(xpos(b - 1), 1),
            "months": month_rules(), "cur": cur_path, "today_x": today_x,
        },
        "rows": rows, "fan": window_fan(cums, sel, a, b, scale),
        "sm": {"month": sm_panel(views.get("month") or [], MONTH_INITIALS, MONTH_ZH),
               "weekday": sm_panel(views.get("weekday") or [], WEEKDAY_EN, WEEKDAY_ZH),
               "tdom": sm_panel(tdom, tlab, tlab)},
        "entities": entities,
        "catalyst": build_catalyst(methodology or {}),
        "n_entities": (index or {}).get("n_entities") or len(entities),
        "program": {"n_symbols": raw_rate.get("n_symbols"),
                    "n_clearing": raw_rate.get("n_clearing"),
                    "per_100": round(float(raw_rate["share"]) * 100)
                               if raw_rate.get("share") is not None else None},
        "family": {"n_candidates": fam.get("n_candidates"),
                   "horizons": len(fam.get("horizons_days") or []),
                   "B": (null or {}).get("B"), "q95": q95_of(null)},
        "payload": json.dumps(ent, separators=(",", ":")).replace("<", "\\u003c"),
    }


def render(root: Path) -> str:
    from jinja2 import Environment, FileSystemLoader

    ent, index, is_example = load_entity(root)
    view = build_view(ent, index, is_example, load_methodology(root))
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    env.globals.update(zip=zip, abs=abs, enumerate=enumerate)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return env.get_template("stock_seasonality.html.j2").render(v=view, built=built)


def main() -> int:
    root = config.ROOT
    try:
        html = render(root)
    except Exception as exc:  # noqa: BLE001 — additive, never fatal to the render lane
        log.error("stock seasonality page failed: %s", exc)
        print(f"::warning title=stock_seasonality::page not rebuilt ({exc})", flush=True)
        return 0
    out = root / "site" / "stock_seasonality.html"
    write_page(out, html)
    log.info("wrote %s (%d KB)", out, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
