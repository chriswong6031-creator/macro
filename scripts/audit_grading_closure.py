"""Standing audit: grading-closure status for every declared forward ledger.

NW Rails Program §7 PR-6 (R2 audit) — RUL-P10 path b.

Walks the declared inventory of forward ledgers (seeded from the 2026-07-06
census) and for each reports:
  - storage        : local-present | absent-by-design
  - grader_wired   : Y | N (+ every wired module path, comma-separated)
  - graders        : list of wired grader module paths (machine-readable)
  - n_logged       : rows / entries in the ledger store
  - n_graded       : rows with a matured outcome
  - last_graded_at : ISO string of the latest grade timestamp, or null
  - tune_step      : Y | N  (auto-tune loop present and wired)
  - verdict        : CLOSED | GRADER-STARVED | LOG-ONLY

Verdict rules
-------------
  CLOSED         : grader wired AND n_logged > 0 AND n_graded > 0
  GRADER-STARVED : grader wired AND n_logged > 0 AND n_graded == 0
                   (loop complete but grades not matured yet)
  LOG-ONLY       : no grader module references this ledger path

Writes:
  data/governance/grading_closure.json   (git-committed, single-writer)
  docs/GRADING_CLOSURE.md                (regenerated from json)

Wired as an end-of-collect audit step — must finish in seconds and NEVER
raise (wrapped identical to other end-of-collect safety-net steps).

Usage:
    python -m scripts.audit_grading_closure           # writes both outputs
    python -m scripts.audit_grading_closure --check   # prints, no writes
    python -m scripts.audit_grading_closure --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("audit_grading_closure")

# ---------------------------------------------------------------------------
# LEDGER INVENTORY
# ---------------------------------------------------------------------------
# Each entry:
#   key          : short ledger id (snake_case)
#   path         : relative path from repo root to the ledger file / dir
#   format       : jsonl | parquet | parquet_dir (per-compound dir)
#   graders      : LIST of module paths that grade this ledger; [] = LOG-ONLY.
#                  One-to-many since 2026-08-14: a ledger can carry an engine-local
#                  grader AND a shared cross-engine grader, and naming only one of
#                  them told evidence-gathering sessions the other did not exist.
#                  (`grader: <str|None>` is still accepted as a legacy single-value
#                  alias so hand-built specs and older callers keep working.)
#   grade_field  : field/column whose presence signals a graded row, or None
#   grade_ts_field : field containing the grade timestamp, or None
#   tune_step    : True if an auto-tune loop is wired after the grader
#   storage_note : if absent-by-design (e.g. R2-only or reversion_forward
#                  directory not yet seeded), record reason here; else None
# ---------------------------------------------------------------------------
INVENTORY: list[dict[str, Any]] = [
    # ── qledger ─────────────────────────────────────────────────────────────
    {
        "key": "qledger_claims",
        "path": "data/qledger/claims.jsonl",
        "format": "jsonl",
        "graders": ["scripts/grade_qledger.py"],
        "grade_field": None,      # grades are a SEPARATE file (grades.jsonl)
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "qledger_grades",
        "path": "data/qledger/grades.jsonl",
        "format": "jsonl",
        "graders": ["scripts/grade_qledger.py"],
        "grade_field": "graded_at",   # every row IS a grade
        "grade_ts_field": "graded_at",
        "tune_step": False,
        "storage_note": None,
    },
    # ── US board ledger ──────────────────────────────────────────────────────
    {
        "key": "board_ledger_hk",
        "path": "data/board_ledger/hk_board.parquet",
        "format": "parquet",
        "graders": ["engine/board_ledger.py"],
        "grade_field": "fwd_mfe_21",       # nullable col; non-null = graded
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "board_ledger_ca",
        "path": "data/board_ledger/ca_board.parquet",
        "format": "parquet",
        "graders": ["engine/board_ledger.py"],
        "grade_field": "fwd_mfe_21",
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "us_board_ledger",
        "path": "data/us_board_ledger/retro_grades.parquet",
        "format": "parquet",
        "graders": ["scripts/grade_us_board.py"],
        "grade_field": "excess_spy",       # non-null = graded (every row is a grade)
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "signal_archive_track_record",
        "path": "data/signal_archive/track_record.parquet",
        "format": "parquet",
        "graders": ["engine/track_record.py"],
        "grade_field": "fwd_ret_20",       # nullable; non-null = graded row
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── China standout track ─────────────────────────────────────────────────
    {
        "key": "china_standout_track",
        "path": "data/china_standout_track/board.parquet",
        "format": "parquet",
        "graders": ["engine/china_standout_track.py"],
        "grade_field": "fwd_mfe_21",
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── Cycle forward logs ───────────────────────────────────────────────────
    {
        "key": "sector_cycles_forward_log",
        "path": "data/sector_cycles/forward_log.parquet",
        "format": "parquet",
        "graders": ["scripts/grade_promises.py"],
        "grade_field": None,      # grade_promises uses a separate scorecard dir
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "china_sector_cycles_forward_log",
        "path": "data/china_sector_cycles/forward_log.parquet",
        "format": "parquet",
        # TWO graders read this ledger, and until 2026-08-14 only the first was
        # named — which read as "the promise-grader does not cover CN".
        #   engine/china_sector_cycles_grader.py — CN-specific drawdown/return/
        #     calibration channels; published to site/chinasectordata/cycles_scorecard.json
        #     by scripts/build_china_cycles_scorecard.py (asia-close lane).
        #   scripts/grade_promises.py — the SHARED cycle promise-grader; china_sector_cycles
        #     is in its ENGINES list and is graded on the same gates as the US/country
        #     siblings, into data/china_sector_cycles/scorecards/promises_<epoch>.json.
        #     That is the scorecard dir n_graded is actually read from below, so the
        #     old single-grader entry credited these grades to the wrong module.
        "graders": [
            "engine/china_sector_cycles_grader.py",
            "scripts/grade_promises.py",
        ],
        "grade_field": None,      # graders output to scorecards, not an in-ledger column
        "grade_ts_field": None,
        "tune_step": False,       # explicitly no-tune per grader comment
        "storage_note": None,
    },
    {
        "key": "country_cycles_forward_log",
        "path": "data/country_cycles/forward_log.parquet",
        "format": "parquet",
        "graders": ["scripts/grade_promises.py"],
        "grade_field": None,
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── Breadth divergence ───────────────────────────────────────────────────
    {
        "key": "breadth_divergence_forward_log",
        "path": "data/breadth_divergence/forward_log.parquet",
        "format": "parquet",
        # PR-A2: nightly grader wired in scripts/grade_breadth_divergence.py,
        # called from collect.py end-of-collect block.  Grades rows whose h21
        # outcome window has matured; idempotent.  Verdict = GRADER-STARVED until
        # the first stamp matures (~21 business days after first elevated/high fire).
        "graders": ["scripts/grade_breadth_divergence.py"],
        "grade_field": "fwd_dd",      # nullable float; non-null = graded
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── Risk radar ───────────────────────────────────────────────────────────
    {
        "key": "risk_radar_forward_log",
        "path": "data/risk_radar/forward_log.jsonl",
        "format": "jsonl",
        # PR-A2 (§0.5.1): US grader IS wired — engine/risk_radar_audit.py
        # grade_log/scorecard/snapshot_and_grade called from engine/run.py:614.
        # Prior None was a hardcoded inventory error; verdict = GRADER-STARVED
        # (time-starved: n=8 rows, none matured to h21 yet as of 2026-07-06).
        "graders": ["engine/risk_radar_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_cn",
        "path": "data/risk_radar_intl/cn_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,        # engine/risk_radar_intl_tune.py wired in build
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_hk",
        "path": "data/risk_radar_intl/hk_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_ca",
        "path": "data/risk_radar_intl/ca_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_kr",
        "path": "data/risk_radar_intl/kr_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_jp",
        "path": "data/risk_radar_intl/jp_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_tw",
        "path": "data/risk_radar_intl/tw_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_in",
        "path": "data/risk_radar_intl/in_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_au",
        "path": "data/risk_radar_intl/au_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_gb",
        "path": "data/risk_radar_intl/gb_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    {
        "key": "risk_radar_intl_ez",
        "path": "data/risk_radar_intl/ez_forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/risk_radar_intl_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,
        "storage_note": None,
    },
    # ── Market state ─────────────────────────────────────────────────────────
    {
        "key": "market_state_forward_log",
        "path": "data/market_state/forward_log.jsonl",
        "format": "jsonl",
        "graders": ["engine/market_state_audit.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": True,        # engine/market_state_tune.py wired in build_site
        "storage_note": None,
    },
    # ── Oracle ───────────────────────────────────────────────────────────────
    {
        "key": "oracle_forward_ledger",
        "path": "data/oracle/forward_ledger.jsonl",
        "format": "jsonl",
        "graders": ["scripts/oracle_nightly.py"],
        "grade_field": None,      # forward detections; not a graded outcomes store
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "oracle_compounds_live_ledger",
        "path": "data/oracle/compounds/live_ledger.jsonl",
        "format": "jsonl",
        "graders": ["scripts/oracle_nightly.py"],
        "grade_field": "excess_21d",   # nullable; non-null after maturity
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "oracle_reversion_forward",
        "path": "data/oracle/reversion_forward",
        "format": "parquet_dir",  # per-compound JSONL files
        "graders": ["scripts/oracle_reversion_forward_ledger.py"],
        "grade_field": "matured",   # boolean field; True = graded
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": "absent-by-design: seeded only after first reversion compound passes gauntlet",
    },
    # ── BTC override ledger ──────────────────────────────────────────────────
    {
        "key": "btc_override_ledger",
        "path": "data/vector/override_ledger.jsonl",
        "format": "jsonl",
        "graders": ["engine/btc_override_ledger.py"],
        "grade_field": None,     # subclaims graded via override_scored.json sidecar
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── Foresight ────────────────────────────────────────────────────────────
    {
        "key": "foresight_log",
        "path": "data/foresight/log.jsonl",
        "format": "jsonl",
        "graders": ["engine/foresight_grader.py"],
        "grade_field": None,     # grader outputs to data/foresight/track_record.json
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "foresight_policy_calendar_ledger",
        "path": "data/foresight/policy_calendar_ledger.jsonl",
        "format": "jsonl",
        # PR-A2 (GO-IF-TRIVIAL): date-accuracy grader wired in
        # scripts/grade_policy_calendar.py (called from collect.py end-of-collect).
        # After next_comment_close_date passes, checks federal_register/documents.parquet
        # for whether the predicted comment-close event occurred (accurate bool).
        # Verdict = GRADER-STARVED until first matured entry (~2026-08-01 earliest).
        "graders": ["scripts/grade_policy_calendar.py"],
        "grade_field": "graded_date",    # ISO date string; non-null = graded
        "grade_ts_field": "graded_date",
        "tune_step": False,
        "storage_note": None,
    },
    # ── Froth fragility ──────────────────────────────────────────────────────
    {
        "key": "froth_fragility_log",
        "path": "data/froth_fragility/log.jsonl",
        "format": "jsonl",
        "graders": ["engine/froth_fragility.py"],
        "grade_field": "graded",
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    # ── Species ledgers ──────────────────────────────────────────────────────
    # Species bind to existing ledgers (us_board_ledger, china_standout_track,
    # or named signal_archive paths). The species registry itself is a config
    # file, not a forward ledger — it is captured here for completeness.
    {
        "key": "species_registry",
        "path": "data/species/registry.json",
        "format": "json",
        "graders": ["engine/species_registry.py"],
        "grade_field": None,     # registry config; outcomes ride the bound ledgers
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": None,
    },
    {
        "key": "species_antichase_shadow_ledger",
        "path": "data/signal_archive/antichase_shadow_ledger.parquet",
        "format": "parquet",
        "graders": ["engine/species_registry.py"],
        "grade_field": None,
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": "absent-by-design: seeded when F3_ANTICHASE species accrues its first ledger row",
    },
    {
        "key": "species_f1d_shadow_ledger",
        "path": "data/signal_archive/f1d_shadow_ledger.parquet",
        "format": "parquet",
        "graders": ["engine/species_registry.py"],
        "grade_field": None,
        "grade_ts_field": None,
        "tune_step": False,
        "storage_note": "absent-by-design: seeded when EI-F1D-RW species accrues its first ledger row",
    },
    # ── BD-AVOID-1 Phase-1 forward ledger (L1 Short-Side Lobe) ──────────────
    # Mac-side ops lane; pre-registered 2026-07-06.
    # Verdict floor: n>=300 events/side; come-back BD-2>=2026-10-01, BD-3>=2027-01-01.
    # Long-side (clean8_21) feeds verdict; short-side grades are quarantined (RUL-3).
    {
        "key": "bd_avoid1_ledger",
        "path": "data/research/bd_avoid1_ledger.parquet",
        "format": "parquet",
        "graders": ["scripts/research/bd_avoid1_stamper.py"],
        "grade_field": "long_state_clean8_21",  # non-null = graded at 21d horizon
        "grade_ts_field": "stamped_at",
        "tune_step": False,
        "storage_note": (
            "absent-by-design until first ops-lane stamp run; "
            "Mac-local only (requires massive_stock_day + replay_boarded)"
        ),
    },
]


# ---------------------------------------------------------------------------
# CYCLE PROMISE-GRADER SCORECARDS
# ---------------------------------------------------------------------------
# The three cycle engines graded by scripts/grade_promises.py (its ENGINES list)
# keep their grades in data/<engine>/scorecards/promises_<epoch>.json rather than
# in a ledger column, so n_graded is read from the scorecard's n_stamps_total.
# ledger key -> data/<engine>/ directory name.  Cross-checked against the real
# ENGINES list by tests/test_audit_grading_closure.py: adding an engine there
# without wiring it here (or without naming grade_promises among that ledger's
# `graders`) fails the suite.
PROMISE_SCORECARD_ENGINES: dict[str, str] = {
    "sector_cycles_forward_log": "sector_cycles",
    "country_cycles_forward_log": "country_cycles",
    "china_sector_cycles_forward_log": "china_sector_cycles",
}

PROMISE_GRADER = "scripts/grade_promises.py"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def spec_graders(spec: dict) -> list[str]:
    """Normalise a spec's grader declaration to a list of module paths.

    Accepts the canonical `graders: [...]` and the legacy single-value
    `grader: <str|None>` alias (hand-built specs, older callers). Order is
    preserved and duplicates are dropped; [] means LOG-ONLY.
    """
    raw = spec.get("graders")
    if raw is None:
        legacy = spec.get("grader")
        raw = [legacy] if legacy else []
    elif isinstance(raw, str):     # tolerate a bare string in `graders`
        raw = [raw]

    out: list[str] = []
    for g in raw:
        if g and g not in out:
            out.append(str(g))
    return out


def _grader_wired(graders: list[str]) -> str:
    """Render the grader_wired cell: 'N', or 'Y:' + every wired module path.

    The 'Y' prefix is load-bearing — scripts/build_measurement.py derives the
    RUL-4 TIME-vs-BUILD starvation column from `grader_wired.upper().startswith('Y')`.
    """
    return ("Y:" + ",".join(graders)) if graders else "N"


def _read_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file; return empty list on any failure."""
    try:
        lines = path.read_text().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _read_parquet_rows(path: Path) -> int:
    """Return row count of a parquet file; -1 on failure."""
    try:
        import pandas as pd
        return len(pd.read_parquet(path))
    except Exception:
        return -1


