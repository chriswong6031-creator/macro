"""tests/test_admin_allies.py — Unit + panel tests for the Allies cockpit (MKT-D11 W1).

Covers admin.allies_store (fold + transition rules), admin.marketing.allies (panel
fail-soft + real fold), and admin.marketing.allies_kit (path-traversal guard).

The status ledger writer NEVER raises and only RECORDS a decision — this page has
no outbound capability (MKT-D11). Tests here assert the fold's last-valid-wins rule
and that illegal / unknown-target transitions are ignored rather than corrupting state.

ROOT bootstrap mirrors test_admin_marketing.py (fixture tmp_path root passed to the
panel) and test_admin_actions.py (patched _ledger_path for the writer).
"""
from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from admin import allies_store, marketing  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — a small seed ledger of targets, authored here (no engine dependency)
# ---------------------------------------------------------------------------

def _target(tid, kind="creator", verdict="open", score=0.5, kit=True, rule=None):
    row = {
        "schema": "marketing.allies_target/v1",
        "target_id": tid,
        "kind": kind,
        "name": tid.replace("-", " ").title(),
        "platform": "youtube",
        "source": "test",
        "link": None,
        "style": None,
        "audience_tier": 2,
        "topical_overlap": 0.8,
        "receipt_friendly": True,
        "outreach_verdict": verdict,
        "rule_citation": rule,
        "score": score,
        "status": "candidate",
        "kit_path": f"data/marketing/allies_kits/{tid}.md",
        "seeded_utc": "2026-07-19",
        "tier": "display",
    }
    return row


@pytest.fixture
def seed_targets():
    return [
        _target("creator-alpha", kind="creator", verdict="open", score=0.9),
        _target("com-beta", kind="community", verdict="conditional", score=0.7,
                rule={"rules_url": "https://x/rules", "rule_ref": "Rule 2",
                      "retrieved_utc": "2026-07-19", "verdict": "conditional",
                      "note": "no promo links"}),
        _target("fund-gamma", kind="fund_manager", verdict="prohibited", score=0.4),
    ]


