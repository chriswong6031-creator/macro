#!/usr/bin/env python3
"""Git-archaeology retro-grader + forward-accruing ledger for the US Buy Board.

WHAT THIS IS
------------
`site/factordata/us_standouts.json` is committed daily (~90 revisions back to
2026-06-16). This script reconstructs every past board from git history, grades
every row (buy / watch / laggard lanes) at matured horizons (5d, 10d, 21d) versus
SPY and versus the name's sector ETF, and writes:

  * data/us_board_ledger/retro_grades.parquet  — one row per (as_of, lane, ticker, horizon)
  * site/factordata/us_board_track.json         — aggregated hit-rate / precision@k / Wilson-CI

It ALSO runs nightly (`--nightly`): it snapshots today's committed board into an
append-only JSONL (data/us_board_ledger/snapshots.jsonl) so the ledger keeps
accruing without depending on git blob availability, and re-grades everything that
has matured. The retro (git) and forward (snapshot) sources are unioned and
de-duplicated on (as_of, ticker, lane) — retro seeds the ledger today, snapshots
carry it forward.

HONESTY CONVENTIONS (read these — they bound every claim downstream)
--------------------------------------------------------------------
* Entry fill = the NEXT session's close after the board's as_of. Boards publish in
  the evening on the as_of date, so the earliest realistic fill is the following
  session's close (next-bar realism). Horizon h return = close[entry+h] / close[entry] - 1.
* Prices come from engine.equity_factors._closes("broad") (survivor-biased S&P-1500
  breadth caches, ~2023-05 -> latest) PLUS data/yahoo/{SPY,XL*}.parquet for the
  benchmarks. All are DIVIDEND-ADJUSTED total-return closes (see MEMORY:
  yahoo-close-is-total-return). Excess return subtracts benchmark total return, so
  both legs share the same basis — the comparison is clean; absolute levels are TR.
* Excess return = name_ret - benchmark_ret (SPY and, separately, sector ETF).
* MAE = maximum ADVERSE excursion. We only have daily CLOSES, not intraday lows, so
  this is a CLOSE-PATH MAE: min(close[entry..entry+h]) / close[entry] - 1, in EXCESS
  terms vs SPY. It UNDER-states true intraday drawdown; labelled `mae_close_excess`.
* n is reported everywhere. ~11 trading days of matured 5d data at first run is TINY.
  Daily boards + multi-day horizons overlap heavily -> serial correlation -> the
  effective independent-sample count is a fraction of n. Wilson CIs are computed on
  the RAW n and are therefore OPTIMISTICALLY narrow; treat them as lower bounds on
  uncertainty. No strong claims. See the "caveats" block in the JSON.

Survivorship: the broad cache is current-membership only. Delisted names are
invisible, which inflates hit-rates for any reversal/laggard lane. Flagged in output.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.equity_factors import _closes  # noqa: E402

BOARD_PATH = "site/factordata/us_standouts.json"
LEDGER_DIR = ROOT / "data" / "us_board_ledger"
RETRO_PARQUET = LEDGER_DIR / "retro_grades.parquet"
SNAPSHOTS_JSONL = LEDGER_DIR / "snapshots.jsonl"
TRACK_JSON = ROOT / "site" / "factordata" / "us_board_track.json"

HORIZONS = [5, 10, 21]
LANES = ["buy", "watch", "laggards", "laggard"]
K_LIST = [1, 3, 5, 10]

# GICS sector -> SPDR sector ETF (mirrors engine/ai_desk.py _GICS_ETF, plus the
# board's occasional non-canonical sector spellings).
_GICS_ETF = {
    "Energy": "XLE", "Information Technology": "XLK", "Technology": "XLK",
    "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE",
    "Communication Services": "XLC", "Communications": "XLC",
}
BENCH = "SPY"


# --------------------------------------------------------------------------- #
# price loading
# --------------------------------------------------------------------------- #
def _load_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (names_closes, etf_closes). Both dividend-adjusted TR closes."""
    names = _closes("broad")
    names.index = pd.to_datetime(names.index)
    names = names.sort_index()

    etf_tickers = sorted(set(_GICS_ETF.values()) | {BENCH})
    cols = {}
    ypath = ROOT / "data" / "yahoo"
    for t in etf_tickers:
        p = ypath / f"{t}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            s = df["close"] if "close" in df.columns else df.iloc[:, 0]
            s.index = pd.to_datetime(s.index)
            cols[t] = s
    etfs = pd.DataFrame(cols).sort_index()
    return names, etfs


