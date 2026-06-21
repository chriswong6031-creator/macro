#!/usr/bin/env python3
"""Demonstration: honest trial accounting drops the Deflated Sharpe.

Runs the keystone end-to-end on a fixed-seed synthetic strategy that mirrors a typical
phase0 search: a grid of vol-window x target x cap configs is swept, the BEST config's
Sharpe is reported, and the DSR is asked "is this edge real after multiple testing?".

It shows the gap between:
  * the LOWBALLED literal n_trials a script might hand-write (e.g. "~6 variants"), and
  * the HONEST count the Trial Ledger records by logging every config AT GENERATION.

The honest count yields a strictly larger multiple-testing haircut, so the DSR — the
probability the edge survives selection bias — falls. That fall is the entire point of
P3 in research/SELF_IMPROVING_AI_SUITE.md: it removes the caller's discretion to
understate how many darts were thrown.

Run from the repo root:  python3 -m scripts.trial_ledger_demo
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from engine.trial_ledger import TrialLedger
from engine.validation import deflated_sharpe, dsr_verdict, ret_moments

# A realistic search grid: 6 vol-windows x 4 targets x 3 caps = 72 configs tried.
VOL_WINS = [10, 20, 40, 60, 90, 120]
TARGETS = [0.10, 0.15, 0.20, 0.25]
CAPS = [1.0, 1.5, 2.0]
GRID = [{"vol_win": w, "target": t, "cap": c} for w in VOL_WINS for t in TARGETS for c in CAPS]

# What a hand-written script might *claim* it tried (the lowball that flatters the DSR).
LOWBALLED_N = 6

FAMILY = "demo_voltarget"


def _best_config_returns():
    """A genuinely-decent daily return series standing in for the winning config —
    fixed seed so the demo is deterministic and needs no network/data files."""
    rng = np.random.default_rng(7)
    return pd.Series(rng.normal(0.0009, 0.028, 3500))


def main() -> int:
    sr, skew, kurt, T = ret_moments(_best_config_returns())

    # --- the dishonest path: caller asserts a small N -------------------- #
    low = deflated_sharpe(sr, skew, kurt, T, n_trials=LOWBALLED_N, trading_year=252)

    # --- the honest path: log the WHOLE grid at generation, let N be counted #
    with tempfile.TemporaryDirectory() as td:
        led = TrialLedger(Path(td) / "trial_ledger.jsonl", family=FAMILY)
        added = led.log_grid(GRID, info_cutoff="2026-06-20", source="voltarget_grid")
        # idempotency: re-logging the same grid must not inflate the count
        assert led.log_grid(GRID) == 0
        honest = deflated_sharpe(sr, skew, kurt, T, ledger=led, family=FAMILY, trading_year=252)
        literal_n = led.literal_n()

    print("=" * 72)
    print("TRIAL LEDGER — honest multiple-testing accounting (P3 keystone demo)")
    print("=" * 72)
    print(f"grid actually swept : {len(VOL_WINS)} vol-wins x {len(TARGETS)} targets "
          f"x {len(CAPS)} caps = {len(GRID)} configs")
    print(f"distinct trials logged at generation : {literal_n} (added {added}, re-run added 0)")
    print(f"winning config Sharpe (annual) : {low['sr_annual']}")
    print("-" * 72)
    print(f"{'path':<26}{'n_trials':>10}{'SR0_annual':>14}{'DSR':>8}   verdict")
    print(f"{'LOWBALLED literal':<26}{low['n_trials']:>10}{low['sr0_annual']:>14}"
          f"{low['dsr']:>8}   {dsr_verdict(low['dsr'])}")
    print(f"{'HONEST ledger count':<26}{honest['n_trials']:>10}{honest['sr0_annual']:>14}"
          f"{honest['dsr']:>8}   {dsr_verdict(honest['dsr'])}")
    print("-" * 72)
    drop = round(low["dsr"] - honest["dsr"], 4)
    print(f"DSR fell by {drop} once every dart thrown was counted "
          f"(higher SR0 hurdle = bigger selection-bias haircut).")
    print("This is why N must be COUNTED, not asserted. See "
          "research/SELF_IMPROVING_AI_SUITE.md (P3).")

    # The demo's own assertion — honest accounting must never flatter the result.
    assert honest["dsr"] <= low["dsr"], "honest N should not raise the DSR"
    assert honest["n_trials"] == len(GRID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
