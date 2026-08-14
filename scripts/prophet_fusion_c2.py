#!/usr/bin/env python3
"""PR-2 — the C2 regularized evidence-family harness + the §5.3 redundancy plane.

WHAT THIS IS.  Masterplan §8.1 rung **C2** (elastic-net over typed FAMILY features, group
budget structural, monotonic non-negative signs where a family carries a filed direction)
plus the §5.3 pre-registered redundancy / estimability / incremental measurement plane,
with §9.2's minimum-usable-fold rule enforced at the fit seam.

WHAT TODAY'S FRAME ANSWERS.  On the graded-board frame (§8.5 frame 2, 24 dates) the
INFERENTIAL half is **REFUSED**: 24 dates cannot yield one lawful fold at a 21-session
embargo, so the C2 fit and the cross-fitted incremental estimates emit the §9.2 refusal
VERBATIM and no coefficients.  That refusal is the result, not a gap in the harness — the
machinery is complete and is PROVEN end to end on synthetic depth by ``--selftest`` and by
``tests/test_prophet_fusion_c2.py``.  The descriptive plane (census, redundancy blocks,
conditional mutual information, in-sample partial correlations, power arithmetic) IS
computable today and is what this report carries.

THE FIVE THINGS THIS MODULE REFUSES TO DO
-----------------------------------------
1. **Fit without a lawful fold.**  There is no in-sample fallback fit anywhere in this
   file.  :func:`fit_c2_over_folds` raises when handed an empty fold plan, and the CLI
   path calls :func:`folds_for_labels` FIRST.  An in-sample C2 read would be a weaker
   result wearing the strong result's name.
2. **Let a member vote on presence alone.**  The PR-2 registry amendment
   (``semantics.variance_floor`` / ``variance_floor_spec``,
   ``DSC:COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE``) adds a VARIANCE axis beside the
   presence floor.  The floor is READ FROM THE REGISTRY (:func:`load_variance_floor`) and
   is never a constant in this file — a hard-coded floor is a registry that does not bind.
3. **Spend a family budget on a raw member column.**  Every evidence column in the design
   matrix is exactly one family's aggregated score (:func:`assert_family_grain`); a raw
   member column reaching the matrix is a free vote and RAISES by name (§10.6).
4. **Flip a governed sign on outcome data.**  Evidence coefficients are bounded ``>= 0``
   after orientation.  The fit may shrink a family to zero; it may never re-point it
   against its filed direction because the outcomes preferred the other way.
5. **Force a cell.**  Every redundancy / CMI / incremental cell that misses its registered
   minimum is ``NOT_ESTIMABLE`` with the counts that made it so.

Zero authority.  Nothing here ranks, sizes, gates, originates or escalates; the report
carries the all-false authority stanza, ``non_promotion_bearing``, ``counterfactual_replay``
and the frame-2 survivorship labels as TOP-LEVEL keys.

Run::

    python3 -m scripts.prophet_fusion_c2 --out research/prophet_fusion/pr2_c2
    python3 -m scripts.prophet_fusion_c2 --selftest

The report carries no wall-clock stamp on purpose: two runs of the same CLI over the same
repo produce byte-identical JSON, which is the reproducibility receipt.  The date lives in
the companion doc and in git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts.prophet_fusion_arena import (                   # noqa: E402
    BACKTEST_LAWFUL_STATUSES,
    FRAME_KIND_BACKTEST,
    MIN_TEST_DATES,
    MIN_TRAIN_DATES,
    REGISTRY_PATH,
    Fold,
    Registry,
    build_folds,
    check_features,
    folds_for_labels,
    load_registry,
)
from scripts.prophet_fusion_labels import (                  # noqa: E402
    FusionRefusal,
    LabelFrame,
    load_prophet_rank_frame,
)
# PROVENANCE.  The underscored names below are imported from the RACE module on purpose:
# scripts/prophet_fusion_race.py is the canonical implementation of the sign law, the
# within-date percentile, the date-blocked bootstrap and PR-1b's §9.4 partial-correlation
# construction.  PR-2's descriptive incremental tier must reproduce §9.4 EXACTLY, so it
# calls race's own helpers rather than re-deriving them — one implementation, no mirror.
# If a race helper changes, this module inherits the change and TestDeterminism
# re-baselines visibly instead of two copies drifting apart in silence.
from scripts.prophet_fusion_race import (                    # noqa: E402
    OPTIONS_PRESENT_NO_FILED_DIRECTION,
    PRIMARY_COMPOSITION,
    PRIMARY_HORIZON,
    PRIMARY_K,
    PRIMARY_TUPLE,
    REGISTERED_SIGNS,
    STRUCTURAL_FAMILY_NOTES,
    RegisteredSign,
    RaceFrame,
    _date_blocked_ci,
    _opt,
    _oriented_values,
    _partial_spearman_by_date,
    _percentile_within_date,
    _round,
    _spearman_by_date,
    assert_no_outcomes,
    benjamini_hochberg,
    build_race_frame,
    load_snapshots,
    rung_g0,
)

SCHEMA = "prophet_fusion.pr2_c2.v1"

DEFAULT_OUT = "research/prophet_fusion/pr2_c2"

CANDIDATES_DIR = "data/us_prophet_rank/candidates"

#: §8.5 frame 1's only board-adjacent cross-section (1,717 curated rows).  The serving
#: side of the train/serve rule reads THIS stamp; the scan tier rides as a labelled
#: secondary exhibit and is never pooled with it (registry `era_boundaries`
#: `cv_universe_widening`).
SERVE_STAMP = "2026-08-07"
SERVE_TIER = "curated"

HORIZONS = (5, 10, 21)
SECONDARY_HORIZONS = tuple(h for h in HORIZONS if h != PRIMARY_HORIZON)

# --------------------------------------------------------------------------- #
# REGISTERED CONSTANTS.  Every one of these is echoed into `report["registered"]`,
# which byte-precedes every outcome block in the serialized document (asserted by
# tests/test_prophet_fusion_c2.py::TestRegisteredBeforeOutcomes).
# --------------------------------------------------------------------------- #

#: Inherited from PR-1b so the two artifacts' date-blocked intervals are comparable.
BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 20260814

#: New for PR-2, registered here: the CMI permutation null.
CMI_PERMUTATION_B = 500
CMI_PERMUTATION_SEED = 20260818

#: §5.3 redundancy cell minimums.  A cell that misses either is NOT_ESTIMABLE with its
#: counts printed — never forced, never pooled to reach the minimum.
REDUNDANCY_MIN_PAIRS_PER_DATE = 30
REDUNDANCY_MIN_DATES = 5

#: CMI estimator minimums (§5.3 / §9.3).
CMI_MIN_ROWS = 300
CMI_MIN_DATES = 8
CMI_TERCILE_CUTS = (1.0 / 3.0, 2.0 / 3.0)

#: The C2 model classes (§8.1's C2 row, spelled out so the report and the suite read the
#: same words).
C2_MODEL_CLASSES = ("elastic_net_logistic_nonneg", "elastic_net_linear_nonneg")

#: The registered hyper-parameter grid.  §8.2: grid size is DISCLOSED and small.
C2_ALPHAS = (0.01, 0.1, 1.0)
C2_L1_RATIOS = (0.0, 0.5, 1.0)
C2_GRID_SIZE = len(C2_ALPHAS) * len(C2_L1_RATIOS)

#: Inner selection block: the last 20% of TRAIN dates, date-contiguous, embargoed from
#: the inner-train block by the horizon.  No RNG anywhere in the selection — the split is
#: positional, so the choice is reproducible from the fold plan alone.
C2_INNER_VAL_SHARE = 0.20
C2_INNER_VAL_MIN_DATES = 3
C2_INNER_TRAIN_MIN_DATES = 20

#: L-BFGS-B settings, frozen so two runs of the same fold produce the same coefficients.
C2_MAXITER = 500
C2_FTOL = 1e-12
C2_GTOL = 1e-10

#: §10.6's family-budget mechanism, in one sentence, echoed into the report.
FAMILY_BUDGET_MECHANISM = (
    "STRUCTURAL, not penalized-into-existence: the design matrix carries exactly ONE "
    "evidence column per eligible family (the within-date member-percentile mean of its "
    "oriented, eligible members) plus that family's missingness indicator plus an "
    "intercept. A raw member column can never enter, so N correlated siblings inside one "
    "family can never buy N votes (§5.1/§10.6). assert_family_grain() raises by name.")

#: The survivorship labels, copied from PR-1b's shape (§8.5 pre-assignment, §9.6).
SURVIVORSHIP = {
    "frame2": "reconstructed curated universe; acceptable with disclosure",
    "price_basis": "pooled by explicit flag — exploratory, promotion-barred",
}

#: The exact, closed verdict vocabulary of the §5.3 "what does X add?" table.  A verdict
#: outside this tuple is a defect, and the suite pins the closure.
VERDICT_VOCABULARY = (
    "incremental_positive", "incremental_negative", "null_unresolved",
    "insufficient_coverage", "not_pit", "not_estimable", "excluded_train_serve_skew",
)

#: The census's eligibility reasons.  A member may carry SEVERAL — every exclusion names
#: itself and none is swallowed by another.
CENSUS_REASONS = (
    "eligible", "below_presence_floor", "vote_inert", "not_backtest_pit", "serving_dead",
    "excluded_train_serve_skew", "no_filed_direction", "absent_from_frame",
    "structurally_excluded", "unwired",
)


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

class C2Refusal(FusionRefusal):
    """The C2 harness cannot be run as specified."""


class DesignMatrixRefusal(C2Refusal):
    """A column tried to enter the design matrix at member grain (§10.6)."""


class FitRefusal(C2Refusal):
    """A fit was attempted without a lawful fold plan (§9.2).

    THIS IS THE WHOLE POINT OF THE CLASS.  The cheapest way to make a thin frame look
    answerable is to fit it in-sample and label the number "descriptive"; the label then
    falls off downstream and the in-sample coefficient is quoted as a fitted result.  The
    fit seam raises instead, so the weaker result cannot be produced at all.
    """


# --------------------------------------------------------------------------- #
# the registry's variance floor (PR-2 amendment) — READ, never hard-coded
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VarianceFloor:
    """``semantics.variance_floor_spec`` as the harness executes it.

    Every field is read from ``research/prophet_fusion/families.yml``.  Nothing here has
    a default: a registry that lost the block must REFUSE, because a silently defaulted
    floor is a registry amendment that does not bind anything.
    """

    axis: str
    min_distinct_values_per_date: int
    min_dates_with_variation_share: float
    excluded_from: tuple[str, ...]
    retained_in: tuple[str, ...]
    source_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "min_distinct_values_per_date": int(self.min_distinct_values_per_date),
            "min_dates_with_variation_share": float(self.min_dates_with_variation_share),
            "excluded_from": list(self.excluded_from),
            "retained_in": list(self.retained_in),
            "read_from": self.source_path,
            "law": ("PR-2 registry amendment DSC:COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-"
                    "VARIANCE. The presence floor cannot see a member whose values are "
                    "almost all the same value (presence ~100%, information ~0). This "
                    "axis is defined on FEATURES ALONE — no outcome data enters the rule, "
                    "so it cannot be tuned to results — and it is FRAME-RELATIVE, "
                    "computed at evaluation time, never a registry constant."),
        }


def load_variance_floor(path: Path | str | None = None) -> VarianceFloor:
    """Read the PR-2 variance floor out of the registry.  Fail closed."""
    target = Path(path) if path is not None else (_REPO_ROOT / REGISTRY_PATH)
    if not target.exists():
        raise C2Refusal(
            f"evidence-family registry not found: {target} — the variance floor is a "
            f"REGISTRY value (semantics.variance_floor_spec) and this module refuses to "
            f"supply a default for it; a hard-coded floor is a registry that binds "
            f"nothing.")
    doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    spec = ((doc or {}).get("semantics") or {}).get("variance_floor_spec")
    if not isinstance(spec, Mapping):
        raise C2Refusal(
            f"{target}: semantics.variance_floor_spec is missing — PR-2's floor-law "
            f"amendment is the registry's, not this module's. Restore the block or the "
            f"harness cannot judge vote-inertness at all.")
    for key in ("axis", "min_distinct_values_per_date", "min_dates_with_variation_share"):
        if spec.get(key) is None:
            raise C2Refusal(f"{target}: semantics.variance_floor_spec.{key} is missing")
    return VarianceFloor(
        axis=str(spec["axis"]),
        min_distinct_values_per_date=int(spec["min_distinct_values_per_date"]),
        min_dates_with_variation_share=float(spec["min_dates_with_variation_share"]),
        excluded_from=tuple(str(v) for v in (spec.get("excluded_from") or ())),
        retained_in=tuple(str(v) for v in (spec.get("retained_in") or ())),
        source_path=str(target.relative_to(_REPO_ROOT)
                        if _REPO_ROOT in target.parents else target),
    )


def registry_known_edges(path: Path | str | None = None) -> list[dict[str, Any]]:
    """``known_redundancy_edges`` verbatim — the registry's 're-measured in PR-2' promise."""
    target = Path(path) if path is not None else (_REPO_ROOT / REGISTRY_PATH)
    doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    edges = (doc or {}).get("known_redundancy_edges") or []
    out: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        pair = list(edge.get("pair") or [])
        out.append({"pair": [str(p) for p in pair], "relation": str(edge.get("relation") or ""),
                    "kind": str(edge.get("kind") or ""), "source": str(edge.get("source") or "")})
    return out


def registry_member_flags(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """``<FAMILY>.<member>`` -> the registry flags :class:`Registry` does not carry.

    ``load_registry`` models the fields the PIT gate needs; PR-2 additionally needs
    ``null_semantics`` (whose nulls are ANSWERS), ``serving_dead`` (whose feed stopped)
    and ``cross_sectional: false`` (F6's structural degeneracy).  Read here rather than
    widened in the arena dataclass, because arena is a sibling's file this PR may not
    touch.
    """
    target = Path(path) if path is not None else (_REPO_ROOT / REGISTRY_PATH)
    doc = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, Any]] = {}

    def _iter(node: Any, key_names: Sequence[str]) -> list[tuple[str, Mapping[str, Any]]]:
        if isinstance(node, Mapping):
            return [(str(k), v if isinstance(v, Mapping) else {}) for k, v in node.items()]
        if isinstance(node, (list, tuple)):
            rows = []
            for item in node:
                if not isinstance(item, Mapping):
                    continue
                key = next((str(item[n]) for n in key_names if item.get(n)), None)
                if key:
                    rows.append((key, item))
            return rows
        return []

    for fam_key, fam_body in _iter(doc.get("families"), ("family", "key", "id")):
        fam_cross = fam_body.get("cross_sectional")
        for mem_key, mem_body in _iter(fam_body.get("members"),
                                       ("member", "name", "key", "id")):
            cross = mem_body.get("cross_sectional")
            out[f"{fam_key}.{mem_key}"] = {
                "null_semantics": str(mem_body.get("null_semantics") or "unmeasured"),
                "serving_dead": bool(mem_body.get("serving_dead") or False),
                "cross_sectional": (bool(cross) if cross is not None
                                    else (bool(fam_cross) if fam_cross is not None else True)),
                "coverage_probe": bool(mem_body.get("coverage_probe") or False),
            }
    return out


# --------------------------------------------------------------------------- #
# the frame abstraction (one shape, two producers: the real store and the selftest)
# --------------------------------------------------------------------------- #

@dataclass
class C2Frame:
    """Features (NO outcomes), outcomes, and the champion baseline the plane conditions on.

    Every function below takes this shape, so the real graded-board frame and the
    synthetic selftest frame travel the SAME code path.  A machinery proof that runs on a
    different path than the artifact is not a proof of the artifact.
    """

    features: pd.DataFrame                       # date, ticker, member columns
    outcomes: pd.DataFrame                       # date, ticker, horizon, excess_spy
    g0: pd.DataFrame                             # date, ticker, g0_score
    signs: Mapping[str, RegisteredSign]
    labels: LabelFrame | None = None
    receipt: dict[str, Any] = field(default_factory=dict)

    @property
    def dates(self) -> list[str]:
        return sorted(self.features["date"].astype(str).unique().tolist())

    def outcome_slice(self, horizon: int) -> pd.DataFrame:
        slab = self.outcomes[self.outcomes["horizon"] == int(horizon)]
        return slab[["date", "ticker", "excess_spy"]].copy()


def build_c2_frame(*, root: Path | str | None = None,
                   raw: pd.DataFrame | None = None,
                   snapshots_path: Path | str | None = None) -> C2Frame:
    """The real §8.5 frame 2, plus the G0 champion replay the incremental plane conditions on."""
    race: RaceFrame = build_race_frame(root=root, raw=raw)
    snapshots = load_snapshots(snapshots_path)
    g0 = rung_g0(race, snapshots)
    g0_scores = g0.scores[["date", "ticker", "score"]].rename(columns={"score": "g0_score"})
    assert_no_outcomes(race.features, "build_c2_frame")
    receipt = dict(race.receipt)
    receipt["g0_replay"] = {
        "dates_raced": len(g0.dates),
        "dates_refused": len(g0.refusals),
        "refusals": [r.as_dict() for r in g0.refusals],
        "note": ("Z / the residualization anchor is the G0 REPLAY of the current scorer "
                 "over frozen published payloads (§6.1: the live score has never been "
                 "graded, N=0). A date with no frozen payload refuses for G0 and leaves "
                 "every conditioned cell, printed rather than smoothed."),
    }
    return C2Frame(features=race.features, outcomes=race.outcomes, g0=g0_scores,
                   signs=dict(REGISTERED_SIGNS), labels=race.labels, receipt=receipt)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _numeric_or_oriented(frame: pd.DataFrame, column: str,
                         sign: RegisteredSign | None) -> pd.Series:
    """The member's oriented value where a sign is filed; the raw numeric otherwise.

    The raw path exists for the CENSUS ONLY (measuring whether a column can order a
    cross-section at all).  An unsigned column never reaches a family score, a design
    matrix or a redundancy cell — reading its direction off this frame's outcomes is the
    audition §8.2/§9.8 forbids.
    """
    if sign is not None:
        return _oriented_values(frame, sign)
    return pd.to_numeric(frame[column], errors="coerce")


