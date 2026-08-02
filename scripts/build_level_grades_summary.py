#!/usr/bin/env python3
"""Publish the LIVE Level Report Card (Market Structure Core R2.4, v1).

Why this exists
---------------
SpotGamma's trust engine is a STATIC 2018–2024 hit-rate study; MenthorQ publishes no
methodology at all. We already GRADE every published level nightly
(``scripts/build_levels_track_record.py`` → ``data/levels/grades.parquet``: per-node
touched/held/broke against the NEXT session, per-board wall/band containment) — but the
grades were consumed only as a calibration scalar. This publisher turns them into the
live scorecard the masterplan calls the flagship: per-root and cross-universe
P(hold | touched) with Wilson intervals, recomputed daily.

Honesty (masterplan §4.1 Tier C):
- ``p_hold`` is judged against the two-sided coin-flip null (0.5): ``beats_null`` is
  true only when the Wilson 95% LOWER bound clears 0.5. The masterplan's stronger nulls
  (random equidistant level, prior-day high/low) need the price store at grade time and
  arrive with R2.4b — the payload NAMES its null so no consumer can over-read it.
- Roles whose dealer sign is undetermined (sticky=None) are counted as touched but never
  scored — absent, not zero.
- ⚠️ Coverage: the grading lane covers SINGLE NAMES (~120 roots). Index anchors
  (SPY/SPX/QQQ) have no boards yet; the ``_universe`` file is the honest context a
  consumer shows for an uncovered root, labelled as such. Index grading is a lane
  extension, tracked in the masterplan ledger.

Outputs (R2 + local):
  options_hub/level_grades/{ROOT}.json   for every root with ≥ MIN_BOARDS boards
  options_hub/level_grades/_universe.json  the cross-universe aggregate

Usage:
  python -m scripts.build_level_grades_summary [--dry-run] [--grades PATH] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("level_grades_summary")

REPO = Path(__file__).resolve().parent.parent
DEFAULT_GRADES = REPO / "data" / "levels" / "grades.parquet"
DEFAULT_OUT = REPO / "data" / "live_flow_out" / "options_hub" / "level_grades"
R2_PREFIX = "options_hub/level_grades/"

SCHEMA = "options_hub.level_grades/v1"
#: Roles that carry a hold/break verdict when touched (flip is direction-scored elsewhere).
SCORED_ROLES = ("call_wall", "put_wall", "anchor", "cluster", "counter", "trapdoor", "launchpad")
#: Trailing window, in distinct SESSION DATES present in the store.
WINDOW_SESSIONS = 252
#: A root below this many graded boards publishes nothing — a two-board "record" is noise.
MIN_BOARDS = 20
#: The null p_hold is judged against (two-sided hold definition ⇒ coin flip).
NULL_P = 0.5


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion. None when n == 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _r4(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)


def summarize(df: pd.DataFrame, root: str | None) -> dict | None:
    """One scorecard over `df` (pre-filtered to the window), for one root or the universe."""
    sub = df if root is None else df[df["root"] == root]
    if sub.empty:
        return None
    boards = sub.drop_duplicates("board_id")
    if len(boards) < MIN_BOARDS:
        return None

    roles_out: dict[str, dict] = {}
    for role in SCORED_ROLES:
        r = sub[sub["role"] == role]
        if r.empty:
            continue
        touched = r[r["touched"] == True]  # noqa: E712 — nullable object column
        scored = touched[touched["held"].notna()]
        n_scored = int(len(scored))
        held = int((scored["held"] == True).sum())  # noqa: E712
        ci = wilson_ci(held, n_scored)
        roles_out[role] = {
            "nodes": int(len(r)),
            "touched": int(len(touched)),
            "scored": n_scored,
            "held": held,
            "p_hold": _r4(held / n_scored) if n_scored else None,
            "ci95": [_r4(ci[0]), _r4(ci[1])] if ci else None,
            # Tier C gate: only a lower bound clear of the coin-flip null earns a claim.
            "beats_null": bool(ci and ci[0] > NULL_P) if n_scored else None,
        }

    flip = sub[(sub["role"] == "flip") & (sub["touched"] == True)]  # noqa: E712
    flip_moves = pd.to_numeric(flip["post_touch_move_pct"], errors="coerce").dropna()

    dates = sorted(sub["session_date"].dropna().unique())
    return {
        "schema": SCHEMA,
        "root": root or "_universe",
        "asof": str(dates[-1]) if dates else None,
        "window": {
            "since": str(dates[0]) if dates else None,
            "until": str(dates[-1]) if dates else None,
            "sessions": len(dates),
            "requested_sessions": WINDOW_SESSIONS,
        },
        "boards": {
            "n": int(len(boards)),
            "wall_contained_rate": _r4((boards["wall_contained"] == True).mean()),  # noqa: E712
            "band_contained_rate": _r4((boards["band_contained"] == True).mean()),  # noqa: E712
        },
        "roles": roles_out,
        "flip": {
            "touched": int(len(flip)),
            "mean_abs_post_move_pct": _r4(flip_moves.abs().mean()) if len(flip_moves) else None,
        },
        "null": "coin-flip 0.5 on the two-sided hold definition; equidistant and "
                "prior-day-extreme nulls arrive with R2.4b",
        "coverage_note": None if root else
            "Aggregate across every graded root (single names). Index anchors are not "
            "yet in the grading lane — a consumer showing this for an uncovered root "
            "must label it as universe context, not that root's record.",
        "authority_tier": "display",
    }


def build_all(grades_path: Path) -> dict[str, dict]:
    df = pd.read_parquet(grades_path)
    # exclude synthetic empty-board rows and rows without a session date
    df = df[(df["role"] != "_board") & df["session_date"].notna()]
    dates = sorted(df["session_date"].dropna().unique())
    window_dates = set(dates[-WINDOW_SESSIONS:])
    win = df[df["session_date"].isin(window_dates)]

    out: dict[str, dict] = {}
    uni = summarize(win, None)
    if uni:
        out["_universe"] = uni
    for root in sorted(win["root"].dropna().unique()):
        s = summarize(win, str(root))
        if s:
            out[str(root)] = s
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grades", default=str(DEFAULT_GRADES), metavar="PATH")
    ap.add_argument("--out", default=str(DEFAULT_OUT), metavar="DIR")
    ap.add_argument("--dry-run", action="store_true", help="build + report, write/publish nothing")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    grades = Path(args.grades)
    if not grades.exists():
        log.error("grades parquet missing at %s — nothing to summarise", grades)
        return 1

    cards = build_all(grades)
    if not cards:
        log.error("no root reached MIN_BOARDS=%d — nothing published", MIN_BOARDS)
        return 1
    covered = [r for r in cards if r != "_universe"]
    log.info("built %d scorecards (%d roots + universe), window %s → %s",
             len(cards), len(covered),
             cards["_universe"]["window"]["since"] if "_universe" in cards else "?",
             cards["_universe"]["window"]["until"] if "_universe" in cards else "?")

    if args.dry_run:
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for root, card in cards.items():
        (out_dir / f"{root}.json").write_text(json.dumps(card, separators=(",", ":")),
                                              encoding="utf-8")

    # R2 publish — same transport as the nightly; fail-open so a creds gap leaves
    # a complete local build rather than a half-published one.
    try:
        from scripts.build_options_hub_nightly import _r2_client, _upload_r2
        s3 = _r2_client()
        bucket = os.environ.get("R2_BUCKET")
        if s3 is None or not bucket:
            log.warning("R2 creds absent — scorecards written locally only")
            return 0
        ok = 0
        for root in cards:
            p = out_dir / f"{root}.json"
            if _upload_r2(s3, bucket, p, f"{R2_PREFIX}{root}.json"):
                ok += 1
        log.info("published %d/%d scorecards to R2", ok, len(cards))
    except Exception as exc:  # noqa: BLE001
        log.warning("R2 publish unavailable — %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
