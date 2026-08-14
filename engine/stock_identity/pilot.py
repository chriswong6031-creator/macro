"""Sealed W1 pilot history and the append-only W1-A1 miner overlay.

``scripts.stock_identity_build_atlas.MINER_PROBE`` is deliberately left unchanged:
it is the recipe that produced the sealed PR #5612 artifacts.  Current analytical
consumers must use :func:`current_miner_probe`, which refuses to return the amended
roster unless the governing receipt is present and internally coherent.

The overlay changes interpretation, not measurements.  GOLD remains in the sealed
W1 files as Gold.com/A-Mark dealer behavior; B is the design-touched Barrick addendum.
Neither row has ranking, sizing, gating, signal, or escalation authority.
"""
from __future__ import annotations

import json
import hashlib
import re
from datetime import date
from pathlib import Path

from engine.stock_identity.authority import is_zero_authority

AMENDMENT_ID = "SI-W1-A1-GOLD-WRONG-ISSUER"
W1A1_INITIAL_REGISTRATION_COMMIT = (
    "adb6ae2ed744e2f76574cb89b0e106ea402e576a"
)
W1A1_PREREQUISITE_SOURCE_HEADS = {
    "pr_5613": "b8601a0dc318c20ebf0b3ace198c9b3b1a735624",
    "pr_5632": "e93ad5343606bda152fd00902f2a6651acffa5d5",
}
W1A1_PREREQUISITE_MERGES = {
    "pr_5613": "666a2efd7aa69881b7d56e2712cc283638ef7b98",
    "pr_5632": "6d04e9b3100af7afaf834ceb2c9c307a48808f0b",
}

W1A1_REGISTERED_OUTPUT_PATHS: tuple[str, ...] = (
    "data/stock_identity/amendments/w1a1_gold_wrong_issuer.json",
    "data/stock_identity/fingerprints/amendments/w1a1_b_fingerprint_v0.parquet",
    "data/stock_identity/state/amendments/w1a1_b_state_daily.parquet",
    "data/stock_identity/episodes/amendments/w1a1_b_episode_catalog_v0.parquet",
    "data/stock_identity/episodes/amendments/B.json",
    "research/stock_identity/dossiers/B.md",
    "research/stock_identity/dossiers/B.svg",
)
W1A1_GENERATED_OUTPUT_PATHS: tuple[str, ...] = W1A1_REGISTERED_OUTPUT_PATHS[1:]
W1A1_GOLD_DISCLOSURE_PATH = "research/stock_identity/dossiers/GOLD.md"
W1A1_GOLD_MD_BEFORE_SHA256 = (
    "2675b5be60cc09a37324e697bb62c20679b8f21cfe4d268f5082ce0730861558"
)
W1A1_GOLD_ANNOTATION_BEGIN = "<!-- SI-W1-A1-GOLD-WRONG-ISSUER:BEGIN -->"
W1A1_GOLD_ANNOTATION_END = "<!-- SI-W1-A1-GOLD-WRONG-ISSUER:END -->"

W1_SEALED_MINER_PROBE: tuple[str, ...] = (
    "NEM",
    "GOLD",
    "AEM",
    "PAAS",
    "WPM",
    "AG",
)

W1A1_EFFECTIVE_MINER_PROBE: tuple[str, ...] = (
    "NEM",
    "AEM",
    "PAAS",
    "WPM",
    "AG",
    "B",
)

