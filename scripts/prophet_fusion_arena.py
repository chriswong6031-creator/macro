#!/usr/bin/env python3
"""Arena harness SKELETON for the Prophet US conditional-fusion program (PR-1a).

Binding spec: ``research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md`` §5.1
(evidence-family registry), §8.3 (metric surface), §8.5 (frames), §9 (validation
protocol).  ``research/prophet_fusion/ARENA_HARNESS_NOTES.md`` is the usage doc.

WHAT THIS IS.  The machinery §9 describes, with a NO-OP challenger in the slot a real
model will later occupy — folds, the PIT gate, fold-scoped normalization, coverage
accounting, date-grouped scoring, and the §8.3 metric scaffold, proven end to end.

WHAT THIS IS NOT.  There is no model here, and no result from it may be quoted.
RESEARCH TIER, ZERO AUTHORITY: read-only over committed stores, no ``data/`` writes
(every artifact goes to a caller-supplied ``--out``), no import of any ranker.  The
challenger is stamped ``dummy: true, non_promotion_bearing: true`` at the point of
production so a copied artifact carries the stamp with it.

THE FOUR REFUSALS THIS HARNESS EXISTS TO MAKE (each is a typed error, never a warning)
--------------------------------------------------------------------------------------
1. **Minimum-usable fold** (§9.2).  After purge+embargo a fold must retain >= 60
   distinct train dates and >= 10 distinct test dates.  Today's graded frame is 24
   dates, so EVERY fold on it refuses — that refusal is the acceptance behaviour, not
   a bug to route around.  The harness never silently shrinks a fold.
2. **PIT contamination** (§9.1, §4.2).  A feature whose registry member is
   ``snapshot_not_pit`` or ``forward_only`` cannot be joined into a BACKTEST frame:
   short interest and forensics are snapshot-only today, and a snapshot join writes
   today's knowledge onto a historical row.
3. **Composite ingestion** (§5.2).  ``conviction`` / ``composite_z`` / hub scores enter
   only decomposed to their legs.  ``forbidden_composites`` in the registry is the
   kill list, and the refusal names the decomposition the caller must use instead.
4. **Unregistered feature** (§5.1).  A column in no family is refused, which is what
   makes the registry the law rather than documentation: the anti-double-count budget
   (§10.6) is meaningless if a feature can enter without a family.

WHY THE NORMALIZER IS A CLASS AND NOT A FUNCTION.  §9.1b: every normalization,
percentile, winsorization or reference distribution is fit on the TRAINING FOLD ONLY
and carried forward frozen.  A function that takes a frame and returns transformed
values has nowhere to put "the parameters are frozen and came from these rows" — so
the leak (fitting on the full frame) is invisible in a diff.  Freezing the parameters
in an object makes the leak a visible field, and lets a test pin it by mutating the
test fold and asserting the parameters did not move.

Usage::

    python3 -m scripts.prophet_fusion_arena --selftest          # the end-to-end proof
    python3 -m scripts.prophet_fusion_arena --survey            # real frame, honest depth
    python3 -m scripts.prophet_fusion_arena --check-registry    # families.yml is lawful
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.prophet_fusion_labels import (  # noqa: E402
    FRAME_BOARD_LEDGER, FRAME_PROPHET_RANK, TAIL_LOSS,
    FusionRefusal, LabelFrame, assert_poolable, build_labels, outcome_summary,
)

SCHEMA = "prophet_fusion.arena.v1"

# --------------------------------------------------------------------------- #
# registry contract (§5.1) — the YAML is the law, this is its reader
# --------------------------------------------------------------------------- #

#: The sibling deliverable.  PR-1a ships the harness AND the registry, so an absent
#: file is a hard error naming the path — never a permissive empty registry, which
#: would turn refusal 4 (unregistered feature) into a no-op.
REGISTRY_PATH = "research/prophet_fusion/families.yml"
REGISTRY_SCHEMA = "prophet_fusion.families.v1"

#: §5.1 registered default; per-family overrides live in the registry.
DEFAULT_COVERAGE_FLOOR = 0.50

PIT_OK = "pit"
PIT_FORWARD_ONLY = "forward_only"
PIT_SNAPSHOT = "snapshot_not_pit"
PIT_STATUSES = (PIT_OK, PIT_FORWARD_ONLY, PIT_SNAPSHOT)

#: A backtest frame may only join ``pit`` members; a LIVE (serving) read has no future
#: to leak, so a snapshot is lawful there.  The distinction is a parameter rather than
#: a hard-coded law because the same registry serves both reads.
FRAME_KIND_BACKTEST = "backtest"
FRAME_KIND_LIVE = "live"
FRAME_KINDS = (FRAME_KIND_BACKTEST, FRAME_KIND_LIVE)

# --------------------------------------------------------------------------- #
# §9.2 minimum-usable-fold rule — REGISTERED, not tunable by a caller in a hurry
# --------------------------------------------------------------------------- #

MIN_TRAIN_DATES = 60
MIN_TEST_DATES = 10
DEFAULT_N_FOLDS = 3

NORMALIZER_METHODS = ("z", "percentile")

#: §8.3 reports P@K at these K.  P@1/3/5 are the bolded primaries there; P@10 rides
#: with the large-loser rate because the loser read is measured on the top-10.
METRIC_KS = (1, 3, 5, 10)

#: The chartered headline horizon for the momentum/other classes (§7, §8.3 primary
#: tuple).  The arena SCORES here by default; the embargo is still sized off the
#: longest horizon present in the fold, which is a different number.
DEFAULT_SCORE_HORIZON = 10


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

class RegistryRefusal(FusionRefusal):
    """``families.yml`` is absent, mis-schema'd, or self-contradictory."""


class UnregisteredFeatureRefusal(FusionRefusal):
    """A requested feature column belongs to no family (§5.1)."""

    def __init__(self, columns: Sequence[str], registry_path: str) -> None:
        self.columns = tuple(columns)
        super().__init__(
            "unregistered feature column(s) " + ", ".join(self.columns)
            + f" — every feature belongs to exactly one family in {registry_path}; "
              "an unregistered column would enter the model outside the "
              "anti-double-count budget (§5.1, §10.6)")


class ForbiddenCompositeRefusal(FusionRefusal):
    """A blended composite was requested as a feature (§5.2)."""

    def __init__(self, column: str, decompose_to: Sequence[str]) -> None:
        self.column = column
        self.decompose_to = tuple(decompose_to)
        target = ", ".join(self.decompose_to) if self.decompose_to else "its typed legs"
        super().__init__(
            f"forbidden composite {column!r} may not be ingested as a feature — "
            f"decompose to {target} (§5.2 composite-decomposition law)")


class PITRefusal(FusionRefusal):
    """A non-PIT member was requested in a backtest frame (§9.1, §4.2)."""

    def __init__(self, column: str, member: str, family: str,
                 pit_status: str, frame_kind: str) -> None:
        self.column = column
        self.member = member
        self.family = family
        self.pit_status = pit_status
        self.frame_kind = frame_kind
        super().__init__(
            f"PIT refusal: column {column!r} (member {member!r}, family {family}) is "
            f"{pit_status!r} and cannot be joined into a {frame_kind} frame — a "
            f"snapshot join writes today's knowledge onto a historical row (§9.1). "
            f"A store with no availability field is forward-accrual-only (§13), "
            f"never lag-approximated.")


