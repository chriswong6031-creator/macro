"""Deterministic, read-only projections of owner research result artifacts.

This module is deliberately an adapter, not an estimator or evaluation owner.  It
copies explicitly selected owner outputs into a closed display contract, verifies
the committed receipts that make those values inspectable, and grants no authority.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

CARD_SCHEMA = "mastermind.research_implication_card/v1"
ENVELOPE_SCHEMA = "mastermind.research_implication_cards/v1"
AUTHORITY_KEYS = (
    "forecast_authority",
    "ranking_authority",
    "gating_authority",
    "sizing_authority",
    "trading_authority",
)
QUALITY_STATES = frozenset(
    {
        "COMPLETE",
        "DIAGNOSTIC_ONLY",
        "ARTIFACT_INCOMPLETE",
        "ARTIFACT_MISSING",
        "DIAGNOSTIC_FAILED",
        "STALE",
    }
)

_CARD_KEYS = frozenset(
    {
        "schema",
        "card_id",
        "adapter_version",
        "method_family",
        "study_run_id",
        "selected_result_id",
        "question",
        "estimand",
        "method_revision",
        "code_identity",
        "population",
        "sample_n",
        "effective_n",
        "cutoff",
        "outputs",
        "uncertainty",
        "diagnostics",
        "placebos_or_counterexamples",
        "ordered_effect_path",
        "evidence_tier",
        "quality",
        "limitations",
        "exclusions",
        "missingness",
        "null_reasons",
        "source_artifacts",
        "authority",
    }
)
_SOURCE_KEYS = frozenset({"role", "path", "sha256", "as_of", "rights"})
_LOCALIZED_KEYS = frozenset({"en", "zh"})
_METRIC_KEYS = frozenset({"code", "label", "value", "unit", "source"})
_GATE_DIAGNOSTIC_KEYS = frozenset({"code", "label", "passed", "detail", "source"})
_NULL_REASON_KEYS = frozenset({"code", "reason", "detail"})
_MISSING_KEYS = frozenset({"code", "reason", "detail", "source"})
_EXCLUSION_KEYS = frozenset({"code", "count", "detail", "source"})
_FORBIDDEN_TOP_LEVEL = frozenset(
    {"rank", "score", "recommendation", "position", "size", "trade", "action"}
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_CARD_ID_RE = re.compile(r"ric_[0-9a-f]{64}")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_SC_ADAPTER_VERSION = "synthetic_control/v1"
_SC_RESULT_PATH = "data/experiments/synthetic_control_phase0_results.json"
_SC_RESULT_SHA256 = "f759bdd72de5370e597459dc0630bb1f880e8a38be9b8882a1c75f54872af1e2"
_SC_GENERATOR_PATH = "scripts/synthetic_control_phase0.py"
_SC_GENERATOR_SHA256 = (
    "bc6479968fd71bc541fdec6b1a1337a1ded9b51c0eb5cdcd1664961bc6f3ab11"
)
_SC_ESTIMATOR_PATH = "engine/synthetic_control.py"
_SC_ESTIMATOR_SHA256 = (
    "31583485f88ebd6c779787a2c0ea5cec68037669460dbb896ea3b83fd7a49a65"
)
_SC_REPORT_PATH = "research/SYNTHETIC_CONTROL_PHASE0.md"
_SC_REPORT_SHA256 = "a8d2e0023279ca241788b589af55bcedbe07117485cb3918a50d0e395a9ac587"
_SC_SELECTION = "sp_pure_adds/sc_nnls/0_5"

_HINCL2_ADAPTER_VERSION = "hincl2_event_study/v1"
_HINCL2_RESULT_PATH = "data/experiments/hincl2_event_study_results.json"
_HINCL2_RESULT_SHA256 = (
    "f415b2c4cf9b12fbc8e4dd9e3a30a51c736c93f4ffbc3f818392b4796ea81139"
)
_HINCL2_GENERATOR_PATH = "scripts/hincl2_event_study.py"
_HINCL2_GENERATOR_SHA256 = (
    "f3c6b5db4aef6c11c4e8105a163bd20ca750de98b56a16052eacd49fa0f9151d"
)
_HINCL2_PREREG_PATH = "research/HINCL2_PREREG.md"
_HINCL2_PREREG_SHA256 = (
    "cd2dbe01981e7f256f79aadac23a2952517bc71810121c05c9517ca324a5ce06"
)
_HINCL2_REPORT_PATH = "reports/hincl2-phase0.md"
_HINCL2_REPORT_SHA256 = (
    "e7391bcabb1a81856ccf3309f611c37c8a7ecc8292cda7a602051bfabfcdfa99"
)
_HINCL2_ROSTER_PATH = "data/hk_connect_roster/roster.parquet"
_HINCL2_ROSTER_SHA256 = (
    "b0816afacd9537fac58c193f511ec919bccda4fc58a5921bd1096221fa35b148"
)
_HINCL2_BENCHMARK_PATH = "data/hk/_HSI.parquet"
_HINCL2_BENCHMARK_SHA256 = (
    "184cbdcf2437c9d8de172535cd87515b020708c9c441406391faa4aa895a1e45"
)
_HINCL2_SELECTION = "announce/h20"


class CardContractError(ValueError):
    """Raised when an owner artifact cannot be projected without invention."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without changing it."""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_card_id(
    *,
    adapter_version: str,
    method_family: str,
    study_run_id: str,
    result_artifact_path: str,
    verified_result_artifact_sha256: str,
    selected_result_id: str,
) -> str:
    """Build the stable content identity specified by the frozen contract."""
    identity = {
        "adapter_version": adapter_version,
        "method_family": method_family,
        "result_artifact_path": result_artifact_path,
        "selected_result_id": selected_result_id,
        "study_run_id": study_run_id,
        "verified_result_artifact_sha256": verified_result_artifact_sha256,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"ric_{sha256(encoded).hexdigest()}"


def _localized(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def _metric(
    code: str,
    label_en: str,
    label_zh: str,
    value: Any,
    unit: str,
    source: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": _localized(label_en, label_zh),
        "value": value,
        "unit": unit,
        "source": source,
    }


def _source_artifact(
    root: Path,
    *,
    role: str,
    path: str,
    expected_sha256: str,
    as_of: str | None,
    rights: str = "REPOSITORY_INTERNAL",
) -> dict[str, Any]:
    absolute = root / path
    if not absolute.is_file():
        raise CardContractError(f"required artifact missing: {path}")
    observed = sha256_file(absolute)
    if observed != expected_sha256:
        raise CardContractError(
            f"artifact digest mismatch for {path}: expected {expected_sha256}, observed {observed}"
        )
    return {
        "role": role,
        "path": path,
        "sha256": observed,
        "as_of": as_of,
        "rights": rights,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CardContractError(
            f"cannot read owner result artifact {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CardContractError(f"owner result artifact must contain an object: {path}")
    return value


def _require_keys(
    value: dict[str, Any], expected: frozenset[str], context: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CardContractError(
            f"{context} keys are not closed: missing={missing}, extra={extra}"
        )


def _validate_localized(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        raise CardContractError(f"{context} must be a localized object")
    _require_keys(value, _LOCALIZED_KEYS, context)
    if any(
        not isinstance(value[key], str) or not value[key].strip()
        for key in _LOCALIZED_KEYS
    ):
        raise CardContractError(f"{context} translations must be non-empty strings")


def _validate_source(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        raise CardContractError(f"{context} must be an artifact object")
    _require_keys(value, _SOURCE_KEYS, context)
    if not isinstance(value["role"], str) or not value["role"]:
        raise CardContractError(f"{context}.role must be non-empty")
    if not isinstance(value["path"], str) or value["path"].startswith(("/", "../")):
        raise CardContractError(f"{context}.path must be repository-relative")
    if not isinstance(value["sha256"], str) or not _SHA256_RE.fullmatch(
        value["sha256"]
    ):
        raise CardContractError(f"{context}.sha256 must be lowercase SHA-256")
    if value["as_of"] is not None and (
        not isinstance(value["as_of"], str)
        or not _ISO_DATE_RE.fullmatch(value["as_of"])
    ):
        raise CardContractError(f"{context}.as_of must be an ISO date or null")
    if not isinstance(value["rights"], str) or not value["rights"]:
        raise CardContractError(f"{context}.rights must be non-empty")


def _validate_metric(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        raise CardContractError(f"{context} must be a metric object")
    _require_keys(value, _METRIC_KEYS, context)
    if not isinstance(value["code"], str) or not value["code"]:
        raise CardContractError(f"{context}.code must be non-empty")
    _validate_localized(value["label"], f"{context}.label")
    if value["value"] is None:
        raise CardContractError(f"{context}.value cannot be null; use null_reasons")
    if not isinstance(value["unit"], str) or not value["unit"]:
        raise CardContractError(f"{context}.unit must be non-empty")
    if not isinstance(value["source"], str) or not value["source"]:
        raise CardContractError(f"{context}.source must be non-empty")


def validate_card(card: dict[str, Any]) -> dict[str, Any]:
    """Validate and defensively copy one closed implication card."""
    if not isinstance(card, dict):
        raise CardContractError("card must be an object")
    if _FORBIDDEN_TOP_LEVEL.intersection(card):
        raise CardContractError(
            f"card contains prohibited authority/action fields: {sorted(_FORBIDDEN_TOP_LEVEL.intersection(card))}"
        )
    _require_keys(card, _CARD_KEYS, "card")
    if card["schema"] != CARD_SCHEMA:
        raise CardContractError(f"unsupported card schema: {card['schema']!r}")
    if not isinstance(card["card_id"], str) or not _CARD_ID_RE.fullmatch(
        card["card_id"]
    ):
        raise CardContractError("card_id must be ric_ followed by lowercase SHA-256")
    for field in (
        "adapter_version",
        "method_family",
        "study_run_id",
        "selected_result_id",
        "method_revision",
        "evidence_tier",
    ):
        if not isinstance(card[field], str) or not card[field]:
            raise CardContractError(f"{field} must be a non-empty string")
    _validate_localized(card["question"], "question")
    _validate_localized(card["estimand"], "estimand")
    if not isinstance(card["population"], dict) or not card["population"]:
        raise CardContractError("population must be a non-empty typed object")
    for field in ("sample_n", "effective_n"):
        if card[field] is not None and (
            isinstance(card[field], bool)
            or not isinstance(card[field], int)
            or card[field] < 0
        ):
            raise CardContractError(f"{field} must be a non-negative integer or null")
    if card["cutoff"] is not None and (
        not isinstance(card["cutoff"], str)
        or not _ISO_DATE_RE.fullmatch(card["cutoff"])
    ):
        raise CardContractError("cutoff must be an ISO date or null")
    if card["quality"] not in QUALITY_STATES:
        raise CardContractError(f"unsupported quality state: {card['quality']!r}")

    for collection in ("outputs", "uncertainty", "placebos_or_counterexamples"):
        if not isinstance(card[collection], list):
            raise CardContractError(f"{collection} must be a list")
        for index, value in enumerate(card[collection]):
            _validate_metric(value, f"{collection}[{index}]")

    if not isinstance(card["diagnostics"], list):
        raise CardContractError("diagnostics must be a list")
    failed_gate = False
    for index, diagnostic in enumerate(card["diagnostics"]):
        context = f"diagnostics[{index}]"
        if not isinstance(diagnostic, dict):
            raise CardContractError(f"{context} must be an object")
        keys = frozenset(diagnostic)
        if keys == _METRIC_KEYS:
            _validate_metric(diagnostic, context)
        elif keys == _GATE_DIAGNOSTIC_KEYS:
            if not isinstance(diagnostic["code"], str) or not diagnostic["code"]:
                raise CardContractError(f"{context}.code must be non-empty")
            _validate_localized(diagnostic["label"], f"{context}.label")
            if not isinstance(diagnostic["passed"], bool):
                raise CardContractError(f"{context}.passed must be boolean")
            _validate_localized(diagnostic["detail"], f"{context}.detail")
            if not isinstance(diagnostic["source"], str) or not diagnostic["source"]:
                raise CardContractError(f"{context}.source must be non-empty")
            failed_gate = failed_gate or not diagnostic["passed"]
        else:
            raise CardContractError(
                f"{context} does not match a closed diagnostic shape"
            )
    if card["quality"] == "DIAGNOSTIC_FAILED" and not failed_gate:
        raise CardContractError("DIAGNOSTIC_FAILED requires an explicit failed gate")
    if failed_gate and card["quality"] != "DIAGNOSTIC_FAILED":
        raise CardContractError(
            "an explicit failed diagnostic requires DIAGNOSTIC_FAILED quality"
        )

    for collection, keys in (
        ("null_reasons", _NULL_REASON_KEYS),
        ("missingness", _MISSING_KEYS),
        ("exclusions", _EXCLUSION_KEYS),
    ):
        if not isinstance(card[collection], list):
            raise CardContractError(f"{collection} must be a list")
        for index, item in enumerate(card[collection]):
            context = f"{collection}[{index}]"
            if not isinstance(item, dict):
                raise CardContractError(f"{context} must be an object")
            _require_keys(item, keys, context)
            if not isinstance(item["code"], str) or not item["code"]:
                raise CardContractError(f"{context}.code must be non-empty")
            _validate_localized(item["detail"], f"{context}.detail")
    null_codes = {item["code"] for item in card["null_reasons"]}
    for field in ("sample_n", "effective_n", "cutoff"):
        if card[field] is None and field not in null_codes:
            raise CardContractError(
                f"null {field} requires a matching null_reasons entry"
            )
    if card["missingness"] and card["quality"] not in {
        "ARTIFACT_INCOMPLETE",
        "ARTIFACT_MISSING",
    }:
        raise CardContractError(
            "typed missingness requires artifact-incomplete or missing quality"
        )

    if not isinstance(card["limitations"], list) or not card["limitations"]:
        raise CardContractError("limitations must be a non-empty list")
    for index, limitation in enumerate(card["limitations"]):
        _validate_localized(limitation, f"limitations[{index}]")

    for collection in ("code_identity", "source_artifacts"):
        if not isinstance(card[collection], list) or not card[collection]:
            raise CardContractError(f"{collection} must be a non-empty list")
        for index, artifact in enumerate(card[collection]):
            _validate_source(artifact, f"{collection}[{index}]")

    if not isinstance(card["authority"], dict):
        raise CardContractError("authority must be an object")
    _require_keys(card["authority"], frozenset(AUTHORITY_KEYS), "authority")
    if any(card["authority"][key] is not False for key in AUTHORITY_KEYS):
        raise CardContractError("all authority flags must be literal false")

    effect_path = card["ordered_effect_path"]
    if effect_path is not None:
        if not isinstance(effect_path, dict):
            raise CardContractError("ordered_effect_path must be an object or null")
        expected_path_keys = frozenset(
            {"owner_supplied", "x_unit", "y_unit", "points", "source"}
        )
        _require_keys(effect_path, expected_path_keys, "ordered_effect_path")
        if effect_path["owner_supplied"] is not True:
            raise CardContractError("ordered_effect_path requires owner_supplied=true")
        if not isinstance(effect_path["points"], list) or not effect_path["points"]:
            raise CardContractError("ordered_effect_path.points must be non-empty")
        horizons = []
        for index, point in enumerate(effect_path["points"]):
            expected_point_keys = frozenset({"horizon", "value", "n"})
            if not isinstance(point, dict):
                raise CardContractError(
                    f"ordered_effect_path.points[{index}] must be an object"
                )
            _require_keys(
                point, expected_point_keys, f"ordered_effect_path.points[{index}]"
            )
            if isinstance(point["horizon"], bool) or not isinstance(
                point["horizon"], int
            ):
                raise CardContractError("ordered effect horizons must be integers")
            horizons.append(point["horizon"])
        if horizons != sorted(horizons) or len(set(horizons)) != len(horizons):
            raise CardContractError(
                "ordered effect horizons must be unique and increasing"
            )

    result_receipts = [
        item for item in card["source_artifacts"] if item["role"] == "result"
    ]
    if len(result_receipts) != 1:
        raise CardContractError("card requires exactly one result artifact receipt")
    result = result_receipts[0]
    expected_id = compute_card_id(
        adapter_version=card["adapter_version"],
        method_family=card["method_family"],
        study_run_id=card["study_run_id"],
        result_artifact_path=result["path"],
        verified_result_artifact_sha256=result["sha256"],
        selected_result_id=card["selected_result_id"],
    )
    if card["card_id"] != expected_id:
        raise CardContractError(
            f"card_id mismatch: expected {expected_id}, observed {card['card_id']}"
        )
    return deepcopy(card)


def adapt_synthetic_control(root: Path) -> dict[str, Any]:
    """Project the frozen synthetic-control diagnostic result."""
    root = Path(root)
    result_receipt = _source_artifact(
        root,
        role="result",
        path=_SC_RESULT_PATH,
        expected_sha256=_SC_RESULT_SHA256,
        as_of="2026-07-02",
    )
    generator_receipt = _source_artifact(
        root,
        role="generator",
        path=_SC_GENERATOR_PATH,
        expected_sha256=_SC_GENERATOR_SHA256,
        as_of="2026-08-06",
    )
    estimator_receipt = _source_artifact(
        root,
        role="estimator",
        path=_SC_ESTIMATOR_PATH,
        expected_sha256=_SC_ESTIMATOR_SHA256,
        as_of="2026-08-06",
    )
    report_receipt = _source_artifact(
        root,
        role="report",
        path=_SC_REPORT_PATH,
        expected_sha256=_SC_REPORT_SHA256,
        as_of="2026-08-06",
    )
    artifact = _read_json(root / _SC_RESULT_PATH)
    try:
        family = artifact["families"]["sp_pure_adds"]
        selected = family["arms"]["sc_nnls"]["real"]["0_5"]
        placebo = family["arms"]["sc_nnls"]["placebo"]["0_5"]
        gate_eval = artifact["gate_eval"]
        gates = gate_eval["gates"]
        reasons = gate_eval["reasons"]
        panel = artifact["panel"]
    except (KeyError, TypeError) as exc:
        raise CardContractError(
            f"frozen synthetic-control result {_SC_SELECTION!r} is missing: {exc}"
        ) from exc
    if artifact.get("study") != "synthetic_control_phase0":
        raise CardContractError("synthetic-control study identity drifted")
    if artifact.get("run_date") != "2026-08-06":
        raise CardContractError("synthetic-control run date drifted")
    if panel.get("calendar") != ["2021-07-06", "2026-07-02"]:
        raise CardContractError("synthetic-control panel cutoff or start drifted")
    if gate_eval.get("verdict") != "ESTIMATOR_BIASED":
        raise CardContractError("synthetic-control diagnostic verdict drifted")
    expected_gates = (
        "PC1_positive_control_survives",
        "PC2_estimators_unbiased",
        "PC3_sc_not_noisier",
        "F1_falsifier_holds",
    )
    if tuple(gates) != expected_gates:
        raise CardContractError("synthetic-control gate inventory or ordering drifted")
    required_selected = frozenset(
        {"n", "n_months", "mean", "t", "p", "hit_rate", "ticker_cluster_t"}
    )
    missing_selected = sorted(required_selected - frozenset(selected))
    if missing_selected:
        raise CardContractError(
            f"frozen synthetic-control result {_SC_SELECTION!r} is missing required fields: "
            f"{missing_selected}"
        )
    gate_copy = {
        "PC1_positive_control_survives": {
            "label": _localized("PC1 positive control survives", "PC1 正向对照通过"),
            "detail_zh": (
                "sc_nnls 标普纯新增 CAAR[0,5]=3.015%（事件加权）/4.907%（月度加权），"
                "月度 Newey-West t=8.291（两者须大于0且 t>2）。"
            ),
        },
        "PC2_estimators_unbiased": {
            "label": _localized("PC2 estimators are unbiased", "PC2 估计器无偏"),
            "detail_zh": (
                "sp_pure_adds/matched_k 均值=0.190%、t=4.316，失败；"
                "sp_pure_adds/sc_nnls 均值=0.197%、t=4.535，失败；"
                "phase3_start/matched_k 均值=0.143%、t=15.429，失败；"
                "phase3_start/sc_nnls 均值=0.137%、t=15.431，失败"
                "（两个家族都要求 |均值|<0.3% 且 |t|<2）。"
            ),
        },
        "PC3_sc_not_noisier": {
            "label": _localized(
                "PC3 synthetic control is not noisier", "PC3 合成控制噪声未增加"
            ),
            "detail_zh": (
                "sc_nnls 安慰剂标准差=0.614%，SPY-CAR 安慰剂标准差=0.650%"
                "（合成控制须不高于现有方法）。"
            ),
        },
        "F1_falsifier_holds": {
            "label": _localized("F1 falsifier holds", "F1 证伪条件成立"),
            "detail_zh": (
                "phase3 sc_nnls CAAR[0,20]=0.496%，月度 Newey-West t=1.662，"
                "经验 p=0.731（要求 |t|<2 且 p>0.05）。"
            ),
        },
    }

    study_run_id = "synthetic_control_phase0@2026-08-06"
    card: dict[str, Any] = {
        "schema": CARD_SCHEMA,
        "card_id": compute_card_id(
            adapter_version=_SC_ADAPTER_VERSION,
            method_family="synthetic_control",
            study_run_id=study_run_id,
            result_artifact_path=_SC_RESULT_PATH,
            verified_result_artifact_sha256=result_receipt["sha256"],
            selected_result_id=_SC_SELECTION,
        ),
        "adapter_version": _SC_ADAPTER_VERSION,
        "method_family": "synthetic_control",
        "study_run_id": study_run_id,
        "selected_result_id": _SC_SELECTION,
        "question": _localized(
            "For pure S&P 500 additions, what did the frozen synthetic-control diagnostic estimate over days 0–5?",
            "对于纯标普500新增样本，冻结的合成控制诊断在第0至5日估计了什么？",
        ),
        "estimand": _localized(
            "Event-weighted five-day cumulative abnormal return relative to the non-negative synthetic donor fit.",
            "相对于非负合成捐助组合拟合的事件加权五日累计异常收益。",
        ),
        "method_revision": f"sha256:{_SC_ESTIMATOR_SHA256}",
        "code_identity": [generator_receipt, estimator_receipt],
        "population": {
            "family": "sp_pure_adds",
            "panel_calendar_start": panel["calendar"][0],
            "panel_calendar_end": panel["calendar"][1],
            "panel_names": panel["names"],
            "events_total": family["n_events"],
            "events_fitted": family["n_fitted"],
            "events_dropped_unfitted": family["n_dropped_unfitted"],
            "ticker_count": family["n_tickers"],
            "mean_donor_pool": family["mean_donor_pool"],
        },
        "sample_n": selected["n"],
        "effective_n": None,
        "cutoff": panel["calendar"][1],
        "outputs": [
            _metric(
                "cumulative_abnormal_return",
                "Five-day cumulative abnormal return",
                "五日累计异常收益",
                selected["mean"],
                "return_fraction",
                "families.sp_pure_adds.arms.sc_nnls.real.0_5.mean",
            ),
            _metric(
                "monthly_newey_west_t",
                "Monthly Newey-West t statistic",
                "月度 Newey-West t 统计量",
                selected["t"],
                "t_statistic",
                "families.sp_pure_adds.arms.sc_nnls.real.0_5.t",
            ),
            _metric(
                "monthly_newey_west_p",
                "Monthly Newey-West p value",
                "月度 Newey-West p 值",
                selected["p"],
                "probability",
                "families.sp_pure_adds.arms.sc_nnls.real.0_5.p",
            ),
            _metric(
                "monthly_observation_count",
                "Monthly observation count",
                "月度观测数",
                selected["n_months"],
                "months",
                "families.sp_pure_adds.arms.sc_nnls.real.0_5.n_months",
            ),
            _metric(
                "hit_rate",
                "Positive abnormal-return share",
                "异常收益为正的占比",
                selected["hit_rate"],
                "fraction",
                "families.sp_pure_adds.arms.sc_nnls.real.0_5.hit_rate",
            ),
        ],
        "uncertainty": [],
        "diagnostics": [
            {
                "code": code,
                "label": gate_copy[code]["label"],
                "passed": gates[code],
                "detail": _localized(
                    reasons[code.split("_")[0]], gate_copy[code]["detail_zh"]
                ),
                "source": f"gate_eval.gates.{code}",
            }
            for code in expected_gates
        ],
        "placebos_or_counterexamples": [
            _metric(
                "placebo_mean",
                "Placebo mean",
                "安慰剂均值",
                placebo["placebo_mean"],
                "return_fraction",
                "families.sp_pure_adds.arms.sc_nnls.placebo.0_5.placebo_mean",
            ),
            _metric(
                "placebo_standard_deviation",
                "Placebo standard deviation",
                "安慰剂标准差",
                placebo["placebo_sd"],
                "return_fraction",
                "families.sp_pure_adds.arms.sc_nnls.placebo.0_5.placebo_sd",
            ),
            _metric(
                "placebo_empirical_p",
                "Placebo empirical p value",
                "安慰剂经验 p 值",
                placebo["empirical_p"],
                "probability",
                "families.sp_pure_adds.arms.sc_nnls.placebo.0_5.empirical_p",
            ),
            _metric(
                "placebo_draw_count",
                "Placebo draw count",
                "安慰剂抽样次数",
                placebo["n_draws"],
                "draws",
                "families.sp_pure_adds.arms.sc_nnls.placebo.0_5.n_draws",
            ),
        ],
        "ordered_effect_path": None,
        "evidence_tier": artifact["tier"],
        "quality": "DIAGNOSTIC_FAILED",
        "limitations": [
            _localized(
                "PC-2 failed: the placebo mean was materially biased, so this estimator is not cleared for causal or trading use.",
                "PC-2 未通过：安慰剂均值存在显著偏差，因此该估计器未获准用于因果判断或交易。",
            ),
            _localized(
                "No confidence interval or independent effective sample size is reported for this selected result.",
                "该选定结果未报告置信区间或独立有效样本量。",
            ),
        ],
        "exclusions": [
            {
                "code": "treated_pre_window_gap",
                "count": family["drop_reasons"]["treated_pre_window_gap"],
                "detail": _localized(
                    "Events dropped because the treated series lacked the required pre-window.",
                    "因处理序列缺少所需前窗而剔除的事件。",
                ),
                "source": "families.sp_pure_adds.drop_reasons.treated_pre_window_gap",
            }
        ],
        "missingness": [],
        "null_reasons": [
            {
                "code": "effective_n",
                "reason": "NOT_REPORTED",
                "detail": _localized(
                    "The owner artifact reports fitted events and months but does not define an independent effective N.",
                    "所有者工件报告了拟合事件数和月份数，但未定义独立有效样本量。",
                ),
            },
            {
                "code": "uncertainty_interval",
                "reason": "NOT_REPORTED",
                "detail": _localized(
                    "The selected owner result does not report a confidence interval.",
                    "选定的所有者结果未报告置信区间。",
                ),
            },
            {
                "code": "ticker_cluster_t",
                "reason": "NOT_REPORTED",
                "detail": _localized(
                    "The owner artifact records ticker_cluster_t as null.",
                    "所有者工件将 ticker_cluster_t 记录为空。",
                ),
            },
        ],
        "source_artifacts": [result_receipt, report_receipt],
        "authority": {key: False for key in AUTHORITY_KEYS},
    }
    return validate_card(card)


def adapt_hincl2_event_study(root: Path) -> dict[str, Any]:
    """Project the frozen HINCL2 inclusion event-study result."""
    root = Path(root)
    result_receipt = _source_artifact(
        root,
        role="result",
        path=_HINCL2_RESULT_PATH,
        expected_sha256=_HINCL2_RESULT_SHA256,
        as_of="2026-07-03",
    )
    generator_receipt = _source_artifact(
        root,
        role="generator",
        path=_HINCL2_GENERATOR_PATH,
        expected_sha256=_HINCL2_GENERATOR_SHA256,
        as_of="2026-07-03",
    )
    prereg_receipt = _source_artifact(
        root,
        role="preregistration",
        path=_HINCL2_PREREG_PATH,
        expected_sha256=_HINCL2_PREREG_SHA256,
        as_of="2026-07-03",
    )
    report_receipt = _source_artifact(
        root,
        role="report",
        path=_HINCL2_REPORT_PATH,
        expected_sha256=_HINCL2_REPORT_SHA256,
        as_of="2026-07-03",
    )
    roster_receipt = _source_artifact(
        root,
        role="event_roster",
        path=_HINCL2_ROSTER_PATH,
        expected_sha256=_HINCL2_ROSTER_SHA256,
        as_of=None,
    )
    benchmark_receipt = _source_artifact(
        root,
        role="benchmark",
        path=_HINCL2_BENCHMARK_PATH,
        expected_sha256=_HINCL2_BENCHMARK_SHA256,
        as_of="2026-07-03",
    )
    artifact = _read_json(root / _HINCL2_RESULT_PATH)
    try:
        selected = artifact["trials"]["announce"]["h20"]
        hac = selected["hac"]
        dsr = selected["dsr"]
        fdr = artifact["bh_fdr"]["announce"]
        curve = artifact["event_curve_announce"]
    except (KeyError, TypeError) as exc:
        raise CardContractError(
            f"frozen event-study result {_HINCL2_SELECTION!r} is missing: {exc}"
        ) from exc
    if (
        artifact.get("panel_end") != "2026-07-03"
        or artifact.get("hsi_end") != "2026-07-03"
    ):
        raise CardContractError("HINCL2 panel or benchmark cutoff drifted")
    if artifact.get("primary_horizon") != 20:
        raise CardContractError("HINCL2 primary horizon drifted")
    if selected.get("anchor") != "announce" or selected.get("h") != 20:
        raise CardContractError("HINCL2 selected result identity drifted")
    if hac.get("n") != selected.get("episode_k"):
        raise CardContractError(
            "HINCL2 HAC N no longer matches the recorded episode count"
        )
    if dsr.get("n_trials") != artifact.get("n_trials_dsr"):
        raise CardContractError("HINCL2 DSR trial count drifted")
    try:
        ordered_points = [
            {"horizon": int(horizon), "value": pair[0], "n": pair[1]}
            for horizon, pair in sorted(curve.items(), key=lambda item: int(item[0]))
        ]
    except (TypeError, ValueError, IndexError) as exc:
        raise CardContractError(f"HINCL2 event curve is malformed: {exc}") from exc

    study_run_id = "hincl2_event_study@2026-07-03"
    card: dict[str, Any] = {
        "schema": CARD_SCHEMA,
        "card_id": compute_card_id(
            adapter_version=_HINCL2_ADAPTER_VERSION,
            method_family="event_study",
            study_run_id=study_run_id,
            result_artifact_path=_HINCL2_RESULT_PATH,
            verified_result_artifact_sha256=result_receipt["sha256"],
            selected_result_id=_HINCL2_SELECTION,
        ),
        "adapter_version": _HINCL2_ADAPTER_VERSION,
        "method_family": "event_study",
        "study_run_id": study_run_id,
        "selected_result_id": _HINCL2_SELECTION,
        "question": _localized(
            "What return pattern was recorded around Stock Connect inclusion announcements in the frozen HINCL2 event-study run?",
            "冻结的 HINCL2 事件研究记录了互联互通纳入公告前后怎样的收益路径？",
        ),
        "estimand": _localized(
            "Descriptive mean cumulative abnormal return through 20 trading days after the announcement anchor.",
            "公告锚点后20个交易日内的描述性平均累计异常收益。",
        ),
        "method_revision": f"sha256:{_HINCL2_GENERATOR_SHA256}",
        "code_identity": [generator_receipt],
        "population": {
            "event_family": "stock_connect_inclusion",
            "anchor": selected["anchor"],
            "primary_horizon_trading_days": selected["h"],
            "panel_names": artifact["panel_names"],
            "roster_add_events": artifact["roster_add_events"],
            "roster_add_tickers": artifact["roster_add_tickers"],
            "coverage_add_tickers": artifact["coverage_add_tickers"],
            "n_add_tickers_total": selected["n_add_tickers_total"],
            "n_studiable_tickers": selected["n_studiable_tickers"],
        },
        "sample_n": selected["n_events"],
        "effective_n": selected["episode_k"],
        "cutoff": artifact["panel_end"],
        "outputs": [
            _metric(
                "mean_cumulative_abnormal_return",
                "Mean cumulative abnormal return",
                "平均累计异常收益",
                selected["mean_car"],
                "return_fraction",
                "trials.announce.h20.mean_car",
            ),
            _metric(
                "event_count",
                "Event observations",
                "事件观测数",
                selected["n_events"],
                "events",
                "trials.announce.h20.n_events",
            ),
            _metric(
                "episode_count",
                "Distinct episodes",
                "独立事件期数",
                selected["episode_k"],
                "episodes",
                "trials.announce.h20.episode_k",
            ),
        ],
        "uncertainty": [
            _metric(
                "hac_mean",
                "HAC mean",
                "HAC 均值",
                hac["mean"],
                "return_fraction",
                "trials.announce.h20.hac.mean",
            ),
            _metric(
                "hac_standard_error",
                "HAC standard error",
                "HAC 标准误",
                hac["se"],
                "return_fraction",
                "trials.announce.h20.hac.se",
            ),
            _metric(
                "hac_t_statistic",
                "HAC t statistic",
                "HAC t 统计量",
                hac["t"],
                "t_statistic",
                "trials.announce.h20.hac.t",
            ),
            _metric(
                "hac_p_value",
                "HAC p value",
                "HAC p 值",
                hac["p"],
                "probability",
                "trials.announce.h20.hac.p",
            ),
            _metric(
                "mean_ci90",
                "90% owner interval",
                "90% 所有者区间",
                selected["mean_ci90"],
                "return_fraction_interval",
                "trials.announce.h20.mean_ci90",
            ),
        ],
        "diagnostics": [
            _metric(
                "deflated_sharpe_ratio",
                "Deflated Sharpe ratio",
                "折减夏普比率",
                dsr["dsr"],
                "ratio",
                "trials.announce.h20.dsr.dsr",
            ),
            _metric(
                "bh_fdr_announce_reject",
                "BH-FDR rejection",
                "BH-FDR 拒绝结果",
                fdr["reject"],
                "boolean",
                "bh_fdr.announce.reject",
            ),
            _metric(
                "bh_fdr_announce_q",
                "BH-FDR q value",
                "BH-FDR q 值",
                fdr["q"],
                "probability",
                "bh_fdr.announce.q",
            ),
            _metric(
                "panel_coverage_fraction",
                "Panel coverage",
                "面板覆盖率",
                artifact["coverage_frac"],
                "fraction",
                "coverage_frac",
            ),
            _metric(
                "imputed_zero_count",
                "Zero-imputed non-studiable tickers",
                "零值填补的不可研究股票数",
                selected["n_imputed_zero"],
                "tickers",
                "trials.announce.h20.n_imputed_zero",
            ),
        ],
        "placebos_or_counterexamples": [
            _metric(
                "pre_event_run_mean",
                "Pre-event run mean",
                "事件前走势均值",
                selected["pre_run_mean"],
                "return_fraction",
                "trials.announce.h20.pre_run_mean",
            ),
            _metric(
                "survivorship_lower_bound_mean",
                "Survivorship lower-bound mean",
                "幸存者偏差下界均值",
                selected["surv_lb_mean"],
                "return_fraction",
                "trials.announce.h20.surv_lb_mean",
            ),
            _metric(
                "split_half_same_sign",
                "Split-half sign agreement",
                "分半符号一致",
                selected["split_half"]["same_sign"],
                "boolean",
                "trials.announce.h20.split_half.same_sign",
            ),
        ],
        "ordered_effect_path": {
            "owner_supplied": True,
            "x_unit": "trading_day_relative_to_announcement",
            "y_unit": "cumulative_abnormal_return",
            "points": ordered_points,
            "source": "event_curve_announce",
        },
        "evidence_tier": "DIAGNOSTIC",
        "quality": "ARTIFACT_INCOMPLETE",
        "limitations": [
            _localized(
                "The result is descriptive and does not identify a causal treatment effect.",
                "该结果属于描述性结果，并未识别因果处理效应。",
            ),
            _localized(
                "A gitignored absolute hk_stocks_ext input was used without an immutable digest or rights receipt.",
                "运行使用了被 Git 忽略的绝对路径 hk_stocks_ext 输入，但没有不可变摘要或权利凭据。",
            ),
            _localized(
                "The pre-registered run concluded NO-GO and is not wired to a signal or trading route.",
                "预注册运行结论为 NO-GO，且未连接到信号或交易路径。",
            ),
        ],
        "exclusions": [
            {
                "code": "non_studiable_tickers_imputed_zero",
                "count": selected["n_imputed_zero"],
                "detail": _localized(
                    "The owner artifact reports these inclusion tickers as zero-imputed in the survivorship lower-bound diagnostic.",
                    "所有者工件报告这些纳入股票在幸存者偏差下界诊断中以零值填补。",
                ),
                "source": "trials.announce.h20.n_imputed_zero",
            }
        ],
        "missingness": [
            {
                "code": "hk_stocks_ext_digest",
                "reason": "INPUT_DIGEST_MISSING",
                "detail": _localized(
                    "The absolute gitignored hk_stocks_ext input has no immutable digest receipt in the committed run artifacts.",
                    "已提交的运行工件未包含绝对路径且被 Git 忽略的 hk_stocks_ext 输入的不可变摘要凭据。",
                ),
                "source": "scripts/hincl2_event_study.py:EXT_ROOT",
            },
            {
                "code": "hk_stocks_ext_rights",
                "reason": "RIGHTS_RECEIPT_MISSING",
                "detail": _localized(
                    "The committed run artifacts do not contain a rights receipt for hk_stocks_ext.",
                    "已提交的运行工件未包含 hk_stocks_ext 的权利凭据。",
                ),
                "source": "research/HINCL2_PREREG.md",
            },
        ],
        "null_reasons": [],
        "source_artifacts": [
            result_receipt,
            roster_receipt,
            benchmark_receipt,
            prereg_receipt,
            report_receipt,
        ],
        "authority": {key: False for key in AUTHORITY_KEYS},
    }
    return validate_card(card)


def build_research_implication_cards(root: Path) -> dict[str, Any]:
    """Return the deterministic envelope in configured, non-ranking method order."""
    cards = [adapt_synthetic_control(root), adapt_hincl2_event_study(root)]
    return {"schema": ENVELOPE_SCHEMA, "cards": cards}
