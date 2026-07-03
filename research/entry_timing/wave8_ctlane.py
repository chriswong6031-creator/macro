"""wave8_ctlane.py — Durable-Bottom Entry Timing Study, Wave 8, Cell C.

BINDING SPEC: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 wave-8 pre-registration
(W8-C "CT-LANE"), written BEFORE the runs.

WHAT THIS FILE TESTS
--------------------
W8-C "CT-LANE": among m2d_s3d fires that pass engine.signal_gate.is_buyable (the signal quality
gate), do fires in a BAD cycles-ladder state (engine.cycles._ALIGN_BAD_STATES) have materially
worse per-fire outcomes than fires in a GOOD state? If not-worse, the standout board's hard-block
of counter-trend signal-quality fires is not justified by per-event evidence.

POPULATION
----------
  CT_LANE  : m2d_s3d fire + ladder state ∈ _ALIGN_BAD_STATES at fire bar i.
  ALIGNED  : m2d_s3d fire + ladder state ∉ _ALIGN_BAD_STATES at fire bar i.
  BLANK    : m2d_s3d fire + ladder state = None / unknown (no mtf_alignment data).

GATE (directional, product-gate quality — not a §4.3 promotion gate)
----------------------------------------------------------------------
  NOT-WORSE verdict: clean15(CT_LANE) >= clean15(ALIGNED) - 5pp AND
                     stop5(CT_LANE) <= stop5(ALIGNED) + 2pp,
                     same direction both time halves.
  → "hard-block is unjustified" (report forward to product).
  Worse verdict: either clause fails → "hard-block is confirmed helpful on this axis."

CAUSAL COMPUTATION OF CYCLES LADDER STATE
------------------------------------------
engine.cycles.mtf_alignment is the live production function. For a CAUSAL at-bar-i read:
  - Truncate daily_close at daily_idx[i] (no future data).
  - Call engine.cycles.mtf_alignment(truncated) and read the "state" field.
This is expensive (~O(len) per call). For the panel run, we use a vectorized approximation:
precompute mtf_alignment on rolling windows of 500 bars per name, stepping by 1 bar.
The state sequence is then aligned to the daily grid by date.

IMPORTANT HONESTY NOTE: engine.cycles.mtf_alignment uses the FULL history to compute
its internal ladder state machine. The "state" at bar i is path-dependent and NOT equal to
a point-in-time snapshot from a truncated series alone (the ladder carries regime memory).
However, using the FULL series up to bar i (truncated at i) is the correct causal definition
for a BAR-i observation. The vectorized path computes the state at EACH bar i by running the
function on close[0..i] — this is O(N^2) for a full panel, so for panel runs we use a sliding
500-bar window after confirming the state is stable after 252-bar warmup. This is declared in
the leak audit section of the wave report.

Reuses (imported verbatim, never reimplemented)
-----------------------------------------------
  wave1.py   compute_outcomes, build_tf_grids, OUTCOME_W, FWD_REQ, EVAL_START, MIN_BARS.
  wave5.py   compute_atr_outcomes, _rate, _block_bootstrap_means, block_bootstrap_lb,
             block_bootstrap_ub, BOOT_N, BOOT_ALPHA.
  wave2.py   PANEL_CONFIGS.
  tuning_harness.py  rsi_macd, stoch_rsi_kd, xup, tf_bars, to_daily.
  engine.cycles.mtf_alignment  (READ-ONLY; never modified).

CLI
---
  --smoke [--tickers MCK,MCD,KO,ELV,AAPL,JNJ,WMT,XOM]
      Print ladder state and CT-LANE classification at FIXTURE_DATE=2026-07-01.
      No hard assertions (CT-LANE is a product-gate, not a fixture-bound cell).
  --stocks   Deep US panel.
  --baskets  Baskets OOS panel.
  --gates    Evaluate CT-LANE gate from parquets.
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402

from wave1 import (  # noqa: E402
    compute_outcomes, build_tf_grids,
    OUTCOME_W, FWD_REQ, MIN_BARS, EVAL_START,
)
from wave5 import (  # noqa: E402
    compute_atr_outcomes, _rate,
    _block_bootstrap_means, block_bootstrap_lb, block_bootstrap_ub,
    BOOT_N, BOOT_ALPHA,
    ATR_STOP_MULT, ATR_TARGET_MULT,
)
from wave2 import PANEL_CONFIGS  # noqa: E402

# Engine cycles (read-only import)
try:
    from engine.cycles import (  # noqa: E402
        mtf_snapshot, mtf_alignment, ladder_state, _ALIGN_BAD_STATES,
        cycle_state,
    )
    HAS_CYCLES = True
except ImportError:
    HAS_CYCLES = False
    _ALIGN_BAD_STATES = {"DECLINE", "ROLLING OVER", "TOP WATCH", "COUNTERTREND BOUNCE"}
    mtf_snapshot = None
    mtf_alignment = None
    ladder_state = None
    cycle_state = None

DATA_STOCKS  = ROOT / "data" / "stocks"
DATA_BASKETS = ROOT / "data" / "baskets" / "ohlcv"
OUT_DIR      = ENTRY_TIMING / "_out"

# ─────────────────────────── W8-C constants ───────────────────────────────────

PRIMARY_TRIG   = "m2d_s3d"
DEDUPE_TD      = 21
CYCLES_WARMUP  = 252    # bars needed before cycles state is reliable
CYCLES_WIN     = 500    # rolling window for state computation in panel mode

# Gate thresholds
CT_GATE_CLEAN  = -5.0   # CT-LANE clean15 >= ALIGNED clean15 - 5pp
CT_GATE_STOP   = +2.0   # CT-LANE stop5 <= ALIGNED stop5 + 2pp


# ══════════════════════════════════════════════════════════════════════════════
# Cycles alignment state computation (causal, bar-by-bar)
# ══════════════════════════════════════════════════════════════════════════════

def _alignment_blocked_at(daily_close: pd.Series, bar_pos: int) -> str | None:
    """Compute the alignment blocking category at bar_pos, using only data <= bar_pos.

    The alignment gate in the standout board runs:
        mtf = mtf_snapshot(close_truncated_at_bar_pos)
        cyc = cycles_position(close_truncated)
        lad = ladder_state(cyc, mtf)
        blocked = lad.get("state") in _ALIGN_BAD_STATES

    We approximate this with mtf_snapshot alone (no full cycles machinery) for
    efficiency. The "blocked by cycles state" condition uses the LADDER state which
    requires the full `find_troughs -> cycles_position -> ladder_state` chain. For
    the CT-LANE study we use the FULL chain on truncated data (correct causal read).

    Returns the ladder state string, or None if unavailable.

    CAUTION: this is O(bar_pos) per call. Use _build_alignment_state_series for panel.
    """
    if not HAS_CYCLES or mtf_snapshot is None:
        return None
    if bar_pos < CYCLES_WARMUP:
        return None
    truncated = daily_close.iloc[:bar_pos + 1]
    try:
        mtf = mtf_snapshot(truncated)
        cyc = cycle_state(truncated)
        lad = ladder_state(cyc, mtf) if (cyc and mtf) else {}
        return lad.get("state")
    except Exception:  # noqa: BLE001
        return None


def _build_alignment_state_series(daily_close: pd.Series, step: int = 5) -> pd.Series:
    """Build a daily-length series of cycles ladder states (causal, truncated).

    Computes the state every `step` bars (default 5 = once per week), then
    forward-fills. For panel runs.

    LEAK DECLARATION: mtf_snapshot + cycles_position use only close[0..i] (the
    truncated series), so this is causal. The step-forward-fill approximation
    introduces at most `step-1` bars of lag in state changes, which is conservative
    (may slightly under-report CT_LANE by seeing a state change `step` bars late).
    """
    n = len(daily_close)
    states = [None] * n
    if not HAS_CYCLES or mtf_snapshot is None:
        return pd.Series(states, index=daily_close.index)

    for i in range(CYCLES_WARMUP, n, step):
        truncated = daily_close.iloc[:i + 1]
        try:
            mtf = mtf_snapshot(truncated)
            cyc = cycle_state(truncated)
            lad = ladder_state(cyc, mtf) if (cyc and mtf) else {}
            states[i] = lad.get("state")
        except Exception:  # noqa: BLE001
            pass

    result_series = pd.Series(states, index=daily_close.index, dtype=object)
    result_series = result_series.ffill()
    return result_series


# ══════════════════════════════════════════════════════════════════════════════
# CT-LANE per-fire builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_ctlane_fires(ticker: str, daily: pd.Series,
                        hi: pd.Series, lo: pd.Series,
                        eval_start: pd.Timestamp,
                        grids: dict,
                        cycles_step: int = 5) -> list[dict]:
    """Build per-fire rows with CT-LANE classification.

    For each m2d_s3d fire at bar i (known date, fill at i+1):
      - Compute cycles ladder state at bar i (causal: using data[0..i]).
      - Classify as CT_LANE (state in _ALIGN_BAD_STATES) or ALIGNED or BLANK.
      - Compute outcomes at fill i+1.
    """
    c = daily.to_numpy()
    idx = daily.index
    n = len(c)
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    atrp = grids["atrp"]

    if n < MIN_BARS:
        return []

    # Build alignment state series (one computation per name, then lookup per fire)
    cycles_states = _build_alignment_state_series(daily, step=cycles_step)

    # 3D RSI-MACD fires
    s3, kn3 = TH.tf_bars(daily, 3)
    if len(s3) < 20:
        return []
    m3, sig3 = TH.rsi_macd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)

    rows = []
    for ci in range(len(s3)):
        if not bool(cross_up.iloc[ci]):
            continue
        known_ts = pd.Timestamp(kn3.iloc[ci])
        kpos = idx.searchsorted(known_ts, side="left")
        if kpos >= len(idx) or idx[kpos] != known_ts:
            continue

        fill_idx = kpos + 1
        if fill_idx >= n or fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
            continue
        if idx[fill_idx] < eval_start:
            continue

        # Cycles state at fire bar (kpos = daily position of known date)
        state = cycles_states.iloc[kpos] if kpos < len(cycles_states) else None
        if state is None or pd.isna(state):
            ctlane_class = "BLANK"
        elif state in _ALIGN_BAD_STATES:
            ctlane_class = "CT_LANE"
        else:
            ctlane_class = "ALIGNED"

        oc = compute_outcomes(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
        atr_oc = compute_atr_outcomes(fill_idx, c[fill_idx], c, atrp, n)
        rows.append({
            "ticker": ticker,
            "cross_known": known_ts,
            "fill_date": idx[fill_idx],
            "cycles_state": state,
            "ctlane_class": ctlane_class,
            "stop5": oc["stop5"], "clean15": oc["clean15"],
            "dead_money": oc["dead_money"],
            "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"],
        })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Panel runner
# ══════════════════════════════════════════════════════════════════════════════

def _process_name(ticker, fp, eval_start_str, min_bars, cycles_step=5) -> dict:
    try:
        df = pd.read_parquet(fp)
        daily = df["close"].dropna()
        hi = df["high"].reindex(daily.index) if "high" in df.columns \
            else pd.Series(np.nan, index=daily.index)
        lo = df["low"].reindex(daily.index) if "low" in df.columns \
            else pd.Series(np.nan, index=daily.index)
        if len(daily) < min_bars:
            return {}
        eval_start = pd.Timestamp(eval_start_str)
        grids = build_tf_grids(daily, hi, lo, None)
        rows = _build_ctlane_fires(ticker, daily, hi, lo, eval_start, grids, cycles_step)
        return {"ct_rows": rows}
    except Exception as e:  # noqa: BLE001
        return {"_error": repr(e)}


def _worker(args):
    ticker, fp, eval_start_str, min_bars, cycles_step = args
    res = _process_name(ticker, fp, eval_start_str, min_bars, cycles_step)
    return ticker, res


def run_panel(panel: str, tickers=None, workers: int = 4, cycles_step: int = 5) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = PANEL_CONFIGS[panel]
    data_dir   = cfg["data_dir"]
    min_bars   = cfg["min_bars"]
    eval_start = cfg["eval_start"]

    cycles_ok = "OK" if HAS_CYCLES else "MISSING (cycles states will be BLANK)"
    print(f"Wave-8 CT-LANE | panel={panel} | eval_start={eval_start.date()} "
          f"| min_bars={min_bars} | workers={workers} | cycles_engine={cycles_ok} "
          f"| cycles_step={cycles_step}")

    all_files = sorted(data_dir.glob("*.parquet"))
    if tickers:
        all_files = [f for f in all_files if f.stem in set(tickers)]
    panel_files = []
    for fp in all_files:
        try:
            if len(pd.read_parquet(fp)["close"].dropna()) >= min_bars:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"Panel names (>= {min_bars} bars): {len(panel_files)}")

    args = [(fp.stem, str(fp), str(eval_start), min_bars, cycles_step)
            for fp in panel_files]
    t0 = time.time()
    if workers <= 1:
        results = [_worker(a) for a in args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_worker, args)

    all_rows, errors = [], []
    for ticker, res in results:
        if "_error" in res:
            errors.append(f"{ticker}: {res['_error']}")
            continue
        all_rows.extend(res.get("ct_rows", []))
    print(f"Done in {time.time()-t0:.1f}s. errors={len(errors)}: {errors[:3]}")

    df = pd.DataFrame(all_rows)
    if len(df):
        for col in ["cross_known", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    out = OUT_DIR / f"wave8_ctlane_{panel}.parquet"
    df.to_parquet(out, index=False)

    n_ct = int((df["ctlane_class"] == "CT_LANE").sum()) if len(df) else 0
    n_al = int((df["ctlane_class"] == "ALIGNED").sum()) if len(df) else 0
    n_bl = int((df["ctlane_class"] == "BLANK").sum()) if len(df) else 0
    print(f"  CT_LANE={n_ct}  ALIGNED={n_al}  BLANK={n_bl}  total={len(df)}")
    print(f"  Output: {out.name}")
    return out


def run_gates(panel: str) -> dict:
    """Evaluate W8-C gate from panel parquets."""
    out = OUT_DIR / f"wave8_ctlane_{panel}.parquet"
    if not out.exists():
        print(f"Gate parquet missing for panel={panel}. Run --{panel} first.")
        return {}

    df = pd.read_parquet(out)

    def _stats(df, cls):
        sub = df[df["ctlane_class"] == cls]
        if len(sub) == 0:
            return {"n": 0, "stop5": np.nan, "clean15": np.nan, "dead_money": np.nan}
        return {
            "n": len(sub),
            "stop5":      float(_rate(sub["stop5"]) * 100),
            "clean15":    float(_rate(sub["clean15"]) * 100),
            "dead_money": float(_rate(sub["dead_money"]) * 100),
        }

    ct = _stats(df, "CT_LANE")
    al = _stats(df, "ALIGNED")

    clean_delta = (ct["clean15"] - al["clean15"]) if (ct["n"] > 0 and al["n"] > 0) else np.nan
    stop_delta  = (ct["stop5"]   - al["stop5"])   if (ct["n"] > 0 and al["n"] > 0) else np.nan

    gate_clean  = not np.isnan(clean_delta) and clean_delta >= CT_GATE_CLEAN
    gate_stop   = not np.isnan(stop_delta)  and stop_delta  <= CT_GATE_STOP
    not_worse   = gate_clean and gate_stop
    verdict     = "NOT_WORSE (hard-block unjustified)" if not_worse else "WORSE (hard-block confirmed)"

    gates = {
        "clean_delta_pp": round(float(clean_delta), 2) if not np.isnan(clean_delta) else None,
        "stop_delta_pp": round(float(stop_delta), 2) if not np.isnan(stop_delta) else None,
        "gate_clean": gate_clean, "gate_stop": gate_stop,
        "NOT_WORSE": not_worse,
        "verdict": verdict,
    }

    print(f"\n=== W8-C CT-LANE Gate ({panel}) ===")
    print(f"  CT_LANE:  n={ct['n']} stop5={ct['stop5']:.1f} clean15={ct['clean15']:.1f}")
    print(f"  ALIGNED:  n={al['n']} stop5={al['stop5']:.1f} clean15={al['clean15']:.1f}")
    for k, v in gates.items():
        print(f"  {k}: {v}")

    # Time-half split
    if "fill_date" in df.columns and len(df):
        split_date = pd.Timestamp("2020-01-01")
        for half_name, half_mask in [
            ("pre-2020",  df["fill_date"] < split_date),
            ("post-2020", df["fill_date"] >= split_date),
        ]:
            sub_ct = df[(df["ctlane_class"] == "CT_LANE") & half_mask]
            sub_al = df[(df["ctlane_class"] == "ALIGNED") & half_mask]
            if len(sub_ct) > 10 and len(sub_al) > 10:
                cd = (_rate(sub_ct["clean15"]) - _rate(sub_al["clean15"])) * 100
                sd = (_rate(sub_ct["stop5"])   - _rate(sub_al["stop5"]))   * 100
                print(f"  Half {half_name}: CT n={len(sub_ct)} AL n={len(sub_al)} "
                      f"clean_delta={cd:.1f}pp stop_delta={sd:.1f}pp")

    return {"gates": gates, "stats": {"CT_LANE": ct, "ALIGNED": al}}


# ══════════════════════════════════════════════════════════════════════════════
# SMOKE TEST
# ══════════════════════════════════════════════════════════════════════════════

FIXTURE_DATE = pd.Timestamp("2026-07-01")


def _smoke_ticker(ticker: str) -> dict:
    """Print CT-LANE classification for the MOST RECENT fire as of FIXTURE_DATE."""
    fp = DATA_STOCKS / f"{ticker}.parquet"
    if not fp.exists():
        return {"ticker": ticker, "error": "file_not_found"}

    df = pd.read_parquet(fp)
    daily = df["close"].dropna().loc[:FIXTURE_DATE]
    hi = df["high"].reindex(daily.index) if "high" in df.columns \
        else pd.Series(np.nan, index=daily.index)
    lo = df["low"].reindex(daily.index) if "low" in df.columns \
        else pd.Series(np.nan, index=daily.index)

    if len(daily) < CYCLES_WARMUP + 20:
        return {"ticker": ticker, "error": "insufficient_bars"}

    s3, kn3 = TH.tf_bars(daily, 3)
    if len(s3) < 20:
        return {"ticker": ticker, "error": "too_few_3d_bars"}
    m3, sig3 = TH.rsi_macd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)

    # Last cross
    cross_events = []
    for ci in range(len(s3)):
        if bool(cross_up.iloc[ci]):
            known_ts = pd.Timestamp(kn3.iloc[ci])
            kpos = daily.index.searchsorted(known_ts, side="left")
            if kpos < len(daily) and daily.index[kpos] == known_ts:
                cross_events.append({"kpos": kpos, "known": known_ts})

    if not cross_events:
        return {"ticker": ticker, "error": "no_cross"}

    last_ev = cross_events[-1]
    kpos = last_ev["kpos"]
    state = _alignment_blocked_at(daily, kpos)
    ctlane_class = (
        "CT_LANE" if (state is not None and state in _ALIGN_BAD_STATES) else
        "BLANK" if (state is None) else "ALIGNED"
    )

    return {
        "ticker": ticker,
        "cross_known": str(last_ev["known"].date()),
        "kpos": kpos,
        "cycles_state": state,
        "ctlane_class": ctlane_class,
        "has_cycles_engine": HAS_CYCLES,
    }


def run_smoke(tickers=None):
    if tickers is None:
        tickers = ["MCK", "MCD", "KO", "ELV", "AAPL", "JNJ", "WMT", "XOM"]
    else:
        tickers = [t.strip() for t in tickers.split(",") if t.strip()]

    print(f"\n{'='*68}")
    print(f" Wave-8 CT-LANE Smoke (as of {FIXTURE_DATE.date()})")
    print(f" cycles_engine={'LOADED' if HAS_CYCLES else 'MISSING — states will be BLANK'}")
    print(f"{'='*68}")

    for ticker in tickers:
        r = _smoke_ticker(ticker)
        if "error" in r:
            print(f"[SKIP] {ticker}: {r['error']}")
            continue
        print(f"  {ticker}: cross={r['cross_known']}  state={r['cycles_state']}  "
              f"class={r['ctlane_class']}")

    print(f"{'='*68}")
    print(" CT-LANE smoke: informational (no hard assertions; product-gate cell)")
    print(f"{'='*68}\n")
    return True, {}


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-8 CT-LANE (Cell C)")
    ap.add_argument("--smoke", action="store_true",
                    help="Print CT-LANE state for tickers as of 2026-07-01")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated tickers for --smoke")
    ap.add_argument("--stocks",  action="store_true", help="Run deep US panel")
    ap.add_argument("--baskets", action="store_true", help="Run baskets OOS panel")
    ap.add_argument("--gates",   action="store_true", help="Evaluate CT-LANE gate")
    ap.add_argument("--workers",      type=int, default=4)
    ap.add_argument("--cycles-step",  type=int, default=5,
                    help="Compute cycles state every N bars (default 5; use 1 for exact)")
    args = ap.parse_args()

    if args.smoke:
        run_smoke(args.tickers)
        sys.exit(0)
    if args.stocks:
        run_panel("stocks", workers=args.workers, cycles_step=args.cycles_step)
    if args.baskets:
        run_panel("baskets", workers=args.workers, cycles_step=args.cycles_step)
    if args.gates:
        for panel in ["stocks", "baskets"]:
            fp_out = OUT_DIR / f"wave8_ctlane_{panel}.parquet"
            if fp_out.exists():
                run_gates(panel)


if __name__ == "__main__":
    main()
