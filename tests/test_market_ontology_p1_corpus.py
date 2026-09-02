"""Tests for the F00A Market Ontology P1 corpus verification/admission harness.

These use SYNTHETIC fixtures only. The real retained corpus is not in the
repository and is not required to exercise the gate logic -- which is the point:
the harness must be provably correct BEFORE the real bytes arrive, because the
one thing it must never do is admit something that is not byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.verify_market_ontology_p1_corpus import (  # noqa: E402
    KNOWN_RECEIPTS,
    main,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_delivery(tmp_path: Path, members: dict[str, bytes]) -> Path:
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    for name, payload in members.items():
        (delivery / name).write_bytes(payload)
    return delivery


def _make_manifest(tmp_path: Path, members: dict[str, bytes], *, overrides=None) -> Path:
    entries = []
    for name, payload in members.items():
        entry = {"name": name, "bytes": len(payload), "sha256": _sha256(payload)}
        if overrides and name in overrides:
            entry.update(overrides[name])
        entries.append(entry)
    manifest = {
        "schema": "mastermind.competitor.market_ontology.p1_turn6_manifest.v1",
        "public_phase": "COMPLETE",
        "files": entries,
    }
    path = tmp_path / "TURN6_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def members() -> dict[str, bytes]:
    return {
        "MEMBER_ONE.csv": b"index,id,capability\n1,MO-1,alpha\n",
        "MEMBER_TWO.json": b'{"capability_count": 1556}\n',
        "MEMBER_THREE.md": b"# Turn 6 final report\n",
    }


def test_clean_delivery_verifies(tmp_path, members):
    delivery = _make_delivery(tmp_path, members)
    manifest = _make_manifest(tmp_path, members)
    assert main(["--delivery", str(delivery), "--manifest", str(manifest)]) == 0


def test_missing_member_fails_and_writes_nothing(tmp_path, members):
    partial = dict(members)
    partial.pop("MEMBER_TWO.json")
    delivery = _make_delivery(tmp_path, partial)
    manifest = _make_manifest(tmp_path, members)
    archive = tmp_path / "archive"

    rc = main([
        "--delivery", str(delivery), "--manifest", str(manifest),
        "--archive", str(archive), "--admit",
    ])
    assert rc == 1
    assert not archive.exists(), "a missing member must never produce a partial archive"


def test_hash_mismatch_refuses_admission(tmp_path, members):
    delivery = _make_delivery(tmp_path, members)
    # Same byte length, different content: size alone must not be enough to pass.
    tampered = b"index,id,capability\n1,MO-1,ALPHA\n"
    assert len(tampered) == len(members["MEMBER_ONE.csv"])
    (delivery / "MEMBER_ONE.csv").write_bytes(tampered)
    manifest = _make_manifest(tmp_path, members)
    archive = tmp_path / "archive"

    rc = main([
        "--delivery", str(delivery), "--manifest", str(manifest),
        "--archive", str(archive), "--admit",
    ])
    assert rc == 1
    assert not archive.exists()


def test_admission_writes_byte_identical_members_and_manifest(tmp_path, members):
    delivery = _make_delivery(tmp_path, members)
    manifest = _make_manifest(tmp_path, members)
    archive = tmp_path / "archive"

    rc = main([
        "--delivery", str(delivery), "--manifest", str(manifest),
        "--archive", str(archive), "--admit",
    ])
    assert rc == 0

    for name, payload in members.items():
        assert (archive / name).read_bytes() == payload, f"{name} was not admitted byte-identically"

    imported = json.loads((archive / "IMPORT_MANIFEST.json").read_text(encoding="utf-8"))
    assert imported["corpus_admitted"] is True
    assert imported["member_count"] == len(members)
    assert imported["operation_key"] == (
        "marketontology-f00a-p1-corpus-admission-20260828-sol-001"
    )
    for member in imported["members"]:
        assert member["content_modified"] is False
        assert member["historical_receipt"]
        assert member["imported_at_utc"].endswith("Z")


def test_manifest_contradicting_published_receipt_is_refused(tmp_path):
    name = "MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.csv"
    payload = b"not the real corpus\n"
    delivery = _make_delivery(tmp_path, {name: payload})
    manifest = _make_manifest(tmp_path, {name: payload})

    # The synthetic manifest necessarily disagrees with the published receipt,
    # which is exactly the source-of-truth conflict the harness must catch.
    with pytest.raises(SystemExit) as excinfo:
        main(["--delivery", str(delivery), "--manifest", str(manifest)])
    assert "contradicts the published receipt" in str(excinfo.value)


def test_partial_requires_explicit_adjudication(tmp_path, members):
    delivery = _make_delivery(tmp_path, members)
    manifest = _make_manifest(tmp_path, members)
    rc = main([
        "--delivery", str(delivery), "--manifest", str(manifest),
        "--admit", "--allow-partial",
    ])
    assert rc == 2, "a narrower boundary must name the Sol ruling that authorized it"


def test_known_receipts_only_can_never_close_admission(tmp_path):
    payload = b"placeholder\n"
    name = next(iter(KNOWN_RECEIPTS))
    delivery = _make_delivery(tmp_path, {name: payload})
    # Even a delivery that matched would stay incomplete: 2 of 28 members.
    rc = main(["--delivery", str(delivery), "--known-receipts-only"])
    assert rc == 1


def test_missing_manifest_is_a_hard_stop(tmp_path, members):
    delivery = _make_delivery(tmp_path, members)
    with pytest.raises(SystemExit) as excinfo:
        main(["--delivery", str(delivery)])
    assert "--manifest is required" in str(excinfo.value)


def test_annotations_start_the_line(tmp_path, members, capsys):
    """A logger would prefix the line and GitHub would drop the annotation."""
    partial = dict(members)
    partial.pop("MEMBER_TWO.json")
    delivery = _make_delivery(tmp_path, partial)
    manifest = _make_manifest(tmp_path, members)

    main(["--delivery", str(delivery), "--manifest", str(manifest)])

    annotations = [
        line for line in capsys.readouterr().out.splitlines() if "::warning" in line or "::error" in line
    ]
    assert annotations, "expected an annotation for an incomplete delivery"
    for line in annotations:
        assert line.startswith("::"), f"annotation must start the line, got {line!r}"
