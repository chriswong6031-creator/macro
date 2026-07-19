"""tests/test_levels_ledger.py — WP-C3 sealed Ledger core (canonicalization + hash + verify)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_ledger import (  # noqa: E402
    canonical_bytes, sha256_hex, seal_board, build_ledger_file, seal, verify,
    index_entry, SCHEMA, INDEX_SCHEMA,
)


def _board(root="AAPL", asof="2024-06-14", spot=213.5):
    return {
        "schema": "levels.v1", "root": root, "asof": asof, "spot": spot,
        "regime": {"label": "sticky"},
        "nodes": [
            {"role": "anchor", "strike": 215.0, "sticky": True, "note": ""},
            {"role": "call_wall", "strike": 220.0, "sticky": True, "note": ""},
            {"role": "put_wall", "strike": 210.0, "sticky": False, "note": ""},
            {"role": "flip", "strike": 213.0, "sticky": None, "note": ""},
            {"role": "void", "strike": None, "strike_lo": 221, "strike_hi": 224, "note": ""},  # dropped
            {"role": "cluster", "strike": None, "sticky": True, "note": "absent"},  # null strike dropped
        ],
    }


class TestCanonical:
    def test_deterministic_bytes_regardless_of_key_order(self):
        a = canonical_bytes({"b": 1, "a": 2, "c": [3, {"y": 1, "x": 2}]})
        b = canonical_bytes({"c": [3, {"x": 2, "y": 1}], "a": 2, "b": 1})
        assert a == b  # sorted keys → identical bytes
        assert sha256_hex(a) == sha256_hex(b)

    def test_sha_changes_on_any_edit(self):
        base = sha256_hex(canonical_bytes({"session_date": "2024-06-14", "x": 215.0}))
        edited = sha256_hex(canonical_bytes({"session_date": "2024-06-14", "x": 215.01}))
        assert base != edited


class TestSealBoard:
    def test_projection_keeps_only_sealed_roles_with_strikes(self):
        sb = seal_board(_board())
        roles = [n["role"] for n in sb["nodes"]]
        assert roles == sorted(roles)  # deterministic order
        assert set(roles) == {"anchor", "call_wall", "put_wall", "flip"}  # void + null-strike cluster dropped
        assert sb["root"] == "AAPL" and sb["session_date"] == "2024-06-14"
        assert sb["spot"] == 213.5 and sb["regime"] == "sticky"

    def test_none_on_bad_input(self):
        assert seal_board(None) is None
        assert seal_board({"nodes": "x"}) is None
        # missing session_date (no asof) → cannot be sealed
        assert seal_board({"root": "AAPL", "nodes": []}) is None
        # root + session_date present, empty nodes → sealable (n=0 nodes)
        sb = seal_board({"root": "AAPL", "asof": "2024-06-14", "nodes": []})
        assert sb is not None and sb["nodes"] == []


class TestSealVerify:
    def test_seal_and_verify_roundtrip(self):
        f, sha = seal("2024-06-14", [seal_board(_board("AAPL")), seal_board(_board("MSFT", spot=440.0))],
                      sealed_at="2024-06-14T13:12:00Z")
        assert f["schema"] == SCHEMA and f["n_boards"] == 2
        assert [b["root"] for b in f["boards"]] == ["AAPL", "MSFT"]  # sorted by root
        assert verify(f, sha) is True
        assert len(sha) == 64

    def test_tamper_is_detected(self):
        f, sha = seal("2024-06-14", [seal_board(_board("AAPL"))], sealed_at="t")
        # move a strike by a penny → hash must no longer match
        f["boards"][0]["nodes"][0]["strike"] += 0.01
        assert verify(f, sha) is False

    def test_reserialize_reproduces_hash(self):
        import json
        f, sha = seal("2024-06-14", [seal_board(_board("AAPL"))], sealed_at="t")
        # simulate download → parse → re-hash (what a user does with shasum)
        roundtrip = json.loads(json.dumps(f))
        assert sha256_hex(canonical_bytes(roundtrip)) == sha

    def test_sealed_at_does_not_break_determinism_but_changes_hash(self):
        f1, s1 = seal("2024-06-14", [seal_board(_board("AAPL"))], sealed_at="A")
        f2, s2 = seal("2024-06-14", [seal_board(_board("AAPL"))], sealed_at="B")
        assert s1 != s2  # sealed_at is part of the sealed bytes
        assert verify(f1, s1) and verify(f2, s2)


class TestIndexEntry:
    def test_index_entry_shape(self):
        f, sha = seal("2024-06-14", [seal_board(_board("AAPL")), seal_board(_board("MSFT"))], sealed_at="t")
        e = index_entry(f, sha)
        assert e["session_date"] == "2024-06-14" and e["n_boards"] == 2
        assert e["roots"] == ["AAPL", "MSFT"] and e["sha256"] == sha
