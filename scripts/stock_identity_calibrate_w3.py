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
from dataclasses import replace as dataclass_replace
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
    truncate_to_guard,
)

DATA = REPO_ROOT / "data" / "stock_identity"
RULER_DIR = DATA / "ruler"
SPEC_PATH = RULER_DIR / "ruler_spec_v1.json"
REPLAY_MANIFEST_PATH = RULER_DIR / "calibration_replay_manifest_v1.json"
REGISTRATION_PATH = REPO_ROOT / "research" / "stock_identity" / "W3_RULER_REGISTRATION.md"
#: B3-minor: the single frozen source of truth for the recent-history guard
#: cutoff. Monkeypatchable (like SPEC_PATH/REPLAY_MANIFEST_PATH above) for tests
#: that build a fully synthetic partition/asof.
CALIBRATION_CONSTANTS_PATH = DATA / "constants" / "si_constants_v1.json"
#: Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law): the committed W2 family registry
#: — the outcome-independent ``family_first_available`` provenance source the
#: sealed-calibration path's ``aggregate_cell_metrics`` call now requires for
#: its recall-denominator eligibility (replacing the prior events-derived
#: "fired-on" coverage universe). Monkeypatchable like the other module-level
#: paths above.
FAMILY_REGISTRY_PATH = DATA / "expert_events" / "family_registry.json"
#: PRE-ACT CONDITION 2 (SI-W3A-RULER-V1 pre-seal fix pass): the two ruler
#: implementation modules whose byte-for-byte sha256 is recorded in the seal
#: receipt below (``build_seal_receipt``'s ``ruler_implementation_sha256``
#: field) — so a post-value change to either module's implementation is
#: detectable from the receipt alone, per the freeze's voiding clause (a
#: value silently computed under different code than what the receipt
#: describes would otherwise leave no trace in the committed artifacts).
#: Monkeypatchable like the other module-level paths above.
RULER_IMPLEMENTATION_PATH = REPO_ROOT / "engine" / "stock_identity" / "ruler.py"
RULER_NULLS_IMPLEMENTATION_PATH = REPO_ROOT / "engine" / "stock_identity" / "ruler_nulls.py"

TRIAL_FAMILY = "stock_identity_w3_ruler_calibration"


class PartialSubstrateError(RuntimeError):
    """Raised when the calibration substrate's provenance does not prove
    coverage of the FULL drawn roster (freeze review finding B1) — refuses
    BEFORE computing anything from partition data, rather than silently
    computing a constant off a partial roster."""


