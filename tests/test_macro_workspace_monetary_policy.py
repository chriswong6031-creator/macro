"""Composer tests for the US monetary_policy workspace (F01 / R2).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Also covers the NOT_APPLICABLE headline
shape (this workspace has no dual-axis quadrant -- see monetary_policy.py's
module docstring for why), both DISAGREEMENT contradiction kinds, digest
determinism, zh-label integrity, schema validation, and a real-owner-artifact
build across the three owner inputs (rates_command, cb_desk, rate_transmission).

    python3 -m pytest tests/test_macro_workspace_monetary_policy.py -x -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, monetary_policy  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
RATES_COMMAND_LATEST = ROOT / "data" / "rates_command" / "latest.json"
INTL_RISK_LATEST = ROOT / "data" / "intl_risk" / "latest.json"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"


# --------------------------------------------------------------------------- #
# fixtures (trimmed, representative subsets of the real owner artifacts)
# --------------------------------------------------------------------------- #
def _base_rates_command() -> dict:
    return {
        "schema": "rates_command.v1",
        "asof": "2026-08-31",
        "built": "2026-09-01T07:04:13.943852+00:00",
        "board": {
            "rate_path_row": {
                "policy_rate": 3.63,
                "implied_path": {"m1": None, "m3": 3.83, "m6": 4.04, "m12": 4.24},
                "implied_bp_12m": 61,
                "dots": [{"year": 2026, "median": 3.8}, {"year": 2027, "median": 3.6}],
                "gap": {
                    "horizon_label": "end-2026", "horizon_months": 4,
                    "fed_dot": 3.8, "market": 3.9, "gap_bp": 10,
                    "lean_en": "market ≈ the Fed", "lean_zh": "市场与美联储基本一致",
                },
                "source_en": "ZQ fed-funds futures",
            },
            "inflation_row": {"vs_target_pp": 1.34},
            "risk_row": {"nyfed_prob": 14.0},
            "policy_row": {"state": "ELEVATED"},
        },
        "expectations_pressure": {
            "hawk_score": 1, "ease_score": 1, "net_state": "two_sided",
            "state_label": {"en": "Two-sided — watch the tape", "zh": "双向——观察市场走势"},
        },
        "divergence": [
            {"key": "D1_dots_vs_market", "active": False, "value_bp": 10.0,
             "detail_en": "Market vs dot gap: +10bp — within normal range (threshold: ±50bp).",
             "detail_zh": "市场与点阵图利差：+10个基点——在正常范围内。"},
        ],
        "stance": {
            "en": "Outlook is two-sided: futures price about two hikes.",
            "zh": "前景双向：期货定价约加息两次。",
        },
    }


def _base_cb_desk() -> dict:
    return {
        "as_of": "2026-08-31",
        "built": "2026-09-01T06:31:51.310305+00:00",
        "cbs": [
            {"id": "FED", "policy_rate": 3.63, "asof": "2026-08-28", "stale": False,
             "source": {"series": "DFF", "store": "fred", "cadence": "daily"},
             "bs_impulse": {"impulse_13w": 0.4, "impulse_52w": 1.93, "level": 6730912.0,
                            "asof": "2026-08-26", "unit": "USD billions (×1, raw WALCL is in billions)",
                            "series": "WALCL"},
             "next_meeting": {"date": "2026-09-16", "days": 15}},
            {"id": "ECB", "policy_rate": 2.25, "asof": "2026-08-31", "stale": False,
             "source": {"series": "ECBDFR", "store": "fred", "cadence": "daily"},
             "bs_impulse": {"impulse_13w": -4.42, "impulse_52w": -2.81, "level": 5913041.0,
                            "asof": "2026-08-21", "unit": "EUR billions", "series": "ECBASSETSW"},
             "next_meeting": {"date": "2026-09-10", "days": 9}},
            {"id": "BOJ", "policy_rate": 0.841, "asof": "2026-06-01", "stale": True,
             "source": {"series": "IRSTCI01JPM156N", "store": "fred", "cadence": "monthly"},
             "bs_impulse": {"impulse_13w": -10.2, "impulse_52w": -12.49, "level": 6442957.0,
                            "asof": "2026-07-01", "unit": "JPY trillions", "series": "JPNASSETS"},
             "next_meeting": {"date": "2026-09-18", "days": 17}},
        ],
    }


def _base_rate_transmission() -> dict:
    return {
        "asof": "2026-09-03",
        "state": {
            "rates": {"real_10y": 2.45, "nominal_10y": 4.79, "curve_2s10s": 0.43},
            "expectations": {"breakeven_10y": 2.35, "breakeven_5y5y": 2.33},
        },
    }


def _compose(rc=None, cbd=None, rt=None, **kw) -> dict:
    return monetary_policy.compose(
        rc if rc is not None else _base_rates_command(),
        cbd if cbd is not None else _base_cb_desk(),
        rt if rt is not None else _base_rate_transmission(),
        built_at=BUILT_AT, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_all_required_sources_current() -> None:
    snap = _compose()
    assert snap["availability"]["state"] == "CURRENT"
    for cid in ("fed_funds_rate", "market_implied_path_12m", "curve_2s10s", "fed_balance_sheet_impulse"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"
    assert snap["workspace"]["id"] == "monetary_policy"


def test_baseline_contradiction_is_the_owner_two_sided_split_only() -> None:
    # The baseline fixture mirrors the real owner state: hawk=1/ease=1/
    # net_state=two_sided, so hawk_ease_split legitimately fires (see
    # test_hawk_ease_split_disagreement_is_typed). What must NOT fire in the
    # baseline is the dots-vs-market leg (divergence[0].active is False).
    snap = _compose()
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "hawk_ease_split"
    assert not any("contradiction=dots_vs_market_path" in r
                   for r in snap["availability"]["reasons"])
    assert _metric(snap, "dots_vs_market_gap_bp")["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# NOT_APPLICABLE headline / empty axes (this workspace has no quadrant)
# --------------------------------------------------------------------------- #
def test_headline_is_not_applicable_by_design() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "NOT_APPLICABLE"
    assert h["one_month_vector"]["null_reason"] == "NOT_APPLICABLE"
    assert h["hysteresis"]["applied"] is False
    assert "no dual-axis quadrant" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_fed_rate_is_typed_source_failed() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"] = [c for c in cbd["cbs"] if c["id"] != "FED"]
    snap = _compose(cbd=cbd)
    r = _required(snap, "fed_funds_rate")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert "fed_funds_rate" in snap["availability"]["degraded"]
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    m = _metric(snap, "fed_funds_rate")
    assert m["value"] is None and m["status"] == "ABSENT"


def test_owner_stale_flag_is_typed_stale_not_current() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["stale"] = True  # FED
    snap = _compose(cbd=cbd)
    r = _required(snap, "fed_funds_rate")
    assert r["freshness"] == "STALE_SOURCE"
    assert r["freshness"] != "CURRENT"
    assert snap["availability"]["state"] != "CURRENT"


def test_aged_market_path_beyond_tolerance_is_typed_stale() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["asof"] = "2026-08-01"  # far older than the _MARKET_STALE_DAYS=12 tolerance vs BUILT_AT
    snap = _compose(rc=rc)
    r = _required(snap, "market_implied_path_12m")
    assert r["freshness"] == "STALE_SOURCE"


def test_not_yet_released_market_path_is_typed() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["board"]["rate_path_row"]["implied_bp_12m"] = None
    rc["board"]["rate_path_row"]["not_yet_released"] = True
    snap = _compose(rc=rc)
    r = _required(snap, "market_implied_path_12m")
    assert r["freshness"] == "NOT_YET_RELEASED"
    assert r["null_reason"] == "NOT_YET_RELEASED"
    assert snap["availability"]["state"] == "NOT_YET_RELEASED"


def test_missing_curve_is_typed_source_failed() -> None:
    rt = copy.deepcopy(_base_rate_transmission())
    rt["state"]["rates"]["curve_2s10s"] = None
    snap = _compose(rt=rt)
    r = _required(snap, "curve_2s10s")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    # per-metric freshness must reflect THIS field's own presence, never a
    # shared group flag borrowed from sibling fields (nominal_10y/real_10y
    # are still present in the same owner sub-object).
    curve_m = _metric(snap, "curve_2s10s")
    assert curve_m["freshness"] == "SOURCE_FAILED"
    assert curve_m["status"] == "ABSENT"
    nominal_m = _metric(snap, "nominal_10y")
    assert nominal_m["status"] == "PRESENT"
    assert nominal_m["freshness"] == "CURRENT"


def test_missing_fed_balance_sheet_is_typed_source_failed() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"] = None  # FED
    snap = _compose(cbd=cbd)
    r = _required(snap, "fed_balance_sheet_impulse")
    assert r["freshness"] == "SOURCE_FAILED"
    m = _metric(snap, "fed_balance_sheet_level")
    assert m["value"] is None and m["status"] == "ABSENT"


# --------------------------------------------------------------------------- #
# global policy-rate divergence: refuse rather than default to a fake 0 spread
# --------------------------------------------------------------------------- #
def test_global_divergence_refuses_below_two_reporting_cbs() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"] = [cbd["cbs"][0]]  # only FED reports
    snap = _compose(cbd=cbd)
    m = _metric(snap, "global_policy_divergence_bp")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_global_divergence_computes_with_two_reporting_cbs() -> None:
    snap = _compose()  # baseline has FED/ECB/BOJ
    m = _metric(snap, "global_policy_divergence_bp")
    assert m["value"] is not None
    assert m["status"] == "PRESENT"
    # FED 3.63 - BOJ 0.841 = 2.789pp = 278.9bp (max-min across all 3)
    assert m["value"] == pytest.approx(278.9, abs=0.1)


# --------------------------------------------------------------------------- #
# DISAGREEMENT contradictions (owner-computed flags, never a composer-invented
# threshold) -- both are independent and can fire together.
# --------------------------------------------------------------------------- #
def test_dots_vs_market_disagreement_is_typed() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["divergence"][0]["active"] = True
    snap = _compose(rc=rc)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "dots_vs_market_path"
    assert any("contradiction=dots_vs_market_path" in r for r in snap["availability"]["reasons"])
    m = _metric(snap, "dots_vs_market_gap_bp")
    assert m["status"] == "DISAGREEMENT"
    assert m["value"] is not None  # typed disagreement, not censored
    assert any(i["implication_id"] == "contradiction_dots_vs_market_path"
               for i in snap["implications"]["items"])


def test_hawk_ease_split_disagreement_is_typed() -> None:
    # baseline already has hawk=1, ease=1, net_state=two_sided
    snap = _compose()
    c = snap["availability"]["contradiction"]
    # dots_vs_market_path did not fire (divergence inactive in baseline), so the
    # single contradiction slot is occupied by hawk_ease_split.
    assert c["present"] is True
    assert c["kind"] == "hawk_ease_split"
    m = _metric(snap, "policy_uncertainty_state")
    assert m["status"] == "DISAGREEMENT"
    assert m["value"] == "ELEVATED"


def test_both_contradictions_fire_independently() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["divergence"][0]["active"] = True  # also fire dots_vs_market_path
    snap = _compose(rc=rc)
    # both typed at metric level even though only one occupies the single
    # availability.contradiction slot
    assert _metric(snap, "dots_vs_market_gap_bp")["status"] == "DISAGREEMENT"
    assert _metric(snap, "policy_uncertainty_state")["status"] == "DISAGREEMENT"
    kinds = {i["implication_id"] for i in snap["implications"]["items"]}
    assert "contradiction_dots_vs_market_path" in kinds
    assert "contradiction_hawk_ease_split" in kinds
    # the primary slot is the architecture-named policy-vs-market concept
    assert snap["availability"]["contradiction"]["kind"] == "dots_vs_market_path"


def test_no_contradiction_when_net_state_not_two_sided() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["expectations_pressure"]["net_state"] = "hawkish"
    snap = _compose(rc=rc)
    assert snap["availability"]["contradiction"]["present"] is False
    assert _metric(snap, "policy_uncertainty_state")["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# clock law: meeting day-count is propagated, never recomputed at build time
# --------------------------------------------------------------------------- #
def test_meeting_days_calculation_as_of_is_cb_desk_build_not_snapshot_built_at() -> None:
    snap = _compose()
    m = _metric(snap, "next_fomc_meeting_days")
    assert m["value"] == 15
    assert m["reference_period"] == "2026-09-16"  # the durable meeting DATE
    # pinned to the cb_desk build clock (cbd.as_of), NOT this snapshot's built_at
    assert m["calculation_as_of"] == "2026-08-31"
    assert m["calculation_as_of"] != BUILT_AT
    assert "not re-derived here" in m["transformation"]


# --------------------------------------------------------------------------- #
# owner-native pass-through, not corrected: the observed WALCL unit mismatch
# --------------------------------------------------------------------------- #
def test_fed_balance_sheet_level_passthrough_flags_unit_note() -> None:
    snap = _compose()
    m = _metric(snap, "fed_balance_sheet_level")
    assert m["value"] == 6730912.0  # owner-native, not corrected
    assert "not corrected by this composer" in m["transformation"]


# --------------------------------------------------------------------------- #
# market-implied path is never labeled a forecast
# --------------------------------------------------------------------------- #
def test_market_implied_metrics_carry_honest_basis() -> None:
    snap = _compose()
    for mid in ("market_implied_path_12m_bp", "market_implied_funds_m6", "market_implied_funds_m12"):
        m = _metric(snap, mid)
        assert m["basis"] == "market_implied_futures_price_not_forecast"
    dot = _metric(snap, "fed_dot_median_nearest")
    assert dot["basis"] == "fomc_sep_median_dot_owner_native"
    assert dot["value"] == 3.8


# --------------------------------------------------------------------------- #
# changes / method-version comparability (mirrors R1A; no axis x/y here)
# --------------------------------------------------------------------------- #
def _prior(method=monetary_policy.METHOD_VERSION, fed_rate=3.5, gen="monetary_policy-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["headline"]["effective_date"] = "2026-08-01"
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "fed_funds_rate":
            m["value"] = fed_rate
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="monetary_policy.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(fed_rate=3.5))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(monetary_policy._TRACKED_CHANGE_METRICS)
    fed_delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "fed_funds_rate")
    assert fed_delta["prior_value"] == 3.5
    assert fed_delta["current_value"] == 3.63
    assert fed_delta["delta"] == pytest.approx(0.13, abs=1e-6)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    rc = _base_rates_command()
    prior_snap = contract.finalize(monetary_policy.compose(
        rc, _base_cb_desk(), _base_rate_transmission(), built_at=BUILT_AT))
    rc2 = copy.deepcopy(rc)
    rc2["board"]["rate_path_row"]["policy_rate"] = 3.88  # same asof, revised value
    cbd2 = copy.deepcopy(_base_cb_desk())
    cbd2["cbs"][0]["policy_rate"] = 3.88
    snap2 = monetary_policy.compose(rc2, cbd2, _base_rate_transmission(),
                                     built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    rc = _base_rates_command()
    prior_snap = contract.finalize(monetary_policy.compose(
        rc, _base_cb_desk(), _base_rate_transmission(), built_at=BUILT_AT))
    rc2 = copy.deepcopy(rc)
    rc2["asof"] = "2026-09-01"  # new observation, not a revision
    rc2["board"]["rate_path_row"]["policy_rate"] = 3.88
    snap2 = monetary_policy.compose(rc2, _base_cb_desk(), _base_rate_transmission(),
                                     built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# digest determinism (contract.py's content_digest excludes generation/build
# provenance; identical owner input -> identical digest)
# --------------------------------------------------------------------------- #
def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_owner_input_changes() -> None:
    snap1 = contract.finalize(_compose())
    rc2 = copy.deepcopy(_base_rates_command())
    # Mutate a field the composer actually publishes (market_implied_path_12m_bp).
    # rate_path_row.policy_rate is deliberately NOT consumed — the realized funds
    # rate comes from cb_desk (FRED DFF), so mutating it must NOT move the digest.
    rc2["board"]["rate_path_row"]["implied_bp_12m"] = 80
    snap2 = contract.finalize(_compose(rc=rc2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]

    rc3 = copy.deepcopy(_base_rates_command())
    rc3["board"]["rate_path_row"]["policy_rate"] = 4.0  # unconsumed duplicate field
    snap3 = contract.finalize(_compose(rc=rc3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False


def test_degraded_snapshots_still_validate() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["divergence"][0]["active"] = True
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"] = [cbd["cbs"][0]]  # force COMPUTATION_REFUSED divergence + only FED
    snap = contract.finalize(monetary_policy.compose(
        rc, cbd, _base_rate_transmission(), built_at=BUILT_AT))
    contract.validate(snap)


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling (mirrors the R1A F11 regression pattern)
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "the market implies", "median dot", "Hawkish and easing pressure legs",
    "roughly balanced", "This is a market", "watch the tape",
)


def _find_english_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _COMPOSER_ENGLISH_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_composer_english_phrasing() -> None:
    rc = copy.deepcopy(_base_rates_command())
    rc["divergence"][0]["active"] = True  # exercise both contradiction paths
    snap = _compose(rc=rc)
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    """Every bilingual pair this composer itself writes (not a straight owner
    pass-through) must carry a real zh string, not None-by-omission."""
    snap = _compose()
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]


# --------------------------------------------------------------------------- #
# real owner artifacts (rates_command + cb_desk sub-block + rate_transmission
# sub-block) -- skipped where the artifact is absent, never fabricated.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not (RATES_COMMAND_LATEST.exists() and INTL_RISK_LATEST.exists() and REGIME_LATEST.exists()),
    reason="one or more real owner artifacts are absent")
def test_builds_and_validates_from_real_owner_artifacts() -> None:
    rc = json.loads(RATES_COMMAND_LATEST.read_text(encoding="utf-8"))
    intl_risk = json.loads(INTL_RISK_LATEST.read_text(encoding="utf-8"))
    cbd = intl_risk.get("cb_desk") or {}
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    rt = regime.get("rate_inflation_transmission") or {}

    snap = contract.finalize(monetary_policy.compose(rc, cbd, rt, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["headline"]["state_id"] is None
    assert snap["axes"]["items"] == []
    assert snap["generation"]["calculation_as_of"] == rc.get("asof")
    assert snap["authority"]["can_size"] is False
    # FED/ECB/BOJ are the architecture-named trio and should be present in any
    # live cb_desk pull (a real-data smoke check, not a hardcoded fixture claim)
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    assert {"fed_funds_rate", "ecb_deposit_rate", "boj_policy_rate"} <= ids
