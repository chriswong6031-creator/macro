"""Cross-pin the four forensic detector ids that exist in THREE implementations.

WHY THIS FILE EXISTS
--------------------
These four detector ids are byte-identical strings in three independent
code paths, and until this guard nothing connected them:

  margin_compression_despite_revenue_growth
  receivables_stretch
  inventory_build
  capital_intensity_rising

  A. ``scripts/build_fundamental_forensics.py`` — declarative ``DETECTORS`` tuple
     (prose thresholds, bilingual) with the real comparisons as INLINE FLOAT
     LITERALS on the ``if`` tests inside ``detect_quarterly``. Fraction scale
     (0.03 / 0.10 / 0.15 / 0.10). Reads ``data/edgar/statements_quarterly.parquet``
     on matched fiscal-QUARTER YoY pairs. Ships to the entitlement-gated Filing
     Forensics workbench.
  B. ``engine/moat_falsifiers.py`` — executable ``_sensor_*`` functions with
     named module constants. Percentage-point scale (3.0 / 10.0 / 15.0 / 10.0).
     Reads ``data/edgar/statements.parquet`` on adjacent fiscal-YEAR pairs,
     PIT-gated by ``period_end + 120d``. Ships to PRODUCTION ticker pages via
     ``scripts/build_ticker_pages.py`` and the thesis-funnel snapshot, nightly.
  C. ``engine/fundamental_forensics/detectors.py`` — registry-driven kernel whose
     thresholds are DATA in ``config/fundamental_forensics.yml`` (Decimal strings
     "3" / "10" / "15" / "10", pp scale). Reads SEC companyfacts vintages.

So the SAME NAMED DETECTOR answers on two live surfaces from two data sources.
Change a threshold in one store and the other two silently keep the old value.

WHAT THIS GUARD DOES **NOT** DO
-------------------------------
It does not unify the implementations and it does not pick a winner. Choosing
which one is authoritative has published-output consequences (ticker pages are
live and have been accruing state since 2026-07-07), so it is an OPERATOR
decision, not a test's. This file only makes divergence VISIBLE: it reads each
implementation's own constants from that implementation's own store, and it
pins the places where they already disagree so that FURTHER drift fails red.

WHY THRESHOLD PINS WERE NOT ENOUGH (2026-08-07)
-----------------------------------------------
Sections 1-4 compare CONSTANTS (3/10/15/10 pp) and the strictly-positive input
domain. All of it was green while ``engine/moat_falsifiers.py`` fired
``capital_intensity_rising`` on 73 live tickers whose ``op_income`` was ABSENT:
its ``oi_g is None`` branch collapsed "operating income is unknown" into the
same relaxation as "operating income is non-positive", and fired on the revenue
leg alone. Same constants, same ids, opposite epistemics — invisible to a
threshold guard. Section 6 therefore pins EVALUABILITY across all three
implementations on a table of missing-input scenarios, which is where that class
of defect actually lives.

THE TESTS
---------
1. id-set relations across all three stores (a new shared id must surface).
2. threshold equality per detector, after unit normalisation, with both raw
   values named in the failure message.
3. the registry's prose ``formula:`` string agrees with its own thresholds map
   (catches the half-edit that moves one and not the other).
4. behavioural agreement of A vs B on the strictly-positive input domain, where
   they are supposed to be equivalent.
6. THE EVALUABILITY CONTRACT, three ways: for every detector x every
   missing-input scenario, the verdict from A, B and C
   (fired / clear / not_evaluable). 6a asserts the RULE — a declared-required
   input that is absent or NaN must make all three not-evaluable; 6b censuses
   the whole matrix and asserts the set of three-way disagreements is EXACTLY
   the pinned, documented, deliberate ones; 6c is the non-vacuity floor.
7. the period/point-in-time models, which differ by DESIGN and are pinned as
   unresolved operator questions rather than silently tolerated.

Section 5 (``KNOWN_DIVERGENCES``) was RETIRED in the same PR that added section
6, not relaxed. Every one of its six rows described a defect that PR fixed, so
none of them is a disagreement any more; every input it carried is now a row of
the section-6 table, which pins all THREE implementations instead of two and
asserts the exact disagreement SET instead of a ">= 5 observable" floor.

Its sixth row is the cautionary one. It pinned "moat gates CURRENT capex, the
projection builder gates PRIOR capex" as tolerable because the projection
builder published CLEAR rather than a false fire. That reasoning was wrong: a
permanent clear drawn from evidence that cannot support one is the same defect
as a false fire with the sign flipped, and it was suppressing coverage counts on
4 live tickers. Both directions of "answering without evidence" are in scope
here — the guard tests verdicts, not just fires.

NO THRESHOLD NUMBER IS WRITTEN INTO THIS FILE. A guard carrying its own copy of
the thresholds passes happily while all three implementations drift together,
which is strictly worse than no guard at all. Every number compared below is
read live from the implementation that owns it. (Section 6 does write literal
INPUT values -- 0.0, -500.0 -- but those are stimuli, not thresholds: they are
chosen to sit far from every fire boundary so that no verdict in the table
depends on a threshold's value.)
"""
from __future__ import annotations

import ast
import json
import random
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

import scripts.build_fundamental_forensics as ff_script
from engine.fundamental_forensics import load_registry, run_fixture_slice
from engine.moat_falsifiers import _SENSOR_FNS, _sensor_cols

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "config" / "fundamental_forensics.yml"

# The four ids under cross-pin. These are the SUBJECT of the guard, not a copy
# of any threshold — they are what must stay in lockstep across the three stores.
SHARED_DETECTOR_IDS = frozenset({
    "margin_compression_despite_revenue_growth",
    "receivables_stretch",
    "inventory_build",
    "capital_intensity_rising",
})

# Detectors that legitimately exist in the projection builder + registry but have
# NO moat sensor. Pinned so that adding a fifth shared detector surfaces here
# instead of quietly creating a fourth un-cross-pinned threshold.
NON_MOAT_DETECTOR_IDS = frozenset({"accruals_trending_up"})


# ── implementation A: AST extraction from the projection builder ──────────────
#
# Regex is NOT safe on this file: 0.03 appears both as the margin FIRE threshold
# and one line later as a severity tier, and 0.10 appears twice inside the capex
# branch. The severity literals (0.25 / 0.30) have the same shape. So anchor on
# the syntax tree instead and take float constants ONLY from `if` TESTS, which
# structurally excludes severity (an Assign, or an IfExp inside the _finding call).
#
# Three detectors anchor on the `_finding("<id>", ...)` call in the if-body.
# capital_intensity_rising CANNOT: its threshold-bearing `if`s contain no
# _finding call, and the `if` that emits the finding contains no constant. It
# anchors on the `capex_triggered` flag assignment instead (a variable name, not
# a number). Every extraction is asserted non-empty so a refactor that breaks an
# anchor fails red rather than passing vacuously on an empty set.
_SCRIPT_FLAG_ANCHORS = {"capital_intensity_rising": "capex_triggered"}