class FoldRefusal(FusionRefusal):
    """§9.2 minimum-usable-fold: the fold does not survive purge+embargo."""

    def __init__(self, fold_index: int, n_train_dates: int, n_test_dates: int,
                 *, min_train: int, min_test: int, horizon: int, embargo: int,
                 n_dates: int) -> None:
        self.fold_index = fold_index
        self.n_train_dates = n_train_dates
        self.n_test_dates = n_test_dates
        self.min_train = min_train
        self.min_test = min_test
        self.horizon = horizon
        self.embargo = embargo
        self.n_dates = n_dates
        super().__init__(
            f"fold {fold_index} refused (§9.2 minimum-usable-fold): "
            f"{n_train_dates} train dates after purge+embargo (minimum {min_train}) and "
            f"{n_test_dates} test dates (minimum {min_test}), at horizon={horizon} "
            f"embargo={embargo} over {n_dates} distinct dates. The harness refuses the "
            f"fold; it never silently shrinks one.")


class NormalizerRefusal(FusionRefusal):
    """The fold-scoped normalizer was used out of order or on a degenerate fit."""


class OutputPathRefusal(FusionRefusal):
    """An ``--out`` directory that would write inside a tracked store."""


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Member:
    key: str
    family: str
    pit_status: str
    columns: tuple[str, ...]
    availability_field: str | None
    coverage_floor: float
    max_staleness_sessions: int | None


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    coverage_floor: float
    members: tuple[str, ...]


@dataclass(frozen=True)
class Registry:
    path: str
    schema: str
    families: Mapping[str, Family]
    members: Mapping[str, Member]
    columns: Mapping[str, Member]
    forbidden: Mapping[str, tuple[str, ...]]

    def family_of(self, column: str) -> str | None:
        member = self.columns.get(column)
        return member.family if member else None

    def pit_columns(self) -> tuple[str, ...]:
        return tuple(sorted(c for c, m in self.columns.items()
                            if m.pit_status == PIT_OK and c not in self.forbidden))


def _entries(node: Any, key_names: Sequence[str], what: str) -> list[tuple[str, dict]]:
    """Iterate a registry node written EITHER as a mapping OR as a list of dicts.

    Tolerance is deliberate and bounded: a sibling builder owns ``families.yml``, and
    both shapes are natural YAML for "a keyed collection".  What is NOT tolerated is a
    missing key or an unknown ``pit_status`` — those are refusals, because tolerance
    there would silently admit a member the PIT gate cannot judge.
    """
    out: list[tuple[str, dict]] = []
    if node is None:
        return out
    if isinstance(node, Mapping):
        for key, body in node.items():
            out.append((str(key), dict(body) if isinstance(body, Mapping) else {}))
        return out
    if isinstance(node, (list, tuple)):
        for item in node:
            if not isinstance(item, Mapping):
                raise RegistryRefusal(f"{what}: list entries must be mappings, got "
                                      f"{type(item).__name__}")
            body = dict(item)
            key = None
            for name in key_names:
                if body.get(name):
                    key = str(body.pop(name))
                    break
            if key is None:
                raise RegistryRefusal(f"{what}: list entry names no key "
                                      f"(expected one of {list(key_names)}): "
                                      f"{sorted(body)[:6]}")
            out.append((key, body))
        return out
    raise RegistryRefusal(f"{what}: expected a mapping or a list, got "
                          f"{type(node).__name__}")


def _as_columns(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(v) for v in value)
    raise RegistryRefusal(f"columns must be a string or a list, got {type(value).__name__}")


