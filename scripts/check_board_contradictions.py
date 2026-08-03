#!/usr/bin/env python3
"""Static guard: validates site/factordata/us_standouts.json for build-time contradictions.

Five invariants checked (W2 original 4 + W4 reflexivity):

  (a) No FRESH-BUY-ish state/label with cross age > FRESH_TICKS+1 OR extension grade.
      The W8 arbiter should have demoted these at build time; a hit here means the arbiter
      missed a path.

  (b) No urgency=imminent on a row with a blocked label or BOTTOMING-class state.
      The W6-US fix 7 + W8 arbiter should close this; a hit means a new code path bypassed both.

  (c) No band high/constructive while verdict is Lagging or no-clear-edge.
      The W6-US fix 2 + W2 arbiter rule-3 should close this; a hit is a regression.

  (d) The board is in its declared sort order. Which order that IS depends on the board
      definition the artifact stamps, so this invariant has two branches:

      * us_prophet_v1 (rows carry `stage`): the order is (stage bucket, priority score
        desc, ticker). Checked as: the stage sequence never goes backwards, the score
        never rises inside a stage, and — the load-bearing one — no blocked-stage row
        sits above any live-stage row. Alpha is one of five scoring legs here, so
        alpha-desc is NOT the contract and must not be asserted.
      * legacy boards (no `stage` field): the pre-2026-08 alpha-desc-within-lane
        contract. Slot-1 alpha must not be negative while positive-alpha rows exist in
        the same lane. A violation means the sort was applied incorrectly.

  (e) W4 reflexivity (R-B): per-lane effective_bets from the board and per-lane n_eff from
      the reflexivity overlay must not diverge by more than 3x.  Both numbers are computed over
      the SAME per-lane candidate set (overlay emits n_eff_by_lane to match the population
      that build_stock_board_v2._concentration() uses).  A >3x ratio means two contradictory
      "independent bets" numbers are visible on the same lane of the board.

Exit 0 on clean. Exit 1 with a readable table on violation.

Usage:
    python3 scripts/check_board_contradictions.py [ARTIFACT_PATH]
    # default: site/factordata/us_standouts.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cross-age threshold from engine/confluence_tiers.py
FRESH_TICKS = 2

_FRESH_BUY_STATES = {"FRESH BUY", "TURN SIGNALED"}
_BOTM_STATES = {"BOTTOMING", "BASING", "ACCUMULATION"}
_GREEN_BANDS = {"high", "constructive"}
_LAGGING_VERDICTS = ("lagging", "no clear edge")

# The grade values that mean "extended" in extension_read
_EXT_GRADES = {"parabolic", "stretched"}


# us_prophet_v1 stage buckets, best-actionable first. Kept as a literal rather than
# imported from engine.us_board_rank so this guard stays a standalone script with no
# engine import (it runs in the pages.yml publish lane too).
_STAGE_ORDER = ("live", "setting_up", "ran", "blocked")


def _check_prophet_order(buy_rows: list) -> list[str]:
    """Invariant (d), us_prophet_v1 branch: the buy array is in (stage, −score) order."""
    out: list[str] = []
    rank_of = {name: i for i, name in enumerate(_STAGE_ORDER)}

    prev_rank = -1
    prev_stage = None
    prev_score = None       # last SCORED row inside the CURRENT bucket
    for r in buy_rows:
        stage = r.get("stage")
        rank = rank_of.get(stage)
        if rank is None:
            out.append(
                f"(d) {r.get('ticker')}: unknown stage {stage!r} — expected one of "
                f"{list(_STAGE_ORDER)}"
            )
            continue
        if rank < prev_rank:
            out.append(
                f"(d) {r.get('ticker')}: stage={stage!r} appears after stage="
                f"{prev_stage!r} — stage buckets must run "
                f"{' -> '.join(_STAGE_ORDER)}"
            )
        if rank != prev_rank:
            # A new bucket restarts the chain: scores are only comparable within one
            # stage, so the previous bucket's last score must not anchor this one.
            prev_score = None
        score = ((r.get("prophet") or {}).get("score"))
        if prev_score is not None and score is not None and score > prev_score + 1e-9:
            out.append(
                f"(d) {r.get('ticker')}: score={score} outranks the row above it "
                f"({prev_score}) inside stage={stage!r} — score must be "
                f"non-increasing within a bucket"
            )
        # A None score is a MISSING READING, not a reset. Overwriting the anchor with
        # None blinded the walk for the row after it, so a single scoreless row in the
        # middle of a bucket masked the very violation that follows it: [100, None,
        # 200] compared nothing at all and passed clean. Carrying the last scored row
        # forward keeps the guard able to SEE that failure.
        if score is not None:
            prev_score = score
        prev_rank, prev_stage = rank, stage

    # The load-bearing one, stated independently of the sequence walk so it cannot be
    # masked by an unknown stage: nothing you are told not to buy may sit above
    # something you are told you can buy today.
    live_at = [i for i, r in enumerate(buy_rows) if r.get("stage") == "live"]
    blocked_at = [i for i, r in enumerate(buy_rows) if r.get("stage") == "blocked"]
    if live_at and blocked_at and min(blocked_at) < max(live_at):
        offender = buy_rows[min(blocked_at)]
        out.append(
            f"(d) {offender.get('ticker')}: a blocked-stage row sits at slot "
            f"{min(blocked_at) + 1}, above a live-stage row at slot {max(live_at) + 1}"
        )
    return out


def _check(artifact_path: str = "site/factordata/us_standouts.json") -> list[str]:
    """Return a list of violation strings. Empty list = clean."""
    p = Path(artifact_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        # Absent artifact is not a violation (first run or not yet emitted)
        return []

    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return [f"JSON parse error: {e}"]

    violations: list[str] = []
    buy_rows = data.get("buy") or []

    # ---- (a) FRESH-BUY-ish state with stale cross or extended grade ----
    for r in buy_rows:
        state = (r.get("state") or "").upper()
        if state not in _FRESH_BUY_STATES:
            continue
        sig = r.get("signal") or {}
        ticks = sig.get("ticks")
        if ticks is not None and ticks > FRESH_TICKS + 1:
            violations.append(
                f"(a) {r.get('ticker')}: state={state!r} but ticks={ticks} > FRESH_TICKS+1={FRESH_TICKS + 1}"
            )
        # Extension grade (best-effort; may be absent in older schemas)
        ext = r.get("extension_read") or {}
        if isinstance(ext, dict) and ext.get("grade") in _EXT_GRADES:
            violations.append(
                f"(a) {r.get('ticker')}: state={state!r} but extension.grade={ext.get('grade')!r}"
            )

    # ---- (b) urgency=imminent on blocked label or BOTTOMING-class state ----
    for r in buy_rows:
        if r.get("urgency") != "imminent":
            continue
        state = (r.get("state") or "").upper()
        if state in _BOTM_STATES:
            violations.append(
                f"(b) {r.get('ticker')}: urgency=imminent but state={state!r}"
            )
        label = (r.get("label") or "").lower()
        if "block" in label:
            violations.append(
                f"(b) {r.get('ticker')}: urgency=imminent but label contains 'block' ({r.get('label')!r})"
            )

    # ---- (c) band high/constructive while verdict is lagging/no-clear-edge ----
    for r in buy_rows:
        c = r.get("conviction") or {}
        band = (c.get("band") or "").lower()
        verdict = (c.get("verdict") or "").lower()
        if band in _GREEN_BANDS and any(k in verdict for k in _LAGGING_VERDICTS):
            violations.append(
                f"(c) {r.get('ticker')}: band={band!r} but verdict={c.get('verdict')!r}"
            )

    # ---- (d) the board is in its declared sort order ----
    # Branch on the board definition the ARTIFACT declares, not on a constant here: a
    # guard that keeps asserting a superseded contract turns every correct render into
    # a red, and a guard that simply stops asserting stops seeing broken sorts. Both
    # branches must still be able to FAIL on a scrambled board.
    if any(r.get("stage") for r in buy_rows):
        violations.extend(_check_prophet_order(buy_rows))
    else:
        # Legacy (pre-us_prophet_v1) contract: alpha desc within lane.
        # Group rows by lane; check that row[0].alpha >= all others.
        # Only fires when at least two rows in a lane have non-None alpha.
        lane_rows: dict[str, list] = {}
        for r in buy_rows:
            lane = r.get("lane") or "buy"
            lane_rows.setdefault(lane, []).append(r)

        for lane, rows in lane_rows.items():
            alphas = [(i, r.get("alpha")) for i, r in enumerate(rows)
                      if r.get("alpha") is not None]
            if len(alphas) < 2:
                continue
            # Find the highest alpha value across the lane
            max_alpha = max(a for _, a in alphas)
            # The first row in the lane should have the highest (or equal) alpha
            first_alpha = alphas[0][1]
            if first_alpha < 0 and max_alpha > 0:
                violations.append(
                    f"(d) lane={lane!r}: slot-1 alpha={first_alpha:.3f} is negative "
                    f"but max alpha in lane={max_alpha:.3f} > 0 (sort broken)"
                )

    # ---- (e) W4 reflexivity R-B: no two divergent effective_bets numbers (per lane) ----
    # Compare each lane's board effective_bets against the SAME LANE's n_eff from the
    # reflexivity overlay (n_eff_by_lane).  Both are computed over identical candidate sets,
    # so the 3x tolerance is meaningful and cannot false-trip from a union-vs-lane mismatch.
    # Only fires when both artifacts are present and both have numeric values for that lane.
    p_v2 = ROOT / "site" / "factordata" / "us_standouts_v2.json"
    p_rx = ROOT / "site" / "factordata" / "reflexivity_overlay.json"
    if p_v2.exists() and p_rx.exists():
        try:
            d_v2 = json.loads(p_v2.read_text())
            d_rx = json.loads(p_rx.read_text())
            # Use per-lane n_eff from overlay (matches the board's per-lane population).
            # Fall back to the union n_eff only if n_eff_by_lane is absent (old overlay schema).
            neff_by_lane_rx = d_rx.get("n_eff_by_lane") or {}
            for lane_name in ("entry_open", "setting_up"):
                conc_v2 = (d_v2.get("concentration") or {}).get(lane_name) or {}
                eff_v2 = conc_v2.get("effective_bets")
                basis_v2 = conc_v2.get("effective_bets_basis", "")
                # Per-lane n_eff from overlay (same population as board _concentration call)
                neff_rx_lane = neff_by_lane_rx.get(lane_name)
                if (isinstance(eff_v2, (int, float)) and isinstance(neff_rx_lane, (int, float))
                        and eff_v2 > 0 and neff_rx_lane > 0):
                    ratio = max(eff_v2, neff_rx_lane) / min(eff_v2, neff_rx_lane)
                    if ratio > 3.0:
                        violations.append(
                            f"(e) W4 R-B: board concentration lane={lane_name!r} effective_bets"
                            f"={eff_v2} (basis={basis_v2!r}) diverges >3x from reflexivity "
                            f"n_eff_by_lane={neff_rx_lane} — two contradictory independent-bets "
                            f"numbers shown on the same lane."
                        )
        except Exception:  # noqa: BLE001  — missing/malformed artifacts are not a violation
            pass

    return violations


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    artifact = argv[0] if argv else "site/factordata/us_standouts.json"

    violations = _check(artifact)
    if violations:
        print(
            f"check_board_contradictions: FAIL — {len(violations)} invariant violation(s) "
            f"in {artifact}:\n",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nThese are build-time invariants: the W8 arbiter + W6-US fix passes should have "
            "prevented them. Investigate the build path for the listed tickers and re-run the build.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_board_contradictions: OK — {artifact} passes all 5 board invariants "
        f"(a: stale-fresh, b: imminent-blocked, c: band-verdict, d: declared-sort "
        f"[stage+score under us_prophet_v1, alpha-desc on legacy boards], "
        f"e: W4-reflexivity-neff-consistency)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