class BlockedDegenerateCalibrationError(RuntimeError):
    """Ruling 1(b) (SI-W3A-RULER-V1 PR-3 seal law): the typed, fail-closed
    refusal for ``lambda_fs = median(recall_at_tier * zone_precision) /
    P75(false_start_rate)`` when either the numerator or the denominator,
    computed over the lawful sealed-calibration grading-cell population, is
    not finite and strictly greater than zero. There is NO epsilon, NO
    clipping, NO cap, NO alternate quantile, and NO fallback fixed lambda
    anywhere in this path — a degenerate calibration substrate is escalated
    to Sol as a typed ``BLOCKED_DEGENERATE_CALIBRATION`` receipt, never
    silently patched around."""

    def __init__(
        self, *, numerator: float, denominator: float, n_lawful_population: int, reason: str,
    ) -> None:
        self.numerator = numerator
        self.denominator = denominator
        self.n_lawful_population = n_lawful_population
        self.reason = reason
        super().__init__(
            f"BLOCKED_DEGENERATE_CALIBRATION: {reason} (numerator={numerator!r}, "
            f"denominator={denominator!r}, n_lawful_population={n_lawful_population})"
        )

    def to_receipt(self) -> dict[str, Any]:
        """The typed receipt surfaced to Sol (printed by ``main()`` and never
        written to ``ruler_spec_v1.json`` — the pr3 sentinel stays pending on
        this path, since no constant was ever set)."""
        return {
            "status": "BLOCKED_DEGENERATE_CALIBRATION",
            "reason": self.reason,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "n_lawful_population": self.n_lawful_population,
            "lambda_fs_rule": LAMBDA_FS_RULE,
            "lambda_fs_rule_hash": rule_hash(LAMBDA_FS_RULE),
        }


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
#: before Step 4/5 ever run against partition data). UNCHANGED by the RULE FORM —
#: only the disclosed TEXT changes here (status: declared_pending_sol_rule_review,
#: RULE_REVIEW_STATUS above).
#:
#: **Ruling 1 (SI-W3A-RULER-V1 PR-3 seal law, Sol) REPLACES both rules' exact
#: forms** — this is a genuine rule-FORM change, not a textual-accuracy-only
#: fix like the two prior re-pins below it in this constant's history:
#:
#: * ``recall_floor`` becomes exactly ``max(quantize_to_nearest_0.05(P25(
#:   recall_at_tier on the lawful sealed-calibration grading-cell population)),
#:   0.05)`` — the ``0.05`` floor is now an explicit, PREREGISTERED SUBSTANTIVE
#:   floor (never a rounding artifact): even a population whose quantized P25
#:   would land BELOW 0.05 is clamped up to 0.05, so ``recall_floor`` can never
#:   be zero. Zero-recall cells are NEVER dropped or conditioned out of the
#:   population (no A3 conditioning) — the P25 is taken over the FULL lawful
#:   population, including any cell whose ``recall_at_tier == 0.0``.
#: * ``lambda_fs`` becomes exactly ``median(recall_at_tier * zone_precision) /
#:   P75(false_start_rate)`` on the SAME lawful population — a wholly
#:   different FORM from the prior ``1 / max(P75(false_start_rate), 0.01)``,
#:   with NO rounding grid (the prior "rounded to the nearest 0.25" step is
#:   gone; the ruling's formula is exact). The computation is FAIL-CLOSED: it
#:   is valid ONLY when both the numerator (the median of
#:   ``recall_at_tier * zone_precision``) and the denominator (P75 of
#:   ``false_start_rate``) are finite and STRICTLY greater than zero. If
#:   either condition fails, the constant-setting act refuses with a typed
#:   ``BlockedDegenerateCalibrationError`` / ``BLOCKED_DEGENERATE_CALIBRATION``
#:   receipt to Sol — there is NO epsilon, NO clipping, NO cap, NO alternate
#:   quantile, and NO fallback fixed lambda anywhere in this path.
#:
#: **The lawful sealed-calibration grading-cell population** (shared by both
#: rules, frozen here before any partition read): every row of the
#: calibration-fire substrate's cell-aggregate frame
#: (``aggregate_cell_metrics``' own output) with ``n_episodes > 0`` — i.e. the
#: cell exists at all (a cell is only ever emitted for a
#: ``(family_key, episode_type, grain)`` combination that fired at least
#: once; freeze review finding B2/B2-residual retired the OLD "at least one
#: fire" ambiguity, so this conjunct is now a near-tautological existence
#: gate over the frame's own rows, retained verbatim from the prior rule text
#: for continuity). PER-RULE missing-value behavior on top of that shared
#: gate — each metric's OWN pandas ``.dropna()``, applied independently,
#: never coupled across metrics (a cell can satisfy the ``n_episodes > 0``
#: gate yet still carry a NaN on any ONE of ``recall_at_tier`` /
#: ``zone_precision`` / ``false_start_rate`` independently — e.g. a fire whose
#: ``atr_dist`` never resolved, or whose ``false_start`` flag never resolved):
#: ``recall_floor``'s P25 is taken over ``recall_at_tier.dropna()``;
#: ``lambda_fs``'s numerator is taken over
#: ``(recall_at_tier * zone_precision).dropna()`` (a row's product is
#: undefined, and so excluded, if EITHER factor is undefined) and its
#: denominator over ``false_start_rate.dropna()``. **Quantile convention**:
#: every percentile in this file (P25 for ``recall_floor``, P75 for
#: ``lambda_fs``'s denominator) uses ``numpy.percentile``'s ``linear``
#: interpolation method (numpy's default; passed explicitly here so the
#: convention is pinned in code, not merely inherited from a default that
#: could silently change upstream). **Deterministic serialization**: the
#: sealed receipt/spec are always written via ``json.dumps(...,
#: sort_keys=True, ...)`` (:func:`seal_ruler_spec`), so re-serializing an
#: identical receipt always produces byte-identical output.
#:
#: This is a genuine RULE-FORM change (not the population-wording-only fixes
#: below), so BOTH hashes necessarily changed again and are re-recorded in
#: ``W3_RULER_REGISTRATION.md`` §3.1 with every PRIOR hash retained alongside
#: the new one (same disclosure pattern as the population-wording re-pins).
#:
#: --- one further POST-Ruling-1 rule-TEXT-only clarification (SI-W3A-RULER-V1
#: pre-seal fix pass, item 5): ``RECALL_FLOOR_RULE`` now names the
#: ``quantize_to_nearest_0.05`` step's TIE CONVENTION explicitly -- it is
#: Python's built-in ``round()`` (``round(p25 / 0.05) * 0.05``, exactly what
#: :func:`compute_recall_floor` has always computed), whose behavior at an
#: exact ``.5`` tie is banker's rounding (round-half-to-even). The MATH is
#: unchanged (``round()`` was always the implementation; only the prose now
#: says so) -- only ``RECALL_FLOOR_RULE``'s hash moves again as a result, and
#: is re-pinned in ``W3_RULER_REGISTRATION.md`` §3.1 with every prior hash
#: (including Ruling 1(a)) retained as history, same disclosure pattern as
#: every re-pin above. ``LAMBDA_FS_RULE`` is untouched by this item; its hash
#: is unchanged.
#:
#: --- history of PRIOR (pre-Ruling-1) rule-TEXT-only changes, retained for
#: provenance: the §4 repair pass corrected the population-wording clause once
#: (MINORS finding: "align rule-text population wording with implementation")
#: to name the ``n_episodes > 0`` / ``n_fires > 0`` predicate each function had
#: always applied, rather than the prior prose's inaccurate "tier-eligible
#: episode" description (a DIFFERENT, unrelated quantity — B2's fix to
#: recall_at_tier's own denominator). The delta-review repair pass then
#: corrected it a SECOND time (RULE-TEXT ITEMS finding) to name BOTH conjuncts
#: each function had always applied: the count filter above AND the implicit
#: ``.dropna()`` on the ranked column itself. Both were textual accuracy
#: fixes, not rule-form changes, at the time they landed.
RECALL_FLOOR_RULE = (
    "recall_floor = max(quantize_to_nearest_0.05(P25(recall_at_tier on the lawful "
    "sealed-calibration grading-cell population)), 0.05). The lawful population is "
    "every row of the calibration-fire substrate's cell-aggregate frame "
    "(aggregate_cell_metrics' own output) with n_episodes > 0 (the cell exists at "
    "all -- emitted only for a (family_key, episode_type, grain) combination that "
    "fired at least once), further restricted to a DEFINED (non-NaN) "
    "recall_at_tier value (a genuine second, independent filter -- pandas "
    "'.dropna()' on the recall_at_tier column alone; a cell can satisfy the count "
    "gate yet still carry a NaN recall_at_tier). Zero-recall cells (recall_at_tier "
    "== 0.0) are NEVER dropped or conditioned out of this population (no A3 "
    "conditioning) -- the P25 is taken over the FULL lawful population including "
    "them. P25 uses numpy.percentile's linear interpolation method, passed "
    "explicitly. The quantize_to_nearest_0.05 step is Python's built-in round() "
    "applied to P25/0.05 before rescaling (round(p25 / 0.05) * 0.05); round()'s tie "
    "convention at an exact .5 boundary is banker's rounding (round-half-to-even), "
    "named here explicitly rather than left as an unstated default. The 0.05 floor "
    "is an explicit, PREREGISTERED SUBSTANTIVE floor, "
    "never a rounding artifact: even a population whose quantized P25 lands below "
    "0.05 is clamped up to 0.05, so recall_floor can never be zero. A cell below "
    "this floor is judged too rarely localized for C-LOC-D to be graded. The rule "
    "references only the POPULATION of measured cells and never any expert's own "
    "outcome rank (DNR:KILL-OUTCOME-AUDITION)."
)

