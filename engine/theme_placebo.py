"""engine.theme_placebo — Thematic placebo tape (TIL W6, PR-H).

Judge #8 + R-TIL-6: on each NEW foresight stage flag (non-WATCH transition),
append K=3 random non-flagged themes + 1 time-shifted variant (same theme,
as_of shifted -21d) to data/foresight/theme_placebo_tape.jsonl.

These placebo rows carry the same field structure as real flag rows PLUS
a placebo_kind field. They are graded by the same future grader so real
hit-rates can be reported as EXCESS over placebo (R-TIL-6 law).

Design:
  - "New flag" = a (theme, asof, stage) triple not already in the tape.
  - WATCH rows are excluded from the placebo-trigger set per the spec
    (WATCH is a control arm, not a directional call — generating placebo
    against it inflates the placebo pool without a directional thesis).
  - Deterministic seed: sha256(theme_id + asof) -> int -> seeded into
    random.Random. NO random.random / Date.now. Same inputs = same output.
  - K random non-flagged themes drawn from the SAME tier pool (all 18
    foresight themes excluding the flagged one itself).
  - Time-shift variant: same theme, same stage, asof shifted -21d.
    Members snapshot is copied from the original flag.
  - Append-only; deduplicated by (theme, asof, placebo_kind).
    Re-runs are idempotent.

Output: data/foresight/theme_placebo_tape.jsonl (append-only, nightly sole advancer).
Authority: is_context_only=True, all promotion flags False.
No LLM calls. Tolerant reader. Always exit 0.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's engine-job
    env.  US_LANE is accepted as a legacy alias.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACT_ID = "theme-placebo-tape"
OUTPUT_PATH = ("data", "foresight", "theme_placebo_tape.jsonl")

K_RANDOM = 3          # number of random non-flagged themes per real flag
TIME_SHIFT_DAYS = 21  # days to shift back for the time-shifted variant

# Stages that trigger placebo generation (excludes WATCH which is a control arm)
_NON_WATCH_STAGES = {"PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK",
                     "PRECIPICE (TEXT)", "BROADENING (TEXT)",
                     "PRECIPICE (FINGERPRINT)", "BROADENING (FINGERPRINT)"}

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}

# ---------------------------------------------------------------------------
# Deterministic seed
# ---------------------------------------------------------------------------

def _placebo_seed(theme_id: str, asof: str) -> int:
    """sha256(theme_id + '|' + asof) -> int. Reproducible across runs."""
    raw = f"{theme_id}|{asof}"
    h = hashlib.sha256(raw.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


# ---------------------------------------------------------------------------
# Dedup index helpers
# ---------------------------------------------------------------------------

def _dedup_key(row: dict) -> tuple[str, str, str]:
    """Canonical dedup key: (theme, asof, placebo_kind)."""
    return (
        str(row.get("theme", "")),
        str(row.get("asof", "")),
        str(row.get("placebo_kind", "")),
    )


def _load_existing_keys(p: Path) -> set[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    if not p.exists():
        return seen
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            seen.add(_dedup_key(row))
        except Exception:  # noqa: BLE001
            continue
    return seen


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------------------
# Core placebo generation
# ---------------------------------------------------------------------------

def _is_non_watch(stage: str) -> bool:
    """True when the stage is a non-WATCH transition (triggers placebo)."""
    upper = (stage or "").upper().strip()
    return not upper.startswith("WATCH")


def build_placebo_rows(
    flag: dict,
    all_theme_ids: list[str],
    seen: set[tuple[str, str, str]],
) -> list[dict]:
    """Build placebo rows for one real flag.

    Returns up to K_RANDOM + 1 new rows (deduped against `seen`).
    Does NOT append to `seen` — caller updates `seen` after deciding to write.
    """
    theme = flag.get("theme", "")
    asof = str(flag.get("asof", ""))
    stage = flag.get("stage", "UNKNOWN")
    members = flag.get("members") or []
    ts_real = flag.get("ts") or datetime.now(timezone.utc).isoformat()

    # Candidate pool: all themes EXCEPT the flagged one
    pool = [t for t in all_theme_ids if t != theme]

    rng = random.Random(_placebo_seed(theme, asof))
    rows: list[dict] = []

    # --- K random non-flagged themes ---
    chosen = rng.sample(pool, min(K_RANDOM, len(pool)))
    for placebo_theme in chosen:
        key = (placebo_theme, asof, "random_peer")
        if key in seen:
            continue
        rows.append({
            "theme": placebo_theme,
            "asof": asof,
            "ts": ts_real,
            "stage": stage,
            "members": members,    # carry the REAL flag's members (PIT snapshot)
            "placebo_kind": "random_peer",
            "source_theme": theme,  # which real flag triggered this
        })

    # --- Time-shifted variant: same theme, asof shifted -21d ---
    shifted_date = (datetime.strptime(asof, "%Y-%m-%d") - timedelta(days=TIME_SHIFT_DAYS)).date().isoformat()
    time_shift_key = (theme, shifted_date, "time_shift_minus_21d")
    if time_shift_key not in seen:
        rows.append({
            "theme": theme,
            "asof": shifted_date,
            "ts": ts_real,
            "stage": stage,
            "members": members,
            "placebo_kind": "time_shift_minus_21d",
            "source_theme": theme,
            "source_asof": asof,
        })

    return rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def append_placebo_tape(
    root: Path,
    today: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Append new placebo rows for any new (non-WATCH) flags found in
    data/foresight/log.jsonl that are not already in the tape.

    Returns a summary dict:
        n_new_flags, n_new_placebo_rows, n_skipped_dedup, n_watch_skipped
    """
    if today is None:
        today = date.today().isoformat()

    foresight_log_path = root / "data" / "foresight" / "log.jsonl"
    tape_path = root.joinpath(*OUTPUT_PATH)

    foresight_flags = _read_jsonl(foresight_log_path)
    if not foresight_flags:
        log.info("theme_placebo: foresight log absent/empty — nothing to do")
        return {
            "as_of": today,
            "n_new_flags": 0,
            "n_new_placebo_rows": 0,
            "n_skipped_dedup": 0,
            "n_watch_skipped": 0,
        }

    # All known theme ids from the flag log (the "tier pool")
    all_theme_ids = list({f.get("theme", "") for f in foresight_flags if f.get("theme")})

    # Load existing tape dedup keys
    existing_keys = _load_existing_keys(tape_path)

    # Also track which (real) flags we've already processed:
    # a flag is "new" if its (theme, asof, stage) is not already backed by a
    # random_peer entry in the tape (i.e., placebo rows for it haven't been written)
    processed_real_flags: set[tuple[str, str, str]] = {
        (str(k[0]), str(k[1]), k[2])
        for k in existing_keys
        if k[2] in ("random_peer", "time_shift_minus_21d")
    }
    # Use (source_theme, asof, kind) — but we track by (theme, asof) in the
    # source fields. Re-read to get source info:
    # Actually simpler: for each flag, generate rows and let dedup handle it.

    n_watch_skipped = 0
    n_new_flags = 0
    new_rows: list[dict] = []

    for flag in foresight_flags:
        stage = flag.get("stage", "")
        if not _is_non_watch(stage):
            n_watch_skipped += 1
            continue

        n_new_flags += 1
        candidate_rows = build_placebo_rows(flag, all_theme_ids, existing_keys)

        for row in candidate_rows:
            key = _dedup_key(row)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_rows.append(row)

    n_new = len(new_rows)
    n_skipped = sum(
        1 for flag in foresight_flags
        for _ in [None]
        if not _is_non_watch(flag.get("stage", ""))
    ) - n_watch_skipped  # already counted; just use n_watch_skipped

    if new_rows and not dry_run:
        if _ledger_advance_enabled():
            tape_path.parent.mkdir(parents=True, exist_ok=True)
            with tape_path.open("a", encoding="utf-8") as fh:
                for row in new_rows:
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            log.info("theme_placebo: appended %d new placebo rows to %s", n_new, tape_path)
        else:
            log.debug(
                "theme_placebo.append_placebo_tape: write skipped "
                "(COLLECT_LANE != nightly)"
            )
    elif new_rows:
        log.info("theme_placebo: dry_run — would append %d rows", n_new)

    return {
        "as_of": today,
        "n_new_flags": n_new_flags,
        "n_new_placebo_rows": n_new,
        "n_skipped_dedup": 0,  # dedup is embedded in generation loop
        "n_watch_skipped": n_watch_skipped,
    }
