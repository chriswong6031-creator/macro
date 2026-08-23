from hashlib import sha256

import pytest

from scripts.research.dislocation_p0_a1r_evidence_catalog import build_catalog, evidence_segments


def test_catalog_segments_replay_exact_source_bytes() -> None:
    source = b"<html><body><p>Operations resumed after the temporary outage.</p></body></html>"
    digest = sha256(source).hexdigest()
    segments = evidence_segments(
        packet_id="packet-1", document_sha256=digest, source=source
    )
    assert len(segments) == 1
    evidence = segments[0]["evidence"]
    assert source[evidence["start"]:evidence["end"]] == evidence["excerpt"].encode()
    assert evidence["document_sha256"] == digest


def test_catalog_preserves_segments_for_every_matched_document(tmp_path) -> None:
    first = b"<html><p>First SEC exhibit supplies adverse disclosure.</p></html>"
    second = b"<html><p>Second SEC exhibit supplies resolution context.</p></html>"
    (tmp_path / "packets").mkdir()
    (tmp_path / "packets/01_doc-a.source").write_bytes(first)
    (tmp_path / "packets/01_doc-b.source").write_bytes(second)
    index = {
        "schema": "mastermind.dislocation_p0.a1r_model_packet_index.v2",
        "packets": [{
            "packet_id": "packet-1",
            "documents": [
                {
                    "document_id": "doc-a",
                    "document_name": "matched-a.htm",
                    "document_sha256": sha256(first).hexdigest(),
                    "byte_length": len(first),
                    "source_path": "packets/01_doc-a.source",
                },
                {
                    "document_id": "doc-b",
                    "document_name": "matched-b.htm",
                    "document_sha256": sha256(second).hexdigest(),
                    "byte_length": len(second),
                    "source_path": "packets/01_doc-b.source",
                },
            ],
        }] * 20,
    }
    # Only build_catalog cardinality is relevant here; use distinct packet IDs
    # to make the fixture a lawful twenty-packet index.
    index["packets"] = [dict(index["packets"][0]) | {"packet_id": f"packet-{slot}"} for slot in range(1, 21)]
    catalog = build_catalog(index, tmp_path)
    assert catalog["schema"].endswith(".v2")
    hashes = {item["evidence"]["document_sha256"] for item in catalog["packets"][0]["segments"]}
    assert hashes == {sha256(first).hexdigest(), sha256(second).hexdigest()}


def test_catalog_fails_closed_when_matched_document_bytes_are_missing(tmp_path) -> None:
    index = {
        "schema": "mastermind.dislocation_p0.a1r_model_packet_index.v2",
        "packets": [{
            "packet_id": f"packet-{slot}",
            "documents": [{
                "document_id": "doc-a",
                "document_name": "matched-a.htm",
                "document_sha256": "a" * 64,
                "byte_length": 1,
                "source_path": "packets/missing.source",
            }],
        } for slot in range(1, 21)],
    }
    with pytest.raises(FileNotFoundError):
        build_catalog(index, tmp_path)
