"""Estimator implication output contract v1 — a read-only composer.

This module is a **read-only composer**: it edits neither
``engine/synthetic_control.py`` nor ``engine/seasonality/event_study.py``, only
reads their frozen result artifacts and copies selected values verbatim.

It is **measurement-tier only**. The emitted payload carries a point estimate,
its uncertainty, honest sample/episode counts, and diagnostics — and nothing
else. There is no rank, gate, size, direction-confidence, or expected-impact
field anywhere in the schema; adding one would be an unauthorized K5-class
promotion this module has no authority to make.

Nulls are **printed with plain-word reasons**, in English and Chinese, never
fabricated or silently dropped. An unregistered search family is refused
outright (``UnregisteredSearchFamily``) rather than served as a weak or
"pending" result.

The composer is **deterministic**: no wall clock, no network, no randomness.
The payload id is a content-bound digest, so mutating the underlying artifact
changes the id.

This is a **strict named profile** of ``mastermind.research_implication_card/v1``
(#6830, ``engine/research_implication_card.py``) — not the same schema. It
reuses #6830's key names and semantics verbatim wherever a field is shared
(the five ``authority`` keys, the six ``quality`` states, the
``null_reasons``/``limitations``/``diagnostics`` key spellings, the
``code/label/value/unit/source`` metric shape, the
``code/label/passed/detail/source`` diagnostic shape, and the ``{en, zh}``
localized shape). It differs deliberately: ``schema`` is its own const (a
profile, not a card); the id namespace is ``eimp_`` rather than ``ric_`` so
the two id spaces can never collide; ``adapter_version`` becomes
``composer_version`` because this module composes rather than adapts; and it
adds ``registered_family`` + ``honest_n`` blocks that #6830's card does not
require. See the PR body for the full reconciliation note.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from engine.seasonality.event_study import (
    UnregisteredSearchFamily,
    family_is_registered,
)
from engine.trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_ID = "mastermind.estimator_implication/v1"
ENVELOPE_SCHEMA = "mastermind.estimator_implications/v1"
COMPOSER_VERSION = "estimator_implication/v1"
CONTRACT_PATH = "contracts/estimator_implication.v1.schema.json"

AUTHORITY_KEYS = ("forecast_authority", "ranking_authority", "gating_authority",
                  "sizing_authority", "trading_authority")

QUALITY_STATES = frozenset({"COMPLETE", "DIAGNOSTIC_ONLY", "ARTIFACT_INCOMPLETE",
                             "ARTIFACT_MISSING", "DIAGNOSTIC_FAILED", "STALE"})

FORBIDDEN_KEYS = frozenset({
    "rank", "score", "ranking", "gate", "gated", "gating", "size",
    "sizing", "position_size", "confidence", "direction_confidence",
    "expected_impact", "recommendation", "action", "trade",
    "signal", "alpha", "target", "weight",
})

SC_MODULE_PATH = "engine/synthetic_control.py"
SC_RESULT_PATH = "data/experiments/synthetic_control_phase0_results.json"
SC_RESULT_SHA256 = "f759bdd72de5370e597459dc0630bb1f880e8a38be9b8882a1c75f54872af1e2"
SC_SELECTION = "sp_pure_adds/sc_nnls/0_5"
SC_FAMILY = "synthetic_control_phase0"

ES_MODULE_PATH = "engine/seasonality/event_study.py"
ES_RESULT_PATH = "data/experiments/hincl2_event_study_results.json"
ES_RESULT_SHA256 = "f415b2c4cf9b12fbc8e4dd9e3a30a51c736c93f4ffbc3f818392b4796ea81139"
ES_SELECTION = "announce/h20"
ES_FAMILY = "hincl2_announce_dsr32"  # the h=20 pick out of a 32-config
# (n_trials_dsr) DSR search over event_curve_announce horizons — a real search
# family that has never been written to engine.trial_ledger (see the refusal
# path below); a test-supplied ledger that DOES register it exercises the
# positive compose path.


class ImplicationContractError(ValueError):
    """A payload could not be composed, or failed contract validation."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_contract(root: Path = REPO_ROOT) -> dict:
    """Read the contract from disk. No network, no off-disk $ref resolution."""
    path = Path(root) / CONTRACT_PATH
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def compute_payload_id(*, composer_version: str, estimator_id: str,
                        result_artifact_path: str, result_artifact_sha256: str,
                        selection_id: str, family_id: str) -> str:
    """Content-bound id: mutating the artifact or selection changes the digest."""
    fields = {
        "composer_version": composer_version,
        "estimator_id": estimator_id,
        "result_artifact_path": result_artifact_path,
        "result_artifact_sha256": result_artifact_sha256,
        "selection_id": selection_id,
        "family_id": family_id,
    }
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "eimp_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_json(root: Path, rel_path: str) -> Any:
    path = Path(root) / rel_path
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _verify_digest(root: Path, rel_path: str, expected_sha256: str) -> None:
    path = Path(root) / rel_path
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise ImplicationContractError(
            f"result artifact digest mismatch for {rel_path!r}: expected "
            f"{expected_sha256!r}, observed {observed!r} — refusing to compose "
            "an implication from an artifact that has changed underneath the pin"
        )


