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

THE TESTS
---------
1. id-set relations across all three stores (a new shared id must surface).
2. threshold equality per detector, after unit normalisation, with both raw
   values named in the failure message.
3. the registry's prose ``formula:`` string agrees with its own thresholds map
   (catches the half-edit that moves one and not the other).
4. behavioural agreement of A vs B on the strictly-positive input domain, where
   they are supposed to be equivalent.
5. the KNOWN, ALREADY-SHIPPED disagreements, pinned explicitly (see
   ``KNOWN_DIVERGENCES``) so nobody papers over them and so a change to any of
   them fails loudly and reaches an operator.

NO THRESHOLD NUMBER IS WRITTEN INTO THIS FILE. A guard carrying its own copy of
the thresholds passes happily while all three implementations drift together,
which is strictly worse than no guard at all. Every number compared below is
read live from the implementation that owns it.
"""
from __future__ import annotations

import ast
import random
import re
from pathlib import Path

import pandas as pd
import pytest

import scripts.build_fundamental_forensics as ff_script
from engine.fundamental_forensics import load_registry
from engine.moat_falsifiers import _SENSOR_FNS

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


# ── 5. the divergences that ALREADY ship ──────────────────────────────────────
#
# These are NOT hypothetical. Both surfaces are live today and answer differently
# on the inputs below. They are pinned, not fixed, because fixing one means
# choosing which surface is authoritative — an operator call with published-output
# consequences, explicitly out of scope for this guard.
#
# Root cause of every row: the two growth helpers have different domains.
#   scripts/build_fundamental_forensics.py  _growth   -> c/p - 1.0, None when p <= 0
#   engine/moat_falsifiers.py               _pct_change -> (new-old)/abs(old)*100,
#                                                        None only when |old| < 1e-9
# so a NEGATIVE prior denominator is not-evaluable in one and a real growth in the
# other; and moat adds current-sign gates the projection builder does not have.
#
# Each row asserts the CURRENT answer on both sides. If a row fails, the behaviour
# moved: either someone made an operator decision (good — record it and update this
# table in the same PR) or a threshold/branch drifted (bad — this is the catch).
#
# format: (case_id, detector_id, current, prior, script_fires, moat_verdict, note)
_BASE = {"gross_profit": 400.0, "receivables": 100.0, "inventory": 100.0}
_NAN = float("nan")

KNOWN_DIVERGENCES = [
    # ---- the headline: capital_intensity_rising with no operating income ----
    # moat falls through to its revenue-only branch and FIRES; the projection
    # builder requires op_income to be present and cannot fire at all. Missing or
    # zero OperatingIncomeLoss is common in EDGAR (financials, REITs, many foreign
    # filers), so this is a live published disagreement, not an exotic edge.
    # On this branch moat is also the outlier against the registry kernel, whose
    # own suite pins the strict reading
    # (tests/test_fundamental_forensics_detectors.py::
    #  test_missing_operating_income_does_not_take_revenue_only_branch).
    (
        "capex_op_income_missing_both_periods",
        "capital_intensity_rising",
        {"revenue": 1030.0, "capex": 130.0, "op_income": _NAN, **_BASE},
        {"revenue": 1000.0, "capex": 100.0, "op_income": _NAN, **_BASE},
        False, True,
        "moat takes the revenue-only branch when op_income growth is None; "
        "the projection builder requires op_income and cannot fire",
    ),
    (
        "capex_prior_op_income_zero",
        "capital_intensity_rising",
        {"revenue": 1030.0, "capex": 130.0, "op_income": 50.0, **_BASE},
        {"revenue": 1000.0, "capex": 100.0, "op_income": 0.0, **_BASE},
        False, True,
        "prior op_income == 0 makes growth None on both sides, but only moat "
        "relaxes to revenue-only",
    ),
    (
        "capex_current_op_income_missing_only",
        "capital_intensity_rising",
        {"revenue": 1030.0, "capex": 130.0, "op_income": _NAN, **_BASE},
        {"revenue": 1000.0, "capex": 100.0, "op_income": 100.0, **_BASE},
        False, True,
        "op_income missing in the current period only reproduces the same split",
    ),
    # ---- negative prior denominator ----
    (
        "margin_prior_revenue_negative",
        "margin_compression_despite_revenue_growth",
        {"revenue": 1000.0, "gross_profit": 380.0, "receivables": 100.0,
         "inventory": 100.0, "capex": 100.0, "op_income": 100.0},
        {"revenue": -500.0, "gross_profit": -200.0, "receivables": 100.0,
         "inventory": 100.0, "capex": 100.0, "op_income": 100.0},
        False, True,
        "_growth returns None on a non-positive prior; _pct_change divides by "
        "abs(prior) and returns a number",
    ),
    # ---- moat's current-sign gates, absent from the projection builder ----
    (
        "receivables_current_revenue_negative",
        "receivables_stretch",
        {"revenue": -100.0, "gross_profit": -40.0, "receivables": 200.0,
         "inventory": 200.0, "capex": 100.0, "op_income": 100.0},
        {"revenue": 1000.0, "gross_profit": 400.0, "receivables": 100.0,
         "inventory": 100.0, "capex": 100.0, "op_income": 100.0},
        True, None,
        "moat refuses to evaluate when current revenue <= 0; the projection "
        "builder has no such gate and fires",
    ),
    (
        "capex_current_capex_negative",
        "capital_intensity_rising",
        {"revenue": 1030.0, "capex": -50.0, "op_income": -10.0, **_BASE},
        {"revenue": 1000.0, "capex": 100.0, "op_income": 100.0, **_BASE},
        False, None,
        "moat requires CURRENT capex > 0; the projection builder requires PRIOR "
        "capex > 0",
    ),
]


@pytest.mark.parametrize(
    "case_id,detector_id,current,prior,script_fires,moat_verdict,note",
    KNOWN_DIVERGENCES,
    ids=[row[0] for row in KNOWN_DIVERGENCES],
)
def test_known_divergences_are_pinned_until_an_operator_picks_an_authority(
    case_id, detector_id, current, prior, script_fires, moat_verdict, note
):
    """Pin an EXISTING disagreement so further drift still fails.

    This is deliberately not an xfail: the disagreement is the shipped state, and
    an xfail would hide a change of behaviour. Asserting the exact current answers
    on both sides means the test stays green while the known split persists and
    goes red the moment either side moves.
    """
    actual_script = detector_id in _script_fired(current, prior)
    actual_moat = _moat_verdict(current, prior, detector_id)

    assert (actual_script, actual_moat) == (script_fires, moat_verdict), (
        f"KNOWN DIVERGENCE {case_id!r} on detector {detector_id!r} has moved.\n"
        f"  {note}\n"
        f"  pinned: scripts/build_fundamental_forensics.py fired={script_fires}, "
        f"engine/moat_falsifiers.py={moat_verdict}\n"
        f"  actual: scripts/build_fundamental_forensics.py fired={actual_script}, "
        f"engine/moat_falsifiers.py={actual_moat}\n"
        f"  current={current}\n  prior={prior}\n"
        f"If this change was intentional, an operator has decided which surface is "
        f"authoritative — record that decision and update this row in the same PR. "
        f"If it was not, a threshold or branch drifted on one surface only."
    )


def test_the_pinned_divergences_are_real_disagreements():
    """Meta-guard: every KNOWN_DIVERGENCES row must actually disagree.

    Without this, a future edit could quietly relax a row to (False, False) and
    the table would still pass while asserting nothing.

    The disjunction this once used — ``moat is None or moat != script`` — could
    not catch the relaxation it existed to prevent: ANY row pinned with
    ``moat=None`` satisfied it regardless of ``script_fires``, so relaxing a row
    to ``(False, None)`` was just as uninformative as ``(False, False)`` and
    passed. Each row is now classified explicitly instead.
    """
    observable = 0
    evaluability_only = 0
    for case_id, _did, _cur, _pri, script_fires, moat_verdict, _note in KNOWN_DIVERGENCES:
        if moat_verdict is None:
            # Not-evaluable on the moat side. This is a real difference in
            # REASONING, but it publishes nothing on either surface unless the
            # script fires, so it is counted separately rather than being waved
            # through by a short-circuit.
            if script_fires:
                observable += 1
            else:
                evaluability_only += 1
            continue
        assert moat_verdict != script_fires, (
            f"KNOWN_DIVERGENCES row {case_id!r} pins script={script_fires} and "
            f"moat={moat_verdict}, which agree. A row that agrees belongs in the "
            f"positive-domain differential, not in the divergence table."
        )
        observable += 1

    # The table's whole point is the OBSERVABLE disagreements. If a future edit
    # relaxed every one of them to evaluability-only, the rows above would each
    # pass individually and the table would assert nothing collectively.
    assert observable >= 5, (
        f"only {observable} row(s) still pin an observable output difference "
        f"({evaluability_only} are evaluability-only). The divergence table has "
        f"been relaxed past the point where it documents a shipping defect."
    )
