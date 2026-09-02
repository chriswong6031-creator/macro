#!/usr/bin/env python3
"""Verify and admit the retained Market Ontology public-P1 research corpus.

Operation: ``marketontology-f00a-p1-corpus-admission-20260828-sol-001``.

F00A admits the ORIGINAL retained Mastermind public-P1 research bytes into a
bounded archive so F00C can reconcile all 1,556 granular capability rows without
model reconstruction or evidence loss. The admission law is byte-exact:

* Only original raw bytes may be admitted. Parsed / searched / exported ChatGPT
  File Library content is NOT raw-byte proof and must never be reserialized as
  the source corpus.
* Every admitted member must match its authoritative receipt (byte size AND
  SHA-256) exactly. No normalization, no rewrite, no reconstruction, no
  substitute source.
* A partial set keeps ``corpus_admitted`` false unless Sol explicitly adjudicates
  a narrower historical archive boundary.

This tool is the whole remaining mechanical step. It does not and cannot obtain
the source bytes -- that requires an authorized original-file/download/attachment
transfer from the environment that actually holds the retained originals. Once
those files exist on a hashable host, this verifies them against the Turn-6
artifact manifest and performs the byte-identical admission.

Usage
-----
Verify only (safe, read-only -- always run this first)::

    python3 scripts/verify_market_ontology_p1_corpus.py \\
        --delivery /path/to/delivered_files \\
        --manifest /path/to/MARKET_ONTOLOGY_P1_TURN6_ARTIFACT_MANIFEST.json

Verify then admit (writes the archive + IMPORT_MANIFEST.json)::

    python3 scripts/verify_market_ontology_p1_corpus.py \\
        --delivery /path/to/delivered_files \\
        --manifest /path/to/MARKET_ONTOLOGY_P1_TURN6_ARTIFACT_MANIFEST.json \\
        --admit

Without the Turn-6 manifest only the two hard receipts below can be checked,
which covers 2 of the 28 declared members and can never satisfy full admission::

    python3 scripts/verify_market_ontology_p1_corpus.py --delivery <dir> --known-receipts-only

Exit codes: ``0`` all declared members verified (and admitted, if requested);
``1`` verification failed (missing / size mismatch / hash mismatch); ``2`` usage
or input error. Failure is always fail-closed: nothing is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Hard receipts published in the F00A commission and independently recorded by
# DSC:MARKET-ONTOLOGY-PUBLIC-P1-CORPUS-RETAINED-OUTSIDE-GITHUB. These are the
# only member identities known WITHOUT the Turn-6 manifest.
KNOWN_RECEIPTS: dict[str, dict[str, object]] = {
    "MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.csv": {
        "bytes": 495_184,
        "sha256": "1b5d1137710d6bae504e94bbcf4155a3bd5491863e0d8e84078b0d009564a827",
    },
    "MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.json": {
        "bytes": 957_866,
        "sha256": "785f83ca2e92e070d41174b2a6e28834019517d6c845351771eb261fde766d59",
    },
}

# The Turn-6 manifest declares the bounded closure set. Recorded in the
# commission as 28 exact file entries.
EXPECTED_MANIFEST_SCHEMA = "mastermind.competitor.market_ontology.p1_turn6_manifest.v1"
EXPECTED_MEMBER_COUNT = 28

DEFAULT_ARCHIVE = Path("research/market_intelligence_productization/market_ontology_p1_archive")

CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    """Stream a SHA-256 so a large member never has to fit in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def annotate(level: str, title: str, message: str) -> None:
    """Emit a GitHub Actions annotation.

    Must be a bare print starting the line and flushed: a logger would prefix
    the line and GitHub would silently drop the annotation, and stdout is block
    buffered when piped in CI.
    """
    print(f"::{level} title={title}::{message}", flush=True)