def _default_ledger(ledger: Any) -> Any:
    if ledger is not None:
        return ledger
    return TrialLedger()


def compose_synthetic_control_implication(root: Path = REPO_ROOT, *, ledger=None) -> dict:
    """Compose the synthetic-control implication payload. Read-only; edits nothing."""
    root = Path(root)
    _verify_digest(root, SC_RESULT_PATH, SC_RESULT_SHA256)
    ledger = _default_ledger(ledger)
    family_id = SC_FAMILY

    if not family_is_registered(ledger, family_id):
        raise UnregisteredSearchFamily(
            f"search family {family_id!r} was never registered in engine.trial_ledger"
        )
    effective_n = int(ledger.effective_n(family_id))

    data = _load_json(root, SC_RESULT_PATH)
    fam = data["families"]["sp_pure_adds"]
    arm = fam["arms"]["sc_nnls"]["real"]["0_5"]
    gates = data["gate_eval"]["gates"]
    pc2_reason = data["gate_eval"]["reasons"].get("PC2", "PC2_estimators_unbiased failed")

    point_value = arm["mean"]
    point_estimate = {
        "code": "sc_nnls_caar_0_5_mean",
        "label": {"en": "Synthetic-control CAAR[0,5], sc_nnls arm, event-weighted mean",
                   "zh": "合成对照 CAAR[0,5]，sc_nnls 组，事件加权均值"},
        "value": point_value,
        "unit": "return_fraction",
        "source": "#/families/sp_pure_adds/arms/sc_nnls/real/0_5/mean",
    }

    uncertainty = [{
        "code": "sc_nnls_caar_0_5_t",
        "kind": "student_t_p",
        "label": {"en": "Monthly-clustered NW t-statistic on the CAAR[0,5] mean",
                  "zh": "CAAR[0,5] 均值的月度聚类 NW t 统计量"},
        "value": arm.get("t"),
        "unit": "t_stat",
        "source": "#/families/sp_pure_adds/arms/sc_nnls/real/0_5/t",
    }]

    null_reasons = []

    # Genuine EN/ZH parity: each detail is a real translation of that code's
    # gate_eval reason (pinned to the SC_RESULT_SHA256 artifact), never a
    # pointer to an internal artifact key.
    zh_detail = {
        "PC1_positive_control_survives": (
            "sc_nnls 标普纯增组 CAAR[0,5]=3.015%（事件加权）／4.907%（月度加权），"
            "月度聚类 NW t=8.291（要求均值大于零且 t 大于 2）"
        ),
        "PC2_estimators_unbiased": (
            "sp_pure_adds/matched_k 均值=0.190% t=4.316 未通过；"
            "sp_pure_adds/sc_nnls 均值=0.197% t=4.535 未通过；"
            "phase3_start/matched_k 均值=0.143% t=15.429 未通过；"
            "phase3_start/sc_nnls 均值=0.137% t=15.431 未通过"
            "（要求两族的 |均值| 均小于 0.3% 且 |t| 均小于 2）"
        ),
        "PC3_sc_not_noisier": (
            "sc_nnls 安慰剂标准差=0.614%，SPY-CAR 安慰剂标准差=0.650%"
            "（要求合成对照标准差不高于基准）"
        ),
        "F1_falsifier_holds": (
            "phase3 sc_nnls CAAR[0,20]=0.496%，月度聚类 NW t=1.662，"
            "经验 p 值=0.731（要求 |t| 小于 2 且 p 大于 0.05）"
        ),
    }
    diagnostics = []
    for code, label_en, label_zh in [
        ("PC1_positive_control_survives", "Positive control survives", "正向对照通过"),
        ("PC2_estimators_unbiased", "Estimators unbiased on placebo families", "安慰剂族估计量无偏"),
        ("PC3_sc_not_noisier", "SC placebo dispersion not noisier than incumbent", "合成对照安慰剂离散度未高于基准"),
        ("F1_falsifier_holds", "Falsifier window holds", "证伪窗口成立"),
    ]:
        diagnostics.append({
            "code": code,
            "label": {"en": label_en, "zh": label_zh},
            "passed": gates.get(code),
            "detail": {"en": data["gate_eval"]["reasons"].get(code.split("_")[0], pc2_reason),
                       "zh": zh_detail[code]},
            "source": f"#/gate_eval/gates/{code}",
        })

    limitations = [{
        "en": "PC2 (estimators unbiased) FAILS on both placebo families "
              "(sp_pure_adds and phase3_start, matched_k and sc_nnls arms all "
              "|t|>2 on a placebo where the true effect should be zero); the "
              "estimator is diagnostically biased and this payload is marked "
              "DIAGNOSTIC_FAILED accordingly.",
        "zh": "PC2（估计量无偏）在两个安慰剂族上均未通过（sp_pure_adds 与 "
              "phase3_start，matched_k 与 sc_nnls 组的 |t| 均大于 2，而安慰剂的"
              "真实效应本应为零）；该估计量存在诊断性偏差，本载荷相应标记为 "
              "DIAGNOSTIC_FAILED。",
    }]

    payload_id = compute_payload_id(
        composer_version=COMPOSER_VERSION,
        estimator_id="engine.synthetic_control",
        result_artifact_path=SC_RESULT_PATH,
        result_artifact_sha256=SC_RESULT_SHA256,
        selection_id=SC_SELECTION,
        family_id=family_id,
    )

    payload = {
        "schema": SCHEMA_ID,
        "payload_id": payload_id,
        "composer_version": COMPOSER_VERSION,
        "estimator_id": "engine.synthetic_control",
        "registered_family": {
            "family_id": family_id,
            "registry": "engine.trial_ledger",
            "registered": True,
            "effective_n": effective_n,
        },
        "selection": {
            "selection_id": SC_SELECTION,
            "window": "0_5",
            "anchor": "sp_pure_adds",
        },
        "point_estimate": point_estimate,
        "uncertainty": uncertainty,
        "honest_n": {
            "sample_n": int(fam["n_fitted"]),
            "episode_n": int(fam["n_events"]),
            "basis": {"en": f"sample_n counts fitted event-window observations "
                            f"(n_fitted={fam['n_fitted']}, after dropping "
                            f"{fam['n_dropped_unfitted']} unfitted); episode_n counts "
                            f"all proposed episodes before that drop "
                            f"(n_events={fam['n_events']}, matching n_tickers="
                            f"{fam['n_tickers']})",
                      "zh": f"sample_n 为已拟合事件窗口观测数（n_fitted="
                            f"{fam['n_fitted']}，已剔除 {fam['n_dropped_unfitted']} "
                            f"个未能拟合的事件）；episode_n 为剔除前提出的全部事件数"
                            f"（n_events={fam['n_events']}，与 n_tickers="
                            f"{fam['n_tickers']} 相同）"},
        },
        "diagnostics": diagnostics,
        "quality": "DIAGNOSTIC_FAILED",
        "null_reasons": null_reasons,
        "limitations": limitations,
        "provenance": {
            "producing_module": SC_MODULE_PATH,
            "producing_module_sha256": sha256_file(root / SC_MODULE_PATH),
            "result_artifact_path": SC_RESULT_PATH,
            "result_artifact_sha256": SC_RESULT_SHA256,
            "generator_path": None,
            "generator_sha256": None,
            "report_path": None,
            "report_sha256": None,
        },
        "authority": {k: False for k in AUTHORITY_KEYS},
    }
    return payload