# --------------------------------------------------------------------------- #
# board reconstruction (git archaeology + snapshot union)
# --------------------------------------------------------------------------- #
def _git_revisions() -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", "--format=%H", "--", BOARD_PATH],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    return out


def _load_blob(sha: str) -> dict | None:
    blob = subprocess.run(
        ["git", "show", f"{sha}:{BOARD_PATH}"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    if not blob.strip():
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _dig(d: dict, *paths, default=None):
    """Tolerant nested getter: returns first path that resolves non-None.
    Each path is a tuple of keys; walks dicts, skips on any miss (schema drift)."""
    for path in paths:
        cur = d
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur and cur[k] is not None:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _row_features(r: dict) -> dict:
    """Extract grading-relevant fields, tolerant to schema drift across revisions.

    Fields moved over time: score/band/composite_z/verdict/validation_status started
    at row top-level in the very first schema (never — they were always under
    `conviction`), and later `vol_squeeze`/`act_level` nested under
    conviction.*/entry_signal.*. `signal` (with .last.quality) only appears in the
    latest schema. `align_tier` is None in the earliest revision. Every getter below
    tries the modern nested path first, then a flat fallback."""
    conv = r.get("conviction") or {}
    sig = r.get("signal") or {}
    es = r.get("entry_signal") or {}
    return {
        "ticker": r.get("ticker"),
        "sector": r.get("sector"),
        "alpha": _num(r.get("alpha")),
        "state": r.get("state"),
        "label": r.get("label"),
        "urgency": r.get("urgency"),
        "align_tier": r.get("align_tier"),
        "score": _num(_dig(r, ("conviction", "score"), ("score",))),
        "band": _dig(r, ("conviction", "band"), ("band",)),
        "composite_z": _num(_dig(r, ("conviction", "composite_z"), ("composite_z",))),
        "verdict": _dig(r, ("conviction", "verdict"), ("verdict",)),
        "validation_status": _dig(r, ("conviction", "validation_status"), ("validation_status",)),
        "trust_tier": _dig(r, ("conviction", "trust_tier", "tier"), ("trust_tier", "tier")),
        # entry_signal.status = the confluence-gated "buyable now" flag
        "entry_status": _dig(r, ("entry_signal", "status"), default=es.get("status")),
        "act_level": _num(_dig(r, ("entry_signal", "act_level"),
                               ("conviction", "act_level"), default=es.get("act_level"))),
        # signal.last.quality = block/ok — the master-veto state (latest schema only)
        "signal_quality": _dig(r, ("signal", "last", "quality"), default=None),
        "signal_last_type": _dig(r, ("signal", "last", "type"), default=None),
        "tier_cascade": _dig(r, ("signal", "tier_cascade"), default=sig.get("tier_cascade")),
        # vol_squeeze nested under conviction.* in later schemas
        "vol_squeeze": _dig(r, ("conviction", "vol_squeeze", "state"),
                            ("vol_squeeze", "state"), ("vol_squeeze",)),
        # spotlight sector ETF (later schemas carry it directly)
        "spot_sector_etf": _dig(r, ("conviction", "spotlight", "sector", "etf")),
        "off_high": _num(r.get("off_high")),
        "dispersion_state": None,  # filled from board-level below
        # COILED wave-2 ranking bonus fields (forward-ledger; None when absent/pre-schema)
        "coiled":        bool((r.get("coiled") or {}).get("coiled")),
        "coiled_star":   bool((r.get("coiled") or {}).get("star")),
        "coiled_cohort": (r.get("coiled") or {}).get("cohort"),
        # COILED-FIRE wave-4 display chip fields (forward-ledger; False/None pre-schema)
        "coiled_fire":       bool((r.get("coiled") or {}).get("fire")),
        "coiled_fire_ticks": (r.get("coiled") or {}).get("fire_ticks"),
        # G6a donor-sector per-row (constant per as_of — from board-level donor object below)
        # filled in _board_to_record after _row_features; None pre-schema
        "donor_state":  None,
        "donor_sector": None,
    }


def _num(x):
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def collect_boards() -> list[dict]:
    """Union git-history boards with snapshot JSONL, de-dup on (as_of).

    Each element: {as_of: 'YYYY-MM-DD', dispersion_state, rank_by, rows: [ {lane, position, **features} ]}.
    Position = 0-based order within lane as published (this IS the ranking under test)."""
    boards: dict[str, dict] = {}

    # 1) snapshots (forward-accruing source) — take precedence (exact bytes at build time)
    if SNAPSHOTS_JSONL.exists():
        for line in SNAPSHOTS_JSONL.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                snap = json.loads(line)
            except json.JSONDecodeError:
                continue
            b = _board_to_record(snap)
            if b:
                boards[b["as_of"]] = b

    # 2) git history (retro source) — fills any as_of not already present
    for sha in _git_revisions():
        d = _load_blob(sha)
        if not d:
            continue
        b = _board_to_record(d)
        if b and b["as_of"] not in boards:
            boards[b["as_of"]] = b

    return sorted(boards.values(), key=lambda x: x["as_of"])


def _board_to_record(d: dict) -> dict | None:
    as_of = d.get("as_of")
    if not as_of:
        return None
    disp = _dig(d, ("dispersion_regime", "state"), default=None)
    rank_by = d.get("rank_by")
    # G6a donor-sector: page-level object, constant for all rows in this snapshot
    _donor = d.get("donor") or {}
    _donor_state_val  = _donor.get("state") if isinstance(_donor, dict) else None
    _donor_sector_val = _donor.get("donor_sector") if isinstance(_donor, dict) else None
    rows = []
    for lane in LANES:
        lst = d.get(lane) or []
        canon_lane = "laggards" if lane == "laggard" else lane
        for pos, r in enumerate(lst):
            if not isinstance(r, dict):
                continue
            feat = _row_features(r)
            if not feat["ticker"]:
                continue
            feat["lane"] = canon_lane
            feat["position"] = pos
            feat["dispersion_state"] = disp
            # propagate page-level donor into each row for the grader
            feat["donor_state"]  = _donor_state_val
            feat["donor_sector"] = _donor_sector_val
            rows.append(feat)
    if not rows:
        return None
    return {"as_of": as_of, "dispersion_state": disp, "rank_by": rank_by, "rows": rows}


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #
def _pos_after(index: pd.DatetimeIndex, date: pd.Timestamp) -> int | None:
    """Index position of the first trading day STRICTLY AFTER `date` (next-bar entry)."""
    loc = index.searchsorted(date, side="right")
    if loc >= len(index):
        return None
    return int(loc)


def _fwd_ret(series: pd.Series, entry_pos: int, h: int) -> float | None:
    """Total return from close at entry_pos to close at entry_pos+h."""
    if entry_pos + h >= len(series):
        return None
    p0 = series.iloc[entry_pos]
    p1 = series.iloc[entry_pos + h]
    if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
        return None
    return float(p1 / p0 - 1.0)


def _close_path_mae(name_ser, bench_ser, entry_pos, h) -> float | None:
    """Close-path MAE in EXCESS terms (min excess cumulative return over the window)."""
    if entry_pos + h >= len(name_ser):
        return None
    np0 = name_ser.iloc[entry_pos]
    bp0 = bench_ser.iloc[entry_pos]
    if pd.isna(np0) or pd.isna(bp0) or np0 <= 0 or bp0 <= 0:
        return None
    worst = 0.0
    for j in range(1, h + 1):
        npj = name_ser.iloc[entry_pos + j]
        bpj = bench_ser.iloc[entry_pos + j]
        if pd.isna(npj) or pd.isna(bpj):
            continue
        exc = (npj / np0 - 1.0) - (bpj / bp0 - 1.0)
        worst = min(worst, exc)
    return float(worst)


def grade_boards(boards: list[dict], names: pd.DataFrame, etfs: pd.DataFrame) -> pd.DataFrame:
    spy = etfs[BENCH].dropna() if BENCH in etfs.columns else None
    last_price_date = names.index.max()
    recs = []
    skipped_no_price = 0
    for b in boards:
        as_of = pd.Timestamp(b["as_of"])
        rank_by = b.get("rank_by")
        for feat in b["rows"]:
            tk = feat["ticker"]
            if tk not in names.columns:
                skipped_no_price += 1
                continue
            nser = names[tk].dropna()
            if nser.empty:
                skipped_no_price += 1
                continue
            entry_pos = _pos_after(nser.index, as_of)
            if entry_pos is None:
                continue
            entry_date = nser.index[entry_pos]
            # benchmark series aligned to name's trading calendar
            # sector ETF
            etf_t = feat.get("spot_sector_etf") or _GICS_ETF.get(feat.get("sector") or "")
            for h in HORIZONS:
                # need matured horizon: entry + h must be <= last available price date
                if entry_pos + h >= len(nser):
                    continue
                # confirm the horizon bar actually exists in the data window (matured)
                horizon_date = nser.index[entry_pos + h]
                if horizon_date > last_price_date:
                    continue
                nret = _fwd_ret(nser, entry_pos, h)
                if nret is None:
                    continue
                rec = {
                    "as_of": b["as_of"], "entry_date": entry_date.date().isoformat(),
                    "rank_by": rank_by,
                    "horizon": h, "lane": feat["lane"], "position": feat["position"],
                    "ticker": tk, "sector": feat.get("sector"),
                    "alpha": feat.get("alpha"), "score": feat.get("score"),
                    "band": feat.get("band"), "composite_z": feat.get("composite_z"),
                    "verdict": feat.get("verdict"), "align_tier": feat.get("align_tier"),
                    "urgency": feat.get("urgency"), "state": feat.get("state"),
                    "entry_status": feat.get("entry_status"),
                    "act_level": feat.get("act_level"),
                    "signal_quality": feat.get("signal_quality"),
                    "validation_status": feat.get("validation_status"),
                    "vol_squeeze": feat.get("vol_squeeze"),
                    "dispersion_state": feat.get("dispersion_state"),
                    "off_high": feat.get("off_high"),
                    "ret": nret,
                }
                # excess vs SPY
                if spy is not None:
                    spy_al = spy.reindex(nser.index).ffill()
                    sret = _fwd_ret(spy_al, entry_pos, h)
                    rec["spy_ret"] = sret
                    rec["excess_spy"] = (nret - sret) if sret is not None else None
                    rec["mae_close_excess_spy"] = _close_path_mae(nser, spy_al, entry_pos, h)
                else:
                    rec["spy_ret"] = rec["excess_spy"] = rec["mae_close_excess_spy"] = None
                # excess vs sector ETF
                if etf_t and etf_t in etfs.columns:
                    etf_al = etfs[etf_t].reindex(nser.index).ffill()
                    eret = _fwd_ret(etf_al, entry_pos, h)
                    rec["sector_etf"] = etf_t
                    rec["etf_ret"] = eret
                    rec["excess_sector"] = (nret - eret) if eret is not None else None
                    rec["mae_close_excess_sector"] = _close_path_mae(nser, etf_al, entry_pos, h)
                else:
                    rec["sector_etf"] = etf_t
                    rec["etf_ret"] = rec["excess_sector"] = rec["mae_close_excess_sector"] = None
                recs.append(rec)
    df = pd.DataFrame(recs)
    df.attrs["skipped_no_price"] = skipped_no_price
    return df


# --------------------------------------------------------------------------- #
# aggregation / stats
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _hit_stats(sub: pd.DataFrame, col: str = "excess_spy") -> dict:
    vals = sub[col].dropna()
    n = len(vals)
    if n == 0:
        return {"n": 0}
    k = int((vals > 0).sum())
    lo, hi = wilson_ci(k, n)
    return {
        "n": n, "hit_rate": round(k / n, 4),
        "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
        "median_excess": round(float(vals.median()), 5),
        "mean_excess": round(float(vals.mean()), 5),
    }


def _precision_at_k(sub: pd.DataFrame, col: str = "excess_spy",
                    rank_col: str = "position", ascending: bool = True) -> dict:
    """P(excess>0) among the top-k by `rank_col` (published board position by default;
    position ascending = higher rank). Set rank_col='alpha', ascending=False to score the
    counterfactual alpha-ordered board. Averaged across boards so each day contributes
    equally (mitigates n-heavy days)."""
    out = {}
    for k in K_LIST:
        per_board_hit = []
        per_board_mean = []
        for as_of, g in sub.groupby("as_of"):
            g = g.sort_values(rank_col, ascending=ascending)
            topk = g.head(k)[col].dropna()
            if len(topk) == 0:
                continue
            per_board_hit.append(float((topk > 0).mean()))
            per_board_mean.append(float(topk.mean()))
        if per_board_hit:
            # pooled across (board, name) too, for the Wilson CI
            pooled = pd.concat([
                sub[sub["as_of"] == a].sort_values(rank_col, ascending=ascending).head(k)[col].dropna()
                for a in sub["as_of"].unique()
            ])
            kk = int((pooled > 0).sum())
            nn = len(pooled)
            lo, hi = wilson_ci(kk, nn)
            out[f"k{k}"] = {
                "n_boards": len(per_board_hit), "n_rows": nn,
                "precision": round(float(np.mean(per_board_hit)), 4),
                "pooled_precision": round(kk / nn, 4) if nn else None,
                "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "mean_excess_topk": round(float(np.mean(per_board_mean)), 5),
            }
        else:
            out[f"k{k}"] = {"n_boards": 0, "n_rows": 0}
    return out


def _slice_table(df: pd.DataFrame, by: str, col: str = "excess_spy") -> dict:
    out = {}
    for val, g in df.groupby(by, dropna=False):
        key = "None" if (val is None or (isinstance(val, float) and math.isnan(val))) else str(val)
        out[key] = _hit_stats(g, col)
    return out


def build_track(df: pd.DataFrame, boards: list[dict], names: pd.DataFrame) -> dict:
    if df.empty:
        return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "empty": True,
                "note": "no matured graded rows"}
    board_dates = sorted({b["as_of"] for b in boards})
    graded_dates = sorted(df["as_of"].unique().tolist())
    per_horizon = {}
    for h in HORIZONS:
        hh = df[df["horizon"] == h]
        if hh.empty:
            per_horizon[f"h{h}"] = {"n": 0}
            continue
        buy = hh[hh["lane"] == "buy"]
        block = {
            "overall_vs_spy": _hit_stats(hh, "excess_spy"),
            "overall_vs_sector": _hit_stats(hh, "excess_sector"),
            "by_lane_vs_spy": _slice_table(hh, "lane", "excess_spy"),
            "buy_lane": {
                "vs_spy": _hit_stats(buy, "excess_spy"),
                "vs_sector": _hit_stats(buy, "excess_sector"),
                "rank_by_of_matured_boards": sorted(buy["rank_by"].dropna().unique().tolist())
                if "rank_by" in buy.columns else [],
                # precision@k under the AS-PUBLISHED board order (the ranking under test)
                "precision_at_k_board_order_vs_spy": _precision_at_k(buy, "excess_spy", "position", True),
                "precision_at_k_vs_sector": _precision_at_k(buy, "excess_sector", "position", True),
                # counterfactuals: if the same names were re-ordered by alpha / composite_z
                "precision_at_k_alpha_order_vs_spy": _precision_at_k(buy, "excess_spy", "alpha", False),
                "precision_at_k_compz_order_vs_spy": _precision_at_k(buy, "excess_spy", "composite_z", False),
                "corr_position_excess": round(float(
                    buy[["position", "excess_spy"]].dropna()["position"].corr(
                        buy[["position", "excess_spy"]].dropna()["excess_spy"])), 4)
                if buy["excess_spy"].notna().sum() > 2 else None,
                "corr_alpha_excess": round(float(
                    buy[["alpha", "excess_spy"]].dropna()["alpha"].corr(
                        buy[["alpha", "excess_spy"]].dropna()["excess_spy"])), 4)
                if buy[["excess_spy", "alpha"]].dropna().shape[0] > 2 else None,
                "by_band": _slice_table(buy, "band", "excess_spy"),
                "by_verdict": _slice_table(buy, "verdict", "excess_spy"),
                "by_align_tier": _slice_table(buy, "align_tier", "excess_spy"),
                "by_entry_status": _slice_table(buy, "entry_status", "excess_spy"),
                "by_signal_quality": _slice_table(buy, "signal_quality", "excess_spy"),
                "by_urgency": _slice_table(buy, "urgency", "excess_spy"),
                "by_sector": _slice_table(buy, "sector", "excess_spy"),
                "by_dispersion": _slice_table(buy, "dispersion_state", "excess_spy"),
                "mae_close_excess_spy": {
                    "median": round(float(buy["mae_close_excess_spy"].dropna().median()), 5)
                    if buy["mae_close_excess_spy"].notna().any() else None,
                    "n": int(buy["mae_close_excess_spy"].notna().sum()),
                },
            },
        }
        # P(fwd>0 | top-5) vs base rate for the buy lane
        base = buy["excess_spy"].dropna()
        top5_frames = [buy[buy["as_of"] == a].sort_values("position").head(5)["excess_spy"].dropna()
                       for a in buy["as_of"].unique()]
        top5 = pd.concat(top5_frames) if top5_frames else pd.Series(dtype=float)
        block["buy_lane"]["p_fwd_pos_top5_vs_base"] = {
            "top5_p": round(float((top5 > 0).mean()), 4) if len(top5) else None,
            "top5_n": int(len(top5)),
            "base_p": round(float((base > 0).mean()), 4) if len(base) else None,
            "base_n": int(len(base)),
            "lift": round(float((top5 > 0).mean() - (base > 0).mean()), 4)
            if len(top5) and len(base) else None,
        }
        per_horizon[f"h{h}"] = block

    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "git-archaeology + forward snapshots (unioned, de-duped on as_of)",
        "board_dates_total": len(board_dates),
        "board_dates_range": [board_dates[0], board_dates[-1]] if board_dates else None,
        "graded_dates": graded_dates,
        "graded_rows_total": int(len(df)),
        "price_source": "engine.equity_factors._closes('broad') (S&P-1500 breadth caches) + data/yahoo/{SPY,XL*}",
        "price_coverage_note": (
            f"{df['ticker'].nunique()} distinct tickers graded; rows with no price in the "
            "broad cache are dropped (survivor-biased current-membership universe)."),
        "conventions": {
            "entry": "next session's close after as_of (next-bar realism)",
            "returns": "total-return (dividend-adjusted) closes; excess = name_ret - benchmark_ret",
            "mae": "CLOSE-PATH MAE (min excess cum-return over window); UNDER-states intraday DD",
            "benchmarks": "SPY and per-name GICS sector SPDR ETF",
        },
        "caveats": [
            "TINY n: multi-day horizons only recently matured; first runs have ~11 trading "
            "days of 5d data. Read n on every cell; no strong claims.",
            "OVERLAPPING WINDOWS: daily boards x multi-day horizons -> heavy serial "
            "correlation. Effective independent-sample count << n. Wilson CIs on raw n are "
            "OPTIMISTICALLY NARROW (lower bound on true uncertainty).",
            "SURVIVORSHIP: broad cache is current membership; delisted names invisible -> "
            "inflates hit-rates, especially for reversal/laggard lanes.",
            "SCHEMA DRIFT: earliest boards (2026-06-16..) had 120-row buy lanes, no watch "
            "lane, no entry_signal/signal fields; those slices show 'None'. align_tier and "
            "signal.last.quality only populate on later revisions.",
        ],
        "per_horizon": per_horizon,
    }


