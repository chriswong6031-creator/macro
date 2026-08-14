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
from pathlib import Path

from engine.stock_identity.authority import is_zero_authority

AMENDMENT_ID = "SI-W1-A1-GOLD-WRONG-ISSUER"

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
    if payload.get("amendment_id") != AMENDMENT_ID:
        raise ValueError(f"{path}: unexpected amendment_id")
    if not is_zero_authority(payload):
        raise ValueError(f"{path}: amendment authority is not all-false")

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