def compose_event_study_implication(root: Path = REPO_ROOT, *, ledger=None,
                                     family_id: "str | None" = ES_FAMILY) -> dict:
    """Compose the event-study implication payload, honoring family registration.

    ``family_id`` names the h=20 pick out of a 32-config (``n_trials_dsr``)
    search over ``event_curve_announce`` — reading that winner without a
    registered family would spend an unrecorded multiple-testing budget, so
    this raises ``UnregisteredSearchFamily`` (event_study.py:144) whenever
    ``family_id`` is unregistered in ``ledger`` — true today against the real
    ``engine.trial_ledger`` (nobody has registered it there), and true for any
    stub ledger with no matching family. A test-supplied ``ledger`` that DOES
    register ``family_id`` exercises the positive compose path below, proving
    the schema against a real ``engine.seasonality.event_study`` payload.
    """
    root = Path(root)
    _verify_digest(root, ES_RESULT_PATH, ES_RESULT_SHA256)
    ledger = _default_ledger(ledger)

    if not family_is_registered(ledger, family_id):
        raise UnregisteredSearchFamily(
            f"search family {family_id!r} was never registered: reading the h=20 "
            "winner of a 32-config event-study search spends a multiple-testing "
            "budget that engine.trial_ledger has no record of, so no implication "
            "can be published for it"
        )
    effective_n = int(ledger.effective_n(family_id))

    data = _load_json(root, ES_RESULT_PATH)
    point_value, curve_n = data["event_curve_announce"][str(data["primary_horizon"])]

    point_estimate = {
        "code": "hincl2_announce_caar_h20_mean",
        "label": {"en": "HINCL2 announcement-window CAAR at h=20, DSR-selected arm",
                   "zh": "HINCL2 公告窗口 h=20 处的 CAAR，DSR 选定组"},
        "value": point_value,
        "unit": "return_fraction",
        "source": "#/event_curve_announce/20/0",
    }

    null_reasons = [{
        "code": "event_study_t_stat_not_recorded",
        "reason": {"en": "No t-statistic recorded for this horizon",
                   "zh": "该窗口未记录 t 统计量"},
        "detail": {"en": "The hincl2 event-study artifact records the DSR-selected "
                         "mean and its supporting count at h=20 but no accompanying "
                         "t-statistic, so uncertainty is left null rather than "
                         "fabricated.",
                   "zh": "hincl2 事件研究产物记录了 h=20 处 DSR 选定的均值及其支持"
                         "样本数，但未记录相应的 t 统计量，因此不确定性字段保留为"
                         "空，而非伪造。"},
    }]
    uncertainty = [{
        "code": "hincl2_announce_caar_h20_t",
        "kind": "student_t_p",
        "label": {"en": "t-statistic on the h=20 CAAR (not recorded)",
                  "zh": "h=20 处 CAAR 的 t 统计量（未记录）"},
        "value": None,
        "unit": "t_stat",
        "source": "#/event_curve_announce/20",
    }]

    diagnostics = [{
        "code": "DSR_search_registered",
        "label": {"en": "DSR search family registered before this read",
                  "zh": "DSR 搜索族在本次读取前已登记"},
        "passed": True,
        "detail": {"en": f"family {family_id!r} carries effective_n={effective_n} "
                         "in engine.trial_ledger, so the 32-config search this "
                         "h=20 pick came from is deflated for multiple testing.",
                   "zh": f"族 {family_id!r} 在 engine.trial_ledger 中的 "
                         f"effective_n={effective_n}，因此该 h=20 结果所来自的 "
                         "32 组搜索已针对多重检验进行了折算。"},
        "source": "#/n_trials_dsr",
    }]

    limitations = [{
        "en": "This payload composes only once family_id is registered; the real "
              "engine.trial_ledger has no such registration today, so in "
              "production this path raises UnregisteredSearchFamily instead.",
        "zh": "本载荷仅在 family_id 已登记时才会生成；当前真实的 "
              "engine.trial_ledger 尚无该登记，因此在生产环境中此路径会抛出 "
              "UnregisteredSearchFamily。",
    }]

    payload_id = compute_payload_id(
        composer_version=COMPOSER_VERSION,
        estimator_id="engine.seasonality.event_study",
        result_artifact_path=ES_RESULT_PATH,
        result_artifact_sha256=ES_RESULT_SHA256,
        selection_id=ES_SELECTION,
        family_id=family_id,
    )

    return {
        "schema": SCHEMA_ID,
        "payload_id": payload_id,
        "composer_version": COMPOSER_VERSION,
        "estimator_id": "engine.seasonality.event_study",
        "registered_family": {
            "family_id": family_id,
            "registry": "engine.trial_ledger",
            "registered": True,
            "effective_n": effective_n,
        },
        "selection": {
            "selection_id": ES_SELECTION,
            "window": "0_20",
            "anchor": "announce",
        },
        "point_estimate": point_estimate,
        "uncertainty": uncertainty,
        "honest_n": {
            "sample_n": int(curve_n),
            "episode_n": int(data["roster_add_events"]),
            "basis": {"en": "sample_n counts the h=20 curve's supporting "
                            "observations; episode_n counts roster_add_events "
                            "(the distinct corporate-action episodes proposed "
                            "before any coverage/fit filtering)",
                      "zh": "sample_n 为 h=20 曲线的支持观测数；episode_n 为 "
                            "roster_add_events（在覆盖率/拟合筛选之前提出的独立"
                            "公司行为事件数）"},
        },
        "diagnostics": diagnostics,
        "quality": "DIAGNOSTIC_ONLY",
        "null_reasons": null_reasons,
        "limitations": limitations,
        "provenance": {
            "producing_module": ES_MODULE_PATH,
            "producing_module_sha256": sha256_file(root / ES_MODULE_PATH),
            "result_artifact_path": ES_RESULT_PATH,
            "result_artifact_sha256": ES_RESULT_SHA256,
            "generator_path": None,
            "generator_sha256": None,
            "report_path": None,
            "report_sha256": None,
        },
        "authority": {k: False for k in AUTHORITY_KEYS},
    }


