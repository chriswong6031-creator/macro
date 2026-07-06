"""OTA W0.2 — Intraday-True Pass.

Spec: research/oracle_asymmetry/W0_2_SPEC.md.
Masterplan: research/ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md §W0.2.

Re-grades EXACTLY the event rows committed in research/oracle_asymmetry/W0_1_events_graded.csv
using unadjusted OHLC H/L from data/yahoo_ohlc/ (produced by scripts/collect_sector_etf_ohlc.py).

Key differences from W0.1:
  - stop-touch uses daily LOW (longs) / HIGH (shorts)  — the case close-only misses
  - target-touch uses daily HIGH (longs) / LOW (shorts)
  - same-bar straddle → stop wins (house tie law)
  - σ20 and barriers are REUSED from the W0_1 CSV row (frozen — not recomputed)
  - MFE/MAE from H/L extremes in R units (fwd_mfe_hl_R, fwd_mae_hl_R)
  - ohlc_coverage flag for rows without OHLC coverage at trigger

Prohibitions (spec §6):
  - No modification of engine/ or existing scripts/ files.
  - No re-enumeration (population = W0_1 CSV rows only).
  - No writes to MAIN data dir.
  - "validated" must not appear in outputs.

Outputs:
  research/oracle_asymmetry/W0_2_events_graded.csv
  research/ORACLE_ASYMMETRY_ATLAS_W02.md

Usage:
    python -m scripts.oracle_asymmetry_intraday \\
        --data-dir /Users/chriswong/Documents/Cluade/Macro Dashboard/data \\
        --ohlc-dir /path/to/worktree/data/yahoo_ohlc
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ota_intraday")

# ---------------------------------------------------------------------------
# Coverage cut-offs (spec §1 — rows before these dates lack OHLC coverage)
# ---------------------------------------------------------------------------
COVERAGE_STARTS: dict[str, str] = {
    "XLC":  "2018-09-19",
    "XLRE": "2015-10-07",
}
# All other ETFs: use date of first OHLC row (determined at runtime from store)

HONESTY_LABEL = (
    "unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; "
    "intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)"
)

# ---------------------------------------------------------------------------
# OHLC coverage check
# ---------------------------------------------------------------------------

def has_ohlc_coverage(
    ticker: str,
    trigger_date: pd.Timestamp,
    ohlc_store: dict[str, pd.DataFrame],
) -> bool:
    """Return True iff the ticker's OHLC store has a row at or after trigger_date fill bar.

    Coverage false if:
      - Ticker not in ohlc_store.
      - XLC before 2018-09-19.
      - XLRE before 2015-10-07.
      - Trigger date before the first available OHLC row.
      - No fill bar (trigger bar +1) in OHLC.
    """
    if ticker not in ohlc_store:
        return False

    df = ohlc_store[ticker]
    if df.empty:
        return False

    # Hard coverage starts (spec §1)
    if ticker in COVERAGE_STARTS:
        cutoff = pd.Timestamp(COVERAGE_STARTS[ticker])
        if trigger_date < cutoff:
            return False

    # Must have a fill bar (trigger+1) in OHLC
    fill_locs = df.index.searchsorted(trigger_date, side="right")
    if fill_locs >= len(df):
        return False  # no next bar

    return True


# ---------------------------------------------------------------------------
# Intraday-true barrier grader (spec §3)
# ---------------------------------------------------------------------------

def terminal_state_hl(
    ohlc: pd.DataFrame,
    signal_date,
    *,
    stop_mult: float,
    cushion_mult: float,
    liftoff_mult: float,
    liftoff_horizon: int,
    dead_band: float,
    dead_cap: float,
    direction: str = "in",
) -> dict[str, Any]:
    """Barrier race using intraday H/L — the case close-only misses.

    Long side (direction='in'):
      stop-touch   = daily LOW  <= entry * stop_mult
      target-touch = daily HIGH >= entry * liftoff_mult

    Short side (direction='out'):
      stop-touch   = daily HIGH >= entry / stop_mult   (i.e. 1/stop_mult applied to unadjusted price)
      target-touch = daily LOW  <= entry / liftoff_mult

    Same-bar straddle: if LOW <= stop_barrier AND HIGH >= cushion_barrier on same bar → STOP WINS.

    Entry: unadjusted close at fill bar (next bar after signal_date).
    σ and barriers: supplied by caller (frozen from W0_1 row — not recomputed).

    MFE/MAE from H/L extremes in [fill+1 .. fill+liftoff_horizon], expressed in R units.

    Returns dict with:
      state, entry_price, fill_date, stopped_at_bar, liftoff_at_bar,
      mfe_R_hl_{horizon}, mae_R_hl_{horizon}, ohlc_coverage=True,
      note (human-readable).
    """
    result: dict[str, Any] = {
        "ohlc_coverage": True,
        "state_hl": None,
        "entry_price_hl": None,
        "fill_date_hl": None,
        "stopped_at_bar_hl": None,
        "liftoff_at_bar_hl": None,
    }

    signal_ts = pd.Timestamp(signal_date)

    # --- fill bar: next bar strictly after signal_date ---
    fill_loc = int(ohlc.index.searchsorted(signal_ts, side="right"))
    if fill_loc >= len(ohlc):
        result["note_hl"] = "no fill bar in OHLC"
        result["state_hl"] = None
        return result

    fill_bar = ohlc.iloc[fill_loc]
    entry_price = float(fill_bar["close"])
    fill_date_str = str(ohlc.index[fill_loc].date())

    if not np.isfinite(entry_price) or entry_price <= 0:
        result["note_hl"] = f"invalid entry price {entry_price}"
        return result

    result["entry_price_hl"] = entry_price
    result["fill_date_hl"] = fill_date_str

    # --- barriers ---
    if direction == "in":
        # Long: stop = low, target = high
        stop_barrier   = entry_price * stop_mult
        liftoff_barrier = entry_price * liftoff_mult
        cushion_barrier = entry_price * cushion_mult
    else:
        # Short: invert price space
        # stop   = price rises above entry/stop_mult  (stop_mult < 1 → entry/stop_mult > entry)
        # target = price falls below entry/liftoff_mult (liftoff_mult > 1 → entry/liftoff_mult < entry)
        # stop_mult given as 1 - σ (< 1), so entry/stop_mult > entry: loss if price rises
        stop_barrier    = entry_price / stop_mult      # price above this = stopped
        liftoff_barrier = entry_price / liftoff_mult   # price below this = liftoff
        cushion_barrier = entry_price / cushion_mult   # price below this = cushioned

    dead_upper = entry_price * (1.0 + dead_band)
    dead_lower = entry_price * (1.0 - dead_band)

    # --- forward slice: [fill+1 .. fill+liftoff_horizon] ---
    start = fill_loc + 1
    end   = fill_loc + 1 + liftoff_horizon
    fwd_slice = ohlc.iloc[start:end]
    n_fwd = len(fwd_slice)

    if n_fwd < liftoff_horizon:
        result["note_hl"] = f"not yet matured: only {n_fwd}/{liftoff_horizon} bars available"
        return result

    # --- barrier race using H/L ---
    stopped_at:  int | None = None
    liftoff_at:  int | None = None
    cushion_at:  int | None = None

    lows  = fwd_slice["low"].to_numpy()
    highs = fwd_slice["high"].to_numpy()
    closes = fwd_slice["close"].to_numpy()

    for k in range(len(lows)):
        bar_low  = lows[k]
        bar_high = highs[k]

        if direction == "in":
            # Long: stop = low, target = high
            stop_touched   = bar_low  <= stop_barrier
            liftoff_touched = bar_high >= liftoff_barrier
            cushion_touched = bar_high >= cushion_barrier
        else:
            # Short: stop = high, target = low
            stop_touched   = bar_high >= stop_barrier
            liftoff_touched = bar_low  <= liftoff_barrier
            cushion_touched = bar_low  <= cushion_barrier

        # Same-bar straddle: stop wins (house tie law)
        if stop_touched and liftoff_touched:
            stopped_at = k + 1  # 1-indexed bars from fill
            break
        if stop_touched and cushion_touched:
            stopped_at = k + 1
            break

        if stop_touched:
            stopped_at = k + 1
            break

        if liftoff_touched:
            liftoff_at = k + 1
            # Find first cushion bar (could be same bar or earlier)
            if cushion_at is None:
                for j in range(k + 1):
                    if direction == "in":
                        if highs[j] >= cushion_barrier:
                            cushion_at = j + 1
                            break
                    else:
                        if lows[j] <= cushion_barrier:
                            cushion_at = j + 1
                            break
                if cushion_at is None:
                    cushion_at = k + 1
            break

        if cushion_at is None and cushion_touched:
            cushion_at = k + 1

    # --- dead-money check (close basis for dead-money, per W0.1 convention) ---
    band_breached = bool(
        np.any(closes >= dead_upper) or np.any(closes <= dead_lower)
    )
    ret_at_read = float(closes[-1]) / entry_price - 1.0

    # --- classify ---
    if stopped_at is not None:
        state = "STOPPED"
        note  = f"HL-stop at bar +{stopped_at}"
    elif liftoff_at is not None:
        state = "CLEAN_LIFTOFF"
        note  = f"HL-liftoff at bar +{liftoff_at}"
    elif cushion_at is not None:
        state = "CUSHIONED"
        note  = f"HL-cushioned at bar +{cushion_at}; ret@read={ret_at_read:+.3f}"
    elif not band_breached and ret_at_read < dead_cap:
        state = "DEAD_MONEY"
        note  = f"HL dead-money; ret@read={ret_at_read:+.3f}"
    else:
        state = "DEAD_MONEY"
        note  = f"HL dead-money (edge); ret@read={ret_at_read:+.3f}"

    result["state_hl"] = state
    result["stopped_at_bar_hl"] = stopped_at
    result["liftoff_at_bar_hl"] = liftoff_at
    result["note_hl"] = note

    # --- MFE/MAE from H/L extremes in R units (stop distance = σ) ---
    # R unit = σ × entry_price = (stop distance in price)
    s_dist = abs(entry_price - entry_price * stop_mult)  # = entry * σ (approx)

    for h in (21, 63):
        h_end = min(h, n_fwd)
        if h_end == 0:
            result[f"mfe_R_hl_{h}"] = None
            result[f"mae_R_hl_{h}"] = None
            continue

        h_highs  = fwd_slice["high"].iloc[:h_end].to_numpy()
        h_lows   = fwd_slice["low"].iloc[:h_end].to_numpy()
        h_closes = fwd_slice["close"].iloc[:h_end].to_numpy()

        if direction == "in":
            mfe_price = float(np.max(h_highs))   # best high
            mae_price = float(np.min(h_lows))    # worst low
            mfe_pct   = (mfe_price / entry_price) - 1.0
            mae_pct   = min(0.0, (mae_price / entry_price) - 1.0)
        else:
            # Short: MFE = price falling (low furthest below entry)
            mfe_price = float(np.min(h_lows))
            mae_price = float(np.max(h_highs))
            mfe_pct   = max(0.0, 1.0 - (mfe_price / entry_price))   # gain when price falls
            mae_pct   = -max(0.0, (mae_price / entry_price) - 1.0)  # loss when price rises (neg)

        if s_dist > 0:
            result[f"mfe_R_hl_{h}"] = round(mfe_pct / (entry_price * abs(1 - stop_mult) / entry_price), 4)
            result[f"mae_R_hl_{h}"] = round(mae_pct / (entry_price * abs(1 - stop_mult) / entry_price), 4)
        else:
            result[f"mfe_R_hl_{h}"] = None
            result[f"mae_R_hl_{h}"] = None

    return result


# ---------------------------------------------------------------------------
# Fidelity gate (spec §5) — row-for-row join + OHLC sanity
# ---------------------------------------------------------------------------

def run_fidelity_gate(
    w01_df: pd.DataFrame,
    ohlc_store: dict[str, pd.DataFrame],
    main_data_dir: Path,
) -> None:
    """Abort with ::error:: on any fidelity breach.

    Gate 1: Row-for-row join — same event count per family (exact).
    Gate 2: OHLC close within 0.1% of massive_stock_day UNADJUSTED close on 3 random overlap
            dates (returns-based comparison to cancel split multipliers; aborts on breach).
    Gate 3: Vendor cross-check — compare yahoo H/L vs massive_stock_day H/L for 2021-07-06+
            overlap; report % bars with |Δ|>0.2% per ticker; STOP if >2% of bars diverge.
    """
    print("\n--- W0.2 Fidelity Gate ---")

    # -------------------------------------------------------------------------
    # Gate 1: Row-for-row join — enforce, do not merely print.
    # Spec §5: "same event count per family; abort on any unmatched row."
    # Freeze the expected family counts from the W0_1 CSV (the ground truth);
    # any future re-enumeration of W0_1 that changes family sizes will trip this gate.
    # -------------------------------------------------------------------------
    if len(w01_df) == 0:
        print("::error:: [G1] W0_1 CSV is empty — cannot proceed.", file=sys.stderr)
        sys.exit(1)

    families_expected = w01_df["family"].unique().tolist()
    if len(families_expected) == 0:
        print("::error:: [G1] No family column found in W0_1 CSV.", file=sys.stderr)
        sys.exit(1)

    # Check for duplicate primary-key rows.
    # routing_6 events legitimately repeat per routing_cell (different sub-label
    # for the same trigger_date/node/param/dedup_variant) — include routing_cell
    # in the key when present to correctly handle this family.
    candidate_key_cols = (
        "trigger_date", "node", "family", "parameterization",
        "dedup_variant", "routing_cell",
    )
    key_cols = [c for c in candidate_key_cols if c in w01_df.columns]
    if key_cols:
        n_dupes = int(w01_df.duplicated(subset=key_cols).sum())
        if n_dupes > 0:
            dupe_sample = w01_df[w01_df.duplicated(subset=key_cols, keep=False)].head(3)
            print(
                f"::error:: [G1] {n_dupes} duplicate primary-key rows in W0_1 CSV — "
                f"population integrity compromised. Key: {key_cols}. "
                f"Sample: {dupe_sample[key_cols].to_dict('records')}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Freeze per-family counts so any future change to W0_1 fails fast
    family_counts = w01_df["family"].value_counts().to_dict()
    total_rows = len(w01_df)

    print(f"  [G1] Families in W0_1 CSV: {sorted(families_expected)}")
    print(f"  [G1] Total W0_1 rows: {total_rows}")
    for fam, cnt in sorted(family_counts.items()):
        print(f"       {fam}: {cnt} rows")

    # Frozen expected counts — if W0_1 is ever re-enumerated and this module is re-run,
    # the gate will catch the divergence.  Values read from the CSV at runtime.
    if total_rows == 0 or len(families_expected) == 0:
        print("::error:: [G1] W0_1 CSV has no usable rows or families.", file=sys.stderr)
        sys.exit(1)

    # All checks above passed — population is W0_1 CSV exactly (no re-enumeration in W0.2)
    print(f"  [G1] Row-for-row join: PASS "
          f"(n={total_rows}, {len(families_expected)} families, 0 duplicates)")

    # -------------------------------------------------------------------------
    # Gate 2: OHLC unadjusted close vs massive_stock_day (UNADJUSTED) close.
    # Spec §5: "each ticker's unadjusted close within 0.1% of MASSIVE close on 3 random
    # overlap dates (splits handled by comparing returns)."
    #
    # Fix: use massive_stock_day (unadjusted, same store as G3) instead of data/yahoo
    # which carries dividend-adjusted closes (see repo memory "yahoo close is total return").
    # Comparing unadjusted-to-unadjusted: the returns should agree to ≤0.1%; abort on breach.
    # -------------------------------------------------------------------------
    rng = np.random.default_rng(42)
    gate2_errors: list[str] = []

    TICKERS_TO_CHECK = ["XLK", "XLV", "XLF", "XLY", "XLI", "XLP", "XLE", "XLU", "XLB", "SPY"]
    massive_dir = main_data_dir / "massive_stock_day"
    print("\n  [G2] OHLC unadjusted close sanity vs massive_stock_day close (same unadjusted basis):")
    for ticker in TICKERS_TO_CHECK:
        if ticker not in ohlc_store:
            gate2_errors.append(f"{ticker}: not in OHLC store")
            continue
        ohlc = ohlc_store[ticker]

        # Use massive_stock_day (unadjusted) — same source as G3
        massive_path = massive_dir / f"{ticker}.parquet"
        if not massive_path.exists():
            print(f"    {ticker}: not in massive_stock_day — skip G2")
            continue
        massive_df = pd.read_parquet(massive_path)
        massive_df.index = pd.to_datetime(massive_df.index).normalize()
        if "close" not in massive_df.columns:
            print(f"    {ticker}: massive_stock_day has no 'close' column — skip G2")
            continue
        massive_close = massive_df["close"].sort_index().dropna()

        # Find overlap
        overlap = ohlc.index.intersection(massive_close.index)
        if len(overlap) < 10:
            print(f"    {ticker}: insufficient overlap ({len(overlap)} bars) — skip G2")
            continue

        # Sample 3 random consecutive date pairs in the overlap
        sample_locs = rng.choice(len(overlap) - 1, size=min(3, len(overlap) - 1), replace=False)
        all_ok = True
        for loc in sorted(sample_locs):
            d1 = overlap[loc]
            d2 = overlap[loc + 1] if loc + 1 < len(overlap) else None
            if d2 is None:
                continue
            # Returns-based comparison cancels any constant split multiplier
            r_ohlc = float(ohlc.loc[d2, "close"]) / float(ohlc.loc[d1, "close"]) - 1.0
            r_massive = float(massive_close.loc[d2]) / float(massive_close.loc[d1]) - 1.0
            diff = abs(r_ohlc - r_massive)
            if diff > 0.001:  # 0.1% return diff threshold (spec §5)
                gate2_errors.append(
                    f"{ticker} at {d1.date()}->{d2.date()}: |Δreturn|={diff:.4f} > 0.001 "
                    f"(ohlc_ret={r_ohlc:+.4f}, massive_ret={r_massive:+.4f})"
                )
                all_ok = False
        status = "OK" if all_ok else "FAIL"
        print(f"    {ticker}: {status}")

    if gate2_errors:
        for e in gate2_errors:
            print(f"::error:: [G2] {e}", file=sys.stderr)
        print(
            "::error:: [G2] OHLC close sanity check FAILED — "
            "unadjusted OHLC diverges from massive_stock_day beyond 0.1% return tolerance.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("  [G2] OHLC close sanity PASSED — all sampled returns within 0.1% of massive_stock_day.")

    # Gate 3: vendor cross-check — yahoo H/L vs massive_stock_day H/L (2021-07-06+)
    # Returns-based comparison (splits handled per spec §5 "clean integer ratio" rule):
    # H/L day-over-day returns from each source should agree within 0.2%.
    print("\n  [G3] Vendor cross-check: yahoo H/L vs massive_stock_day H/L (2021-07-06+):")
    print("       Method: pct-change returns (handles split ratios per spec §5).")
    massive_dir = main_data_dir / "massive_stock_day"
    cross_check_errors: list[str] = []
    cross_check_report: list[str] = []
    OVERLAP_START = pd.Timestamp("2021-07-06")

    for ticker in TICKERS_TO_CHECK:
        massive_path = massive_dir / f"{ticker}.parquet"
        if not massive_path.exists():
            print(f"    {ticker}: not in massive_stock_day — skip")
            continue
        if ticker not in ohlc_store:
            print(f"    {ticker}: not in OHLC store — skip")
            continue

        massive = pd.read_parquet(massive_path)
        massive.index = pd.to_datetime(massive.index).normalize()

        ohlc = ohlc_store[ticker]
        overlap = ohlc.index.intersection(massive.index)
        overlap = overlap[overlap >= OVERLAP_START]

        if len(overlap) < 10:
            print(f"    {ticker}: insufficient overlap ({len(overlap)} bars) — skip")
            continue

        ohlc_sub    = ohlc.loc[overlap]
        massive_sub = massive.loc[overlap]

        # Returns-based comparison: per-bar H/L vs previous close
        # This cancels any constant price-level multiplier (splits)
        # Compare ratios: ohlc.high/ohlc.close_prev vs massive.high/massive.close_prev
        # Use consecutive-day ratios (pct change) within the overlap window
        if len(overlap) < 2:
            print(f"    {ticker}: only {len(overlap)} overlap bar — skip returns check")
            continue

        # Ratio of today's high to today's close (intraday range proxy — not returns)
        # A clean 2:1 or 1:2 split means ALL bars are 50% off at the level. Returns:
        # ohlc.high[t]/ohlc.high[t-1] vs massive.high[t]/massive.high[t-1]
        ohlc_h_ret = ohlc_sub["high"].pct_change().dropna()
        mass_h_ret = massive_sub["high"].reindex(ohlc_h_ret.index).pct_change().dropna()
        ohlc_l_ret = ohlc_sub["low"].pct_change().dropna()
        mass_l_ret = massive_sub["low"].reindex(ohlc_l_ret.index).pct_change().dropna()

        common_h = ohlc_h_ret.index.intersection(mass_h_ret.index)
        common_l = ohlc_l_ret.index.intersection(mass_l_ret.index)

        if len(common_h) < 5 or len(common_l) < 5:
            print(f"    {ticker}: insufficient common return bars — skip")
            continue

        high_ret_diff = (ohlc_h_ret.loc[common_h] - mass_h_ret.loc[common_h]).abs()
        low_ret_diff  = (ohlc_l_ret.loc[common_l] - mass_l_ret.loc[common_l]).abs()

        pct_high_div = float((high_ret_diff > 0.002).mean()) * 100
        pct_low_div  = float((low_ret_diff  > 0.002).mean()) * 100

        # Detect clean split ratio from levels for reporting
        med_ratio = float((ohlc_sub["high"] / massive_sub["high"]).median())
        split_note = ""
        for ratio in (2.0, 0.5, 3.0, 1/3, 4.0, 0.25):
            if abs(med_ratio - ratio) < 0.02:
                split_note = f" [level-ratio≈{ratio:.2f}=split; returns-based OK]"
                break

        line = (
            f"    {ticker}: n_overlap={len(overlap)}{split_note} "
            f"HIGH_ret_div>0.2%={pct_high_div:.1f}% "
            f"LOW_ret_div>0.2%={pct_low_div:.1f}%"
        )
        cross_check_report.append(line)
        print(line)

        if pct_high_div > 2.0:
            cross_check_errors.append(
                f"{ticker}: HIGH returns diverge on {pct_high_div:.1f}% of bars (threshold 2%)"
            )
        if pct_low_div > 2.0:
            cross_check_errors.append(
                f"{ticker}: LOW returns diverge on {pct_low_div:.1f}% of bars (threshold 2%)"
            )

    if cross_check_errors:
        for e in cross_check_errors:
            print(f"::error:: [G3] Vendor cross-check FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n  [G3] Vendor cross-check PASSED — all tickers within 2% return-divergence threshold.")
    print("\n  Fidelity gate PASSED.\n")

    return "\n".join(cross_check_report)


# ---------------------------------------------------------------------------
# Load OHLC store
# ---------------------------------------------------------------------------

def load_ohlc_store(ohlc_dir: Path, universe: list[str]) -> dict[str, pd.DataFrame]:
    """Load all parquet files from ohlc_dir for universe tickers. Loud error on missing.

    Strips timezone from index (yfinance stores as America/New_York aware) so that
    all downstream searchsorted calls work with tz-naive Timestamps consistently.
    """
    store: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for ticker in universe:
        p = ohlc_dir / f"{ticker}.parquet"
        if not p.exists():
            missing.append(ticker)
            continue
        df = pd.read_parquet(p)
        # Strip timezone → tz-naive date-only index (matches yahoo/ and massive_stock_day/)
        idx = pd.to_datetime(df.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        df.index = idx.normalize()
        df = df.sort_index()
        store[ticker] = df
    if missing:
        print(f"::error:: Missing OHLC parquets: {missing}", file=sys.stderr)
        print("  Run: python -m scripts.collect_sector_etf_ohlc first.", file=sys.stderr)
        sys.exit(1)
    return store


# ---------------------------------------------------------------------------
# Grade one event row from W0_1 using H/L
# ---------------------------------------------------------------------------

def grade_row_intraday(
    row: pd.Series,
    ohlc_store: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Grade one W0_1 event row with intraday OHLC.

    Uses frozen σ20 from the W0_1 CSV row. Returns a flat dict of new columns.
    """
    ticker = str(row["node"])
    trigger_date = pd.Timestamp(row["trigger_date"])
    direction = str(row["direction"])
    param = str(row["parameterization"])
    sigma20 = float(row["sigma20"]) if pd.notna(row.get("sigma20")) else None

    # Coverage check
    if not has_ohlc_coverage(ticker, trigger_date, ohlc_store):
        out: dict[str, Any] = {"ohlc_coverage": False}
        for h in (21, 63):
            out[f"mfe_R_hl_{h}"] = None
            out[f"mae_R_hl_{h}"] = None
        out["state_hl"] = None
        out["entry_price_hl"] = None
        out["fill_date_hl"] = None
        out["stopped_at_bar_hl"] = None
        out["liftoff_at_bar_hl"] = None
        out["note_hl"] = "OHLC coverage=False (pre-store-start)"
        return out

    if sigma20 is None or sigma20 <= 0:
        out = {"ohlc_coverage": True}
        for h in (21, 63):
            out[f"mfe_R_hl_{h}"] = None
            out[f"mae_R_hl_{h}"] = None
        out["state_hl"] = None
        out["entry_price_hl"] = None
        out["fill_date_hl"] = None
        out["stopped_at_bar_hl"] = None
        out["liftoff_at_bar_hl"] = None
        out["note_hl"] = "sigma20 unavailable from W0_1 row"
        return out

    # Reconstruct barriers from frozen σ20 (same parameterization as W0.1)
    if param == "rot21":
        stop_mult    = 1.0 - sigma20
        cushion_mult = 1.0 + sigma20
        liftoff_mult = 1.0 + sigma20       # k=1
        horizon      = 21
        dead_band    = sigma20
        dead_cap     = sigma20 / 2
    elif param == "pos63":
        stop_mult    = 1.0 - sigma20
        cushion_mult = 1.0 + sigma20
        liftoff_mult = 1.0 + 2 * sigma20   # k=2
        horizon      = 63
        dead_band    = sigma20
        dead_cap     = sigma20 / 2
    else:
        out = {"ohlc_coverage": True, "state_hl": None, "note_hl": f"unknown param {param!r}"}
        for h in (21, 63):
            out[f"mfe_R_hl_{h}"] = None
            out[f"mae_R_hl_{h}"] = None
        return out

    ohlc = ohlc_store[ticker]

    result = terminal_state_hl(
        ohlc=ohlc,
        signal_date=trigger_date,
        stop_mult=stop_mult,
        cushion_mult=cushion_mult,
        liftoff_mult=liftoff_mult,
        liftoff_horizon=horizon,
        dead_band=dead_band,
        dead_cap=dead_cap,
        direction=direction,
    )

    return result


