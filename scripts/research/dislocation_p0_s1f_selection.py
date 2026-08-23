#!/usr/bin/env python3
"""Deterministic, source-blind exact-70 selection for Dislocation P0-S1F.

This is deliberately an offline pure function.  It consumes the already frozen
complete candidate universe and no semantic, price, market, outcome, or model
fields.  The 70 selected filing identities are *packets for review*, never
economic episodes or signals.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from scripts.research.dislocation_p0_a1_lib import (
    PRIMARY_FAMILIES,
    base_form,
    canonical_accession,
    canonical_cik,
    canonical_json,
    era_for_filed_on,
    is_amendment,
    is_design_excluded,
    selection_key,
)

STRATA = tuple(PRIMARY_FAMILIES) + (
    "STRUCTURAL_IMPAIRMENT_CONTROL",
    "RESOLVED_BEFORE_DISCLOSURE_CONTROL",
)
ERAS = ("modern", "development")
FORMS = ("8-K", "6-K")
AUTHORITY = {"can_rank": False, "can_gate": False, "can_size": False,
             "can_originate_signal": False, "can_escalate": False}
FORBIDDEN_SELECTION_KEYS = frozenset({
    "semantic", "proposal", "audit", "episode", "price", "market", "outcome",
    "return", "score", "rank", "sizing", "trade", "control_match",
})


class SelectionBlocked(RuntimeError):
    """The frozen source-only allocation cannot lawfully be constructed."""


def _digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _identity(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["cik"]), str(row["accession"])


def _slot(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row["stratum"]), str(row["era"]), str(row["form"])


def _has_forbidden(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            next_path = f"{path}.{key}".strip(".")
            if str(key).lower() in FORBIDDEN_SELECTION_KEYS:
                return next_path
            found = _has_forbidden(child, next_path)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _has_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def validate_candidates(rows: Iterable[Mapping[str, Any]], *, strata: Sequence[str] = STRATA,
                        design_ciks: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Normalize and validate frozen candidate rows without reading their bytes.

    A filing can carry all of its FTS query edges, but can occupy only one
    selected identity.  The retrieval stratum is provenance, not a semantic
    classification.
    """
    expected_strata = tuple(strata)
    if len(expected_strata) != 7 or len(set(expected_strata)) != 7:
        raise SelectionBlocked("S1F requires exactly seven distinct frozen strata")
    forbidden_ciks = {canonical_cik(value) for value in design_ciks}
    forbidden_ciks.discard(None)
    normal: list[dict[str, Any]] = []
    seen_identity_edges: dict[tuple[str, str, str], set[str]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise SelectionBlocked("candidate row is not an object")
        if forbidden := _has_forbidden(raw):
            raise SelectionBlocked(f"selection input contains forbidden field: {forbidden}")
        cik, accession = canonical_cik(raw.get("cik")), canonical_accession(raw.get("accession"))
        form = base_form(str(raw.get("form") or raw.get("base_form") or ""))
        filed_on = raw.get("filed_on")
        era = era_for_filed_on(str(filed_on) if filed_on is not None else None)
        stratum = str(raw.get("stratum") or raw.get("family") or "")
        if not cik or not accession or form not in FORMS or era not in ERAS or stratum not in expected_strata:
            raise SelectionBlocked("candidate lacks frozen CIK/accession/stratum/era/base-form identity")
        if is_amendment(str(raw.get("form") or "")):
            continue
        if cik in forbidden_ciks or is_design_excluded(ticker=raw.get("ticker"), cik=cik, display_name=raw.get("display_name")):
            continue
        expected_key = selection_key(family=stratum, era=era, base=form, cik=cik, accession=accession)
        if str(raw.get("selection_key") or "") != expected_key:
            raise SelectionBlocked("candidate selection_key does not reproduce from frozen fields")
        edges = raw.get("query_edges")
        if not isinstance(edges, list) or not edges:
            raise SelectionBlocked("candidate lacks frozen query provenance edges")
        edge_bytes = {canonical_json(edge) for edge in edges if isinstance(edge, Mapping)}
        if len(edge_bytes) != len(edges):
            raise SelectionBlocked("candidate has non-object query edge")
        candidate = {"stratum": stratum, "era": era, "form": form, "cik": cik,
                     "accession": accession, "selection_key": expected_key,
                     "filed_on": str(filed_on), "query_edges": [json.loads(edge) for edge in sorted(edge_bytes)]}
        for optional in ("filename", "display_name", "ticker", "hit_id", "items", "base_form"):
            if optional in raw:
                candidate[optional] = raw[optional]
        identity_key = (cik, accession, stratum)
        prior = seen_identity_edges.setdefault(identity_key, set())
        prior.update(edge_bytes)
        normal.append(candidate)
    # Merge duplicate representations of the same identity/stratum while retaining all query edges.
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in normal:
        key = (row["cik"], row["accession"], row["stratum"])
        if key not in merged:
            merged[key] = dict(row)
        else:
            combined = {canonical_json(edge) for edge in merged[key]["query_edges"]}
            combined.update(canonical_json(edge) for edge in row["query_edges"])
            merged[key]["query_edges"] = [json.loads(edge) for edge in sorted(combined)]
    return sorted(merged.values(), key=lambda row: str(row["selection_key"]))


def _local_plan(stratum: str, x: int) -> dict[tuple[str, str, str], int]:
    """One lawful 7-modern/7-8-K joint table for a ten-packet stratum."""
    if x not in range(4, 8):
        raise SelectionBlocked("invalid S1F local margin plan")
    return {
        (stratum, "modern", "8-K"): x,
        (stratum, "modern", "6-K"): 7 - x,
        (stratum, "development", "8-K"): 7 - x,
        (stratum, "development", "6-K"): x - 4,
    }


def _frontier(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep 70 distinct identities per joint cell; later ones cannot be optimal."""
    result: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
    for row in rows:
        slot = _slot(row)
        identities = seen.setdefault(slot, set())
        identity = _identity(row)
        if identity in identities:
            continue
        if len(identities) == 70:
            continue
        identities.add(identity)
        result.append(row)
    return result


class _MilpOracle:
    """Precomputed exact binary feasibility oracle for shared identities.

    HiGHS is an existing direct scientific dependency (also used for the exact
    interval layer).  The objective is zero: lexicographic order is enforced by
    the caller's sequential include/exclude decisions, not floating weights.
    """

    def __init__(self, rows: Sequence[dict[str, Any]], strata: Sequence[str]) -> None:
        self.n = len(rows)
        constraints: list[tuple[list[int], float, float]] = []
        for stratum in strata:
            constraints.append(([
                index for index, row in enumerate(rows)
                if row["stratum"] == stratum
            ], 10, 10))
            constraints.append(([
                index for index, row in enumerate(rows)
                if row["stratum"] == stratum and row["era"] == "modern"
            ], 7, 7))
            constraints.append(([
                index for index, row in enumerate(rows)
                if row["stratum"] == stratum and row["form"] == "8-K"
            ], 7, 7))
        by_identity: dict[tuple[str, str], list[int]] = {}
        for index, row in enumerate(rows):
            by_identity.setdefault(_identity(row), []).append(index)
        constraints.extend((indexes, 0, 1) for indexes in by_identity.values())

        matrix = lil_matrix((len(constraints), self.n), dtype=float)
        lower: list[float] = []
        upper: list[float] = []
        for line, (indexes, lo, hi) in enumerate(constraints):
            matrix.rows[line] = list(indexes)
            matrix.data[line] = [1.0] * len(indexes)
            lower.append(lo)
            upper.append(hi)
        self.constraint = LinearConstraint(matrix.tocsr(), lower, upper)
        self.objective = [0.0] * self.n
        self.integrality = [1] * self.n

    def feasible(self, fixed: Mapping[int, int]) -> bool:
        lb = [0.0] * self.n
        ub = [1.0] * self.n
        for index, value in fixed.items():
            lb[index] = ub[index] = float(value)
        result = milp(
            c=self.objective,
            integrality=self.integrality,
            bounds=Bounds(lb, ub),
            constraints=self.constraint,
            options={"presolve": True},
        )
        if result.status == 0 and result.success:
            return True
        if result.status == 2:
            return False
        raise SelectionBlocked(
            f"MILP_FEASIBILITY_UNRESOLVED:{result.status}:{result.message}"
        )


def solve_exact70(rows: Iterable[Mapping[str, Any]], *, design_ciks: Iterable[str] = (),
                  strata: Sequence[str] = STRATA) -> list[dict[str, Any]]:
    """Return the lexicographically smallest feasible 70-packet source set.

    Selection checks every legal margin plan.  The candidate frontier is bounded
    by 70 distinct identities in each joint cell: any later filing has at least
    70 earlier substitutes in its own cell and no exact-70 solution can occupy
    all of them elsewhere.
    """
    candidates = _frontier(validate_candidates(rows, strata=strata, design_ciks=design_ciks))
    # The normal case has no filing identity shared across retrieval strata.
    # Then the margin problem factors into seven four-plan choices, which is
    # exact and avoids visiting the 4**7 Cartesian product for every row.
    identity_strata: dict[tuple[str, str], set[str]] = {}
    for row in candidates:
        identity_strata.setdefault(_identity(row), set()).add(str(row["stratum"]))
    if all(len(found) == 1 for found in identity_strata.values()):
        selected: list[dict[str, Any]] = []
        for stratum in strata:
            local = [row for row in candidates if row["stratum"] == stratum]
            options: list[list[dict[str, Any]]] = []
            for x in range(4, 8):
                plan = _local_plan(stratum, x)
                option: list[dict[str, Any]] = []
                for slot in plan:
                    option.extend(row for row in local if _slot(row) == slot)  # trimmed below in sorted order
                selected_keys = {slot: 0 for slot in plan}
                chosen_local: list[dict[str, Any]] = []
                for row in sorted(option, key=lambda value: str(value["selection_key"])):
                    slot = _slot(row)
                    if selected_keys[slot] < plan[slot]:
                        chosen_local.append(row)
                        selected_keys[slot] += 1
                if len(chosen_local) == 10:
                    options.append(sorted(chosen_local, key=lambda value: str(value["selection_key"])))
            if not options:
                raise SelectionBlocked("SOURCE_ALLOCATION_INFEASIBLE")
            selected.extend(min(options, key=lambda option: tuple(str(row["selection_key"]) for row in option)))
        selected = sorted(selected, key=lambda row: str(row["selection_key"]))
        if selection_margins_ok(selected, strata=strata):
            return selected
    oracle = _MilpOracle(candidates, strata)
    if not oracle.feasible({}):
        raise SelectionBlocked("SOURCE_ALLOCATION_INFEASIBLE")
    chosen: list[dict[str, Any]] = []
    fixed: dict[int, int] = {}
    for index, row in enumerate(candidates):
        trial = dict(fixed); trial[index] = 1
        if oracle.feasible(trial):
            fixed[index] = 1
            chosen.append(row)
        else:
            fixed[index] = 0
        if len(chosen) == 70:
            break
    if len(chosen) != 70 or not oracle.feasible(fixed):
        raise SelectionBlocked("SOURCE_ALLOCATION_INFEASIBLE")
    selected = sorted(chosen, key=lambda row: str(row["selection_key"]))
    if not selection_margins_ok(selected, strata=strata):
        raise SelectionBlocked("selected exact-70 breaches frozen joint margins")
    return selected


def selection_margins_ok(rows: Sequence[Mapping[str, Any]], *, strata: Sequence[str] = STRATA) -> bool:
    if len(rows) != 70 or len({_identity(row) for row in rows}) != 70:
        return False
    for stratum in strata:
        subset = [row for row in rows if row["stratum"] == stratum]
        if len(subset) != 10 or sum(row["era"] == "modern" for row in subset) != 7 or sum(row["form"] == "8-K" for row in subset) != 7:
            return False
    return True


def exact70_manifest(rows: Iterable[Mapping[str, Any]], *, design_ciks: Iterable[str],
                     frozen_universe_sha256: str, strata: Sequence[str] = STRATA) -> dict[str, Any]:
    selected = solve_exact70(rows, design_ciks=design_ciks, strata=strata)
    packet_rows = [{key: row.get(key) for key in ("stratum", "era", "form", "cik", "accession", "selection_key", "filed_on", "query_edges", "filename", "display_name", "ticker", "hit_id", "items", "base_form") if key in row}
                   for row in selected]
    manifest = {"schema": "mastermind.dislocation_p0.s1f_exact70_source_manifest.v1",
                "n": 70, "selection_identity": ["cik", "accession"],
                "frozen_candidate_universe_sha256": frozen_universe_sha256,
                "design_ciks_excluded": sorted({canonical_cik(value) for value in design_ciks if canonical_cik(value)}),
                "strata": list(strata), "candidates": packet_rows, "authority": dict(AUTHORITY)}
    manifest["manifest_sha256"] = _digest(manifest)
    return manifest


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (canonical_json(manifest) + "\n").encode("utf-8")
