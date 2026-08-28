"""Stock Identity W3A — the Channel-A model constitution (freeze §4.1b, plan Task 3B).

Prereg only. **This module fits nothing** — it freezes the LEGAL MODEL CLASS that
a future W5Q confirmatory fit must stay inside, before any fit exists. All three
original masterplan §2.3 Channel-A controls bind; W3 owns freezing the first:

  (i) **capacity budget** — the map's effective parameter count ``p_eff`` is
      declared before fitting and must satisfy, exactly and per training fold,
      ``p_eff <= floor(N_train_names / 10)``; the functional form is fixed at
      the W3/PR-3 stage — additive/monotone in a declared feature subset unless
      a richer form is separately preregistered.
  (ii) name-disjoint OOS — frozen elsewhere (§4.3/§4.4); not this module's job.
  (iii) name-permutation null — frozen elsewhere (§4.3/§4.4); not this module's job.

``assert_capacity`` is the enforcement contract: W5Q evaluates it on every
training fold BEFORE any fit and a violation ABORTS the read rather than
shrinking the model silently. No fitting/estimation library is imported here and
no function named ``fit``/``fit_*`` exists anywhere in this module — both are
test-enforced (source-level AST scan), because "no fitting" needs to be provable
from the module's own text, not merely asserted in a docstring.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "ChannelAConstitution",
    "CapacityViolation",
    "load_constitution",
    "count_p_eff",
    "assert_capacity",
]

#: The "10" in `p_eff <= floor(N_train_names / 10)` (freeze §4.1b (i), frozen).
CAPACITY_DENOMINATOR = 10


class CapacityViolation(RuntimeError):
    """Raised when a declared ``p_eff`` exceeds ``floor(N_train_names / CAPACITY_DENOMINATOR)``."""


@dataclass(frozen=True)
class ChannelAConstitution:
    """Immutable, hashable Channel-A model constitution (no fit state)."""

    schema: str
    version: str
    feature_subset: tuple[str, ...]
    functional_form: str
    separately_preregistered_form_ref: str | None
    p_eff_counting_rule: str
    p_eff_terms: Mapping[str, int]
    capacity_denominator: int
    authority: Mapping[str, bool]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "feature_subset": list(self.feature_subset),
            "functional_form": self.functional_form,
            "separately_preregistered_form_ref": self.separately_preregistered_form_ref,
            "p_eff_counting_rule": self.p_eff_counting_rule,
            "p_eff_terms": dict(self.p_eff_terms),
            "capacity_denominator": self.capacity_denominator,
            "authority": dict(self.authority),
        }

    def spec_hash(self) -> str:
        payload = json.dumps(
            self.to_canonical_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_constitution(path: str | Path) -> ChannelAConstitution:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ChannelAConstitution(
        schema=payload["schema"],
        version=payload["version"],
        feature_subset=tuple(payload["feature_subset"]),
        functional_form=payload["functional_form"],
        separately_preregistered_form_ref=payload.get("separately_preregistered_form_ref"),
        p_eff_counting_rule=payload["p_eff_counting_rule"],
        p_eff_terms=dict(payload["p_eff_terms"]),
        capacity_denominator=int(payload.get("capacity_denominator", CAPACITY_DENOMINATOR)),
        authority=dict(payload["authority"]),
    )


def count_p_eff(constitution: ChannelAConstitution) -> int:
    """The declared effective parameter count: the sum of the per-feature shape-term
    counts named in ``p_eff_terms`` (one entry per declared feature; an additive
    monotone term contributes 1, a richer declared shape contributes more) — a
    pure, deterministic sum, never a fitted quantity."""
    return int(sum(constitution.p_eff_terms.values()))


def assert_capacity(p_eff: int, n_train_names: int) -> None:
    """Raise :class:`CapacityViolation` iff ``p_eff > floor(n_train_names / 10)``.

    Exact floor law (freeze §4.1b (i)): the boundary itself is legal
    (``p_eff == floor(N/10)`` passes), only strictly exceeding it raises.
    """
    if n_train_names < 0:
        raise ValueError("n_train_names must be >= 0")
    cap = n_train_names // CAPACITY_DENOMINATOR
    if p_eff > cap:
        raise CapacityViolation(
            f"p_eff={p_eff} exceeds floor(N_train_names/{CAPACITY_DENOMINATOR})={cap} "
            f"(N_train_names={n_train_names})"
        )