def load_receipts(manifest_path: Path | None, known_only: bool) -> tuple[dict, str]:
    """Return {filename: {bytes, sha256}} plus a human label for the source."""
    if known_only:
        return dict(KNOWN_RECEIPTS), "known-receipts-only (2 of 28 members)"

    if manifest_path is None:
        raise SystemExit(
            "error: --manifest is required unless --known-receipts-only is passed.\n"
            "The Turn-6 artifact manifest is the authoritative per-member receipt list;\n"
            "without it only 2 of the 28 declared members can be verified and full\n"
            "admission is impossible. Request it alongside the raw files."
        )

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"error: manifest not found: {manifest_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: manifest is not valid JSON ({exc}). Do not hand-repair it.")

    schema = raw.get("schema")
    if schema != EXPECTED_MANIFEST_SCHEMA:
        annotate(
            "warning",
            "f00a-manifest-schema",
            f"manifest schema is {schema!r}, expected {EXPECTED_MANIFEST_SCHEMA!r} -- "
            "this may be a different corpus (e.g. the 88-anchor Desk packet), which is "
            "NOT a substitute for the public-P1 set",
        )

    entries = raw.get("files")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("error: manifest has no usable 'files' list.")

    receipts: dict[str, dict[str, object]] = {}
    for entry in entries:
        name = entry.get("name") or entry.get("filename")
        size = entry.get("bytes") if "bytes" in entry else entry.get("size")
        digest = entry.get("sha256")
        if not name or size is None or not digest:
            raise SystemExit(
                f"error: manifest entry missing name/bytes/sha256: {entry!r}. "
                "An incomplete receipt cannot gate a byte-exact admission."
            )
        receipts[name] = {"bytes": int(size), "sha256": str(digest).lower()}

    # Cross-check the two independently published receipts. A manifest that
    # disagrees with them is not the authoritative Turn-6 manifest.
    for name, known in KNOWN_RECEIPTS.items():
        found = receipts.get(name)
        if found and (found["bytes"] != known["bytes"] or found["sha256"] != known["sha256"]):
            raise SystemExit(
                f"error: manifest contradicts the published receipt for {name}.\n"
                f"  manifest: {found['bytes']} bytes / {found['sha256']}\n"
                f"  published: {known['bytes']} bytes / {known['sha256']}\n"
                "Refusing to proceed -- resolve the source-of-truth conflict with Sol first."
            )

    if len(receipts) != EXPECTED_MEMBER_COUNT:
        annotate(
            "warning",
            "f00a-manifest-count",
            f"manifest declares {len(receipts)} members, commission recorded "
            f"{EXPECTED_MEMBER_COUNT}",
        )

    return receipts, f"{manifest_path.name} ({len(receipts)} members)"


def verify(delivery: Path, receipts: dict) -> tuple[list, list, list]:
    """Classify every declared member as verified / missing / mismatched."""
    verified, missing, mismatched = [], [], []

    for name in sorted(receipts):
        expected = receipts[name]
        candidate = delivery / name
        if not candidate.is_file():
            missing.append(name)
            continue

        actual_size = candidate.stat().st_size
        actual_hash = sha256_of(candidate)
        if actual_size != expected["bytes"] or actual_hash != expected["sha256"]:
            mismatched.append(
                {
                    "name": name,
                    "expected_bytes": expected["bytes"],
                    "observed_bytes": actual_size,
                    "expected_sha256": expected["sha256"],
                    "observed_sha256": actual_hash,
                }
            )
            continue

        verified.append({"name": name, "bytes": actual_size, "sha256": actual_hash})

    return verified, missing, mismatched