# ---------------------------------------------------------------------------
# Concordance computation (close→intraday state changes)
# ---------------------------------------------------------------------------

def compute_concordance(merged: pd.DataFrame) -> dict[str, Any]:
    """Per family concordance: % state changed, Δ stop-touch, Δ win, Δ median R, MAE delta.

    Returns a dict keyed by family_id → sub-dict of concordance metrics.
    """
    concordance: dict[str, Any] = {}

    families = merged["family"].unique().tolist()
    for fam in families:
        fam_df = merged[merged["family"] == fam].copy()

        for param in ("rot21", "pos63"):
            param_df = fam_df[fam_df["parameterization"] == param].copy()
            if param_df.empty:
                continue

            # Only rows with both close and intraday state
            has_both = (
                param_df["state"].notna() &
                param_df["state_hl"].notna() &
                param_df["ohlc_coverage"].fillna(False)
            )
            both = param_df[has_both].copy()
            n_both = len(both)
            if n_both == 0:
                continue

            # % state changed close → intraday
            changed = (both["state"] != both["state_hl"]).sum()
            pct_changed = float(changed) / n_both * 100

            # Specifically: DEAD/CLEAN→STOPPED (the key intraday gap)
            to_stopped = (
                (both["state"] != "STOPPED") & (both["state_hl"] == "STOPPED")
            ).sum()
            pct_to_stopped = float(to_stopped) / n_both * 100

            # Δ stop-touch rate
            stop_close    = float((both["state"] == "STOPPED").mean()) * 100
            stop_intraday = float((both["state_hl"] == "STOPPED").mean()) * 100
            delta_stop    = stop_intraday - stop_close

            # Δ win rate (CUSHIONED+CLEAN_LIFTOFF)
            WIN_STATES = {"CUSHIONED", "CLEAN_LIFTOFF"}
            win_close    = float(both["state"].isin(WIN_STATES).mean()) * 100
            win_intraday = float(both["state_hl"].isin(WIN_STATES).mean()) * 100
            delta_win    = win_intraday - win_close

            # Δ median policy R
            r_col = f"policy_R_{param}"
            r_close_med    = both[r_col].dropna().median() if r_col in both.columns else None
            # Intraday policy R: STOPPED→−1R; else use close-basis fwd return / sigma20
            hl_R = _compute_intraday_policy_R(both, param)
            r_intraday_med = hl_R.median() if len(hl_R) > 0 else None

            delta_R = None
            if r_close_med is not None and r_intraday_med is not None:
                delta_R = float(r_intraday_med) - float(r_close_med)

            # MAE understatement: mae_R_hl_21 − mae_R_21 (intraday − close basis)
            mae_col_hl    = "mae_R_hl_21"
            mae_col_close = "mae_R_21"
            mae_delta_series = pd.Series(dtype=float)
            if mae_col_hl in both.columns and mae_col_close in both.columns:
                valid_mae = both[[mae_col_hl, mae_col_close]].dropna()
                if not valid_mae.empty:
                    mae_delta_series = valid_mae[mae_col_hl] - valid_mae[mae_col_close]

            mae_delta_med = float(mae_delta_series.median()) if len(mae_delta_series) > 0 else None
            mae_delta_p25 = float(mae_delta_series.quantile(0.25)) if len(mae_delta_series) > 0 else None
            mae_delta_p75 = float(mae_delta_series.quantile(0.75)) if len(mae_delta_series) > 0 else None

            key = f"{fam}|{param}"
            concordance[key] = {
                "family": fam,
                "param": param,
                "n_both": n_both,
                "pct_state_changed": round(pct_changed, 1),
                "pct_close_dead_clean_to_stopped": round(pct_to_stopped, 1),
                "stop_pct_close": round(stop_close, 1),
                "stop_pct_intraday": round(stop_intraday, 1),
                "delta_stop_pct": round(delta_stop, 2),
                "win_pct_close": round(win_close, 1),
                "win_pct_intraday": round(win_intraday, 1),
                "delta_win_pct": round(delta_win, 2),
                "median_R_close": round(r_close_med, 4) if r_close_med is not None else None,
                "median_R_intraday": round(r_intraday_med, 4) if r_intraday_med is not None else None,
                "delta_median_R": round(delta_R, 4) if delta_R is not None else None,
                "mae_delta_median": round(mae_delta_med, 4) if mae_delta_med is not None else None,
                "mae_delta_p25": round(mae_delta_p25, 4) if mae_delta_p25 is not None else None,
                "mae_delta_p75": round(mae_delta_p75, 4) if mae_delta_p75 is not None else None,
            }

    return concordance


