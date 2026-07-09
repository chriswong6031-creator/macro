"""scripts/lab_backtest.py — CLI to backtest any catalog signal in one command.

Usage (one-liner)::

    python -m scripts.lab_backtest <signal_id> [--universe ALL|quick] [--horizon 21] [--cost-bps 5]

Discovery::

    python -m scripts.lab_backtest --list          # grouped by family
    python -m scripts.lab_backtest --list rsi_bands # single family

Backtest::

    python -m scripts.lab_backtest rsi14_oversold --universe quick --horizon 21 --cost-bps 5
    python -m scripts.lab_backtest golden_star_lt_50_200 --universe ALL --horizon 42 --json

Key entry points (reused, no new stats)::

    engine.lab.load(universe)          → dict[ticker, DataFrame]
    engine.lab.catalog_backtest(...)   → Trial
    engine.lab.list_signals(family)    → list[dict]  (same as engine.tech_catalog.list_signals)

Display is research-only; nothing wired to allocation or signals.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_stat(key: str, val: Any) -> str:
    """Format a single stat key/value for human display."""
    if val is None:
        return f"  {key}: —"
    if isinstance(val, float):
        return f"  {key}: {val:.4f}"
    if isinstance(val, (list, tuple)):
        inner = ", ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in val)
        return f"  {key}: [{inner}]"
    return f"  {key}: {val}"


def _print_trial(trial: Any, signal_id: str, universe_key: str,
                 horizon: int, cost_bps: float) -> None:
    """Print a Trial result in a readable block."""
    verdict = trial.verdict()
    print()
    print("=" * 62)
    print(f"  Signal   : {signal_id}")
    print(f"  Universe : {universe_key}")
    print(f"  Horizon  : {horizon}d   Cost: {cost_bps}bps")
    print(f"  Bias     : survivorship_biased={trial.survivorship_biased}")
    print("-" * 62)
    print("  STATS")
    # Show a priority-ordered subset first, then the rest
    _PRIORITY = [
        "dsr", "dsr_verdict", "sharpe_ann", "sharpe_ci",
        "split_half_consistent", "split_half_sr_h1", "split_half_sr_h2",
        "mean_ic", "ic_nw_t", "ic_nw_p", "n_tickers",
    ]
    shown = set()
    for key in _PRIORITY:
        if key in trial.stats:
            print(_fmt_stat(key, trial.stats[key]))
            shown.add(key)
    for key, val in trial.stats.items():
        if key not in shown:
            print(_fmt_stat(key, val))
    print("-" * 62)
    print(f"  VERDICT  : {verdict}")
    print("=" * 62)
    print()


def _print_list(signals: list[dict], family_filter: str | None = None) -> None:
    """Print signals grouped by family."""
    by_family: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        by_family[s.get("family", "?")].append(s)

    total = 0
    for fam in sorted(by_family):
        entries = by_family[fam]
        print(f"\n  [{fam}]")
        for e in entries:
            sid = e.get("signal_id", "?")
            disp = e.get("display", {}).get("en", "")
            kind = e.get("kind", "")
            direction = e.get("direction", 0)
            dir_ch = "+" if direction > 0 else ("-" if direction < 0 else "~")
            print(f"    {dir_ch}  {sid:<42}  {kind:<8}  {disp[:60]}")
            total += 1

    print()
    print(f"  Total: {total} signal(s)")
    if family_filter:
        print(f"  (filtered to family={family_filter!r})")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.lab_backtest",
        description=(
            "Backtest any catalog signal in one command.  "
            "Uses engine.lab.load + engine.lab.catalog_backtest — no new stats."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    p.add_argument(
        "signal_id",
        nargs="?",
        default=None,
        help="Signal ID to backtest (run --list to see all IDs).",
    )
    p.add_argument(
        "--list",
        metavar="FAMILY",
        nargs="?",
        const="__all__",
        dest="list_family",
        help=(
            "List all registered signals grouped by family. "
            "Optionally pass a family name to filter (e.g. --list rsi_bands)."
        ),
    )
    p.add_argument(
        "--universe",
        default="quick",
        help="Universe to load: 'ALL' (full survivor set) or 'quick' (8 mega-caps). Default: quick.",
    )
    p.add_argument(
        "--horizon",
        type=int,
        default=21,
        help="Forward-return horizon in calendar days. Default: 21.",
    )
    p.add_argument(
        "--cost-bps",
        type=float,
        default=5.0,
        dest="cost_bps",
        help="One-way transaction cost in basis points. Default: 5.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Print machine-readable JSON instead of a human block.",
    )
    p.add_argument(
        "--min-bars",
        type=int,
        default=400,
        dest="min_bars",
        help="Drop tickers with fewer bars than this threshold. Default: 400.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns exit code (0 = ok, 1 = error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    from engine import lab  # lazy — keeps import fast for --list

    # ------------------------------------------------------------------
    # --list
    # ------------------------------------------------------------------
    if args.list_family is not None:
        family_filter = None if args.list_family == "__all__" else args.list_family
        signals = lab.list_signals(family=family_filter)
        if args.json_out:
            # Strip the 'fn' callable before serialising
            safe = [{k: v for k, v in s.items() if k != "fn"} for s in signals]
            print(json.dumps(safe, indent=2, default=str))
        else:
            _print_list(signals, family_filter=family_filter)
        return 0

    # ------------------------------------------------------------------
    # backtest
    # ------------------------------------------------------------------
    if not args.signal_id:
        parser.print_help()
        return 1

    signal_id = args.signal_id

    # Validate signal exists before loading (cheap)
    from engine import tech_catalog
    try:
        descriptor = tech_catalog.get_signal(signal_id)
    except KeyError:
        print(f"Error: signal '{signal_id}' not found in catalog.", file=sys.stderr)
        print("Run --list to see all available signal IDs.", file=sys.stderr)
        return 1

    universe_key = args.universe
    print(f"Loading universe={universe_key!r} (min_bars={args.min_bars}) …", flush=True)
    universe = lab.load(tickers=universe_key, min_bars=args.min_bars)

    if not universe:
        print(
            f"Warning: universe={universe_key!r} returned 0 tickers. "
            "The data store may be empty in this environment.",
            file=sys.stderr,
        )
        # Return a minimal result rather than erroring hard
        if args.json_out:
            print(json.dumps({"error": "empty_universe", "signal_id": signal_id}))
        return 1

    print(f"Running backtest: {signal_id}  n_tickers={len(universe)}  horizon={args.horizon}d  cost={args.cost_bps}bps …", flush=True)

    trial = lab.catalog_backtest(
        signal_id,
        universe,
        horizon=args.horizon,
        cost_bps=args.cost_bps,
    )

    if args.json_out:
        out = {
            "signal_id": signal_id,
            "universe": universe_key,
            "horizon": args.horizon,
            "cost_bps": args.cost_bps,
            "n_tickers_loaded": len(universe),
            "name": trial.name,
            "family": trial.family,
            "survivorship_biased": trial.survivorship_biased,
            "stats": trial.stats,
            "verdict": trial.verdict(),
            "meta": trial.meta,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        _print_trial(trial, signal_id, universe_key, args.horizon, args.cost_bps)

    return 0


if __name__ == "__main__":
    sys.exit(main())
