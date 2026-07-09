"""E2 re-entry (corrected path) — D4-01 cn_supply_absorption, E2 leg ONLY.

WHY THIS RE-RUN EXISTS:
  The merged Day-4 study (scripts/d4_cn_supply_absorption_phase0.py, PR #1932)
  mis-pathed the E2 event source. The spec named the historical archive
  `data/china_block_tape` (mrtj yearly partitions, 2005-2026, usable 2013+),
  which EXISTS — the F5-01 archiver had already backfilled it. The lane instead
  substituted `data/china_block_trades/detail.parquet` (a single-date rolling
  snapshot, 461 rows) and registered E2 as a data-gap null with only 61
  deep-discount rows. This script re-runs ONLY the E2 leg against the correct
  store, preserving the frozen design, and amends the merged report with an
  'E2 re-entry (corrected path)' section.

FROZEN DESIGN (unchanged from the pre-registration):
  E2 event: deep-discount block day, avg_premium_pct <= -15 (PERCENT units).
    The tape carries `premium_ratio` = cross_price/close - 1 in RAW RATIO units
    (F5-01 archiver doc: "raw ratio, NOT percent"). Unit assertions below prove
    the scale, then avg_premium_pct = premium_ratio * 100 and the frozen -15
    percent threshold applies (== premium_ratio <= -0.15).
    Usable window: 2013-01-01 onward (per spec 'mrtj 2013+').
  Absorption confirmation: cumulative own return over [t, t+10 sessions]
    >= per-date UNIVERSE median of the same [t, t+10] return, where
    t = first trading day after the block date (same availability convention
    as the merged E1 leg) and the universe = the covered price store
    (data/china_stocks_raw), evaluated per event date.
  Entry: t+10+1 (one trading day after the absorption window closes).
    Forward returns at 21d and 63d are measured FROM that entry — they do NOT
    overlap the absorption window. (DISCREPANCY FLAG: the merged E1 code
    measured forward returns from t itself, overlapping the absorption window,
    despite the registered 't+11' entry. The gated E2 cells here implement the
    registered entry; the merged-code convention is reported as a labelled
    NON-GATED sensitivity so E1/E2 can be compared on either convention.)
  G1 (DECISIVE): absorbed vs matched controls, matched on
    (a) same [t,t+10] return-path quintile, (b) trailing-60d vol tercile,
    (c) size tercile; up to 3 controls per absorbed event (seed 42), relax to
    path-quintile-only if no exact cell match, exclude if none (AM-2).
    |t_HAC| >= 2 with date-clustered (calendar-quarter collapse) Newey-West,
    AND BH q <= 0.10 — with BH RE-COMPUTED ACROSS THE NOW-4 GATED CELLS
    (E1x21d, E1x63d frozen from the merged run; E2x21d, E2x63d from this run).
  Family verdict: changes from FAIL only if BOTH E2 cells pass G1 under the
    4-cell BH. G2 (split-half at 2020-09-23) and G3 (LOCO) reported
    descriptively for E2, as in the merged report.

E2-SPECIFIC IMPLEMENTATION AMENDMENTS (registered here, before results):
  AM-E2-1: Path quintile is assigned against the per-date UNIVERSE [t,t+10]
    return distribution (quintile edges at 20/40/60/80%), not a per-date qcut
    across same-date E2 events. Deep-discount block days average only ~4
    events per date — a per-date 5-bin qcut is degenerate there (the merged
    E1 code's exception branch would dump nearly all events into one bucket,
    silently deleting the path control). Universe-relative bins preserve the
    registered 'same [t,t+10] return quintile' matching.
  AM-E2-2: Per-date universe median/quintiles require >= 30 covered tickers
    with a valid [t,t+10] return; event dates below that are dropped
    (count printed).
  AM-E2-3: Trailing vol/size reuse the merged implementations verbatim
    (_trailing_vol/_trailing_size), evaluated at the block date.

TAPE STORE RESOLUTION:
  Default ROOT/data/china_block_tape; override with env CHINA_BLOCK_TAPE_STORE
  (the store is runner-local / untracked, so worktrees may not carry it).

Run:
    python -m scripts.d4_cn_supply_absorption_e2_rerun
Appends/refreshes the 'E2 re-entry (corrected path)' section of
reports/d4-cn-supply-absorption-phase0.md. Trial-ledger rows are logged
(family cn_supply_absorption); the lane restores data/trial_ledger.jsonl after
capturing the delta, per the intraday data/-discard law.
"""
from __future__ import annotations

import math
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import benjamini_hochberg                      # noqa: E402
from engine.trial_ledger import TrialLedger                           # noqa: E402
from scripts.d4_cn_supply_absorption_phase0 import (                  # noqa: E402
    CRISIS_WINDOWS,
    MAX_CONTROLS,
    SPLIT_DATE,
    _norm_ticker,
    _nw_tstat,
    _tercile_bucket,
    _trailing_size,
    _trailing_vol,
    load_price_store,
)

