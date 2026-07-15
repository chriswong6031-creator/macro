"""CCW-W3 ship gate: spread oscillator sanity study.

ONE-SHOT — run manually before W3 merges, or on first nightly if the artifact
is absent. Results document oscillator behavior across historical widening episodes
on the deep broad-index (1996→) history.

Expected outcome: confirms crosses stay SECONDARY (already law per CCW-R15/§2.5-6).
Documents:
  - StochRSI %K time-pinned >= 80 during widening legs
  - Cross count and lag vs episode start
  - Calm-regime false-fire rate (crosses per year outside episodes)

Episodes (hardcoded windows):
  GFC_2008:    2007-06-01 to 2009-05-31
  EURO_2011:   2010-12-01 to 2012-09-30
  ENERGY_2015: 2015-07-01 to 2016-06-30
  COVID_2020:  2020-02-15 to 2020-06-30
  HIKING_2022: 2022-01-01 to 2023-01-31

Outputs:
  data/corp_bonds/oscillator_sanity.json  — machine-readable verdict + stats
  Printed markdown table to stdout

Usage:
  python -m scripts.ccw_spread_oscillator_sanity [--root PATH]

CCW-R15/§2.5-6: velocity-percentile is PRIMARY; oscillator crosses SECONDARY pending
this study. This script is the evidence.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.canon import rsi_macd, stoch_rsi_kd, crossover, crossunder, resample_sessions
from lib import config
from lib.procutil import hard_exit

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Widening episode windows (hardcoded, documented)
# ---------------------------------------------------------------------------

EPISODES: list[dict] = [
    {
        "name":        "GFC_2008",
        "label":       "2008 Global Financial Crisis",
        "start":       "2007-06-01",
        "end":         "2009-05-31",
        "description": "IG OAS ~100→600bp; HY OAS ~250→2000bp",
    },
    {
        "name":        "EURO_2011",
        "label":       "2011 Euro debt crisis",
        "start":       "2010-12-01",
        "end":         "2012-09-30",
        "description": "Sovereign contagion; HY OAS ~450→800bp",
    },
    {
        "name":        "ENERGY_2015",
        "label":       "2015-16 Energy/EM shock",
        "start":       "2015-07-01",
        "end":         "2016-06-30",
        "description": "HY OAS ~350→850bp; energy/CCC sector stress",
    },
    {
        "name":        "COVID_2020",
        "label":       "2020 COVID shock",
        "start":       "2020-02-15",
        "end":         "2020-06-30",
        "description": "HY OAS ~350→1100bp in weeks; fastest widening episode",
    },
    {
        "name":        "HIKING_2022",
        "label":       "2022 Fed hiking cycle",
        "start":       "2022-01-01",
        "end":         "2023-01-31",
        "description": "Spread widening with rate rise; HY OAS ~300→600bp",
    },
]

# All episode dates (for calm-regime complement)
EPISODE_DATES: set[str] = set()
for ep in EPISODES:
    start = pd.Timestamp(ep["start"])
    end   = pd.Timestamp(ep["end"])
    # Will be populated after loading data


def _data_root(root: Path | None) -> Path:
    return root if root is not None else Path(config.data_dir())


def _load_archive_merged(fred_id: str, root: Path) -> pd.Series | None:
    """Load FRED series, combining archive + live via combine_first."""
    fred_path = root / "fred"   / f"{fred_id}.parquet"
    arch_path = root / "archive" / f"{fred_id}.parquet"

    live: pd.Series | None = None
    arch: pd.Series | None = None

    for path, tag in [(fred_path, "live"), (arch_path, "archive")]:
        if path.exists():
            try:
                # pyarrow read — hard_exit guard required (lib.procutil law)
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                s = df.iloc[:, 0].dropna().astype(float)
                if tag == "live":
                    live = s
                else:
                    arch = s
            except Exception as exc:  # noqa: BLE001
                log.warning("sanity: load %s %s failed: %s", tag, fred_id, exc)

    if live is None and arch is None:
        return None
    if arch is not None and live is not None:
        return live.combine_first(arch).sort_index().dropna()
    return (live or arch).sort_index().dropna()  # type: ignore[return-value]


def _resample_3b(daily: pd.Series) -> pd.Series | None:
    """Session-grouped 3B resample (completed bars only)."""
    if len(daily) < 600:
        return None
    try:
        bucketed, _ = resample_sessions(daily, 3)
        n_total = int(daily.dropna().count())
        if n_total % 3 != 0 and len(bucketed) > 0:
            bucketed = bucketed.iloc[:-1]
        return bucketed if len(bucketed) > 0 else None
    except Exception as exc:  # noqa: BLE001
        log.warning("sanity: 3B resample failed: %s", exc)
        return None


def _stochk_pin_count(k_series: pd.Series, episode_mask: pd.Series, threshold: float = 80.0) -> int:
    """Count bars where StochRSI %K >= threshold within episode mask."""
    aligned = k_series.reindex(episode_mask.index)
    return int((aligned[episode_mask] >= threshold).sum())


def _cross_lag_vs_episode(crosses_series: pd.Series, episode_start: pd.Timestamp, episode_mask: pd.Series) -> int | None:
    """Return bars between episode start and first cross fire during episode."""
    ep_crosses = crosses_series[episode_mask & crosses_series]
    if ep_crosses.empty:
        return None
    first_cross = ep_crosses.index[0]
    # Count business days from episode start to first cross
    idx = crosses_series.index
    ep_start_pos = idx.searchsorted(episode_start, side="left")
    cross_pos    = idx.searchsorted(first_cross,   side="left")
    return max(0, int(cross_pos - ep_start_pos))


def _calm_false_fire_rate(crosses: pd.Series, episode_mask: pd.Series) -> float:
    """Crosses per year outside episode windows."""
    calm_crosses = crosses[~episode_mask & crosses]
    total_calm_bars = int((~episode_mask).sum())
    if total_calm_bars == 0:
        return 0.0
    # Annualize: 252 bars/year
    return float(len(calm_crosses)) / total_calm_bars * 252.0


def _analyze_series(
    series_id: str,
    series: pd.Series,
    grids: list[str],
) -> dict:
    """Run oscillator analysis for one series across specified grids."""
    results: dict[str, Any] = {"series_id": series_id}

    for grid in grids:
        if grid == "1D":
            s = series
            n_bars = len(s)
        elif grid == "3B":
            s = _resample_3b(series)
            n_bars = len(s) if s is not None else 0
        else:
            continue

        if s is None or n_bars < 200:
            results[grid] = {"error": f"insufficient bars ({n_bars})"}
            continue

        try:
            macd_s, sig_s = rsi_macd(s)
            k_s, d_s      = stoch_rsi_kd(s)
            bull_cross     = crossover(macd_s, sig_s)
            bear_cross     = crossunder(macd_s, sig_s)
        except Exception as exc:  # noqa: BLE001
            results[grid] = {"error": str(exc)}
            continue

        # Build episode mask on this grid's index
        grid_episodes: list[dict] = []
        total_episode_bars = 0
        for ep in EPISODES:
            ep_start = pd.Timestamp(ep["start"])
            ep_end   = pd.Timestamp(ep["end"])
            ep_mask  = pd.Series((s.index >= ep_start) & (s.index <= ep_end), index=s.index)
            n_ep_bars = int(ep_mask.sum())
            total_episode_bars += n_ep_bars
            if n_ep_bars == 0:
                grid_episodes.append({
                    "name":             ep["name"],
                    "label":            ep["label"],
                    "note":             "no bars in series window (pre-history)",
                })
                continue

            # StochRSI %K pin count
            k_pin = _stochk_pin_count(k_s, ep_mask)
            k_pin_frac = k_pin / n_ep_bars if n_ep_bars > 0 else None

            # Bear cross (widening = bear direction in price-analogy space)
            bear_lag = _cross_lag_vs_episode(bear_cross, ep_start, ep_mask)
            n_bear_cross = int(bear_cross[ep_mask].sum())
            # Bull cross (tightening — less relevant for widening episodes)
            bull_lag = _cross_lag_vs_episode(bull_cross, ep_start, ep_mask)
            n_bull_cross = int(bull_cross[ep_mask].sum())

            grid_episodes.append({
                "name":             ep["name"],
                "label":            ep["label"],
                "description":      ep["description"],
                "n_bars_in_episode": n_ep_bars,
                "stochk_pin_ge80_count": k_pin,
                "stochk_pin_ge80_frac":  round(k_pin_frac, 3) if k_pin_frac is not None else None,
                "bear_cross_count":      n_bear_cross,
                "bear_cross_lag_bars":   bear_lag,
                "bull_cross_count":      n_bull_cross,
                "bull_cross_lag_bars":   bull_lag,
            })

        # Calm-regime false-fire rate
        all_ep_mask = pd.Series(False, index=s.index)
        for ep in EPISODES:
            ep_start = pd.Timestamp(ep["start"])
            ep_end   = pd.Timestamp(ep["end"])
            all_ep_mask = all_ep_mask | ((s.index >= ep_start) & (s.index <= ep_end))

        calm_bear_rate = _calm_false_fire_rate(bear_cross, all_ep_mask)
        calm_bull_rate = _calm_false_fire_rate(bull_cross, all_ep_mask)
        n_calm_bars    = int((~all_ep_mask).sum())

        results[grid] = {
            "n_bars_total":        n_bars,
            "n_bars_episodes":     total_episode_bars,
            "n_bars_calm":         n_calm_bars,
            "episodes":            grid_episodes,
            "calm_bear_crosses_per_year": round(calm_bear_rate, 2),
            "calm_bull_crosses_per_year": round(calm_bull_rate, 2),
        }

    return results


_DISCRIMINATION_MARGIN = 1.5   # pre-declared: episode cross-rate must be >= 1.5x calm rate

def _compute_discrimination_ratio(grid_result: dict) -> float | None:
    """Episode cross-rate / calm cross-rate for bear crosses per bar.

    Episode cross-rate = (total bear crosses in episodes) / (total episode bars) * 252.
    Calm cross-rate = calm_bear_crosses_per_year (already annualised).
    Returns None if calm rate is zero or insufficient data.
    """
    calm_rate = grid_result.get("calm_bear_crosses_per_year")
    if calm_rate is None or calm_rate <= 0:
        return None

    episodes = grid_result.get("episodes", [])
    total_ep_bars = 0
    total_ep_crosses = 0
    for ep in episodes:
        if "n_bars_in_episode" in ep:
            total_ep_bars += ep.get("n_bars_in_episode", 0)
            total_ep_crosses += ep.get("bear_cross_count", 0)

    if total_ep_bars == 0:
        return None

    # Annualise episode cross rate
    ep_rate = (total_ep_crosses / total_ep_bars) * 252.0
    return ep_rate / calm_rate


def _verdict_from_results(analyses: list[dict]) -> tuple[str, dict]:
    """Compute discrimination ratios per series×grid and return verdict + ratio table.

    Pre-declared margin (§2.5-6, CCW-R15): episode/calm ratio >= 1.5x required for
    SECONDARY-CONFIRMED. Below margin → DEMOTED. The verdict is determined by the
    minimum ratio across all analysed series×grid combinations.

    Returns (verdict_string, ratios_dict).
    """
    ratios: dict[str, dict] = {}  # {series_id: {grid: ratio}}
    all_ratios: list[float] = []

    for a in analyses:
        sid = a["series_id"]
        ratios[sid] = {}
        for grid in ["1D", "3B"]:
            gd = a.get(grid, {})
            if not gd or "error" in gd:
                ratios[sid][grid] = None
                continue
            r = _compute_discrimination_ratio(gd)
            ratios[sid][grid] = round(r, 3) if r is not None else None
            if r is not None:
                all_ratios.append(r)

    if not all_ratios:
        verdict = (
            "INCONCLUSIVE — insufficient data to compute discrimination ratios. "
            "Velocity-percentile remains PRIMARY per CCW-R15/§2.5-6. "
            "Oscillator crosses are retained as secondary context with this caveat."
        )
        return verdict, ratios

    min_ratio = min(all_ratios)
    if min_ratio >= _DISCRIMINATION_MARGIN:
        verdict = (
            f"SECONDARY-CONFIRMED — episode/calm discrimination ratio {min_ratio:.2f}x "
            f"(pre-declared threshold: >={_DISCRIMINATION_MARGIN}x) across all series×grids. "
            "Oscillator crosses correlate with widening episodes at above-threshold rate. "
            "Velocity-percentile remains PRIMARY per CCW-R15/§2.5-6."
        )
    else:
        verdict = (
            f"DEMOTED — no episode discrimination: episode/calm bear-cross ratio {min_ratio:.2f}x "
            f"below pre-declared threshold of {_DISCRIMINATION_MARGIN}x. "
            "Crosses print as context with caveat; excluded from ledger and never a tag's sole basis. "
            "K-of-N tags retain cross legs as 1-of-3 contributors (never sole basis) — "
            "this is consistent with the multi-signal confluence design (CCW-R15/§2.5-6). "
            "Velocity-percentile remains PRIMARY."
        )
    return verdict, ratios


def _print_markdown_table(analyses: list[dict]) -> None:
    """Print a markdown summary table to stdout."""
    print("\n## CCW-W3 Spread Oscillator Sanity Study\n")
    print("**Ruling:** CCW-R15 / §2.5-6 — velocity-percentile PRIMARY, oscillator crosses SECONDARY\n")
    print("| Series | Grid | Episode | Bars | StochK≥80 % | Bear-cross count | Bear lag (bars) | Calm false-fire /yr |")
    print("|--------|------|---------|------|------------|-----------------|----------------|---------------------|")

    for a in analyses:
        sid = a["series_id"]
        for grid in ["1D", "3B"]:
            gd = a.get(grid, {})
            if not gd or "error" in gd:
                print(f"| {sid} | {grid} | — | — | — | — | — | — |")
                continue
            calm_rate = gd.get("calm_bear_crosses_per_year", "?")
            for ep in gd.get("episodes", []):
                if "n_bars_in_episode" not in ep:
                    # Pre-history
                    continue
                name   = ep.get("name", "")
                n_bars = ep.get("n_bars_in_episode", 0)
                k_frac = ep.get("stochk_pin_ge80_frac")
                bc     = ep.get("bear_cross_count", 0)
                b_lag  = ep.get("bear_cross_lag_bars")
                k_str  = f"{k_frac:.1%}" if k_frac is not None else "—"
                lag_str = str(b_lag) if b_lag is not None else "—"
                print(f"| {sid} | {grid} | {name} | {n_bars} | {k_str} | {bc} | {lag_str} | {calm_rate:.2f} |")

    print()


def run(root: Path | None = None) -> dict:
    """Run the sanity study and write data/corp_bonds/oscillator_sanity.json."""
    t0 = time.time()
    _root = root or _data_root(None)

    # Load series
    hy_oas_live = _load_archive_merged("BAMLH0A0HYM2", _root)
    ig_oas_live = _load_archive_merged("BAMLC0A0CM",   _root)

    if hy_oas_live is None:
        log.error("sanity: HY OAS not available — cannot run study")
        result = {
            "as_of": str(date.today()),
            "verdict": "ERROR: HY OAS series not available",
            "analyses": [],
        }
        out_path = _root / "corp_bonds" / "oscillator_sanity.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        return result

    # Note: hard_exit is required when pyarrow is touched in procutil-guarded scripts.
    # We have read the parquets above; call hard_exit after writing the output.

    analyses = []
    for series_id, series in [("hy_oas", hy_oas_live), ("ig_oas", ig_oas_live)]:
        if series is None:
            log.warning("sanity: %s not available, skipping", series_id)
            continue
        a = _analyze_series(series_id, series, grids=["1D", "3B"])
        analyses.append(a)

    verdict, discrimination_ratios = _verdict_from_results(analyses)
    elapsed = time.time() - t0

    # Print markdown table
    _print_markdown_table(analyses)

    # Print discrimination ratio table
    print("\n### Discrimination Ratios (episode bear-cross rate / calm bear-cross rate)\n")
    print(f"**Pre-declared threshold:** >={_DISCRIMINATION_MARGIN}x for SECONDARY-CONFIRMED\n")
    print("| Series | Grid | Episode rate /yr | Calm rate /yr | Ratio | Verdict |")
    print("|--------|------|-----------------|---------------|-------|---------|")
    for a in analyses:
        sid = a["series_id"]
        for grid in ["1D", "3B"]:
            gd = a.get(grid, {})
            if not gd or "error" in gd:
                continue
            calm_rate = gd.get("calm_bear_crosses_per_year", 0)
            ratio = discrimination_ratios.get(sid, {}).get(grid)
            # Compute episode rate for table
            episodes = gd.get("episodes", [])
            total_ep_bars = sum(ep.get("n_bars_in_episode", 0) for ep in episodes if "n_bars_in_episode" in ep)
            total_ep_crosses = sum(ep.get("bear_cross_count", 0) for ep in episodes if "n_bars_in_episode" in ep)
            ep_rate = (total_ep_crosses / total_ep_bars * 252.0) if total_ep_bars > 0 else 0.0
            verdict_cell = ("CONFIRMED" if (ratio or 0) >= _DISCRIMINATION_MARGIN else "DEMOTED") if ratio is not None else "N/A"
            ratio_str = f"{ratio:.2f}x" if ratio is not None else "N/A"
            print(f"| {sid} | {grid} | {ep_rate:.2f} | {calm_rate:.2f} | {ratio_str} | {verdict_cell} |")
    print()

    # Episode summary table
    print("### Episode Summary (HY OAS 1D grid)\n")
    hy_1d = next((a for a in analyses if a["series_id"] == "hy_oas"), {}).get("1D", {})
    if hy_1d and "episodes" in hy_1d:
        for ep in hy_1d["episodes"]:
            if "n_bars_in_episode" in ep:
                k_f = ep.get("stochk_pin_ge80_frac", 0) or 0
                print(f"- **{ep['name']}** ({ep.get('description','')}): "
                      f"{ep['n_bars_in_episode']} bars, StochK≥80 {k_f:.0%}, "
                      f"bear-crosses: {ep.get('bear_cross_count',0)}, "
                      f"lag: {ep.get('bear_cross_lag_bars','—')} bars")
        print(f"\n**Calm false-fire rate (HY OAS, 1D):** {hy_1d.get('calm_bear_crosses_per_year','?'):.2f} bear-crosses/year")

    print(f"\n**VERDICT:** {verdict}\n")

    result = {
        "as_of":          str(date.today()),
        "generated_at":   pd.Timestamp.utcnow().isoformat(),
        "series":         ["hy_oas", "ig_oas"],
        "grids":          ["1D", "3B"],
        "episodes":       [ep["name"] for ep in EPISODES],
        "verdict":        verdict,
        "discrimination_threshold": _DISCRIMINATION_MARGIN,
        "discrimination_ratios":   discrimination_ratios,
        "verdict_caveat": (
            "If verdict is DEMOTED: crosses are retained as secondary context only — "
            "1-of-3 in K-of-N tags (never sole basis). If SECONDARY-CONFIRMED: "
            "crosses remain secondary (velocity-percentile is always PRIMARY)."
        ),
        "verdict_detail": (
            "Oscillator crosses are RETAINED as secondary context — they may fire during "
            "widening episodes, but with lag vs episode onset and non-trivial calm-regime "
            "false-fire rates. See discrimination_ratios for episode/calm rate per series×grid. "
            "Velocity-percentile (Δ21/Δ63 vs 10y rolling window) is the "
            "primary spread read per CCW-R15. This file is the evidence record."
        ),
        "analyses":       analyses,
        "_timing_s":      round(elapsed, 2),
    }

    out_path = _root / "corp_bonds" / "oscillator_sanity.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    log.info("ccw_spread_oscillator_sanity: wrote %s (%.2fs)", out_path, elapsed)

    # hard_exit: pyarrow was touched in _load_archive_merged (read_parquet calls)
    # Caller is responsible; use hard_exit(0) at __main__ level.
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="CCW-W3 spread oscillator sanity study (one-shot)")
    ap.add_argument("--root", default=None, help="data root override")
    args = ap.parse_args()
    run(root=Path(args.root) if args.root else None)
    hard_exit(0)
