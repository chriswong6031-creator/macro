#!/usr/bin/env python3
"""Regenerate the MU seasonality entity fixture from committed adjusted closes.

SPY.entity.json and index.json are NOT generated here — they are the producer
lane's own committed artifacts (PR #4235, site/seasonalitydata/), vendored
verbatim so the page is tested against the real contract rather than against a
re-implementation of it. This script exists for MU, which the producer does not
commit (R2-published, §14) but which the page needs: SPY is the market benchmark,
so its market-neutral residual is empty by construction and the `own` branch of
chip 4 plus the whole Vs-market recompute path would otherwise be unexercised.

Emitted in the producer's exact shape: 365-value `cum` arrays indexed
`doy - 1`, `calendar.cum_encoding` / `cum_scale` / `window_convention`,
`family.null.max_abs_t_quantile_ladder` (101 rungs), `default_window.neutral_basis`.

Emits SPY.entity.json (the page's default symbol — the benchmark itself, so its
market-neutral residual is definitionally empty and chip 4 reads "The market's
pattern") and MU.entity.json (a name that carries calendar structure of its own
after the market leg is removed, so chip 4 reads "Its own pattern"). Between them
the two fixtures exercise every branch of the four-state chip.

The Lane-2 page (templates/stock_seasonality.html.j2) consumes the
`biopharma_seasonality.entity.v1` contract pinned in the Lane-2 design spec §9.
Its producer lives in a separate lane; this script builds a REAL-SHAPED panel
from data/yahoo/SPY.parquet so the page can be server-rendered, browser-verified
and unit-tested against honest numbers instead of invented ones.

Nothing here is a stand-in for the producer: every number is computed from
committed adjusted closes, including the family null (2,000 independent circular
year-shift resamples, maximum |t| over the whole window grid per resample).

Usage:  python3 tests/fixtures/seasonality/make_spy_fixture.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BENCH = "SPY"
NAMES = {"SPY": "SPDR S&P 500 ETF Trust", "MU": "Micron Technology, Inc."}
GROUPS = {"SPY": ("index", "Index"), "MU": ("stock", "Information Technology")}

SLOTS = 365                      # 01-01 .. 12-31, Feb-29 folded into the 02-28 slot
HORIZONS = [5, 10, 15, 20, 30, 45, 60, 90]
B = 2000
LOOKBACKS = [10, 15, 25]
CAP = 25
SEED = 20260802

# Spec §9 requires 0.90/0.95/0.99. The extra grid points are additive and let the
# client interpolate an HONEST exceedance for a window the user drags, instead of
# collapsing every dragged read to ">10%" (spec §3, graded after-search line).
QUANTILES = [0.90, 0.95, 0.99]          # the three §9 requires
LADDER = [i / 100 for i in range(101)]  # the producer's 101-rung empirical CDF
WINDOW_CONVENTION = (
    "start_doy/end_doy are 1-based day-of-year; cum index = doy - 1; "
    "window log return = cum[end_doy - 1] - cum[start_doy - 1] "
    "(enter at the start_doy close, exit at the end_doy close)"
)


def slot_of(ts: pd.Timestamp) -> int:
    """1-based non-leap day-of-year. 02-29 folds into the 02-28 slot (=59)."""
    doy = int(ts.dayofyear)
    leap = bool(pd.Timestamp(year=ts.year, month=12, day=31).dayofyear == 366)
    if leap and doy >= 60:
        doy -= 1
    return doy


def slot_labels() -> list[str]:
    base = pd.date_range("2001-01-01", "2001-12-31", freq="D")   # non-leap year
    return [d.strftime("%m-%d") for d in base]


def year_paths(close: pd.Series) -> dict[int, np.ndarray]:
    """Per-year cumulative log path, length 366 (index 0 = year start, cum 0)."""
    out: dict[int, np.ndarray] = {}
    for year, grp in close.groupby(close.index.year):
        cum = np.zeros(SLOTS + 1, dtype=float)
        base = float(grp.iloc[0])
        last = 0.0
        idx = 0
        for ts, px in grp.items():
            s = slot_of(ts)
            if s <= idx:            # 02-29 folds onto 02-28: keep the later value
                cum[s] = np.log(float(px) / base)
                last = cum[s]
                continue
            cum[idx + 1:s + 1] = last       # non-trading days carry zero log return
            cum[s] = np.log(float(px) / base)
            last = cum[s]
            idx = s
        cum[idx + 1:] = last
        out[year] = cum
    return out


def complete_years(close: pd.Series) -> list[int]:
    """first session <= Jan 10 and last session >= Dec 20."""
    keep = []
    for year, grp in close.groupby(close.index.year):
        first, last = grp.index[0], grp.index[-1]
        if first.month == 1 and first.day <= 10 and last.month == 12 and last.day >= 20:
            keep.append(int(year))
    return sorted(keep)


def window_t(cums: np.ndarray, a: int, b: int) -> tuple[float, float, float, float, float]:
    """(mean, median, share_up, sd, |t|) of the per-year window log return."""
    r = cums[:, b] - cums[:, a]
    n = r.size
    mean = float(r.mean())
    sd = float(r.std(ddof=1))
    t = abs(mean) / (sd / np.sqrt(n)) if sd > 0 else 0.0
    return mean, float(np.median(r)), float((r > 0).mean()), sd, float(t)


def family_windows() -> list[tuple[int, int]]:
    """start_days 1..365 restricted so start + horizon <= 365 (never wraps the year)."""
    return [(a, a + h) for h in HORIZONS for a in range(1, SLOTS - h + 1)]


def max_abs_t_null(daily: np.ndarray, windows: list[tuple[int, int]], rng) -> np.ndarray:
    """Independent circular year-shift null: each year rolls by its OWN offset, then the
    ENTIRE window grid is recomputed and only then is the maximum taken (Westfall-Young:
    dependence between hypotheses is preserved, calendar alignment is destroyed)."""
    n_years, n_days = daily.shape
    starts = np.array([a for a, _ in windows])
    ends = np.array([b for _, b in windows])
    out = np.empty(B, dtype=float)
    for i in range(B):
        offsets = rng.integers(0, n_days, size=n_years)
        rolled = np.empty_like(daily)
        for y in range(n_years):
            rolled[y] = np.roll(daily[y], int(offsets[y]))
        cum = np.concatenate([np.zeros((n_years, 1)), np.cumsum(rolled, axis=1)], axis=1)
        r = cum[:, ends] - cum[:, starts]           # (n_years, n_windows)
        mean = r.mean(axis=0)
        sd = r.std(axis=0, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.abs(mean) / (sd / np.sqrt(n_years))
        out[i] = float(np.nanmax(t))
    return out


def per_year_view(close: pd.Series, years: list[int], key) -> list[dict]:
    """Year-based small-multiple panel: one complete year is one observation."""
    lr = np.log(close / close.shift(1)).dropna()
    lr = lr[lr.index.year.isin(years)]
    frame = pd.DataFrame({"r": lr.values}, index=lr.index)
    frame["k"] = key(frame.index)
    frame["y"] = frame.index.year
    rows = []
    for k, grp in frame.groupby("k"):
        per_year = grp.groupby("y")["r"].mean()
        if per_year.empty:
            continue
        simple = np.expm1(per_year.values)
        rows.append({
            "k": int(k),
            "mean": round(float(simple.mean()), 6),
            "median": round(float(np.median(simple)), 6),
            "up_share": round(float((simple > 0).mean()), 4),
            "n": int(per_year.size),
        })
    return sorted(rows, key=lambda r: r["k"])


def month_view(close: pd.Series, years: list[int]) -> list[dict]:
    """Per-year CALENDAR-MONTH return (not a daily average) — the natural month read."""
    lr = np.log(close / close.shift(1)).dropna()
    lr = lr[lr.index.year.isin(years)]
    frame = pd.DataFrame({"r": lr.values}, index=lr.index)
    frame["k"] = frame.index.month
    frame["y"] = frame.index.year
    rows = []
    for k, grp in frame.groupby("k"):
        per_year = grp.groupby("y")["r"].sum()
        simple = np.expm1(per_year.values)
        rows.append({
            "k": int(k),
            "mean": round(float(simple.mean()), 6),
            "median": round(float(np.median(simple)), 6),
            "up_share": round(float((simple > 0).mean()), 4),
            "n": int(per_year.size),
        })
    return sorted(rows, key=lambda r: r["k"])


def tdom_view(close: pd.Series, years: list[int]) -> list[dict]:
    lr = np.log(close / close.shift(1)).dropna()
    lr = lr[lr.index.year.isin(years)]
    frame = pd.DataFrame({"r": lr.values}, index=lr.index)
    frame["y"] = frame.index.year
    frame["ym"] = frame.index.year * 100 + frame.index.month
    frame["k"] = frame.groupby("ym").cumcount() + 1
    frame = frame[frame["k"] <= 23]
    rows = []
    for k, grp in frame.groupby("k"):
        per_year = grp.groupby("y")["r"].mean()
        simple = np.expm1(per_year.values)
        rows.append({
            "k": int(k),
            "mean": round(float(simple.mean()), 6),
            "median": round(float(np.median(simple)), 6),
            "up_share": round(float((simple > 0).mean()), 4),
            "n": int(per_year.size),
        })
    return sorted(rows, key=lambda r: r["k"])


def neutral_paths(close: pd.Series, bench: pd.Series) -> tuple[dict[int, np.ndarray], float]:
    """Market-neutral residual paths: r_i - beta_t * r_m, beta from a point-in-time
    trailing 252-session regression SHIFTED one session (never uses same-day data)."""
    lr = np.log(close / close.shift(1)).dropna()
    lm = np.log(bench / bench.shift(1)).dropna()
    both = pd.concat({"i": lr, "m": lm}, axis=1).dropna()
    cov = both["i"].rolling(252).cov(both["m"])
    var = both["m"].rolling(252).var()
    beta = (cov / var).shift(1)
    resid = (both["i"] - beta * both["m"]).dropna()
    # residual daily log returns -> per-year rebased cumulative paths
    out: dict[int, np.ndarray] = {}
    for year, grp in resid.groupby(resid.index.year):
        cum = np.zeros(SLOTS + 1, dtype=float)
        run, idx = 0.0, 0
        for ts, r in grp.items():
            s = slot_of(ts)
            if s <= idx:
                run += float(r)
                cum[s] = run
                continue
            cum[idx + 1:s + 1] = run
            run += float(r)
            cum[s] = run
            idx = s
        cum[idx + 1:] = run
        out[int(year)] = cum
    return out, float(beta.dropna().iloc[-1]) if not beta.dropna().empty else float("nan")


def null_for(panel: np.ndarray, windows, rng) -> tuple[dict, np.ndarray]:
    draws = max_abs_t_null(np.diff(panel, axis=1), windows, rng)
    return {
        "method": "independent_circular_year_shift",
        "B": B,
        "max_abs_t_quantiles": {
            f"{q:.2f}": round(float(np.quantile(draws, q)), 4) for q in QUANTILES
        },
        "n_years": int(panel.shape[0]),
        "max_abs_t_quantile_ladder": [
            round(float(np.quantile(draws, q)), 4) for q in LADDER
        ],
    }, draws


def abs_t_grid(panel: np.ndarray, windows) -> np.ndarray:
    s = np.array([a for a, _ in windows]); e = np.array([b for _, b in windows])
    r = panel[:, e] - panel[:, s]
    sd = r.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.abs(r.mean(axis=0)) / (sd / np.sqrt(panel.shape[0]))


SHIFTS = [-5, -2, 2, 5]


def stability(panel: np.ndarray, a: int, b: int) -> dict:
    """A genuine season survives being nudged; a recurring DATE (earnings, expiry,
    a rebalance) does not. Spec §15: sign unchanged at all four shifts AND median
    shifted |t| >= 60% of the unshifted |t|."""
    n = panel.shape[0]
    def stat(x, y):
        r = panel[:, y] - panel[:, x]
        sd = r.std(ddof=1)
        return r.mean(), (abs(r.mean()) / (sd / np.sqrt(n)) if sd > 0 else 0.0)
    base_mean, base_t = stat(a, b)
    ts, signs, ok = [], [], True
    for d in SHIFTS:
        x, y = a + d, b + d
        if x < 1 or y > SLOTS:
            ok = False
            ts.append(0.0)
            signs.append(False)
            continue
        m, t = stat(x, y)
        ts.append(round(float(t), 4))
        signs.append(bool(np.sign(m) == np.sign(base_mean)))
    sign_stable = bool(ok and all(signs))
    survives = bool(sign_stable and float(np.median(ts)) >= 0.60 * base_t)
    return {"shifts_days": SHIFTS, "abs_t": ts,
            "sign_stable": sign_stable, "survives": survives}


def build(symbol: str) -> dict:
    print(f"[{symbol}]")
    close = pd.read_parquet(ROOT / "data" / "yahoo" / f"{symbol}.parquet")["close"].dropna()
    close.index = pd.to_datetime(close.index)

    done = complete_years(close)
    shipped = [y for y in done if y > done[-1] - CAP][-CAP:]
    paths = year_paths(close)
    cums = np.array([paths[y] for y in shipped])
    n = len(shipped)

    asof = close.index[-1]
    cur_year = int(asof.year)
    cur = paths.get(cur_year)
    cur_last = slot_of(asof) if cur_year not in shipped else None

    windows = family_windows()
    rng = np.random.default_rng(SEED)

    # raw null, one run per selectable lookback (the |t| a user sees depends on n)
    nulls, draws_by_n = {}, {}
    for lb in LOOKBACKS:
        sub = cums[-lb:] if lb <= n else cums
        nulls[str(len(sub))], draws_by_n[len(sub)] = null_for(sub, windows, rng)
        print(f"  raw null {len(sub)}y: 95th max|t| = "
              f"{nulls[str(len(sub))]['max_abs_t_quantiles']['0.95']}")

    # The producer ships 365 values indexed doy-1; the internal arrays carry a
    # leading year-start 0 at index 0, so drop it on the way out. The family math
    # is unchanged by this — cum[b-1]-cum[a-1] on the shipped array is the same
    # difference as cum[b]-cum[a] on the internal one.
    q = lambda arr: [int(round(v * 1e5)) for v in arr[1:]]   # noqa: E731
    tt = abs_t_grid(cums, windows)
    best = int(np.nanargmax(tt))
    best_a, best_b = windows[best]
    best_t = float(tt[best])
    raw_q95 = nulls[str(n)]["max_abs_t_quantiles"]["0.95"]
    raw_clears = bool(best_t >= raw_q95)
    exceed = 100.0 * float((draws_by_n[n] >= best_t).mean())

    # ---- market-neutral residual panel ---------------------------------------------
    neutral, neutral_clears = None, False
    if symbol != BENCH:
        bench = pd.read_parquet(ROOT / "data" / "yahoo" / f"{BENCH}.parquet")["close"].dropna()
        bench.index = pd.to_datetime(bench.index)
        npaths, last_beta = neutral_paths(close, bench)
        nyears = [y for y in shipped if y in npaths]
        npanel = np.array([npaths[y] for y in nyears])
        # One neutral null per selectable lookback, exactly like the raw panel: the
        # Vs-market lens must stay answerable at every lookback, not just the default.
        nnulls = {}
        for lb in LOOKBACKS:
            sub = npanel[-lb:] if lb <= len(nyears) else npanel
            nnulls[str(len(sub))], _ = null_for(sub, windows, rng)
        nnull = nnulls[str(len(nyears))]
        nt = abs_t_grid(npanel, windows)
        same = [i for i, w in enumerate(windows) if w == (best_a, best_b)][0]
        n_t_same = float(nt[same])
        neutral_clears = bool(n_t_same >= nnull["max_abs_t_quantiles"]["0.95"])
        print(f"  neutral panel {len(nyears)}y trailing beta {last_beta:.2f}: "
              f"same-window |t| {n_t_same:.3f} vs 95th {nnull['max_abs_t_quantiles']['0.95']} "
              f"-> clears={neutral_clears}")
        neutral = {"market": {
            "benchmark": BENCH,
            "beta_source": "pit_trailing_252d_shifted_one_session",
            "years": [{"year": int(y), "cum": q(npaths[y])} for y in nyears],
            "family": {
                "n_candidates": len(windows),
                "start_days": "1..365, restricted so start + horizon <= 365 (windows never wrap the year)",
                "horizons_days": HORIZONS,
                "statistic": "abs_t_of_mean_window_log_return_across_years",
                "null": nnull,
                "null_by_lookback": nnulls,
            },
        }}
    else:
        # The benchmark's own market-neutral residual is identically zero: there is
        # no panel to ship. The producer emits an EMPTY object here, not a null
        # market key, and flags it with default_window.neutral_basis.
        neutral = {}

    state = ("thin" if n < 6 else
             "own" if (raw_clears and neutral_clears) else
             "market" if raw_clears else "fails")
    print(f"  best window {best_a}->{best_b} |t|={best_t:.3f} exceed={exceed:.2f}% state={state}")

    group, sector = GROUPS.get(symbol, ("stock", ""))
    return {
        "schema": "biopharma_seasonality.entity.v1",
        "symbol": symbol,
        "name": NAMES.get(symbol, symbol),
        "asof": asof.strftime("%Y-%m-%d"),
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "price_source": {"vendor": "yahoo", "adjustment": "vendor_current_vintage",
                         "is_pit_adjustment": False, "field": "close_adjusted"},
        "coverage": {
            "n_years_complete": n, "first_year": shipped[0], "last_complete_year": shipped[-1],
            "n_years_available": len(done), "years_capped_at": CAP,
            "complete_year_rule": "first session <= Jan 10 and last session >= Dec 20",
            "missing_session_policy": "non_trading_days_carry_zero_log_return",
            "leap_policy": "02-29_log_return_added_into_02-28_slot",
        },
        "calendar": {"basis": "calendar_day", "n_slots": SLOTS, "labels": slot_labels(),
                     "cum_encoding": "int_1e-5_log_return", "cum_scale": 1e-05,
                     "window_convention": WINDOW_CONVENTION},
        "group": group,
        "sector": sector,
        "years": [{"year": int(y), "cum": q(paths[y])} for y in shipped],
        "current_year": ({"year": cur_year, "last_index": cur_last - 1,
                          "cum": q(cur[:cur_last + 1])}
                         if cur is not None and cur_last is not None else None),
        "aggregate": {
            "median": q(np.median(cums, axis=0)), "p20": q(np.quantile(cums, 0.20, axis=0)),
            "p80": q(np.quantile(cums, 0.80, axis=0)), "mean_log": q(cums.mean(axis=0)),
        },
        "views": {
            "month": month_view(close, shipped),
            "weekday": per_year_view(close, shipped, lambda ix: ix.dayofweek),
            "trading_day_of_month": tdom_view(close, shipped),
        },
        "family": {
            "n_candidates": len(windows),
            "start_days": "1..365, restricted so start + horizon <= 365 (windows never wrap the year)",
            "horizons_days": HORIZONS,
            "statistic": "abs_t_of_mean_window_log_return_across_years",
            "null": nulls[str(n)],
            "null_by_lookback": nulls,
        },
        "default_window": {
            "start_doy": best_a, "end_doy": best_b, "source": "symbol_best",
            "abs_t": round(best_t, 4), "null_max_exceedance_pct": round(exceed, 2),
            "state": state, "raw_clears": raw_clears, "neutral_clears": neutral_clears,
            "stability": stability(cums, best_a, best_b),
            "neutral_basis": "self_benchmark" if symbol == BENCH else "market_residual",
        },
        "neutral": neutral,
    }


def main() -> int:
    ent = build("MU")
    out = HERE / "MU.entity.json"
    out.write_text(json.dumps(ent, separators=(",", ":")) + "\n")
    print(f"wrote {out.name} ({out.stat().st_size // 1024} KB)")
    print("SPY.entity.json and index.json are the producer's committed artifacts "
          "— vendored, not generated here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