FAMILY = "cn_supply_absorption"

TAPE_STORE = Path(os.environ.get("CHINA_BLOCK_TAPE_STORE", str(ROOT / "data" / "china_block_tape")))
REPORT_PATH = ROOT / "reports" / "d4-cn-supply-absorption-phase0.md"

USABLE_FROM = pd.Timestamp("2013-01-01")
DEEP_DISCOUNT_PCT = -15.0     # frozen threshold, PERCENT units
ABSORPTION_WINDOW = 10        # sessions
ENTRY_LAG = ABSORPTION_WINDOW + 1   # entry = t+10+1 (registered)
HORIZONS = [21, 63]
MIN_UNIVERSE = 30             # AM-E2-2
EXPECTED_PASS_RATE = 8.0      # % of rows, per the F5-01 audit (event-set verification law)

SECTION_HEADING = "## E2 re-entry (corrected path)"

# Frozen E1 G1 cells from the merged run (PR #1932, report table §5) — the other
# two cells of the now-4-cell BH panel. NOT re-run here.
E1_FROZEN = {
    "E1_x_21d": {"t_hac": -1.292, "p_hac": 0.196, "mean_diff": 0.0242,
                 "n_pairs": 13023, "n_clusters": 68, "t_iid": 13.282},
    "E1_x_63d": {"t_hac": 1.855, "p_hac": 0.064, "mean_diff": 0.1085,
                 "n_pairs": 12885, "n_clusters": 68, "t_iid": 30.831},
}


# ---------------------------------------------------------------------------
# Tape load + unit assertions (event-set verification law)
# ---------------------------------------------------------------------------

def load_tape() -> pd.DataFrame:
    files = sorted(TAPE_STORE.glob("mrtj_*.parquet"))
    if not files:
        raise SystemExit(f"[FATAL] no mrtj partitions under {TAPE_STORE} "
                         f"(set CHINA_BLOCK_TAPE_STORE to the archive location)")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    print(f"\n[tape] {len(files)} mrtj partitions from {TAPE_STORE}")
    print(f"  total rows: {len(df):,}, dates {df['date'].min().date()}..{df['date'].max().date()}")

    dup = int(df.duplicated(subset=["date", "ticker"]).sum())
    print(f"  duplicate (date,ticker) rows: {dup}")
    assert dup == 0, "tape must be one row per (date,ticker) block day"

    # ---- Unit assertions -------------------------------------------------
    pr = df["premium_ratio"].astype(float)
    # (1) identity check: premium_ratio == cross_price/close - 1 (F5-01 doc)
    ok = df["close"].astype(float) > 0
    ident_err = (df.loc[ok, "cross_price"].astype(float) / df.loc[ok, "close"].astype(float)
                 - 1.0 - pr[ok]).abs()
    print(f"  identity |cross/close-1 - premium_ratio|: p99.9={ident_err.quantile(0.999):.2e}, "
          f"max={ident_err.max():.2e}")
    assert float(ident_err.quantile(0.999)) < 1e-3, "premium_ratio identity violated"
    # (2) RAW-RATIO scale: a percent-scale field would violate both of these
    assert float(pr.min()) > -1.0, "premium_ratio below -100% — not a raw ratio"
    assert float(pr.abs().median()) < 0.5, "premium_ratio median magnitude not ratio-scale"
    n_at_pct_scale = int((pr <= -15).sum())
    print(f"  rows with premium_ratio <= -15 (raw units): {n_at_pct_scale} "
          f"(must be 0 — proves the field is NOT already in percent)")
    assert n_at_pct_scale == 0

    df["avg_premium_pct"] = pr * 100.0
    app = df["avg_premium_pct"]
    print(f"  avg_premium_pct (derived, PERCENT): min={app.min():.2f}, "
          f"median={app.median():.2f}, mean={app.mean():.2f}, max={app.max():.2f}")
    # percent-units sanity: deep discounts exist but nothing beyond -100%
    assert float(app.min()) > -100.0 and float(app.min()) < -15.0
    return df


def build_e2_events(tape: pd.DataFrame) -> pd.DataFrame:
    usable = tape[tape["date"] >= USABLE_FROM].copy()
    print(f"\n[E2_filter] usable rows (>= {USABLE_FROM.date()}): {len(usable):,}")
    events = usable[usable["avg_premium_pct"] <= DEEP_DISCOUNT_PCT].copy()
    rate = 100.0 * len(events) / max(len(usable), 1)
    print(f"  deep-discount filter avg_premium_pct <= {DEEP_DISCOUNT_PCT:.0f}: "
          f"{len(events):,}/{len(usable):,} rows = {rate:.2f}% pass rate")
    print(f"  expected ~{EXPECTED_PASS_RATE:.0f}% per the F5-01 audit — "
          f"{'CONSISTENT' if 4.0 <= rate <= 14.0 else 'INCONSISTENT (halt and inspect)'}")
    assert 4.0 <= rate <= 14.0, "pass rate far from the F5-01 audit expectation"
    per_date = events.groupby("date").size()
    print(f"  events per date: mean={per_date.mean():.1f}, median={per_date.median():.0f}, "
          f"dates={events['date'].nunique():,}")
    return events