def _as_decompose(value: Any) -> tuple[str, ...]:
    """``decompose_to`` as display strings, from either shape the registry may use.

    Plain names (``["F2.momentum_leg"]``) and typed entries
    (``[{"input": "edge_remaining", "family": "F3_THEME_STRUCTURE"}]``) both occur —
    the second carries the family the leg must land in, which is the more useful form
    and the one the shipped registry writes.  Rendered ``family.input`` so the refusal
    message names the destination, not just the leg.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise RegistryRefusal(f"decompose_to must be a string, mapping or list, got "
                              f"{type(value).__name__}")
    out: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            leg = item.get("input") or item.get("column") or item.get("name")
            fam = item.get("family")
            out.append(f"{fam}.{leg}" if fam and leg else str(leg or fam or item))
        else:
            out.append(str(item))
    return tuple(out)


def load_registry(path: Path | str | None = None) -> Registry:
    """Read ``research/prophet_fusion/families.yml`` — the §5.1 law, machine-readable.

    HARD ERROR when absent: PR-1a ships the harness and the registry together, and a
    permissive fallback would quietly disable the unregistered-feature refusal, which
    is the one that makes the registry binding at all.
    """
    target = Path(path) if path is not None else (_REPO_ROOT / REGISTRY_PATH)
    if not target.exists():
        raise RegistryRefusal(
            f"evidence-family registry not found: {target} — PR-1a ships the harness "
            f"and {REGISTRY_PATH} together (§5.1); the harness will not run against an "
            f"absent registry because an absent registry disables the "
            f"unregistered-feature refusal entirely")
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RegistryRefusal(f"{target} is not readable YAML: {exc}") from exc
    if not isinstance(doc, Mapping):
        raise RegistryRefusal(f"{target}: top level must be a mapping, got "
                              f"{type(doc).__name__}")

    schema = str(doc.get("schema") or doc.get("schema_version") or "")
    if not schema.startswith(REGISTRY_SCHEMA):
        raise RegistryRefusal(f"{target}: schema is {schema!r}, expected "
                              f"{REGISTRY_SCHEMA!r}")

    default_floor = float(doc.get("coverage_floor", DEFAULT_COVERAGE_FLOOR))
    families: dict[str, Family] = {}
    members: dict[str, Member] = {}
    columns: dict[str, Member] = {}

    for fam_key, fam_body in _entries(doc.get("families"),
                                      ("family", "key", "id"), "families"):
        fam_floor = float(fam_body.get("coverage_floor", default_floor))
        fam_name = str(fam_body.get("name") or fam_body.get("title") or fam_key)
        fam_staleness = fam_body.get("max_staleness_sessions")
        member_keys: list[str] = []
        for mem_key, mem_body in _entries(fam_body.get("members"),
                                          ("member", "name", "key", "id"),
                                          f"families.{fam_key}.members"):
            pit_status = str(mem_body.get("pit_status") or "").strip()
            if pit_status not in PIT_STATUSES:
                raise RegistryRefusal(
                    f"{target}: member {fam_key}.{mem_key} has pit_status "
                    f"{pit_status!r}; must be one of {list(PIT_STATUSES)} — an "
                    f"unknown status cannot be judged by the PIT gate and is never "
                    f"assumed safe")
            member = Member(
                key=mem_key,
                family=fam_key,
                pit_status=pit_status,
                columns=_as_columns(mem_body.get("columns")),
                availability_field=(str(mem_body["availability_field"])
                                    if mem_body.get("availability_field") else None),
                coverage_floor=float(mem_body.get("coverage_floor", fam_floor)),
                max_staleness_sessions=(
                    int(mem_body["max_staleness_sessions"])
                    if mem_body.get("max_staleness_sessions") is not None
                    else (int(fam_staleness) if fam_staleness is not None else None)),
            )
            qualified = f"{fam_key}.{mem_key}"
            if qualified in members:
                raise RegistryRefusal(f"{target}: duplicate member {qualified}")
            members[qualified] = member
            member_keys.append(qualified)
            for column in member.columns:
                # §5.1: "every feature belongs to EXACTLY ONE family — enforced by a
                # uniqueness test over the registry, not by prose".  This is that test.
                if column in columns:
                    prior = columns[column]
                    raise RegistryRefusal(
                        f"{target}: column {column!r} is registered twice — "
                        f"{prior.family}.{prior.key} and {fam_key}.{mem_key}. §5.1: a "
                        f"dual-role column gets a single home plus, where the second "
                        f"hypothesis is wanted, an explicitly derived orthogonalized "
                        f"term registered separately — never a second membership.")
                columns[column] = member
        families[fam_key] = Family(key=fam_key, name=fam_name,
                                   coverage_floor=fam_floor,
                                   members=tuple(member_keys))

    forbidden: dict[str, tuple[str, ...]] = {}
    node = doc.get("forbidden_composites")
    if isinstance(node, (list, tuple)):
        for item in node:
            if isinstance(item, str):
                forbidden[item] = ()
            elif isinstance(item, Mapping):
                name = (item.get("composite") or item.get("column")
                        or item.get("name") or item.get("key"))
                if not name:
                    raise RegistryRefusal(f"{target}: forbidden_composites entry names "
                                          f"no column: {sorted(item)[:6]}")
                forbidden[str(name)] = _as_decompose(item.get("decompose_to"))
            else:
                raise RegistryRefusal(f"{target}: forbidden_composites entries must be "
                                      f"strings or mappings, got {type(item).__name__}")
    elif isinstance(node, Mapping):
        for name, body in node.items():
            forbidden[str(name)] = _as_decompose(
                body.get("decompose_to") if isinstance(body, Mapping) else body)
    elif node is not None:
        raise RegistryRefusal(f"{target}: forbidden_composites must be a list or a "
                              f"mapping, got {type(node).__name__}")

    if not families:
        raise RegistryRefusal(f"{target}: registry declares no families")
    return Registry(path=str(target), schema=schema, families=families,
                    members=members, columns=columns, forbidden=forbidden)


# --------------------------------------------------------------------------- #
# the PIT / contamination gate
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FeatureGate:
    columns: tuple[str, ...]
    members: tuple[str, ...]
    families: tuple[str, ...]
    frame_kind: str


def check_features(registry: Registry, columns: Iterable[str], *,
                   frame_kind: str = FRAME_KIND_BACKTEST) -> FeatureGate:
    """Admit a feature set, or refuse it by name.

    REFUSAL ORDER — forbidden composite, then unregistered, then PIT status.  The most
    specific named refusal wins: a composite that someone also registered is still
    forbidden (otherwise registering it would launder it), and an unregistered column
    has no ``pit_status`` to judge, so it cannot reach the PIT check.
    """
    if frame_kind not in FRAME_KINDS:
        raise FusionRefusal(f"unknown frame_kind {frame_kind!r}; "
                            f"known: {list(FRAME_KINDS)}")
    wanted = [str(c) for c in columns]
    for column in wanted:
        if column in registry.forbidden:
            raise ForbiddenCompositeRefusal(column, registry.forbidden[column])
    unregistered = [c for c in wanted if c not in registry.columns]
    if unregistered:
        raise UnregisteredFeatureRefusal(unregistered, registry.path)
    if frame_kind == FRAME_KIND_BACKTEST:
        for column in wanted:
            member = registry.columns[column]
            if member.pit_status != PIT_OK:
                raise PITRefusal(column, member.key, member.family,
                                 member.pit_status, frame_kind)
    members = tuple(sorted({f"{registry.columns[c].family}.{registry.columns[c].key}"
                            for c in wanted}))
    fams = tuple(sorted({registry.columns[c].family for c in wanted}))
    return FeatureGate(columns=tuple(wanted), members=members, families=fams,
                       frame_kind=frame_kind)


#: The PIT join keys, in §9.1's order.  ``board_definition`` participates when BOTH
#: sides carry it — a definition change starts a fresh series rather than shadowing
#: one, so joining across definitions would silently mix two admission rules.
JOIN_KEYS = ("date", "ticker", "board_definition")

_FEATURE_DATE_COLUMNS = ("date", "as_of", "stamp_date")


def join_features(labels: LabelFrame, feature_frame: pd.DataFrame | None,
                  registry: Registry, *, columns: Sequence[str],
                  frame_kind: str = FRAME_KIND_BACKTEST
                  ) -> tuple[pd.DataFrame, FeatureGate, dict[str, Any]]:
    """THE FEATURE-JOIN SEAM — the one place a feature can enter the arena.

    Everything the harness refuses (§5.1 unregistered, §5.2 forbidden composite, §9.1
    non-PIT) is refused HERE, before a single value is copied onto an outcome row.  The
    gate runs first and unconditionally: a refusal must be impossible to reach around
    by pre-joining, which is why ``run_arena`` never merges a feature itself.

    The join is a LEFT join from the label frame, so an unmatched outcome row keeps its
    label and reads NULL for the feature — unmeasured, never zero.  The match rate is
    reported, because a join that quietly matched 3% of rows and a join that matched
    97% produce the same-shaped frame.

    ``feature_frame=None`` means the caller already carries the columns on the label
    frame (the graded-board frame does: ``retro_grades.parquet`` is one wide table).
    The gate still runs.
    """
    gate = check_features(registry, columns, frame_kind=frame_kind)
    left = labels.frame
    if feature_frame is None:
        missing = [c for c in gate.columns if c not in left.columns]
        if missing:
            raise FusionRefusal(
                f"feature_frame=None but the label frame does not carry {missing}; "
                f"pass the frame the features live on so the join is auditable")
        return left.copy(), gate, {
            "mode": "already_on_label_frame", "join_keys": [],
            "n_label_rows": int(len(left)), "match_rate": 1.0,
            "coverage_after_join": {c: float(left[c].notna().mean())
                                    for c in gate.columns}}

    right = feature_frame.copy()
    date_col = next((c for c in _FEATURE_DATE_COLUMNS if c in right.columns), None)
    if date_col is None:
        raise FusionRefusal(
            "feature frame carries no availability/date column (looked for "
            f"{list(_FEATURE_DATE_COLUMNS)}) — §9.1 forbids derived statutory lags as "
            "join keys, so a store with no availability field is forward-accrual-only, "
            "never lag-approximated")
    right["date"] = right[date_col].astype(str).str.slice(0, 10)
    right["ticker"] = right["ticker"].astype(str)
    keys = [k for k in JOIN_KEYS if k in left.columns and k in right.columns]
    missing = [c for c in gate.columns if c not in right.columns]
    if missing:
        raise FusionRefusal(f"feature frame does not carry gated column(s): {missing}")

    right = (right[keys + list(gate.columns)]
             .drop_duplicates(subset=keys, keep="first"))   # store keep-first law
    merged = left.merge(right, on=keys, how="left", indicator=True)
    matched = int((merged["_merge"] == "both").sum())
    merged = merged.drop(columns="_merge")
    return merged, gate, {
        "mode": "pit_left_join", "join_keys": keys,
        "n_label_rows": int(len(left)), "n_feature_rows": int(len(right)),
        "n_matched": matched,
        "match_rate": round(matched / len(left), 6) if len(left) else 0.0,
        "coverage_after_join": {c: round(float(merged[c].notna().mean()), 6)
                                for c in gate.columns},
    }


# --------------------------------------------------------------------------- #
# folds (§9.2, §9.3)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Fold:
    index: int
    horizon: int
    embargo: int
    train_dates: tuple[str, ...]
    test_dates: tuple[str, ...]
    purged_dates: tuple[str, ...]
    embargoed_dates: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "horizon": self.horizon, "embargo": self.embargo,
            "n_train_dates": len(self.train_dates),
            "n_test_dates": len(self.test_dates),
            "n_purged_dates": len(self.purged_dates),
            "n_embargoed_dates": len(self.embargoed_dates),
            "train_range": [self.train_dates[0], self.train_dates[-1]] if self.train_dates else [],
            "test_range": [self.test_dates[0], self.test_dates[-1]] if self.test_dates else [],
        }


@dataclass
class FoldPlan:
    folds: list[Fold]
    refusals: list[dict[str, Any]]
    receipt: dict[str, Any] = field(default_factory=dict)


def build_folds(dates: Sequence[str], *, horizon: int,
                n_folds: int = DEFAULT_N_FOLDS,
                test_size: int | None = None,
                embargo: int | None = None,
                min_train_dates: int = MIN_TRAIN_DATES,
                min_test_dates: int = MIN_TEST_DATES,
                strict: bool = True) -> FoldPlan:
    """Date-grouped walk-forward folds with purge + embargo (§9.2, §9.3).

    THE SESSION GRID IS THE FRAME'S OWN SORTED DISTINCT DATES, and that is the
    conservative direction: the graded frame's dates are a SUBSET of trading days (the
    board does not publish every session), so moving k positions in the frame spans at
    least k trading sessions.  A purge measured in frame positions therefore removes at
    least as much history as one measured in sessions — never less.  Pass a fuller
    ``dates`` grid if a caller has one.

    PURGE vs EMBARGO, kept as separate fields because they answer different questions:
      * PURGED   — train dates whose OUTCOME WINDOW (d .. d+horizon) reaches the test
                   window.  Their labels are partly made of test-period returns.
      * EMBARGOED— the extra buffer beyond the label window when the caller asks for an
                   ``embargo`` larger than ``horizon``.  §9.2 requires embargo >= the
                   longest horizon graded in the fold, so the default equals it and
                   this band is empty; a caller who widens it sees where it went.

    ``strict=True`` raises :class:`FoldRefusal` on the first unusable fold (the §9.2
    law).  ``strict=False`` collects the refusals instead, which is what ``--survey``
    uses to report honest depth on a frame too short to fold.
    """
    grid = [str(d) for d in sorted(dict.fromkeys(dates))]
    n = len(grid)
    horizon = int(horizon)
    embargo = max(horizon, int(embargo) if embargo is not None else 0)
    n_folds = max(1, int(n_folds))

    if test_size is None:
        # The largest test block that still leaves the registered minimum train
        # history, floored at the registered minimum test size.  Chosen this way so a
        # frame that CAN be folded is folded generously, and a frame that cannot is
        # refused with the honest counts rather than shaved to fit.
        feasible = (n - min_train_dates - embargo) // n_folds
        test_size = max(min_test_dates, feasible)
    test_size = max(1, int(test_size))

    folds: list[Fold] = []
    refusals: list[dict[str, Any]] = []
    for k in range(n_folds):
        test_start = n - (n_folds - k) * test_size
        test_end = test_start + test_size
        test_dates = tuple(grid[max(test_start, 0):max(test_end, 0)])

        label_cut = test_start - horizon      # label windows reach the test window
        embargo_cut = test_start - embargo    # the wider buffer, when asked for
        train_dates = tuple(grid[:max(embargo_cut, 0)])
        purged = tuple(grid[max(label_cut, 0):max(test_start, 0)])
        embargoed = tuple(grid[max(embargo_cut, 0):max(label_cut, 0)])

        if len(train_dates) < min_train_dates or len(test_dates) < min_test_dates:
            refusal = FoldRefusal(k, len(train_dates), len(test_dates),
                                  min_train=min_train_dates, min_test=min_test_dates,
                                  horizon=horizon, embargo=embargo, n_dates=n)
            if strict:
                raise refusal
            refusals.append({
                "fold_index": k, "n_train_dates": len(train_dates),
                "n_test_dates": len(test_dates), "min_train_dates": min_train_dates,
                "min_test_dates": min_test_dates, "horizon": horizon,
                "embargo": embargo, "n_dates": n, "message": str(refusal),
            })
            continue
        folds.append(Fold(index=k, horizon=horizon, embargo=embargo,
                          train_dates=train_dates, test_dates=test_dates,
                          purged_dates=purged, embargoed_dates=embargoed))

    return FoldPlan(folds=folds, refusals=refusals, receipt={
        "n_dates": n, "date_range": [grid[0], grid[-1]] if grid else [],
        "n_folds_requested": n_folds, "n_folds_usable": len(folds),
        "n_folds_refused": len(refusals), "test_size": test_size,
        "horizon": horizon, "embargo": embargo,
        "min_train_dates": min_train_dates, "min_test_dates": min_test_dates,
        "grid_source": "frame distinct dates (subset of sessions => conservative purge)",
    })


def folds_for_labels(labels: LabelFrame, **kwargs: Any) -> FoldPlan:
    """Folds sized off the LONGEST horizon graded in the frame (§9.2).

    The embargo is not the scoring horizon: a fold containing H=21 rows must embargo
    >= 21 sessions even when the primary tuple is read at H=10, because the H=21 labels
    are the ones that straddle.
    """
    horizon = kwargs.pop("horizon", None)
    if horizon is None:
        horizon = max(labels.horizons) if labels.horizons else 0
    return build_folds(labels.dates, horizon=int(horizon), **kwargs)


# --------------------------------------------------------------------------- #
# fold-scoped normalization (§9.1b)
# --------------------------------------------------------------------------- #

@dataclass
class FoldNormalizer:
    """Fit on the train fold ONLY; carried to the test fold frozen.

    The frozen parameters are a public field, and :meth:`fingerprint` hashes them, so a
    test can prove no test-fold statistic reached the transform by mutating the test
    frame and asserting the fingerprint did not move.
    """

    method: str = "z"
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    columns: tuple[str, ...] = ()
    n_fit_rows: int = 0
    fit_dates: tuple[str, ...] = ()
    fitted: bool = False

    def fit(self, frame: pd.DataFrame, columns: Iterable[str]) -> "FoldNormalizer":
        if self.method not in NORMALIZER_METHODS:
            raise NormalizerRefusal(f"unknown method {self.method!r}; "
                                    f"known: {list(NORMALIZER_METHODS)}")
        if self.fitted:
            raise NormalizerRefusal(
                "this normalizer is already fitted — refusing to re-fit. §9.1b: the "
                "training-fold parameters are carried forward FROZEN; a re-fit is how "
                "a full-sample statistic reaches a feature.")
        cols = tuple(str(c) for c in columns)
        missing = [c for c in cols if c not in frame.columns]
        if missing:
            raise NormalizerRefusal(f"cannot fit on absent column(s): {missing}")
        params: dict[str, dict[str, Any]] = {}
        for column in cols:
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if self.method == "z":
                mean = float(values.mean()) if len(values) else 0.0
                std = float(values.std(ddof=0)) if len(values) else 0.0
                degenerate = (not np.isfinite(std)) or std == 0.0
                params[column] = {"kind": "z", "mean": mean if np.isfinite(mean) else 0.0,
                                  "std": 1.0 if degenerate else std,
                                  "n": int(len(values)), "degenerate": bool(degenerate)}
            else:
                grid = np.sort(values.to_numpy(dtype="float64")) if len(values) else np.array([])
                params[column] = {"kind": "percentile",
                                  "grid": [float(x) for x in grid],
                                  "n": int(len(grid)),
                                  "degenerate": bool(len(grid) == 0)}
        self.params = params
        self.columns = cols
        self.n_fit_rows = int(len(frame))
        self.fit_dates = tuple(sorted(frame["date"].astype(str).unique())
                               if "date" in frame.columns else ())
        self.fitted = True
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply the FROZEN parameters.  Never updates them — that is the whole point."""
        if not self.fitted:
            raise NormalizerRefusal("transform() before fit() — the transform has no "
                                    "training-fold parameters to carry")
        out = frame.copy()
        for column in self.columns:
            if column not in out.columns:
                out[f"{column}__norm"] = np.nan
                continue
            values = pd.to_numeric(out[column], errors="coerce")
            spec = self.params[column]
            if spec["kind"] == "z":
                out[f"{column}__norm"] = (values - spec["mean"]) / spec["std"]
            else:
                grid = np.asarray(spec["grid"], dtype="float64")
                if grid.size == 0:
                    out[f"{column}__norm"] = np.nan
                    continue
                raw = values.to_numpy(dtype="float64")
                ranks = np.searchsorted(grid, raw, side="right") / float(grid.size)
                ranks = np.clip(ranks, 0.0, 1.0)
                ranks[~np.isfinite(raw)] = np.nan
                out[f"{column}__norm"] = ranks
        return out

    def fingerprint(self) -> str:
        """Stable hash of the frozen parameters (the mutation receipt's anchor)."""
        blob = json.dumps({"method": self.method, "params": self.params},
                          sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        return {"method": self.method, "columns": list(self.columns),
                "n_fit_rows": self.n_fit_rows, "n_fit_dates": len(self.fit_dates),
                "fit_range": ([self.fit_dates[0], self.fit_dates[-1]]
                              if self.fit_dates else []),
                "fingerprint": self.fingerprint(),
                "params": {c: {k: v for k, v in spec.items() if k != "grid"}
                           for c, spec in self.params.items()}}


# --------------------------------------------------------------------------- #
# coverage accounting (§9.9)
# --------------------------------------------------------------------------- #

def family_coverage(frame: pd.DataFrame, registry: Registry, *,
                    split: str = "train",
                    families: Iterable[str] | None = None) -> pd.DataFrame:
    """Per-family share of NON-NULL, with the null-vs-zero law applied.

    A null is UNMEASURED, never zero (#4485 null-never-false at model scale).  A
    registered column that the frame does not carry at all is 100% unmeasured, so it
    contributes 0.0 to its family's coverage and is counted separately as
    ``n_columns_absent`` — reporting it as "excluded" would let a family score full
    coverage on the one column that happens to be present.

    A family below its registered floor is marked ``abstain`` (§9.9: abstains rather
    than imputes).  PR-1a MARKS and excludes from the dummy run; it enforces nothing
    further, because there is no model here to abstain.
    """
    keys = list(families) if families is not None else list(registry.families)
    n_rows = int(len(frame))
    rows: list[dict[str, Any]] = []
    for key in keys:
        fam = registry.families[key]
        cols = [c for m in fam.members for c in registry.members[m].columns]
        present = [c for c in cols if c in frame.columns]
        absent = [c for c in cols if c not in frame.columns]
        if not cols:
            coverage = 0.0
        elif n_rows == 0:
            coverage = 0.0
        else:
            shares = [float(frame[c].notna().mean()) for c in present]
            coverage = float(sum(shares) / len(cols))  # absent columns contribute 0.0
        rows.append({
            "family": key, "family_name": fam.name, "split": split,
            "n_rows": n_rows, "n_columns": len(cols),
            "n_columns_present": len(present), "n_columns_absent": len(absent),
            "coverage": round(coverage, 6), "coverage_floor": fam.coverage_floor,
            "abstain": bool(coverage < fam.coverage_floor),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# the dummy challenger + the §8.3 metric scaffold
# --------------------------------------------------------------------------- #

def dummy_challenger(frame: pd.DataFrame, *, feature: str | None = None) -> pd.Series:
    """A NO-OP challenger: rank by ONE pit-clean registered column, or by nothing.

    Deterministic by construction — no RNG, no fitting, no state.  When ``feature`` is
    None (or carries no measured values) the score is a constant and the ordering
    collapses to the ticker-alphabetical tiebreak :func:`score_by_date` applies.  That
    fallback is not a fancy baseline; it is a ranking with ZERO information, which is
    exactly what the harness needs in the challenger slot to prove the plumbing without
    producing a number anyone could mistake for a result.
    """
    if feature is None or feature not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[feature], errors="coerce")
    if not values.notna().any():
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return values.fillna(values.min() - 1.0)  # a null never outranks a measured value


def score_by_date(frame: pd.DataFrame, *, score_col: str = "score",
                  outcome: str = "excess_spy", ks: Sequence[int] = METRIC_KS,
                  loser_threshold: float = TAIL_LOSS) -> dict[str, Any]:
    """§8.3 metric SCAFFOLD, computed within date groups (§9.3).

    Every metric is a per-date figure averaged over dates with equal weight — a
    pooled row-level average would let a wide night outvote a narrow one, and the
    product question ("was tonight's top-5 any good?") is asked per night.

    STAMPED, NOT SILENT: §8.3 requires the primaries on the DEPLOYED COMPOSITION (the
    challenger's score substituted into the same stage-bucketing, vetoes and
    ``(stage_rank, -score, ticker)`` sort the champion uses), because a majority of
    cross-bucket raw-score comparisons contradict the published order (§6.7.1).  PR-1a
    has no composition stage, so what comes out here is the pure-score-order DIAGNOSTIC
    §8.3 explicitly demotes, and it says so in its own output.
    """
    per_date: list[dict[str, Any]] = []
    for date, slab in frame.groupby("date", sort=True):
        ordered = slab.sort_values([score_col, "ticker"],
                                   ascending=[False, True], kind="mergesort")
        row: dict[str, Any] = {"date": str(date), "n_candidates": int(len(ordered))}
        for k in ks:
            top = ordered.head(int(k))
            measured = pd.to_numeric(top[outcome], errors="coerce").dropna()
            row[f"p_at_{k}"] = float((measured > 0).mean()) if len(measured) else np.nan
            row[f"top_{k}_mean_excess"] = float(measured.mean()) if len(measured) else np.nan
            row[f"top_{k}_median_excess"] = float(measured.median()) if len(measured) else np.nan
            row[f"top_{k}_n_measured"] = int(len(measured))
        top10 = pd.to_numeric(ordered.head(10)[outcome], errors="coerce").dropna()
        row["large_loser_rate_top10"] = (float((top10 < loser_threshold).mean())
                                         if len(top10) else np.nan)
        per_date.append(row)

    table = pd.DataFrame(per_date)
    aggregate: dict[str, Any] = {}
    if not table.empty:
        for column in table.columns:
            if column in ("date",) or column.endswith("_n_measured"):
                continue
            series = pd.to_numeric(table[column], errors="coerce").dropna()
            aggregate[column] = float(series.mean()) if len(series) else None
    return {
        "dummy": True,
        "non_promotion_bearing": True,
        "composition": "raw_score_order",
        "deployed_composition": False,
        "composition_note": (
            "§8.3 primaries must be measured on the deployed composition (stage "
            "buckets + vetoes + (stage_rank, -score, ticker)); PR-1a has no "
            "composition stage, so these are the pure-score-order diagnostics §8.3 "
            "demotes. Not comparable to any published primary."),
        "outcome": outcome,
        "loser_threshold": loser_threshold,
        "n_dates": int(len(table)),
        "n_rows": int(len(frame)),
        "aggregate": aggregate,
        "per_date": per_date,
    }


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def _safe_out_dir(out: Path | str | None) -> Path:
    """Resolve ``--out``, refusing anything inside a tracked store.

    House law: research tooling never writes ``data/`` or ``site/``.  The default is
    the system scratch dir, not a repo path, so a caller who forgets ``--out`` cannot
    dirty the tree.
    """
    target = (Path(out) if out is not None
              else Path(tempfile.gettempdir()) / "prophet_fusion_arena")
    target = target.expanduser().resolve()
    for tracked in ("data", "site"):
        root = (_REPO_ROOT / tracked).resolve()
        if target == root or root in target.parents:
            raise OutputPathRefusal(
                f"--out {target} is inside the tracked {tracked}/ tree; this harness is "
                f"research tier and never writes a tracked store")
    target.mkdir(parents=True, exist_ok=True)
    return target


def run_arena(labels: LabelFrame, registry: Registry, *,
              features: Sequence[str],
              feature_frame: pd.DataFrame | None = None,
              score_horizon: int = DEFAULT_SCORE_HORIZON,
              n_folds: int = DEFAULT_N_FOLDS,
              embargo: int | None = None,
              normalizer_method: str = "z",
              allow_price_basis_pool: bool = False,
              frame_kind: str = FRAME_KIND_BACKTEST,
              out_dir: Path | str | None = None) -> dict[str, Any]:
    """Labels -> pooling law -> PIT gate -> folds -> normalize -> coverage -> score.

    Returns the receipt.  Raises the typed refusal of whichever stage refuses; a
    refusal is the harness working, not the harness failing.
    """
    pooling = assert_poolable(labels, allow_price_basis_pool=allow_price_basis_pool)
    frame, gate, join = join_features(labels, feature_frame, registry,
                                      columns=features, frame_kind=frame_kind)

    plan = folds_for_labels(labels, n_folds=n_folds, embargo=embargo, strict=True)
    scored = frame[frame["horizon"] == int(score_horizon)]
    if scored.empty:
        raise FusionRefusal(
            f"no rows at score_horizon={score_horizon}; frame carries "
            f"{labels.horizons} — the chartered headline horizon is not optional "
            f"(§7 chartered-horizon prereg)")

    fold_reports: list[dict[str, Any]] = []
    for fold in plan.folds:
        train = frame[frame["date"].isin(fold.train_dates)]
        test = scored[scored["date"].isin(fold.test_dates)]

        coverage = pd.concat([family_coverage(train, registry, split="train"),
                              family_coverage(test, registry, split="test")],
                             ignore_index=True)
        abstaining = sorted(coverage.loc[coverage["split"].eq("train")
                                         & coverage["abstain"], "family"].tolist())
        # §9.9: a family below floor abstains rather than imputes.  PR-1a has no model
        # to abstain, so the mechanical consequence here is that its columns are not
        # offered to the dummy — marked AND excluded, never silently carried.
        usable = [c for c in gate.columns
                  if registry.family_of(c) not in set(abstaining)]

        normalizer = FoldNormalizer(method=normalizer_method).fit(train, usable)
        test_normed = normalizer.transform(test)

        feature = f"{usable[0]}__norm" if usable else None
        test_normed = test_normed.assign(score=dummy_challenger(test_normed,
                                                                feature=feature))
        metrics = score_by_date(test_normed)

        fold_reports.append({
            **fold.as_dict(),
            "features_requested": list(gate.columns),
            "features_used": usable,
            "features_dropped_for_abstention": [c for c in gate.columns
                                                if c not in usable],
            "abstaining_families": abstaining,
            "coverage": coverage.to_dict(orient="records"),
            "normalizer": normalizer.as_dict(),
            "challenger": {"kind": "dummy", "ranked_by": feature or "constant",
                           "tiebreak": "ticker ascending"},
            "metrics": metrics,
        })

    across = {}
    if fold_reports:
        keys = sorted({k for r in fold_reports for k in r["metrics"]["aggregate"]})
        for key in keys:
            vals = [r["metrics"]["aggregate"].get(key) for r in fold_reports]
            vals = [v for v in vals if v is not None and np.isfinite(v)]
            across[key] = float(np.mean(vals)) if vals else None

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "dummy": True,
        "non_promotion_bearing": True,
        "registry": {"path": registry.path, "schema": registry.schema,
                     "n_families": len(registry.families),
                     "n_members": len(registry.members),
                     "n_columns": len(registry.columns),
                     "n_forbidden_composites": len(registry.forbidden)},
        "labels": labels.receipt,
        "pooling": pooling,
        "feature_gate": {"frame_kind": gate.frame_kind, "columns": list(gate.columns),
                         "members": list(gate.members), "families": list(gate.families)},
        "feature_join": join,
        "folds": plan.receipt,
        "score_horizon": int(score_horizon),
        "normalizer_method": normalizer_method,
        "fold_reports": fold_reports,
        "across_folds": across,
        "survivorship_biased": labels.receipt.get("survivorship_biased"),
        "exploratory": labels.receipt.get("exploratory"),
    }
    if out_dir is not None:
        target = _safe_out_dir(out_dir)
        (target / "arena_receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        rows = [dict(row, fold=r["index"])
                for r in fold_reports for row in r["coverage"]]
        if rows:
            pd.DataFrame(rows).to_csv(target / "coverage.csv", index=False)
        receipt["out_dir"] = str(target)
    return receipt


# --------------------------------------------------------------------------- #
# synthetic fixture + the end-to-end selftest
# --------------------------------------------------------------------------- #

SYNTHETIC_SEED = 20260814

#: The synthetic registry the selftest writes and then loads THROUGH
#: :func:`load_registry` — the loader is part of what is being proven, so the fixture
#: goes through the file, never straight into the dataclasses.
SYNTHETIC_REGISTRY: dict[str, Any] = {
    "schema": REGISTRY_SCHEMA,
    "coverage_floor": DEFAULT_COVERAGE_FLOOR,
    "families": {
        "F2": {"name": "MOMENTUM-EXTENSION", "members": {
            "syn_momentum_leg": {"pit_status": PIT_OK, "columns": ["syn_momentum"],
                                 "availability_field": "date",
                                 "max_staleness_sessions": 1}}},
        "F3": {"name": "THEME-STRUCTURE", "members": {
            "syn_theme": {"pit_status": PIT_OK, "columns": ["syn_theme_heat"],
                          "availability_field": "date",
                          "max_staleness_sessions": 3}}},
        "F5": {"name": "FLOW-POSITIONING", "members": {
            "syn_short_interest": {"pit_status": PIT_SNAPSHOT,
                                   "columns": ["syn_short_interest"],
                                   "max_staleness_sessions": 10}}},
        "F7": {"name": "QUALITY-FUNDAMENTAL", "coverage_floor": 0.50, "members": {
            "syn_forensics": {"pit_status": PIT_FORWARD_ONLY,
                              "columns": ["syn_forensic"],
                              "max_staleness_sessions": 63}}},
        # PIT-clean but THIN: exists so the selftest exercises the coverage-floor
        # abstention path, which the non-PIT families never reach (the PIT gate
        # refuses them first, so a below-floor forward_only member would prove
        # nothing about §9.9).
        "F8": {"name": "ATTENTION-CROWDING", "coverage_floor": 0.50, "members": {
            "syn_attention": {"pit_status": PIT_OK, "columns": ["syn_attention"],
                              "availability_field": "date",
                              "max_staleness_sessions": 1}}},
    },
    "forbidden_composites": [
        {"column": "syn_conviction",
         "decompose_to": ["F2.syn_momentum_leg", "F3.syn_theme"]},
    ],
}


def synthetic_frame(*, n_dates: int = 150, n_tickers: int = 40,
                    horizons: Sequence[int] = (10, 21),
                    end: str = "2026-08-14",
                    seed: int = SYNTHETIC_SEED,
                    price_bases: Sequence[str] = ("adjusted",)) -> pd.DataFrame:
    """A deterministic graded-store-shaped frame deep enough to FOLD.

    Exists because the real frame cannot exercise the harness: 24 dates refuses every
    fold by design (§9.2), so an end-to-end proof needs synthetic depth.  The date grid
    ends 2026-08-14 and therefore SPANS the disclosed null era 2026-08-03..08-06, so
    the era exclusion is exercised by the selftest rather than only by a unit test.

    ``syn_momentum`` carries a small real edge into ``excess_spy`` so the dummy's
    metrics are non-degenerate; that edge is a property of the fixture, not a finding.
    """
    rng = np.random.default_rng(seed)
    dates = [d.strftime("%Y-%m-%d")
             for d in pd.bdate_range(end=end, periods=int(n_dates))]
    tickers = [f"SYN{i:03d}" for i in range(int(n_tickers))]
    rows: list[dict[str, Any]] = []
    for date in dates:
        momentum = rng.normal(0.0, 1.0, size=len(tickers))
        theme = rng.uniform(0.0, 1.0, size=len(tickers))
        theme[rng.random(len(tickers)) < 0.20] = np.nan          # honest partial coverage
        short_int = rng.normal(0.0, 1.0, size=len(tickers))
        forensic = rng.normal(0.0, 1.0, size=len(tickers))
        forensic[rng.random(len(tickers)) < 0.85] = np.nan
        attention = rng.normal(0.0, 1.0, size=len(tickers))
        attention[rng.random(len(tickers)) < 0.85] = np.nan      # below the 0.50 floor
        conviction = rng.normal(0.0, 1.0, size=len(tickers))
        for i, ticker in enumerate(tickers):
            for horizon in horizons:
                noise = rng.normal(0.0, 0.06)
                excess = 0.02 * momentum[i] + noise
                rows.append({
                    "as_of": date, "ticker": ticker, "horizon": int(horizon),
                    "excess_spy": float(excess),
                    "fwd_mfe": float(abs(excess) + abs(rng.normal(0.0, 0.03))),
                    "fwd_mdd": float(-abs(rng.normal(0.0, 0.04))),
                    "syn_momentum": float(momentum[i]),
                    "syn_theme_heat": float(theme[i]),
                    "syn_short_interest": float(short_int[i]),
                    "syn_forensic": float(forensic[i]),
                    "syn_attention": float(attention[i]),
                    "syn_conviction": float(conviction[i]),
                    "syn_unregistered": float(rng.normal()),
                    "price_basis": price_bases[i % len(price_bases)],
                    "rank_by": "confluence",
                    "board_definition": "syn_board_v1",
                    "universe_tier": "curated",
                })
    return pd.DataFrame(rows)


def write_synthetic_registry(out_dir: Path) -> Path:
    path = Path(out_dir) / "families.synthetic.yml"
    path.write_text(yaml.safe_dump(SYNTHETIC_REGISTRY, sort_keys=False),
                    encoding="utf-8")
    return path


def _stage(name: str, ok: bool, **detail: Any) -> dict[str, Any]:
    return {"stage": name, "ok": bool(ok), **detail}


def selftest(out_dir: Path | str | None = None) -> dict[str, Any]:
    """The end-to-end proof: every stage runs, every refusal fires, exit 0 or nothing.

    Deliberately self-contained on a SYNTHETIC registry: the real
    ``research/prophet_fusion/families.yml`` is a sibling builder's deliverable in the
    same PR, so binding this proof to its contents would make my harness's verdict
    depend on their file's timing.  The real registry's status is REPORTED (loaded /
    absent / unlawful) in the receipt regardless, so the gap is never invisible.
    """
    target = _safe_out_dir(out_dir)
    stages: list[dict[str, Any]] = []
    refusals: list[str] = []

    # 1 — fixture
    raw = synthetic_frame()
    stages.append(_stage("fixture", len(raw) > 0, n_rows=int(len(raw)),
                         n_dates=int(raw["as_of"].nunique()),
                         n_tickers=int(raw["ticker"].nunique()),
                         horizons=sorted(int(h) for h in raw["horizon"].unique())))

    # 2 — registry (written, then read back THROUGH the loader)
    reg_path = write_synthetic_registry(target)
    registry = load_registry(reg_path)
    stages.append(_stage("registry", len(registry.families) == 5,
                         path=str(reg_path), n_families=len(registry.families),
                         n_columns=len(registry.columns),
                         n_forbidden=len(registry.forbidden),
                         pit_clean_columns=list(registry.pit_columns())))

    # 3 — labels (era exclusion exercised: the grid spans 2026-08-03..08-06)
    labels = build_labels(raw, frame_name=FRAME_BOARD_LEDGER)
    era = labels.receipt["era_hygiene"]
    stages.append(_stage("labels", era["rows_excluded"] > 0,
                         rows_out=labels.receipt["rows_out"],
                         n_dates=labels.receipt["n_dates"],
                         era_rows_excluded=era["rows_excluded"],
                         era_dates_excluded=era["dates_excluded"],
                         era_source=Path(str(era["source"])).name,
                         deferred_heads=labels.receipt["deferred_heads"]))

    # 4 — the pooling law (§9.4), on a deliberately two-era variant
    two_era = build_labels(synthetic_frame(price_bases=("adjusted", "unadjusted")),
                           frame_name=FRAME_BOARD_LEDGER)
    pooled_ok = False
    try:
        assert_poolable(two_era)
    except FusionRefusal as exc:
        pooled_ok = True
        refusals.append(f"PriceBasisPoolRefusal: {exc}")
    stages.append(_stage("pooling_refusal", pooled_ok,
                         note="two price_basis eras refuse to pool without the flag"))

    # 5 — the three contamination refusals
    fired: dict[str, str] = {}
    for label, columns, expected in (
        ("snapshot_not_pit", ["syn_short_interest"], PITRefusal),
        ("forward_only", ["syn_forensic"], PITRefusal),
        ("forbidden_composite", ["syn_conviction"], ForbiddenCompositeRefusal),
        ("unregistered", ["syn_unregistered"], UnregisteredFeatureRefusal),
    ):
        try:
            check_features(registry, columns, frame_kind=FRAME_KIND_BACKTEST)
        except expected as exc:  # noqa: PERF203 — four explicit probes, not a loop body
            fired[label] = type(exc).__name__
            refusals.append(f"{type(exc).__name__}: {exc}")
    # a snapshot member IS lawful in a live frame — the gate is frame-kind aware
    live_ok = bool(check_features(registry, ["syn_short_interest"],
                                  frame_kind=FRAME_KIND_LIVE).columns)
    stages.append(_stage("pit_gate", len(fired) == 4 and live_ok,
                         fired=fired, live_frame_admits_snapshot=live_ok))

    # 6 — the §9.2 refusal on the REAL frame's depth (24 dates -> every fold refuses)
    short_plan = build_folds([f"2026-06-{d:02d}" for d in range(1, 25)],
                             horizon=21, strict=False)
    stages.append(_stage("fold_refusal_on_real_depth",
                         short_plan.receipt["n_folds_usable"] == 0
                         and short_plan.receipt["n_folds_refused"] == DEFAULT_N_FOLDS,
                         **short_plan.receipt,
                         first_refusal=(short_plan.refusals[0]["message"]
                                        if short_plan.refusals else None)))

    # 7-11 — the full path on the synthetic frame.  ``syn_attention`` is requested
    # deliberately: it is PIT-clean (so it passes the gate) and below its coverage
    # floor (so §9.9 must mark F8 abstaining and drop it before the dummy ranks).
    receipt = run_arena(labels, registry,
                        features=["syn_momentum", "syn_theme_heat", "syn_attention"],
                        feature_frame=raw, out_dir=target)
    folds = receipt["fold_reports"]
    stages.append(_stage("folds", len(folds) == DEFAULT_N_FOLDS,
                         **receipt["folds"]))
    stages.append(_stage("normalizer",
                         all(f["normalizer"]["n_fit_dates"] == f["n_train_dates"]
                             for f in folds),
                         fingerprints=[f["normalizer"]["fingerprint"] for f in folds],
                         method=receipt["normalizer_method"]))
    # §9.9 abstention must have MARKED F8 and DROPPED its column from the dummy run —
    # a coverage table that merely exists proves nothing.
    stages.append(_stage("coverage",
                         all("F8" in f["abstaining_families"]
                             and "syn_attention" in f["features_dropped_for_abstention"]
                             for f in folds),
                         abstaining_by_fold=[f["abstaining_families"] for f in folds],
                         dropped_for_abstention=[f["features_dropped_for_abstention"]
                                                 for f in folds],
                         train_coverage=[{r["family"]: r["coverage"]
                                          for r in f["coverage"]
                                          if r["split"] == "train"} for f in folds][:1]))
    stages.append(_stage("challenger",
                         all(f["challenger"]["ranked_by"] != "constant" for f in folds),
                         ranked_by=[f["challenger"]["ranked_by"] for f in folds]))
    stages.append(_stage("metrics",
                         all(f["metrics"]["n_dates"] == f["n_test_dates"] for f in folds),
                         dummy=receipt["dummy"],
                         non_promotion_bearing=receipt["non_promotion_bearing"],
                         composition=folds[0]["metrics"]["composition"],
                         across_folds={k: (round(v, 6) if v is not None else None)
                                       for k, v in receipt["across_folds"].items()
                                       if k.startswith("p_at_")
                                       or k.startswith("top_5_")
                                       or k == "large_loser_rate_top10"}))

    # the real registry's status, reported either way
    try:
        real = load_registry()
        real_status = {"status": "loaded", "path": real.path,
                       "n_families": len(real.families),
                       "n_columns": len(real.columns)}
    except RegistryRefusal as exc:
        real_status = {"status": "absent_or_unlawful", "detail": str(exc)[:240]}

    ok = all(s["ok"] for s in stages)
    return {
        "schema": SCHEMA, "selftest": True, "ok": ok,
        "out_dir": str(target),
        "stages": stages,
        "refusals_exercised": refusals,
        "real_registry": real_status,
        "outcome_summary": outcome_summary(labels),
    }


def _print_selftest(doc: Mapping[str, Any]) -> None:
    print(f"=== prophet_fusion_arena --selftest  [{SCHEMA}] ===", flush=True)
    print(f"out_dir: {doc['out_dir']}", flush=True)
    for stage in doc["stages"]:
        mark = "PASS" if stage["ok"] else "FAIL"
        detail = {k: v for k, v in stage.items() if k not in ("stage", "ok")}
        print(f"  [{mark}] {stage['stage']}: "
              + json.dumps(detail, default=str, sort_keys=True)[:420], flush=True)
    print(f"  refusals exercised: {len(doc['refusals_exercised'])}", flush=True)
    for line in doc["refusals_exercised"]:
        print(f"    - {line[:200]}", flush=True)
    print(f"  real registry ({REGISTRY_PATH}): {doc['real_registry']['status']}",
          flush=True)
    print(f"RESULT: {'ok' if doc['ok'] else 'FAILED'} "
          f"(dummy challenger; non-promotion-bearing)", flush=True)


def _survey(frame_name: str, root: str | None, horizon: int | None) -> dict[str, Any]:
    """Honest-depth report on a REAL frame: what the harness can and cannot fold."""
    labels = build_labels(frame_name=frame_name, root=root)
    longest = max(labels.horizons) if labels.horizons else 0
    plan = folds_for_labels(labels, horizon=(horizon or longest), strict=False)
    return {
        "schema": SCHEMA, "survey": True, "frame": frame_name,
        "labels": labels.receipt, "folds": plan.receipt,
        "fold_refusals": plan.refusals,
        "summary": outcome_summary(labels),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run the full synthetic end-to-end proof")
    parser.add_argument("--survey", action="store_true",
                        help="report honest fold depth on a real frame")
    parser.add_argument("--check-registry", action="store_true",
                        help="load research/prophet_fusion/families.yml and report it")
    parser.add_argument("--frame", default=FRAME_BOARD_LEDGER,
                        choices=[FRAME_BOARD_LEDGER, FRAME_PROPHET_RANK])
    parser.add_argument("--horizon", type=int, default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--out", default=None,
                        help="artifact directory (default: system scratch dir)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not (args.selftest or args.survey or args.check_registry):
        parser.error("choose one of --selftest / --survey / --check-registry")

    try:
        if args.check_registry:
            registry = load_registry()
            doc = {"schema": SCHEMA, "registry": registry.path,
                   "registry_schema": registry.schema,
                   "n_families": len(registry.families),
                   "n_members": len(registry.members),
                   "n_columns": len(registry.columns),
                   "pit_clean_columns": list(registry.pit_columns()),
                   "forbidden_composites": sorted(registry.forbidden)}
            print(json.dumps(doc, indent=2) if args.json
                  else f"registry ok: {registry.path} families={len(registry.families)} "
                       f"members={len(registry.members)} columns={len(registry.columns)} "
                       f"forbidden={len(registry.forbidden)}", flush=True)
            return 0
        if args.survey:
            doc = _survey(args.frame, args.root, args.horizon)
            if args.json:
                print(json.dumps(doc, indent=2, default=str), flush=True)
            else:
                lab, fol = doc["labels"], doc["folds"]
                print(f"survey frame={doc['frame']} rows={lab['rows_out']} "
                      f"dates={lab['n_dates']} horizons={lab['horizons']} "
                      f"folds_usable={fol['n_folds_usable']} "
                      f"folds_refused={fol['n_folds_refused']} "
                      f"(embargo={fol['embargo']}, min_train={fol['min_train_dates']})",
                      flush=True)
                for refusal in doc["fold_refusals"]:
                    print(f"  REFUSED {refusal['message']}", flush=True)
            return 0
        doc = selftest(args.out)
        if args.json:
            print(json.dumps(doc, indent=2, default=str), flush=True)
        else:
            _print_selftest(doc)
        return 0 if doc["ok"] else 1
    except FusionRefusal as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", flush=True)
        return 2


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