LAMBDA_FS_RULE = (
    "lambda_fs = median(recall_at_tier * zone_precision) / P75(false_start_rate), "
    "both computed over the SAME lawful sealed-calibration grading-cell population "
    "recall_floor's rule defines (n_episodes > 0 -- the cell exists at all). The "
    "numerator's population is further restricted to rows with a DEFINED "
    "(non-NaN) product of recall_at_tier * zone_precision (pandas '.dropna()' on "
    "that product -- undefined, and so excluded, if EITHER factor is undefined); "
    "the denominator's population is restricted to rows with a DEFINED "
    "false_start_rate (pandas '.dropna()' on that column alone, independent of "
    "the numerator's filter). P75 uses numpy.percentile's linear interpolation "
    "method, passed explicitly. NO rounding or quantization grid is applied to "
    "the result -- lambda_fs is the exact quotient. FAIL-CLOSED: this computation "
    "is valid ONLY when the numerator (the median product) AND the denominator "
    "(the P75 false-start rate) are BOTH finite and STRICTLY greater than zero. "
    "If either fails, the constant-setting act refuses with a typed "
    "BLOCKED_DEGENERATE_CALIBRATION error/receipt to Sol -- there is NO epsilon, "
    "NO clipping, NO cap, NO alternate quantile, and NO fallback fixed lambda "
    "anywhere in this path. The rule references only the POPULATION "
    "distributions of recall_at_tier, zone_precision, and false_start_rate, and "
    "never any expert's own outcome rank (DNR:KILL-OUTCOME-AUDITION)."
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


def _lawful_calibration_population(cells: pd.DataFrame) -> pd.DataFrame:
    """Ruling 1(c): the single 'lawful sealed-calibration grading-cell
    population' predicate shared by BOTH PR-3 constant rules —
    ``n_episodes > 0`` (the cell exists at all; ``aggregate_cell_metrics``
    only ever emits a row for a ``(family_key, episode_type, grain)``
    combination that fired at least once). Each rule then applies its OWN
    per-metric ``.dropna()`` independently on top of this shared gate (a cell
    can satisfy this gate yet still carry a NaN on any ONE of
    ``recall_at_tier`` / ``zone_precision`` / ``false_start_rate``
    independently — a blanket dropna here would silently couple three
    independent metrics' missingness together)."""
    return cells.loc[cells["n_episodes"] > 0]


def compute_recall_floor(cells: pd.DataFrame) -> float:
    """RECALL_FLOOR_RULE, exactly: max(quantize_to_nearest_0.05(P25(
    recall_at_tier on the lawful population)), 0.05). Zero-recall cells are
    NEVER dropped (no A3 conditioning); the 0.05 floor is a preregistered
    substantive minimum, not a rounding artifact."""
    population = _lawful_calibration_population(cells)
    eligible = population["recall_at_tier"].dropna()
    if eligible.empty:
        raise ValueError(
            "no lawful cells (n_episodes>0, defined recall_at_tier) to compute recall_floor"
        )
    p25 = float(np.percentile(eligible.to_numpy(dtype=float), 25, method="linear"))
    quantized = round(p25 / 0.05) * 0.05
    return max(quantized, 0.05)


def compute_lambda_fs(cells: pd.DataFrame) -> float:
    """LAMBDA_FS_RULE, exactly: median(recall_at_tier * zone_precision) /
    P75(false_start_rate), over the SAME lawful population. FAIL-CLOSED: both
    numerator and denominator must be finite and strictly > 0, or this raises
    :class:`BlockedDegenerateCalibrationError` — NO epsilon, NO clipping, NO
    cap, NO alternate quantile, and NO fallback fixed lambda."""
    population = _lawful_calibration_population(cells)
    n_lawful_population = int(len(population))

    product = (population["recall_at_tier"] * population["zone_precision"]).dropna()
    numerator = float(product.median()) if not product.empty else float("nan")

    fsr = population["false_start_rate"].dropna()
    denominator = (
        float(np.percentile(fsr.to_numpy(dtype=float), 75, method="linear"))
        if not fsr.empty else float("nan")
    )

    numerator_ok = np.isfinite(numerator) and numerator > 0
    denominator_ok = np.isfinite(denominator) and denominator > 0
    if not (numerator_ok and denominator_ok):
        reasons = []
        if not numerator_ok:
            reasons.append(
                f"numerator median(recall_at_tier*zone_precision)={numerator!r} is not "
                "finite and strictly > 0"
            )
        if not denominator_ok:
            reasons.append(
                f"denominator P75(false_start_rate)={denominator!r} is not finite and "
                "strictly > 0"
            )
        raise BlockedDegenerateCalibrationError(
            numerator=numerator, denominator=denominator,
            n_lawful_population=n_lawful_population, reason="; ".join(reasons),
        )
    return numerator / denominator


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
        c_loc_d_rank_population="episode_type_x_grain",
        recall_floor=None, lambda_fs=None, pr3_status="internal_calibration_pass",
        pr3_receipt=None,
        authority={"can_rank": False, "can_size": False, "can_gate": False,
                   "can_originate_signal": False, "can_escalate": False},
    )


