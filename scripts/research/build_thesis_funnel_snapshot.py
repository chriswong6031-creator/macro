"""LT-4 Thesis Funnel Snapshot — per-ticker state snapshot.

Program: LT External Foundation — LT-4 Thesis Funnel Shadow.
Reference: research/long_hold/LT_EXTERNAL_FOUNDATION_ADJUDICATION.md §3 LT-4.
Ruling: LH-R2 (transparent AND-gate; no composite, no behavioral surface).

DISPLAY-ONLY. This script computes the thesis funnel state for every ticker in
the current fundamentals universe and writes a research snapshot.  The output
is for human inspection and longitudinal population tracking — it MUST NOT
feed board ordering, alert triage, top-setups gates, or push floor (LH-R1).

Output:
  data/research/thesis_funnel_states.parquet
  data/research/thesis_funnel_states_manifest.json

Synapse: config/synapse.yml
  tier: display
  horizon_role: hold_thesis
  fdr_family: long_hold
  scored_path_surfaces: []

State enum (EXACTLY these three values, no others):
  not_eligible           — survival gate failed (dilution / moat falsifier / solvency / coverage)
  watch_for_thesis       — survival gate passed, but not meeting candidate criteria yet
  thesis_candidate_shadow — survival pass + Piotroski F >= 6 + not dilutive cap allocation

Timing:
  Runtime is O(seconds) because all parquets are loaded once and the state
  computation for each ticker is in-memory (pure function with no I/O).
  The main bottleneck is parquet I/O at startup.

Usage:
    python scripts/research/build_thesis_funnel_snapshot.py
    python scripts/research/build_thesis_funnel_snapshot.py --dry-run
    python scripts/research/build_thesis_funnel_snapshot.py --smoke  # first 200 tickers
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_EDGAR = _DATA / "edgar"
_OUT_PARQUET = _DATA / "research" / "thesis_funnel_states.parquet"
_OUT_MANIFEST = _DATA / "research" / "thesis_funnel_states_manifest.json"

# ---------------------------------------------------------------------------
# Schema version (bump on any breaking change to the output columns)
# ---------------------------------------------------------------------------
_SCHEMA_VERSION = "thesis_funnel_states.v1"


def _load_parquet_safe(path: Path) -> pd.DataFrame | None:
    """Load a parquet; return None on any error (fail-open)."""
    if not path.exists():
        log.warning("build_thesis_funnel_snapshot: %s not found", path)
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_thesis_funnel_snapshot: cannot load %s: %s", path, exc)
        return None


def _build(
    tickers: list[str],
    statements_df: pd.DataFrame | None,
    fundamentals_panel_df: pd.DataFrame | None,
    quarterly_df: pd.DataFrame | None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Build per-ticker funnel state rows.

    Reuses the engines already imported by stock_fundamentals.panels() but
    drives them directly here for an off-pipeline standalone run.

    Returns a DataFrame with columns:
      ticker, as_of, state, state_reason,
      s1_dilution_fired, s1_dilution_value,
      s2_moat_falsifier_fired, s2_sensors_fired,
      s3_solvency_fired, s3_altman_z,
      s4_coverage_fired, s4_n_computable,
      piotroski_score, piotroski_of,
      capital_allocation_delta,
      _display_only, _horizon_role, _version
    """
    from engine.moat_falsifiers import (  # noqa: PLC0415
        compute_moat_falsifiers, compute_base_rates,
    )
    from engine.capital_allocation import compute_capital_allocation  # noqa: PLC0415
    from engine.thesis_funnel import compute_thesis_funnel  # noqa: PLC0415
    from engine.stock_fundamentals import _load_statements, _multiyear, _piotroski  # noqa: PLC0415

    statements_map = _load_statements()  # availability-gated by _load_statements

    # Pre-compute moat base rates once for the whole universe
    moat_base_rates: dict = {}
    if statements_df is not None and not statements_df.empty:
        try:
            moat_base_rates = compute_base_rates(statements_df)
        except Exception as exc:  # noqa: BLE001
            log.warning("build_thesis_funnel_snapshot: base rates failed: %s", exc)

    as_of = str(date.today())
    rows_out: list[dict[str, Any]] = []

    for ticker in tickers:
        try:
            # ---- Altman Z + Piotroski (from _multiyear / _piotroski) ----
            stmt_rows = statements_map.get(ticker) or []
            my = _multiyear(stmt_rows, None)  # mktcap None → approx Altman but ok for display
            altman_block = (my or {}).get("altman") or {}
            altman_z_val = altman_block.get("z")
            altman_approx = bool(altman_block.get("approx", False))

            pio_block = _piotroski(stmt_rows) or {}
            pio_score = pio_block.get("score")
            pio_of = pio_block.get("of")

            # ---- Moat falsifiers ----
            mf_result = None
            if statements_df is not None and not statements_df.empty:
                try:
                    mf_result = compute_moat_falsifiers(
                        ticker, statements_df, base_rates=moat_base_rates,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.debug("thesis_funnel snapshot: moat_falsifiers failed for %s: %s", ticker, exc)

            # ---- Capital allocation ----
            ca_result: dict[str, Any] = {}
            if (fundamentals_panel_df is not None and not fundamentals_panel_df.empty):
                try:
                    ca_result = compute_capital_allocation(
                        ticker,
                        quarterly_df if quarterly_df is not None else pd.DataFrame(),
                        fundamentals_panel_df,
                        statements_df=statements_df,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.debug("thesis_funnel snapshot: capital_allocation failed for %s: %s", ticker, exc)

            shares_yoy = ca_result.get("shares_yoy_change_pct")
            cap_delta = ca_result.get("capital_allocation_delta")

            # ---- Thesis funnel ----
            funnel = compute_thesis_funnel(
                ticker,
                altman_z=altman_z_val,
                altman_approx=altman_approx,
                moat_falsifiers_result=mf_result,
                shares_yoy_change_pct=shares_yoy,
                capital_allocation_delta=cap_delta,
                piotroski_score=pio_score,
                piotroski_of=pio_of,
            )

            flags = funnel.get("flags") or {}
            s1 = flags.get("s1_dilution") or {}
            s2 = flags.get("s2_moat_falsifier") or {}
            s3 = flags.get("s3_solvency") or {}
            s4 = flags.get("s4_coverage") or {}

            row: dict[str, Any] = {
                "ticker": ticker,
                "as_of": as_of,
                "state": funnel["state"],
                "state_reason": funnel.get("state_reason", ""),
                "s1_dilution_fired": s1.get("fired"),
                "s1_dilution_value": s1.get("value"),
                "s2_moat_falsifier_fired": s2.get("fired"),
                "s2_sensors_fired": json.dumps(s2.get("sensors_fired") or []),
                "s3_solvency_fired": s3.get("fired"),
                "s3_altman_z": s3.get("value"),
                "s3_altman_approx": s3.get("approx", False),
                "s4_coverage_fired": s4.get("fired"),
                "s4_n_computable": s4.get("n_computable"),
                "piotroski_score": pio_score,
                "piotroski_of": pio_of,
                "capital_allocation_delta": cap_delta,
                "_display_only": True,
                "_horizon_role": "hold_thesis",
                "_version": "v1",
            }
            rows_out.append(row)

        except Exception as exc:  # noqa: BLE001
            log.warning("build_thesis_funnel_snapshot: skipped %s: %s", ticker, exc)
            rows_out.append({
                "ticker": ticker,
                "as_of": as_of,
                "state": "unavailable",
                "state_reason": f"exception: {exc}",
                "_display_only": True,
                "_horizon_role": "hold_thesis",
                "_version": "v1",
            })

    if not rows_out:
        return pd.DataFrame()

    df = pd.DataFrame(rows_out)
    return df


def _write_manifest(df: pd.DataFrame, elapsed: float) -> dict[str, Any]:
    """Write manifest JSON and return it."""
    if df.empty:
        state_counts: dict[str, int] = {}
    else:
        state_counts = {
            str(k): int(v)
            for k, v in df["state"].value_counts().to_dict().items()
        }

    manifest: dict[str, Any] = {
        "schema": _SCHEMA_VERSION,
        "as_of": str(date.today()),
        "n_tickers": int(len(df)),
        "state_counts": state_counts,
        "elapsed_seconds": round(elapsed, 2),
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
        "notes": (
            "LT-4 thesis funnel shadow snapshot. Display-only; no behavioral authority. "
            "Gate = survival conjunction only (s1 dilution, s2 moat falsifiers, "
            "s3 solvency, s4 coverage). Study context: ED-7 descriptive pass "
            "RBC=0.041 is TINY; SUE wrong-sign at the trap ruler "
            "(see EXPECT_DRIFT_RULER_P_RESULTS.md) — explicitly NOT a gate input. "
            "Ceiling = thesis_candidate_shadow (W3-locked; no active_thesis)."
        ),
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build thesis funnel state snapshot")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output files")
    parser.add_argument("--smoke", action="store_true",
                        help="First 200 tickers only (fast smoke-test)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    t0 = time.time()
    log.info("build_thesis_funnel_snapshot: loading parquets …")

    statements_df = _load_parquet_safe(_EDGAR / "statements.parquet")
    fundamentals_panel_df = _load_parquet_safe(_EDGAR / "fundamentals_panel.parquet")
    quarterly_df = _load_parquet_safe(_EDGAR / "statements_quarterly.parquet")

    # Discover ticker universe from fundamentals_panel
    if fundamentals_panel_df is not None and not fundamentals_panel_df.empty and "ticker" in fundamentals_panel_df.columns:
        all_tickers = sorted(fundamentals_panel_df["ticker"].dropna().astype(str).unique().tolist())
    elif statements_df is not None and not statements_df.empty and "ticker" in statements_df.columns:
        all_tickers = sorted(statements_df["ticker"].dropna().astype(str).unique().tolist())
    else:
        log.error("build_thesis_funnel_snapshot: no universe found — parquets missing or empty")
        return 1

    if args.smoke:
        tickers = all_tickers[:200]
        log.info("build_thesis_funnel_snapshot: smoke mode — first %d tickers", len(tickers))
    else:
        tickers = all_tickers
        log.info("build_thesis_funnel_snapshot: full universe — %d tickers", len(tickers))

    df = _build(
        tickers,
        statements_df=statements_df,
        fundamentals_panel_df=fundamentals_panel_df,
        quarterly_df=quarterly_df,
    )

    elapsed = time.time() - t0

    # ---- State counts summary ----
    if not df.empty and "state" in df.columns:
        counts = df["state"].value_counts()
        log.info("build_thesis_funnel_snapshot: state counts:")
        for state, n in counts.items():
            log.info("  %-30s  %d", state, n)
    else:
        log.warning("build_thesis_funnel_snapshot: result DataFrame is empty")

    log.info("build_thesis_funnel_snapshot: elapsed %.1fs for %d tickers", elapsed, len(tickers))

    if args.dry_run:
        log.info("build_thesis_funnel_snapshot: --dry-run; skipping file writes")
        return 0

    if df.empty:
        log.error("build_thesis_funnel_snapshot: nothing to write — aborting")
        return 1

    # Ensure output directory exists
    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    log.info("build_thesis_funnel_snapshot: writing %s", _OUT_PARQUET)
    df.to_parquet(_OUT_PARQUET, index=False)

    manifest = _write_manifest(df, elapsed)
    log.info("build_thesis_funnel_snapshot: writing %s", _OUT_MANIFEST)
    _OUT_MANIFEST.write_text(json.dumps(manifest, indent=2))

    # Print counts table to stdout for PR body
    print("\n=== THESIS FUNNEL STATE COUNTS ===")
    if "state" in df.columns:
        counts = df["state"].value_counts()
        for state, n in counts.items():
            print(f"  {state:<35}  {n}")
        print(f"  {'TOTAL':<35}  {len(df)}")
    print(f"\n  elapsed: {elapsed:.1f}s  ({len(tickers)} tickers)")
    print(f"  as_of: {date.today()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