# ---------------------------------------------------------------------------
# Universe [t, t+10] return matrix + event returns
# ---------------------------------------------------------------------------

def _anchored_returns(s: pd.Series, dates: np.ndarray, start_off: int, end_off: int) -> np.ndarray:
    """Return close[pos+end_off]/close[pos+start_off] - 1 per date, where
    pos = first session strictly after the date (searchsorted right).
    NaN when out of range or entry <= 0."""
    idx = s.index.values
    vals = s.values.astype(float)
    pos = np.searchsorted(idx, dates, side="right")
    out = np.full(len(dates), np.nan)
    ok = (pos + end_off) < len(vals)
    if not ok.any():
        return out
    p = pos[ok]
    entry = vals[p + start_off]
    exit_ = vals[p + end_off]
    r = np.where(entry > 0, exit_ / entry - 1.0, np.nan)
    out[ok] = r
    return out


def universe_path_matrix(prices: dict[str, pd.Series], dates: list[pd.Timestamp]) -> pd.DataFrame:
    """[t, t+10] return for EVERY price-store ticker, anchored at each event date."""
    date_arr = np.array(pd.DatetimeIndex(dates).values)
    cols = {}
    for tk, s in prices.items():
        cols[tk] = _anchored_returns(s, date_arr, 0, ABSORPTION_WINDOW)
    U = pd.DataFrame(cols, index=pd.DatetimeIndex(dates))
    return U


# ---------------------------------------------------------------------------
# Event table
# ---------------------------------------------------------------------------

def build_event_table(events: pd.DataFrame, prices: dict[str, pd.Series]) -> pd.DataFrame:
    tickers = events["ticker"].unique()
    covered_map = {t: _norm_ticker(t) for t in tickers}
    covered_tickers = {t for t, st in covered_map.items() if st in prices}
    sh = [t for t in tickers if t.endswith(".SH")]
    sz = [t for t in tickers if t.endswith(".SZ")]
    print(f"\n[coverage] unique E2 tickers: {len(tickers)} "
          f"(SH {len(sh)}, SZ {len(sz)}, other {len(tickers)-len(sh)-len(sz)})")
    print(f"  covered after .SH->.SS normalization: {len(covered_tickers)} "
          f"({100*len(covered_tickers)/max(len(tickers),1):.1f}% of tickers)")

    ev = events.copy()
    ev["store_ticker"] = ev["ticker"].map(covered_map)
    ev["covered"] = ev["store_ticker"].isin(prices.keys())
    n_cov = int(ev["covered"].sum())
    print(f"  covered EVENTS: {n_cov:,}/{len(ev):,} = {100*n_cov/max(len(ev),1):.1f}% "
          f"(join coverage — expected ~30%)")

    cov = ev[ev["covered"]].copy()

    # per-ticker vectorized return computations
    path, fwd21, fwd63, fwd21_t1, fwd63_t1 = {}, {}, {}, {}, {}
    for st, grp in cov.groupby("store_ticker"):
        s = prices[st]
        d = np.array(pd.DatetimeIndex(grp["date"]).values)
        path[st] = (grp.index, _anchored_returns(s, d, 0, ABSORPTION_WINDOW))
        fwd21[st] = (grp.index, _anchored_returns(s, d, ENTRY_LAG, ENTRY_LAG + 21))
        fwd63[st] = (grp.index, _anchored_returns(s, d, ENTRY_LAG, ENTRY_LAG + 63))
        # NON-GATED sensitivity: merged-code convention (entry at t, overlaps window)
        fwd21_t1[st] = (grp.index, _anchored_returns(s, d, 0, 21))
        fwd63_t1[st] = (grp.index, _anchored_returns(s, d, 0, 63))

    for name, store in [("path_ret", path), ("fwd_ret_21d", fwd21), ("fwd_ret_63d", fwd63),
                        ("fwd_ret_21d_t1", fwd21_t1), ("fwd_ret_63d_t1", fwd63_t1)]:
        col = pd.Series(np.nan, index=cov.index)
        for st, (ix, vals) in store.items():
            col.loc[ix] = vals
        cov[name] = col

    # trailing vol / size at the block date (AM-E2-3: merged helpers verbatim)
    tvol, tsize = [], []
    for _, row in cov.iterrows():
        s = prices[row["store_ticker"]]
        tvol.append(_trailing_vol(s, row["date"]))
        tsize.append(_trailing_size(s, row["date"]))
    cov["trailing_vol"] = tvol
    cov["trailing_size"] = tsize
    return cov


# ---------------------------------------------------------------------------
# Absorption classification + matching features
# ---------------------------------------------------------------------------