def _variation_by_date(frame: pd.DataFrame, values: pd.Series,
                       floor: VarianceFloor) -> dict[str, Any]:
    """The §5.3 variance axis: distinct non-null oriented values per date."""
    counts = values.groupby(frame["date"].astype(str)).apply(
        lambda block: int(block.dropna().nunique()))
    if counts.empty:
        return {"n_dates": 0, "n_dates_with_variation": 0, "variation_share": 0.0,
                "min_distinct": 0, "median_distinct": 0, "max_distinct": 0}
    carries = counts >= int(floor.min_distinct_values_per_date)
    return {
        "n_dates": int(len(counts)),
        "n_dates_with_variation": int(carries.sum()),
        "variation_share": _round(float(carries.mean())),
        "min_distinct": int(counts.min()),
        "median_distinct": _round(float(counts.median())),
        "max_distinct": int(counts.max()),
        "per_date_distinct": {str(k): int(v) for k, v in counts.sort_index().items()},
    }


def _coverage_by_date(frame: pd.DataFrame, values: pd.Series) -> dict[str, Any]:
    """min / median / max of the per-date non-null share.

    Printed rather than averaged away: the frame-2 pre-schema era reads 0.00 by ERA, and
    a whole-frame mean of 0.66 hides the fact that seven nights carry nothing at all.
    """
    shares = values.notna().groupby(frame["date"].astype(str)).mean()
    if shares.empty:
        return {"min": None, "median": None, "max": None, "n_dates_zero": 0}
    return {
        "min": _round(float(shares.min())),
        "median": _round(float(shares.median())),
        "max": _round(float(shares.max())),
        "n_dates_zero": int((shares <= 0.0).sum()),
        "n_dates_full": int((shares >= 1.0).sum()),
    }


# --------------------------------------------------------------------------- #
# Part 1 — the estimability census (feeds everything else)
# --------------------------------------------------------------------------- #

