"""W-F — the US 200-day RECLAIM-VETO decision packet (research; NO behaviour change).

WHAT THIS IS.  `engine.signal_quality._buy_filter` applies one leg — call it the RECLAIM
VETO — to a name that is BOTH below its 200-day average AND weekly-down: such a name is
admitted only if it closes back above the 200-day line within 2 bars (`reclaim`) on top of
the next-bar follow-through (`held`) every other name gets.  The leg is ON by default
everywhere and this instrument does not change that.  It assembles the US mirror of the
evidence HK used when it took the era stamp (#4470, `hk_prophet_v2`): what did the leg
REFUSE on the current US tape, and what happened next — printed on both sides.

WHY A PACKET AND NOT A FLIP.  The buy-filter this leg belongs to is a DRAWDOWN tool with a
measured benefit: it cut average max drawdown -23.7% -> -15.5% across 110 held-out US names
(84% improved) — `engine/signal_quality.py:7`.  That validation was measured WITH the leg
on.  So the honest question is not "is the veto good" but "what does it cost on this tape,
beside the drawdown benefit it was shipped for" — a two-sided ledger for an operator
era-stamp decision (us_prophet_v1 -> v2), exactly as HK's was.  NOTHING here recommends a
flip; `reclaim_veto` stays True at every entry point (pinned by
tests/test_hk_reclaim_veto_policy.py::test_every_entry_point_defaults_to_the_validated_policy).

THE CONSTRUCTION — the crux: the counterfactual moves ONE leg, and we prove it did.
`analyze()` takes `reclaim_veto` as a keyword and `signal_frame()` does NOT depend on it, so
the SAME production function is called twice on the SAME series and every other leg (the
CB/revBuy confluence, the bearish-divergence veto, the weekly gate, the 200-day gate itself)
is re-evaluated identically under both settings.  The refusal set is then the MARKER DIFF:

    on  = analyze(t, close, reclaim_veto=True)      # what the board does today
    off = analyze(t, close, reclaim_veto=False)     # the same engine, that one leg dropped
    refused = { d : on[d].quality == "block"
                    and on[d].reason == "counter-trend, no 200-reclaim/hold"
                    and off[d].quality == "take" }

A date in that set is provably refused SOLELY by the reclaim leg.  Read the branch in
`_buy_filter` to see why the two conditions together are exactly the isolation:
  * the block reason pins `below AND weekly-down` and `not (held and reclaim)`;
  * `off == "take"` on the SAME bar pins `held is True` (the veto=False branch returns
    `held`), which leaves `reclaim is False` as the only remaining cause;
  * a bearish-divergence veto would have returned the SAME reason under both settings, so
    it cannot enter the set; a bar too near the end returns "pending" under `on`, not
    "block", so it cannot enter either.
`reclaim_only_refusals()` below is that predicate as a pure function, unit-tested in
tests/test_us_reclaim_veto_packet.py alongside a direct `_buy_filter` branch test — the
predicate must not be a paraphrase of the engine, so the tests drive the REAL function.

NO LOOK-AHEAD — the anchor is the crux #2.  `_buy_filter` reads bars i+1 and i+2, so the
label at bar i is knowable only in the FUTURE relative to i; `signal_quality`'s docstring
makes marker-date grading FORBIDDEN (a 'take' marker carries +5.7pp/10d of look-ahead).
The refusal verdict needs `reclaim` to have failed at BOTH i+1 and i+2, so it is first
knowable at the close of 3D bar i+2.  Every forward return here is therefore anchored on
the last DAILY close inside 3D bar i+2 — the confirmation close — never on the marker date.
That is a strictly more conservative entry than the signal bar: it concedes the first two
3D bars of any move to the veto's side of the ledger.

UNITS + CENSORING.  One row per (ticker, refusal date).  Forward horizons are DAILY
sessions on the panel's own trading calendar, +10/+21/+63 from the anchor, raw and excess
vs SPY, plus MAE (max adverse excursion) within 21.  The panel ends at its last cached bar,
so a refusal in the last H sessions has NO complete H-horizon: those rows are recorded as
null and EXCLUDED from that horizon's aggregate, with the surviving n printed per horizon.
The 63-session column is censored hardest by construction and must be read as the thinnest.

PANEL.  The curated stock universe caches (breadth / midcap_breadth / smallcap_breadth
`_closes_cache.parquet`) — the same loader idiom as `runner_exclusion_audit.load_universe`.
Read-only: writes exactly one JSON next to this file.

Run:  python3 research/prophet_us_audit/reclaim_veto_packet.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

# PRICE-ADJUSTMENT AUDIT (2026-08-06) — see PRICE_ADJUSTMENT_AUDIT_2026-08-06.md.
import price_ladder  # noqa: E402

PRICE_BASIS = os.environ.get("PRICE_BASIS", "cache").strip().lower()
if PRICE_BASIS not in ("cache", "adjusted"):
    raise SystemExit(f"PRICE_BASIS must be 'cache' or 'adjusted', got {PRICE_BASIS!r}")
OUT = os.path.join(HERE, "reclaim_veto_packet_results_2026-08-05.json"
                   if PRICE_BASIS == "cache"
                   else "reclaim_veto_packet_adjusted_rerun.json")
PANEL_PROVENANCE: dict = {}

from engine import signal_quality as sq  # noqa: E402

# The exact string `_buy_filter` returns on the branch this packet is about. BOUND to the
# engine constant, never copied: #4583 split the single counter-trend refusal into
# CT_BOTH_FAIL (both legs tested, both failed) and CT_RECLAIM_FAIL (the hold PASSED, the
# reclaim did not). This packet is about the SECOND — a name that held and was refused
# anyway — so the pre-split literal kept here silently became the OTHER case's label and
# emptied the refusal set. A copy could drift again; a reference cannot.
BLOCK_REASON = sq.CT_RECLAIM_FAIL
TAKE_QUALITY = "take"

WINDOW_SESSIONS = 126           # the trailing panel window refusals are drawn from
HORIZONS = (10, 21, 63)         # daily forward sessions from the confirmation anchor
MAE_HORIZON = 21
LOSER_PP = -3.0                 # excess-return threshold (pp) defining a loser at 21
WINNER_PP = 3.0
DD_BANDS = ((0.0, 20.0, "0-20%"), (20.0, 35.0, "20-35%"), (35.0, np.inf, ">35%"))
BENCH = "SPY"
MIN_BARS = 300                  # signal_frame needs >=90 3B bars; 300 daily is the floor


# --------------------------------------------------------------------------- panel
def load_panel() -> pd.DataFrame:
    """The curated stock universe, wide (dates x tickers). Mirrors
    `runner_exclusion_audit.load_universe`: the midcap index is the longest, so it is the
    ruler; breadth names simply carry NaN before their cache starts."""
    frames = []
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        frames.append(pd.read_parquet(f"data/{grp}/_closes_cache.parquet"))
    idx = frames[1].index
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()]

    # PRICE-ADJUSTMENT AUDIT (2026-08-06): this packet's 126-session window sits inside
    # the exposed tail, where the caches carry raw closes and the yahoo SPY benchmark is
    # back-adjusted. PRICE_BASIS=adjusted re-prices the SAME names, on the SAME calendar,
    # in the SAME observed cells so a delta is attributable to the basis alone.
    PANEL_PROVENANCE.clear()
    PANEL_PROVENANCE["basis"] = PRICE_BASIS
    if PRICE_BASIS == "adjusted":
        adj, prov = price_ladder.close_panel(
            list(wide.columns), asof=str(idx.max().date()), start=str(idx.min().date()))
        adj = adj.reindex(index=wide.index, columns=wide.columns)
        prov["basis"] = "adjusted"
        prov["cells_observed"] = int(wide.notna().to_numpy().sum())
        prov.pop("price_source", None)
        wide = adj.where(wide.notna())
        PANEL_PROVENANCE.update(prov)
    return wide


def load_benchmark(idx: pd.DatetimeIndex) -> pd.Series:
    """SPY close on the panel's calendar. ffill only (a benchmark gap must never
    manufacture a return); returns an all-NaN series if the store is unreadable, which the
    caller reports as a null excess rather than silently scoring raw returns as excess."""
    p = Path("data/yahoo") / f"{BENCH}.parquet"
    if not p.exists():
        return pd.Series(np.nan, index=idx, dtype=float)
    df = pd.read_parquet(p)
    col = "close" if "close" in df.columns else df.columns[0]
    s = pd.Series(df[col].to_numpy(), index=pd.to_datetime(df.index), dtype=float)
    return s.reindex(idx, method="ffill")


# --------------------------------------------------------------------- the predicate
def reclaim_only_refusals(markers_on: list[dict], markers_off: list[dict]) -> list[str]:
    """Dates refused SOLELY by the reclaim leg, from the two marker streams of the SAME
    series (`reclaim_veto=True` and `=False`).

    A date qualifies iff the veto-ON stream blocked it with the counter-trend reclaim
    reason AND the veto-OFF stream took it on that same bar. See the module docstring for
    why those two conditions together exclude every other refusal cause.
    """
    off = {m.get("date"): m for m in markers_off}
    out = []
    for m in markers_on:
        if m.get("quality") != "block" or m.get("reason") != BLOCK_REASON:
            continue
        f = off.get(m.get("date"))
        if f is not None and f.get("quality") == TAKE_QUALITY:
            out.append(m["date"])
    return out


def confirmation_anchors(close: pd.Series) -> dict[pd.Timestamp, pd.Timestamp]:
    """3D marker label -> the DAILY date whose close first makes the refusal knowable.

    `_buy_filter` reads bars i+1 and i+2, so the verdict is knowable at the close of 3D bar
    i+2; that bar's information is complete only at the LAST daily close inside it. Both
    maps are rebuilt from the same `signal_frame`/resample the markers came from, so the
    labels align by construction.
    """
    sig = sq.signal_frame(close)
    if sig.empty:
        return {}
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    sidx = sig.index
    bin_last = pd.Series(close.index, index=close.index).resample("3B").last().dropna()
    out: dict[pd.Timestamp, pd.Timestamp] = {}
    for i in range(len(sidx) - 2):
        conf_label = sidx[i + 2]
        d = bin_last.get(conf_label)
        if d is not None and pd.notna(d):
            out[sidx[i]] = pd.Timestamp(d)
    return out


# ------------------------------------------------------------------ forward metrics
def forward_block(px: pd.Series, spy: pd.Series, pos: int) -> dict:
    """Raw/excess forward returns + MAE from an anchor POSITION on the panel calendar.
    An incomplete horizon (anchor too near the panel's end) is null, never zero."""
    n = len(px)
    p0, b0 = px.iloc[pos], spy.iloc[pos]
    out: dict = {}
    for h in HORIZONS:
        j = pos + h
        if j >= n or pd.isna(p0) or pd.isna(px.iloc[j]):
            out[f"ret_{h}"] = out[f"excess_{h}"] = None
            continue
        r = float(px.iloc[j] / p0 - 1.0) * 100.0
        out[f"ret_{h}"] = round(r, 3)
        if pd.isna(b0) or pd.isna(spy.iloc[j]):
            out[f"excess_{h}"] = None
        else:
            out[f"excess_{h}"] = round(r - (float(spy.iloc[j] / b0 - 1.0) * 100.0), 3)
    seg = px.iloc[pos + 1: pos + 1 + MAE_HORIZON].dropna()
    out["mae_21"] = (round(float(seg.min() / p0 - 1.0) * 100.0, 3)
                     if len(seg) and pd.notna(p0) else None)
    out["mae_21_complete"] = bool(len(seg) >= MAE_HORIZON)
    return out


def drawdown_from_252d_high(px: pd.Series, pos: int) -> float | None:
    """Drawdown (positive %) from the trailing 252-session high at the anchor."""
    hist = px.iloc[max(0, pos - 251): pos + 1].dropna()
    if len(hist) < 120 or pd.isna(px.iloc[pos]):
        return None
    hi = float(hist.max())
    return None if hi <= 0 else round((1.0 - float(px.iloc[pos]) / hi) * 100.0, 3)


def dd_band(dd: float | None) -> str:
    if dd is None:
        return "unknown"
    for lo, hi, name in DD_BANDS:
        if lo <= dd < hi:
            return name
    return ">35%"


# ------------------------------------------------------------------------- the scan
def scan(wide: pd.DataFrame, spy: pd.Series, win_start: pd.Timestamp) -> list[dict]:
    idx = wide.index
    rows: list[dict] = []
    for t in wide.columns:
        px = wide[t]
        c = px.dropna()
        if len(c) < MIN_BARS:
            continue
        try:
            on = sq.analyze(t, c, reclaim_veto=True)
            off = sq.analyze(t, c, reclaim_veto=False)
        except Exception:
            continue
        if not on or not off:
            continue
        dates = reclaim_only_refusals(on["markers"], off["markers"])
        if not dates:
            continue
        anchors = confirmation_anchors(c)
        for ds in dates:
            d = pd.Timestamp(ds)
            if d < win_start:
                continue
            anchor = anchors.get(d)
            if anchor is None:
                continue
            try:
                pos = idx.get_loc(anchor)
            except KeyError:
                continue
            dd = drawdown_from_252d_high(px, pos)
            row = {"ticker": t, "refusal_date": ds, "anchor_date": str(anchor.date()),
                   "dd_from_252d_high_pct": dd, "dd_band": dd_band(dd)}
            row.update(forward_block(px, spy, pos))
            rows.append(row)
    return rows


# ---------------------------------------------------------------------- aggregation
def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "median": None, "mean": None}
    a = np.array(vals, dtype=float)
    return {"n": int(a.size), "median": round(float(np.median(a)), 3),
            "mean": round(float(a.mean()), 3)}


