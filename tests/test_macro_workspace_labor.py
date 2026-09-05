"""Composer tests for the US labor_markets workspace (F01 / R2, Labor lane).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Mirrors the exact pattern proven by
tests/test_macro_workspace_liquidity_regime.py: quadrant classification,
disclosed hysteresis, the 1M vector, corrections/supersession, digest
determinism, zh-label integrity, and a real-owner-artifact build.

It ALSO carries the tests that isolate this producer's one known, disclosed
contract gap: the closed schema's ``axis_id`` enum is still R1A-scoped to the
two liquidity axis names and has not yet been widened for a second workspace
(see labor.py's module docstring "KNOWN CONTRACT GAP"). Those tests prove the
composed snapshot is schema-conformant in every other respect and pin the
EXACT single blocker precisely, rather than silently skipping schema coverage.

    python3 -m pytest tests/test_macro_workspace_labor.py -x -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, labor  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"


def _base_regime() -> dict:
    """Realistic values lifted from the real data/regime/latest.json baseline
    (asof 2026-09-03) so the happy-path test doubles as a directional sanity
    check against the live owner data."""
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "labor_nowcast": {
            "initial_claims_4wk": 207250.0,
            "continued_claims": 1779000.0,
            "claims_yoy_pct": -13.375130616509923,
            "claims_z": -1.305491507338908,
            "claims_trend": "falling",
            "indeed_postings": 102.13,
            "indeed_chg_3m_pct": 1.7433751743375137,
            "indeed_trend": "rising",
            "withheld_tax_yoy_pct": 2.9080052937736633,
            "income_trend": "rising",
            "read": "labor firm",
        },
        "recession": {
            "score": 0.217, "label": "low",
            "components": {"prob": 0.76, "curve": 0.0, "claims": 0.0},
            "sahm": -0.03,
        },
        "conditions": {
            "stale_inputs": [],
            "vintages": {},
        },
    }


def _compose(regime: dict, **kw) -> dict:
    return labor.compose(regime, built_at=BUILT_AT, **kw)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _axis(snapshot: dict, axis_id: str) -> dict:
    return next(a for a in snapshot["axes"]["items"] if a["axis_id"] == axis_id)


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_classifies_strong_hiring_tight_market_quadrant_B() -> None:
    snap = _compose(_base_regime())
    assert snap["workspace"]["id"] == "labor_markets"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["status"] == "PRESENT"
    x = snap["headline"]["quadrant"]["x"]
    y = snap["headline"]["quadrant"]["y"]
    assert x >= 50 and y >= 50           # strengthening demand, tight market
    assert snap["headline"]["state_id"] == "B"
    assert snap["headline"]["state_label"]["en"].startswith("Strong hiring")
    for cid in ("claims_momentum", "job_postings_momentum", "sahm_rule_level",
               "claims_recession_subscore"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"
    assert snap["availability"]["contradiction"]["present"] is False


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_required_source_is_typed_source_failed() -> None:
    reg = _base_regime()
    reg["labor_nowcast"]["claims_z"] = None
    snap = _compose(reg)
    r = _required(snap, "claims_momentum")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert "claims_momentum" in snap["availability"]["degraded"]
    assert snap["availability"]["state"] == "SOURCE_FAILED"  # conservative worst


def test_demand_axis_below_coverage_floor_refuses_no_neutral_default() -> None:
    reg = _base_regime()
    # knock out 2 of 3 demand components -> below min_components/floor
    reg["labor_nowcast"]["claims_z"] = None
    reg["labor_nowcast"]["indeed_chg_3m_pct"] = None
    snap = _compose(reg)
    axis = _axis(snap, "labor_demand")
    assert axis["value"] is None
    assert axis["value_status"] == "ABSENT"
    assert axis["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["headline"]["state_id"] is None
    assert snap["headline"]["status"] == "ABSENT"
    assert snap["headline"]["quadrant"]["x"] is None


def test_tightness_axis_requires_both_components_present() -> None:
    # y has exactly 2 total components with min_components=2: losing either
    # one refuses the WHOLE axis (no partial state is possible at 1-of-2).
    reg = _base_regime()
    reg["recession"]["sahm"] = None
    snap = _compose(reg)
    axis = _axis(snap, "labor_supply_tightness")
    assert axis["value"] is None
    assert axis["value_status"] == "ABSENT"
    assert axis["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["headline"]["quadrant"]["y"] is None


def test_stale_required_source_is_typed_stale_not_current() -> None:
    reg = _base_regime()
    reg["conditions"]["stale_inputs"] = ["claims"]
    snap = _compose(reg)
    r = _required(snap, "claims_momentum")
    assert r["freshness"] == "STALE_SOURCE"
    assert snap["availability"]["state"] == "STALE_SOURCE"
    assert snap["availability"]["state"] != "CURRENT"


def test_not_yet_released_source_is_typed() -> None:
    reg = _base_regime()
    reg["labor_nowcast"]["claims_z"] = None
    reg["conditions"]["vintages"]["claims"] = {"not_yet_released": True}
    snap = _compose(reg)
    r = _required(snap, "claims_momentum")
    assert r["freshness"] == "NOT_YET_RELEASED"
    assert snap["availability"]["state"] == "NOT_YET_RELEASED"


def test_source_failed_on_missing_sahm() -> None:
    reg = _base_regime()
    reg["recession"]["sahm"] = None
    snap = _compose(reg)
    r = _required(snap, "sahm_rule_level")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"


# --------------------------------------------------------------------------- #
# contradiction / DISAGREEMENT
# --------------------------------------------------------------------------- #
def test_low_hires_low_fires_contradiction_is_typed_disagreement() -> None:
    reg = _base_regime()
    reg["labor_nowcast"]["claims_trend"] = "falling"
    reg["labor_nowcast"]["indeed_trend"] = "falling"
    snap = _compose(reg)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "low_hires_low_fires"
    assert any("contradiction" in r for r in snap["availability"]["reasons"])
    assert any(i["implication_id"] == "low_hires_low_fires_contradiction"
               for i in snap["implications"]["items"])
    axis = _axis(snap, "labor_demand")
    assert axis["value_status"] == "DISAGREEMENT"
    assert axis["value"] is not None          # typed disagreement, not censoring
    assert snap["headline"]["quadrant"]["x_status"] == "DISAGREEMENT"
    for cid in ("claims_momentum", "job_postings_momentum"):
        comp = next(c2 for c2 in axis["components"] if c2["component_id"] == cid)
        assert comp["coverage_state"] == "DISAGREEMENT"
    # y axis is untouched -- this contradiction only implicates x-side components
    assert _axis(snap, "labor_supply_tightness")["value_status"] != "DISAGREEMENT"
    assert snap["headline"]["quadrant"]["y_status"] != "DISAGREEMENT"


def test_claims_income_divergence_contradiction_is_typed_disagreement() -> None:
    reg = _base_regime()
    reg["labor_nowcast"]["claims_trend"] = "falling"
    reg["labor_nowcast"]["indeed_trend"] = "rising"       # not the low-hires-low-fires case
    reg["labor_nowcast"]["income_trend"] = "falling"
    snap = _compose(reg)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "claims_income_divergence"
    axis = _axis(snap, "labor_demand")
    assert axis["value_status"] == "DISAGREEMENT"
    for cid in ("claims_momentum", "income_growth_proxy"):
        comp = next(c2 for c2 in axis["components"] if c2["component_id"] == cid)
        assert comp["coverage_state"] == "DISAGREEMENT"


def test_no_contradiction_on_healthy_baseline() -> None:
    snap = _compose(_base_regime())
    assert snap["availability"]["contradiction"]["present"] is False
    assert not any("contradiction" in r for r in snap["availability"]["reasons"])


# --------------------------------------------------------------------------- #
# changes / method-version comparability / 1M vector
# --------------------------------------------------------------------------- #
def _prior(state_id="B", method=labor.METHOD_VERSION, x=70.0, y=65.0) -> dict:
    return {
        "generation": {"generation_id": "labor_markets-US-deadbeefdeadbeef"},
        "headline": {
            "state_id": state_id, "method_version": method,
            "effective_date": "2026-08-04",
            "quadrant": {"x": x, "y": y},
        },
    }


def test_no_prior_yields_warmup() -> None:
    snap = _compose(_base_regime())
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "WARMUP"


def test_method_version_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(method="labor_markets.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"


def test_comparable_prior_produces_deltas_and_vector() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(x=40.0, y=55.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    assert {d["metric_id"] for d in snap["changes"]["deltas"]} == {"labor_demand", "labor_supply_tightness"}
    v = snap["headline"]["one_month_vector"]
    assert v["status"] == "PRESENT"
    assert v["dx"] is not None and v["dy"] is not None


# --------------------------------------------------------------------------- #
# hysteresis
# --------------------------------------------------------------------------- #
def _regime_at(claims_z, indeed_chg, withheld_yoy, sahm, claims_recession) -> dict:
    reg = _base_regime()
    reg["labor_nowcast"]["claims_z"] = claims_z
    reg["labor_nowcast"]["indeed_chg_3m_pct"] = indeed_chg
    reg["labor_nowcast"]["withheld_tax_yoy_pct"] = withheld_yoy
    reg["labor_nowcast"]["claims_trend"] = "falling"
    reg["labor_nowcast"]["indeed_trend"] = "rising"
    reg["labor_nowcast"]["income_trend"] = "rising"
    reg["recession"]["sahm"] = sahm
    reg["recession"]["components"]["claims"] = claims_recession
    return reg


def test_hysteresis_holds_prior_within_band() -> None:
    # Exact-target construction (each component standardizes to exactly the
    # axis target, so weighted-mean rounding introduces no drift):
    #   x_target=47.6 -> z=(50-47.6)*0.05=0.12, chg=(47.6-50)*0.2=-0.48, yoy=(47.6-50)*0.16=-0.384
    #   y_target=48.0 -> sahm=(50-48.0)*0.01=0.02, cr=(100-48.0)/100=0.52
    # raw classify(47.6, 48.0) = C (weakening & loose); prior D (x=52 >=50,
    # y=48 <50) only crosses on the demand axis, and 47.6 is within the 5-pt
    # band of its own 50 boundary -> hysteresis holds D.
    reg = _regime_at(claims_z=0.12, indeed_chg=-0.48, withheld_yoy=-0.384, sahm=0.02, claims_recession=0.52)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    x = snap["headline"]["quadrant"]["x"]
    y = snap["headline"]["quadrant"]["y"]
    assert x == 47.6
    assert y == 48.0
    assert abs(x - 50) <= labor.HYSTERESIS_BAND
    assert abs(y - 50) <= labor.HYSTERESIS_BAND
    assert snap["headline"]["hysteresis"]["held_prior"] is True
    assert snap["headline"]["state_id"] == "D"


def test_hysteresis_flips_when_both_axes_beyond_band() -> None:
    # All five inputs sit at their standardization clamp boundary -> x=y=100,
    # both far beyond the 5-pt band from a prior at (20, 20) -> raw classify
    # wins outright (B: strengthening & tight).
    reg = _regime_at(claims_z=-2.5, indeed_chg=10.0, withheld_yoy=8.0, sahm=-0.5, claims_recession=0.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="C", x=20.0, y=20.0))
    assert snap["headline"]["quadrant"]["x"] == 100.0
    assert snap["headline"]["quadrant"]["y"] == 100.0
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "B"


def test_hysteresis_does_not_suppress_decisive_flip_on_other_axis() -> None:
    # demand flips decisively (prior x=20 -> now x=100, far beyond the band)
    # while tightness idles near ITS OWN boundary (y_target=49, via
    # sahm=(50-49)*0.01=0.01, cr=(100-49)/100=0.51) without crossing it (prior
    # y=48, also < 50 -- same side, no crossing). raw classify(100, 49) = D
    # (strengthening & loose). The corrected rule only lets CROSSING axes gate
    # the hold; y never crossed, so it cannot suppress x's real flip.
    reg = _regime_at(claims_z=-2.5, indeed_chg=10.0, withheld_yoy=8.0, sahm=0.01, claims_recession=0.51)
    snap = _compose(reg, prior_snapshot=_prior(state_id="C", x=20.0, y=48.0))
    assert snap["headline"]["quadrant"]["x"] == 100.0
    assert snap["headline"]["quadrant"]["y"] == 49.0
    assert abs(snap["headline"]["quadrant"]["y"] - 50) <= labor.HYSTERESIS_BAND
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "D"


# --------------------------------------------------------------------------- #
# zh narrative strings must never embed an English quadrant label
# --------------------------------------------------------------------------- #
_QUADRANT_EN_LABEL_PHRASES = ("Cooling demand", "Strong hiring", "Weak demand",
                              "Strong demand", "Tight market", "Loose market")


def _find_english_label_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _QUADRANT_EN_LABEL_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_label_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_label_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_english_quadrant_label() -> None:
    for claims_z, indeed_chg, withheld_yoy, sahm, claims_recession in (
        (-2.5, 10.0, 8.0, -0.5, 0.0),    # strong demand / tight -> B
        (2.5, -10.0, -8.0, 0.5, 1.0),    # weak demand / loose -> C
    ):
        reg = _regime_at(claims_z, indeed_chg, withheld_yoy, sahm, claims_recession)
        snap = _compose(reg)
        assert snap["headline"]["state_id"] in ("A", "B", "C", "D")
        leaks = _find_english_label_leaks(snap)
        assert leaks == [], f"English quadrant label leaked into zh field(s): {leaks}"


# --------------------------------------------------------------------------- #
# corrections / supersession honesty (F8 pattern)
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose(_base_regime())
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None
    assert snap["corrections"]["changed_fingerprints"] == []


def test_corrections_superseded_when_same_period_source_value_changes() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["labor_nowcast"]["claims_z"] = -3.0  # revision, SAME asof
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert any(fp.startswith("claims:claims_momentum:")
               for fp in snap2["corrections"]["changed_fingerprints"])
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_same_period_no_source_change() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    snap2 = _compose(copy.deepcopy(reg), prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"
    assert snap2["corrections"]["changed_fingerprints"] == []


def test_corrections_none_when_reference_period_advances() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["asof"] = reg2["date"] = "2026-09-10"  # new observation, not a revision
    reg2["labor_nowcast"]["claims_z"] = -3.0
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# digest determinism (content_sha256 stable under identical owner input)
# --------------------------------------------------------------------------- #
def test_identical_owner_input_yields_identical_digest() -> None:
    reg = _base_regime()
    snap_a = contract.finalize(_compose(copy.deepcopy(reg)))
    snap_b = contract.finalize(_compose(copy.deepcopy(reg)))
    assert snap_a["generation"]["content_sha256"] == snap_b["generation"]["content_sha256"]
    assert snap_a["generation"]["generation_id"] == snap_b["generation"]["generation_id"]


def test_digest_changes_when_owner_input_changes() -> None:
    reg = _base_regime()
    snap_a = contract.finalize(_compose(copy.deepcopy(reg)))
    reg2 = copy.deepcopy(reg)
    reg2["labor_nowcast"]["claims_z"] = -9.0
    snap_b = contract.finalize(_compose(reg2))
    assert snap_a["generation"]["content_sha256"] != snap_b["generation"]["content_sha256"]


def test_digest_is_stable_across_a_different_code_version_stamp() -> None:
    # F2-style adversarial-review guard, mirrored from the R1A contract's own
    # promise: code_version is excluded from the digest, so an identical
    # owner input reproduces an identical digest regardless of which commit
    # produced it.
    reg = _base_regime()
    snap_a = contract.finalize(_compose(copy.deepcopy(reg), code_version="abc123"))
    snap_b = contract.finalize(_compose(copy.deepcopy(reg), code_version="def456"))
    assert snap_a["generation"]["content_sha256"] == snap_b["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# typed-ABSENT required-capability disclosures (Labor-specific care)
# --------------------------------------------------------------------------- #
def test_payrolls_revision_history_is_typed_absent_with_method_text() -> None:
    snap = _compose(_base_regime())
    m = _metric(snap, "payrolls_nfp_change_and_revision")
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert m["value"] is None
    assert "revision" in m["transformation"].lower()
    assert "two months" in m["transformation"].lower() or "two-month" in m["transformation"].lower()


def test_adp_bls_divergence_is_typed_absent_not_fabricated() -> None:
    snap = _compose(_base_regime())
    m = _metric(snap, "adp_bls_payroll_divergence")
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert m["value"] is None
    assert "disagreement" in m["transformation"].lower() or "adp" in m["transformation"].lower()
    # never silently absorbed into availability as if it were a scored axis
    assert "adp_bls_payroll_divergence" not in {c["component_id"] for c in snap["availability"]["required"]}


def test_continued_claims_is_informational_only_not_axis_scored() -> None:
    snap = _compose(_base_regime())
    m = _metric(snap, "continued_claims")
    assert m["status"] == "PRESENT"
    assert m["value"] == 1779000.0
    axis = _axis(snap, "labor_supply_tightness")
    assert "continued_claims" not in {c["component_id"] for c in axis["components"]}
    assert "continued_claims" not in {c["component_id"] for c in _axis(snap, "labor_demand")["components"]}


def test_withheld_tax_is_disclosed_as_proxy_not_true_wage_series() -> None:
    snap = _compose(_base_regime())
    proxy = _metric(snap, "withheld_tax_yoy_pct")
    assert proxy["status"] == "PRESENT"
    assert "proxy" in proxy["transformation"].lower()
    true_wage = _metric(snap, "avg_hourly_earnings_yoy")
    assert true_wage["status"] == "ABSENT"
    assert true_wage["null_reason"] == "NOT_COVERED"


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_labor_markets_is_a_closed_registry_workspace_id() -> None:
    schema = contract.load_schema()
    assert "labor_markets" in schema["$defs"]["workspaceId"]["enum"]


def _widened_validator() -> Draft202012Validator:
    """A LOCAL, in-memory copy of the committed schema with ONLY the
    axis_id enum widened to admit this workspace's two axis ids. This never
    touches the committed schema file -- it exists purely to prove that a
    composed labor_markets snapshot satisfies every OTHER closed-schema rule
    (required keys, nested $defs, presence/null vocab, the drivers block,
    etc.), isolating the one real, disclosed gap to axis_id alone."""
    schema = copy.deepcopy(contract.load_schema())
    schema["$defs"]["axis"]["properties"]["axis_id"]["enum"] = [
        "funding_pressure", "balance_sheet_support",
        "labor_demand", "labor_supply_tightness",
    ]
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_schema_conformant_modulo_axis_id_enum() -> None:
    """Proves the composed+finalized snapshot satisfies the ENTIRE closed
    contract except the not-yet-widened axis_id enum -- the isolating
    counterpart to test_contract_validate_fails_closed_on_axis_id_enum_gap
    below."""
    snap = contract.finalize(_compose(_base_regime()))
    errors = sorted(_widened_validator().iter_errors(snap), key=lambda e: list(e.path))
    assert errors == [], f"unexpected schema violations beyond the known axis_id gap: {errors}"


def test_contract_validate_accepts_native_axis_ids() -> None:
    """The 2026-09-04 R2 schema widening (axis_id enum -> lowercase snake_case
    pattern) made native axis identities legal: the real shared validator now
    accepts a labor_markets snapshot publishing labor_demand /
    labor_supply_tightness directly. Successor of the pre-widening RED pin
    test_contract_validate_fails_closed_on_axis_id_enum_gap."""
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)  # raises ContractError on any violation
    assert [a["axis_id"] for a in snap["axes"]["items"]] == [
        "labor_demand", "labor_supply_tightness"]


def test_drivers_block_reuses_closed_schema_key_names() -> None:
    # The one other schema literal (drivers.rate_side / drivers.balance_sheet)
    # is NOT a blocker -- this producer reuses the exact required key names,
    # just repurposed for the labor-demand and labor-supply-tightness axes.
    snap = _compose(_base_regime())
    assert set(snap["drivers"].keys()) == {"rate_side", "balance_sheet"}
    assert {d["driver_id"] for d in snap["drivers"]["rate_side"]} == {
        "claims_momentum", "job_postings_momentum", "income_growth_proxy"}
    assert {d["driver_id"] for d in snap["drivers"]["balance_sheet"]} == {
        "sahm_rule_level", "claims_recession_subscore"}


# --------------------------------------------------------------------------- #
# real owner artifact
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REGIME_LATEST.exists(), reason="owner artifact data/regime/latest.json absent")
def test_builds_from_real_owner_artifact_and_is_schema_conformant_modulo_axis_id() -> None:
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(labor.compose(regime, built_at=BUILT_AT))
    errors = sorted(_widened_validator().iter_errors(snap), key=lambda e: list(e.path))
    assert errors == [], f"real-data snapshot violates the closed contract beyond axis_id: {errors}"
    assert snap["headline"]["state_id"] in ("A", "B", "C", "D", None)
    assert snap["generation"]["calculation_as_of"] == regime.get("asof")
    assert snap["authority"]["can_size"] is False
    assert snap["workspace"]["id"] == "labor_markets"
