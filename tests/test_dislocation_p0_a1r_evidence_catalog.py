from hashlib import sha256

from scripts.research.dislocation_p0_a1r_evidence_catalog import evidence_segments


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