def _parquet_grade_count(path: Path, grade_field: str | None) -> int:
    """Count non-null rows in grade_field of a parquet file."""
    if grade_field is None:
        return 0
    try:
        import pandas as pd
        df = pd.read_parquet(path, columns=[grade_field])
        return int(df[grade_field].notna().sum())
    except Exception:
        return 0


def _jsonl_last_ts(rows: list[dict], ts_field: str) -> str | None:
    """Return max value of ts_field across rows (all non-null strings)."""
    vals = [r[ts_field] for r in rows if r.get(ts_field)]
    return max(vals) if vals else None


def _verdict(entry: dict, graders: list[str], n_logged: int, n_graded: int) -> str:
    """Classify verdict from parameters."""
    if not graders:
        return "LOG-ONLY"
    if n_logged > 0 and n_graded == 0:
        return "GRADER-STARVED"
    if n_logged > 0 and n_graded > 0:
        return "CLOSED"
    # grader wired but no rows yet (absent-by-design or empty)
    return "GRADER-STARVED"


# ---------------------------------------------------------------------------
# CORE AUDIT
# ---------------------------------------------------------------------------

def audit_entry(spec: dict, root: Path) -> dict:
    """Audit one ledger entry; return a result dict."""
    key = spec["key"]
    rel = spec["path"]
    fmt = spec["format"]
    graders = spec_graders(spec)
    grade_field = spec.get("grade_field")
    grade_ts_field = spec.get("grade_ts_field")
    tune_step = bool(spec.get("tune_step", False))
    storage_note = spec.get("storage_note")

    p = root / rel

    # --- storage status ---
    if fmt == "parquet_dir":
        exists = p.is_dir() and any(p.glob("*.jsonl"))
    else:
        exists = p.is_file()

    if not exists:
        storage = storage_note if storage_note else "absent-locally"
        return {
            "key": key,
            "path": rel,
            "storage": storage,
            "grader_wired": _grader_wired(graders),
            "graders": graders,
            "n_logged": 0,
            "n_graded": 0,
            "last_graded_at": None,
            "tune_step": "Y" if tune_step else "N",
            "verdict": "LOG-ONLY" if not graders else "GRADER-STARVED",
        }

    # --- count logged / graded ---
    n_logged = 0
    n_graded = 0
    last_graded_at = None

    try:
        if fmt == "jsonl":
            rows = _read_jsonl(p)
            n_logged = len(rows)
            if grade_field:
                # non-null / truthy graded field = graded
                n_graded = sum(1 for r in rows if r.get(grade_field) is not None and r.get(grade_field) is not False)
            if grade_ts_field:
                last_graded_at = _jsonl_last_ts(rows, grade_ts_field)

        elif fmt == "parquet":
            n_logged = _read_parquet_rows(p)
            if grade_field:
                n_graded = _parquet_grade_count(p, grade_field)

        elif fmt == "parquet_dir":
            # per-compound JSONL directory (oracle reversion_forward)
            for f in sorted(p.glob("*.jsonl")):
                rows_f = _read_jsonl(f)
                n_logged += len(rows_f)
                if grade_field:
                    n_graded += sum(1 for r in rows_f if r.get(grade_field))

        elif fmt == "json":
            # single-file JSON (species registry, foresight track_record)
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and "species" in data:
                    n_logged = len(data["species"])
                elif isinstance(data, dict):
                    n_logged = 1
                elif isinstance(data, list):
                    n_logged = len(data)
            except Exception:
                n_logged = 1  # file exists, parseable count uncertain

    except Exception as exc:  # noqa: BLE001
        log.warning("audit_grading_closure: ledger read failed for %s: %s", key, exc)

    # --- grade sidecar lookups for special cases ---
    # qledger_claims: look up grade count from grades.jsonl
    if key == "qledger_claims":
        grades_p = root / "data" / "qledger" / "grades.jsonl"
        if grades_p.exists():
            grade_rows = _read_jsonl(grades_p)
            n_graded = len(grade_rows)
            ts_vals = [r.get("graded_at") for r in grade_rows if r.get("graded_at")]
            last_graded_at = max(ts_vals) if ts_vals else None

    # foresight_log: look up graded count from track_record.json
    if key == "foresight_log":
        tr_p = root / "data" / "foresight" / "track_record.json"
        if tr_p.exists():
            try:
                tr = json.loads(tr_p.read_text())
                n_graded = int(tr.get("n_graded") or 0)
                last_graded_at = tr.get("updated")
            except Exception:
                pass

    # oracle_forward_ledger: not an outcome store — check forward_ledger.jsonl grading
    # via the oracle_nightly outcome pass (no direct graded field; register as 0)
    if key == "oracle_forward_ledger":
        n_graded = 0  # forward detections; outcome grading in compounds/live_ledger

    # btc_override_ledger: outcomes in override_scored.json sidecar
    if key == "btc_override_ledger":
        scored_p = root / "data" / "vector" / "override_scored.json"
        if scored_p.exists():
            try:
                sc = json.loads(scored_p.read_text())
                subclaims = sc.get("subclaims") or {}
                n_graded = sum(1 for v in subclaims.values()
                               if v.get("status") not in (None, "PENDING"))
                last_graded_at = sc.get("as_of")
            except Exception:
                pass

    # Cycle promise-graders: grades live in data/<engine>/scorecards/, not in the
    # ledger, so n_graded is read from the scorecard's n_stamps_total.  All three
    # engines are graded by scripts/grade_promises.py (its ENGINES list) — china
    # used to be a duplicated branch below, keyed off a grader that publishes
    # somewhere else entirely.  Explicit map, not a substring test: "sector" is in
    # BOTH sector_cycles_forward_log and china_sector_cycles_forward_log.
    sc_engine = PROMISE_SCORECARD_ENGINES.get(key)
    if sc_engine:
        sc_dir = root / "data" / sc_engine / "scorecards"
        if sc_dir.is_dir() and list(sc_dir.glob("*.json")):
            # scorecards exist — grader has run; count n_stamps_total as n_graded proxy
            try:
                sc_file = next(sc_dir.glob("*.json"))
                sc_data = json.loads(sc_file.read_text())
                n_graded = int(sc_data.get("n_stamps_total") or 0)
                last_graded_at = sc_data.get("as_of")
            except Exception:
                n_graded = 1  # scorecard exists but unreadable — grader has run

    verdict = _verdict(spec, graders, n_logged, n_graded)

    return {
        "key": key,
        "path": rel,
        "storage": "present" if exists else (storage_note or "absent-locally"),
        "grader_wired": _grader_wired(graders),
        "graders": graders,
        "n_logged": n_logged,
        "n_graded": n_graded,
        "last_graded_at": last_graded_at,
        "tune_step": "Y" if tune_step else "N",
        "verdict": verdict,
    }


