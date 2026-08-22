from __future__ import annotations

from dataclasses import replace
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import persist_response
from scripts.research.dislocation_p0_a1r_owner_run import (
    OwnerRunBlocked,
    _replay_generic_source_receipt,
)


def test_replays_persisted_generic_owner_sidecar_not_ephemeral_receipt(
    tmp_path: Path,
) -> None:
    content = json.dumps({"filings": {"recent": {}}}).encode()
    persisted = persist_response(
        tmp_path,
        cik="1",
        endpoint="submissions",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        content=content,
        retrieved_at="2026-08-22T10:00:00Z",
    )
    ephemeral = replace(persisted, retrieved_at="2026-08-22T11:00:00Z")
    raw, sidecar, storage_key, sidecar_sha = _replay_generic_source_receipt(
        tmp_path, ephemeral
    )
    sidecar_bytes = (tmp_path / storage_key).read_bytes()
    assert raw == content
    assert sidecar["retrieved_at"] == "2026-08-22T10:00:00Z"
    assert sidecar_sha == sha256(sidecar_bytes).hexdigest()


def test_replay_rejects_corrupt_generic_owner_object(tmp_path: Path) -> None:
    content = b'{"filings":{}}'
    receipt = persist_response(
        tmp_path,
        cik="1",
        endpoint="submissions",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        content=content,
        retrieved_at="2026-08-22T10:00:00Z",
    )
    with gzip.open(tmp_path / receipt.object_path, "wb") as handle:
        handle.write(content + b"corrupt")
    with pytest.raises(OwnerRunBlocked, match="receipt replay failed"):
        _replay_generic_source_receipt(tmp_path, receipt)