def admit(
    verified: list,
    delivery: Path,
    archive: Path,
    receipt_source: str,
    adjudication: str | None,
    complete: bool,
) -> Path:
    """Copy verified members byte-identically and write IMPORT_MANIFEST.json."""
    archive.mkdir(parents=True, exist_ok=True)
    imported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    members = []
    for item in verified:
        source = delivery / item["name"]
        target = archive / item["name"]
        shutil.copy2(source, target)

        # Re-hash the written file. Copying is where silent truncation would
        # show up (a sparse checkout can swallow a write), so the admitted
        # bytes are proven at rest, not merely at read.
        written_hash = sha256_of(target)
        written_size = target.stat().st_size
        if written_hash != item["sha256"] or written_size != item["bytes"]:
            target.unlink(missing_ok=True)
            raise SystemExit(
                f"error: admitted copy of {item['name']} does not match after write "
                f"({written_size} bytes / {written_hash}). Archive left without this member."
            )

        members.append(
            {
                "original_filename": item["name"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "historical_receipt": receipt_source,
                "imported_at_utc": imported_at,
                "content_modified": False,
            }
        )

    manifest = {
        "schema": "mastermind.market_ontology.p1_archive_import_manifest.v1",
        "operation_key": "marketontology-f00a-p1-corpus-admission-20260828-sol-001",
        "imported_at_utc": imported_at,
        "receipt_source": receipt_source,
        "corpus_admitted": bool(complete),
        "member_count": len(members),
        "members": members,
    }
    if adjudication:
        manifest["narrower_boundary_adjudication"] = adjudication

    manifest_path = archive / "IMPORT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and admit the retained Market Ontology public-P1 corpus.",
    )
    parser.add_argument("--delivery", required=True, type=Path,
                        help="directory holding the delivered ORIGINAL raw files")
    parser.add_argument("--manifest", type=Path,
                        help="MARKET_ONTOLOGY_P1_TURN6_ARTIFACT_MANIFEST.json")
    parser.add_argument("--known-receipts-only", action="store_true",
                        help="verify only the 2 published receipts (cannot satisfy admission)")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE,
                        help=f"archive destination (default: {DEFAULT_ARCHIVE})")
    parser.add_argument("--admit", action="store_true",
                        help="write the archive after a fully clean verification")
    parser.add_argument("--allow-partial", action="store_true",
                        help="admit a verified subset; requires --adjudication")
    parser.add_argument("--adjudication", type=str,
                        help="Sol reference authorizing a narrower archive boundary")
    args = parser.parse_args(argv)

    if not args.delivery.is_dir():
        print(f"error: --delivery is not a directory: {args.delivery}", file=sys.stderr)
        return 2
    if args.allow_partial and not args.adjudication:
        print(
            "error: --allow-partial requires --adjudication naming the Sol ruling that\n"
            "authorizes a narrower historical archive boundary. Sol declined to adjudicate\n"
            "one on 2026-08-30; without that ruling a partial set keeps corpus_admitted false.",
            file=sys.stderr,
        )
        return 2

    receipts, receipt_source = load_receipts(args.manifest, args.known_receipts_only)
    verified, missing, mismatched = verify(args.delivery, receipts)
    complete = not missing and not mismatched and not args.known_receipts_only

    print(f"receipt source : {receipt_source}")
    print(f"delivery       : {args.delivery}")
    print(f"declared       : {len(receipts)}")
    print(f"verified       : {len(verified)}")
    print(f"missing        : {len(missing)}")
    print(f"mismatched     : {len(mismatched)}")

    for name in missing:
        print(f"  MISSING    {name}")
    for bad in mismatched:
        print(f"  MISMATCH   {bad['name']}")
        print(f"             expected {bad['expected_bytes']} bytes / {bad['expected_sha256']}")
        print(f"             observed {bad['observed_bytes']} bytes / {bad['observed_sha256']}")

    if mismatched:
        annotate(
            "error",
            "f00a-source-hash-mismatch",
            f"{len(mismatched)} member(s) failed byte/hash verification -- return "
            "DECISION_REQUEST SOURCE_HASH_MISMATCH with expected vs observed; do not "
            "normalize, rewrite or import",
        )
    if missing:
        annotate(
            "warning",
            "f00a-source-bytes-unavailable",
            f"{len(missing)} declared member(s) absent from the delivery -- the lawful "
            "return is BLOCKED SOURCE_BYTES_UNAVAILABLE, never a reconstructed substitute",
        )

    if not args.admit:
        print("\nverify-only (no --admit): nothing written.")
        return 0 if complete else 1

    if mismatched:
        print("\nREFUSING TO ADMIT: hash/size mismatch present. Nothing written.")
        return 1
    if missing and not args.allow_partial:
        print("\nREFUSING TO ADMIT: declared members are missing and --allow-partial "
              "was not given. Nothing written.")
        return 1
    if not verified:
        print("\nREFUSING TO ADMIT: nothing verified. Nothing written.")
        return 1

    manifest_path = admit(
        verified, args.delivery, args.archive, receipt_source, args.adjudication, complete
    )
    print(f"\nadmitted {len(verified)} member(s) -> {args.archive}")
    print(f"wrote {manifest_path}")
    print(f"corpus_admitted = {str(complete).lower()}")
    if not complete:
        annotate(
            "warning",
            "f00a-partial-admission",
            "corpus_admitted is FALSE -- a partial archive does not close F00A and "
            "authorizes no F00C release",
        )
    return 0 if complete else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
