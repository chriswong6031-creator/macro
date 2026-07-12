"""scripts/census_rebalance_days.py — Rebalance Field Guide census (one-shot).

Scans data/breadth/_volume_cache.parquet and data/breadth/updown.parquet
over quarter-end windows and Russell recon days from 2023-06 to present,
and prints a markdown table for each window.

Output:
  research/REBALANCE_FIELD_GUIDE.md

Descriptive census only — no signal claims; verdicts only via pre-registered
rulers (see RLT masterplan §1, RLT-R2, W2 study pre-registration).

SPY 21-session forward return is descriptive-only — it is NOT a signal claim
and NOT pre-registered; it is printed for orientational context only.

Usage:
    python -m scripts.census_rebalance_days
    python -m scripts.census_rebalance_days --root /path/to/repo
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    import pandas as pd
    import numpy as np

    ap = argparse.ArgumentParser(description="Rebalance census one-shot")
    ap.add_argument("--root", type=Path, default=None)
    args = ap.parse_args(argv)
    root = args.root.resolve() if args.root else _REPO_ROOT
    data_dir = root / "data"

    from engine.rebalance_calendar import (
        quarter_end_sessions,
        russell_recon_sessions,
        RECON_OVERRIDES,
    )

    # ── Load data ────────────────────────────────────────────────────────────
    vol_path = data_dir / "breadth" / "_volume_cache.parquet"
    updown_path = data_dir / "breadth" / "updown.parquet"
    closes_path = data_dir / "breadth" / "_closes_cache.parquet"

    print("Loading data...", file=sys.stderr)
    try:
        vol_df = pd.read_parquet(vol_path)
        vol_df.index = pd.DatetimeIndex(vol_df.index)
    except Exception as exc:
        print(f"ERROR: cannot load _volume_cache: {exc}", file=sys.stderr)
        vol_df = pd.DataFrame()

    try:
        updown_df = pd.read_parquet(updown_path)
        updown_df.index = pd.DatetimeIndex(updown_df.index)
    except Exception as exc:
        print(f"WARNING: cannot load updown: {exc}", file=sys.stderr)
        updown_df = pd.DataFrame()

    try:
        closes_df = pd.read_parquet(closes_path)
        closes_df.index = pd.DatetimeIndex(closes_df.index)
    except Exception as exc:
        print(f"WARNING: cannot load closes: {exc}", file=sys.stderr)
        closes_df = pd.DataFrame()

    # ── Compute market total volume series ────────────────────────────────────
    if not vol_df.empty:
        vol_total = vol_df.sum(axis=1).sort_index()
    else:
        vol_total = pd.Series(dtype=float)

    VOL_WINDOW = 20

    def _vol_ratio(d: date) -> str:
        ts = pd.Timestamp(d)
        if vol_total.empty or ts not in vol_total.index:
            return "n/a"
        today_v = vol_total.loc[ts]
        prior = vol_total[vol_total.index < ts].iloc[-VOL_WINDOW:]
        if len(prior) < 5 or prior.median() <= 0:
            return "n/a"
        return f"{today_v / prior.median():.2f}×"

    def _up_share(d: date) -> str:
        if updown_df.empty:
            return "n/a"
        ts = pd.Timestamp(d)
        if ts not in updown_df.index:
            return "n/a"
        row = updown_df.loc[ts]
        uv = float(row.get("up_vol", 0) or 0)
        dv = float(row.get("down_vol", 0) or 0)
        if uv + dv == 0:
            return "n/a"
        return f"{uv / (uv + dv):.2f}"

    def _n_megacap_rvol2(d: date) -> str:
        from engine.rebalance_pulse import MEGACAP_TICKERS, RVOL_SPIKE_THRESHOLD
        if vol_df.empty:
            return "n/a"
        ts = pd.Timestamp(d)
        if ts not in vol_df.index:
            return "n/a"
        count = 0
        for ticker in MEGACAP_TICKERS:
            if ticker not in vol_df.columns:
                continue
            col = vol_df[ticker].sort_index()
            if ts not in col.index:
                continue
            today_v = float(col.loc[ts])
            prior = col[col.index < ts].iloc[-VOL_WINDOW:]
            if len(prior) < 5 or prior.median() <= 0:
                continue
            if today_v / prior.median() >= RVOL_SPIKE_THRESHOLD:
                count += 1
        return str(count)

    def _spy_fwd21(d: date) -> str:
        """SPY next-21-session return — DESCRIPTIVE ONLY, NOT a signal claim."""
        if closes_df.empty or "SPY" not in closes_df.columns:
            return "n/a"
        ts = pd.Timestamp(d)
        if ts not in closes_df.index:
            return "n/a"
        spy = closes_df["SPY"].dropna().sort_index()
        future = spy[spy.index > ts].iloc[:21]
        if len(future) < 10:
            return "n/a"
        entry = float(spy.loc[ts])
        exit_v = float(future.iloc[-1])
        if entry <= 0:
            return "n/a"
        ret = (exit_v / entry - 1) * 100
        return f"{ret:+.1f}%"

    # ── Build rows ────────────────────────────────────────────────────────────
    # Quarter-end days 2023-06 → present
    today = date.today()
    qe_days = [d for d in quarter_end_sessions(2023, today.year) if d <= today]

    # Russell recon days 2023-06 → present
    recon_days = [d for d in russell_recon_sessions(2023, today.year) if d <= today
                  and d >= date(2023, 6, 1)]

    # ── Generate markdown ─────────────────────────────────────────────────────
    lines = [
        "# Rebalance Field Guide",
        "",
        "> **Descriptive census — no signal claims; verdicts only via pre-registered rulers.**",
        "> SPY fwd-21d return is DESCRIPTIVE ONLY (not pre-registered; printed for context).",
        "> Authority: display/context. may_rank=false, may_gate=false, may_size=false.",
        "",
        f"Generated: {today.isoformat()}",
        "",
        "---",
        "",
        "## Quarter-End Windows (2023-06 → present)",
        "",
        "| Date | Market Vol Ratio | Up-Share | N Mega-Cap RVOL≥2× | SPY Fwd-21d (CONTEXT) |",
        "| ---- | ---------------- | -------- | ------------------- | --------------------- |",
    ]
    for d in qe_days:
        lines.append(
            f"| {d.isoformat()} | {_vol_ratio(d)} | {_up_share(d)} | "
            f"{_n_megacap_rvol2(d)} | {_spy_fwd21(d)} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Russell Reconstitution Days (2023-06 → present)",
        "",
        "| Date | Source | Market Vol Ratio | Up-Share | N Mega-Cap RVOL≥2× | SPY Fwd-21d (CONTEXT) |",
        "| ---- | ------ | ---------------- | -------- | ------------------- | --------------------- |",
    ]
    for d in recon_days:
        source = "override" if d.year in RECON_OVERRIDES else "rule"
        lines.append(
            f"| {d.isoformat()} | {source} | {_vol_ratio(d)} | {_up_share(d)} | "
            f"{_n_megacap_rvol2(d)} | {_spy_fwd21(d)} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Notes",
        "",
        "- **Market Vol Ratio**: total market volume on the day ÷ 20-day median.",
        "- **Up-Share**: up-volume / (up-volume + down-volume) from `data/breadth/updown.parquet`",
        "  (available from 2026-05-19 only; earlier dates show `n/a`).",
        "- **N Mega-Cap RVOL≥2×**: count of top-30 names with RVOL20 ≥ 2× on the day.",
        "- **SPY Fwd-21d**: SPY close-to-close return over the 21 sessions starting the day after.",
        "  NOT a signal claim — descriptive context only, from a single non-overlapping window.",
        "- All 'n/a' entries = data absent from the local store.",
        "- This census was produced by `scripts/census_rebalance_days.py` from local parquet stores.",
        "  Production stores on the Mac Studio runner may have more history.",
    ]

    out = "\n".join(lines) + "\n"
    print(out)

    # Write to research/
    out_path = root / "research" / "REBALANCE_FIELD_GUIDE.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out, encoding="utf-8")
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    from lib.procutil import hard_exit
    main()
    hard_exit(0)
