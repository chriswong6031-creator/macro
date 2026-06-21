"""Holdout Vault (engine/holdout_vault.py) — the irreversible out-of-sample gate.

Proves the three governance properties: tamper-evident sealing, an append-only peek count
(the holdout's multiple-testing budget), permanent retirement, and hash-chain integrity.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.holdout_vault import HoldoutVault, VaultError  # noqa: E402


def _root():
    return Path(tempfile.mkdtemp())


def test_seal_is_idempotent_for_same_content():
    v = HoldoutVault(_root())
    h1 = v.seal("2026H2", {"dates": ["2026-07-01", "2026-12-31"], "n": 128})
    h2 = v.seal("2026H2", {"dates": ["2026-07-01", "2026-12-31"], "n": 128})
    assert h1 == h2 and v.is_sealed("2026H2")


def test_reseal_with_different_content_is_tamper():
    v = HoldoutVault(_root())
    v.seal("2026H2", {"n": 128})
    try:
        v.seal("2026H2", {"n": 129})              # changed the holdout
    except VaultError as e:
        assert "tamper" in str(e)
    else:
        raise AssertionError("re-sealing with different content must raise")


def test_peek_requires_a_sealed_window():
    v = HoldoutVault(_root())
    try:
        v.peek("hyp-1", window_id="missing", result={"dsr": 0.9})
    except VaultError as e:
        assert "not sealed" in str(e)
    else:
        raise AssertionError("peeking an unsealed window must raise")


def test_peeks_count_into_the_budget_and_persist():
    root = _root()
    v = HoldoutVault(root)
    v.seal("W", {"n": 100})
    v.peek("hyp-1", window_id="W", result={"dsr": 0.91})
    r = v.peek("hyp-2", window_id="W", result={"dsr": 0.40})
    assert r["peek_n"] == 2 and v.peek_count("W") == 2
    # survives a reload (a fresh process can't pretend the holdout was untouched)
    assert HoldoutVault(root).peek_count("W") == 2


def test_retired_hypothesis_cannot_be_peeked_again():
    v = HoldoutVault(_root())
    v.seal("W", {"n": 100})
    v.peek("hyp-1", window_id="W", result={"dsr": 0.3})
    v.retire("hyp-1", reason="failed holdout DSR")
    assert v.is_retired("hyp-1")
    try:
        v.peek("hyp-1", window_id="W", result={"dsr": 0.95})   # "let me just re-run it"
    except VaultError as e:
        assert "retired" in str(e)
    else:
        raise AssertionError("a retired hypothesis must never be peekable again")


def test_retirement_persists_across_reload():
    root = _root()
    v = HoldoutVault(root)
    v.seal("W", {"n": 1})
    v.retire("hyp-x", "blown")
    assert HoldoutVault(root).is_retired("hyp-x")


def test_hash_chain_verifies_and_detects_tamper():
    root = _root()
    v = HoldoutVault(root)
    v.seal("W", {"n": 100})
    v.peek("hyp-1", window_id="W", result={"dsr": 0.2})
    v.peek("hyp-2", window_id="W", result={"dsr": 0.8})
    assert v.verify_chain() is True
    # tamper with the log on disk: flip a recorded result
    p = root / "data" / "vault" / "peek_log.jsonl"
    lines = p.read_text().splitlines()
    rec = json.loads(lines[0]); rec["result"] = {"dsr": 0.99}      # rewrite history
    lines[0] = json.dumps(rec); p.write_text("\n".join(lines) + "\n")
    assert HoldoutVault(root).verify_chain() is False              # chain breaks → caught