W1A1_RECEIPT_SCHEMA = "stock_identity.w1_amendment.v1"
W1A1_ASOF = "2026-08-13"
W1A1_IDENTITY_RECEIPT = {
    "GOLD": {
        "issuer": "Gold.com, Inc. (fka A-Mark Precious Metals)",
        "edgar_cik": "1591588",
        "role": "bullion dealer instrument; frozen W1 miner interpretation withdrawn",
        "effective_symbol_date": "2025-12-02",
        "store_first_print": "2014-03-17",
    },
    "B": {
        "issuer": "Barrick Mining Corporation",
        "edgar_cik": "756894",
        "role": "design-touched W1-A1 miner-probe addendum",
        "effective_symbol_date": "2025-05-09",
        "curated_tape_floor": "2014-01-02",
    },
}
W1A1_PARTITION_TREATMENT = {
    "B_design_touched": True,
    "B_absent_from_w1_universe": True,
    "B_absent_from_w1_pilot": True,
    "B_excluded_from_blind": True,
    "B_excluded_from_calibration": True,
    "B_excluded_from_future_blind_extension": True,
    "B_excluded_from_confirmatory_grading": True,
}
W1A1_PROCEDURAL_DEVIATION = {
    "status": "DISCLOSED_PRE_REGISTRATION_IMPLEMENTATION_EXPOSURE",
    "write_scope": "no repository artifacts written; independent git status/diff clean",
    "observed_scope": (
        "B tape shape/edge rows plus in-memory state, episode, fingerprint, "
        "percentile and instability outputs were printed before registration"
    ),
    "consequence": (
        "observations cannot choose outputs, thresholds, constants, acceptance "
        "rules or interpretations; B is permanently design-touched"
    ),
}
W1A1_TRIAL_BUDGET = (
    "not applicable: one deterministic descriptive configuration, no sweep, "
    "outcome attachment, graded question, or result-contingent choice"
)
W1A1_REFERENCE_SHA256 = {
    "raw_all.parquet": "ca9c5e5ac78c9a1913a145f8763a2bea84cd80a4a10d6fd2f4d095377f021a08",
    "univ_ew.parquet": "80f5ab3c80aa44da26e17ca58d8a14db930e5d3c03e45031c4c9505c3edba70a",
    "strata.parquet": "67ae54370dfd2279583f99a16475865796542b786cd983a1e94da27edb33f769",
}
W1A1_SEALED_W1_SHA256 = {
    "data/stock_identity/partition/partition_manifest_v1.json":
        "b1f82f842350e39ac7a73214fd8ebd58b175b52fdf42b3a0fb5a2d03143a5d48",
    "data/stock_identity/partition/universe_snapshot_v1.parquet":
        "9f22807e7cb6ba570f1963de945b7be77461a1788608754e25db6235f4fe3730",
    "data/stock_identity/constants/si_constants_v1.json":
        "276d4ad267ab8711942943e306e844bfdff1f17a051bd17a9d460c1e428fc648",
    "data/stock_identity/fingerprints/fingerprint_spec.json":
        "bbefcd5b72915435acb8714d7892b79e010cb49d394b3222d89575c7b022dee0",
    "data/stock_identity/fingerprints/pilot_fingerprint_v0.parquet":
        "2bdef8763b0c73a6df3f27e8307246887b7b9dc982f66331ba4d96ff09d72ba3",
    "data/stock_identity/state/pilot_state_daily.parquet":
        "e2c43f8761431c62506311e61fa387c70433f82bde8143b564fdf87da7ee485e",
    "data/stock_identity/episodes/pilot_episode_catalog_v0.parquet":
        "3216f6cbbf539584dba31caf30e09b6e76e0297ca34698fcb0235cf6e0d6bc0f",
    "data/stock_identity/episodes/pilot/GOLD.json":
        "be8a1d053c6fc9f639017abb4cf7f3063e7bde8229d9a1622dedd38a02ff16d1",
    "data/stock_identity/census/coverage_census_v0.parquet":
        "d64d37c0ab8e0729aa732f2a68a183dd08e0ca3336e9a4a71975772f28c0b4cd",
    "data/stock_identity/census/coverage_census_v0.md":
        "cf1a818749802bf6143656cfc06efa8ad95d3e87570a011726766c461bf371bb",
    W1A1_GOLD_DISCLOSURE_PATH: W1A1_GOLD_MD_BEFORE_SHA256,
    "research/stock_identity/dossiers/GOLD.svg":
        "e4e6466f2b4535b97d2fae4eb3eb7e39c1a40600343d955f0e0fe843d7df49db",
}

RECEIPT_RELATIVE_PATH = Path(
    W1A1_REGISTERED_OUTPUT_PATHS[0]
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _contained_path(root: Path, relative: str, *, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label}: path must be repository-relative and contained")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label}: path escapes the repository")
    return resolved