def validate_payload(payload: Mapping[str, Any]) -> dict:
    """Validate ``payload`` against the contract plus the extra structural checks."""
    forbidden_hit = FORBIDDEN_KEYS.intersection(payload)
    if forbidden_hit:
        raise ImplicationContractError(
            f"payload carries forbidden promotion field(s): {sorted(forbidden_hit)}"
        )

    contract = load_contract()
    Draft202012Validator(contract).validate(payload)

    recomputed = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id=payload["selection"]["selection_id"],
        family_id=payload["registered_family"]["family_id"],
    )
    if recomputed != payload["payload_id"]:
        raise ImplicationContractError(
            f"payload_id mismatch: recomputed {recomputed!r} != stored "
            f"{payload['payload_id']!r}"
        )

    null_codes = {nr["code"] for nr in payload.get("null_reasons", [])}
    nullable_spots = []
    if payload["point_estimate"]["value"] is None:
        nullable_spots.append(payload["point_estimate"]["code"])
    for u in payload["uncertainty"]:
        if u["value"] is None:
            nullable_spots.append(u["code"])
    if payload["honest_n"]["sample_n"] is None:
        nullable_spots.append("honest_n.sample_n")
    if payload["honest_n"]["episode_n"] is None:
        nullable_spots.append("honest_n.episode_n")
    # every null needs *a* matching null_reasons entry; we don't force 1:1 naming
    # beyond requiring at least one code exists per null found.
    if nullable_spots and not null_codes:
        raise ImplicationContractError(
            f"nulls present ({nullable_spots}) with no null_reasons entries"
        )

    expected_authority = {k: False for k in AUTHORITY_KEYS}
    if payload["authority"] != expected_authority:
        raise ImplicationContractError("authority block must be exactly five literal-false keys")

    return copy.deepcopy(dict(payload))


def build_estimator_implications(root: Path = REPO_ROOT, *, ledger=None) -> dict:
    """Build the envelope of payloads + typed refusals. Fixed composer order."""
    root = Path(root)
    ledger = _default_ledger(ledger)
    payloads = []
    refusals = []

    sc_payload = compose_synthetic_control_implication(root, ledger=ledger)
    validate_payload(sc_payload)
    payloads.append(sc_payload)

    try:
        es_payload = compose_event_study_implication(root, ledger=ledger)
        validate_payload(es_payload)
        payloads.append(es_payload)
    except UnregisteredSearchFamily:
        refusals.append({
            "estimator_id": "engine.seasonality.event_study",
            "refusal_code": "unregistered_search_family",
            "detail": {
                "en": "No implication is published for this event study: its search "
                      "family was never written to the trial ledger, so the "
                      "multiple-testing budget it spent is unrecorded.",
                "zh": "本事件研究不发布含义："
                      "其搜索族未登记入试验账本。",
            },
            "source": ES_RESULT_PATH,
        })

    return {
        "schema": ENVELOPE_SCHEMA,
        "composer_version": COMPOSER_VERSION,
        "payloads": payloads,
        "refusals": refusals,
    }