def _float_constants(node: ast.AST) -> set[float]:
    """Float literals in `node`. Ints are excluded so `op_cur <= 0` contributes nothing."""
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, float)
    }


def _finding_ids(nodes: list[ast.stmt]) -> set[str]:
    ids: set[str] = set()
    for stmt in nodes:
        for child in ast.walk(stmt):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_finding"
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and isinstance(child.args[0].value, str)
            ):
                ids.add(child.args[0].value)
    return ids


def _assigns_flag(nodes: list[ast.stmt], flag: str) -> bool:
    """True if any Assign in `nodes` targets `flag`, including tuple targets
    such as `capex_triggered, capex_gap = True, ...`."""
    for stmt in nodes:
        for child in ast.walk(stmt):
            if not isinstance(child, ast.Assign):
                continue
            for target in child.targets:
                elements = target.elts if isinstance(target, ast.Tuple) else [target]
                if any(isinstance(el, ast.Name) and el.id == flag for el in elements):
                    return True
    return False


def script_thresholds_pp() -> dict[str, float]:
    """Fire thresholds from `detect_quarterly`, converted fraction -> percentage points.

    Read out of the source file that the imported module was actually loaded
    from, so the parsed text and the executed code cannot diverge.
    """
    source = Path(ff_script.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "detect_quarterly"
    )

    found: dict[str, set[float]] = {did: set() for did in SHARED_DETECTOR_IDS}
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        body = node.body + node.orelse
        consts = _float_constants(node.test)
        if not consts:
            continue
        for did in _finding_ids(body) & SHARED_DETECTOR_IDS:
            if did not in _SCRIPT_FLAG_ANCHORS:
                found[did] |= consts
        for did, flag in _SCRIPT_FLAG_ANCHORS.items():
            if _assigns_flag(body, flag):
                found[did] |= consts

    out: dict[str, float] = {}
    for did, consts in found.items():
        assert consts, (
            f"AST anchor for {did!r} extracted NO threshold literal from "
            f"detect_quarterly in {ff_script.__file__}. The guard cannot see this "
            f"detector's threshold any more, so it would pass vacuously. The "
            f"anchoring rule (a _finding call, or the "
            f"{_SCRIPT_FLAG_ANCHORS.get(did, 'n/a')!r} flag assignment) needs "
            f"updating to match the refactored source."
        )
        assert len(consts) == 1, (
            f"AST anchor for {did!r} found MULTIPLE distinct threshold literals "
            f"{sorted(consts)} on its `if` tests. The guard refuses to guess which "
            f"one is the fire threshold — update the anchoring rule explicitly."
        )
        out[did] = round(next(iter(consts)) * 100.0, 6)  # fraction -> pp
    return out


# ── implementation B: importable module constants ─────────────────────────────
def moat_thresholds_pp() -> dict[str, float]:
    """Named constants from engine/moat_falsifiers.py (already percentage points).

    Imported by attribute NAME, never re-typed as a literal, so an edit to the
    module moves this side of the comparison automatically.
    """
    import engine.moat_falsifiers as moat

    names = {
        "margin_compression_despite_revenue_growth": "_MARGIN_MIN_REVENUE_GROWTH_PP",
        "receivables_stretch": "_RECV_STRETCH_PP",
        "inventory_build": "_INV_BUILD_PP",
        "capital_intensity_rising": "_CAPEX_INTENSITY_PP",
    }
    out: dict[str, float] = {}
    for did, attr in names.items():
        assert hasattr(moat, attr), (
            f"engine/moat_falsifiers.py no longer defines {attr!r}, the threshold "
            f"constant for {did!r}. It was renamed or inlined — re-point this guard "
            f"at the new store, do not delete the cross-pin."
        )
        out[did] = round(float(getattr(moat, attr)), 6)
    return out


# ── implementation C: registry data ───────────────────────────────────────────
def registry_thresholds_pp() -> dict[str, float]:
    """Thresholds from config/fundamental_forensics.yml, read via the public API."""
    registry = load_registry(REGISTRY_PATH)
    out: dict[str, float] = {}
    for did in SHARED_DETECTOR_IDS:
        thresholds = registry.detector(did).threshold_map()
        assert len(thresholds) == 1, (
            f"registry detector {did!r} now carries {len(thresholds)} thresholds "
            f"{sorted(thresholds)}; the cross-pin assumed exactly one and refuses "
            f"to guess which is comparable to the other two implementations."
        )
        out[did] = round(float(next(iter(thresholds.values()))), 6)
    return out


# ── 1. id-set relations ───────────────────────────────────────────────────────
def test_shared_detector_ids_are_exactly_the_four_in_all_three_stores():
    moat_ids = set(_SENSOR_FNS)
    script_ids = {d["id"] for d in ff_script.DETECTORS}
    registry_ids = {d.detector_id for d in load_registry(REGISTRY_PATH).detectors}

    assert moat_ids == set(SHARED_DETECTOR_IDS), (
        f"engine/moat_falsifiers.py _SENSOR_FNS ids changed.\n"
        f"  expected: {sorted(SHARED_DETECTOR_IDS)}\n"
        f"  actual:   {sorted(moat_ids)}\n"
        f"A sensor added or removed here changes what production ticker pages "
        f"publish. Extend this cross-pin in the same PR."
    )

    assert set(SHARED_DETECTOR_IDS) < script_ids, (
        f"scripts/build_fundamental_forensics.py DETECTORS no longer contains every "
        f"cross-pinned id. missing: {sorted(set(SHARED_DETECTOR_IDS) - script_ids)}"
    )
    assert set(SHARED_DETECTOR_IDS) < registry_ids, (
        f"config/fundamental_forensics.yml no longer contains every cross-pinned id. "
        f"missing: {sorted(set(SHARED_DETECTOR_IDS) - registry_ids)}"
    )

    assert script_ids == registry_ids, (
        f"the projection builder and the registry disagree on the detector roster.\n"
        f"  only in scripts/build_fundamental_forensics.py: {sorted(script_ids - registry_ids)}\n"
        f"  only in config/fundamental_forensics.yml:       {sorted(registry_ids - script_ids)}"
    )

    # A fifth detector appearing in all three (or a new detector anywhere) must
    # reach a human: it is a new un-cross-pinned threshold surface.
    assert moat_ids & script_ids & registry_ids == set(SHARED_DETECTOR_IDS), (
        f"the set of detector ids shared by ALL THREE implementations is no longer "
        f"exactly the four under cross-pin: "
        f"{sorted(moat_ids & script_ids & registry_ids)}. Add the new id to "
        f"SHARED_DETECTOR_IDS and to the threshold accessors above."
    )
    assert script_ids - set(SHARED_DETECTOR_IDS) == set(NON_MOAT_DETECTOR_IDS), (
        f"the roster of detectors that exist WITHOUT a moat sensor changed: "
        f"{sorted(script_ids - set(SHARED_DETECTOR_IDS))} "
        f"(pinned: {sorted(NON_MOAT_DETECTOR_IDS)}). A new detector needs either a "
        f"cross-pin or an explicit entry here recording that moat has no sensor for it."
    )