def run(root: Path | None = None, write: bool = True) -> dict:
    """Run the full grading-closure audit.  Returns summary dict."""
    t0 = time.monotonic()
    if root is None:
        # resolve relative to this file's grandparent
        root = Path(__file__).resolve().parent.parent

    results: list[dict] = []
    for spec in INVENTORY:
        try:
            results.append(audit_entry(spec, root))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit_grading_closure: entry %s crashed: %s", spec["key"], exc)
            results.append({
                "key": spec["key"], "path": spec["path"],
                "storage": "error", "grader_wired": "?", "graders": [],
                "n_logged": 0, "n_graded": 0,
                "last_graded_at": None, "tune_step": "N",
                "verdict": "LOG-ONLY",
            })

    # --- summary counts ---
    closed = sum(1 for r in results if r["verdict"] == "CLOSED")
    starved = sum(1 for r in results if r["verdict"] == "GRADER-STARVED")
    log_only = sum(1 for r in results if r["verdict"] == "LOG-ONLY")

    payload = {
        # v1 retained: `graders` is purely ADDITIVE and grader_wired keeps its
        # 'Y'/'N' contract (it now names every wired module, comma-separated,
        # instead of only the first). Read `graders` in preference to splitting
        # grader_wired — that is the machine-readable form.
        "schema": "grading_closure.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_ledgers": len(results),
        "n_closed": closed,
        "n_grader_starved": starved,
        "n_log_only": log_only,
        "ledgers": results,
    }

    elapsed = time.monotonic() - t0
    log.info(
        "grading_closure audit: %d ledgers — %d CLOSED / %d GRADER-STARVED / "
        "%d LOG-ONLY (%.2fs)",
        len(results), closed, starved, log_only, elapsed,
    )

    if write:
        _write_json(payload, root)
        _write_md(payload, root)

    return payload