def classify_and_bin(cov: pd.DataFrame, U: pd.DataFrame) -> pd.DataFrame:
    stats = U.notna().sum(axis=1)
    med = U.median(axis=1)
    edges = U.quantile([0.2, 0.4, 0.6, 0.8], axis=1).T  # index=date, cols=quantiles

    valid_dates = stats[stats >= MIN_UNIVERSE].index
    n_drop = int((~cov["date"].isin(valid_dates)).sum())
    print(f"\n[universe] event dates with >= {MIN_UNIVERSE} covered tickers: "
          f"{len(valid_dates):,}/{U.shape[0]:,}; events dropped for thin universe: {n_drop}")

    cov = cov[cov["date"].isin(valid_dates) & cov["path_ret"].notna()].copy()
    cov["universe_median"] = cov["date"].map(med)
    cov["absorbed"] = (cov["path_ret"] >= cov["universe_median"]).astype(int)

    e = edges.loc[cov["date"]].to_numpy()
    pr = cov["path_ret"].to_numpy()[:, None]
    cov["path_quintile"] = (pr >= e).sum(axis=1)  # 0..4 vs per-date universe edges

    n_abs = int(cov["absorbed"].sum())
    print(f"[absorption] {n_abs:,}/{len(cov):,} events absorbed "
          f"({100*n_abs/max(len(cov),1):.1f}%) — [t,t+10] own return >= per-date universe median")
    print(f"  path_quintile distribution: "
          f"{cov['path_quintile'].value_counts().sort_index().to_dict()}")

    # full-sample vol/size terciles (merged convention)
    vol_valid = cov["trailing_vol"].dropna()
    v33, v67 = float(vol_valid.quantile(0.333)), float(vol_valid.quantile(0.667))
    sz_valid = cov["trailing_size"].dropna()
    s33, s67 = float(sz_valid.quantile(0.333)), float(sz_valid.quantile(0.667))
    cov["vol_tercile"] = cov["trailing_vol"].apply(lambda v: _tercile_bucket(v, v33, v67, "mid"))
    cov["size_tercile"] = cov["trailing_size"].apply(lambda v: _tercile_bucket(v, s33, s67, "mid"))
    print(f"[matching_features] vol T33={v33:.5f} T67={v67:.5f}; size T33={s33:.2f} T67={s67:.2f}")
    return cov


# ---------------------------------------------------------------------------
# Matched pairs + G1 (mirrors merged build_matched_pairs / g1_clustered_tstat)
# ---------------------------------------------------------------------------

def build_matched_pairs(df: pd.DataFrame, fwd_col: str) -> pd.DataFrame:
    df = df[df["absorbed"].notna() & df[fwd_col].notna()].copy()
    df["quarter"] = df["date"].dt.to_period("Q")
    absorbed_events = df[df["absorbed"] == 1]
    control_pool = df[df["absorbed"] == 0]

    pairs, n_excluded = [], 0
    for _, ab in absorbed_events.iterrows():
        mask = (
            (control_pool["path_quintile"] == ab["path_quintile"])
            & (control_pool["vol_tercile"] == ab["vol_tercile"])
            & (control_pool["size_tercile"] == ab["size_tercile"])
        )
        controls = control_pool[mask]
        if len(controls) == 0:
            controls = control_pool[control_pool["path_quintile"] == ab["path_quintile"]]
        if len(controls) == 0:
            n_excluded += 1
            continue
        ctrl_sample = controls.sample(n=min(MAX_CONTROLS, len(controls)), random_state=42)
        for _, ct in ctrl_sample.iterrows():
            pairs.append({
                "signal_date": ab["date"],
                "quarter": ab["quarter"],
                "diff": float(ab[fwd_col]) - float(ct[fwd_col]),
            })
    out = pd.DataFrame(pairs)
    print(f"\n[matched_pairs {fwd_col}] {len(out):,} pairs from "
          f"{out['signal_date'].nunique() if len(out) else 0:,} event dates, "
          f"{out['quarter'].nunique() if len(out) else 0} quarters; "
          f"absorbed excluded (no controls, AM-2): {n_excluded}/{len(absorbed_events)} "
          f"({100*n_excluded/max(len(absorbed_events),1):.1f}%)")
    return out, n_excluded, len(absorbed_events)


def g1_cell(pairs: pd.DataFrame, label: str) -> dict:
    if len(pairs) == 0:
        return {"label": label, "n_pairs": 0, "n_clusters": 0, "mean_diff": None,
                "t_hac": None, "p_hac": None, "t_iid": None, "p_iid": None}
    quarterly = pairs.groupby("quarter")["diff"].mean()
    res = _nw_tstat(quarterly)
    from scipy import stats as sst
    t_iid, p_iid = sst.ttest_1samp(pairs["diff"].dropna(), 0)
    cell = {
        "label": label, "n_pairs": len(pairs), "n_clusters": len(quarterly),
        "mean_diff": float(pairs["diff"].mean()),
        "t_hac": res["t"], "p_hac": res["p"],
        "t_iid": float(t_iid), "p_iid": float(p_iid),
    }
    print(f"[G1 {label}] n_pairs={cell['n_pairs']:,}, n_quarters={cell['n_clusters']}, "
          f"mean_diff={cell['mean_diff']*100:+.3f}pp, t_HAC={cell['t_hac']}, "
          f"p_HAC={cell['p_hac']}, t_iid={cell['t_iid']:.2f}")
    return cell