@pytest.fixture
def seeded_root(tmp_path, seed_targets):
    """A tmp repo root with allies_targets.jsonl + one kit file present."""
    mdir = tmp_path / "data" / "marketing"
    kdir = mdir / "allies_kits"
    kdir.mkdir(parents=True)
    with (mdir / "allies_targets.jsonl").open("w", encoding="utf-8") as fh:
        for t in seed_targets:
            fh.write(json.dumps(t) + "\n")
    (kdir / "creator-alpha.md").write_text("# Kit for Alpha\n\nReal receipts here.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def empty_root(tmp_path):
    """A tmp root with no allies data — accruing state."""
    return tmp_path


# ---------------------------------------------------------------------------
# allies_store: transition rules
# ---------------------------------------------------------------------------

def test_is_legal_forward_steps():
    assert allies_store.is_legal("candidate", "operator_approved")
    assert allies_store.is_legal("operator_approved", "contacted")
    assert allies_store.is_legal("contacted", "active")


def test_is_legal_rejects_skips_and_backward():
    # candidate -> contacted is a skip and must be rejected
    assert not allies_store.is_legal("candidate", "contacted")
    assert not allies_store.is_legal("candidate", "active")
    # backward
    assert not allies_store.is_legal("contacted", "candidate")
    # same status
    assert not allies_store.is_legal("candidate", "candidate")


def test_is_legal_retire_from_any_live_status():
    for s in ("candidate", "operator_approved", "contacted", "active"):
        assert allies_store.is_legal(s, "retired"), f"{s} -> retired should be legal"
    # retiring an already-retired target is a no-op → rejected
    assert not allies_store.is_legal("retired", "retired")


def test_is_legal_rejects_unknown_status():
    assert not allies_store.is_legal("candidate", "bogus")
    assert not allies_store.is_legal("bogus", "active")


def test_legal_next():
    assert allies_store.legal_next("candidate") == ["operator_approved", "retired"]
    assert allies_store.legal_next("contacted") == ["active", "retired"]
    assert allies_store.legal_next("active") == ["retired"]
    assert allies_store.legal_next("retired") == []


# ---------------------------------------------------------------------------
# allies_store: fold_status
# ---------------------------------------------------------------------------

def _tr(tid, to, frm="", note=""):
    return {"ts": "2026-07-19T00:00:00+00:00", "actor": "operator",
            "target_id": tid, "from_status": frm, "to_status": to, "note": note}


def test_fold_last_valid_wins(seed_targets):
    """A legal chain of transitions advances the fold; the last valid state wins."""
    transitions = [
        _tr("creator-alpha", "operator_approved"),
        _tr("creator-alpha", "contacted"),
    ]
    fold = allies_store.fold_status(seed_targets, transitions)
    assert fold["creator-alpha"]["status"] == "contacted"
    assert len(fold["creator-alpha"]["history"]) == 2
    # untouched targets stay at seed
    assert fold["com-beta"]["status"] == "candidate"


def test_fold_illegal_transition_ignored(seed_targets):
    """An illegal step (candidate -> active) is skipped; the fold stays at candidate,
    and a later LEGAL step still applies from the true current status."""
    transitions = [
        _tr("creator-alpha", "active"),            # illegal skip — ignored
        _tr("creator-alpha", "operator_approved"),  # legal — applied
    ]
    fold = allies_store.fold_status(seed_targets, transitions)
    assert fold["creator-alpha"]["status"] == "operator_approved"
    # only the legal one made it into history
    assert len(fold["creator-alpha"]["history"]) == 1
    assert fold["creator-alpha"]["history"][0]["to_status"] == "operator_approved"


def test_fold_unknown_target_ignored(seed_targets):
    """A transition referencing a target not in the seed ledger is ignored."""
    transitions = [_tr("ghost-target", "operator_approved")]
    fold = allies_store.fold_status(seed_targets, transitions)
    assert "ghost-target" not in fold
    # known targets untouched
    assert all(v["status"] == "candidate" for v in fold.values())


def test_fold_retire_then_no_advance(seed_targets):
    """Once retired, no further transition applies (retired has no legal next)."""
    transitions = [
        _tr("fund-gamma", "retired"),
        _tr("fund-gamma", "operator_approved"),  # illegal from retired — ignored
    ]
    fold = allies_store.fold_status(seed_targets, transitions)
    assert fold["fund-gamma"]["status"] == "retired"
    assert len(fold["fund-gamma"]["history"]) == 1


# ---------------------------------------------------------------------------
# allies_store: writer (never raises)
# ---------------------------------------------------------------------------

def test_append_transition_writes_row(tmp_path):
    ledger = tmp_path / "allies_status.jsonl"
    with unittest.mock.patch("admin.allies_store._ledger_path", return_value=ledger):
        row = allies_store.append_transition("creator-alpha", "candidate", "operator_approved", note="worth it")
    assert ledger.exists()
    written = json.loads(ledger.read_text().strip())
    assert written["actor"] == "operator"
    assert written["target_id"] == "creator-alpha"
    assert written["to_status"] == "operator_approved"
    assert row["from_status"] == "candidate"


def test_append_transition_note_capped(tmp_path):
    ledger = tmp_path / "allies_status.jsonl"
    with unittest.mock.patch("admin.allies_store._ledger_path", return_value=ledger):
        row = allies_store.append_transition("x", "candidate", "retired", note="y" * 500)
    assert len(row["note"]) == allies_store.NOTE_MAX_CHARS


def test_append_transition_never_raises(tmp_path):
    with unittest.mock.patch("builtins.open", side_effect=OSError("disk full")):
        with unittest.mock.patch("admin.allies_store._ledger_path", return_value=tmp_path / "x.jsonl"):
            row = allies_store.append_transition("x", "candidate", "retired")
    assert row["target_id"] == "x"  # row still returned


# ---------------------------------------------------------------------------
# marketing.allies panel
# ---------------------------------------------------------------------------

def test_panel_missing_ledger_accruing(empty_root):
    """No allies_targets.jsonl → ok:True with accruing note + empty counts (never raises)."""
    d = marketing.allies(empty_root)
    assert d["ok"] is True
    assert "note" in d
    assert "accruing" in d["note"].lower()
    assert d["targets"] == []
    assert d["counts"]["total"] == 0
    # the gate + referral truth are ALWAYS present, even on day 0
    assert "operator" in d["operator_gate"].lower()
    assert "never contacts" in d["operator_gate"].lower()
    assert "MNZ" in d["referral_note"]


def test_panel_real_fold(seeded_root):
    """Panel reads real seed targets, sorts by score desc, folds status, tallies counts."""
    d = marketing.allies(seeded_root)
    assert d["ok"] is True
    assert d["counts"]["total"] == 3
    # sorted by score desc
    ids = [t["target_id"] for t in d["targets"]]
    assert ids == ["creator-alpha", "com-beta", "fund-gamma"]
    # counts
    assert d["counts"]["by_verdict"] == {"open": 1, "conditional": 1, "prohibited": 1}
    assert d["counts"]["by_kind"]["community"] == 1
    assert d["counts"]["by_status"]["candidate"] == 3
    # kit availability reflects the one file we wrote
    kit_map = {t["target_id"]: t["kit_available"] for t in d["targets"]}
    assert kit_map["creator-alpha"] is True
    assert kit_map["com-beta"] is False
    # every folded row carries status + history
    assert all("status" in t and "status_history" in t for t in d["targets"])


def test_panel_reflects_operator_transitions(seeded_root):
    """After an operator transition is written to the ledger under the same root,
    the panel's fold reflects the new status."""
    ledger = seeded_root / "data" / "operator" / "allies_status.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(_tr("creator-alpha", "operator_approved")) + "\n", encoding="utf-8")
    with unittest.mock.patch("admin.allies_store._ledger_path", return_value=ledger):
        d = marketing.allies(seeded_root)
    row = next(t for t in d["targets"] if t["target_id"] == "creator-alpha")
    assert row["status"] == "operator_approved"
    assert d["counts"]["by_status"]["operator_approved"] == 1


# ---------------------------------------------------------------------------
# marketing.allies_kit — path-traversal guard
# ---------------------------------------------------------------------------

def test_kit_returns_markdown(seeded_root):
    d = marketing.allies_kit(seeded_root, "creator-alpha")
    assert d["ok"] is True
    assert "Real receipts" in d["markdown"]


def test_kit_missing_is_soft(seeded_root):
    d = marketing.allies_kit(seeded_root, "com-beta")  # no kit file written
    assert d["ok"] is True
    assert d["markdown"] == ""


def test_kit_rejects_traversal(seeded_root):
    for bad in ("../secrets", "..%2f..%2f", "a/b", "foo/../bar", ".."):
        d = marketing.allies_kit(seeded_root, bad)
        assert d["ok"] is False, f"{bad!r} must be rejected"
        assert "invalid" in d["error"].lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