def current_miner_probe(repo_root: str | Path | None = None) -> tuple[str, ...]:
    """Return the effective W1-A1 roster after validating its governing receipt.

    Fail closed when the amendment is absent or contradictory.  Falling back to the
    sealed tuple would silently reintroduce the dealer under a miner label, exactly
    the defect this overlay exists to prevent.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    path = root / RECEIPT_RELATIVE_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"missing {path}; the current miner roster is unavailable until W1-A1 lands"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != W1A1_RECEIPT_SCHEMA:
        raise ValueError(f"{path}: unexpected receipt schema")
    if payload.get("amendment_id") != AMENDMENT_ID:
        raise ValueError(f"{path}: unexpected amendment_id")
    if payload.get("asof") != W1A1_ASOF:
        raise ValueError(f"{path}: amendment asof drifted")
    if not isinstance(payload.get("pull_request"), int) or payload["pull_request"] <= 0:
        raise ValueError(f"{path}: pull_request receipt is malformed")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("registration_commit") or "")):
        raise ValueError(f"{path}: registration commit receipt is malformed")
    if payload.get("initial_registration_commit") != W1A1_INITIAL_REGISTRATION_COMMIT:
        raise ValueError(f"{path}: initial registration commit drifted")
    if not is_zero_authority(payload):
        raise ValueError(f"{path}: amendment authority is not all-false")
    if payload.get("identity_receipt") != W1A1_IDENTITY_RECEIPT:
        raise ValueError(f"{path}: issuer identity receipt drifted")
    if payload.get("partition_treatment") != W1A1_PARTITION_TREATMENT:
        raise ValueError(f"{path}: B partition quarantine drifted")

    if payload.get("prerequisite_source_heads") != W1A1_PREREQUISITE_SOURCE_HEADS:
        raise ValueError(f"{path}: prerequisite source-head closure drifted")
    if payload.get("prerequisite_merges") != W1A1_PREREQUISITE_MERGES:
        raise ValueError(f"{path}: prerequisite merge closure drifted")

    if payload.get("procedural_deviation") != W1A1_PROCEDURAL_DEVIATION:
        raise ValueError(f"{path}: preregistration deviation disclosure drifted")
    if payload.get("trial_budget") != W1A1_TRIAL_BUDGET:
        raise ValueError(f"{path}: no-sweep trial-budget receipt drifted")

    rank = payload.get("rank_context") or {}
    rank_expected = {
        "frozen_reference_rows": 2780,
        "hypothetical_joint_rows": 2781,
        "only_B_persisted": True,
        "w1_percentiles_rewritten": False,
        "univ_ew_recomputed": False,
        "reference_sha256": W1A1_REFERENCE_SHA256,
    }
    if any(rank.get(key) != value for key, value in rank_expected.items()):
        raise ValueError(f"{path}: frozen rank context drifted")
    if "GOLD dealer context" not in str(rank.get("dealer_context_disclosure") or ""):
        raise ValueError(f"{path}: dealer rank-context disclosure is absent")

    price = payload.get("price_input") or {}
    stable_price = {
        "path": "data/baskets/ohlcv/B.parquet",
        "price_plane_id": "baskets_ohlcv_v1",
        "prefix_asof": W1A1_ASOF,
        "prefix_sha256": "6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db",
        "seed_container_sha256": "dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f",
        "rows_used": 3172,
        "first_date": "2014-01-02",
        "last_date_used": W1A1_ASOF,
    }
    if any(price.get(key) != value for key, value in stable_price.items()):
        raise ValueError(f"{path}: B price-input receipt drifted")
    if not re.fullmatch(r"[0-9a-f]{64}", str(price.get("file_sha256_at_run") or "")):
        raise ValueError(f"{path}: B run-file hash is malformed")
    if not isinstance(price.get("file_rows_at_run"), int) or price["file_rows_at_run"] < 3172:
        raise ValueError(f"{path}: B run-file row count precedes the registered prefix")
    file_last_date = price.get("file_last_date_at_run")
    try:
        parsed_file_last_date = date.fromisoformat(file_last_date)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: B run-file last date is not canonical ISO") from exc
    if parsed_file_last_date.isoformat() != file_last_date:
        raise ValueError(f"{path}: B run-file last date is not canonical ISO")
    if parsed_file_last_date < date.fromisoformat(W1A1_ASOF):
        raise ValueError(f"{path}: B run file does not reach the registered asof")

    sealed = payload.get("sealed_w1_sha256") or {}
    if sealed != W1A1_SEALED_W1_SHA256:
        raise ValueError(f"{path}: sealed W1 hash receipt drifted")
    for relative, expected in sealed.items():
        if relative == W1A1_GOLD_DISCLOSURE_PATH:
            continue
        frozen = _contained_path(root, relative, label=str(path))
        if not frozen.is_file() or _sha256(frozen) != expected:
            raise ValueError(f"{path}: sealed W1 artifact drifted: {relative}")

    roster = payload.get("miner_probe_roster") or {}
    sealed = tuple(roster.get("sealed_w1") or ())
    effective = tuple(roster.get("effective_w1a1") or ())
    if sealed != W1_SEALED_MINER_PROBE:
        raise ValueError(f"{path}: sealed W1 roster receipt drifted")
    if effective != W1A1_EFFECTIVE_MINER_PROBE:
        raise ValueError(f"{path}: effective W1-A1 roster receipt drifted")
    if payload.get("measured_rows_mutated") is not False:
        raise ValueError(f"{path}: measured_rows_mutated must be false")

    registered = tuple(payload.get("registered_output_paths") or ())
    if registered != W1A1_REGISTERED_OUTPUT_PATHS:
        raise ValueError(f"{path}: registered output allowlist drifted")

    generated = payload.get("generated_output_sha256") or {}
    if set(generated) != set(W1A1_GENERATED_OUTPUT_PATHS):
        raise ValueError(f"{path}: generated output hash closure is incomplete")
    for relative, expected in generated.items():
        governed = _contained_path(root, str(relative), label=str(path))
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"{path}: malformed governed hash: {relative}")
        if not governed.exists() or _sha256(governed) != expected:
            raise ValueError(f"{path}: governed output drifted or is missing: {relative}")

    disclosure = payload.get("disclosure_only") or {}
    if disclosure.get("path") != W1A1_GOLD_DISCLOSURE_PATH:
        raise ValueError(f"{path}: GOLD disclosure path drifted")
    if disclosure.get("before_sha256") != W1A1_GOLD_MD_BEFORE_SHA256:
        raise ValueError(f"{path}: GOLD disclosure pre-annotation hash drifted")
    if disclosure.get("restores_original_when_removed") is not True:
        raise ValueError(f"{path}: GOLD disclosure is not declared reversible")
    if disclosure.get("gold_svg_unchanged") is not True:
        raise ValueError(f"{path}: GOLD chart is not declared unchanged")
    gold_path = _contained_path(root, W1A1_GOLD_DISCLOSURE_PATH, label=str(path))
    if not gold_path.is_file() or _sha256(gold_path) != disclosure.get("after_sha256"):
        raise ValueError(f"{path}: GOLD disclosure path/hash is not closed")
    gold_text = gold_path.read_text(encoding="utf-8")
    begin = str(disclosure.get("marker_begin") or "")
    end = str(disclosure.get("marker_end") or "")
    if begin != W1A1_GOLD_ANNOTATION_BEGIN or end != W1A1_GOLD_ANNOTATION_END:
        raise ValueError(f"{path}: GOLD disclosure marker receipt drifted")
    if gold_text.count(begin) != 1 or gold_text.count(end) != 1:
        raise ValueError(f"{path}: GOLD disclosure markers are absent or ambiguous")
    start = gold_text.index(begin)
    finish = gold_text.index(end) + len(end)
    if start >= finish:
        raise ValueError(f"{path}: GOLD disclosure markers are out of order")
    block = gold_text[start:finish]
    restored = gold_text.replace(f"\n\n{block}\n\n", "\n\n", 1)
    if hashlib.sha256(restored.encode("utf-8")).hexdigest() != W1A1_GOLD_MD_BEFORE_SHA256:
        raise ValueError(f"{path}: GOLD disclosure does not restore the sealed dossier")
    return effective