# ── 2. threshold equality ─────────────────────────────────────────────────────
@pytest.mark.parametrize("detector_id", sorted(SHARED_DETECTOR_IDS))
def test_threshold_agrees_across_all_three_implementations(detector_id: str):
    """Every number here is read live from the store that owns it.

    Unit trap: the projection builder compares FRACTIONS (0.03), moat compares
    PERCENTAGE POINTS (3.0), the registry stores Decimal STRINGS ("3"). Comparing
    them raw gives a 100x false pass/fail, so the script side is scaled to pp
    inside script_thresholds_pp() before it reaches this assertion.
    """
    script = script_thresholds_pp()[detector_id]
    moat = moat_thresholds_pp()[detector_id]
    registry = registry_thresholds_pp()[detector_id]

    assert script == moat == registry, (
        f"THRESHOLD DRIFT on detector {detector_id!r} — the same named detector "
        f"now answers differently on different surfaces:\n"
        f"  scripts/build_fundamental_forensics.py (detect_quarterly, inline literal): "
        f"{script} pp  (written as {script / 100.0} in fraction scale)\n"
        f"  engine/moat_falsifiers.py (module constant):                              "
        f"{moat} pp\n"
        f"  config/fundamental_forensics.yml (registry data):                         "
        f"{registry} pp\n"
        f"These feed the Filing Forensics workbench, production ticker pages, and the "
        f"SEC lineage kernel respectively. Update ALL THREE stores, or record an "
        f"operator decision that they are intentionally different."
    )