# --------------------------------------------------------------------------- #
# nightly snapshot
# --------------------------------------------------------------------------- #
def snapshot_today() -> str | None:
    """Append today's committed board (site/factordata/us_standouts.json working tree)
    to the append-only snapshot JSONL. Idempotent per as_of."""
    p = ROOT / BOARD_PATH
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    as_of = d.get("as_of")
    if not as_of:
        return None
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    existing = set()
    if SNAPSHOTS_JSONL.exists():
        for line in SNAPSHOTS_JSONL.read_text().splitlines():
            try:
                existing.add(json.loads(line).get("as_of"))
            except json.JSONDecodeError:
                pass
    if as_of in existing:
        return as_of  # already snapshotted
    # store a trimmed record (lanes + the fields the grader reads) to keep the file lean
    trimmed = {"as_of": as_of, "rank_by": d.get("rank_by"),
               "dispersion_regime": {"state": _dig(d, ("dispersion_regime", "state"))}}
    # G6a donor-sector: persist the page-level donor object into the snapshot so
    # forward grades can stratify by rotation state (constant per as_of).
    if d.get("donor"):
        trimmed["donor"] = d["donor"]
    for lane in LANES:
        if lane in d:
            trimmed[lane] = d[lane]
    with SNAPSHOTS_JSONL.open("a") as f:
        f.write(json.dumps(trimmed, separators=(",", ":")) + "\n")
    return as_of


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="snapshot today's board then re-grade everything matured (cron entry point)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.nightly:
        snap = snapshot_today()
        if not args.quiet:
            print(f"[snapshot] as_of={snap} appended to {SNAPSHOTS_JSONL.name}")

    names, etfs = _load_prices()
    boards = collect_boards()
    if not args.quiet:
        print(f"[boards] {len(boards)} distinct as_of dates "
              f"({boards[0]['as_of']}..{boards[-1]['as_of']})" if boards else "[boards] none")

    df = grade_boards(boards, names, etfs)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(RETRO_PARQUET, index=False)
    if not args.quiet:
        print(f"[grade] {len(df)} matured rows -> {RETRO_PARQUET.name} "
              f"(skipped {df.attrs.get('skipped_no_price', 0)} no-price rows)")

    track = build_track(df, boards, names)
    TRACK_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRACK_JSON.write_text(json.dumps(track, indent=1, default=str))
    if not args.quiet:
        print(f"[track] wrote {TRACK_JSON.relative_to(ROOT)}")
        # headline
        for h in HORIZONS:
            blk = track.get("per_horizon", {}).get(f"h{h}", {})
            bl = blk.get("buy_lane", {})
            vs = bl.get("vs_spy", {})
            if vs.get("n"):
                pk = bl.get("precision_at_k_board_order_vs_spy", {}).get("k5", {})
                pa = bl.get("precision_at_k_alpha_order_vs_spy", {}).get("k5", {})
                print(f"  h{h}d buy-lane: n={vs['n']} hit={vs['hit_rate']} "
                      f"CI[{vs['wilson_lo']},{vs['wilson_hi']}] med_exc={vs['median_excess']} "
                      f"| P@5 board={pk.get('pooled_precision')} alpha={pa.get('pooled_precision')} "
                      f"| corr(pos,exc)={bl.get('corr_position_excess')} "
                      f"rank_by={bl.get('rank_by_of_matured_boards')}")


if __name__ == "__main__":
    main()