# ---------------------------------------------------------------------------
# WRITERS
# ---------------------------------------------------------------------------

def _write_json(payload: dict, root: Path) -> None:
    """Write data/governance/grading_closure.json."""
    out = root / "data" / "governance" / "grading_closure.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, separators=(",", ": ")))
        log.info("grading_closure: wrote %s", out)
    except Exception as exc:  # noqa: BLE001
        log.warning("grading_closure: json write failed: %s", exc)


def _write_md(payload: dict, root: Path) -> None:
    """Write / overwrite docs/GRADING_CLOSURE.md."""
    lines: list[str] = []
    lines.append("# Grading Closure — Forward Ledger Audit")
    lines.append("")
    lines.append(
        f"Generated: {payload['generated_at']}  "
        f"— {payload['n_ledgers']} ledgers  "
        f"— {payload['n_closed']} CLOSED / "
        f"{payload['n_grader_starved']} GRADER-STARVED / "
        f"{payload['n_log_only']} LOG-ONLY"
    )
    lines.append("")
    lines.append(
        "**Verdict key:**  "
        "CLOSED = grader wired + n_graded > 0;  "
        "GRADER-STARVED = grader wired but 0 grades (not yet matured);  "
        "LOG-ONLY = no grader (fixes are per-program follow-ups, not this rail)."
    )
    lines.append("")
    # table header
    lines.append("| Ledger | Storage | Grader(s) | n_logged | n_graded | last_graded_at | Tune | Verdict |")
    lines.append("|--------|---------|-----------|----------|----------|----------------|------|---------|")
    for r in payload["ledgers"]:
        grader_cell = r["grader_wired"]
        if grader_cell.startswith("Y:"):
            # one-to-many: every wired module gets its own backticked cell entry
            modules = [m for m in grader_cell[2:].split(",") if m]
            grader_cell = "Y: " + ", ".join(f"`{m}`" for m in modules)
        last = r["last_graded_at"] or "—"
        if last and len(last) > 19:
            last = last[:19]  # truncate to datetime without TZ noise
        verdict = r["verdict"]
        verdict_fmt = (
            f"**{verdict}**" if verdict == "CLOSED"
            else (f"*{verdict}*" if verdict == "GRADER-STARVED" else verdict)
        )
        lines.append(
            f"| `{r['key']}` | {r['storage']} | {grader_cell} "
            f"| {r['n_logged']} | {r['n_graded']} | {last} "
            f"| {r['tune_step']} | {verdict_fmt} |"
        )

    lines.append("")
    lines.append("> Source of truth: `data/governance/grading_closure.json`")
    lines.append("> Generated by `scripts/audit_grading_closure.py` (end-of-collect step).")
    lines.append("")

    out = root / "docs" / "GRADING_CLOSURE.md"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        log.info("grading_closure: wrote %s", out)
    except Exception as exc:  # noqa: BLE001
        log.warning("grading_closure: md write failed: %s", exc)


# ---------------------------------------------------------------------------
# COLLECT STEP HOOK
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise; wraps run() in a broad except."""
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        log.error("[grading_closure] audit crashed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="print results without writing outputs")
    ap.add_argument("--root", default=None,
                    help="repo root (default: parent of scripts/)")
    ap.add_argument("--json", action="store_true",
                    help="print JSON summary to stdout")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    root = Path(args.root) if args.root else None
    payload = run(root=root, write=not args.check)

    if args.json or args.check:
        print(json.dumps(payload, indent=2))
    else:
        # compact table
        print(f"\nGrading Closure Audit — {payload['generated_at'][:10]}")
        print(f"  {payload['n_ledgers']} ledgers: "
              f"{payload['n_closed']} CLOSED / "
              f"{payload['n_grader_starved']} GRADER-STARVED / "
              f"{payload['n_log_only']} LOG-ONLY\n")
        fmt = "{:<40} {:>8} {:>8}  {}"
        print(fmt.format("Ledger", "n_log", "n_grade", "Verdict"))
        print("-" * 70)
        for r in payload["ledgers"]:
            print(fmt.format(r["key"][:40], r["n_logged"], r["n_graded"], r["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