def episode_clustering(rows: list[dict]) -> dict:
    """THE SAMPLE-SIZE DISCLOSURE — read this before any pooled number above.

    353 fires are NOT 353 independent observations. Markers live on a 3D grid, so refusal
    dates are 3-business-days apart at best, and a market-wide washout fires dozens of
    names on ONE date whose forward returns then share almost all of their variance. This
    block prints the concentration and the per-date view so the pooled median can never be
    read as an n=353 result: `median_of_per_date_medians` weights each date once, which is
    the conservative reading, and `per_date_median_excess_21` shows whether the pooled sign
    is a stable property or one episode's shadow.
    """
    dates = sorted({r["refusal_date"] for r in rows})
    per_date, counts = {}, {}
    for d in dates:
        sub = [r for r in rows if r["refusal_date"] == d]
        counts[d] = len(sub)
        vals = [r["excess_21"] for r in sub if r["excess_21"] is not None]
        per_date[d] = round(float(np.median(vals)), 3) if vals else None
    graded = [v for v in per_date.values() if v is not None]
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    months: dict[str, int] = {}
    for r in rows:
        months[r["refusal_date"][:7]] = months.get(r["refusal_date"][:7], 0) + 1
    return {
        "n_distinct_refusal_dates": len(dates),
        "n_fires": len(rows),
        "top5_dates": [{"date": d, "n_fires": n} for d, n in top],
        "top5_share_of_fires_pct": (round(100.0 * sum(n for _, n in top) / len(rows), 1)
                                    if rows else None),
        "fires_by_month": dict(sorted(months.items())),
        "per_date_median_excess_21": per_date,
        "n_dates_graded": len(graded),
        "median_of_per_date_medians": round(float(np.median(graded)), 3) if graded else None,
        "share_of_dates_negative_pct": (round(100.0 * float(np.mean(np.array(graded) < 0)), 1)
                                        if graded else None),
    }