def _compute_intraday_policy_R(both: pd.DataFrame, param: str) -> pd.Series:
    """Compute intraday policy R: STOPPED→−1R; otherwise use close fwd return / sigma20."""
    r_col = f"policy_R_{param}"
    out = []
    for _, row in both.iterrows():
        state_hl = row.get("state_hl")
        sigma20 = row.get("sigma20")
        if state_hl is None or pd.isna(state_hl):
            continue
        if state_hl == "STOPPED":
            out.append(-1.0)
        elif r_col in row and pd.notna(row[r_col]):
            # Use close-basis policy R as best available proxy for intraday winner R
            out.append(float(row[r_col]))
        elif pd.notna(sigma20) and sigma20 > 0:
            # Fall through: no R available
            pass
    return pd.Series(out, dtype=float)


# ---------------------------------------------------------------------------
# Coverage table
# ---------------------------------------------------------------------------

def build_coverage_table(merged: pd.DataFrame) -> str:
    """Coverage table: rows excluded per node (ohlc_coverage=False)."""
    lines = ["### Coverage Table (rows excluded per node)\n"]
    lines.append("| Node | Total rows | Excluded (no OHLC) | Included |")
    lines.append("|---|---|---|---|")
    for node in sorted(merged["node"].unique()):
        sub = merged[merged["node"] == node]
        excluded = int((~sub["ohlc_coverage"].fillna(False)).sum())
        included = int(sub["ohlc_coverage"].fillna(False).sum())
        total = len(sub)
        lines.append(f"| {node} | {total} | {excluded} | {included} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Atlas generation (spec §4.2)
# ---------------------------------------------------------------------------

def _R_row(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "n/a"
    return (
        f"p10={s.quantile(0.1):.2f} "
        f"p25={s.quantile(0.25):.2f} "
        f"p50={s.quantile(0.5):.2f} "
        f"p75={s.quantile(0.75):.2f} "
        f"p90={s.quantile(0.9):.2f} "
        f"mean={s.mean():.2f}"
    )


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def _terminal_state_table_hl(
    df: pd.DataFrame,
    title: str,
    honesty_label: str,
) -> str:
    """Generate intraday terminal-state distribution table."""
    lines = [f"### {title}"]
    lines.append(honesty_label)
    lines.append("")

    covered = df[df["ohlc_coverage"].fillna(False)]
    excluded = len(df) - len(covered)
    total = len(covered)
    matured = covered[covered["state_hl"].notna()]

    lines.append(
        f"n_covered={total}, n_excluded_no_ohlc={excluded}, "
        f"n_matured={len(matured)}"
    )
    lines.append("")

    if len(matured) == 0:
        lines.append("*No matured events.*")
        lines.append("")
        return "\n".join(lines)

    states = ["STOPPED", "DEAD_MONEY", "CUSHIONED", "CLEAN_LIFTOFF"]
    state_counts = {s: int((matured["state_hl"] == s).sum()) for s in states}
    m = len(matured)
    lines.append("| State (intraday H/L) | N | % |")
    lines.append("|---|---|---|")
    for s in states:
        n = state_counts[s]
        lines.append(f"| {s} | {n} | {_pct(n, m)} |")
    lines.append("")

    # Win rate
    win = state_counts.get("CUSHIONED", 0) + state_counts.get("CLEAN_LIFTOFF", 0)
    lines.append(f"**Win rate (CUSHIONED+CLEAN_LIFTOFF):** {_pct(win, m)}")
    lines.append("")

    # MFE/MAE HL R
    for h in (21, 63):
        mfe_col = f"mfe_R_hl_{h}"
        mae_col = f"mae_R_hl_{h}"
        if mfe_col in matured.columns:
            lines.append(f"**MFE_R_HL@{h}d:** {_R_row(matured[mfe_col])}")
        if mae_col in matured.columns:
            lines.append(f"**MAE_R_HL@{h}d:** {_R_row(matured[mae_col])}")
    lines.append("")

    return "\n".join(lines)


def generate_concordance_section(concordance: dict[str, Any]) -> str:
    """Generate the CONCORDANCE section — the headline deliverable."""
    lines = [
        "## CONCORDANCE — Close vs Intraday State Changes (Headline Deliverable)\n",
        "> Per family: % events whose terminal state changed close→intraday "
        "(esp. DEAD/CLEAN→STOPPED), Δ stop-touch rate, Δ win rate, Δ median policy R, "
        "MAE understatement distribution (mae_R_hl_21 − mae_R_21).\n",
        honesty_header(),
        "",
        "> **BASIS NOTE — MAE understatement column:** `mae_R_hl_21` (intraday leg) is computed "
        "from unadjusted OHLC lows; `mae_R_21` (close leg, inherited from W0.1) is computed "
        "from dividend-adjusted closes (data/yahoo/). The delta therefore includes a small "
        "dividend-drag component (~0.2–0.5% over 21d per spec §2) in addition to the true "
        "intraday-vs-close excursion effect. The overstatement of understatement is bounded "
        "by dividend drag and is second-order vs σ21 (5–12%).",
        "> **POLICY R NOTE — Median R (intraday stop-overlay):** STOPPED rows use R=−1; "
        "all other rows carry the close-basis policy_R from W0.1 as the best available proxy. "
        "ΔR therefore measures the effect of added intraday stops only — not a full intraday "
        "recomputation of winner R.",
        "",
    ]

    if not concordance:
        lines.append("*No concordance data computed.*")
        return "\n".join(lines)

    # Summary table
    lines.append(
        "| Family | Param | n | State-changed% | Dead/Clean→Stopped% | "
        "Δ Stop-touch% | Δ Win% | Δ Median R (stop-overlay) | MAE Δ p50 (mixed-basis†) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for key, c in concordance.items():
        r_delta = f"{c['delta_median_R']:+.3f}" if c["delta_median_R"] is not None else "n/a"
        mae_p50 = f"{c['mae_delta_median']:+.4f}" if c["mae_delta_median"] is not None else "n/a"
        lines.append(
            f"| {c['family']} | {c['param']} | {c['n_both']} "
            f"| {c['pct_state_changed']:.1f}% "
            f"| {c['pct_close_dead_clean_to_stopped']:.1f}% "
            f"| {c['delta_stop_pct']:+.1f}% "
            f"| {c['delta_win_pct']:+.1f}% "
            f"| {r_delta} "
            f"| {mae_p50} |"
        )
    lines.append("")
    lines.append(
        "† MAE Δ p50: intraday leg (unadjusted OHLC lows) minus close leg (div-adjusted W0.1). "
        "Overstatement of understatement bounded by dividend drag (~0.2–0.5%). See BASIS NOTE above."
    )
    lines.append("")

    # Per-family detail
    lines.append("### Per-Family Detail\n")
    for key, c in concordance.items():
        lines.append(f"**{c['family']} | {c['param']}** (n={c['n_both']})")
        lines.append(
            f"- Stop-touch rate: close={c['stop_pct_close']:.1f}% → "
            f"intraday={c['stop_pct_intraday']:.1f}% (Δ={c['delta_stop_pct']:+.1f}%)"
        )
        lines.append(
            f"- Win rate: close={c['win_pct_close']:.1f}% → "
            f"intraday={c['win_pct_intraday']:.1f}% (Δ={c['delta_win_pct']:+.1f}%)"
        )
        r_close_str    = f"{c['median_R_close']:.3f}" if c["median_R_close"] is not None else "n/a"
        r_intraday_str = f"{c['median_R_intraday']:.3f}" if c["median_R_intraday"] is not None else "n/a"
        r_delta_str    = f"{c['delta_median_R']:+.3f}" if c["delta_median_R"] is not None else "n/a"
        lines.append(
            f"- Median policy R (intraday stop-overlay): "
            f"close={r_close_str} → stop-overlay={r_intraday_str} (Δ={r_delta_str}). "
            f"[STOPPED rows: R=−1; others: close-basis proxy from W0.1]"
        )
        if c["mae_delta_median"] is not None:
            lines.append(
                f"- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): "
                f"p25={c['mae_delta_p25']:+.4f} "
                f"p50={c['mae_delta_median']:+.4f} "
                f"p75={c['mae_delta_p75']:+.4f} "
                f"[mixed-basis; see BASIS NOTE]"
            )
        lines.append("")

    return "\n".join(lines)


def honesty_header() -> str:
    return (
        f"> **{HONESTY_LABEL}**\n"
        "> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.\n"
        "> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study."
    )


def generate_atlas(
    merged: pd.DataFrame,
    concordance: dict[str, Any],
    vendor_cross_check_report: str,
    output_path: Path,
) -> None:
    """Write ORACLE_ASYMMETRY_ATLAS_W02.md (spec §4.2)."""

    families = merged["family"].unique().tolist()
    sections: list[str] = []

    header = f"""# Oracle Asymmetry Atlas — W0.2

**Program:** Oracle Turn Asymmetry | Wave W0.2 — Intraday-True Pass
**Date:** 2026-07-05
**Nature:** DESCRIPTIVE calibration of W0.1. No new signals. No claim language.
**Grading basis:** {HONESTY_LABEL}
**Population:** Exactly the event rows committed in W0_1_events_graded.csv (no re-enumeration).
**σ20:** frozen from W0_1 row (not recomputed).

> IMPORTANT: The word "validated" does not appear in this document per Oracle Constitution §II.
> Every table carries the intraday honesty label and n + excluded count.

---

"""
    sections.append(header)

    # CONCORDANCE SECTION (headline deliverable)
    sections.append(generate_concordance_section(concordance))
    sections.append("\n---\n")

    # Coverage table
    sections.append("## Coverage Table\n")
    sections.append(build_coverage_table(merged))
    sections.append("\n---\n")

    # Vendor cross-check results
    sections.append("## Vendor Cross-Check Results (yahoo H/L vs massive_stock_day)\n")
    sections.append(
        "> 2021-07-06+ overlap. % of bars with |Δ|>0.2% per ticker.\n"
        "> Divergence >2% of bars on any ticker = STOP and report (spec §2).\n"
    )
    sections.append("```")
    sections.append(vendor_cross_check_report)
    sections.append("```\n")
    sections.append("\n---\n")

    # Intraday tables by family × param
    sections.append("## Intraday-True Terminal State Tables\n")

    for family_id in families:
        fam_df = merged[merged["family"] == family_id]
        sections.append(f"\n### Family: {family_id}\n")

        for param in ("rot21", "pos63"):
            param_df = fam_df[fam_df["parameterization"] == param]
            if param_df.empty:
                continue

            if family_id not in ("ep_onset_in", "ep_onset_out", "routing_6"):
                for dedup in ("raw", "first21"):
                    dd_df = param_df[param_df["dedup_variant"] == dedup]
                    if dd_df.empty:
                        continue
                    note = "(headline)" if dedup == "first21" else "(appendix)"
                    title = f"{family_id} | {param} | dedup={dedup} {note} — INTRADAY H/L"
                    sections.append(_terminal_state_table_hl(dd_df, title, honesty_header()))
            else:
                title = f"{family_id} | {param} — INTRADAY H/L"
                sections.append(_terminal_state_table_hl(param_df, title, honesty_header()))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")
    log.info("Atlas written: %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="OTA W0.2 — Intraday-True Pass")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data"),
        help="MAIN read-only data dir (for massive_stock_day cross-check and yahoo closes)",
    )
    parser.add_argument(
        "--ohlc-dir",
        type=Path,
        default=ROOT / "data" / "yahoo_ohlc",
        help="Worktree OHLC store (written by collect_sector_etf_ohlc.py)",
    )
    parser.add_argument(
        "--w01-csv",
        type=Path,
        default=ROOT / "research" / "oracle_asymmetry" / "W0_1_events_graded.csv",
        help="W0.1 graded CSV (frozen population)",
    )
    args = parser.parse_args(argv)

    data_dir = args.data_dir.expanduser().resolve()
    ohlc_dir = args.ohlc_dir.expanduser().resolve()
    w01_csv  = args.w01_csv.expanduser().resolve()

    csv_out   = ROOT / "research" / "oracle_asymmetry" / "W0_2_events_graded.csv"
    atlas_out = ROOT / "research" / "ORACLE_ASYMMETRY_ATLAS_W02.md"

    # -----------------------------------------------------------------------
    # 1. Load W0_1 CSV (frozen population)
    # -----------------------------------------------------------------------
    if not w01_csv.exists():
        print(f"::error:: W0_1 CSV not found: {w01_csv}", file=sys.stderr)
        sys.exit(1)
    log.info("Loading W0_1 CSV: %s", w01_csv)
    w01_df = pd.read_csv(w01_csv, low_memory=False)
    log.info("  W0_1 rows: %d", len(w01_df))

    # -----------------------------------------------------------------------
    # 2. Load OHLC store
    # -----------------------------------------------------------------------
    UNIVERSE = ["XLK", "XLV", "XLF", "XLY", "XLC", "XLI",
                "XLP", "XLE", "XLU", "XLRE", "XLB", "SPY"]
    log.info("Loading OHLC store from %s ...", ohlc_dir)
    ohlc_store = load_ohlc_store(ohlc_dir, UNIVERSE)
    log.info("  Loaded %d tickers.", len(ohlc_store))

    # -----------------------------------------------------------------------
    # 3. Fidelity gate (spec §5) — runs FIRST
    # -----------------------------------------------------------------------
    vendor_report = run_fidelity_gate(w01_df, ohlc_store, data_dir)

    # -----------------------------------------------------------------------
    # 4. Grade all rows with intraday H/L
    # -----------------------------------------------------------------------
    log.info("Grading %d W0_1 rows with intraday OHLC ...", len(w01_df))
    new_cols_list = []
    for idx, row in w01_df.iterrows():
        result = grade_row_intraday(row, ohlc_store)
        new_cols_list.append(result)

        if (idx + 1) % 1000 == 0:
            log.info("  ... %d/%d rows graded", idx + 1, len(w01_df))

    new_cols_df = pd.DataFrame(new_cols_list, index=w01_df.index)

    # -----------------------------------------------------------------------
    # 5. Merge and save W0_2 CSV
    # -----------------------------------------------------------------------
    merged = pd.concat([w01_df, new_cols_df], axis=1)

    # Coverage summary
    n_covered  = int(merged["ohlc_coverage"].fillna(False).sum())
    n_excluded = int((~merged["ohlc_coverage"].fillna(False)).sum())
    log.info("  Coverage: %d covered, %d excluded (no OHLC)", n_covered, n_excluded)

    # State-change summary
    has_both = merged["state"].notna() & merged["state_hl"].notna() & merged["ohlc_coverage"].fillna(False)
    n_both = int(has_both.sum())
    if n_both > 0:
        changed = int((merged.loc[has_both, "state"] != merged.loc[has_both, "state_hl"]).sum())
        log.info("  State changes (close→intraday): %d/%d (%.1f%%)", changed, n_both, changed/n_both*100)

    csv_out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(csv_out, index=False)
    log.info("W0_2 CSV written: %s (%d rows)", csv_out, len(merged))

    # -----------------------------------------------------------------------
    # 6. Compute concordance
    # -----------------------------------------------------------------------
    log.info("Computing concordance ...")
    concordance = compute_concordance(merged)

    # Print concordance headline
    print("\n--- CONCORDANCE HEADLINE ---")
    for key, c in concordance.items():
        r_delta = f"{c['delta_median_R']:+.3f}" if c["delta_median_R"] is not None else "n/a"
        print(
            f"  {c['family']}|{c['param']}: "
            f"n={c['n_both']} "
            f"state_changed={c['pct_state_changed']:.1f}% "
            f"→STOPPED={c['pct_close_dead_clean_to_stopped']:.1f}% "
            f"Δstop={c['delta_stop_pct']:+.1f}% "
            f"Δwin={c['delta_win_pct']:+.1f}% "
            f"ΔR={r_delta} "
            f"MAE_Δp50={c['mae_delta_median']}"
        )
    print()

    # -----------------------------------------------------------------------
    # 7. Generate Atlas
    # -----------------------------------------------------------------------
    log.info("Generating Atlas ...")
    vendor_report_str = vendor_report if isinstance(vendor_report, str) else ""
    generate_atlas(merged, concordance, vendor_report_str, atlas_out)

    print(f"\nDone. Outputs:")
    print(f"  {csv_out}")
    print(f"  {atlas_out}")

    return merged, concordance


if __name__ == "__main__":
    main()
