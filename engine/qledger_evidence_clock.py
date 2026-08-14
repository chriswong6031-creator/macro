"""engine/qledger_evidence_clock.py — write-once record of each qledger claim
FAMILY's first PROSPECTIVE registration (Eval OS P3).

WHY THIS EXISTS. The CEO's P3 directive requires "the exact first
prospective-registration timestamp for each family" — the instant the evidence
clock starts for that family's forward record. That instant matters because
every honesty claim downstream ("N graded dates", "this family has been live
M days") is measured FROM it; a start timestamp that could be quietly moved
forward would let a family's track record look older (more matured, more
credible) than it actually is. So the record is WRITE-ONCE: once a family has
a start timestamp, nothing may ever change it — not a re-run, not a later
family activation, not a backfill.

ONE FILE PER FAMILY, DELIBERATELY (not one shared JSON keyed by family). The
three P3 families (stock_desk, thematic_desk, demand_chain) each register from
a DIFFERENT nightly script (scripts/build_stock_briefs.py,
scripts/build_allocation.py, scripts/build_demand.py) that may run in
different Actions jobs. A single shared `evidence_clock_start.json` would make
two families' FIRST-EVER writes a real read-modify-write race on one whole-file
JSON document — and unlike this repo's append-only JSONL ledgers (which get
`merge=union` in .gitattributes, see data/qledger/claims.jsonl), a JSON object
cannot be union-merged: two concurrent single-key insertions land as a
same-region text conflict, and the push-retry loop's `-X theirs` resolution
(scripts/ci/push_retry.sh) would silently keep one side's key and drop the
other's — exactly the failure class B4 warns about for claims.jsonl, just one
document over. Splitting per family removes the conflict at the object level:
two families can never collide on the SAME path, and even a same-family double
write (which should never happen — this fires at most once per family, ever)
degrades to picking one of two honestly-near-simultaneous timestamps rather
than losing one family's record to another's.

NOTHING PRE-CREATES THESE FILES. They are written into existence by the first
real prospective registration on the nightly path — never stubbed or seeded by
this PR (data/qledger/ must stay untouched by a build task; see
CLAUDE.md "the ledgers are append-only nightly stores").
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("qledger_evidence_clock")

# data/qledger/evidence_clock_start/<family>.json — one small whole-file JSON
# document per claim family. See the module note for why per-family, not
# one shared file.
_CLOCK_DIR = ("data", "qledger", "evidence_clock_start")


def _clock_path(family: str, root: Path | str | None) -> Path:
    from lib import config  # local import — mirrors engine/qledger.py's own _root()
    base = Path(root) if root else config.ROOT
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in str(family))
    return base.joinpath(*_CLOCK_DIR, f"{safe}.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any] | None:
    """The existing record, or None when absent/unreadable.

    Unreadable (corrupt JSON, permission error) is treated as ABSENT for the
    write-once gate below rather than raising — a start timestamp is small,
    inspectable, human-diffable text; a truly corrupted file is a repo-hygiene
    problem to fix by hand, not a reason to crash the nightly. It is logged
    loudly (never silently) so the corruption is visible."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("qledger_evidence_clock: %s is unreadable (%s) — treating as absent "
                   "for the write-once gate; this file needs manual attention", path, exc)
        return None
    return raw if isinstance(raw, dict) else None


def read_start(family: str, root: Path | str | None = None) -> dict[str, Any] | None:
    """The recorded first-prospective-registration record for `family`, or None
    if the evidence clock has not started for it yet."""
    return _read(_clock_path(family, root))


def record_start(family: str, *, horizon_d: int, horizon_unit: str,
                 git_sha: str | None = None, root: Path | str | None = None,
                 now: str | None = None) -> dict[str, Any]:
    """WRITE-ONCE: record `family`'s first prospective-registration instant.

    If `family` already has a record, it is returned UNCHANGED — every argument
    here (horizon_d, horizon_unit, git_sha, now) is ignored on a second call.
    This is the entire contract: nothing may move a family's evidence-clock
    start once it exists, no matter what a later run passes.

    Never raises: an unwritable clock file must not sink a registration run
    that otherwise succeeded (the claims themselves are the record that
    matters most; this is a durable ANNOTATION on top of them). A write
    failure is logged loudly and the caller gets back the record it TRIED to
    write (not persisted) so a test/caller can still see what would have been
    recorded.
    """
    path = _clock_path(family, root)
    existing = _read(path)
    if existing is not None and existing.get("first_prospective_registration_utc"):
        return existing
    record: dict[str, Any] = {
        "claim_family": family,
        "first_prospective_registration_utc": now or _now_iso(),
        "declared_horizon_d": int(horizon_d),
        "horizon_unit": horizon_unit,
        "git_sha": git_sha,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)          # atomic on POSIX — no reader ever sees a half-written file
    except Exception as exc:  # noqa: BLE001 — never sink registration over an annotation write
        log.error("qledger_evidence_clock: could not persist start record for %s: %s",
                 family, exc)
        print(f"::error title={family}-evidence-clock-write-failed::qledger evidence-clock "
             f"start for {family} could not be written: {exc}", flush=True)
    return record


def git_sha(root: Path | str | None = None) -> str | None:
    """Best-effort current commit SHA — `GITHUB_SHA` first (set on every Actions
    run, cheap and exact), then `git rev-parse HEAD` as a local fallback. None,
    never raises, when neither source is available."""
    import os
    env_sha = os.environ.get("GITHUB_SHA")
    if env_sha:
        return env_sha.strip()
    try:
        import subprocess  # noqa: PLC0415
        from lib import config  # noqa: PLC0415
        base = Path(root) if root else config.ROOT
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(base),
                             capture_output=True, text=True, timeout=5, check=False)
        sha = (out.stdout or "").strip()
        return sha or None
    except Exception:  # noqa: BLE001
        return None