def by_month(rows: list[dict]) -> dict:
    """Calendar decomposition of the outcome — the honest way to look for a regime effect.

    A month split is chosen BEFORE looking at outcomes (it is just the calendar), so it
    carries no selection. Any coarser cut a reader draws from it — "the drawdown leg vs the
    recovery leg" — is POST HOC by definition and must be labelled as such wherever it is
    quoted: the split point was chosen after seeing these rows. Note also that the later
    months are censored at the longer horizons (the panel ends), so `n` per horizon falls
    away and the months are NOT measured on the same ruler.
    """
    out: dict = {}
    for m in sorted({r["refusal_date"][:7] for r in rows}):
        sub = [r for r in rows if r["refusal_date"].startswith(m)]
        g = [r for r in sub if r["excess_21"] is not None]
        out[m] = {
            "n_fires": len(sub), "n_names": len({r["ticker"] for r in sub}),
            "excess_10": _stats([r["excess_10"] for r in sub if r["excess_10"] is not None]),
            "excess_21": _stats([r["excess_21"] for r in g]),
            "excess_63": _stats([r["excess_63"] for r in sub if r["excess_63"] is not None]),
            "mae_21": _stats([r["mae_21"] for r in sub if r["mae_21"] is not None]),
            "loser_rate_pct": (round(100.0 * sum(1 for r in g if r["excess_21"] < LOSER_PP)
                                     / len(g), 1) if g else None),
            "winner_rate_pct": (round(100.0 * sum(1 for r in g if r["excess_21"] > WINNER_PP)
                                      / len(g), 1) if g else None),
        }
    return out


