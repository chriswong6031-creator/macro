#!/usr/bin/env python3
"""Stock Identity W3A — the one-time PR-3 ruler-constant setting act (plan Task 3C
Steps 2, 3, 5). Runs ONLY after the calibration-fire substrate (Step 4) exists.

Rule-before-value discipline (W1's ``scripts/stock_identity_calibrate.py`` law,
reused verbatim): each PR-3 constant's selection rule is declared as a frozen
string constant BELOW, in code, and its sha256 is recorded in the W3 registration
BEFORE any value is computed from partition data. Declared ±20% diagnostic
sensitivity grids are registered in the TrialLedger before execution; they are
NEVER used to re-pick a constant. This script is a ONE-TIME act: a second
invocation refuses (the shipped spec no longer carries the pending sentinel).

Before computing anything, this script verifies the substrate's own provenance
covers the FULL drawn roster (never a partial one) and re-checks the
recent-history guard against the substrate's own provenance fields (freeze
review findings B1/B3) — a substrate directory built by a sampled/estimate-only
run, or one whose bars leaked past the calibration clock's cutoff, is refused
with a typed error rather than silently computed over.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity.ruler import (  # noqa: E402
    GRAIN_CLASSES,
    PR3_PENDING_SENTINEL,
    RulerSpec,
    aggregate_cell_metrics,
    compute_fire_metrics,
)
from engine.trial_ledger import TrialLedger  # noqa: E402
from scripts.stock_identity_calibration_replay import (  # noqa: E402
    RecentHistoryGuardViolation,
    _partition_manifest,
    assert_disjoint_from_pilot_and_blind,
    assert_recent_history_guard,
    drawn_roster,
    recent_history_cutoff,
    truncate_to_guard,
)

DATA = REPO_ROOT / "data" / "stock_identity"
RULER_DIR = DATA / "ruler"
SPEC_PATH = RULER_DIR / "ruler_spec_v1.json"
REPLAY_MANIFEST_PATH = RULER_DIR / "calibration_replay_manifest_v1.json"
REGISTRATION_PATH = REPO_ROOT / "research" / "stock_identity" / "W3_RULER_REGISTRATION.md"

TRIAL_FAMILY = "stock_identity_w3_ruler_calibration"


class PartialSubstrateError(RuntimeError):
    """Raised when the calibration substrate's provenance does not prove
    coverage of the FULL drawn roster (freeze review finding B1) — refuses
    BEFORE computing anything from partition data, rather than silently
    computing a constant off a partial roster."""


#: B4 disclosure (adversarial review, REPAIR-BEFORE-SEAL): this repair does NOT
#: change either rule's FORM — that decision belongs to Sol, not this packet.
#: What changes is disclosure: the review previewed pilot/partial-derived values
#: for these exact rule forms (lambda_fs=1.5, recall_floor=0.0 — design-tier
#: material, SI-SEALED-CAL-P1 unread) BEFORE this repair landed. Those previews
#: are VOID: they were never computed under receipted rule text against the real
#: substrate, and neither rule form may be treated as accepted until Sol rules on
#: it. Both declarations below carry this status explicitly, and it is echoed
#: into every receipt/report this script emits. See
#: W3_RULER_REGISTRATION.md §"Rule-review disclosure".
RULE_REVIEW_STATUS = "declared_pending_sol_rule_review"

#: --- rule-before-value: the exact selection rule for each PR-3 constant, declared
#: as frozen text BEFORE any value exists. Hashing this string is what proves the
#: rule predates the value (the hash is recorded in the registration in Step 2,
#: before Step 4/5 ever run against partition data). UNCHANGED by this repair
#: (status: declared_pending_sol_rule_review, RULE_REVIEW_STATUS above). The
#: SELECTION MATH (P25 of recall_at_tier, rounded to 0.05) is unchanged by this
#: repair. The population-wording clause below WAS corrected (MINORS finding:
#: "align rule-text population wording with implementation") to name the exact
#: predicate ``compute_recall_floor`` has always applied
#: (``cells["n_episodes"] > 0`` — a cell with at least one FIRE, per
#: ``aggregate_cell_metrics``' own fired-episode count) rather than the prior
#: prose's inaccurate "tier-eligible episode" description (that population is a
#: DIFFERENT, unrelated quantity — B2's fix to recall_at_tier's own denominator).
#: This is a textual accuracy fix, not a rule-form change: no computed value
#: exists yet to void, and the corrected text describes the SAME code path that
#: has run unchanged throughout. Its hash necessarily changed and is re-recorded
#: in W3_RULER_REGISTRATION.md §3.1.
RECALL_FLOOR_RULE = (
    "recall_floor = the 25th percentile (P25) of the cell-level recall_at_tier "
    "distribution, computed over every (family_key, episode_type, grain) cell in "
    "the calibration-fire substrate for which n_episodes > 0 (aggregate_cell_metrics' "
    "own count of that cell's distinct FIRED episodes -- i.e. a cell with at least "
    "one fire; this is the population filter compute_recall_floor has always "
    "applied via cells['n_episodes'] > 0, and is a DIFFERENT quantity from the "
    "tier-eligible-episode set recall_at_tier's own denominator is computed over), "
    "rounded to the nearest 0.05. A cell below this floor is judged too rarely "
    "localized for C-LOC-D to be graded. The rule references only the POPULATION "
    "of measured cells and never any expert's own outcome rank "
    "(DNR:KILL-OUTCOME-AUDITION)."
)

LAMBDA_FS_RULE = (
    "lambda_fs = 1 / max(P75(false_start_rate), 0.01), rounded to the nearest 0.25, "
    "where P75(false_start_rate) is the 75th percentile of the cell-level "
    "false_start_rate distribution computed over every (family_key, episode_type, "
    "grain) cell in the calibration-fire substrate with at least one fire. The "
    "penalty scale is calibrated so a cell at the empirical P75 false-start rate "
    "loses approximately one full composite point. The rule references only the "
    "POPULATION distribution of false_start_rate and never any expert's own "
    "outcome rank (DNR:KILL-OUTCOME-AUDITION)."
)

#: The declared ±20% diagnostic sensitivity grid (Step 3) — registered in the
#: TrialLedger BEFORE execution. Diagnostic only: these variants are NEVER read
#: back to choose a different base value than the one the rules above compute.
DIAGNOSTIC_GRID: list[dict[str, str]] = [
    {"constant": "recall_floor", "variant": v} for v in ("base", "minus20", "plus20")
] + [
    {"constant": "lambda_fs", "variant": v} for v in ("base", "minus20", "plus20")
]

#: The W5Q confirmatory fit-read look budget, logged at this same registration
#: (freeze §4.1: "the later fit-read look budget is logged"). One look each for
#: Q1, Q2, Q3 — the frozen §14.1 questions this program may confirmatory-read once.
FIT_READ_LOOK_BUDGET = 3
FIT_READ_LOOK_BUDGET_REASON = (
    "one confirmatory look each for Q1 (Channel-A OOS), Q2 (neighborhood transfer), "
    "Q3 (Channel-C residual value) — freeze §4.4 'execute the frozen Q1-Q3 ... once, "
    "without rescue tuning'"
)


def rule_hash(rule_text: str) -> str:
    return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()


def register_rules_and_grid(ledger: TrialLedger, *, info_cutoff: str) -> dict[str, Any]:
    """Step 2 + Step 3: record rule hashes and register the diagnostic grid + the
    fit-read look budget, all BEFORE Step 4/5 touch partition data. NEVER called
    in ``--dry-run`` mode (dry-run must not write to the shared TrialLedger)."""
    n_new = ledger.log_grid(
        DIAGNOSTIC_GRID, family=TRIAL_FAMILY, info_cutoff=info_cutoff,
        source="w3_pr3_diagnostic_grid",
        note="declared +/-20% sensitivity grid for the PR-3 ruler-composite constants; "
             "diagnostic only, never used to re-pick a constant",
    )
    ledger.log_declared_budget(
        FIT_READ_LOOK_BUDGET, family=TRIAL_FAMILY, reason=FIT_READ_LOOK_BUDGET_REASON,
    )
    return {
        "recall_floor_rule_hash": rule_hash(RECALL_FLOOR_RULE),
        "lambda_fs_rule_hash": rule_hash(LAMBDA_FS_RULE),
        "diagnostic_grid_new_trials": n_new,
        "diagnostic_grid_effective_n": ledger.effective_n(TRIAL_FAMILY),
        "fit_read_look_budget": FIT_READ_LOOK_BUDGET,
        "rule_review_status": RULE_REVIEW_STATUS,
    }


def assert_full_roster_coverage(
    provenance: dict[str, Any], roster: list[str], manifest: dict[str, Any],
) -> None:
    """B1: before computing anything, verify the substrate's own provenance
    covers the FULL drawn roster — both that its recorded roster hash equals the
    replay manifest's ``roster_sha256`` AND that ``n_names_attempted`` equals the
    drawn roster's size. Either mismatch refuses with a typed error rather than
    silently computing a constant from a partial roster (e.g. one written by a
    ``--sample`` run of ``stock_identity_calibration_replay.py``)."""
    expected_hash = manifest["roster"]["roster_sha256"]
    recorded_hash = provenance.get("roster_sha256")
    if recorded_hash != expected_hash:
        raise PartialSubstrateError(
            f"substrate provenance roster_sha256={recorded_hash!r} does not match "
            f"the replay manifest's roster_sha256={expected_hash!r} — refuse to "
            "compute any PR-3 value from a substrate that cannot be proven to "
            "cover the drawn roster this manifest declares"
        )
    n_attempted = provenance.get("n_names_attempted")
    if n_attempted != len(roster):
        raise PartialSubstrateError(
            f"substrate provenance n_names_attempted={n_attempted!r} != drawn "
            f"roster size {len(roster)} — refuse to compute any PR-3 value from a "
            "PARTIAL roster; the calibration-fire substrate act is bounded to the "
            "FULL drawn roster only (freeze §4.1), never a sample or estimate"
        )


def compute_recall_floor(cells: pd.DataFrame) -> float:
    eligible = cells.loc[cells["n_episodes"] > 0, "recall_at_tier"].dropna()
    if eligible.empty:
        raise ValueError("no eligible cells (n_episodes>0) to compute recall_floor")
    p25 = float(np.percentile(eligible.to_numpy(dtype=float), 25))
    return round(p25 / 0.05) * 0.05


def compute_lambda_fs(cells: pd.DataFrame) -> float:
    fired = cells.loc[cells["n_fires"] > 0, "false_start_rate"].dropna()
    if fired.empty:
        raise ValueError("no fired cells (n_fires>0) to compute lambda_fs")
    p75 = max(float(np.percentile(fired.to_numpy(dtype=float), 75)), 0.01)
    raw = 1.0 / p75
    return round(raw / 0.25) * 0.25


def diagnostic_variants(base: float) -> dict[str, float]:
    """The ±20% diagnostic-only variants registered in Step 3 — printed, never used
    to reselect."""
    return {"base": base, "minus20": round(base * 0.8, 6), "plus20": round(base * 1.2, 6)}


def _fixture_spec_for_computation(atr_basis, p_pre, w, delta, theta_fs, anchor_map) -> RulerSpec:
    """A RulerSpec carrying the shipped geometry but a NON-pending pr3_status, used
    ONLY internally to drive ``compute_fire_metrics``/``aggregate_cell_metrics``
    over the calibration substrate before the real constants exist. Never written
    to disk; the shipped spec keeps the pending sentinel until this script writes
    the receipted values in Step 5."""
    return RulerSpec(
        schema="stock_identity.ruler_spec.v1", version="v1", atr_basis=atr_basis,
        p_pre_sessions=p_pre, useful_zone_window_sessions=w, useful_zone_delta_atr=delta,
        false_start_atr_threshold=theta_fs, episode_type_anchor=anchor_map,
        grain_classes=GRAIN_CLASSES, graded_composites=("c_loc_r", "c_loc_d"),
        recall_floor=None, lambda_fs=None, pr3_status="internal_calibration_pass",
        pr3_receipt=None,
        authority={"can_rank": False, "can_size": False, "can_gate": False,
                   "can_originate_signal": False, "can_escalate": False},
    )


def compute_constants_from_substrate(
    events: pd.DataFrame, attribution: pd.DataFrame, episodes: pd.DataFrame,
    bars_by_symbol: dict[str, pd.DataFrame], base_spec: RulerSpec,
) -> tuple[float, float, pd.DataFrame]:
    """Runs the ruler's own metric/aggregation math (already frozen in Tasks 2-3)
    over the guard-truncated calibration substrate, then applies the pre-declared
    rules. Returns ``(recall_floor, lambda_fs, cells)``."""
    calc_spec = _fixture_spec_for_computation(
        base_spec.atr_basis, base_spec.p_pre_sessions, base_spec.useful_zone_window_sessions,
        base_spec.useful_zone_delta_atr, base_spec.false_start_atr_threshold,
        base_spec.episode_type_anchor,
    )
    fire_metrics = compute_fire_metrics(events, attribution, episodes, bars_by_symbol, calc_spec)
    cells = aggregate_cell_metrics(fire_metrics, episodes, calc_spec)
    recall_floor = compute_recall_floor(cells)
    lambda_fs = compute_lambda_fs(cells)
    return recall_floor, lambda_fs, cells


def seal_ruler_spec(
    recall_floor: float, lambda_fs: float, *, receipt: dict[str, Any],
) -> RulerSpec:
    """Step 5: replace the pending sentinels in the shipped ``ruler_spec_v1.json``
    with the receipted values, exactly once. Refuses if the shipped spec no longer
    carries the pending sentinel (one-time law)."""
    current = RulerSpec.from_json(SPEC_PATH)
    if not current.pr3_pending:
        raise RuntimeError(
            "ruler_spec_v1.json PR-3 fields are already sealed — the one-time "
            "constant-setting act may not run twice. This is a re-run refusal, "
            "not a silent no-op."
        )
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    payload["pr3"] = {
        "status": "sealed",
        "recall_floor": recall_floor,
        "lambda_fs": lambda_fs,
        "receipt": receipt,
    }
    SPEC_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return RulerSpec.from_json(SPEC_PATH)


def build_dry_run_report(
    *, roster: list[str], events: pd.DataFrame, episodes: pd.DataFrame,
    cells: pd.DataFrame, cutoff: pd.Timestamp,
) -> dict[str, Any]:
    """The dry-run report body (freeze review finding B1) — structure only, EVERY
    derived PR-3 constant value is masked to a fixed non-numeric placeholder
    string. This is a pure function so the masking property is directly
    unit-testable without needing to fake the whole manifest/partition/replay
    wiring: no caller of this function may pass a real ``recall_floor``/
    ``lambda_fs`` value in — there is no parameter for one."""
    return {
        "schema": "stock_identity.w3_calibration_dry_run_report.v1",
        "status": "DRY_RUN_OK",
        "roster_n": len(roster),
        "n_events": int(len(events)),
        "n_episodes": int(len(episodes)),
        "n_cells": int(len(cells)),
        "recall_floor_rule_hash": rule_hash(RECALL_FLOOR_RULE),
        "lambda_fs_rule_hash": rule_hash(LAMBDA_FS_RULE),
        "rule_review_status": RULE_REVIEW_STATUS,
        "recall_floor_value": "MASKED_DRY_RUN",
        "lambda_fs_value": "MASKED_DRY_RUN",
        "recent_history_guard_cutoff": str(cutoff.date()),
        "note": "dry-run validates wiring/inputs/structure only; derived PR-3 "
                "constant values are never printed, logged, or written in this "
                "mode -- the only place a real value may ever appear is the real "
                "seal's receipt. No write to data/trial_ledger.jsonl or "
                "ruler_spec_v1.json occurs in dry-run mode.",
    }


def _load_substrate_bars(episodes: pd.DataFrame, asof: pd.Timestamp) -> dict[str, pd.DataFrame]:
    from engine.stock_identity.plane import load_symbol

    plane_by_symbol = _partition_manifest()["universe"]["plane_by_symbol"]
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for sym in sorted(set(episodes["symbol"].astype(str)) if not episodes.empty else []):
        plane_id = plane_by_symbol.get(sym)
        if not plane_id:
            continue
        try:
            bars_by_symbol[sym] = load_symbol(sym, plane_id, REPO_ROOT).loc[:asof]
        except (FileNotFoundError, ValueError):
            continue
    return bars_by_symbol


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--substrate-dir", required=True, type=Path,
                    help="output-dir the calibration replay act wrote to (scratch)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate wiring/inputs/structure WITHOUT printing, logging, or "
                         "writing any derived PR-3 constant value, and WITHOUT writing to "
                         "data/trial_ledger.jsonl or ruler_spec_v1.json")
    args = ap.parse_args()

    manifest = json.loads(REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    roster = drawn_roster(manifest)
    assert_disjoint_from_pilot_and_blind(roster)

    events_path = args.substrate_dir / "calibration_events_v1.parquet"
    attribution_path = args.substrate_dir / "calibration_attribution_v1.parquet"
    episodes_path = args.substrate_dir / "calibration_episodes_v1.parquet"
    provenance_path = args.substrate_dir / "provenance_receipt.json"
    if not events_path.exists() or not episodes_path.exists():
        raise SystemExit(f"missing substrate artifacts under {args.substrate_dir} — run "
                          "stock_identity_calibration_replay.py first")
    if not provenance_path.exists():
        raise PartialSubstrateError(
            f"missing provenance_receipt.json under {args.substrate_dir} — refuse to "
            "compute any PR-3 value without provenance proving the substrate's coverage"
        )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    # B1: before computing anything.
    assert_full_roster_coverage(provenance, roster, manifest)

    events = pd.read_parquet(events_path)
    attribution = pd.read_parquet(attribution_path) if attribution_path.exists() else pd.DataFrame()
    episodes = pd.read_parquet(episodes_path)
    for df, name in ((events, "events"), (attribution, "attribution"), (episodes, "episodes")):
        if not df.empty and "calibration_substrate" in df.columns:
            if not bool(df["calibration_substrate"].all()):
                raise ValueError(f"{name}: not every row is stamped calibration_substrate=True")

    asof = pd.Timestamp(_partition_manifest()["asof"])
    bars_by_symbol = _load_substrate_bars(episodes, asof)

    calendar = pd.DatetimeIndex(sorted({d for df in bars_by_symbol.values() for d in df.index}))
    cutoff = recent_history_cutoff(asof, calendar, guard_sessions=126)
    bars_by_symbol = truncate_to_guard(bars_by_symbol, cutoff)

    # B3: the second barrier — checked against the substrate's OWN provenance
    # fields (never a freshly self-truncated bars copy). The independently
    # recomputed cutoff (from this run's own asof/calendar) must agree with what
    # the substrate act itself recorded, and the substrate's actual events/
    # episodes (as loaded, not re-derived) must obey that cutoff.
    recorded_cutoff_str = provenance.get("recent_history_guard_cutoff")
    if not recorded_cutoff_str:
        raise RecentHistoryGuardViolation(
            "substrate provenance carries no recent_history_guard_cutoff — refuse "
            "to compute any PR-3 value without provenance proving the guard held"
        )
    recorded_cutoff = pd.Timestamp(recorded_cutoff_str)
    if recorded_cutoff != cutoff:
        raise RecentHistoryGuardViolation(
            f"recomputed recent-history cutoff {cutoff.date()} does not match the "
            f"substrate provenance's recorded cutoff {recorded_cutoff.date()} — "
            "refuse to compute any PR-3 value from a substrate whose guard clock "
            "cannot be independently reproduced"
        )
    assert_recent_history_guard(events, episodes, cutoff)

    base_spec = RulerSpec.from_json(SPEC_PATH)

    if args.dry_run:
        # Structural validation only. The full pipeline (including the PR-3
        # rule computation) runs so a real wiring/input defect still surfaces as
        # an exception here, but no derived constant value is ever printed,
        # logged, or written — the only place a real value may appear is the
        # real seal's receipt (Step 5, non-dry-run). No write to the shared
        # data/trial_ledger.jsonl occurs in dry-run mode (register_rules_and_grid
        # is never called below).
        # The returned values are deliberately UNUSED beyond isinstance() below —
        # build_dry_run_report has no parameter through which a real value could
        # reach the printed report.
        recall_floor, lambda_fs, cells = compute_constants_from_substrate(
            events, attribution, episodes, bars_by_symbol, base_spec,
        )
        assert isinstance(recall_floor, float) and isinstance(lambda_fs, float)  # proves computation succeeded
        report = build_dry_run_report(
            roster=roster, events=events, episodes=episodes, cells=cells, cutoff=cutoff,
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
        return 0

    ledger = TrialLedger(family=TRIAL_FAMILY)
    registration_receipt = register_rules_and_grid(ledger, info_cutoff=str(asof.date()))

    recall_floor, lambda_fs, cells = compute_constants_from_substrate(
        events, attribution, episodes, bars_by_symbol, base_spec,
    )

    receipt: dict[str, Any] = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "recall_floor": {
            "value": recall_floor,
            "rule": RECALL_FLOOR_RULE,
            "rule_hash": registration_receipt["recall_floor_rule_hash"],
            "status": RULE_REVIEW_STATUS,
            "diagnostic_variants_pm20pct": diagnostic_variants(recall_floor),
        },
        "lambda_fs": {
            "value": lambda_fs,
            "rule": LAMBDA_FS_RULE,
            "rule_hash": registration_receipt["lambda_fs_rule_hash"],
            "status": RULE_REVIEW_STATUS,
            "diagnostic_variants_pm20pct": diagnostic_variants(lambda_fs),
        },
        "roster_sha256": manifest["roster"]["roster_sha256"],
        "n_names_drawn": len(roster),
        "recent_history_guard_cutoff": str(cutoff.date()),
        "trial_ledger_family": TRIAL_FAMILY,
        "trial_ledger_effective_n": registration_receipt["diagnostic_grid_effective_n"],
        "fit_read_look_budget": registration_receipt["fit_read_look_budget"],
        "base_spec_hash_before_seal": base_spec.spec_hash(),
    }

    print(json.dumps(receipt, indent=2, sort_keys=True, default=str), flush=True)

    sealed = seal_ruler_spec(recall_floor, lambda_fs, receipt=receipt)
    print(json.dumps({"sealed_spec_hash": sealed.spec_hash()}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