# ── 3. registry prose vs registry data ────────────────────────────────────────
@pytest.mark.parametrize("detector_id", sorted(SHARED_DETECTOR_IDS))
def test_registry_formula_text_matches_its_own_thresholds(detector_id: str):
    """The yml carries the threshold twice: once as data, once restated in prose.

    Catches the half-edit that moves `thresholds:` and leaves `formula:` stale
    (or the reverse) — the formula string is what a reviewer reads.
    """
    spec = load_registry(REGISTRY_PATH).detector(detector_id)
    threshold = round(float(next(iter(spec.threshold_map().values()))), 6)
    in_prose = {
        round(float(tok), 6)
        for tok in re.findall(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?", spec.formula)
    }
    assert in_prose == {threshold}, (
        f"registry detector {detector_id!r}: the prose formula and the thresholds map "
        f"disagree.\n  formula:    {spec.formula!r} -> numbers {sorted(in_prose)}\n"
        f"  thresholds: {spec.threshold_map()} -> {threshold}\n"
        f"One of the two was edited without the other."
    )


# ── behavioural differential: shared harness ──────────────────────────────────
_QUARTER_KEYS = {"fiscal_year": 2025, "fiscal_quarter": 1}
_PRIOR_KEYS = {"fiscal_year": 2024, "fiscal_quarter": 1}
_CIK = 320193


def _pair(current: dict, prior: dict) -> tuple[pd.Series, pd.Series]:
    return (
        pd.Series({**current, **_QUARTER_KEYS}),
        pd.Series({**prior, **_PRIOR_KEYS}),
    )


def _script_fired(current: dict, prior: dict) -> set[str]:
    """Bare detector ids fired by the projection builder.

    NOTE the key is "detector", NOT "id": _finding() stamps "id" as
    f"{detector}:{period}" (e.g. "inventory_build:fy2025-q1"), so a guard keyed
    on "id" would find zero matches and report universal disagreement.
    """
    cur, pri = _pair(current, prior)
    return {finding["detector"] for finding in ff_script.detect_quarterly(cur, pri, _CIK)}


def _moat_verdict(current: dict, prior: dict, detector_id: str) -> bool | None:
    cur, pri = _pair(current, prior)
    return _SENSOR_FNS[detector_id](cur, pri)


def _positive_domain_pairs(n: int, seed: int):
    """Strictly-positive, finite synthetic pairs.

    Growth is drawn across (-30%, +60%) so the sampled band straddles every fire
    threshold — that is what makes this differential SENSITIVE rather than
    decorative. Measured: a 2pp move in any one constant produces 15-18
    disagreements per 1,000 pairs.
    """
    rng = random.Random(seed)
    for _ in range(n):
        prior: dict[str, float] = {}
        current: dict[str, float] = {}
        prior["revenue"] = rng.uniform(50.0, 5000.0)
        current["revenue"] = prior["revenue"] * (1.0 + rng.uniform(-0.30, 0.60))
        for field in ("gross_profit", "receivables", "inventory", "capex", "op_income"):
            base = prior["revenue"] * rng.uniform(0.02, 0.5)
            prior[field] = base
            current[field] = base * (1.0 + rng.uniform(-0.30, 0.60))
        yield current, prior


# ── 4. behavioural agreement where they ARE meant to agree ────────────────────
def test_script_and_moat_agree_on_the_strictly_positive_domain():
    """A structural (non-numeric) drift that leaves all constants alone still fails here.

    Scope is deliberate: agreement holds ONLY on strictly-positive, finite inputs.
    The full domain (negatives, zeros, NaN) is where they already diverge, and
    those cases are pinned in test_known_divergences_are_pinned below rather than
    asserted equal — see that test for why.
    """
    disagreements: dict[str, list[tuple[dict, dict, bool, bool]]] = {}
    compared: dict[str, int] = {d: 0 for d in SHARED_DETECTOR_IDS}
    fired_true: dict[str, int] = {d: 0 for d in SHARED_DETECTOR_IDS}
    for current, prior in _positive_domain_pairs(2000, seed=20260807):
        fired = _script_fired(current, prior)
        for detector_id in SHARED_DETECTOR_IDS:
            moat = _moat_verdict(current, prior, detector_id)
            if moat is None:
                continue  # not-evaluable on the moat side is not a disagreement
            compared[detector_id] += 1
            if moat:
                fired_true[detector_id] += 1
            script = detector_id in fired
            if moat != script:
                disagreements.setdefault(detector_id, []).append(
                    (current, prior, script, moat)
                )

    # Non-vacuity floor. Without it this test passes having compared NOTHING:
    # the loop `continue`s whenever the moat side returns None, so a future
    # moat-side gate that made these sensors not-evaluable across the sampled
    # domain would turn the whole differential green while proving nothing.
    # Measured 2026-08-07 over this exact seed: every detector compared on
    # every pair (moat_none == 0), and each fired on a healthy fraction, so
    # these floors are far below today's values and are a regression alarm,
    # not a tuning knob.
    for detector_id in SHARED_DETECTOR_IDS:
        assert compared[detector_id] >= 500, (
            f"{detector_id}: only {compared[detector_id]} of 2000 pairs were "
            "actually compared — the moat side returned not-evaluable for the "
            "rest, so this differential is close to vacuous. Investigate the "
            "moat-side gate before trusting a green run here."
        )
        assert fired_true[detector_id] > 0, (
            f"{detector_id}: the moat sensor never fired across 2000 positive "
            "pairs, so agreement here is agreement on an all-False answer and "
            "proves nothing about the rule."
        )

    if disagreements:
        lines = []
        for detector_id, cases in sorted(disagreements.items()):
            current, prior, script, moat = cases[0]
            lines.append(
                f"  {detector_id}: {len(cases)} disagreement(s); first case\n"
                f"    current={current}\n    prior={prior}\n"
                f"    scripts/build_fundamental_forensics.py fired={script}  "
                f"engine/moat_falsifiers.py={moat}"
            )
        pytest.fail(
            "the projection builder and the moat sensors now disagree on the "
            "strictly-positive input domain, where they were equivalent:\n"
            + "\n".join(lines)
            + "\nThe same named detector would publish different answers on the "
            "Filing Forensics workbench and on production ticker pages."
        )


# ── 6. the EVALUABILITY contract, three ways ──────────────────────────────────
#
# The subject here is not "what number fires" but "when is this detector
# entitled to answer at all". A detector that answers on evidence it DECLARES it
# requires but does not have is publishing a verdict about nothing — and nothing
# in sections 1-4 could see it, because the constants were identical throughout.
#
# All three implementations are driven from the SAME numbers — the registry's own
# companyfacts fixture — so a disagreement in this table is always a difference
# in RULE and never a difference in input. A and B read the fixture's selected
# vintage pair as two pandas rows; C runs its real pipeline over the same payload.
#
# Verdict vocabulary is fired | clear | not_evaluable, taken from each
# implementation's own public surface:
#   A  scripts/build_fundamental_forensics.py — detector_evaluability() decides
#      evaluable, detect_quarterly() decides fired. BOTH are needed: A emits no
#      finding at all for a clear pair AND none for an unevaluable one, so a
#      guard reading only detect_quarterly() would score every refusal as
#      "clear" and reach three-way agreement for entirely the wrong reason.
#   B  engine/moat_falsifiers.py — the sensor returns True / False / None.
#   C  engine/fundamental_forensics/detectors.py via run_fixture_slice() —
#      FindingState TRIGGERED / CLEAR / NOT_EVALUABLE.

FIRED = "fired"
CLEAR = "clear"
NOT_EVALUABLE = "not_evaluable"

FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
_LATEST_ACCESSION = "0000000001-25-000001"
_CURRENT_END = "2024-12-31"
_PRIOR_END = "2023-12-31"

# The same quantity under three names: A and B call it `capex`, the registry
# calls it `capital_expenditures`, EDGAR calls it
# PaymentsToAcquirePropertyPlantAndEquipment. Each scenario edits the us-gaap
# concept and the pandas column together, so every implementation sees one edit.
_FIELD_CONCEPT = {
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "gross_profit": "GrossProfit",
    "receivables": "AccountsReceivableNetCurrent",
    "inventory": "InventoryNet",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "op_income": "OperatingIncomeLoss",
}

# Fields that enter as a growth DENOMINATOR, where a prior value of 0 makes the
# comparison uncomputable. gross_profit is excluded deliberately: it is only ever
# a ratio NUMERATOR (gross_profit / revenue), so a prior of 0 is a perfectly
# computable 0% margin rather than an evaluability failure.
_NUMERATOR_ONLY_FIELDS = frozenset({"gross_profit"})

_ABSENT = "__absent__"   # the filer never reported it
_NAN = "__nan__"         # reported but unparseable -> NaN in the pandas panels

# Stimuli, not thresholds (see module docstring): 0.0 and -500.0 are chosen to
# sit nowhere near any fire boundary, so no verdict in this table moves if a
# threshold constant is retuned. Section 2 owns threshold drift; this section
# owns evaluability.
_MUTATIONS = (
    ("absent_current", (_CURRENT_END,), _ABSENT),
    ("absent_prior", (_PRIOR_END,), _ABSENT),
    ("absent_both", (_CURRENT_END, _PRIOR_END), _ABSENT),
    ("nan_current", (_CURRENT_END,), _NAN),
    ("nan_prior", (_PRIOR_END,), _NAN),
    ("zero_prior", (_PRIOR_END,), 0.0),
    ("zero_current", (_CURRENT_END,), 0.0),
    ("negative_prior", (_PRIOR_END,), -500.0),
    ("negative_current", (_CURRENT_END,), -500.0),
)

# "baseline" applies no mutation. It is load-bearing twice over: it is the
# non-vacuity anchor (all four detectors must FIRE three ways on it, proving the
# harness reaches the detector code at all), and it is the control that every
# mutated row is read against.
# A scenario is an id plus a tuple of EDITS, each (field, periods, value).
#
# Most rows carry exactly one edit. The COMBINED rows exist because single-field
# mutation cannot reach some real filings, and a gate that looks redundant in
# isolation stops being redundant at the intersection. Measured while
# mutation-testing this file (2026-08-07): deleting the current-capex gate from
# detect_quarterly is invisible on every single-field row, because a
# non-positive current capex gives capex_g <= -1.0 which cannot clear
# rev_g + 0.10 — UNLESS current revenue is also negative, which pushes rev_g
# below -1.10 and lets a capex COLLAPSE register as capital intensity RISING.
# A distressed filer reporting a negative revenue restatement and no capex in
# the same period is not exotic, and only a combined row can see it.
SCENARIOS: list[tuple[str, tuple[tuple[str, tuple[str, ...], object], ...]]] = [
    ("baseline", ()),
] + [
    (f"{field}__{name}", ((field, periods, value),))
    for field in _FIELD_CONCEPT
    for name, periods, value in _MUTATIONS
] + [
    (
        "combined__negative_current_revenue_and_zero_current_capex",
        (("revenue", (_CURRENT_END,), -500.0), ("capex", (_CURRENT_END,), 0.0)),
    ),
    (
        "combined__negative_current_revenue_and_negative_current_capex",
        (("revenue", (_CURRENT_END,), -500.0), ("capex", (_CURRENT_END,), -500.0)),
    ),
    (
        "combined__absent_op_income_and_zero_current_capex",
        (("op_income", (_CURRENT_END,), _ABSENT), ("capex", (_CURRENT_END,), 0.0)),
    ),
    # The exact intersection that makes the current-capex gate load-bearing, and
    # the only row in this table that reaches it. THREE conditions must coincide:
    # negative current revenue (so rev_g falls below -1.10), non-positive current
    # capex (so capex_g == -1.0 clears rev_g + 0.10), and a non-positive current
    # operating income (so the DISCLOSED revenue-only fallback is taken and the
    # op-income conjunct cannot veto). A distressed filer posting a negative
    # revenue restatement, no capex and an operating loss in one period satisfies
    # all three — and the detector would report CAPITAL INTENSITY RISING off a
    # capex COLLAPSE to zero. Every single-field row misses this.
    (
        "combined__negative_revenue_zero_capex_and_operating_loss",
        (
            ("revenue", (_CURRENT_END,), -500.0),
            ("capex", (_CURRENT_END,), 0.0),
            ("op_income", (_CURRENT_END,), -500.0),
        ),
    ),
]

_SCENARIO_BY_ID = {scenario_id: edits for scenario_id, edits in SCENARIOS}


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _baseline_pair() -> tuple[dict[str, float], dict[str, float]]:
    """The selected vintage pair's values, read out of the registry's OWN fixture.

    Anchoring both sides on that file is what makes this table a comparison of
    rules. Hand-typing the numbers here would let an edit to the fixture move
    C's answers while A and B kept answering about the old values, and the
    resulting "disagreement" would be an artefact of the guard.
    """
    payload = _fixture("companyfacts_versions.json")
    out: dict[str, dict[str, float]] = {_PRIOR_END: {}, _CURRENT_END: {}}
    for field, concept in _FIELD_CONCEPT.items():
        for entry in payload["facts"]["us-gaap"][concept]["units"]["USD"]:
            if entry.get("accn") == _LATEST_ACCESSION and entry.get("end") in out:
                out[entry["end"]][field] = float(entry["val"])
        assert field in out[_PRIOR_END] and field in out[_CURRENT_END], (
            f"the registry fixture no longer carries {concept!r} (the {field!r} "
            f"column for A and B) on accession {_LATEST_ACCESSION} at BOTH "
            f"{_PRIOR_END} and {_CURRENT_END}. The three-way table can no longer "
            f"drive every implementation off identical numbers, so it would be "
            f"comparing rules against different inputs. Re-point the fixture map."
        )
    return out[_CURRENT_END], out[_PRIOR_END]


def _scenario_dicts(edits) -> tuple[dict, dict]:
    """A and B's view of one scenario: the fixture pair with every edit applied."""
    base_cur, base_pri = _baseline_pair()
    current, prior = dict(base_cur), dict(base_pri)
    for field, periods, value in edits:
        for period in periods:
            target = current if period == _CURRENT_END else prior
            if value == _ABSENT:
                target.pop(field, None)
            elif value == _NAN:
                target[field] = float("nan")
            else:
                target[field] = float(value)
    return current, prior


def _verdict_script(current: dict, prior: dict, detector_id: str) -> str:
    """A's verdict, with the EMITTED FINDING outranking the evaluability map.

    A is the only one of the three that keeps "may I answer" and "what is the
    answer" in two separate functions (detector_evaluability vs
    detect_quarterly), so the two can contradict each other. Reading
    evaluability FIRST and returning not_evaluable on its word would mask a
    finding that detect_quarterly really did emit — and that finding is what
    ships to the workbench. Measured while mutation-testing this file
    (2026-08-07): reverting only detect_quarterly's current-revenue gate, and
    leaving the evaluability map gated, made a genuine false fire INVISIBLE to
    the census. So a fire is reported as a fire whatever the map claims, and the
    contradiction is asserted separately below.
    """
    cur, pri = _pair(current, prior)
    if detector_id in _script_fired(current, prior):
        return FIRED
    evaluable = ff_script.detector_evaluability(cur, pri, pd.DataFrame())
    return CLEAR if evaluable[detector_id] else NOT_EVALUABLE


def _verdict_moat(current: dict, prior: dict, detector_id: str) -> str:
    verdict = _moat_verdict(current, prior, detector_id)
    if verdict is None:
        return NOT_EVALUABLE
    return FIRED if verdict else CLEAR


_REGISTRY_STATE_TO_VERDICT = {
    "triggered": FIRED,
    "clear": CLEAR,
    "not_evaluable": NOT_EVALUABLE,
}


def _verdict_registry(edits) -> dict[str, str]:
    """One real kernel run per scenario; every detector's state comes back from it.

    The kernel has no NaN — on its side of the boundary a fact is reported or it
    is not — so the _NAN scenarios mutate only the pandas panels A and B read and
    present C with the ABSENT payload, which is exactly what an unparseable fact
    IS to the kernel. That is why the nan_* and absent_* rows agree on C.
    """
    payload = deepcopy(_fixture("companyfacts_versions.json"))
    for field, periods, value in edits:
        concept = _FIELD_CONCEPT[field]
        entries = payload["facts"]["us-gaap"][concept]["units"]["USD"]
        if value in (_ABSENT, _NAN):
            payload["facts"]["us-gaap"][concept]["units"]["USD"] = [
                entry for entry in entries
                if not (
                    entry.get("accn") == _LATEST_ACCESSION
                    and entry.get("end") in periods
                )
            ]
        else:
            for entry in entries:
                if entry.get("accn") == _LATEST_ACCESSION and entry.get("end") in periods:
                    entry["val"] = value
    result = run_fixture_slice(
        payload,
        _fixture("submissions_versions.json"),
        load_registry(REGISTRY_PATH),
        as_of="2025-12-31T23:59:59Z",
        recorded_at="2026-08-01T12:00:00Z",
        computed_at="2026-08-01T12:05:00Z",
        knowledge_clock="source_event",
        vintage_policy="latest_known",
    )
    return {
        finding.detector_id: _REGISTRY_STATE_TO_VERDICT[finding.state.value]
        for finding in result.findings
    }


@lru_cache(maxsize=None)
def _verdicts(scenario_id: str) -> dict[str, tuple[str, str, str]]:
    """(script, moat, registry) verdict per detector for one scenario."""
    edits = _SCENARIO_BY_ID[scenario_id]
    current, prior = _scenario_dicts(edits)
    registry = _verdict_registry(edits)
    out: dict[str, tuple[str, str, str]] = {}
    for detector_id in SHARED_DETECTOR_IDS:
        assert detector_id in registry, (
            f"the registry kernel returned no finding at all for {detector_id!r} on "
            f"scenario {scenario_id!r}. Every detector must reach an explicit state "
            f"— absence of a finding is precisely the failure mode this table exists "
            f"to catch, so it is an error here rather than a silently skipped cell."
        )
        out[detector_id] = (
            _verdict_script(current, prior, detector_id),
            _verdict_moat(current, prior, detector_id),
            registry[detector_id],
        )
    return out


def _render(triple: tuple[str, str, str]) -> str:
    script, moat, registry = triple
    return (
        f"\n    A scripts/build_fundamental_forensics.py : {script}"
        f"\n    B engine/moat_falsifiers.py              : {moat}"
        f"\n    C engine/fundamental_forensics/detectors.py: {registry}"
    )


# What each detector DECLARES it needs, read LIVE from the moat module rather
# than copied here, so that widening _sensor_cols() automatically widens this
# guard instead of leaving the new input untested.
_REQUIRED_INPUTS = _sensor_cols()

_ABSENCE_MUTATIONS = ("absent_current", "absent_prior", "absent_both", "nan_current", "nan_prior")

_ABSENCE_CASES = [
    (detector_id, field, mutation)
    for detector_id in sorted(SHARED_DETECTOR_IDS)
    for field in _REQUIRED_INPUTS[detector_id]
    for mutation in _ABSENCE_MUTATIONS
]


# ── 6a. the rule: absent declared evidence => nobody may answer ───────────────
@pytest.mark.parametrize(
    "detector_id,field,mutation",
    _ABSENCE_CASES,
    ids=[f"{d}-{f}-{m}" for d, f, m in _ABSENCE_CASES],
)
def test_absent_required_input_is_not_evaluable_in_all_three(detector_id, field, mutation):
    """A declared-required input that is missing must produce NO verdict anywhere.

    This is the contract the registry kernel owns (it is the attested path, and
    its findings carry an explicit missing_inputs reason), stated as a rule so it
    holds for inputs added later rather than only for the ones known today.

    The regression it exists to catch shipped for weeks:
    engine/moat_falsifiers.py::_sensor_capex_intensity treated an absent
    op_income as licence to fall back to the revenue-only branch and FIRE — 73
    live tickers on data/edgar/statements.parquet, published to production ticker
    pages, while the module's own _assess_coverage recorded the very same row as
    "partial". Unknown is not the same as non-positive.
    """
    triple = _verdicts(f"{field}__{mutation}")[detector_id]
    assert triple == (NOT_EVALUABLE, NOT_EVALUABLE, NOT_EVALUABLE), (
        f"EVALUABILITY BREACH on detector {detector_id!r}: its declared-required "
        f"input {field!r} is {'NaN' if 'nan' in mutation else 'absent'} "
        f"({mutation}) and at least one implementation still reached a verdict."
        f"{_render(triple)}\n"
        f"  {detector_id!r} declares it requires {_REQUIRED_INPUTS[detector_id]} "
        f"(engine/moat_falsifiers.py::_sensor_cols).\n"
        f"An implementation that answers here publishes a signal about evidence it "
        f"does not have. De-escalating to not_evaluable is always permitted; making "
        f"one of these fire is an ESCALATION and goes through the promotion "
        f"gauntlet, not through this test."
    )


_ZERO_PRIOR_CASES = [
    (detector_id, field)
    for detector_id in sorted(SHARED_DETECTOR_IDS)
    for field in _REQUIRED_INPUTS[detector_id]
    if field not in _NUMERATOR_ONLY_FIELDS
]


@pytest.mark.parametrize(
    "detector_id,field",
    _ZERO_PRIOR_CASES,
    ids=[f"{d}-{f}" for d, f in _ZERO_PRIOR_CASES],
)
def test_zero_prior_denominator_is_not_evaluable_in_all_three(detector_id, field):
    """A prior value of 0 leaves no computable growth, so no implementation may answer.

    Distinct from 6a on purpose: the input is PRESENT and perfectly well-formed
    here. What is absent is the ratio, and a detector that treats "I cannot
    compute the comparison" as "the comparison came out negative" makes exactly
    the substitution this section exists to forbid.
    """
    triple = _verdicts(f"{field}__zero_prior")[detector_id]
    assert triple == (NOT_EVALUABLE, NOT_EVALUABLE, NOT_EVALUABLE), (
        f"detector {detector_id!r} reached a verdict with a ZERO prior {field!r}, "
        f"which leaves its growth term undefined."
        f"{_render(triple)}\n"
        f"Division by (or normalisation against) a zero prior has no answer; the "
        f"honest state is not_evaluable."
    )


# ── 6b. the full census, and the disagreements that are DELIBERATE ────────────
#
# Every remaining cell of the matrix is expected to agree three ways. The rows
# below are the exceptions: real, shipped, intentional differences that were
# reviewed and NOT fixed, because fixing any of them moves published output —
# either firing more often (an escalation, which belongs behind the promotion
# gauntlet) or dropping findings a live surface already shows.
#
# Format: (scenario_id, detector_id, script, moat, registry, family, why)
_F1 = "negative prior denominator"

PINNED_THREE_WAY_DISAGREEMENTS: list[tuple[str, str, str, str, str, str, str]] = [
    # ---- family 1: what a NEGATIVE prior denominator means ----
    # scripts/build_fundamental_forensics.py::_growth returns None whenever the
    # prior is <= 0. engine/moat_falsifiers.py::_pct_change and the kernel's
    # _growth both divide by abs(prior) and return a real number. So A refuses a
    # comparison the other two make. Making A match them would let it fire on
    # loss-to-profit turnarounds it has never fired on — strictly MORE findings
    # on a live workbench, i.e. an escalation. Operator call, pinned meanwhile.
    (
        "revenue__negative_prior", "receivables_stretch",
        NOT_EVALUABLE, CLEAR, CLEAR, _F1,
        "prior revenue < 0: A refuses to define revenue growth at all; B and C "
        "normalise by abs(prior) and go on to compare the spread",
    ),
    (
        "revenue__negative_prior", "inventory_build",
        NOT_EVALUABLE, CLEAR, CLEAR, _F1,
        "same split as receivables_stretch — the divergence is in the shared "
        "revenue-growth term, not in the working-capital leg",
    ),
    (
        "revenue__negative_prior", "capital_intensity_rising",
        NOT_EVALUABLE, CLEAR, CLEAR, _F1,
        "same split, reaching the capex comparator through the same revenue term",
    ),
    (
        "receivables__negative_prior", "receivables_stretch",
        NOT_EVALUABLE, FIRED, FIRED, _F1,
        "a negative prior receivables balance: A will not compute the growth, "
        "B and C compute it off abs(prior) and FIRE — the sharpest form of this "
        "family, because the two live surfaces publish opposite answers",
    ),
    (
        "inventory__negative_prior", "inventory_build",
        NOT_EVALUABLE, FIRED, FIRED, _F1,
        "negative prior inventory balance, same split as receivables",
    ),
    (
        "capex__negative_prior", "capital_intensity_rising",
        NOT_EVALUABLE, FIRED, FIRED, _F1,
        "negative prior capex (disposal proceeds in the prior period): A refuses, "
        "B and C fire",
    ),
    (
        "op_income__negative_prior", "capital_intensity_rising",
        NOT_EVALUABLE, CLEAR, CLEAR, _F1,
        "prior operating income < 0 with current > 0 — the loss-to-profit "
        "turnaround. A can never evaluate capital_intensity_rising for one; B and "
        "C compute the growth off abs(prior). NOTE this is NOT the non-positive "
        "revenue-only fallback: that branch keys on the CURRENT value and all "
        "three implementations agree on it (see the op_income__zero_current and "
        "op_income__negative_current rows of the census, which agree three ways)",
    ),
    # ---- family 2 (WHICH period's capex must be positive) was FIXED, not pinned ----
    # It briefly lived here as "A publishes clear, not a false fire, so this is
    # only an evaluability difference". That reasoning was wrong and is worth
    # recording: a permanent CLEAR drawn from evidence that cannot support one is
    # the same defect as a false fire, just pointing the other way. A's _growth
    # constrains only the PRIOR capex, so a non-positive CURRENT capex (net
    # disposal proceeds) produced capex_g <= -1.0 — a well-formed number that can
    # never clear rev_g + 0.10 — and the pair reported clear forever while being
    # COUNTED AS COVERED. 4 live tickers on statements_quarterly.parquet.
    # scripts/build_fundamental_forensics.py now gates current capex > 0 in both
    # detect_quarterly and detector_evaluability, matching both siblings, so
    # capex__zero_current and capex__negative_current now agree three ways and are
    # asserted by the census below rather than pinned as exceptions.
]

_PINNED_BY_CELL = {
    (scenario_id, detector_id): (script, moat, registry, family, why)
    for scenario_id, detector_id, script, moat, registry, family, why
    in PINNED_THREE_WAY_DISAGREEMENTS
}


@pytest.mark.parametrize(
    "scenario_id,detector_id,script,moat,registry,family,why",
    PINNED_THREE_WAY_DISAGREEMENTS,
    ids=[f"{row[0]}-{row[1]}" for row in PINNED_THREE_WAY_DISAGREEMENTS],
)
def test_deliberate_divergences_still_read_exactly_as_pinned(
    scenario_id, detector_id, script, moat, registry, family, why
):
    """Pin a difference that was reviewed and left in place, in BOTH directions.

    Deliberately not an xfail. An xfail would go quietly green the day someone
    "fixed" one of these, which is the outcome that most needs an operator: every
    row here has published-output consequences on at least one live surface.
    """
    actual = _verdicts(scenario_id)[detector_id]
    assert actual == (script, moat, registry), (
        f"PINNED DIVERGENCE moved — {scenario_id!r} on {detector_id!r}.\n"
        f"  family: {family}\n  rationale: {why}\n"
        f"  pinned:{_render((script, moat, registry))}\n"
        f"  actual:{_render(actual)}\n"
        f"If this was intentional an operator has picked an authority for this "
        f"case: record that decision and update this row in the same PR. If it "
        f"was not, one implementation drifted on its own."
    )


def test_the_three_implementations_disagree_on_exactly_the_pinned_cells():
    """The census. Catches a NEW divergence and a silently-healed one alike.

    This is the assertion that replaces the retired section 5's ``observable >= 5``
    floor, and it is strictly stronger: a floor only notices the table shrinking,
    while an exact set notices any movement in either direction — including the
    case where somebody "fixes" a pinned row and deletes its pin in the same
    edit, which a floor of 5 would have waved through at 5 remaining rows.
    """
    actual_disagreements = {}
    for scenario_id, _edits in SCENARIOS:
        for detector_id, triple in _verdicts(scenario_id).items():
            if len(set(triple)) > 1:
                actual_disagreements[(scenario_id, detector_id)] = triple

    unexpected = sorted(set(actual_disagreements) - set(_PINNED_BY_CELL))
    healed = sorted(set(_PINNED_BY_CELL) - set(actual_disagreements))

    detail = []
    for cell in unexpected:
        detail.append(
            f"  NEW DIVERGENCE {cell[0]!r} / {cell[1]!r}:"
            f"{_render(actual_disagreements[cell])}"
        )
    for cell in healed:
        script, moat, registry, family, why = _PINNED_BY_CELL[cell]
        detail.append(
            f"  PINNED DIVERGENCE GONE {cell[0]!r} / {cell[1]!r} ({family}):"
            f"\n    was:{_render((script, moat, registry))}"
            f"\n    now:{_render(_verdicts(cell[0])[cell[1]])}"
            f"\n    {why}"
        )
    assert not unexpected and not healed, (
        f"the set of cells where the three implementations disagree has changed "
        f"({len(unexpected)} new, {len(healed)} gone):\n" + "\n".join(detail) + "\n"
        f"A NEW divergence means the same named detector now publishes different "
        f"answers on the Filing Forensics workbench, production ticker pages and "
        f"the attested receipt path. A divergence GOING AWAY is good news that "
        f"still needs recording — delete its row from "
        f"PINNED_THREE_WAY_DISAGREEMENTS in the same PR and say so."
    )


def test_the_projection_builder_never_fires_what_it_calls_not_evaluable():
    """A's two sources of truth must agree with each other.

    scripts/build_fundamental_forensics.py decides "is this pair evaluable" in
    detector_evaluability() and "does it fire" in detect_quarterly(), as two
    independent expressions of the same gates. detector_evaluability's own
    docstring promises it applies "the same denominator/period gates as each
    detector" — nothing enforced that, so a gate added to one and not the other
    would leave the workbench emitting a finding it simultaneously labels
    uncovered, and the coverage counters (``coverage_by_detector``) would
    disagree with the findings they count.

    Asserted over the whole section-6 scenario table, so every missing-input
    shape exercises both functions.
    """
    contradictions = []
    for scenario_id, edits in SCENARIOS:
        current, prior = _scenario_dicts(edits)
        cur, pri = _pair(current, prior)
        evaluable = ff_script.detector_evaluability(cur, pri, pd.DataFrame())
        fired = _script_fired(current, prior)
        for detector_id in SHARED_DETECTOR_IDS:
            if detector_id in fired and not evaluable[detector_id]:
                contradictions.append((scenario_id, detector_id))

    assert not contradictions, (
        f"scripts/build_fundamental_forensics.py emitted a finding for a pair its "
        f"own detector_evaluability() calls NOT evaluable:\n"
        + "\n".join(f"  {sid!r} -> {did!r}" for sid, did in contradictions)
        + "\nOne of the two functions gained a gate the other did not. The "
        "finding is what reaches the Filing Forensics workbench, so the "
        "published page would carry a detector result that the same build "
        "counts as uncovered."
    )


# ── 6c. non-vacuity floors ────────────────────────────────────────────────────
def test_the_evaluability_table_actually_exercises_all_three_implementations():
    """Without this the whole section can pass having proved nothing.

    Two ways that happens, both seen in this repo before: a table that stops
    reaching the detector code answers not_evaluable everywhere and "agrees"
    perfectly; and a harness wired to the wrong key (``id`` vs ``detector`` — the
    trap section 4's helper documents) finds no findings and scores every row
    clear. Requiring every implementation to produce every verdict, and requiring
    real coverage per detector, makes both of those failures loud.
    """
    seen: dict[int, set[str]] = {0: set(), 1: set(), 2: set()}
    per_detector = {d: 0 for d in SHARED_DETECTOR_IDS}
    for scenario_id, _edits in SCENARIOS:
        for detector_id, triple in _verdicts(scenario_id).items():
            per_detector[detector_id] += 1
            for position, verdict in enumerate(triple):
                seen[position].add(verdict)

    names = {
        0: "A scripts/build_fundamental_forensics.py",
        1: "B engine/moat_falsifiers.py",
        2: "C engine/fundamental_forensics/detectors.py",
    }
    for position, name in names.items():
        assert seen[position] == {FIRED, CLEAR, NOT_EVALUABLE}, (
            f"{name} produced only {sorted(seen[position])} across the whole "
            f"scenario table. Every implementation must reach all three verdicts "
            f"here, or the agreement this section reports is agreement on a "
            f"constant answer and proves nothing about the rules."
        )

    for detector_id, count in per_detector.items():
        assert count >= 40, (
            f"{detector_id} was only exercised on {count} scenarios; the table is "
            f"much smaller than it was when these floors were measured "
            f"({len(SCENARIOS)} scenarios x 4 detectors). Scenarios were deleted "
            f"— restore them or re-derive this floor deliberately."
        )

    assert _verdicts("baseline") == {
        detector_id: (FIRED, FIRED, FIRED) for detector_id in SHARED_DETECTOR_IDS
    }, (
        "the unmutated fixture no longer fires all four detectors in all three "
        "implementations. Every row of this table is read against that control, "
        "so if the baseline does not fire, a not_evaluable elsewhere may simply "
        "mean the harness never reached the detector. Fix the control first: "
        f"{_verdicts('baseline')}"
    )


# ── 7. the period and point-in-time models, pinned as OPEN questions ──────────
def test_period_and_point_in_time_models_are_pinned_as_unresolved_divergences():
    """The largest divergence of all is not numeric and not an input edge case.

    The same detector_id means different THINGS on different surfaces:
      A  matched fiscal QUARTERS, year over year, paired purely on the
         (fiscal_quarter, fiscal_year - 1) labels with no day-gap check, and with
         NO point-in-time gate whatsoever.
      B  adjacent ANNUAL fiscal years (fy_gap == 1), point-in-time gated at
         period_end + _REPORTING_LAG_DAYS, fail-open for rows with no period_end.
      C  an annual vintage pair constrained by a real day gap, plus acceptance
         -time vintage selection and a rule-availability as-of clock.
    So "receivables_stretch" on the Filing Forensics workbench is a QUARTERLY
    statement and the identically-named finding on a ticker page is an ANNUAL
    one, and a relabelled fiscal calendar can slide A's pair without tripping
    anything. That is a product-design question with published consequences, not
    a bug to be quietly fixed by a test, so it is pinned here instead.

    No number from any threshold store is asserted; these are structural facts
    about which period model each implementation carries.
    """
    import engine.moat_falsifiers as moat
    from engine.fundamental_forensics import detectors as kernel

    assert hasattr(ff_script, "detect_quarterly"), (
        "the projection builder's quarterly entry point is gone; if it now "
        "compares annual periods the period-basis divergence has been RESOLVED "
        "— record that and update this pin."
    )
    assert not hasattr(ff_script, "_REPORTING_LAG_DAYS"), (
        "scripts/build_fundamental_forensics.py has acquired a point-in-time "
        "constant. It had none: its findings were computed with no availability "
        "gate at all, unlike both siblings. If a PIT gate was added, this "
        "divergence is resolved — update the pin and say so."
    )
    assert hasattr(moat, "_REPORTING_LAG_DAYS"), (
        "engine/moat_falsifiers.py no longer carries a reporting-lag constant; "
        "its point-in-time gate is the only thing keeping a not-yet-filed fiscal "
        "year from firing on a live ticker page."
    )
    assert kernel.MIN_PERIOD_GAP_DAYS > 100, (
        f"the registry kernel's minimum period gap is now "
        f"{kernel.MIN_PERIOD_GAP_DAYS} days, which is short enough to admit a "
        f"QUARTERLY pair. The kernel has always been annual-only, which is "
        f"precisely why a finding produced by the quarterly projection builder "
        f"can never be reproduced on the attested path. If the kernel is now "
        f"quarterly-capable, the two surfaces can finally be reconciled — that is "
        f"an operator decision, not a silent change."
    )


def test_accruals_has_no_moat_sensor_and_that_gap_is_still_open():
    """A company flagged for accruals on the workbench shows nothing on its stock page.

    accruals_trending_up is declared by the projection builder AND the registry
    but has no sensor in engine/moat_falsifiers.py, so the ticker-page surface is
    silent for it. Adding one would be a NEW signal on a live page — an
    escalation, gauntlet territory — so the gap is pinned rather than closed.
    Test 1 already pins the id sets; this states WHY the asymmetry is tolerated
    so the next reader does not "fix" it as an oversight.
    """
    assert NON_MOAT_DETECTOR_IDS == frozenset({"accruals_trending_up"}), (
        f"the set of detectors that exist on the workbench and in the registry "
        f"but NOT on ticker pages changed to {sorted(NON_MOAT_DETECTOR_IDS)}. "
        f"Each such id is a surface where the two products disagree about what "
        f"is even being measured."
    )
    assert "accruals_trending_up" not in _SENSOR_FNS, (
        "engine/moat_falsifiers.py has gained an accruals sensor. That publishes "
        "a signal on production ticker pages that has never appeared there "
        "before — an escalation, which needs a pre-registered promotion decision "
        "rather than a green test. Record the ruling and update this pin."
    )