def aggregate(rows: list[dict]) -> dict:
    """Both sides of the ledger, on one construction. `cost` = what the veto refused that
    then ran; `saved` = what it refused that then fell (and the drawdown it kept off the
    book). Neither is a recommendation — they are the two columns an era-stamp decision
    needs beside the validated -23.7%->-15.5% drawdown benefit."""
    out: dict = {"n_fires": len(rows), "n_names": len(({r["ticker"] for r in rows}))}
    for h in HORIZONS:
        out[f"excess_{h}"] = _stats([r[f"excess_{h}"] for r in rows if r[f"excess_{h}"] is not None])
        out[f"ret_{h}"] = _stats([r[f"ret_{h}"] for r in rows if r[f"ret_{h}"] is not None])

    graded = [r for r in rows if r["excess_21"] is not None]
    losers = [r for r in graded if r["excess_21"] < LOSER_PP]
    winners = [r for r in graded if r["excess_21"] > WINNER_PP]
    mae = [r["mae_21"] for r in rows if r["mae_21"] is not None]
    out["both_sides"] = {
        "graded_at_21": len(graded),
        "cost_side": {
            "n_winners_gt_+3pp": len(winners),
            "share_pct": round(100.0 * len(winners) / len(graded), 1) if graded else None,
            "excess_21": _stats([r["excess_21"] for r in winners]),
            "best": sorted(({"ticker": r["ticker"], "refusal_date": r["refusal_date"],
                             "excess_21": r["excess_21"], "ret_21": r["ret_21"]}
                            for r in winners),
                           key=lambda r: -r["excess_21"])[:12],
        },
        "saved_side": {
            "n_losers_lt_-3pp": len(losers),
            "loser_rate_pct": round(100.0 * len(losers) / len(graded), 1) if graded else None,
            "excess_21": _stats([r["excess_21"] for r in losers]),
            "mae_21": _stats(mae),
            "share_mae_worse_than_-10pct": (
                round(100.0 * sum(1 for m in mae if m <= -10.0) / len(mae), 1) if mae else None),
            "share_mae_worse_than_-20pct": (
                round(100.0 * sum(1 for m in mae if m <= -20.0) / len(mae), 1) if mae else None),
            "worst": sorted(({"ticker": r["ticker"], "refusal_date": r["refusal_date"],
                              "excess_21": r["excess_21"], "mae_21": r["mae_21"]}
                             for r in losers),
                            key=lambda r: r["excess_21"])[:12],
        },
    }

    out["episode_clustering"] = episode_clustering(rows)
    out["by_month"] = by_month(rows)

    strat: dict = {}
    for _, _, name in DD_BANDS:
        sub = [r for r in rows if r["dd_band"] == name]
        g = [r for r in sub if r["excess_21"] is not None]
        strat[name] = {
            "n_fires": len(sub), "n_names": len({r["ticker"] for r in sub}),
            "excess_10": _stats([r["excess_10"] for r in sub if r["excess_10"] is not None]),
            "excess_21": _stats([r["excess_21"] for r in g]),
            "excess_63": _stats([r["excess_63"] for r in sub if r["excess_63"] is not None]),
            "mae_21": _stats([r["mae_21"] for r in sub if r["mae_21"] is not None]),
            "loser_rate_pct": (round(100.0 * sum(1 for r in g if r["excess_21"] < LOSER_PP)
                                     / len(g), 1) if g else None),
        }
    unknown = [r for r in rows if r["dd_band"] == "unknown"]
    if unknown:
        strat["unknown"] = {"n_fires": len(unknown),
                            "note": "fewer than 120 sessions of history at the anchor"}
    out["by_drawdown_band"] = strat
    return out


