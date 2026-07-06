"""R4 contract drift checker (NW Rails PR-7).

Compares each entry in site/factordata/contracts/artifact_manifest.json against the
live artifact on disk.  Exits nonzero when the artifact's actual top-level JSON fields
diverge from the manifest's schema_fields contract.

The "34-field china_standouts consumed by a real-money bot with no handshake" hazard:
a field added or removed silently in the nightly build is invisible to consumers until
they crash on a KeyError at trade time.  This guard makes schema drift visible at PR
merge time.

Wildcard artifacts (kind=per_stock_intel, per_stock_signal): sampled from the first
file in the glob directory.  If no live sample exists the entry is SKIPPED (no data
in this environment is not a drift).

Usage:
    python scripts/check_contract_drift.py            # hard-fail mode (default)
    python scripts/check_contract_drift.py --warn-only  # exit 0 even on drift

Ratchet: flip to hard-fail after one clean week: 2026-07-13
(Remove --warn-only from the ci.yml step and delete this comment once the date passes.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "site" / "factordata" / "contracts" / "artifact_manifest.json"

# Wildcard placeholder present in artifact paths for per-ticker artifacts.
_WILDCARD = "<SYM>"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"manifest not found: {MANIFEST_PATH}")
    with open(MANIFEST_PATH) as fh:
        return json.load(fh)


def _resolve_artifact_path(artifact_pattern: str) -> Path | None:
    """Return a concrete path for the artifact pattern.

    For wildcard patterns (containing <SYM>) return the first .json file found in the
    directory, or None if the directory does not exist / is empty.
    """
    if _WILDCARD in artifact_pattern:
        # e.g. "site/stockdata/<SYM>.json" → directory "site/stockdata"
        directory = Path(artifact_pattern.replace(f"/{_WILDCARD}.json", ""))
        dir_path = ROOT / directory
        if not dir_path.is_dir():
            return None
        candidates = sorted(dir_path.glob("*.json"))
        return candidates[0] if candidates else None
    else:
        p = ROOT / artifact_pattern
        return p if p.exists() else None


def _actual_fields(path: Path) -> list[str]:
    """Return the sorted top-level JSON keys of the artifact at path."""
    with open(path) as fh:
        data = json.load(fh)
    return sorted(data.keys())


def _diff_fields(
    artifact: str,
    registered: list[str],
    actual: list[str],
) -> tuple[list[str], list[str]]:
    """Return (added, removed) field lists."""
    reg_set = set(registered)
    act_set = set(actual)
    added = sorted(act_set - reg_set)    # in artifact but not in contract
    removed = sorted(reg_set - act_set)  # in contract but not in artifact
    return added, removed


def check_drift(warn_only: bool = False) -> int:
    """Run the drift check.  Returns 0 (clean) or 1 (drift found).

    Prints a human-readable diff for any entry that diverges.
    """
    manifest = _load_manifest()
    artifacts = manifest.get("artifacts", [])

    drift_count = 0
    skip_count = 0
    clean_count = 0

    for entry in artifacts:
        artifact_pattern = entry["artifact"]
        registered = entry.get("schema_fields")

        if registered is None:
            # No schema_fields registered yet — nothing to check.
            skip_count += 1
            continue

        live_path = _resolve_artifact_path(artifact_pattern)
        if live_path is None:
            # Artifact not present in this environment (e.g. R2 store, CI runner).
            skip_count += 1
            continue

        actual = _actual_fields(live_path)
        added, removed = _diff_fields(artifact_pattern, registered, actual)

        if not added and not removed:
            clean_count += 1
            continue

        # Drift detected.
        drift_count += 1
        print(f"\nDRIFT: {artifact_pattern}")
        print(f"  sample: {live_path.relative_to(ROOT)}")
        if added:
            print(f"  fields in artifact NOT in contract (+{len(added)}): {added}")
            print("    -> bump schema_version minor + add to schema_fields in "
                  "scripts/export_signal_contracts.py, then re-run the script to "
                  "regenerate site/factordata/contracts/artifact_manifest.json")
        if removed:
            print(f"  fields in contract NOT in artifact (-{len(removed)}): {removed}")
            print("    -> bump schema_version major + remove from schema_fields in "
                  "scripts/export_signal_contracts.py, then notify bot/terminal consumers "
                  "before merging (breaking change)")

    # Summary line.
    total = len(artifacts)
    print(
        f"\ncontract drift: {drift_count} drift(s), {clean_count} clean, "
        f"{skip_count} skipped (no live sample)  [{total} entries total]"
    )

    if drift_count == 0:
        return 0

    if warn_only:
        print(
            "WARN-ONLY mode: drift detected but exiting 0.  "
            "Flip to hard-fail after one clean week: 2026-07-13"
        )
        return 0

    print("EXIT 1 — fix drift or use --warn-only during ratchet period")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Exit 0 even when drift is detected (warn-first ratchet tier)",
    )
    args = parser.parse_args()
    sys.exit(check_drift(warn_only=args.warn_only))


if __name__ == "__main__":
    main()
