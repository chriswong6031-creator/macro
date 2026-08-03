"""Shared append-time discipline for the desks' theses.jsonl ledgers. NEVER-RAISES.

WHY THIS EXISTS (2026-08-03 experiments audit)
----------------------------------------------
Desk thesis ids were minted from the DATA date (`{asof}-{i}`), not run identity. A stale
detector state re-briefed on later run days reuses the same `state_asof`, so every re-run
collided with the prior run's ids: data/ai_desk/theses.jsonl held 124 rows under 51 ids
(73 silently discarded by the scorers' last-wins dedupe, 68 of them past-due and never
graded — graded coverage 28%), and data/stock_desk/theses.jsonl held 606 rows under 259
ids with 35 graded ids re-appended under MUTATED lean/check_by. A falsifier whose
direction or horizon is rewritten after logging is not pre-registered; that mutation is
the direct cause of desk_placebo's pairing failure on stock_desk ("reconstructed 24
graded predicates but the track record has 72"), which caps its placebo coverage and
makes the desk unpromotable.

The two invariants this module enforces, at every desk:

  1. RUN-SCOPED IDS — `run_token(generated_at)` yields the full UTC second of the run
     (YYYYMMDDHHMMSS), so two runs over the same state_asof mint disjoint ids.
  2. IMMUTABLE ROWS — `reject_existing_ids()` refuses to append a row whose id is
     already in the ledger, LOUDLY (a GitHub annotation + log line): first write wins,
     a live row's lean/check_by can never be rewritten by a later append.

MIGRATION STORY for the already-collided ledgers: docs/DESK_LEDGER_ID_MIGRATION.md.
History is NOT rewritten — scored rows stay as-scored, the scorers keep last-wins
dedupe for the legacy window, and coverage heals forward from the deploy date.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def run_token(generated_at) -> str:
    """The run's identity for id-minting: the leading 14 digits (YYYYMMDDHHMMSS, UTC)
    of the brief's `generated_at` ISO timestamp. Full-second precision — a token built
    from the time-of-day alone (policy_intent's original HHMMSS) still collides when
    two different run DAYS share a stale state_asof and happen to fire at the same
    wall-clock second. Returns "" when the timestamp is unusable (caller keeps the
    legacy id shape rather than minting a malformed one)."""
    digits = "".join(c for c in str(generated_at or "") if c.isdigit())[:14]
    return digits if len(digits) == 14 else ""


def existing_ids(ledger_path) -> set:
    """All ids already present in an append-only jsonl ledger. Unreadable/absent file
    -> empty set (cold start); unparseable lines are skipped, never fatal."""
    out: set = set()
    try:
        p = Path(ledger_path)
        if not p.exists():
            return out
        for line in p.read_text().splitlines():
            try:
                rid = json.loads(line).get("id")
                if rid:
                    out.add(rid)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


def reject_existing_ids(ledger_path, rows: list, desk: str) -> list:
    """Filter `rows` down to those whose id is NOT already in the ledger — the
    append-time immutability gate. Logged theses are pre-registered predictions: an
    append that reuses a live id would rewrite that row's lean/check_by under the
    scorers' dedupe, so it is refused and announced (a rejection here means id minting
    regressed, or two runs shared a wall-clock second — either way a real defect
    signal, not noise). First write wins; never raises."""
    if not rows:
        return rows
    seen = existing_ids(ledger_path)
    if not seen:
        return rows
    kept = []
    for r in rows:
        rid = r.get("id")
        if rid in seen:
            # Annotation must START the line via bare print (never a logger — the
            # prefixing log format makes GitHub drop it silently); flush because CI
            # stdout is block-buffered when piped.
            print(f"::warning title=desk-ledger-id-collision::{desk}: refused to "
                  f"re-append thesis id {rid} — the logged row is immutable "
                  f"(first write wins; a re-run must mint a fresh run-scoped id)",
                  flush=True)
            log.warning("%s: ledger append refused for existing id %s (immutable row)",
                        desk, rid)
        else:
            kept.append(r)
    return kept


# --------------------------------------------------------------------------- #
# placebo-null disclosure — the measured no-skill base rate, printed BESIDE the
# hit-rate wherever a track record narrates itself. `hit` is a NOT-falsified
# endpoint whose null sits far above one-half (engine.desk_placebo); a bare
# "hit-rate 0.889" reads as skill and feeds back into the conviction-calibrating
# LLM prompt uncorrected.
# --------------------------------------------------------------------------- #
def placebo_lines(root, slug: str) -> tuple[str, str]:
    """(english, chinese) sentences for the desk's calibration note. Reads the desk's
    row out of data/calibration/summary.json under `root` (written by
    engine.calibration_hub — so the number is the PREVIOUS hub build's; nulls move
    slowly and this is a disclosure, not a gate). When no measured null exists the
    honest absence is printed instead — never a silent omission. Never raises."""
    nh = nd = None
    try:
        s = json.loads((Path(root) / "data" / "calibration" / "summary.json").read_text())
        for d in s.get("desks") or []:
            if d.get("slug") == slug:
                if d.get("placebo_available"):
                    nh, nd = d.get("null_hit_rate"), d.get("null_dir_rate")
                break
    except Exception:  # noqa: BLE001
        pass
    if nh is None:
        return ("The no-skill base rate for these exact conditions is not yet measured "
                "— read the hit-rate as unbenchmarked, not as evidence of skill.",
                "这些条件下的无技能基线尚未测得——命中率暂无基准，不应视作能力证据。")
    dir_en = f" (directional accuracy near {nd})" if nd is not None else ""
    dir_zh = f"（方向准确率约 {nd}）" if nd is not None else ""
    return (f"Chance alone would land a hit-rate near {nh}{dir_en} on these exact "
            f"conditions — judge the numbers above against that bar, not one-half.",
            f"同样条件下，无技能判断凭机会即可达到约 {nh} 的命中率{dir_zh}"
            f"——上述数字应与该基线比较，而非 0.5。")