def main() -> int:
    t0 = time.time()
    wide = load_panel()
    idx = wide.index
    spy = load_benchmark(idx)
    win_start = idx[-WINDOW_SESSIONS]
    rows = scan(wide, spy, win_start)
    rows.sort(key=lambda r: (r["refusal_date"], r["ticker"]))
    payload = {
        "instrument": "W-F US reclaim-veto decision packet",
        "tier": "research — decision input; NO code-path change, reclaim_veto stays True",
        "generated": "2026-08-05",
        "price_basis": PRICE_BASIS,
        "price_ladder": dict(PANEL_PROVENANCE),
        "panel": {
            "source": ["data/breadth/_closes_cache.parquet",
                       "data/midcap_breadth/_closes_cache.parquet",
                       "data/smallcap_breadth/_closes_cache.parquet"],
            "tickers_in_panel": int(wide.shape[1]),
            "panel_first_bar": str(idx[0].date()), "panel_last_bar": str(idx[-1].date()),
            "window_sessions": WINDOW_SESSIONS,
            "window_first_refusal_date": str(win_start.date()),
            "benchmark": BENCH,
            "benchmark_readable": bool(spy.notna().any()),
            # The excess column's other half. The refused cohort is below-200 AND
            # weekly-down BY CONSTRUCTION, so against a benchmark that rose this much a
            # negative median excess is partly cohort definition, not veto skill. Raw
            # `ret_h` is printed beside every `excess_h` for exactly this reason.
            "benchmark_return_over_window_pct": (
                round(float(spy.loc[win_start:].iloc[-1] / spy.loc[win_start:].iloc[0] - 1.0)
                      * 100.0, 2) if spy.notna().any() else None),
        },
        "construction": {
            "isolation": "marker diff: analyze(reclaim_veto=True).quality=='block' with "
                         f"reason '{BLOCK_REASON}' AND analyze(reclaim_veto=False)"
                         ".quality=='take' on the same bar",
            "anchor": "last daily close inside 3D bar i+2 — the first close at which the "
                      "refusal is knowable (marker-date grading is forbidden; see "
                      "engine/signal_quality.py analyze/_buy_filter docstrings)",
            "horizons_are": "daily sessions on the panel calendar",
            "censoring": "a refusal within H sessions of the panel end has a null H-horizon "
                         "and is excluded from that horizon's aggregate",
            "validated_benefit_this_sits_beside":
                "buy-filter cut average max drawdown -23.7% -> -15.5% across 110 held-out "
                "US names (84% improved) — engine/signal_quality.py:7",
        },
        "aggregate": aggregate(rows),
        "fires": rows,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    a = payload["aggregate"]
    print(f"[reclaim_veto_packet] {a['n_fires']} fires / {a['n_names']} names "
          f"in {time.time() - t0:.0f}s -> {OUT}")
    print(f"  excess@21 median {a['excess_21']['median']} (n={a['excess_21']['n']}); "
          f"winners>{WINNER_PP}pp {a['both_sides']['cost_side']['n_winners_gt_+3pp']} / "
          f"losers<{LOSER_PP}pp {a['both_sides']['saved_side']['n_losers_lt_-3pp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