def frame1_slabs(root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """§8.5 frame 1 — the candidates store, PER STAMP DATE and per tier, never pooled.

    The registry's ``era_boundaries.cv_universe_widening`` names the break this respects:
    08-05/06 carry scan rows only and 08-07 carries 1,717 curated rows, so a pooled
    coverage number would average a universe that changed size mid-window.
    """
    base = Path(root) if root is not None else _REPO_ROOT
    cand_dir = base / CANDIDATES_DIR
    slabs: dict[str, dict[str, Any]] = {}
    if not cand_dir.is_dir():
        return slabs
    for path in sorted(cand_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if "stamp_date" not in frame.columns:
            continue
        frame = frame.copy()
        frame["_stamp"] = frame["stamp_date"].astype(str).str.slice(0, 10)
        tier_col = frame["tier"].astype("string").fillna("<null>") if "tier" in frame.columns \
            else pd.Series(["<null>"] * len(frame), index=frame.index, dtype="string")
        frame["_tier"] = tier_col
        for (stamp, tier), slab in frame.groupby(["_stamp", "_tier"], sort=True):
            slabs[f"{stamp}|{tier}"] = {
                "stamp_date": str(stamp), "tier": str(tier), "file": path.name,
                "n_rows": int(len(slab)), "frame": slab.reset_index(drop=True),
            }
    return slabs


def _serve_coverage(member_columns: Sequence[str], slab: pd.DataFrame | None, *,
                    comparable_columns: Sequence[str]) -> tuple[Any, dict[str, Any]]:
    """Serving-side coverage for one member, or the honest string status.

    ``not_yet_measurable`` is a STRING, never a number, and never 0.0.  §8.5.2's
    train/serve exclusion fires on MEASURED skew: a PR-1a telemetry column that has not
    been stamped yet has no serving reading at all, and scoring it 0.0 would exclude the
    member for a fact nobody measured.

    THE RULE COMPARES LIKE WITH LIKE.  ``comparable_columns`` are the member's columns
    that actually FED the train reading (i.e. are present on frame 2); only those can be
    skewed against it.  Averaging in a column the train side never carried is an
    apples-to-oranges ratio — measured here: F2.residual_alpha's ``alpha`` serves at
    0.930 against a train 1.000 (no skew at all), but pooling the unstamped
    ``alpha_percentile`` at 0.046 drags the mean to 0.488 and would have excluded F2's
    strongest member from the design matrix for a column that was never in it.  The
    whole-member reading rides beside it, labelled, because it is still worth seeing.
    """
    if slab is None:
        return "not_yet_measurable", {"reason": "serving stamp not present in the store"}
    all_present = [c for c in member_columns if c in slab.columns]
    absent = [c for c in member_columns if c not in slab.columns]
    shares = {c: _round(float(slab[c].notna().mean())) for c in all_present}
    detail: dict[str, Any] = {
        "columns_absent_from_store": absent, "per_column": shares,
        "serve_coverage_all_registered_columns": (
            _round(float(np.mean(list(shares.values())))) if shares else None),
        "comparability_law": (
            "the RULE reads only the columns that also fed the train coverage; a column "
            "the train side never carried cannot be skewed against it"),
    }
    comparable = [c for c in comparable_columns if c in slab.columns]
    if not comparable:
        detail["reason"] = ("no column of this member that feeds the TRAIN reading is "
                            "stamped in the candidates store yet (PR-1a telemetry debt)")
        return "not_yet_measurable", detail
    detail["columns_measured"] = comparable
    return _round(float(np.mean([shares[c] for c in comparable]))), detail


def estimability_census(frame: C2Frame, registry: Registry, floor: VarianceFloor, *,
                        member_flags: Mapping[str, Mapping[str, Any]],
                        serve_slab: pd.DataFrame | None = None,
                        serve_label: str = f"{SERVE_STAMP} {SERVE_TIER}") -> dict[str, Any]:
    """Every registry family x every wired member, on frame 2, with the serving side beside it.

    ONE PASS DECIDES EVERY DOWNSTREAM MEMBERSHIP.  The family score, the redundancy
    blocks, the CMI variables, the incremental table and the design matrix all read the
    verdicts computed here, so a member cannot be eligible for one and quietly excluded
    from another.  A member may carry SEVERAL reasons and every one is listed — the first
    failing gate is not a counterfactual for the others.
    """
    features = frame.features
    assert_no_outcomes(features, "estimability_census")
    n_rows = int(len(features))
    signs = dict(frame.signs)

    families: dict[str, Any] = {}
    for fam_key in sorted(registry.families):
        fam = registry.families[fam_key]
        member_rows: list[dict[str, Any]] = []
        for qualified in fam.members:
            member = registry.members[qualified]
            flags = dict(member_flags.get(qualified) or {})
            null_semantics = str(flags.get("null_semantics") or "unmeasured")
            serving_dead = bool(flags.get("serving_dead") or False)
            cross_sectional = bool(flags.get("cross_sectional", True))
            columns = list(member.columns)
            present = [c for c in columns if c in features.columns]
            absent = [c for c in columns if c not in features.columns]

            reasons: list[str] = []
            if not columns:
                reasons.append("unwired")
            if not cross_sectional:
                reasons.append("structurally_excluded")
            if member.pit_status not in BACKTEST_LAWFUL_STATUSES:
                reasons.append("not_backtest_pit")
            if serving_dead:
                reasons.append("serving_dead")

            # --- the signed vote column, if the registry filed a direction for one -----
            signed = [c for c in present if c in signs]
            vote_column = signed[0] if signed else None
            if columns and present and not signed:
                reasons.append("no_filed_direction")
            if columns and not present:
                reasons.append("absent_from_frame")

            # --- presence axis --------------------------------------------------------
            per_column_coverage = {c: _round(float(features[c].notna().mean()))
                                   for c in present}
            coverage_present = (_round(float(np.mean(list(per_column_coverage.values()))))
                                if per_column_coverage else 0.0)
            coverage_all = (_round(float(sum(per_column_coverage.values()) / len(columns)))
                            if columns else 0.0)
            # measured_negative: the null IS the producer's answer.  MEASURED rather than
            # assumed — the board ledger's boolean chips store False explicitly, so their
            # non-null share IS the measured share and the presence floor reads it
            # directly; a measured_negative member with no explicit negatives on the frame
            # would be a different fact and is reported as such.
            explicit_negatives = 0
            if vote_column is not None:
                col = features[vote_column]
                explicit_negatives = int((col == False).sum())      # noqa: E712 — object col
            counts_against = null_semantics != "measured_negative"
            if not counts_against and explicit_negatives == 0 and present:
                coverage_for_floor = 1.0
                coverage_basis = "measured_negative_nulls_are_answers"
            else:
                coverage_for_floor = coverage_present
                coverage_basis = ("non_null_share_over_present_columns"
                                  if counts_against else
                                  "non_null_share (measured_negative member stores its "
                                  "negatives EXPLICITLY on this frame, so the non-null "
                                  "share is the measured share — as C1 measured it)")
            member_floor = float(member.coverage_floor)
            if present and float(coverage_for_floor or 0.0) < member_floor:
                reasons.append("below_presence_floor")

            # --- variance axis (the PR-2 amendment) -----------------------------------
            variance: dict[str, Any] = {}
            vote_inert: bool | None = None
            for column in present:
                values = _numeric_or_oriented(features, column, signs.get(column))
                variance[column] = _variation_by_date(features, values, floor)
                variance[column]["oriented"] = column in signs
            axis_column = vote_column or (present[0] if present else None)
            if axis_column is not None:
                share = float(variance[axis_column]["variation_share"] or 0.0)
                vote_inert = share < float(floor.min_dates_with_variation_share)
                if vote_inert:
                    reasons.append("vote_inert")

            # --- serving side + §8.5.2 train/serve rule -------------------------------
            serve_value, serve_detail = _serve_coverage(
                columns, serve_slab, comparable_columns=present)
            train_serve: dict[str, Any] = {
                "serve_frame": serve_label, "serve_coverage": serve_value,
                "train_coverage": coverage_for_floor, **serve_detail}
            if isinstance(serve_value, (int, float)) and present:
                skew = float(serve_value) < 0.5 * float(coverage_for_floor or 0.0)
                train_serve["ratio_serve_over_train"] = _round(
                    float(serve_value) / float(coverage_for_floor)
                    if coverage_for_floor else None)
                train_serve["rule"] = ("§8.5.2: serve coverage < 0.5 x train coverage "
                                       "EXCLUDES the member from every fitted design "
                                       "matrix; the rule fires on MEASURED skew only")
                if skew:
                    reasons.append("excluded_train_serve_skew")
            else:
                train_serve["rule"] = ("not applied — serve coverage is "
                                       "`not_yet_measurable`, and an unmeasured serving "
                                       "side is not a measured skew")

            if not reasons:
                reasons.append("eligible")
            unknown = [r for r in reasons if r not in CENSUS_REASONS]
            if unknown:                                            # pragma: no cover
                raise C2Refusal(f"census emitted an unregistered reason {unknown} for "
                                f"{qualified}; the vocabulary is {list(CENSUS_REASONS)}")

            verdict = "eligible" if reasons == ["eligible"] else sorted(set(reasons))
            in_design = reasons == ["eligible"]
            # The family SCORE is C1's aggregation, so it keeps the members C1 raced:
            # signed, present, above the presence floor, carrying variation.  It does NOT
            # apply the FIT-only exclusions (serving_dead / train-serve skew), which is
            # exactly how the report can print `insider_cluster` as raced-in-C1 and
            # excluded-from-the-C2-fit in the same row.
            in_score = bool(
                vote_column is not None
                and "below_presence_floor" not in reasons
                and "vote_inert" not in reasons
                and "structurally_excluded" not in reasons
                and "not_backtest_pit" not in reasons)

            member_rows.append({
                "member": qualified, "family": fam_key,
                "pit_status": member.pit_status,
                "backtest_lawful": member.pit_status in BACKTEST_LAWFUL_STATUSES,
                "null_semantics": null_semantics,
                "serving_dead": serving_dead,
                "cross_sectional": cross_sectional,
                "columns": columns,
                "columns_present_on_frame": present,
                "columns_absent_from_frame": absent,
                "vote_column": vote_column,
                "sign": (int(signs[vote_column].sign) if vote_column else None),
                "sign_source": (signs[vote_column].source if vote_column else None),
                "coverage": {
                    "per_column": per_column_coverage,
                    "mean_over_present_columns": coverage_present,
                    "mean_over_all_registered_columns": coverage_all,
                    "used_for_floor": coverage_for_floor,
                    "basis": coverage_basis,
                    "floor": member_floor,
                    "n_explicit_negative_values": explicit_negatives,
                    "per_date": (_coverage_by_date(features, features[axis_column])
                                 if axis_column else {}),
                },
                "variance_axis": variance,
                "vote_inert": vote_inert,
                "train_serve": train_serve,
                "verdict": verdict,
                "reasons": sorted(set(reasons)),
                "in_family_score": in_score,
                "in_design_matrix": in_design,
                "n_rows": n_rows,
            })

        score_members = [m["vote_column"] for m in member_rows if m["in_family_score"]]
        design_members = [m["vote_column"] for m in member_rows if m["in_design_matrix"]]
        families[fam_key] = {
            "family": fam_key, "name": fam.name, "coverage_floor": fam.coverage_floor,
            "n_members": len(member_rows),
            "n_members_wired": sum(1 for m in member_rows if m["columns"]),
            "eligible_for_design_matrix": bool(design_members),
            "design_matrix_members": design_members,
            "family_score_members": score_members,
            "structural_note": STRUCTURAL_FAMILY_NOTES.get(fam_key),
            "members": member_rows,
        }

    c1_raced = ["alpha", "off_high", "sue_fresh", "smartmoney_add", "insider_cluster",
                "news_burst"]
    reconciliation = []
    for column in c1_raced:
        row = next((m for fam in families.values() for m in fam["members"]
                    if m["vote_column"] == column), None)
        reconciliation.append({
            "column": column,
            "member": row["member"] if row else None,
            "c1_disposition": "raced in PR-1b C1 (coverage floor 0.50, no variance axis)",
            "c2_verdict": row["verdict"] if row else "absent_from_registry",
            "in_family_score": row["in_family_score"] if row else False,
            "in_design_matrix": row["in_design_matrix"] if row else False,
            "variation_share": (
                (row["variance_axis"].get(column) or {}).get("variation_share")
                if row and row["variance_axis"] else None),
        })

    return {
        "law": ("Every registry family x every wired member. Coverage is the PRESENCE "
                "axis and variation_share is the VARIANCE axis; a member must clear BOTH "
                "to carry a vote. Every exclusion NAMES itself and a member may carry "
                "several — the first failing gate is not a counterfactual for the rest."),
        "frame": "frame2_graded_board",
        "n_rows": n_rows,
        "n_dates": len(frame.dates),
        "variance_floor": floor.as_dict(),
        "serve_frame": serve_label,
        "families": families,
        "c1_to_c2_reconciliation": reconciliation,
        "options_present_no_filed_direction": list(OPTIONS_PRESENT_NO_FILED_DIRECTION),
        "options_note": (
            "Present on frame 2, homed nowhere in the registry's SIGNED set: no single "
            "a-priori member direction is filed, and choosing signs from this frame's "
            "outcomes is the audition §8.2/§9.8 forbids. They appear in the census as "
            "unsigned and never in a score, a matrix or a cell."),
    }


def census_families_in_score(census: Mapping[str, Any]) -> list[str]:
    """Families carrying at least one score-eligible member, sorted."""
    return sorted(k for k, v in census["families"].items() if v["family_score_members"])


def census_families_in_design(census: Mapping[str, Any]) -> list[str]:
    """Families carrying at least one design-matrix-eligible member, sorted."""
    return sorted(k for k, v in census["families"].items()
                  if v["eligible_for_design_matrix"])


# --------------------------------------------------------------------------- #
# family aggregation (C1's construction, re-used everywhere so nothing drifts)
# --------------------------------------------------------------------------- #

def member_percentiles(frame: C2Frame, columns: Sequence[str]) -> pd.DataFrame:
    """date, ticker, <column> -> within-date percentile of the ORIENTED value.

    Nulls stay NULL (race's ``_percentile_within_date``): a missing member ABSTAINS and
    is never handed the mid-pool 0.5, because a neutral vote and no vote are different
    acts (§7 O6 / §9.9).
    """
    features = frame.features
    assert_no_outcomes(features, "member_percentiles")
    out = features[["date", "ticker"]].copy()
    for column in columns:
        sign = frame.signs.get(column)
        if sign is None:
            raise C2Refusal(
                f"{column!r} has no REGISTERED sign — an unsigned column may not be "
                f"aggregated into a family score; reading its direction off this frame's "
                f"outcomes is the audition §8.2/§9.8 forbids.")
        out[column] = _percentile_within_date(features, _oriented_values(features, sign))
    return out


def build_family_scores(frame: C2Frame, census: Mapping[str, Any], *,
                        membership: str = "score") -> tuple[pd.DataFrame, dict[str, Any]]:
    """C1's aggregation at family grain: the mean of its eligible members' percentiles.

    ``membership="score"`` keeps the members C1 raced (signed, present, above the presence
    floor, carrying variation).  ``membership="design"`` additionally drops the FIT-only
    exclusions (``serving_dead``, measured train/serve skew, non-PIT), which is why the
    same family can appear in a redundancy block and be absent from the design matrix.
    """
    if membership not in ("score", "design"):
        raise C2Refusal(f"unknown membership {membership!r}; known: score | design")
    key = "family_score_members" if membership == "score" else "design_matrix_members"
    per_family = {fam: list(body[key]) for fam, body in census["families"].items()
                  if body[key]}
    columns = sorted({c for cols in per_family.values() for c in cols})
    percentiles = member_percentiles(frame, columns)

    scores = frame.features[["date", "ticker"]].copy()
    missing = frame.features[["date", "ticker"]].copy()
    for fam in sorted(per_family):
        cols = sorted(per_family[fam])
        scores[fam] = percentiles[cols].mean(axis=1, skipna=True)
        # §5.1 missingness-is-first-class: 1 iff EVERY eligible member is null on the row.
        missing[f"{fam}__absent"] = percentiles[cols].isna().all(axis=1).astype(float)

    receipt = {
        "membership": membership,
        "families": sorted(per_family),
        "members_per_family": {k: sorted(v) for k, v in sorted(per_family.items())},
        "construction": (
            "Per member: within-date cross-sectional percentile rank (average ties) of "
            "the value oriented by its REGISTERED sign. Per family: the mean of its "
            "eligible members' percentiles, nulls ABSTAINING. Identical to PR-1b C1's "
            "aggregation so the two artifacts' family scores are the same object."),
        "missingness_law": (
            "One indicator per family, 1 iff every eligible member is null on the row. "
            "It is a first-class model input (registry semantics.missingness_is_first_"
            "class), never an imputed zero for the score itself."),
    }
    return scores, {"missing": missing, **receipt}


# --------------------------------------------------------------------------- #
# Part 2 — the §5.3 redundancy blocks
# --------------------------------------------------------------------------- #

def _spearman_cell(frame: pd.DataFrame, left: str, right: str, *,
                   min_pairs: int = REDUNDANCY_MIN_PAIRS_PER_DATE,
                   min_dates: int = REDUNDANCY_MIN_DATES,
                   b: int = BOOTSTRAP_B,
                   seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """One §5.3 cell: per-date cross-sectional rho, date-mean + date-blocked bootstrap CI.

    A STRICTER-MINIMUM SIBLING of race's ``_spearman_by_date`` (which registers a 5-pair
    minimum for the PR-1b construction).  §5.3's redundancy cells register 30 pairs within
    a date and 5 counted dates, so the counting is done here and the counts are PRINTED on
    every refusal.  The PR-1b construction itself still calls race's helper verbatim
    (Part 4b) — the two minimums are different registered laws, not two copies of one.
    """
    values: list[float] = []
    pair_counts: list[int] = []
    for _date, slab in frame.groupby("date", sort=True):
        both = slab[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
        pair_counts.append(int(len(both)))
        if len(both) < int(min_pairs):
            continue
        if both[left].nunique() <= 1 or both[right].nunique() <= 1:
            continue
        rho = both[left].corr(both[right], method="spearman")
        if pd.notna(rho):
            values.append(float(rho))
    n_pairs_median = _round(float(np.median(pair_counts))) if pair_counts else None
    if len(values) < int(min_dates):
        return {
            "status": "NOT_ESTIMABLE",
            "n_dates_counted": len(values),
            "n_dates_seen": len(pair_counts),
            "n_pairs_median": n_pairs_median,
            "min_pairs_per_date": int(min_pairs),
            "min_dates": int(min_dates),
            "reason": ("fewer counted dates than the registered §5.3 cell minimum — the "
                       "cell is NOT forced by pooling dates or by lowering the pair "
                       "minimum"),
        }
    ci = _date_blocked_ci(values, b=b, seed=seed)
    return {"status": "estimated", "tier": "date_blocked", "n_pairs_median": n_pairs_median,
            "n_dates_counted": len(values), **ci}


def _cross_section_cell(slab: pd.DataFrame, left: str, right: str, *,
                        min_pairs: int = REDUNDANCY_MIN_PAIRS_PER_DATE) -> dict[str, Any]:
    """A frame-1 cell: ONE cross-section, so plain rho + n and NO interval.

    §5.3 cells on frame 2 are date-blocked; frame 1 has a single stamp date, so the
    >= 5-counted-dates rule cannot hold by construction.  Reporting these under a
    ``single_cross_section`` tier — descriptive, no CI — keeps them from ever being read
    as, or pooled with, a date-blocked estimate.
    """
    both = slab[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(both) < int(min_pairs) or both[left].nunique() <= 1 or both[right].nunique() <= 1:
        return {"status": "NOT_ESTIMABLE", "tier": "single_cross_section",
                "n_pairs": int(len(both)), "min_pairs": int(min_pairs),
                "reason": ("below the registered pair minimum, or one side is constant "
                           "across the cross-section")}
    rho = both[left].corr(both[right], method="spearman")
    return {"status": "estimated", "tier": "single_cross_section",
            "rho": _round(rho), "n_pairs": int(len(both)),
            "no_ci_reason": ("one date is one block; a date-blocked interval over a "
                             "single block is not an interval")}


def _numeric_registry_columns(slab: pd.DataFrame, registry: Registry,
                              family: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Frame-1 columns of one family that can carry a cross-sectional rank at all."""
    usable: list[str] = []
    skipped: list[dict[str, Any]] = []
    for qualified in registry.families[family].members:
        for column in registry.members[qualified].columns:
            if column not in slab.columns:
                skipped.append({"column": column, "reason": "absent_from_stamp"})
                continue
            values = pd.to_numeric(slab[column], errors="coerce")
            if values.notna().sum() >= REDUNDANCY_MIN_PAIRS_PER_DATE:
                usable.append(column)
                continue
            mapped = _MAPPED_ORDINALS.get(column)
            if mapped is not None:
                skipped.append({"column": column, "reason": "mapped_ordinal",
                                "mapping": {str(k): float(v) for k, v in mapped.items()}})
                usable.append(column)
                continue
            skipped.append({"column": column,
                            "reason": ("not_measurable_categorical" if values.isna().all()
                                       else "below_pair_minimum")})
    return usable, skipped


#: Registered categorical->ordinal maps, imported from race so the ordering is the GATE's
#: and the confirmer's own documented one, never re-derived here.
from scripts.prophet_fusion_race import _GEX_ORDINAL, _TIER_ORDINAL    # noqa: E402

_MAPPED_ORDINALS: dict[str, Mapping[str, float]] = {
    "tier_cascade": _TIER_ORDINAL,
    "gex_confirm_verdict": _GEX_ORDINAL,
}


def _mapped_numeric(slab: pd.DataFrame, column: str) -> pd.Series:
    mapping = _MAPPED_ORDINALS.get(column)
    if mapping is None:
        return pd.to_numeric(slab[column], errors="coerce")
    numeric = slab[column].astype("string").str.strip().map(
        {str(k): float(v) for k, v in mapping.items()})
    return pd.to_numeric(numeric, errors="coerce")


def redundancy_blocks(frame: C2Frame, registry: Registry, census: Mapping[str, Any],
                      fam_scores: pd.DataFrame, *,
                      frame1: Mapping[str, Mapping[str, Any]],
                      bootstrap_b: int = BOOTSTRAP_B,
                      registry_path: Path | str | None = None) -> dict[str, Any]:
    """§5.3's Spearman blocks — within-family, cross-family, frame 1, and the known edges."""
    signed_present = {}
    inert = {}
    for fam, body in census["families"].items():
        cols = []
        for member in body["members"]:
            column = member["vote_column"]
            if column is None:
                continue
            cols.append(column)
            if member["vote_inert"]:
                inert[column] = member["variance_axis"].get(column, {}).get(
                    "variation_share")
        if cols:
            signed_present[fam] = sorted(cols)

    # --- frame 2, within family ----------------------------------------------------
    all_signed = sorted({c for cols in signed_present.values() for c in cols})
    pct = member_percentiles(frame, all_signed)
    within: list[dict[str, Any]] = []
    for fam in sorted(signed_present):
        cols = signed_present[fam]
        for i, left in enumerate(cols):
            for right in cols[i + 1:]:
                cell = _spearman_cell(pct, left, right, b=bootstrap_b)
                within.append({
                    "family": fam, "left": left, "right": right,
                    "left_vote_inert": left in inert, "right_vote_inert": right in inert,
                    "basis": "within-date percentile of the sign-oriented value",
                    **cell})

    # --- frame 2, cross family -------------------------------------------------------
    fams = [c for c in fam_scores.columns if c not in ("date", "ticker")]
    cross: dict[str, dict[str, Any]] = {}
    for left in sorted(fams):
        cross[left] = {}
        for right in sorted(fams):
            if left == right:
                cross[left][right] = {"status": "identity", "mean": 1.0}
                continue
            cross[left][right] = _spearman_cell(fam_scores, left, right, b=bootstrap_b)

    # --- frame 1, per stamp ----------------------------------------------------------
    def _frame1_block(slab: pd.DataFrame) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for fam in sorted(registry.families):
            body = census["families"].get(fam) or {}
            structural = any(not m["cross_sectional"] for m in body.get("members", []))
            if structural:
                out[fam] = {"status": "structurally_excluded",
                            "reason": ("F6-class members are row-constant per night "
                                       "(cross_sectional: false); a within-date rho over "
                                       "a constant is undefined, not small")}
                continue
            usable, skipped = _numeric_registry_columns(slab, registry, fam)
            work = pd.DataFrame({c: _mapped_numeric(slab, c) for c in usable})
            cells: list[dict[str, Any]] = []
            for i, left in enumerate(sorted(usable)):
                for right in sorted(usable)[i + 1:]:
                    cells.append({"left": left, "right": right,
                                  **_cross_section_cell(work, left, right)})
            out[fam] = {"status": "measured" if cells else "no_measurable_pair",
                        "n_columns_measured": len(usable), "cells": cells,
                        "columns_skipped": skipped}
        return out

    serve_key = f"{SERVE_STAMP}|{SERVE_TIER}"
    serve = frame1.get(serve_key)
    frame1_curated = {
        "stamp": SERVE_STAMP, "tier": SERVE_TIER,
        "status": "present" if serve else "absent_from_store",
        "n_rows": int(serve["n_rows"]) if serve else 0,
        "tier_law": ("ONE cross-section => the >= 5-counted-dates rule cannot hold, so "
                     "every cell here is `single_cross_section` tier: plain rho + n, no "
                     "CI, and NEVER pooled with a frame-2 date-blocked cell."),
        "families": _frame1_block(serve["frame"]) if serve else {},
    }
    scan_stamps = {}
    for key, body in sorted(frame1.items()):
        if body["tier"] == SERVE_TIER:
            continue
        scan_stamps[key] = {
            "stamp": body["stamp_date"], "tier": body["tier"], "n_rows": body["n_rows"],
            "families": _frame1_block(body["frame"]),
        }

    # --- the registry's known edges ---------------------------------------------------
    edges = []
    for edge in registry_known_edges(registry_path or registry.path):
        left_name, right_name = (edge["pair"] + ["", ""])[:2]
        measured = _measure_known_edge(left_name, right_name, registry, census,
                                       pct, fam_scores, serve, bootstrap_b)
        edges.append({**edge, **measured})

    return {
        "law": ("§5.3, pre-registered: Spearman blocks per-date then date-mean with a "
                "date-blocked bootstrap CI. A cell needs >= "
                f"{REDUNDANCY_MIN_PAIRS_PER_DATE} non-null pairs WITHIN a date for that "
                f"date to count and >= {REDUNDANCY_MIN_DATES} counted dates, else it is "
                "NOT_ESTIMABLE with its counts. No cell is forced."),
        "frame2_within_family": within,
        "frame2_cross_family": cross,
        "frame2_cross_family_note": (
            "Family score x family score over the families carrying a score-eligible "
            "member. A vote-inert member is excluded from the SCORE and its member-level "
            "row still appears in the within-family block, flagged — inertness is "
            "DISCLOSED, never hidden (registry variance_floor_spec.retained_in)."),
        "frame1_stamp_20260807": frame1_curated,
        "frame1_scan_stamps": scan_stamps,
        "known_edges": edges,
    }


def _measure_known_edge(left_name: str, right_name: str, registry: Registry,
                        census: Mapping[str, Any], pct: pd.DataFrame,
                        fam_scores: pd.DataFrame, serve: Mapping[str, Any] | None,
                        bootstrap_b: int) -> dict[str, Any]:
    """One ``known_redundancy_edges`` row -> a measured rho, or a NAMED missing side."""

    def _resolve(name: str) -> tuple[str | None, str | None]:
        """`FAMILY.member` -> (frame2 vote column, frame1 column), either may be None."""
        if "." not in name:
            return None, None
        member = registry.members.get(name)
        if member is None:
            return None, None
        body = census["families"].get(member.family) or {}
        row = next((m for m in body.get("members", []) if m["member"] == name), None)
        vote = row["vote_column"] if row else None
        store = None
        if serve is not None:
            store = next((c for c in member.columns if c in serve["frame"].columns), None)
        return vote, store

    left_vote, left_store = _resolve(left_name)
    right_vote, right_store = _resolve(right_name)

    if left_vote and right_vote and left_vote in pct.columns and right_vote in pct.columns:
        return {"measured_on": "frame2_graded_board",
                "columns": [left_vote, right_vote],
                "measurement": _spearman_cell(pct, left_vote, right_vote, b=bootstrap_b)}
    if left_store and right_store and serve is not None:
        slab = serve["frame"]
        work = pd.DataFrame({left_store: _mapped_numeric(slab, left_store),
                             right_store: _mapped_numeric(slab, right_store)})
        return {"measured_on": f"frame1_{SERVE_STAMP}_{SERVE_TIER}",
                "columns": [left_store, right_store],
                "measurement": _cross_section_cell(work, left_store, right_store)}
    missing = []
    if not (left_vote or left_store):
        missing.append(left_name)
    if not (right_vote or right_store):
        missing.append(right_name)
    return {"measured_on": None, "measurement": {"status": "NOT_MEASURABLE"},
            "missing_side": missing or [left_name, right_name],
            "reason": ("neither frame carries a wired, present column for the named "
                       "side(s) — the edge stays an ASSERTED prior and says so")}


# --------------------------------------------------------------------------- #
# Part 3 — conditional mutual information at family grain
# --------------------------------------------------------------------------- #

CMI_ESTIMATOR = {
    "variables": {
        "X": "family score -> within-date percentile -> fixed terciles at cuts (1/3, 2/3]",
        "Z": "G0 champion replay score -> within-date percentile -> the SAME fixed cuts",
        "Y": "1[excess_spy > 0] at the cell's horizon",
    },
    "weights": ("date-equal: every row in date d carries weight 1/n_d, so a night with "
                "120 names cannot outvote a night with 30 (§9.3's date-group law applied "
                "to an information estimate)"),
    "statistic": "plug-in CMI(X;Y|Z) on the weighted 3x3x2 table, natural log, reported in bits",
    "null": {"kind": "permutation of X within (date x Z-bin) strata",
             "b": CMI_PERMUTATION_B, "seed": CMI_PERMUTATION_SEED,
             "reported": ["observed", "null_mean", "excess", "p_one_sided"]},
    "minimums": {"min_rows": CMI_MIN_ROWS, "min_dates": CMI_MIN_DATES,
                 "every_z_bin_non_empty": True},
    "tier": "descriptive_in_sample_counterfactual",
}


def _tercile(pct: pd.Series) -> pd.Series:
    """Fixed cuts, never data-chosen: bin 0 <= 1/3 < bin 1 <= 2/3 < bin 2."""
    values = pd.to_numeric(pct, errors="coerce")
    out = pd.Series(np.nan, index=values.index, dtype="float64")
    low, high = CMI_TERCILE_CUTS
    out[values <= low] = 0.0
    out[(values > low) & (values <= high)] = 1.0
    out[values > high] = 2.0
    out[values.isna()] = np.nan
    return out


def _plug_in_cmi(x: np.ndarray, y: np.ndarray, z: np.ndarray,
                 weights: np.ndarray) -> float:
    """CMI(X;Y|Z) in BITS from a weighted 3x3x2 contingency table."""
    index = (x * 6 + z * 2 + y).astype("int64")
    table = np.bincount(index, weights=weights, minlength=18).reshape(3, 3, 2)
    total = table.sum()
    if total <= 0:
        return float("nan")
    p = table / total
    p_z = p.sum(axis=(0, 2))                     # (z,)
    p_xz = p.sum(axis=2)                         # (x, z)
    p_zy = p.sum(axis=0)                         # (z, y)
    out = 0.0
    for xi in range(3):
        for zi in range(3):
            for yi in range(2):
                joint = p[xi, zi, yi]
                if joint <= 0:
                    continue
                denominator = p_xz[xi, zi] * p_zy[zi, yi]
                if denominator <= 0:
                    continue
                out += joint * math.log(joint * p_z[zi] / denominator)
    return float(out / math.log(2.0))


def permute_within_strata(values: np.ndarray, strata: np.ndarray,
                          rng: np.random.Generator) -> np.ndarray:
    """Shuffle ``values`` WITHIN each stratum, leaving every stratum's multiset unchanged.

    The null has to destroy the X-Y association and NOTHING else: permuting X across
    Z-bins would also destroy the X-Z dependence the statistic conditions on, and the
    "null" would then be testing a different hypothesis than the observed statistic.
    Permuting within (date x Z-bin) keeps each date's weight and each Z-bin's X marginal
    exactly where they were — a property the suite asserts on this function directly.
    """
    order_by_stratum = np.argsort(strata, kind="stable")
    shuffled = np.lexsort((rng.random(len(values)), strata))
    out = np.empty_like(values)
    out[order_by_stratum] = values[shuffled]
    return out


def cmi_cell(joined: pd.DataFrame, *, family: str, horizon: int,
             b: int = CMI_PERMUTATION_B,
             seed: int = CMI_PERMUTATION_SEED) -> dict[str, Any]:
    """One (family, horizon) CMI cell with its seeded, stratified permutation null."""
    work = joined.dropna(subset=["x_bin", "z_bin", "y", "date"]).copy()
    n_rows, n_dates = int(len(work)), int(work["date"].nunique())
    z_bins = sorted(int(v) for v in work["z_bin"].unique()) if n_rows else []
    problems = []
    if n_rows < CMI_MIN_ROWS:
        problems.append(f"{n_rows} measured rows < {CMI_MIN_ROWS}")
    if n_dates < CMI_MIN_DATES:
        problems.append(f"{n_dates} dates < {CMI_MIN_DATES}")
    empty = [b_ for b_ in (0, 1, 2) if b_ not in z_bins]
    if empty:
        problems.append(f"Z-bin(s) {empty} empty")
    if problems:
        return {"family": family, "horizon": int(horizon), "status": "NOT_ESTIMABLE",
                "tier": CMI_ESTIMATOR["tier"], "n_rows": n_rows, "n_dates": n_dates,
                "z_bins_present": z_bins, "reason": "; ".join(problems),
                "law": ("the estimator's registered minimums are not met; the cell is "
                        "printed as a refusal with its counts rather than estimated on "
                        "a table that cannot support it")}

    counts = work.groupby("date")["y"].transform("size").to_numpy(dtype="float64")
    weights = 1.0 / counts
    x = work["x_bin"].to_numpy(dtype="int64")
    y = work["y"].to_numpy(dtype="int64")
    z = work["z_bin"].to_numpy(dtype="int64")
    observed = _plug_in_cmi(x, y, z, weights)

    # Permute X within (date x Z-bin) strata: the null keeps every stratum's marginal and
    # every date's weight, so it destroys ONLY the X-Y association the statistic reads.
    date_codes = pd.factorize(work["date"].astype(str), sort=True)[0]
    strata = date_codes.astype("int64") * 3 + z
    rng = np.random.default_rng(int(seed))
    nulls = np.empty(int(b), dtype="float64")
    for draw in range(int(b)):
        nulls[draw] = _plug_in_cmi(permute_within_strata(x, strata, rng), y, z, weights)
    null_mean = float(np.nanmean(nulls))
    return {
        "family": family, "horizon": int(horizon), "status": "estimated",
        "tier": CMI_ESTIMATOR["tier"], "n_rows": n_rows, "n_dates": n_dates,
        "z_bins_present": z_bins,
        "observed_bits": _round(observed), "null_mean_bits": _round(null_mean),
        "excess_bits": _round(observed - null_mean),
        "p_one_sided": _round(float((nulls >= observed).mean())),
        "permutation_b": int(b), "permutation_seed": int(seed),
    }


def cmi_block(frame: C2Frame, fam_scores: pd.DataFrame, *,
              families: Sequence[str],
              b: int = CMI_PERMUTATION_B,
              seed: int = CMI_PERMUTATION_SEED) -> dict[str, Any]:
    """Part 3: CMI(family ; outcome | champion) for every family x horizon."""
    g0 = frame.g0.copy()
    g0["g0_pct"] = _percentile_within_date(g0, g0["g0_score"])
    g0["z_bin"] = _tercile(g0["g0_pct"])
    cells: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        outcome = frame.outcome_slice(horizon)
        for family in families:
            slab = fam_scores[["date", "ticker", family]].copy()
            slab["x_pct"] = _percentile_within_date(slab, slab[family])
            slab["x_bin"] = _tercile(slab["x_pct"])
            joined = (slab.merge(g0[["date", "ticker", "z_bin"]], on=["date", "ticker"],
                                 how="inner")
                          .merge(outcome, on=["date", "ticker"], how="inner"))
            joined["y"] = (pd.to_numeric(joined["excess_spy"], errors="coerce") > 0
                           ).astype("float64")
            joined.loc[joined["excess_spy"].isna(), "y"] = np.nan
            cells.append(cmi_cell(joined[["date", "x_bin", "z_bin", "y"]],
                                  family=family, horizon=horizon, b=b, seed=seed))
    return {
        "estimator": CMI_ESTIMATOR,
        "primary_horizon": PRIMARY_HORIZON,
        "cells": cells,
        "reading": ("A positive excess says the family's tercile carries information "
                    "about the sign of forward excess that the CHAMPION's own tercile "
                    "does not. Every cell is in-sample and descriptive; nothing here "
                    "promotes, and the H=21 refusal is a printed result."),
    }


# --------------------------------------------------------------------------- #
# Part 4a — the cross-fitted residualization harness (the inferential tier)
# --------------------------------------------------------------------------- #

CROSSFIT_SPEC = {
    "residualizer": ("per fold, on TRAIN dates only: within-date percentile of the "
                     "outcome rank ~ a + b * within-date percentile of the G0 rank, OLS "
                     "with date-equal weights. (a, b) are FROZEN and fingerprinted; the "
                     "test fold's residual is outcome_pct - (a + b * g0_pct)."),
    "statistic": ("per family, per test date: Spearman(family score, residual); "
                  "aggregated over the test-date UNION across folds with a date-blocked "
                  "bootstrap CI"),
    "fold_law": (f"§9.2 minimum-usable-fold: >= {MIN_TRAIN_DATES} train dates and >= "
                 f"{MIN_TEST_DATES} test dates AFTER purge + embargo, else the harness "
                 f"REFUSES the fold and says so — it never silently shrinks one"),
    "leakage_fence": ("the fit sees NO test-fold row; assert_no_outcomes() guards every "
                      "feature frame and outcomes reach the harness only through the "
                      "labels path"),
}


@dataclass
class Residualizer:
    """Fit on the TRAIN fold only; carried to the test fold FROZEN.

    Modelled on ``arena.FoldNormalizer`` deliberately: the frozen parameters are a public
    field and :meth:`fingerprint` hashes them, so a test can perturb the TEST-fold
    outcomes and assert the fingerprint did not move.  That is a proof, not a promise —
    the number cannot have been reached by a test statistic if the hash of the parameters
    is unchanged.
    """

    params: dict[str, float] = field(default_factory=dict)
    n_fit_rows: int = 0
    fit_dates: tuple[str, ...] = ()
    fitted: bool = False

    def fit(self, frame: pd.DataFrame, *, outcome_pct: str = "outcome_pct",
            g0_pct: str = "g0_pct") -> "Residualizer":
        if self.fitted:
            raise C2Refusal(
                "this residualizer is already fitted — refusing to re-fit. §9.1b: the "
                "training-fold parameters are carried forward FROZEN; a re-fit is how a "
                "full-sample statistic reaches a feature.")
        block = frame[["date", outcome_pct, g0_pct]].dropna()
        if len(block) < 2 or block[g0_pct].nunique() <= 1:
            raise C2Refusal(
                f"residualizer cannot fit: {len(block)} usable train rows and "
                f"{int(block[g0_pct].nunique())} distinct anchor values — a degenerate "
                f"anchor is refused, never silently reduced to an intercept.")
        counts = block.groupby("date")[g0_pct].transform("size").to_numpy(dtype="float64")
        w = 1.0 / counts
        x = block[g0_pct].to_numpy(dtype="float64")
        y = block[outcome_pct].to_numpy(dtype="float64")
        sw = w.sum()
        mean_x = float((w * x).sum() / sw)
        mean_y = float((w * y).sum() / sw)
        var_x = float((w * (x - mean_x) ** 2).sum() / sw)
        cov = float((w * (x - mean_x) * (y - mean_y)).sum() / sw)
        slope = 0.0 if var_x <= 0 else cov / var_x
        self.params = {"a": float(mean_y - slope * mean_x), "b": float(slope)}
        self.n_fit_rows = int(len(block))
        self.fit_dates = tuple(sorted(block["date"].astype(str).unique()))
        self.fitted = True
        return self

    def residual(self, frame: pd.DataFrame, *, outcome_pct: str = "outcome_pct",
                 g0_pct: str = "g0_pct") -> pd.Series:
        if not self.fitted:
            raise C2Refusal("residual() before fit() — the transform has no training-fold "
                            "parameters to carry")
        x = pd.to_numeric(frame[g0_pct], errors="coerce")
        y = pd.to_numeric(frame[outcome_pct], errors="coerce")
        return y - (self.params["a"] + self.params["b"] * x)

    def fingerprint(self) -> str:
        blob = json.dumps({"kind": "outcome_pct ~ a + b*g0_pct (date-equal WLS)",
                           "params": self.params}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        return {"params": {k: _round(v) for k, v in self.params.items()},
                "n_fit_rows": self.n_fit_rows, "n_fit_dates": len(self.fit_dates),
                "fit_range": [self.fit_dates[0], self.fit_dates[-1]] if self.fit_dates else [],
                "fingerprint": self.fingerprint()}


def _residual_frame(frame: C2Frame, fam_scores: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """(date, ticker, family scores, outcome_pct, g0_pct) — the crossfit's working frame."""
    outcome = frame.outcome_slice(horizon)
    g0 = frame.g0.copy()
    joined = (fam_scores.merge(g0, on=["date", "ticker"], how="inner")
                        .merge(outcome, on=["date", "ticker"], how="inner"))
    joined = joined.dropna(subset=["excess_spy", "g0_score"])
    joined["outcome_pct"] = _percentile_within_date(joined, joined["excess_spy"])
    joined["g0_pct"] = _percentile_within_date(joined, joined["g0_score"])
    return joined


def crossfit_incremental(frame: C2Frame, fam_scores: pd.DataFrame,
                         folds: Sequence[Fold], *, families: Sequence[str],
                         horizon: int = PRIMARY_HORIZON,
                         bootstrap_b: int = BOOTSTRAP_B) -> dict[str, Any]:
    """Cross-fitted incremental-vs-Prophet, per family, over the test-date union.

    RAISES on an empty fold plan.  There is no in-sample branch here to fall back to —
    see :class:`FitRefusal`.
    """
    if not folds:
        raise FitRefusal(
            "crossfit_incremental was handed ZERO usable folds. There is no in-sample "
            "fallback in this module: an in-sample residualization is a DIFFERENT and "
            "weaker estimator, and labelling it 'cross-fitted' downstream is exactly the "
            "failure the §9.2 refusal exists to prevent.")
    work = _residual_frame(frame, fam_scores, horizon)
    per_family: dict[str, list[float]] = {f: [] for f in families}
    fold_rows: list[dict[str, Any]] = []
    for fold in folds:
        train = work[work["date"].isin(set(fold.train_dates))]
        test = work[work["date"].isin(set(fold.test_dates))]
        if train.empty or test.empty:
            fold_rows.append({"fold": fold.index, "status": "no_rows",
                              "n_train_rows": int(len(train)),
                              "n_test_rows": int(len(test))})
            continue
        residualizer = Residualizer().fit(train)
        test = test.copy()
        test["residual"] = residualizer.residual(test)
        per_fold: dict[str, Any] = {}
        for family in families:
            values = _spearman_by_date(test[["date", family, "residual"]], family,
                                       "residual")
            per_family[family].extend(values)
            per_fold[family] = {"n_test_dates_counted": len(values),
                                "mean_rho": _round(float(np.mean(values)) if values else None)}
        fold_rows.append({
            "fold": fold.index, "status": "fitted",
            "n_train_dates": len(fold.train_dates), "n_test_dates": len(fold.test_dates),
            "n_purged_dates": len(fold.purged_dates),
            "n_embargoed_dates": len(fold.embargoed_dates),
            "n_train_rows": int(len(train)), "n_test_rows": int(len(test)),
            "residualizer": residualizer.as_dict(),
            "per_family": per_fold,
        })
    aggregate = {family: {"tier": "crossfit_out_of_fold",
                          **_date_blocked_ci(per_family[family], b=bootstrap_b,
                                             seed=BOOTSTRAP_SEED)}
                 for family in families}
    return {"status": "estimated", "horizon": int(horizon), "spec": CROSSFIT_SPEC,
            "n_folds": len(folds), "folds": fold_rows, "per_family": aggregate}


# --------------------------------------------------------------------------- #
# Part 4b — the descriptive in-sample tier (PR-1b §9.4, extended over horizons)
# --------------------------------------------------------------------------- #

def _normal_two_sided_p(values: Sequence[float]) -> float | None:
    """Two-sided p from the date-blocked mean / SE normal approximation.

    DISCLOSED, not hidden: with 6-24 date blocks the t and the normal differ in the third
    decimal and no verdict in this file turns on that difference — but the method is
    named in every cell that uses it (`p_method`) so a reader never has to guess.
    """
    arr = np.array([v for v in values if math.isfinite(v)], dtype="float64")
    if len(arr) < 3:
        return None
    se = float(arr.std(ddof=1) / math.sqrt(len(arr)))
    if not math.isfinite(se) or se == 0.0:
        return None
    return float(math.erfc(abs(float(arr.mean()) / se) / math.sqrt(2.0)))


def descriptive_incremental(frame: C2Frame, fam_scores: pd.DataFrame, *,
                            families: Sequence[str],
                            bootstrap_b: int = BOOTSTRAP_B) -> dict[str, Any]:
    """Plain rho and partial rho | G0 per family x horizon — PR-1b §9.4's construction."""
    g0 = frame.g0.rename(columns={"g0_score": "g0_score"})
    cells: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        outcome = frame.outcome_slice(horizon)
        joined = fam_scores.merge(outcome, on=["date", "ticker"], how="left")
        conditioned = joined.merge(g0, on=["date", "ticker"], how="inner")
        for family in families:
            raw = _spearman_by_date(joined, family, "excess_spy")
            partial = _partial_spearman_by_date(conditioned, family, "excess_spy",
                                                ["g0_score"])
            cells.append({
                "family": family, "horizon": int(horizon),
                "tier": "descriptive_in_sample_counterfactual",
                "n_rows": int(joined[[family, "excess_spy"]].dropna().shape[0]),
                "spearman_vs_outcome": _date_blocked_ci(raw, b=bootstrap_b,
                                                        seed=BOOTSTRAP_SEED),
                "partial_spearman_given_g0": _date_blocked_ci(partial, b=bootstrap_b,
                                                              seed=BOOTSTRAP_SEED),
                "p_partial": _round(_normal_two_sided_p(partial)),
                "p_method": ("two-sided normal approximation on the date-blocked mean / "
                             "SE over nights (disclosed; the t and the normal differ in "
                             "the third decimal at these block counts)"),
                "n_dates_partial": len(partial),
            })
    return {
        "method": ("rank-residual partial correlation within date: rank every series "
                   "inside the night, regress the family rank and the outcome rank on "
                   "the G0-replay rank, correlate the residuals; date-blocked bootstrap "
                   "CI over nights. Identical construction to PR-1b §9.4 — it calls "
                   "race's own helpers rather than re-deriving them."),
        "tier": "descriptive_in_sample_counterfactual",
        "cells": cells,
        "reading": ("This tier is computable TODAY and is what feeds the §5.3 verdict "
                    "table. It is in-sample by construction and promotion-barred; the "
                    "cross-fitted tier beside it is the one that would carry inference, "
                    "and on this frame it is refused."),
    }


# --------------------------------------------------------------------------- #
# Part 7 — the C2 fit machinery (reachable ONLY through a lawful fold plan)
# --------------------------------------------------------------------------- #

def assert_family_grain(columns: Sequence[str], registry: Registry,
                        families: Sequence[str]) -> None:
    """§10.6: every evidence column is ONE family's score.  A member column RAISES.

    This is the anti-double-count budget as a STRUCTURE.  If a raw member column could
    reach the matrix, a family with four correlated siblings would buy four votes and the
    budget would be defeated by copy-paste — so the check is on the column NAMES, before
    any value is read, and it names the offender.
    """
    allowed = {f"{family}__score" for family in families}
    for column in columns:
        if column in allowed:
            continue
        member = registry.columns.get(column)
        if member is not None:
            raise DesignMatrixRefusal(
                f"{column!r} is a raw MEMBER column ({member.family}.{member.key}) and "
                f"may not enter the C2 design matrix. §10.6: evidence enters by FAMILY "
                f"at every rung C1-C5 — a member column is a family budget spent twice. "
                f"Aggregate it into {member.family}__score or leave it out.")
        raise DesignMatrixRefusal(
            f"{column!r} is not a registered family score. The C2 matrix carries exactly "
            f"one column per eligible family plus that family's missingness indicator "
            f"plus an intercept, and nothing else: {sorted(allowed)}")


@dataclass(frozen=True)
class C2Design:
    """The matrix, the column roles, and the receipt that makes the budget auditable."""

    matrix: np.ndarray
    columns: tuple[str, ...]
    families: tuple[str, ...]
    evidence_index: tuple[int, ...]
    missingness_index: tuple[int, ...]
    intercept_index: int
    dates: np.ndarray
    keys: pd.DataFrame
    receipt: dict[str, Any]


def build_design_matrix(frame: C2Frame, registry: Registry, census: Mapping[str, Any],
                        *, fam_scores: pd.DataFrame | None = None,
                        missing: pd.DataFrame | None = None) -> C2Design:
    """One column per eligible family + one missingness indicator each + an intercept.

    ``check_features`` gates the MEMBER columns feeding the scores (frame_kind backtest),
    so an unregistered / forbidden / non-PIT member cannot reach the matrix even
    indirectly, and ``assert_no_outcomes`` guards the feature frame.
    """
    assert_no_outcomes(frame.features, "build_design_matrix")
    families = census_families_in_design(census)
    if not families:
        raise DesignMatrixRefusal(
            "no family is eligible for the C2 design matrix on this frame — every "
            "registered family is absent, below its presence floor, vote-inert, non-PIT, "
            "serving-dead or structurally excluded. A matrix with no evidence column is "
            "not a null result about the evidence, it is a null result about the frame.")
    if fam_scores is None or missing is None:
        fam_scores, receipt = build_family_scores(frame, census, membership="design")
        missing = receipt["missing"]
    # THE FENCE RUNS ON WHAT THE CALLER HANDED OVER, not on the slice this function goes
    # on to select.  Validating only the selection would let a caller smuggle a raw member
    # column into the frame and have it silently ignored -- which reads like acceptance.
    assert_family_grain([f"{c}__score" if c in census["families"] else c
                         for c in fam_scores.columns if c not in ("date", "ticker")],
                        registry, sorted(census["families"]))

    member_columns = sorted({c for family in families
                             for c in census["families"][family]["design_matrix_members"]})
    gate = check_features(registry, member_columns, frame_kind=FRAME_KIND_BACKTEST)

    evidence = fam_scores[["date", "ticker"] + families].copy()
    evidence.columns = ["date", "ticker"] + [f"{f}__score" for f in families]
    assert_family_grain([c for c in evidence.columns if c not in ("date", "ticker")],
                        registry, families)

    joined = evidence.merge(missing, on=["date", "ticker"], how="left")
    score_cols = [f"{f}__score" for f in families]
    absent_cols = [f"{f}__absent" for f in families]
    for column in absent_cols:
        if column not in joined.columns:
            joined[column] = 1.0
    # A family that ABSTAINS on a row contributes its missingness indicator, and its score
    # slot carries 0.0 alongside the SET indicator -- never a mid-pool 0.5, which would be
    # imputation at the neutral value (registry semantics.null_is_not_zero).  The pair
    # (score=0, absent=1) is a distinct, learnable state; (score=0.5, absent=0) would be a
    # lie the model cannot tell from a real half-percentile.
    filled = joined[score_cols].fillna(0.0).to_numpy(dtype="float64")
    indicators = joined[absent_cols].fillna(1.0).to_numpy(dtype="float64")
    intercept = np.ones((len(joined), 1), dtype="float64")
    matrix = np.hstack([intercept, filled, indicators])
    columns = ("intercept",) + tuple(score_cols) + tuple(absent_cols)

    receipt = {
        "family_budget_mechanism": FAMILY_BUDGET_MECHANISM,
        "families": list(families),
        "n_evidence_columns": len(score_cols),
        "n_missingness_columns": len(absent_cols),
        "members_feeding_scores": list(gate.members),
        "member_columns_gated": list(gate.columns),
        "frame_kind": gate.frame_kind,
        "abstention_encoding": ("score slot 0.0 WITH the family's missingness indicator "
                                "set to 1; never the mid-pool 0.5 (registry "
                                "semantics.null_is_not_zero / abstention_is_not_a_zero_vote)"),
    }
    return C2Design(matrix=matrix, columns=columns, families=tuple(families),
                    evidence_index=tuple(range(1, 1 + len(score_cols))),
                    missingness_index=tuple(range(1 + len(score_cols), matrix.shape[1])),
                    intercept_index=0,
                    dates=joined["date"].astype(str).to_numpy(),
                    keys=joined[["date", "ticker"]].reset_index(drop=True),
                    receipt=receipt)


def _date_equal_weights(dates: np.ndarray) -> np.ndarray:
    """w_i = 1 / (D * n_{d(i)}) — every night contributes exactly 1/D of the loss (§9.3)."""
    labels, inverse, sizes = np.unique(dates, return_inverse=True, return_counts=True)
    return 1.0 / (float(len(labels)) * sizes[inverse].astype("float64"))


def fit_c2_head(matrix: np.ndarray, y: np.ndarray, dates: np.ndarray, *,
                head: str, alpha: float, l1_ratio: float,
                evidence_index: Sequence[int],
                missingness_index: Sequence[int]) -> dict[str, Any]:
    """One elastic-net fit with the governed non-negativity bound on evidence coefs.

    THE BOUND IS THE SIGN LAW.  Every entering family carries a filed POSITIVE direction
    after orientation, so ``w_f >= 0``: the fit may SHRINK a family to zero when the data
    do not support it, and it may never re-point that family against its governed sign
    because the outcomes preferred the other way.  With ``w >= 0`` the L1 term is LINEAR
    on the feasible set, so the objective is smooth and L-BFGS-B is exact — no subgradient
    games, and the optimum is reproducible from a zero init.

    Missingness coefficients carry RIDGE ONLY and are unbounded: they are epistemic
    (whether the family spoke), carry no governed direction, and keeping them out of L1
    keeps the objective smooth.  The intercept is unpenalized and unbounded.
    """
    if head not in C2_MODEL_CLASSES:
        raise C2Refusal(f"unknown head {head!r}; registered: {list(C2_MODEL_CLASSES)}")
    w = _date_equal_weights(dates)
    evidence_index = list(evidence_index)
    missingness_index = list(missingness_index)
    n_params = matrix.shape[1]

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        z = matrix @ theta
        if head == "elastic_net_logistic_nonneg":
            # log(1+exp(z)) computed stably.
            loss = float((w * (np.logaddexp(0.0, z) - y * z)).sum())
            residual = 1.0 / (1.0 + np.exp(-z)) - y
            grad = matrix.T @ (w * residual)
        else:
            diff = z - y
            loss = float((w * diff ** 2).sum())
            grad = 2.0 * (matrix.T @ (w * diff))
        ev = theta[evidence_index]
        ms = theta[missingness_index]
        loss += float(alpha * (l1_ratio * ev.sum() + 0.5 * (1.0 - l1_ratio) * (ev ** 2).sum()))
        loss += float(0.5 * alpha * (1.0 - l1_ratio) * (ms ** 2).sum())
        grad = grad.copy()
        grad[evidence_index] += alpha * (l1_ratio + (1.0 - l1_ratio) * ev)
        grad[missingness_index] += alpha * (1.0 - l1_ratio) * ms
        return loss, grad

    bounds = [(None, None)] * n_params
    for index in evidence_index:
        bounds[index] = (0.0, None)
    result = minimize(objective, np.zeros(n_params, dtype="float64"), jac=True,
                      method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": C2_MAXITER, "ftol": C2_FTOL, "gtol": C2_GTOL})
    theta = np.asarray(result.x, dtype="float64")
    return {"head": head, "alpha": float(alpha), "l1_ratio": float(l1_ratio),
            "theta": theta, "converged": bool(result.success),
            "n_iterations": int(result.nit), "objective": _round(float(result.fun))}


def _head_loss(matrix: np.ndarray, y: np.ndarray, dates: np.ndarray,
               theta: np.ndarray, *, head: str) -> float:
    """The date-equal weighted log-loss (logistic) / MSE (linear), penalty EXCLUDED."""
    w = _date_equal_weights(dates)
    z = matrix @ theta
    if head == "elastic_net_logistic_nonneg":
        return float((w * (np.logaddexp(0.0, z) - y * z)).sum())
    return float((w * (z - y) ** 2).sum())


def _inner_split(train_dates: Sequence[str], horizon: int) -> tuple[list[str], list[str]]:
    """Last 20% of TRAIN dates as the inner validation block, embargoed by the horizon."""
    dates = list(train_dates)
    n_val = max(C2_INNER_VAL_MIN_DATES, int(round(C2_INNER_VAL_SHARE * len(dates))))
    if len(dates) <= n_val + int(horizon) + C2_INNER_TRAIN_MIN_DATES:
        raise FitRefusal(
            f"inner selection block cannot be cut: {len(dates)} train dates leave fewer "
            f"than {C2_INNER_TRAIN_MIN_DATES} inner-train dates after a {n_val}-date "
            f"validation block and a {int(horizon)}-date embargo. The grid is NOT chosen "
            f"on the outer test fold and it is NOT chosen without an embargo.")
    inner_val = dates[len(dates) - n_val:]
    inner_train = dates[:len(dates) - n_val - int(horizon)]
    return inner_train, inner_val


def select_hyperparameters(matrix: np.ndarray, y: np.ndarray, dates: np.ndarray, *,
                           head: str, train_dates: Sequence[str], horizon: int,
                           evidence_index: Sequence[int],
                           missingness_index: Sequence[int]) -> dict[str, Any]:
    """The registered 3x3 grid, scored on the inner validation block.

    Tie rule: LARGEST alpha, then LARGEST l1_ratio.  The simpler (more shrunk, more
    sparse) model wins ties by house law, so a tie can never be broken toward complexity.
    """
    inner_train, inner_val = _inner_split(train_dates, horizon)
    train_mask = np.isin(dates, np.array(inner_train, dtype=object))
    val_mask = np.isin(dates, np.array(inner_val, dtype=object))
    if not train_mask.any() or not val_mask.any():
        raise FitRefusal("the inner split selected zero rows on one side — refusing to "
                         "choose hyper-parameters on an empty block")
    scored: list[dict[str, Any]] = []
    for alpha in C2_ALPHAS:
        for l1_ratio in C2_L1_RATIOS:
            fit = fit_c2_head(matrix[train_mask], y[train_mask], dates[train_mask],
                              head=head, alpha=alpha, l1_ratio=l1_ratio,
                              evidence_index=evidence_index,
                              missingness_index=missingness_index)
            loss = _head_loss(matrix[val_mask], y[val_mask], dates[val_mask],
                              fit["theta"], head=head)
            scored.append({"alpha": float(alpha), "l1_ratio": float(l1_ratio),
                           "inner_val_loss": _round(loss, 10),
                           "converged": fit["converged"]})
    # Tie rule, house law: LARGEST alpha then LARGEST l1_ratio, so a tie is never broken
    # toward the less-shrunk / less-sparse model.  The 10-dp rounding is what makes a tie
    # a TIE rather than a float artifact at the 15th decimal.
    chosen = min(scored, key=lambda row: (row["inner_val_loss"], -row["alpha"],
                                          -row["l1_ratio"]))
    return {
        "inner_train_dates": len(inner_train), "inner_val_dates": len(inner_val),
        "inner_train_range": [inner_train[0], inner_train[-1]] if inner_train else [],
        "inner_val_range": [inner_val[0], inner_val[-1]] if inner_val else [],
        "embargo_dates_between": int(horizon),
        "grid_size": C2_GRID_SIZE, "grid": scored,
        "chosen": {"alpha": chosen["alpha"], "l1_ratio": chosen["l1_ratio"]},
        "selection_rule": ("inner date-equal log-loss (logistic) / MSE (linear) on the "
                           "last 20% of TRAIN dates, embargoed from the inner-train block "
                           "by the horizon; ties -> LARGEST alpha then LARGEST l1_ratio "
                           "(the simpler model wins ties, house law)"),
    }


def _p_at_k(order: pd.DataFrame, *, k: int = PRIMARY_K) -> dict[str, Any]:
    """Raw-order P@K and top-K mean excess, per date then date-mean.

    ``composition: raw`` and labelled as such everywhere it is printed: the DEPLOYED
    composition needs the champion's stage buckets, which a synthetic frame does not have
    and which no fold plan on the real frame has ever existed to join.  §8.3 demotes the
    raw order to a diagnostic and this is that diagnostic, not a primary.
    """
    per_date: list[float] = []
    per_date_mean: list[float] = []
    for _date, slab in order.groupby("date", sort=True):
        block = slab.dropna(subset=["score", "excess_spy"])
        if len(block) < k:
            continue
        top = block.sort_values(["score", "ticker"], ascending=[False, True]).head(k)
        per_date.append(float((top["excess_spy"] > 0).mean()))
        per_date_mean.append(float(top["excess_spy"].mean()))
    return {"composition": "raw", "k": int(k), "n_dates": len(per_date),
            f"p_at_{k}": _round(float(np.mean(per_date)) if per_date else None),
            f"top_{k}_mean_excess": _round(float(np.mean(per_date_mean))
                                           if per_date_mean else None)}


def fit_c2_over_folds(frame: C2Frame, registry: Registry, census: Mapping[str, Any],
                      folds: Sequence[Fold], *, head: str,
                      horizon: int = PRIMARY_HORIZON) -> dict[str, Any]:
    """The C2 fit, per fold.  RAISES on an empty fold plan — there is no in-sample branch.

    Returns per-fold coefficients, the inner grid choice, and the test-fold raw-order
    diagnostic.  Nothing here is reachable on today's real frame, which is the point:
    :func:`c2_fit_block` calls :func:`folds_for_labels` first and emits the §9.2 refusal.
    """
    if not folds:
        raise FitRefusal(
            "fit_c2_over_folds was handed ZERO usable folds (§9.2 minimum-usable-fold). "
            "This module has NO in-sample fallback fit: an in-sample C2 read is a "
            "different and weaker estimator, and the one thing a research artifact must "
            "never do is publish the weaker number under the stronger number's name.")
    design = build_design_matrix(frame, registry, census)
    outcome = frame.outcome_slice(horizon)
    joined = design.keys.merge(outcome, on=["date", "ticker"], how="left")
    excess = pd.to_numeric(joined["excess_spy"], errors="coerce").to_numpy(dtype="float64")
    measured = np.isfinite(excess)
    y = (excess > 0).astype("float64") if head == "elastic_net_logistic_nonneg" else excess

    fold_rows: list[dict[str, Any]] = []
    for fold in folds:
        train_mask = measured & np.isin(design.dates, np.array(fold.train_dates, dtype=object))
        test_mask = measured & np.isin(design.dates, np.array(fold.test_dates, dtype=object))
        if not train_mask.any() or not test_mask.any():
            fold_rows.append({"fold": fold.index, "status": "no_measured_rows"})
            continue
        selection = select_hyperparameters(
            design.matrix[train_mask], y[train_mask], design.dates[train_mask],
            head=head, train_dates=[d for d in fold.train_dates
                                    if d in set(design.dates[train_mask])],
            horizon=horizon, evidence_index=design.evidence_index,
            missingness_index=design.missingness_index)
        fit = fit_c2_head(design.matrix[train_mask], y[train_mask],
                          design.dates[train_mask], head=head,
                          alpha=selection["chosen"]["alpha"],
                          l1_ratio=selection["chosen"]["l1_ratio"],
                          evidence_index=design.evidence_index,
                          missingness_index=design.missingness_index)
        theta = fit["theta"]
        coefficients = {design.columns[i]: _round(float(theta[i]))
                        for i in range(len(design.columns))}
        pinned = [design.columns[i] for i in design.evidence_index
                  if abs(float(theta[i])) <= 1e-12]

        test_scores = design.matrix[test_mask] @ theta
        order = design.keys[test_mask].copy()
        order["score"] = test_scores
        order = order.merge(outcome, on=["date", "ticker"], how="left")
        fold_rows.append({
            "fold": fold.index, "status": "fitted", "head": head,
            "n_train_dates": len(fold.train_dates), "n_test_dates": len(fold.test_dates),
            "n_train_rows": int(train_mask.sum()), "n_test_rows": int(test_mask.sum()),
            "inner_selection": selection,
            "coefficients": coefficients,
            "evidence_coefficients": {design.columns[i]: _round(float(theta[i]))
                                      for i in design.evidence_index},
            "coefficients_pinned_at_zero_by_the_nonneg_bound": pinned,
            "converged": fit["converged"], "n_iterations": fit["n_iterations"],
            "test_fold_raw_order": _p_at_k(order),
        })
    return {"status": "fitted", "head": head, "horizon": int(horizon),
            "design": design.receipt, "folds": fold_rows,
            "composition_note": ("test-fold metrics are `composition: raw`. The DEPLOYED "
                                 "composition joins the champion's stage buckets, which "
                                 "no lawful REAL fold plan has ever existed to provide "
                                 "and which a synthetic frame does not have (§8.3)."),
            "sign_law": ("evidence coefficients are bounded >= 0 after orientation: the "
                         "fit may shrink a family to 0.0, never flip it against its "
                         "filed direction on outcome data")}


def c2_vs_simpler_rung(frame: C2Frame, registry: Registry, census: Mapping[str, Any],
                       folds: Sequence[Fold], *, head: str,
                       horizon: int = PRIMARY_HORIZON) -> dict[str, Any]:
    """§8.1's complexity-ladder MACHINERY: C2 vs the C1-style equal-weight score, same folds.

    SYNTHETIC-PROOF, NOT A RESULT.  The ladder law adjudicates a REAL race; this function
    exists so that the comparison exists and is exercised, and every cell it emits is
    labelled ``synthetic_machinery_proof`` so it can never be quoted as an increment.
    """
    fitted = fit_c2_over_folds(frame, registry, census, folds, head=head, horizon=horizon)
    outcome = frame.outcome_slice(horizon)
    fam_scores, _receipt = build_family_scores(frame, census, membership="design")
    families = census_families_in_design(census)
    equal = fam_scores[["date", "ticker"]].copy()
    equal["score"] = fam_scores[families].mean(axis=1, skipna=True)
    equal = equal.merge(outcome, on=["date", "ticker"], how="left")

    rows: list[dict[str, Any]] = []
    for fold_row, fold in zip(fitted["folds"], folds):
        if fold_row.get("status") != "fitted":
            continue
        test = set(fold.test_dates)
        c1_like = _p_at_k(equal[equal["date"].isin(test)])
        c2 = fold_row["test_fold_raw_order"]
        rows.append({
            "fold": fold.index, "tier": "synthetic_machinery_proof",
            "c2_raw": c2, "c1_equal_weight_raw": c1_like,
            "delta_p_at_5": _round((_opt(c2.get(f"p_at_{PRIMARY_K}")) or 0.0)
                                   - (_opt(c1_like.get(f"p_at_{PRIMARY_K}")) or 0.0)),
        })
    return {"tier": "synthetic_machinery_proof", "head": head, "horizon": int(horizon),
            "law": ("§8.1 complexity-ladder law: a rung ships only if its INCREMENT over "
                    "the best surviving SIMPLER rung clears the CI + FDR bar (registered "
                    "minimum ΔP@5 >= +3pp, date-blocked 95% CI excluding zero). This "
                    "block proves the comparison EXISTS and runs; it adjudicates nothing."),
            "per_fold": rows}


def c2_fit_block(frame: C2Frame, registry: Registry, census: Mapping[str, Any],
                 fold_plan: Any, *, horizon: int = PRIMARY_HORIZON) -> dict[str, Any]:
    """The fit seam.  Folds FIRST; zero lawful folds -> the §9.2 refusal and NO coefficients."""
    would_have_entered = _would_have_entered(registry, census)
    if not getattr(fold_plan, "folds", None):
        refusals = [str(r.get("message")) for r in getattr(fold_plan, "refusals", [])]
        return {
            "status": "refused_no_lawful_folds",
            "law": ("§9.2 minimum-usable-fold: >= 60 train dates and >= 10 test dates "
                    "AFTER purge + embargo, else the harness REFUSES the fold and says "
                    "so — it never silently shrinks one."),
            "model_classes": list(C2_MODEL_CLASSES),
            "horizon": int(horizon),
            "n_usable_folds": 0,
            "refusal_verbatim": refusals[0] if refusals else None,
            "refusals_verbatim": refusals,
            "fold_receipt": getattr(fold_plan, "receipt", {}),
            "would_have_entered": would_have_entered,
            "no_in_sample_fallback": (
                "There is NO in-sample fallback fit in this module. fit_c2_over_folds() "
                "RAISES on an empty fold plan (FitRefusal), so a C2 coefficient cannot be "
                "produced on this frame at all — not printed-with-a-caveat, not produced. "
                "An in-sample C2 read is a different, weaker estimator and the caveat is "
                "exactly what falls off downstream."),
        }
    heads = {head: fit_c2_over_folds(frame, registry, census, fold_plan.folds,
                                     head=head, horizon=horizon)
             for head in C2_MODEL_CLASSES}
    return {"status": "fitted", "horizon": int(horizon),
            "n_usable_folds": len(fold_plan.folds),
            "fold_receipt": getattr(fold_plan, "receipt", {}),
            "would_have_entered": would_have_entered, "heads": heads}


def _would_have_entered(registry: Registry, census: Mapping[str, Any]) -> dict[str, Any]:
    """The design-matrix receipt a refused fit still owes its reader.

    A refusal that does not say WHAT it refused to fit is unfalsifiable.  This names the
    families that would have carried a column, the members feeding each, and every
    excluded member WITH its reasons — which is where `insider_cluster` appears as
    raced-in-C1 / excluded-from-the-C2-fit.
    """
    families = census_families_in_design(census)
    excluded: list[dict[str, Any]] = []
    for fam_key in sorted(census["families"]):
        for member in census["families"][fam_key]["members"]:
            if member["in_design_matrix"] or not member["columns"]:
                continue
            excluded.append({"member": member["member"], "family": fam_key,
                             "vote_column": member["vote_column"],
                             "reasons": member["reasons"],
                             "in_family_score": member["in_family_score"]})
    return {
        "families": families,
        "n_evidence_columns": len(families),
        "n_missingness_columns": len(families),
        "n_columns_total": 1 + 2 * len(families),
        "members_per_family": {f: census["families"][f]["design_matrix_members"]
                               for f in families},
        "family_budget_mechanism": FAMILY_BUDGET_MECHANISM,
        "excluded_members": excluded,
        "registry": registry.path,
    }


# --------------------------------------------------------------------------- #
# Part 5 — the governed "what does X add?" table (family grain, BH-FDR)
# --------------------------------------------------------------------------- #

#: Sub-reason -> the nearest state in the closed verdict vocabulary, in PRECEDENCE order.
#: Precedence matters: a family excluded for several reasons is reported under the most
#: STRUCTURAL one, and every other reason still rides in `reason` so nothing is swallowed.
#
# THE ORDER IS AN ARGUMENT, not a convenience.  This table's column is "what does X add
# ON THIS FRAME", so the gates that fired on the TRAINING side lead: a member that cannot
# order a cross-section, or that covers a quarter of the rows, is unanswerable here no
# matter what its serving side looks like.  The train/serve exclusion is a FORWARD
# disqualifier — it says a fitted model would find the feature dead at serving time — so
# it leads only when the training side was otherwise fine (F5.insider_panel), and rides in
# `sub_reasons` otherwise (F1, which is both below its floor and skewed).  PIT
# unlawfulness ranks above the coverage gates because a contaminated reading's coverage is
# not a fact about the evidence at all.
#
_REASON_TO_VERDICT: tuple[tuple[str, str], ...] = (
    ("structurally_excluded", "not_estimable"),
    ("not_backtest_pit", "not_pit"),
    ("vote_inert", "not_estimable"),
    ("below_presence_floor", "insufficient_coverage"),
    ("no_filed_direction", "not_estimable"),
    ("serving_dead", "excluded_train_serve_skew"),
    ("excluded_train_serve_skew", "excluded_train_serve_skew"),
    ("absent_from_frame", "insufficient_coverage"),
    ("unwired", "insufficient_coverage"),
)


def _family_block_reason(body: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Why a family carries no descriptive read, mapped onto the closed vocabulary.

    ABSENCE IS ADJUDICATED FIRST, and deliberately so.  A ``pit_status`` on a column this
    frame does not carry is a HYPOTHETICAL — F3 and F7 have forward-only / snapshot
    members, but the binding fact about them here is that the frozen board payload carries
    none of their evidence columns at all.  Reporting them as ``not_pit`` would name a
    gate they never reached and would hide the real one (§8.5 keeps "absent from this
    frame" and "unlawful for backtest" apart).  Once at least one member IS present, the
    precedence table below decides among the gates that actually fired.
    """
    wired = [m for m in body["members"] if m["columns"]]
    if not wired:
        return "insufficient_coverage", ["no_wired_member"]
    reasons = sorted({r for member in wired for r in member["reasons"] if r != "eligible"})
    # STRUCTURAL EXCLUSION OUTRANKS EVERYTHING, including absence.  §5.1 F6 is
    # row-constant per night and is therefore cross-sectionally DEGENERATE BY DESIGN —
    # true whether or not this frame happens to carry its columns.  Calling it
    # "insufficient coverage" would promise that more data fixes it; nothing does.
    if "structurally_excluded" in reasons:
        return "not_estimable", reasons
    present = [m for m in wired if m["columns_present_on_frame"]]
    if not present:
        return "insufficient_coverage", reasons or ["absent_from_frame"]
    live = sorted({r for member in present for r in member["reasons"] if r != "eligible"})
    for reason, verdict in _REASON_TO_VERDICT:
        if reason in live:
            return verdict, reasons
    return "not_estimable", reasons or ["no_wired_member"]


def what_does_x_add(census: Mapping[str, Any], descriptive: Mapping[str, Any],
                    cmi: Mapping[str, Any], crossfit_status: str,
                    power: Mapping[str, Any], *,
                    n_tests: int, alpha: float = 0.05,
                    horizon: int = PRIMARY_HORIZON) -> dict[str, Any]:
    """One row per registry family at the primary horizon, BH-FDR over the family grain.

    §9.8: the family-grain BH table is SEPARATE from the leaderboard's model x metric x
    horizon table, and it is the axis this §5.3 exhibit varies over — one test per family
    at H=10.  Secondary horizons get their own separately-bookkept tables, marked
    secondary, and never share this table's alpha.
    """
    cells = {(c["family"], c["horizon"]): c for c in descriptive["cells"]}
    cmi_cells = {(c["family"], c["horizon"]): c for c in cmi["cells"]}
    scored = census_families_in_score(census)

    pvalues: list[float] = []
    scored_at_horizon: list[str] = []
    for family in scored:
        cell = cells.get((family, horizon))
        p = None if cell is None else _opt(cell.get("p_partial"))
        if p is None:
            continue
        scored_at_horizon.append(family)
        pvalues.append(float(p))
    bh = benjamini_hochberg(pvalues, alpha=alpha) if pvalues else []
    by_family = {family: bh[i] for i, family in enumerate(scored_at_horizon)}

    rows: list[dict[str, Any]] = []
    for family in sorted(census["families"]):
        body = census["families"][family]
        cell = cells.get((family, horizon))
        cmi_cell = cmi_cells.get((family, horizon))
        power_note = _power_note(family, cell, cmi_cell, power)
        member_detail = [{
            "member": m["member"], "vote_column": m["vote_column"],
            "verdict": m["verdict"], "reasons": m["reasons"],
            "c1_raced": m["in_family_score"], "c2_fit_eligible": m["in_design_matrix"],
            "variation_share": ((m["variance_axis"].get(m["vote_column"]) or {})
                                .get("variation_share") if m["vote_column"] else None),
        } for m in body["members"] if m["columns"]]

        if family in by_family:
            verdict_row = by_family[family]
            effect = _opt((cell.get("partial_spearman_given_g0") or {}).get("mean"))
            if verdict_row["reject"] and (effect or 0.0) > 0:
                verdict, reason = "incremental_positive", "BH-FDR rejects at alpha=0.05, positive"
            elif verdict_row["reject"] and (effect or 0.0) < 0:
                verdict, reason = "incremental_negative", "BH-FDR rejects at alpha=0.05, negative"
            else:
                verdict, reason = "null_unresolved", "BH-FDR does not reject at alpha=0.05"
            rows.append({
                "family": family, "verdict": verdict, "reason": reason,
                "sub_reasons": sorted({r for m in body["members"] for r in m["reasons"]
                                       if r != "eligible"}),
                "tier": cell["tier"],
                "effect_partial_rho_given_g0": _round(effect),
                "ci95": (cell.get("partial_spearman_given_g0") or {}).get("ci95"),
                "spearman_vs_outcome": (cell.get("spearman_vs_outcome") or {}).get("mean"),
                "p": verdict_row["p"], "p_adj": verdict_row["p_adj"],
                "reject": verdict_row["reject"], "p_method": cell["p_method"],
                "n_dates": cell["n_dates_partial"], "n_rows": cell["n_rows"],
                "cmi": _cmi_summary(cmi_cell),
                "crossfit_status": crossfit_status,
                "power_note": power_note,
                "members": member_detail,
            })
            continue

        verdict, sub_reasons = _family_block_reason(body)
        rows.append({
            "family": family, "verdict": verdict,
            "reason": "; ".join(sub_reasons),
            "sub_reasons": sub_reasons,
            "tier": "census_only_no_descriptive_read",
            "effect_partial_rho_given_g0": None, "ci95": [None, None],
            "spearman_vs_outcome": None,
            "p": None, "p_adj": None, "reject": False,
            "p_method": None,
            "n_dates": (cell["n_dates_partial"] if cell else 0),
            "n_rows": (cell["n_rows"] if cell else 0),
            "cmi": _cmi_summary(cmi_cell),
            "crossfit_status": crossfit_status,
            "power_note": power_note,
            "members": member_detail,
        })

    unknown = sorted({r["verdict"] for r in rows} - set(VERDICT_VOCABULARY))
    if unknown:                                                    # pragma: no cover
        raise C2Refusal(f"verdict vocabulary breach: {unknown} — the commissioned states "
                        f"are {list(VERDICT_VOCABULARY)}")
    if len(pvalues) != int(n_tests):
        raise C2Refusal(
            f"BH bookkeeping breach: the registered n_tests is {int(n_tests)} but "
            f"{len(pvalues)} family-grain p-values were consumed. The registered count is "
            f"written BEFORE any outcome cell and is derived from the FEATURE-side census "
            f"alone; a mismatch means the table silently varied its own multiplicity.")

    return {
        "horizon": int(horizon),
        "axis": "family_grain",
        "alpha": float(alpha),
        "n_tests_registered": int(n_tests),
        "n_tests_consumed": len(pvalues),
        "n_rejections": int(sum(1 for r in rows if r["reject"])),
        "vocabulary": list(VERDICT_VOCABULARY),
        "law": ("BH-FDR across the family-grain p-values of the DESCRIPTIVE partial-rho | "
                "G0 at H=10 only (§9.8's family-grain axis). Secondary horizons carry "
                "their own separately-bookkept tables, marked secondary. Every row "
                "carries its tier and its power context — a verdict is never printed "
                "without them."),
        "rows": rows,
    }


def _cmi_summary(cell: Mapping[str, Any] | None) -> dict[str, Any]:
    if cell is None:
        return {"status": "absent"}
    if cell.get("status") != "estimated":
        return {"status": cell.get("status"), "reason": cell.get("reason"),
                "n_rows": cell.get("n_rows"), "n_dates": cell.get("n_dates")}
    return {"status": "estimated", "excess_bits": cell.get("excess_bits"),
            "observed_bits": cell.get("observed_bits"),
            "p_one_sided": cell.get("p_one_sided"), "n_dates": cell.get("n_dates")}


def _power_note(family: str, cell: Mapping[str, Any] | None,
                cmi_cell: Mapping[str, Any] | None,
                power: Mapping[str, Any]) -> str:
    n_dates = (cell or {}).get("n_dates_partial", 0)
    mde = power.get("minimum_detectable_delta_p_at_5_inherited")
    cmi_state = (cmi_cell or {}).get("status", "absent")
    return (f"{n_dates} date-blocks on the descriptive partial; CMI {cmi_state}; the "
            f"frame's measured MDE(ΔP@5) is {mde} (PR-1b §10, inherited — no rung is "
            f"raced here) and the inferential tier is REFUSED for want of a lawful fold, "
            f"so nothing in this row can be promoted.")


def secondary_horizon_tables(census: Mapping[str, Any], descriptive: Mapping[str, Any], *,
                             alpha: float = 0.05) -> dict[str, Any]:
    """The secondary horizons' own BH tables — separately bookkept, marked secondary."""
    cells = {(c["family"], c["horizon"]): c for c in descriptive["cells"]}
    out: dict[str, Any] = {}
    for horizon in SECONDARY_HORIZONS:
        families, pvalues = [], []
        for family in census_families_in_score(census):
            cell = cells.get((family, horizon))
            p = None if cell is None else _opt(cell.get("p_partial"))
            if p is None:
                continue
            families.append(family)
            pvalues.append(float(p))
        bh = benjamini_hochberg(pvalues, alpha=alpha) if pvalues else []
        out[str(horizon)] = {
            "tier": "secondary", "horizon": int(horizon), "alpha": float(alpha),
            "n_tests": len(pvalues),
            "rows": [{"family": families[i], **bh[i]} for i in range(len(bh))],
            "law": ("SEPARATELY BOOKKEPT: a secondary horizon never shares the primary "
                    "table's alpha, and no verdict in `what_does_x_add` is derived here."),
        }
    return out


# --------------------------------------------------------------------------- #
# Part 6 — power / distance to power
# --------------------------------------------------------------------------- #

def _dates_needed_for_first_lawful_fold(horizon: int, n_folds: int) -> int | None:
    """DERIVED, not asserted: the smallest date grid that yields one lawful fold.

    Searched through ``arena.build_folds`` itself over a synthetic positional grid, so the
    number cannot drift away from the fold builder's own arithmetic (purge, embargo and
    the test-size rule included).  No calendar and no wall clock enter — the answer is in
    DATES, and the sessions-per-month conversion below is labelled arithmetic.
    """
    for n in range(int(MIN_TRAIN_DATES + MIN_TEST_DATES), 600):
        grid = [f"D{i:04d}" for i in range(n)]
        plan = build_folds(grid, horizon=int(horizon), n_folds=int(n_folds), strict=False)
        if plan.folds:
            return n
    return None


def power_block(frame: C2Frame, census: Mapping[str, Any], cmi: Mapping[str, Any],
                fold_plan: Any) -> dict[str, Any]:
    """§8.7's table, re-derived for PR-2's estimators."""
    labels = frame.labels
    n_graded_dates = len(frame.dates)
    max_horizon = max(labels.horizons) if labels is not None and labels.horizons else max(HORIZONS)
    need_one_fold = _dates_needed_for_first_lawful_fold(max_horizon, 1)
    need_default = _dates_needed_for_first_lawful_fold(max_horizon, 3)
    more_needed = (None if need_one_fold is None
                   else max(0, int(need_one_fold) - n_graded_dates))

    rows_by_horizon = {}
    if labels is not None:
        grouped = labels.frame.groupby("horizon")["excess_spy"].agg(["size", "count"])
        rows_by_horizon = {str(int(h)): {"rows": int(v["size"]),
                                         "rows_with_measured_excess": int(v["count"])}
                           for h, v in grouped.to_dict("index").items()}

    cmi_power = []
    for cell in cmi["cells"]:
        cmi_power.append({
            "family": cell["family"], "horizon": cell["horizon"],
            "status": cell["status"], "n_rows": cell.get("n_rows"),
            "n_dates": cell.get("n_dates"),
            "min_rows": CMI_MIN_ROWS, "min_dates": CMI_MIN_DATES,
            "rows_short_by": max(0, CMI_MIN_ROWS - int(cell.get("n_rows") or 0)),
            "dates_short_by": max(0, CMI_MIN_DATES - int(cell.get("n_dates") or 0)),
        })

    return {
        "written_before_outcomes": True,
        "primary_tuple": PRIMARY_TUPLE,
        "primary_horizon": PRIMARY_HORIZON,
        "primary_composition": PRIMARY_COMPOSITION,
        "graded_dates_have": n_graded_dates,
        "graded_prophet_scored_dates_have": 0,
        "graded_dates_needed_for_minimum_usable_fold": MIN_TRAIN_DATES,
        "fold_arithmetic": {
            "max_horizon_in_frame": int(max_horizon),
            "embargo": int(max_horizon),
            "min_train_dates": int(MIN_TRAIN_DATES),
            "min_test_dates": int(MIN_TEST_DATES),
            "dates_needed_for_ONE_lawful_fold": need_one_fold,
            "dates_needed_for_the_default_3_fold_plan": need_default,
            "dates_have": n_graded_dates,
            "more_graded_dates_needed": more_needed,
            "derivation": ("searched through arena.build_folds itself over a synthetic "
                           "positional grid, so purge, embargo and the test-size rule are "
                           "the fold builder's own and cannot drift from this number"),
            "illustrative_conversion": (
                None if more_needed is None else
                f"{more_needed} more graded dates ÷ 21 sessions per month ≈ "
                f"{round(more_needed / 21.0, 1)} months of ARITHMETIC — not a calendar "
                f"projection, and not a promise about when the board will publish"),
        },
        "distance_to_power": [
            f"need >= {MIN_TRAIN_DATES} graded prophet-era dates (§9.2 minimum-usable-"
            f"fold) — have {n_graded_dates} graded board dates, and ZERO of them carry a "
            f"published prophet score (§6.1: the live score has never been graded, N=0)",
            (f"need {need_one_fold} distinct graded dates for the FIRST lawful fold at "
             f"embargo {int(max_horizon)} — {more_needed} more than this frame holds"),
            "need a SECOND graded PROPHET-SCORED era for §8.6.3's era-strata condition — "
            "there are zero, so that half of the gate is UNSATISFIABLE today; that is the "
            "intended reading, not a defect",
            "need H=42/63 rows for any basing-class claim — there are none",
        ],
        "rows_by_horizon": rows_by_horizon,
        "cmi_power": cmi_power,
        "minimum_detectable_delta_p_at_5_inherited": 0.174,
        "mde_note": (
            "INHERITED from PR-1b §10, not recomputed: the measured date-blocked SE of "
            "ΔP@5 on this frame was 0.049-0.089 across ten challenger-vs-anchor pairs, "
            "implying a smallest readable ΔP@5 of ~0.174 (17.4pp) against §8.1's "
            "registered +3pp minimum increment — the gate is ~6x less sensitive than the "
            "increment it adjudicates. No rung is raced in PR-2, so recomputing the band "
            "here would be inventing a number, not measuring one."),
        "n_usable_folds": len(getattr(fold_plan, "folds", []) or []),
    }


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def _safe_out_dir(out: Path | str | None) -> Path:
    """Never write inside a tracked store.  Same law as race's `_safe_out_dir`."""
    target = (Path(out) if out is not None
              else Path(tempfile.gettempdir()) / "prophet_fusion_c2")
    if not target.is_absolute():
        target = _REPO_ROOT / target
    resolved = target.resolve()
    for tracked in ("data", "site"):
        store = (_REPO_ROOT / tracked).resolve()
        if resolved == store or store in resolved.parents:
            raise C2Refusal(
                f"--out {resolved} is inside {tracked}/ — research tooling never writes a "
                f"tracked store (house law).")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def write_report(report: Mapping[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=False,
                               ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def _registered_block(floor: VarianceFloor, *, n_tests: int,
                      registry: Registry) -> dict[str, Any]:
    """Everything registered BEFORE an outcome cell is read (§8.2 / §9.8)."""
    return {
        "primary_tuple": PRIMARY_TUPLE,
        "primary_horizon": PRIMARY_HORIZON,
        "primary_k": PRIMARY_K,
        "horizons": list(HORIZONS),
        "secondary_horizons": list(SECONDARY_HORIZONS),
        "registry": registry.path,
        "seeds": {
            "bootstrap": BOOTSTRAP_SEED, "bootstrap_b": BOOTSTRAP_B,
            "cmi_permutation": CMI_PERMUTATION_SEED,
            "cmi_permutation_b": CMI_PERMUTATION_B,
            "c2_inner_split": ("NONE — the inner selection block is date-contiguous and "
                               "positional (last 20% of TRAIN dates); there is no RNG in "
                               "the C2 path at all, so a fold's coefficients are "
                               "reproducible from the fold plan alone"),
        },
        "c2_model_classes": list(C2_MODEL_CLASSES),
        "c2_penalty": (
            "evidence coefs w_f: alpha*(l1_ratio*Σw_f + ½(1−l1_ratio)*Σw_f²) with the "
            "GOVERNED-DIRECTION bound w_f >= 0; missingness coefs: ridge only "
            "(½*alpha*(1−l1_ratio)*Σm²), unbounded — epistemic, no governed direction, and "
            "keeping them out of L1 keeps the objective smooth; intercept unpenalized and "
            "unbounded. Loss is date-equal weighted NLL / MSE (§9.3)."),
        "c2_optimizer": {
            "method": "scipy.optimize.minimize L-BFGS-B, analytic gradient, zero init",
            "maxiter": C2_MAXITER, "ftol": C2_FTOL, "gtol": C2_GTOL,
            "why_smooth": ("with w >= 0 the L1 term is LINEAR on the feasible set, so the "
                           "objective is smooth there and no subgradient handling is "
                           "needed"),
        },
        "grid": {"alpha": list(C2_ALPHAS), "l1_ratio": list(C2_L1_RATIOS),
                 "size": C2_GRID_SIZE,
                 "inner_selection": ("last 20% of TRAIN dates, date-contiguous, >= 3 "
                                     "dates, embargoed from inner-train by the horizon; "
                                     "picked by inner date-equal log-loss / MSE; ties -> "
                                     "LARGEST alpha then LARGEST l1_ratio")},
        "family_budget_mechanism": FAMILY_BUDGET_MECHANISM,
        "variance_floor_spec": floor.as_dict(),
        "cmi_estimator": CMI_ESTIMATOR,
        "crossfit_spec": CROSSFIT_SPEC,
        "fdr": {"axis": "family_grain", "alpha": 0.05, "n_tests": int(n_tests),
                "derivation": ("the count of families carrying a score-eligible member "
                               "at H=10, computed from the FEATURE-side census alone — no "
                               "outcome value enters the multiplicity count"),
                "secondary_tables": ("H=5 and H=21 carry their own separately-bookkept BH "
                                     "tables, marked secondary; they never share this "
                                     "alpha")},
        "redundancy_cell_minimums": {
            "min_non_null_pairs_within_a_date": REDUNDANCY_MIN_PAIRS_PER_DATE,
            "min_counted_dates": REDUNDANCY_MIN_DATES,
            "frame1_tier": ("single_cross_section — plain rho + n, NO CI, never pooled "
                            "with a frame-2 date-blocked cell")},
        "fold_law": {"min_train_dates": MIN_TRAIN_DATES, "min_test_dates": MIN_TEST_DATES,
                     "embargo": "the longest horizon graded in the fold (§9.2)"},
    }


def _frames_block(frame: C2Frame, frame1: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    stamps = [{"stamp_date": body["stamp_date"], "tier": body["tier"],
               "file": body["file"], "n_rows": body["n_rows"]}
              for body in sorted(frame1.values(),
                                 key=lambda b: (b["stamp_date"], b["tier"]))]
    try:
        load_prophet_rank_frame()
        grades_status = "non_empty"
    except Exception as exc:                                       # noqa: BLE001
        grades_status = f"REFUSED: {exc}"
    return {
        "frame2_graded_board": {
            "name": "board_ledger",
            "source": "data/us_board_ledger/retro_grades.parquet",
            "champion_inputs": "data/us_board_ledger/snapshots.jsonl",
            "frames_never_pooled": True,
            **frame.receipt,
        },
        "frame1_candidates_store": {
            "source": CANDIDATES_DIR,
            "role": ("CENSUS + SERVING SIDE ONLY. Frame 1 has five stamped days and no "
                     "matured outcomes, so it races nothing and is never pooled with "
                     "frame 2 (registry era_boundaries.cv_universe_widening)."),
            "stamps": stamps, "n_stamps": len(stamps),
            "serving_stamp": f"{SERVE_STAMP} ({SERVE_TIER})",
            "grades_sibling_status": grades_status,
            "grades_note": ("§4.0/§8.7: the candidates store's grades/ sibling has ZERO "
                            "matured rows, so frame 1 has no outcomes to race at any "
                            "horizon today. labels.load_prophet_rank_frame() is called "
                            "here for its REFUSAL, which is the printed receipt."),
        },
    }


def run_c2(*, root: Path | str | None = None,
           registry_path: Path | str | None = None,
           snapshots_path: Path | str | None = None,
           raw: pd.DataFrame | None = None,
           frame: C2Frame | None = None,
           bootstrap_b: int = BOOTSTRAP_B,
           cmi_permutation_b: int = CMI_PERMUTATION_B) -> dict[str, Any]:
    """Build the PR-2 report.  Registered block first, outcomes after — always."""
    registry = load_registry(registry_path)
    floor = load_variance_floor(registry_path)
    flags = registry_member_flags(registry_path)
    if frame is None:
        frame = build_c2_frame(root=root, raw=raw, snapshots_path=snapshots_path)
    frame1 = frame1_slabs(root)
    serve = frame1.get(f"{SERVE_STAMP}|{SERVE_TIER}")

    census = estimability_census(frame, registry, floor, member_flags=flags,
                                 serve_slab=serve["frame"] if serve else None)
    fam_scores, score_receipt = build_family_scores(frame, census, membership="score")
    scored_families = census_families_in_score(census)
    # The FDR multiplicity is fixed HERE, from the feature-side census, before a single
    # outcome value is read — which is what makes writing it into `registered` honest.
    n_tests = len(scored_families)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "authority": {"can_rank": False, "can_size": False, "can_gate": False,
                      "can_originate_signal": False, "can_escalate": False},
        "non_promotion_bearing": True,
        "counterfactual_replay": True,
        "survivorship": dict(SURVIVORSHIP),
        "horizons_available": list(HORIZONS),
        "calibration_sentence": (
            "This is a counterfactual replay on a survivorship-flagged frame whose "
            "inferential half is REFUSED for want of a lawful fold; it is a calibration "
            "and machinery exercise and is non-promotion-bearing (§14, §15)."),
        "registered": _registered_block(floor, n_tests=n_tests, registry=registry),
        "frames": _frames_block(frame, frame1),
    }

    # --- outcomes begin here; everything above is registered ------------------------
    report["estimability_census"] = census
    report["family_scores"] = {k: v for k, v in score_receipt.items() if k != "missing"}
    report["redundancy"] = redundancy_blocks(frame, registry, census, fam_scores,
                                             frame1=frame1, bootstrap_b=bootstrap_b,
                                             registry_path=registry.path)
    cmi = cmi_block(frame, fam_scores, families=scored_families, b=cmi_permutation_b)
    report["cmi"] = cmi

    fold_plan = folds_for_labels(frame.labels, strict=False) if frame.labels is not None \
        else build_folds(frame.dates, horizon=max(HORIZONS), strict=False)
    if fold_plan.folds:
        crossfit = crossfit_incremental(frame, fam_scores, fold_plan.folds,
                                        families=scored_families,
                                        bootstrap_b=bootstrap_b)
    else:
        refusals = [str(r.get("message")) for r in fold_plan.refusals]
        crossfit = {
            "status": "refused_no_lawful_folds",
            "law": CROSSFIT_SPEC["fold_law"],
            "n_usable_folds": 0,
            "refusal_verbatim": refusals[0] if refusals else None,
            "refusals_verbatim": refusals,
            "fold_receipt": fold_plan.receipt,
            "per_family": {family: {"status": "refused_no_lawful_folds"}
                           for family in scored_families},
            "note": ("NO FOLD WAS MANUFACTURED and no in-sample substitute was computed "
                     "under this key. The descriptive tier beside it is a DIFFERENT "
                     "estimator and is labelled as one on every cell."),
        }
    descriptive = descriptive_incremental(frame, fam_scores, families=scored_families,
                                          bootstrap_b=bootstrap_b)
    report["incremental"] = {"crossfit": crossfit, "descriptive": descriptive}

    power = power_block(frame, census, cmi, fold_plan)
    report["what_does_x_add"] = what_does_x_add(
        census, descriptive, cmi, crossfit["status"], power, n_tests=n_tests)
    report["what_does_x_add_secondary_horizons"] = secondary_horizon_tables(
        census, descriptive)
    report["c2_fit"] = c2_fit_block(frame, registry, census, fold_plan)
    report["folds"] = {
        "law": ("§9.2 minimum-usable-fold: >= 60 train dates and >= 10 test dates AFTER "
                "purge + embargo, else the harness REFUSES the fold and says so — it "
                "never silently shrinks one."),
        "n_usable_folds": len(fold_plan.folds),
        "n_refused_folds": len(fold_plan.refusals),
        "refusals_verbatim": [str(r.get("message")) for r in fold_plan.refusals],
        "receipt": fold_plan.receipt,
        "folds": [f.as_dict() for f in fold_plan.folds],
    }
    report["power"] = power
    report["selftest_receipt"] = {
        "ran": False,
        "note": ("The committed report NEVER embeds selftest output: the selftest proves "
                 "the MACHINERY on synthetic depth and the report is a read of the REAL "
                 "frame. Mixing them would let a synthetic pass decorate a refused real "
                 "result. Run `python3 -m scripts.prophet_fusion_c2 --selftest`; the "
                 "suite runs it separately."),
    }
    return report


# --------------------------------------------------------------------------- #
# Part 8 — the synthetic fixture and the selftest (the machinery proof)
# --------------------------------------------------------------------------- #

SYNTHETIC_SEED = 20260818

#: The synthetic registry.  Written to a temp file and loaded THROUGH ``load_registry`` +
#: ``load_variance_floor``, so the loaders are part of what the selftest proves.  It
#: carries its own ``semantics.variance_floor_spec`` — the floor is read from the file
#: here exactly as it is read from the real registry on the real frame.
SYNTHETIC_REGISTRY: dict[str, Any] = {
    "schema": "prophet_fusion.families.v1",
    "coverage_floor": 0.50,
    "semantics": {
        "variance_floor_spec": {
            "axis": "within_date_distinct_nonnull_oriented_values",
            "min_distinct_values_per_date": 2,
            "min_dates_with_variation_share": 0.50,
            "excluded_from": ["family_vote_aggregation", "fitted_design_matrices"],
            "retained_in": ["census", "coverage_tables", "redundancy_matrices", "display"],
        },
    },
    "families": {
        "FP_PLANTED_POSITIVE": {"title": "Planted positive", "members": {
            "planted_positive": {"pit_status": "pit", "columns": ["syn_pos"],
                                 "null_semantics": "unmeasured", "coverage_probe": True},
            # A correlated SIBLING inside the same family: the within-family redundancy
            # block needs a pair to measure, and the family budget needs something to
            # refuse to spend twice.
            "planted_positive_sibling": {"pit_status": "pit", "columns": ["syn_pos_sib"],
                                         "null_semantics": "unmeasured"}}},
        "FA_ANTI_ORIENTED": {"title": "Anti-oriented", "members": {
            "anti_oriented": {"pit_status": "pit", "columns": ["syn_anti"],
                              "null_semantics": "unmeasured", "coverage_probe": True}}},
        "FN_PURE_NOISE": {"title": "Pure noise", "members": {
            "pure_noise": {"pit_status": "pit", "columns": ["syn_noise"],
                           "null_semantics": "unmeasured", "coverage_probe": True}}},
        "FI_NEAR_CONSTANT": {"title": "Near-constant flag", "members": {
            "near_constant": {"pit_status": "pit", "columns": ["syn_inert"],
                              "null_semantics": "measured_negative",
                              "coverage_probe": True}}},
        "FS_SPARSE_VARIABLE": {"title": "Sparse but variable flag", "members": {
            "sparse_variable": {"pit_status": "pit", "columns": ["syn_sparse"],
                                "null_semantics": "measured_negative",
                                "coverage_probe": True}}},
    },
    "known_redundancy_edges": [
        {"pair": ["FP_PLANTED_POSITIVE.planted_positive", "FN_PURE_NOISE.pure_noise"],
         "relation": "independent by construction", "kind": "synthetic_control",
         "source": "scripts/prophet_fusion_c2.py synthetic fixture"},
        {"pair": ["FP_PLANTED_POSITIVE.planted_positive", "FX_ABSENT.never_wired"],
         "relation": "unmeasurable by construction", "kind": "synthetic_control",
         "source": "scripts/prophet_fusion_c2.py synthetic fixture"},
    ],
}

SYNTHETIC_SIGNS: dict[str, RegisteredSign] = {
    "syn_pos": RegisteredSign(column="syn_pos", family="FP_PLANTED_POSITIVE", sign=+1,
                              kind="continuous", source="synthetic fixture: filed +"),
    # FILED POSITIVE ON PURPOSE.  The generator makes its ORIENTED score anti-correlated
    # with the outcome, so the non-negativity bound must pin its coefficient at exactly
    # 0.0 rather than letting the fit re-point a governed family on outcome data.
    "syn_pos_sib": RegisteredSign(column="syn_pos_sib", family="FP_PLANTED_POSITIVE",
                                  sign=+1, kind="continuous",
                                  source="synthetic fixture: filed +, correlated sibling"),
    "syn_anti": RegisteredSign(column="syn_anti", family="FA_ANTI_ORIENTED", sign=+1,
                               kind="continuous", source="synthetic fixture: filed +"),
    "syn_noise": RegisteredSign(column="syn_noise", family="FN_PURE_NOISE", sign=+1,
                                kind="continuous", source="synthetic fixture: filed +"),
    "syn_inert": RegisteredSign(column="syn_inert", family="FI_NEAR_CONSTANT", sign=+1,
                                kind="flag", source="synthetic fixture: filed +"),
    "syn_sparse": RegisteredSign(column="syn_sparse", family="FS_SPARSE_VARIABLE", sign=+1,
                                 kind="flag", source="synthetic fixture: filed +"),
}


def synthetic_c2_frame(*, n_dates: int = 130, n_tickers: int = 40,
                       seed: int = SYNTHETIC_SEED,
                       inert_fire_share_of_dates: float = 0.30,
                       sparse_fire_share_of_dates: float = 0.95,
                       sparse_fires_per_date: int = 2) -> C2Frame:
    """A deterministic frame deep enough to FOLD, carrying every falsifier half.

    Exists because the real frame CANNOT exercise the inferential machinery: 24 dates
    refuse every fold by design (§9.2).  Shaped so each stage of the selftest has a known
    right answer:

      * ``syn_pos``    — planted POSITIVE: its oriented score carries a real edge.
      * ``syn_pos_sib``— a CORRELATED SIBLING of ``syn_pos`` inside the same family, so
                         the within-family redundancy block has a pair and the family
                         budget has something to refuse to spend twice.
      * ``syn_anti``   — planted ANTI-oriented under a filed POSITIVE sign, so the nonneg
                         bound has something to pin at 0.0.
      * ``syn_noise``  — no edge: the crossfit CI must COVER zero.
      * ``syn_inert``  — near-constant flag: fires on ~1% of rows and carries two distinct
                         values on only 30% of dates -> VOTE-INERT (falsifier half 1).
      * ``syn_sparse`` — sparse but VARIABLE: fires on exactly 5% of rows on 95% of dates
                         -> PASSES the floor (falsifier half 2).  The 0.95 (not 1.00) is
                         deliberate: it leaves room for the registry-wiring test to move
                         the floor to 0.99 and flip this member.
    """
    rng = np.random.default_rng(int(seed))
    dates = [f"S{i:04d}" for i in range(int(n_dates))]
    tickers = [f"SYN{i:03d}" for i in range(int(n_tickers))]
    feature_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    g0_rows: list[dict[str, Any]] = []

    for date in dates:
        pos = rng.normal(0.0, 1.0, size=n_tickers)
        anti = rng.normal(0.0, 1.0, size=n_tickers)
        noise = rng.normal(0.0, 1.0, size=n_tickers)
        pos_sibling = 0.8 * pos + 0.6 * rng.normal(0.0, 1.0, size=n_tickers)
        g0_specific = rng.normal(0.0, 1.0, size=n_tickers)
        g0 = 0.5 * pos + g0_specific

        inert = np.zeros(n_tickers, dtype=bool)
        if rng.random() < float(inert_fire_share_of_dates):
            inert[rng.integers(0, n_tickers)] = True
        sparse = np.zeros(n_tickers, dtype=bool)
        if rng.random() < float(sparse_fire_share_of_dates):
            for index in rng.choice(n_tickers, size=int(sparse_fires_per_date),
                                    replace=False):
                sparse[int(index)] = True

        for i, ticker in enumerate(tickers):
            feature_rows.append({
                "date": date, "ticker": ticker,
                "syn_pos": float(pos[i]), "syn_pos_sib": float(pos_sibling[i]),
                "syn_anti": float(anti[i]),
                "syn_noise": float(noise[i]),
                "syn_inert": bool(inert[i]), "syn_sparse": bool(sparse[i]),
            })
            g0_rows.append({"date": date, "ticker": ticker, "g0_score": float(g0[i])})
            excess = (0.030 * float(pos[i]) - 0.030 * float(anti[i])
                      + 0.010 * float(g0_specific[i]) + float(rng.normal(0.0, 0.05)))
            for horizon in HORIZONS:
                outcome_rows.append({"date": date, "ticker": ticker,
                                     "horizon": int(horizon), "excess_spy": float(excess)})

    features = pd.DataFrame(feature_rows)
    outcomes = pd.DataFrame(outcome_rows)
    labels = LabelFrame(frame=outcomes.copy(),
                        receipt={"synthetic": True, "n_dates": len(dates)})
    return C2Frame(features=features, outcomes=outcomes,
                   g0=pd.DataFrame(g0_rows), signs=dict(SYNTHETIC_SIGNS), labels=labels,
                   receipt={"synthetic": True, "n_dates": len(dates),
                            "n_tickers": len(tickers), "seed": int(seed)})


def write_synthetic_registry(out_dir: Path, *,
                             overrides: Mapping[str, Any] | None = None) -> Path:
    """The synthetic registry, on disk, so ``load_registry`` is exercised end to end."""
    doc = json.loads(json.dumps(SYNTHETIC_REGISTRY))
    for key, value in (overrides or {}).items():
        doc["semantics"]["variance_floor_spec"][key] = value
    path = Path(out_dir) / "families.synthetic.yml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def _stage(name: str, ok: bool, **detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def selftest(out_dir: Path | str | None = None) -> dict[str, Any]:
    """End-to-end machinery proof on synthetic depth.  Every stage, or a non-zero exit."""
    target = _safe_out_dir(out_dir if out_dir is not None
                           else Path(tempfile.mkdtemp(prefix="prophet_fusion_c2_")))
    stages: list[dict[str, Any]] = []
    registry_path = write_synthetic_registry(target)
    registry = load_registry(registry_path)
    floor = load_variance_floor(registry_path)
    flags = registry_member_flags(registry_path)
    frame = synthetic_c2_frame()

    # 1 — census -------------------------------------------------------------------
    census = estimability_census(frame, registry, floor, member_flags=flags,
                                 serve_slab=None, serve_label="synthetic (no serve frame)")
    scored = census_families_in_score(census)
    design_families = census_families_in_design(census)
    stages.append(_stage("census", bool(scored) and bool(design_families),
                         families_scored=scored, families_in_design=design_families,
                         n_members=sum(len(b["members"]) for b in census["families"].values())))

    # 2 — the variance floor, BOTH halves of the DSC falsifier -----------------------
    def _member(family: str) -> dict[str, Any]:
        return census["families"][family]["members"][0]

    inert = _member("FI_NEAR_CONSTANT")
    sparse = _member("FS_SPARSE_VARIABLE")
    inert_share = (inert["variance_axis"].get("syn_inert") or {}).get("variation_share")
    sparse_share = (sparse["variance_axis"].get("syn_sparse") or {}).get("variation_share")
    stages.append(_stage(
        "variance_floor_near_constant_is_vote_inert",
        bool(inert["vote_inert"]) and "vote_inert" in inert["reasons"],
        variation_share=inert_share, floor=floor.min_dates_with_variation_share,
        verdict=inert["verdict"]))
    stages.append(_stage(
        "variance_floor_sparse_but_variable_passes",
        (not sparse["vote_inert"]) and sparse["in_family_score"],
        variation_share=sparse_share, floor=floor.min_dates_with_variation_share,
        verdict=sparse["verdict"]))

    fam_scores, score_receipt = build_family_scores(frame, census, membership="score")

    # 3 — redundancy blocks ----------------------------------------------------------
    redundancy = redundancy_blocks(frame, registry, census, fam_scores, frame1={},
                                   registry_path=registry_path)
    cross = redundancy["frame2_cross_family"]
    estimated_cells = sum(1 for left in cross for right in cross[left]
                          if cross[left][right].get("status") == "estimated")
    edges_unmeasurable = sum(1 for e in redundancy["known_edges"]
                             if e["measurement"]["status"] == "NOT_MEASURABLE")
    within_estimated = [c for c in redundancy["frame2_within_family"]
                        if c["status"] == "estimated"]
    stages.append(_stage(
        "redundancy_blocks",
        estimated_cells > 0 and edges_unmeasurable == 1 and len(within_estimated) == 1,
        cross_family_cells_estimated=estimated_cells,
        within_family_cells_estimated=len(within_estimated),
        within_family_rho=(within_estimated[0]["mean"] if within_estimated else None),
        known_edges=len(redundancy["known_edges"]),
        known_edges_not_measurable=edges_unmeasurable))

    # 4 — CMI is estimable at synthetic depth ----------------------------------------
    cmi = cmi_block(frame, fam_scores, families=scored, b=100)
    primary_cells = [c for c in cmi["cells"] if c["horizon"] == PRIMARY_HORIZON]
    planted_cmi = next(c for c in primary_cells if c["family"] == "FP_PLANTED_POSITIVE")
    stages.append(_stage("cmi_estimable_on_synthetic_depth",
                         all(c["status"] == "estimated" for c in primary_cells)
                         and (planted_cmi["excess_bits"] or 0.0) > 0.0,
                         planted_excess_bits=planted_cmi["excess_bits"],
                         planted_p=planted_cmi["p_one_sided"],
                         n_cells=len(primary_cells)))

    # 5 — folds exist ----------------------------------------------------------------
    plan = folds_for_labels(frame.labels, strict=False)
    stages.append(_stage("folds_exist", len(plan.folds) >= 1,
                         n_usable_folds=len(plan.folds),
                         n_refused=len(plan.refusals), receipt=plan.receipt))

    # 6 — the residualizer is FROZEN against test-fold mutation ----------------------
    fold = plan.folds[0]
    work = _residual_frame(frame, fam_scores, PRIMARY_HORIZON)
    train = work[work["date"].isin(set(fold.train_dates))]
    before = Residualizer().fit(train).fingerprint()
    mutated = frame.outcomes.copy()
    test_mask = mutated["date"].isin(set(fold.test_dates))
    mutated.loc[test_mask, "excess_spy"] = mutated.loc[test_mask, "excess_spy"] * -7.0 + 3.0
    mutated_frame = C2Frame(features=frame.features, outcomes=mutated, g0=frame.g0,
                            signs=frame.signs,
                            labels=LabelFrame(frame=mutated.copy(), receipt={}),
                            receipt=frame.receipt)
    mutated_work = _residual_frame(mutated_frame, fam_scores, PRIMARY_HORIZON)
    after = Residualizer().fit(
        mutated_work[mutated_work["date"].isin(set(fold.train_dates))]).fingerprint()
    stages.append(_stage("residualizer_frozen_against_test_fold_mutation", before == after,
                         fingerprint_before=before, fingerprint_after=after,
                         mutation="test-fold excess_spy -> -7x + 3"))

    # 7 — the crossfit recovers the planted family and covers zero for noise ---------
    crossfit = crossfit_incremental(frame, fam_scores, plan.folds, families=scored,
                                    bootstrap_b=400)
    planted = crossfit["per_family"]["FP_PLANTED_POSITIVE"]
    noise = crossfit["per_family"]["FN_PURE_NOISE"]
    planted_ok = ((planted["mean"] or 0.0) > 0.0
                  and (planted["ci95"][0] or 0.0) > 0.0)
    noise_ok = ((noise["ci95"][0] or 0.0) <= 0.0 <= (noise["ci95"][1] or 0.0))
    stages.append(_stage("crossfit_recovers_planted_and_covers_zero_for_noise",
                         planted_ok and noise_ok,
                         planted_mean=planted["mean"], planted_ci=planted["ci95"],
                         noise_mean=noise["mean"], noise_ci=noise["ci95"]))

    # 8 — the C2 fit: planted > 0, anti PINNED at 0.0, inner choice recorded ---------
    fit_stages: dict[str, Any] = {}
    fit_ok = True
    fitted_heads: dict[str, Any] = {}
    for head in C2_MODEL_CLASSES:
        fitted = fit_c2_over_folds(frame, registry, census, plan.folds, head=head)
        fitted_heads[head] = fitted
        rows = [row for row in fitted["folds"] if row.get("status") == "fitted"]
        planted_coefs = [row["evidence_coefficients"]["FP_PLANTED_POSITIVE__score"]
                         for row in rows]
        anti_coefs = [row["evidence_coefficients"]["FA_ANTI_ORIENTED__score"]
                      for row in rows]
        chosen = [row["inner_selection"]["chosen"] for row in rows]
        head_ok = (bool(rows) and all((c or 0.0) > 0.0 for c in planted_coefs)
                   and all(float(c) == 0.0 for c in anti_coefs)
                   and all(set(c) == {"alpha", "l1_ratio"} for c in chosen))
        fit_ok = fit_ok and head_ok
        fit_stages[head] = {"ok": head_ok, "planted_coefficients": planted_coefs,
                            "anti_coefficients": anti_coefs, "inner_choices": chosen,
                            "pinned": [row["coefficients_pinned_at_zero_by_the_nonneg_bound"]
                                       for row in rows]}
    stages.append(_stage("c2_fit_sign_constraint_and_grid", fit_ok, **fit_stages))

    # 9 — C2's raw P@5 on the test folds beats the noise family's -------------------
    logistic = fitted_heads["elastic_net_logistic_nonneg"]
    outcome = frame.outcome_slice(PRIMARY_HORIZON)
    noise_order = fam_scores[["date", "ticker"]].copy()
    noise_order["score"] = fam_scores["FN_PURE_NOISE"]
    noise_order = noise_order.merge(outcome, on=["date", "ticker"], how="left")
    c2_p5, noise_p5 = [], []
    for row, fold in zip(logistic["folds"], plan.folds):
        if row.get("status") != "fitted":
            continue
        c2_p5.append(_opt(row["test_fold_raw_order"][f"p_at_{PRIMARY_K}"]) or 0.0)
        noise_p5.append(_opt(_p_at_k(noise_order[noise_order["date"].isin(
            set(fold.test_dates))])[f"p_at_{PRIMARY_K}"]) or 0.0)
    stages.append(_stage("c2_raw_p_at_5_beats_the_noise_family",
                         bool(c2_p5) and float(np.mean(c2_p5)) > float(np.mean(noise_p5)),
                         c2_mean_p_at_5=_round(float(np.mean(c2_p5)) if c2_p5 else None),
                         noise_mean_p_at_5=_round(float(np.mean(noise_p5)) if noise_p5 else None),
                         composition="raw"))

    # 10 — the ladder machinery runs -------------------------------------------------
    ladder = c2_vs_simpler_rung(frame, registry, census, plan.folds,
                                head="elastic_net_logistic_nonneg")
    stages.append(_stage("complexity_ladder_comparison_runs", bool(ladder["per_fold"]),
                         n_folds_compared=len(ladder["per_fold"]),
                         tier=ladder["tier"]))

    # 11 — the report writes and reruns byte-identical --------------------------------
    first = run_c2(frame=frame, registry_path=registry_path, bootstrap_b=200,
                   cmi_permutation_b=50)
    second = run_c2(frame=synthetic_c2_frame(), registry_path=registry_path,
                    bootstrap_b=200, cmi_permutation_b=50)
    one = write_report(first, target / "run_a")
    two = write_report(second, target / "run_b")
    stages.append(_stage("report_writes_and_reruns_byte_identical",
                         one.read_bytes() == two.read_bytes(),
                         bytes=len(one.read_bytes()), out_dir=str(target)))

    return {"schema": SCHEMA, "mode": "selftest", "out_dir": str(target),
            "ok": all(s["ok"] for s in stages), "stages": stages}


def _print_selftest(doc: Mapping[str, Any]) -> None:
    print(f"prophet-fusion C2 selftest — {doc['schema']}")
    for stage in doc["stages"]:
        print(f"  [{'ok ' if stage['ok'] else 'FAIL'}] {stage['name']}")
    print(f"  out_dir: {doc['out_dir']}")
    print(f"  RESULT : {'PASS' if doc['ok'] else 'FAIL'}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR-2 C2 harness — non-promotion-bearing, counterfactual replay")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="output directory (never inside data/ or site/)")
    parser.add_argument("--root", default=None, help="repo root override (tests)")
    parser.add_argument("--registry", default=None, help="families.yml override")
    parser.add_argument("--snapshots", default=None, help="snapshots.jsonl override")
    parser.add_argument("--bootstrap-b", type=int, default=BOOTSTRAP_B)
    parser.add_argument("--cmi-permutation-b", type=int, default=CMI_PERMUTATION_B)
    parser.add_argument("--selftest", action="store_true",
                        help="synthetic end-to-end machinery proof; writes to a temp dir")
    args = parser.parse_args(argv)

    if args.selftest:
        doc = selftest()
        _print_selftest(doc)
        return 0 if doc["ok"] else 1

    out_dir = _safe_out_dir(args.out)
    report = run_c2(root=args.root, registry_path=args.registry,
                    snapshots_path=args.snapshots, bootstrap_b=args.bootstrap_b,
                    cmi_permutation_b=args.cmi_permutation_b)
    path = write_report(report, out_dir)

    census = report["estimability_census"]
    print(f"prophet-fusion C2 — {SCHEMA} (NON-PROMOTION-BEARING, counterfactual replay)")
    print(f"  frame       : frame2 ({census['n_dates']} dates, {census['n_rows']} rows)")
    spec = report["registered"]["variance_floor_spec"]
    print(f"  variance    : floor {spec['min_dates_with_variation_share']} "
          f"(read from {spec['read_from']})")
    for row in report["what_does_x_add"]["rows"]:
        print(f"    {row['family']:26} {row['verdict']:26} "
              f"effect={row['effect_partial_rho_given_g0']} n_dates={row['n_dates']}")
    print(f"  BH-FDR      : n_tests={report['what_does_x_add']['n_tests_registered']}, "
          f"rejections={report['what_does_x_add']['n_rejections']}")
    print(f"  crossfit    : {report['incremental']['crossfit']['status']}")
    print(f"  c2_fit      : {report['c2_fit']['status']}")
    print(f"  report      : {path}")
    return 0


if __name__ == "__main__":                                        # pragma: no cover
    raise SystemExit(main())
