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
    "data/stock_identity/amendments/w1a1_gold_wrong_issuer.json"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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

    generated = payload.get("generated_output_sha256") or {}
    if not generated:
        raise ValueError(f"{path}: generated output hashes are absent")
    for relative, expected in generated.items():
        governed = root / relative
        if not governed.exists() or _sha256(governed) != expected:
            raise ValueError(f"{path}: governed output drifted or is missing: {relative}")

    disclosure = payload.get("disclosure_only") or {}
    gold_path = root / str(disclosure.get("path") or "")
    if not gold_path.is_file() or _sha256(gold_path) != disclosure.get("after_sha256"):
        raise ValueError(f"{path}: GOLD disclosure path/hash is not closed")
    gold_text = gold_path.read_text(encoding="utf-8")
    begin = str(disclosure.get("marker_begin") or "")
    end = str(disclosure.get("marker_end") or "")
    if not begin or not end or gold_text.count(begin) != 1 or gold_text.count(end) != 1:
        raise ValueError(f"{path}: GOLD disclosure markers are absent or ambiguous")
    return effective
