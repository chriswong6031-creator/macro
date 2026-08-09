#!/usr/bin/env python3
"""Build the Stage Analysis (SGA) context feed + forward ledger.

Thin CLI over engine.stage_analysis. Runs in the daily.yml parallel band,
off the render-critical path (masterplan W1).

Exit 0 even on partial failure (logs ::warning::); exit 1 only on a total
failure (the engine could not produce a contract at all).

Usage:
    python -m scripts.build_stage_analysis [--root DATA_ROOT] [--asof YYYY-MM-DD]
                                           [--max-workers N] [--fixture PATH]

--fixture PATH: skip the universe fan-out and load a pre-built stage_context.v1
    JSON (used by tests / dry runs); the forward ledger is still appended from it.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make the repo root importable when run as a bare script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine import stage_analysis  # noqa: E402

log = logging.getLogger("build_stage_analysis")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Stage Analysis context feed.")
    ap.add_argument("--root", default=None,
                    help="Data root override (defaults to repo data/).")
    ap.add_argument("--asof", default=None,
                    help="As-of date YYYY-MM-DD (defaults to today UTC).")
    ap.add_argument("--max-workers", type=int, default=None,
                    help="Process-pool size (capped at 4 by the engine).")
    ap.add_argument("--fixture", default=None,
                    help="Load a pre-built stage_context.v1 JSON instead of "
                         "running the universe fan-out (tests / dry runs).")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    root = Path(args.root) if args.root else None

    # --- SGA-2 independent side surfaces ------------------------------------
    # Earnings/alt-data/research can build before the classifier. Industry
    # ranks + flows cannot: build_context_feed now retains the live per-name
    # frame, joins reference-only GICS taxonomy, and passes that same current
    # frame to both engines before projecting the screener. This avoids the old
    # cold-start path that silently emitted empty artifacts when the optional
    # stage_daily.parquet seed was absent.
    # Skipped in --fixture mode (dry runs / tests load a pre-built contract).
    if not args.fixture:
        try:
            from engine import earnings_qual  # noqa: PLC0415
            # build_all_earnings_surfaces takes the REPO root (data/ lives under it).
            eq_root = root.parent if root is not None else None
            earnings_qual.build_all_earnings_surfaces(eq_root)
            log.info("earnings_qual: 4 Earnings-Calls surfaces built")
        except Exception as e:  # noqa: BLE001
            print(f"::warning:: earnings_qual.build_all_earnings_surfaces failed ({e})",
                  flush=True)
        try:
            from engine import altdata_stage  # noqa: PLC0415
            altdata_stage.build_altdata_trending(root=root)
            log.info("altdata_stage: altdata_trending artifact built")
        except Exception as e:  # noqa: BLE001
            print(f"::warning:: altdata_stage.build_altdata_trending failed ({e})", flush=True)
        try:
            from engine import stage_research  # noqa: PLC0415
            stage_research.build_research_index(root=root)
            log.info("stage_research: research_index artifact built")
        except Exception as e:  # noqa: BLE001
            print(f"::warning:: stage_research.build_research_index failed ({e})", flush=True)

    try:
        if args.fixture:
            fx = Path(args.fixture)
            contract = json.loads(fx.read_text())
            log.info("loaded fixture contract from %s (asof=%s)",
                     fx, contract.get("asof"))
        else:
            contract = stage_analysis.build_context_feed(
                root=root, asof=args.asof, max_workers=args.max_workers)
    except Exception as e:  # noqa: BLE001 — total failure
        print(f"::error:: stage_analysis: context feed failed entirely ({e})", flush=True)
        return 1

    if not contract or contract.get("schema") != "stage_context.v1":
        print("::error:: stage_analysis: no valid contract produced", flush=True)
        return 1

    counts = contract.get("counts") or {}
    log.info("stage_context.v1 asof=%s total=%s stage2=%s fresh=%s changes=%s",
             contract.get("asof"), counts.get("total"),
             counts.get("stage2"), counts.get("stage2_fresh"),
             (contract.get("changes") or {}).get("n"))

    # Session-stamp heal (forward-ledger calendar-asof audit 2026-08-05) — runs
    # BEFORE the append so the append's (date, ticker) dedupe sees the healed
    # keys. It lives here rather than in the PR that wrote it because
    # .gitignore:574 gives this ledger a file-scoped law of its own — "nightly is
    # the SOLE advancer (house law) — never commit from a worktree" — so the
    # nightly lane is the only lane allowed to perform and commit the repair.
    # Idempotent: a healed ledger no-ops, so this stays in place permanently.
    # Fail-open, including the heal's own fail-closed SystemExit abort: one
    # unreadable ticker frame must not take the stage build down with it.
    try:
        from scripts.heal_stage_forward_ledger import heal as _heal_stage_ledger
        # heal() takes the REPO root (it resolves root/"data"/...), while this
        # script's `root` is the DATA root and defaults to None. Reuse the
        # engine's own resolver rather than hand-rolling the parent walk — it
        # honours MACRO_DATA_ROOT and the None default identically. Passing
        # `root` straight through would have made the heal permanently dark:
        # None raises TypeError, and an explicit data root resolves to
        # <data>/data/stage_analysis, which never exists.
        _hs = _heal_stage_ledger(stage_analysis._repo_root(root))
        if _hs.get("error"):
            # Never silent: a heal that cannot find its ledger is a defect, not
            # a no-op, and this is the only place it would ever be visible.
            print(f"::warning title=stage-ledger-heal-unreachable::"
                  f"forward-ledger heal did not run ({_hs['error']})", flush=True)
        elif _hs.get("n_restamped") or _hs.get("n_quarantined_now"):
            log.info("forward ledger heal: restamped %s, quarantined %s",
                     _hs.get("n_restamped"), _hs.get("n_quarantined_now"))
    except SystemExit as e:  # fail-closed abort inside the heal — never fatal here
        print(f"::warning:: forward-ledger heal aborted fail-closed ({e})", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: forward-ledger heal failed ({e})", flush=True)

    # Forward ledger (SGA-R7) — fail-open, never fatal.
    try:
        n_led = stage_analysis.append_forward_ledger(contract, root=root)
        log.info("forward ledger: appended %d fresh-Stage-2 row(s)", n_led)
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: forward-ledger append failed ({e})", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
