"""scripts/build_analog_library.py — Build the HAR analog library.

Segments the BACKTEST cohort of data/cycle_pattern/state_monthly.parquet into
COMPLETED half-cycles, normalizes each half-cycle, attaches a macro fingerprint,
and writes data/cycle_pattern/analog_library.parquet.

SPAN DEFINITION
  A half-cycle (span) is a maximal consecutive run of rows sharing the same
  `direction` value (up / down) for one entity.  Span boundaries are
  detected by changes in `direction`.  The last span for each entity is
  treated as OPEN (the turn has not yet been observed) and is EXCLUDED from
  the library — only COMPLETED spans (where the direction later changed) are
  included.  This is the leak-prevention boundary per HAR-1 preregistration.

NORMALIZATION
  Elapsed-fraction grid: 10 equally-spaced points from 0 (start of span) to
  1 (end of span).  At each fraction point, the `pos` (oscillator position,
  0-100 scale) value is linearly interpolated from the monthly sequence.
  Stored as norm_pos_0 … norm_pos_9 (value at fraction 0.0, 0.1, … 0.9).
  Amplitude is stored as the max `amp_proxy` across the span (already 0-1
  scale).

MACRO FINGERPRINT
  Era-mean of revision-optimistic regime columns (quad one-hot Q1/Q2/Q3/Q4,
  liquidity expanding/contracting/neutral) plus vol_pctile (if present in
  the lake).  Averaged over all rows of the span.
  revision_optimistic=True because quad/liquidity are not PIT-vintaged
  (P-D5-1), mirroring the hazard model disclosure.

FAMILY MAPPING
  entity_id prefix -> family:
    us_sector  -> us_sector
    country    -> country
    bloc       -> country  (same KM family in hazard panel)
    cn_sector  -> cn_sector

BACKTEST COHORT
  Only rows with hazard_epoch == 'price_c4414dcb' are used.
  LIVE rows (future stamps beyond the available lake window) are not blended.

Output columns in analog_library.parquet:
  span_id        : string, globally unique (entity_id + ':' + YYYYMM of start)
  entity_id      : source entity
  family         : us_sector / country / cn_sector
  direction      : up / down
  start_date     : first month-end of span (Timestamp)
  end_date       : last month-end of span (Timestamp; the turn month)
  realized_dur_m : realized total duration in months (age_m at last row)
  n_rows         : number of monthly rows in the span
  amp_proxy      : max amp_proxy across the span (0-1)
  norm_pos_0 … norm_pos_9 : normalized oscillator trajectory (0-100 scale,
                            interpolated at elapsed fractions 0.0..0.9)
  fp_quad_Q1..fp_quad_Q4  : fraction of span months in each quad bucket
  fp_liq_expanding        : fraction of span months with liquidity=expanding
  fp_liq_contracting      : fraction of span months with liquidity=contracting
  fp_liq_neutral          : fraction of span months with liquidity=neutral
  fp_vol_pctile           : mean vol_pctile over span (NaN when absent)
  revision_optimistic     : always True (macro fingerprint, P-D5-1)

Usage:
  python scripts/build_analog_library.py [--out data/cycle_pattern/analog_library.parquet]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── Paths ──────────────────────────────────────────────────────────────────────
STATE_MONTHLY_PATH = _REPO / "data" / "cycle_pattern" / "state_monthly.parquet"
DEFAULT_OUT = _REPO / "data" / "cycle_pattern" / "analog_library.parquet"

# ── Frozen constants ───────────────────────────────────────────────────────────
HAZARD_EPOCH = "price_c4414dcb"
N_GRID = 10          # elapsed-fraction grid points: 0.0, 0.1, ..., 0.9
GRID_FRACS = [i / N_GRID for i in range(N_GRID)]  # [0.0, 0.1, ..., 0.9]

# Family mapping: entity_id prefix -> hazard family label
_FAMILY_MAP = {
    "us_sector": "us_sector",
    "country": "country",
    "bloc": "country",      # blocs are in the country family in the hazard panel
    "cn_sector": "cn_sector",
}

# Macro regime one-hot columns
_QUAD_CATS = ("Q1", "Q2", "Q3", "Q4")
_LIQ_CATS = ("expanding", "contracting", "neutral")


def _entity_family(entity_id: str) -> str | None:
    prefix = entity_id.split(":")[0]
    return _FAMILY_MAP.get(prefix)


def _normalize_trajectory(pos_vals: np.ndarray) -> np.ndarray:
    """Interpolate oscillator positions to N_GRID elapsed-fraction grid points.

    pos_vals : array of `pos` values in temporal order (length = n_rows >= 1).
    Returns  : array of length N_GRID, values at fractions 0.0, 0.1, ..., 0.9.
    If n_rows == 1, all grid points return that single value.
    """
    n = len(pos_vals)
    if n == 1:
        return np.full(N_GRID, pos_vals[0])
    # Source positions: equally spaced in [0, 1]
    src_fracs = np.linspace(0.0, 1.0, n)
    return np.interp(GRID_FRACS, src_fracs, pos_vals)


def _macro_fingerprint(span_df: pd.DataFrame) -> dict:
    """Compute macro fingerprint as era-mean of regime columns over span rows."""
    n = len(span_df)
    fp: dict = {}

    # Quad one-hot fractions
    if "quad" in span_df.columns:
        for q in _QUAD_CATS:
            fp[f"fp_quad_{q}"] = float((span_df["quad"] == q).sum() / n)
    else:
        for q in _QUAD_CATS:
            fp[f"fp_quad_{q}"] = float("nan")

    # Liquidity fractions
    if "liquidity" in span_df.columns:
        for liq in _LIQ_CATS:
            fp[f"fp_liq_{liq}"] = float((span_df["liquidity"] == liq).sum() / n)
    else:
        for liq in _LIQ_CATS:
            fp[f"fp_liq_{liq}"] = float("nan")

    # vol_pctile mean (NaN when absent or all-NaN)
    if "vol_pctile" in span_df.columns:
        vp = pd.to_numeric(span_df["vol_pctile"], errors="coerce")
        fp["fp_vol_pctile"] = float(vp.mean()) if vp.notna().any() else float("nan")
    else:
        fp["fp_vol_pctile"] = float("nan")

    fp["revision_optimistic"] = True  # quad/liquidity not PIT-vintaged (P-D5-1)
    return fp


def segment_spans(state: pd.DataFrame) -> list[dict]:
    """Extract completed half-cycle spans from the BACKTEST cohort.

    Walk-forward contract: span i (ending at date T) may only be used as an
    analog for queries at date T' > T.  No open spans enter the library.

    Returns a list of dicts, one per completed span.
    """
    # BACKTEST only: hazard_epoch is set
    backtest = state[state["hazard_epoch"] == HAZARD_EPOCH].copy()
    backtest = backtest[backtest["direction"].notna()]
    backtest = backtest.sort_values(["entity_id", "date"]).reset_index(drop=True)

    records: list[dict] = []

    for entity_id, grp in backtest.groupby("entity_id", sort=False):
        family = _entity_family(entity_id)
        if family is None:
            continue  # skip unmapped entity prefixes

        grp = grp.sort_values("date").reset_index(drop=True)
        dirs = grp["direction"].values

        # Detect run boundaries
        run_ids = np.ones(len(dirs), dtype=int)
        for j in range(1, len(dirs)):
            run_ids[j] = run_ids[j - 1] + (1 if dirs[j] != dirs[j - 1] else 0)

        # Last run_id = open span → exclude
        max_run = run_ids[-1]
        for run_id in range(1, max_run):  # excludes max_run (open)
            mask = run_ids == run_id
            span_df = grp[mask].reset_index(drop=True)

            direction = str(span_df["direction"].iloc[0])
            start_date = span_df["date"].iloc[0]
            end_date = span_df["date"].iloc[-1]
            n_rows = len(span_df)

            # Realized duration: age_m at last row
            realized_dur_m = float(span_df["age_m"].iloc[-1]) if pd.notna(
                span_df["age_m"].iloc[-1]) else float(n_rows)

            # Amplitude: max amp_proxy
            amp_proxy = float(span_df["amp_proxy"].dropna().max()) if (
                "amp_proxy" in span_df.columns and span_df["amp_proxy"].notna().any()
            ) else float("nan")

            # Normalized trajectory (pos 0-100)
            pos_vals = span_df["pos"].fillna(50.0).values  # 50 = neutral default
            norm_traj = _normalize_trajectory(pos_vals)

            # Macro fingerprint
            fp = _macro_fingerprint(span_df)

            span_id = f"{entity_id}:{start_date.strftime('%Y%m')}"

            rec: dict = {
                "span_id": span_id,
                "entity_id": entity_id,
                "family": family,
                "direction": direction,
                "start_date": start_date,
                "end_date": end_date,
                "realized_dur_m": realized_dur_m,
                "n_rows": n_rows,
                "amp_proxy": amp_proxy,
            }
            # Grid points
            for i, val in enumerate(norm_traj):
                rec[f"norm_pos_{i}"] = float(val)
            # Fingerprint
            rec.update(fp)

            records.append(rec)

    return records


def build_library(state_path: Path = STATE_MONTHLY_PATH) -> pd.DataFrame:
    """Build and return the completed half-cycle analog library DataFrame."""
    state = pd.read_parquet(state_path)
    records = segment_spans(state)
    lib = pd.DataFrame(records)
    lib = lib.sort_values(["family", "direction", "entity_id", "start_date"]
                         ).reset_index(drop=True)
    return lib


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build HAR analog library")
    ap.add_argument("--state", default=str(STATE_MONTHLY_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    print(f"Loading state_monthly: {args.state}")
    state = pd.read_parquet(args.state)

    print("Segmenting completed half-cycle spans…")
    records = segment_spans(state)
    lib = pd.DataFrame(records)
    lib = lib.sort_values(["family", "direction", "entity_id", "start_date"]
                         ).reset_index(drop=True)

    print(f"Total completed spans: {len(lib)}")
    for fam in ("us_sector", "country", "cn_sector"):
        sub = lib[lib["family"] == fam]
        print(f"  {fam}: {len(sub)} spans "
              f"(up={int((sub['direction']=='up').sum())}, "
              f"down={int((sub['direction']=='down').sum())})")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lib.to_parquet(out_path, index=False)
    print(f"Written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