def load_family_registry() -> list[dict[str, Any]]:
    """Ruling 2: the committed W2 family registry's ``families`` list, read
    straight off disk (never re-derived/invented). ``[]`` (never ``None``)
    when the file does not exist, so a caller checking
    ``family_registry is not None`` still supplies a real, empty-but-present
    list rather than accidentally reading as "not supplied"."""
    if not FAMILY_REGISTRY_PATH.exists():
        return []
    payload = json.loads(FAMILY_REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(payload.get("families", []))


def compute_constants_from_substrate(
    events: pd.DataFrame, attribution: pd.DataFrame, episodes: pd.DataFrame,
    bars_by_symbol: dict[str, pd.DataFrame], base_spec: RulerSpec,
    *, family_registry: list[dict[str, Any]] | None = None,
) -> tuple[float, float, pd.DataFrame]:
    """Runs the ruler's own metric/aggregation math (already frozen in Tasks 2-3)
    over the guard-truncated calibration substrate, then applies the pre-declared
    rules. Returns ``(recall_floor, lambda_fs, cells)``.

    Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law): ``aggregate_cell_metrics``'s
    recall-denominator eligibility is now availability-based
    (``family_registry`` + ``bars_by_symbol``), applied identically to this
    sealed-calibration path and to the pilot diagnostics build
    (``scripts/stock_identity_build_ruler.py``). ``family_registry`` defaults
    to :func:`load_family_registry`'s committed read when the caller does not
    supply one explicitly (test callers may still pass ``None``/``[]``/a
    fixture list directly)."""
    calc_spec = _fixture_spec_for_computation(
        base_spec.atr_basis, base_spec.p_pre_sessions, base_spec.useful_zone_window_sessions,
        base_spec.useful_zone_delta_atr, base_spec.false_start_atr_threshold,
        base_spec.episode_type_anchor,
    )
    if family_registry is None:
        family_registry = load_family_registry()
    fire_metrics = compute_fire_metrics(events, attribution, episodes, bars_by_symbol, calc_spec)
    cells = aggregate_cell_metrics(
        fire_metrics, episodes, calc_spec, events,
        family_registry=family_registry, bars_by_symbol=bars_by_symbol,
    )
    recall_floor = compute_recall_floor(cells)
    lambda_fs = compute_lambda_fs(cells)
    return recall_floor, lambda_fs, cells


def core_spec_hash(spec: RulerSpec, *, recall_floor: float | None, lambda_fs: float | None, status: str) -> str:
    """The spec's substantive-content hash with ``pr3_receipt`` projected to
    ``None`` (freeze review finding M8's "spec hash before/after"). The receipt
    itself embeds this hash, so hashing the receipt-INCLUSIVE spec would be
    self-referential (a value can never legally hash itself); this hashes only
    the geometry/PR3-status/PR3-values/authority that the receipt is ABOUT,
    which is exactly the substantive content a before/after comparison needs to
    prove changed."""
    projected = dataclass_replace(
        spec, recall_floor=recall_floor, lambda_fs=lambda_fs, pr3_status=status, pr3_receipt=None,
    )
    return projected.spec_hash()


def build_seal_receipt(
    *, recall_floor: float, lambda_fs: float, base_spec: RulerSpec, roster: list[str],
    manifest: dict[str, Any], provenance: dict[str, Any], provenance_path: Path,
    cutoff: pd.Timestamp, registration_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the M8 seal receipt: per-constant value + rule hash/status,
    roster hash, replay-manifest hash, W2 family-registry hash, substrate
    provenance hash, ruler-implementation hash, spec hash before/after,
    timestamp. This is the SAME ``receipt`` dict embedded in
    ``ruler_spec_v1.json``'s ``pr3.receipt`` field AND rendered into
    ``W3_RULER_REGISTRATION.md`` (via :func:`append_seal_receipt_to_registration`).

    PRE-ACT CONDITION 2 (SI-W3A-RULER-V1 pre-seal fix pass): the receipt also
    records the exact byte-for-byte sha256 of ``engine/stock_identity/ruler.py``
    and ``engine/stock_identity/ruler_nulls.py`` AT SEAL TIME
    (``ruler_implementation_sha256``) — the two modules whose functions compute
    every value this receipt certifies. A post-value edit to either module's
    implementation changes its recorded hash, so it is detectable from the
    receipt alone, satisfying the freeze's voiding clause without requiring any
    separate provenance channel."""
    replay_manifest_hash = hashlib.sha256(REPLAY_MANIFEST_PATH.read_bytes()).hexdigest()
    substrate_provenance_hash = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    w2_family_registry_hash = hashlib.sha256(
        json.dumps(
            provenance.get("spec_hashes_asserted_at_run", {}), sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    ruler_py_sha256 = hashlib.sha256(RULER_IMPLEMENTATION_PATH.read_bytes()).hexdigest()
    ruler_nulls_py_sha256 = hashlib.sha256(RULER_NULLS_IMPLEMENTATION_PATH.read_bytes()).hexdigest()
    spec_hash_before_seal = core_spec_hash(
        base_spec, recall_floor=None, lambda_fs=None, status=PR3_PENDING_SENTINEL,
    )
    spec_hash_after_seal = core_spec_hash(
        base_spec, recall_floor=recall_floor, lambda_fs=lambda_fs, status="sealed",
    )
    return {
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
        "replay_manifest_hash": replay_manifest_hash,
        "w2_family_registry_hash": w2_family_registry_hash,
        "substrate_provenance_hash": substrate_provenance_hash,
        # PRE-ACT CONDITION 2: byte-for-byte sha256 of the two ruler
        # implementation modules at seal time -- a post-value implementation
        # change is detectable from the receipt alone.
        "ruler_implementation_sha256": {
            "ruler_py": ruler_py_sha256,
            "ruler_nulls_py": ruler_nulls_py_sha256,
        },
        "spec_hash_before_seal": spec_hash_before_seal,
        "spec_hash_after_seal": spec_hash_after_seal,
        # kept for backward compatibility with the pre-M8 field name
        "base_spec_hash_before_seal": base_spec.spec_hash(),
    }


def format_seal_receipt_markdown(receipt: dict[str, Any]) -> str:
    """M8: the registration-doc append block for a completed real seal."""
    rf, lf = receipt["recall_floor"], receipt["lambda_fs"]
    lines = [
        "",
        "## 5. Sealed constants receipt (Task 3C Step 5 -- the real, one-time seal)",
        "",
        f"- Sealed at: `{receipt['computed_at']}`",
        f"- `recall_floor` = `{rf['value']}` (rule hash `{rf['rule_hash']}`, status `{rf['status']}`)",
        f"- `lambda_fs` = `{lf['value']}` (rule hash `{lf['rule_hash']}`, status `{lf['status']}`)",
        f"- Roster hash: `{receipt['roster_sha256']}` (n={receipt['n_names_drawn']})",
        f"- Replay-manifest hash: `{receipt['replay_manifest_hash']}`",
        f"- W2 family-registry hash: `{receipt['w2_family_registry_hash']}`",
        f"- Substrate provenance hash: `{receipt['substrate_provenance_hash']}`",
        f"- Ruler implementation hash (`ruler.py`): "
        f"`{receipt['ruler_implementation_sha256']['ruler_py']}`",
        f"- Ruler implementation hash (`ruler_nulls.py`): "
        f"`{receipt['ruler_implementation_sha256']['ruler_nulls_py']}`",
        f"- Spec hash before seal: `{receipt['spec_hash_before_seal']}`",
        f"- Spec hash after seal: `{receipt['spec_hash_after_seal']}`",
        f"- Recent-history guard cutoff: `{receipt['recent_history_guard_cutoff']}`",
        f"- Trial ledger family: `{receipt['trial_ledger_family']}` (effective N="
        f"{receipt['trial_ledger_effective_n']})",
        f"- Fit-read look budget: `{receipt['fit_read_look_budget']}`",
        "",
    ]
    return "\n".join(lines)


def append_seal_receipt_to_registration(receipt: dict[str, Any]) -> None:
    """M8: append the seal receipt to ``W3_RULER_REGISTRATION.md`` (via the
    module-level ``REGISTRATION_PATH``, so a test can monkeypatch it to a
    throwaway file, exactly like ``SPEC_PATH``)."""
    block = format_seal_receipt_markdown(receipt)
    with REGISTRATION_PATH.open("a", encoding="utf-8") as f:
        f.write(block)


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


def frozen_calibration_history_cutoff() -> pd.Timestamp:
    """B3-minor: the single frozen source of truth for the W3A recent-history
    guard cutoff — ``si_constants_v1.json``'s ``calibration_history_cutoff``,
    computed ONCE at partition-build time
    (``scripts/stock_identity_build_atlas.py``:
    ``CALIBRATION_LOOKBACK_SESSIONS`` (126) sessions before ``asof``, on the
    canonical market calendar built there — never re-derived here from whatever
    narrower symbol set (e.g. only symbols that produced an episode, as the
    prior second-barrier implementation did via ``_load_substrate_bars``) a
    later reader happens to have bars loaded for. Two different symbol sets can
    silently disagree on the 126th-trading-session-back date purely from
    calendar composition, which would falsely accuse a genuinely-correct
    substrate of a guard violation it never committed."""
    values = json.loads(CALIBRATION_CONSTANTS_PATH.read_text(encoding="utf-8"))
    return pd.Timestamp(values["calibration_history_cutoff"])


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

    # B3-minor: the second barrier — checked against the substrate's OWN
    # provenance fields (never a freshly self-truncated bars copy) AND against
    # the single frozen W1 source of truth (si_constants_v1.json's
    # calibration_history_cutoff), never recomputed from whatever narrower
    # symbol set this script happens to have bars loaded for (that used to be
    # only the symbols present in `episodes`, which can silently disagree with
    # the substrate's own recorded cutoff purely from calendar composition).
    recorded_cutoff_str = provenance.get("recent_history_guard_cutoff")
    if not recorded_cutoff_str:
        raise RecentHistoryGuardViolation(
            "substrate provenance carries no recent_history_guard_cutoff — refuse "
            "to compute any PR-3 value without provenance proving the guard held"
        )
    recorded_cutoff = pd.Timestamp(recorded_cutoff_str)
    frozen_cutoff = frozen_calibration_history_cutoff()
    if recorded_cutoff != frozen_cutoff:
        raise RecentHistoryGuardViolation(
            f"substrate provenance's recorded recent_history_guard_cutoff "
            f"{recorded_cutoff.date()} does not match the frozen W1 "
            f"calibration_history_cutoff constant {frozen_cutoff.date()} "
            f"({CALIBRATION_CONSTANTS_PATH.name}) — refuse to compute any PR-3 "
            "value from a substrate whose guard clock disagrees with the single "
            "frozen source of truth"
        )
    cutoff = frozen_cutoff

    asof = pd.Timestamp(_partition_manifest()["asof"])
    bars_by_symbol = _load_substrate_bars(episodes, asof)
    bars_by_symbol = truncate_to_guard(bars_by_symbol, cutoff)
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
        try:
            recall_floor, lambda_fs, cells = compute_constants_from_substrate(
                events, attribution, episodes, bars_by_symbol, base_spec,
            )
        except BlockedDegenerateCalibrationError as exc:
            print(f"::error title=si-w3a-blocked-degenerate-calibration::{exc}", flush=True)
            print(json.dumps(exc.to_receipt(), indent=2, sort_keys=True, default=str), flush=True)
            return 3
        # Explicit raise, not a bare `assert` (which python -O strips) — this is
        # the proof that the dry-run computation actually succeeded, not an
        # optional debugging aid.
        if not (isinstance(recall_floor, float) and isinstance(lambda_fs, float)):
            raise TypeError(
                "compute_constants_from_substrate must return (float, float, "
                f"DataFrame) — got recall_floor={type(recall_floor).__name__!r}, "
                f"lambda_fs={type(lambda_fs).__name__!r}"
            )
        report = build_dry_run_report(
            roster=roster, events=events, episodes=episodes, cells=cells, cutoff=cutoff,
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
        return 0

    ledger = TrialLedger(family=TRIAL_FAMILY)
    registration_receipt = register_rules_and_grid(ledger, info_cutoff=str(asof.date()))

    try:
        recall_floor, lambda_fs, cells = compute_constants_from_substrate(
            events, attribution, episodes, bars_by_symbol, base_spec,
        )
    except BlockedDegenerateCalibrationError as exc:
        # Ruling 1(b): FAIL-CLOSED, typed refusal — no epsilon/clipping/cap/
        # alternate quantile/fallback fixed lambda anywhere in this path. The
        # rule registration above (rule text + hashes, diagnostic grid) has
        # already been recorded — that is the rule, not a value — but
        # ruler_spec_v1.json's pr3 sentinel is NEVER touched on this path:
        # seal_ruler_spec is never reached.
        print(f"::error title=si-w3a-blocked-degenerate-calibration::{exc}", flush=True)
        print(json.dumps(exc.to_receipt(), indent=2, sort_keys=True, default=str), flush=True)
        return 3

    # M8: the seal receipt carries per-constant value+rule hash, roster hash,
    # replay-manifest hash, W2 family-registry hash, substrate provenance hash,
    # spec hash before/after, and a timestamp -- written into BOTH
    # ruler_spec_v1.json's pr3.receipt AND W3_RULER_REGISTRATION.md.
    receipt: dict[str, Any] = build_seal_receipt(
        recall_floor=recall_floor, lambda_fs=lambda_fs, base_spec=base_spec, roster=roster,
        manifest=manifest, provenance=provenance, provenance_path=provenance_path,
        cutoff=cutoff, registration_receipt=registration_receipt,
    )

    print(json.dumps(receipt, indent=2, sort_keys=True, default=str), flush=True)

    sealed = seal_ruler_spec(recall_floor, lambda_fs, receipt=receipt)
    try:
        append_seal_receipt_to_registration(receipt)
    except Exception as exc:
        # M8-minor recovery path: the seal ALREADY committed durably to
        # ruler_spec_v1.json's pr3.receipt before this append was attempted —
        # never attempt to unseal on an append failure. The human-readable
        # registration line is fully reconstructible from that durable receipt
        # at any later time via format_seal_receipt_markdown(receipt).
        print(
            "::warning title=si-w3a-registration-append-failed::the seal already "
            "committed durably to ruler_spec_v1.json's pr3.receipt, but appending "
            f"the registration line to {REGISTRATION_PATH.name} failed "
            f"({type(exc).__name__}: {exc}) — do NOT attempt to unseal; the "
            "registration line can be reconstructed at any time from "
            "ruler_spec_v1.json's pr3.receipt via "
            "format_seal_receipt_markdown(receipt)",
            flush=True,
        )
        raise

    # M8-minor: `sealed.spec_hash()` is the RECEIPT-INCLUSIVE hash of the spec
    # exactly as written to disk (pr3.receipt embedded in the hashed payload) —
    # distinct from the receipt's own `spec_hash_after_seal` field, which is the
    # RECEIPT-EXCLUSIVE core hash (pr3_receipt projected to None by
    # core_spec_hash, since the receipt cannot legally hash itself). Named
    # `sealed_spec_receipt_hash` (not `sealed_spec_hash`) so a reader never
    # confuses the two; the assertion below pins that they are, in fact,
    # different hashes of different payloads.
    sealed_spec_receipt_hash = sealed.spec_hash()
    assert sealed_spec_receipt_hash != receipt["spec_hash_after_seal"], (
        "the receipt-INCLUSIVE spec hash must differ from the receipt-EXCLUSIVE "
        "spec_hash_after_seal — equality here would mean pr3.receipt is somehow "
        "not actually part of the spec as written to disk"
    )
    print(json.dumps({"sealed_spec_receipt_hash": sealed_spec_receipt_hash}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