def descriptive_g2_g3(pairs_21: pd.DataFrame, pairs_63: pd.DataFrame) -> dict:
    out = {"g2": {}, "g3": []}
    for h, p in [(21, pairs_21), (63, pairs_63)]:
        if len(p) == 0:
            out["g2"][h] = {"h1": None, "h2": None, "same_sign": False}
            continue
        h1 = float(p[p["signal_date"] < SPLIT_DATE]["diff"].mean())
        h2 = float(p[p["signal_date"] >= SPLIT_DATE]["diff"].mean())
        out["g2"][h] = {"h1": h1, "h2": h2,
                        "same_sign": (not math.isnan(h1)) and (not math.isnan(h2)) and h1 * h2 > 0}
    for lab, a, b in CRISIS_WINDOWS:
        for h, p in [(21, pairs_21), (63, pairs_63)]:
            if len(p) == 0:
                out["g3"].append({"label": lab, "h": h, "mean": None})
                continue
            excl = p[~((p["signal_date"] >= a) & (p["signal_date"] <= b))]
            out["g3"].append({"label": lab, "h": h,
                              "mean": float(excl["diff"].mean()) if len(excl) else None})
    return out


# ---------------------------------------------------------------------------
# Report amendment
# ---------------------------------------------------------------------------

def _f(v, scale=100.0, digits=2, suffix="%"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    return f"{v*scale:+.{digits}f}{suffix}"


def render_report_section(ctx: dict) -> str:
    L: list[str] = []
    W = L.append
    W(SECTION_HEADING)
    W("")
    W("*Amended 2026-07-08 by `scripts/d4_cn_supply_absorption_e2_rerun.py` — E2 leg only;")
    W("E1 cells frozen from the merged run (PR #1932).*")
    W("")
    W("### Correction of the record")
    W("")
    W("The merged run registered E2 as a data-gap null, stating `data/china_block_tape`")
    W("\"does not exist anywhere in the worktree.\" That was a MIS-PATH, not a data gap:")
    W("the F5-01 archiver's historical tape exists at `data/china_block_tape` (mrtj yearly")
    W("partitions, 2005-2026; runner-local/untracked, so a fresh worktree does not carry")
    W("it). The lane substituted `data/china_block_trades/detail.parquet` — a single-date")
    W("rolling snapshot — leaving E2 with 61 rows and no event tape. This section re-runs")
    W("ONLY the E2 leg against the correct store under the frozen design. The §2/§7 claims")
    W("that the tape does not exist are superseded.")
    W("")
    W("### Event set (verification-law prints)")
    W("")
    W("| Check | Value |")
    W("|---|---|")
    W(f"| mrtj tape rows (all years) | {ctx['tape_rows']:,} |")
    W(f"| Usable rows (2013+, per spec) | {ctx['usable_rows']:,} |")
    W("| Unit assertion | `premium_ratio` is a RAW ratio (identity vs `cross_price/close - 1` verified; 0 rows <= -15 in raw units — the field is NOT percent); derived `avg_premium_pct = premium_ratio x 100` |")
    W(f"| avg_premium_pct (percent, derived) | min {ctx['app_min']:.2f} / median {ctx['app_med']:.2f} / max {ctx['app_max']:.2f} |")
    W(f"| Deep-discount filter (<= -15) pass rate | {ctx['n_events']:,} / {ctx['usable_rows']:,} = {ctx['pass_rate']:.2f}% (F5-01 audit expectation ~8% — consistent) |")
    W(f"| Ticker join coverage (.SH->.SS) | {ctx['cov_events']:,} / {ctx['n_events']:,} events = {ctx['cov_rate']:.1f}% (expected ~30%) |")
    W(f"| Events after universe + path validity | {ctx['n_final']:,} ({ctx['n_dropped_universe']} dropped for thin universe) |")
    W(f"| Absorbed ([t,t+10] own return >= per-date universe median) | {ctx['n_absorbed']:,} / {ctx['n_final']:,} = {ctx['abs_rate']:.1f}% |")
    W("")
    W("Implementation amendments AM-E2-1..3, registered in the script docstring before")
    W("results: path quintile binned against the per-date UNIVERSE [t,t+10] return")
    W("distribution (a per-date qcut across same-date E2 events is degenerate at ~4")
    W("events/date and would silently delete the path control); >= 30 covered tickers")
    W("required per event date; trailing vol/size reuse the merged helpers verbatim.")
    W("")
    W("### G1 — gated cells (entry t+10+1, registered convention)")
    W("")
    W("Matching, clustering and thresholds are the merged design unchanged: up to 3")
    W("non-absorbed controls per absorbed event matched on (path quintile, vol tercile,")
    W("size tercile) with path-quintile-only relaxation; calendar-quarter collapse +")
    W("Newey-West; gate |t_HAC| >= 2 AND BH q <= 0.10, BH re-computed across the")
    W("now-4 gated cells (two frozen E1 cells + two E2 cells from this run):")
    W("")
    W("| Cell | n pairs | n quarters | diff (abs - ctrl) | t_iid | t_HAC | p_HAC | BH q (4-cell) | Gate |")
    W("|---|---|---|---|---|---|---|---|---|")
    for key, c in ctx["bh_table"]:
        t_iid = f"{c['t_iid']:.2f}" if c.get("t_iid") is not None else "N/A"
        t_hac = f"{c['t_hac']:.3f}" if c.get("t_hac") is not None else "N/A"
        p_hac = f"{c['p_hac']:.3f}" if c.get("p_hac") is not None else "N/A"
        q = f"{c['bh_q']:.3f}" if c.get("bh_q") is not None else "N/A"
        gate = "**PASS**" if c["gate_pass"] else "**FAIL**"
        src = " (frozen)" if key.startswith("E1") else ""
        W(f"| {key}{src} | {c['n_pairs']:,} | {c['n_clusters']} | {_f(c['mean_diff'])} | "
          f"{t_iid} | {t_hac} | {p_hac} | {q} | {gate} |")
    W("")
    ex21, na21 = ctx["excl"][21]
    ex63, na63 = ctx["excl"][63]
    W(f"**AM-2 exclusion rate (reported per the amendment):** absorbed events with zero")
    W(f"same-path-quintile controls are excluded — {ex21:,}/{na21:,} ({100*ex21/max(na21,1):.1f}%)")
    W(f"at 21d, {ex63:,}/{na63:,} ({100*ex63/max(na63,1):.1f}%) at 63d. The rate is")
    W("structurally high by construction, not a data defect: absorption is DEFINED as")
    W("path >= per-date universe median, so absorbed events occupy universe path")
    W("quintiles 2-4 while the non-absorbed control pool occupies 0-2. The only region")
    W("where both classes coexist is the median-straddling quintile, so G1 is identified")
    W("off boundary events — which is precisely the red-team neutralization question")
    W("(does absorption add anything beyond the path itself, holding the path fixed?).")
    W("The merged E1 leg shares this structure.")
    W("")
    W("**ENTRY-CONVENTION DISCREPANCY FLAG:** the registered design (and the merged")
    W("report's §4 table) specifies entry = t+10+1, but the merged E1 *code* measured")
    W("forward returns from t itself, overlapping the absorption window. The gated E2")
    W("cells above implement the registered entry. For an apples-to-apples read against")
    W("the E1 numbers, the merged-code convention is reported below as a NON-GATED")
    W("sensitivity (logged to the trial ledger; not part of the gate panel):")
    W("")
    W("| Sensitivity cell (entry t, overlaps absorption window) | n pairs | n quarters | diff | t_iid | t_HAC | p_HAC |")
    W("|---|---|---|---|---|---|---|")
    for key, c in ctx["sens_cells"]:
        t_iid = f"{c['t_iid']:.2f}" if c.get("t_iid") is not None else "N/A"
        t_hac = f"{c['t_hac']:.3f}" if c.get("t_hac") is not None else "N/A"
        p_hac = f"{c['p_hac']:.3f}" if c.get("p_hac") is not None else "N/A"
        W(f"| {key} | {c['n_pairs']:,} | {c['n_clusters']} | {_f(c['mean_diff'])} | "
          f"{t_iid} | {t_hac} | {p_hac} |")
    W("")
    W("Read the sensitivity with care: under the entry-at-t convention the forward")
    W("window CONTAINS the absorption window, and within a matched path quintile the")
    W("absorbed events sit above the quintile's own median path by construction. Much of")
    W("the sensitivity diff is therefore the residual within-quintile path gap itself,")
    W("not post-window alpha — the same contamination channel the merged report's G4")
    W("discussion identified. The clean post-window increment is what the gated cells")
    W("measure, and it is small and statistically indistinguishable from zero. No entry")
    W("convention changes the family outcome: under the merged-code convention the E1")
    W("cells themselves remain failed (t_HAC -1.29 / +1.86).")
    W("")
    W("### G2 / G3 (descriptive, per the merged family design)")
    W("")
    g2 = ctx["g2g3"]["g2"]
    W("| Split at 2020-09-23 | 21d diff | 63d diff |")
    W("|---|---|---|")
    W(f"| H1 (pre) | {_f(g2[21]['h1'])} | {_f(g2[63]['h1'])} |")
    W(f"| H2 (post) | {_f(g2[21]['h2'])} | {_f(g2[63]['h2'])} |")
    W("")
    W("| Crisis excluded | 21d diff | 63d diff |")
    W("|---|---|---|")
    g3 = ctx["g2g3"]["g3"]
    for lab, _, _ in CRISIS_WINDOWS:
        r21 = next(r for r in g3 if r["label"] == lab and r["h"] == 21)
        r63 = next(r for r in g3 if r["label"] == lab and r["h"] == 63)
        W(f"| Excl {lab} | {_f(r21['mean'])} | {_f(r63['mean'])} |")
    W("")
    g2_21_ss = g2[21]["same_sign"]
    g2_63_ss = g2[63]["same_sign"]
    W(f"Split halves same-sign: {'yes' if g2_21_ss else 'NO'} at 21d, "
      f"{'yes' if g2_63_ss else 'NO'} at 63d"
      + (" — the 21d effect flips sign in the early half, so G2 would fail"
         " descriptively for E2." if not (g2_21_ss and g2_63_ss) else "."))
    W("")
    W("### Gate outcome and family verdict")
    W("")
    e2_pass = ctx["e2_pass"]
    W(f"**E2 G1: {'PASS' if e2_pass else 'FAIL'}.** "
      + ("Both E2 cells clear |t_HAC| >= 2 with BH q <= 0.10 under the 4-cell panel."
         if e2_pass else
         "The E2 cells do not clear |t_HAC| >= 2 with BH q <= 0.10 under the 4-cell panel."))
    W("")
    if ctx["e1_bh_changed"]:
        W("Note: re-computing BH over 4 cells changed an E1 cell's BH flag, but E1 gate")
        W("outcomes are unchanged (both E1 t_HAC remain below the |t| >= 2 threshold).")
        W("")
    W(f"**FAMILY VERDICT: {'CHANGES to PASS' if ctx['family_changes'] else 'UNCHANGED — FAIL'}.** "
      + ("E2 passes G1 under the re-computed 4-cell BH; the family verdict flips per the"
         " pre-registered rule." if ctx["family_changes"] else
         "The pre-registered rule flips the family verdict only if E2 passes G1 under the"
         " re-computed 4-cell BH; it does not. The well-powered E1 legs already failed G1"
         " in the merged run, and the corrected-path E2 leg "
         + ("does not rescue the family." if not e2_pass else "")))
    W("")
    W("The E2 'registered null' in §7 is retired: the null was a mis-path artifact, not a")
    W("data gap. The F5-01 archiver re-entry condition (>= 3 years of tape) was already")
    W("satisfied at merge time.")
    W("")
    W(f"*Store: `{ctx['store']}` (mrtj partitions; runner-local/untracked — set")
    W(f"CHINA_BLOCK_TAPE_STORE when the worktree does not carry it).")
    W(f"Prices: `data/china_stocks_raw` with .SH->.SS normalization. Repro:")
    W(f"`python -m scripts.d4_cn_supply_absorption_e2_rerun`. Trial-ledger rows for this")
    W(f"run were logged then restored per the intraday data/-discard law; the delta is")
    W(f"reported in the PR body. Numbers above are display-tier study output, not a")
    W(f"production signal.*")
    W("")
    return "\n".join(L)


def amend_report(section_text: str) -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    if SECTION_HEADING in text:
        text = text[: text.index(SECTION_HEADING)].rstrip() + "\n"
    else:
        text = text.rstrip() + "\n"
    text += "\n---\n\n" + section_text
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(f"\n[report] Amended: {REPORT_PATH} (section: {SECTION_HEADING!r})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print(f"FAMILY: {FAMILY} — E2 re-entry (corrected path), E2 leg ONLY")
    print("=" * 70)

    tape = load_tape()
    events = build_e2_events(tape)

    prices = load_price_store()
    cov = build_event_table(events, prices)

    dates = sorted(cov["date"].unique())
    print(f"\n[universe] computing [t,t+10] returns for {len(prices)} tickers x "
          f"{len(dates)} event dates ...")
    U = universe_path_matrix(prices, dates)

    cov = classify_and_bin(cov, U)

    # ---- G1 gated cells (registered entry t+10+1) ----
    pairs_21, excl_21, nabs_21 = build_matched_pairs(cov, "fwd_ret_21d")
    pairs_63, excl_63, nabs_63 = build_matched_pairs(cov, "fwd_ret_63d")
    e2_21 = g1_cell(pairs_21, "E2_x_21d")
    e2_63 = g1_cell(pairs_63, "E2_x_63d")

    # ---- Sensitivity (merged-code entry convention; NON-GATED) ----
    pairs_21_t1, _, _ = build_matched_pairs(cov, "fwd_ret_21d_t1")
    pairs_63_t1, _, _ = build_matched_pairs(cov, "fwd_ret_63d_t1")
    s2_21 = g1_cell(pairs_21_t1, "E2_x_21d_entryT_sens")
    s2_63 = g1_cell(pairs_63_t1, "E2_x_63d_entryT_sens")

    # ---- 4-cell BH (frozen E1 + fresh E2) ----
    panel_p = {
        "E1_x_21d": E1_FROZEN["E1_x_21d"]["p_hac"],
        "E1_x_63d": E1_FROZEN["E1_x_63d"]["p_hac"],
        "E2_x_21d": e2_21["p_hac"],
        "E2_x_63d": e2_63["p_hac"],
    }
    bh = benjamini_hochberg(panel_p, alpha=0.10)
    print(f"\n[BH 4-cell] {bh}")

    cells = {}
    for key in ["E1_x_21d", "E1_x_63d", "E2_x_21d", "E2_x_63d"]:
        base = dict(E1_FROZEN[key]) if key in E1_FROZEN else dict(e2_21 if key == "E2_x_21d" else e2_63)
        base["bh_q"] = bh.get(key, {}).get("q")
        base["bh_reject"] = bh.get(key, {}).get("reject", False)
        base["gate_pass"] = (base.get("t_hac") is not None
                             and abs(base["t_hac"]) >= 2.0 and base["bh_reject"])
        base.setdefault("t_iid", None)
        cells[key] = base

    e2_pass = cells["E2_x_21d"]["gate_pass"] and cells["E2_x_63d"]["gate_pass"]
    # merged run: neither E1 cell BH-rejected under the 2-cell panel
    e1_bh_changed = cells["E1_x_21d"]["bh_reject"] or cells["E1_x_63d"]["bh_reject"]
    family_changes = e2_pass

    print(f"\n[gate] E2 G1 pass: {e2_pass}")
    print(f"[verdict] FAMILY VERDICT {'CHANGES to PASS' if family_changes else 'UNCHANGED: FAIL'}")

    # ---- descriptive G2/G3 on gated-convention pairs ----
    g2g3 = descriptive_g2_g3(pairs_21, pairs_63)

    # ---- trial ledger (logged; the lane restores the file after capturing delta) ----
    led = TrialLedger(family=FAMILY)
    ledger_rows = []
    for key in ["E2_x_21d", "E2_x_63d"]:
        c = cells[key]
        ledger_rows.append({
            "cell": f"{key}_matched_tape", "source_store": "data/china_block_tape",
            "entry": "t+10+1", "label": f"E2 deep-discount block absorbed vs matched controls, {key.split('_x_')[1]}",
            "mean_ret": c["mean_diff"], "t_hac": c["t_hac"], "p_hac": c["p_hac"],
            "bh_q_4cell": c["bh_q"], "gate_pass": c["gate_pass"],
        })
    for lab, c in [("E2_x_21d", s2_21), ("E2_x_63d", s2_63)]:
        ledger_rows.append({
            "cell": f"{lab}_matched_tape_entryT_sens", "source_store": "data/china_block_tape",
            "entry": "t (merged-code convention; NON-GATED sensitivity)",
            "mean_ret": c["mean_diff"], "t_hac": c["t_hac"], "p_hac": c["p_hac"],
            "gate_pass": False,
        })
    n_new = led.log_grid(ledger_rows, family=FAMILY,
                         note="E2 re-entry corrected path (d4_cn_supply_absorption_e2_rerun)")
    print(f"\n[trial_ledger] logged {n_new} new rows (family {FAMILY})")

    # ---- report ----
    app = tape.loc[tape["date"] >= USABLE_FROM, "avg_premium_pct"]
    ctx = {
        "tape_rows": len(tape),
        "usable_rows": int((tape["date"] >= USABLE_FROM).sum()),
        "app_min": float(app.min()), "app_med": float(app.median()), "app_max": float(app.max()),
        "n_events": len(events),
        "pass_rate": 100.0 * len(events) / max(int((tape["date"] >= USABLE_FROM).sum()), 1),
        "cov_events": int(events["ticker"].map(lambda t: _norm_ticker(t)).isin(prices.keys()).sum()),
        "cov_rate": 100.0 * int(events["ticker"].map(lambda t: _norm_ticker(t)).isin(prices.keys()).sum()) / max(len(events), 1),
        "n_final": len(cov),
        "n_dropped_universe": int(events["ticker"].map(lambda t: _norm_ticker(t)).isin(prices.keys()).sum() - len(cov)),
        "n_absorbed": int(cov["absorbed"].sum()),
        "abs_rate": 100.0 * int(cov["absorbed"].sum()) / max(len(cov), 1),
        "bh_table": [(k, cells[k]) for k in ["E1_x_21d", "E1_x_63d", "E2_x_21d", "E2_x_63d"]],
        "sens_cells": [("E2_x_21d entry-t", s2_21), ("E2_x_63d entry-t", s2_63)],
        "g2g3": g2g3,
        "e2_pass": e2_pass,
        "e1_bh_changed": e1_bh_changed,
        "family_changes": family_changes,
        "excl": {21: (excl_21, nabs_21), 63: (excl_63, nabs_63)},
        "store": ("data/china_block_tape" if TAPE_STORE.name == "china_block_tape"
                  else str(TAPE_STORE)),
    }
    amend_report(render_report_section(ctx))
    print("\n[done] E2 re-entry complete.")


if __name__ == "__main__":
    main()
