"""Hermetic tests for scripts.oracle_nightly helpers.

Tests the forward ledger (keep-first), banner floor logic, and directive
structure.  All I/O is mocked via tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(episodes=None, breadth=0.5, n_active=0, asof="2026-07-01"):
    return {
        "schema": "oracle_state.v1",
        "asof": asof,
        "regime": {"n_active_complexes": n_active, "breadth": breadth, "vix_regime": 0.38},
        "complexes": [],
        "active_episodes": episodes or [],
        "onset_watchlist": [],
        "disclaimers": {
            "display_only": True,
            "error_rates": {
                "onset_to_confirmed_conversion": 0.997,
                "false_start_rate": 0.38,
            },
        },
    }


def _ep(node, direction, tier):
    cd = "2026-06-28" if tier in ("confirmed", "undeniable") else None
    return {
        "node": node, "direction": direction, "tier": tier,
        "onset_date": "2026-06-25", "confirmed_date": cd,
        "two_sided": False, "pair": None, "survivorship_flagged": False,
    }


# ---------------------------------------------------------------------------
# Forward ledger: keep-FIRST, PIT-stamped
# ---------------------------------------------------------------------------

def test_ledger_keep_first(tmp_path):
    """Appending the same episode twice only writes it once (keep-FIRST)."""
    # Import the step function
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.oracle_nightly import _step_ledger

    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()

    state1 = _state([_ep("XLK", "out", "onset")], asof="2026-07-01")
    n1 = _step_ledger(state1, tmp_path, dry_run=False)
    assert n1 == 1

    # Run again with same episode — should add 0
    state2 = _state([_ep("XLK", "out", "onset")], asof="2026-07-02")
    n2 = _step_ledger(state2, tmp_path, dry_run=False)
    assert n2 == 0  # already in ledger (keep-FIRST by episode_id)

    # Verify only 1 line in ledger
    ledger_path = oracle_dir / "forward_ledger.jsonl"
    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


def test_ledger_appends_new_episodes(tmp_path):
    """Different episodes → both appended."""
    from scripts.oracle_nightly import _step_ledger

    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()

    state1 = _state([_ep("XLK", "out", "onset")], asof="2026-07-01")
    _step_ledger(state1, tmp_path, dry_run=False)

    state2 = _state([_ep("XLV", "in", "onset")], asof="2026-07-01")
    n2 = _step_ledger(state2, tmp_path, dry_run=False)
    assert n2 == 1

    ledger_path = tmp_path / "oracle" / "forward_ledger.jsonl"
    rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 2


def test_ledger_pit_stamp(tmp_path):
    """Each ledger row has a pit_stamp matching the oracle_state asof."""
    from scripts.oracle_nightly import _step_ledger

    (tmp_path / "oracle").mkdir()
    state = _state([_ep("XLK", "out", "confirmed")], asof="2026-07-03")
    _step_ledger(state, tmp_path, dry_run=False)

    ledger_path = tmp_path / "oracle" / "forward_ledger.jsonl"
    row = json.loads(ledger_path.read_text().splitlines()[0])
    assert row["pit_stamp"] == "2026-07-03"


def test_ledger_cell_tags_on_onset_out(tmp_path):
    """exit_onset_5d cell tag is set for out-direction onset episodes."""
    from scripts.oracle_nightly import _step_ledger

    (tmp_path / "oracle").mkdir()
    state = _state([_ep("XLK", "out", "onset")], asof="2026-07-01")
    _step_ledger(state, tmp_path, dry_run=False)

    row = json.loads((tmp_path / "oracle" / "forward_ledger.jsonl").read_text().strip())
    assert row["cell_tags"].get("exit_onset_5d") is True


def test_ledger_dry_run_writes_nothing(tmp_path):
    """dry_run=True must not create the ledger file."""
    from scripts.oracle_nightly import _step_ledger

    (tmp_path / "oracle").mkdir()
    state = _state([_ep("XLK", "out", "onset")])
    _step_ledger(state, tmp_path, dry_run=True)
    assert not (tmp_path / "oracle" / "forward_ledger.jsonl").exists()


# ---------------------------------------------------------------------------
# Banner: floor logic
# ---------------------------------------------------------------------------

def test_banner_emits_when_above_floor(tmp_path):
    """breadth >= floor + confirmed complex → banner entry written."""
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    # Build state with breadth above floor and a confirmed-out complex
    state = {
        "asof": "2026-07-01",
        "regime": {"n_active_complexes": 2, "breadth": 0.70},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "confirmed", "state": "active_out"},
            {"id": "healthcare", "name": "Healthcare", "name_zh": "医疗",
             "direction": "in", "tier": "confirmed", "state": "active_in"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    result = _step_banner(state, site_dir, dry_run=False)
    assert result is True

    banner_path = site_dir / "wh_banner.json"
    assert banner_path.exists()
    banner = json.loads(banner_path.read_text())
    oracle_entries = [a for a in banner["alerts"] if (a.get("id") or "").startswith("oracle:rotation:")]
    assert len(oracle_entries) == 1
    # Must be bilingual
    assert oracle_entries[0]["title_zh"]
    # Must contain the descriptive-only language
    assert "descriptive" in oracle_entries[0]["title"].lower()


def test_banner_no_emit_below_floor(tmp_path):
    """breadth < floor → no oracle banner entry."""
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    state = {
        "asof": "2026-07-01",
        "regime": {"breadth": 0.50},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "confirmed", "state": "active_out"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    result = _step_banner(state, site_dir, dry_run=False)
    assert result is True
    # File should not exist (or have no oracle entries)
    banner_path = site_dir / "wh_banner.json"
    if banner_path.exists():
        banner = json.loads(banner_path.read_text())
        oracle_entries = [a for a in banner["alerts"] if (a.get("id") or "").startswith("oracle:")]
        assert len(oracle_entries) == 0


def test_banner_no_emit_without_confirmed_complex(tmp_path):
    """breadth above floor but no confirmed-tier complex → no oracle banner."""
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    state = {
        "asof": "2026-07-01",
        "regime": {"breadth": 0.75},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "onset", "state": "active_out"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    result = _step_banner(state, site_dir, dry_run=False)
    assert result is True
    banner_path = site_dir / "wh_banner.json"
    if banner_path.exists():
        banner = json.loads(banner_path.read_text())
        oracle_entries = [a for a in banner["alerts"] if (a.get("id") or "").startswith("oracle:")]
        assert len(oracle_entries) == 0


def test_banner_is_idempotent(tmp_path):
    """Running the banner step twice with the same date replaces the entry (not duplicates)."""
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    state = {
        "asof": "2026-07-01",
        "regime": {"breadth": 0.70},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "confirmed", "state": "active_out"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    _step_banner(state, site_dir, dry_run=False)
    _step_banner(state, site_dir, dry_run=False)

    banner = json.loads((site_dir / "wh_banner.json").read_text())
    oracle_entries = [a for a in banner["alerts"] if (a.get("id") or "").startswith("oracle:rotation:")]
    assert len(oracle_entries) == 1


def test_banner_additive_keeps_other_entries(tmp_path):
    """Banner step preserves existing non-oracle alerts."""
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    # Pre-populate with a non-oracle alert
    existing = {
        "schema": "wh_banner.v1",
        "alerts": [{"id": "wh:001", "title": "Existing alert", "title_zh": "已有提示", "tickers": []}],
    }
    (site_dir / "wh_banner.json").write_text(json.dumps(existing))

    state = {
        "asof": "2026-07-01",
        "regime": {"breadth": 0.70},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "confirmed", "state": "active_out"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    _step_banner(state, site_dir, dry_run=False)

    banner = json.loads((site_dir / "wh_banner.json").read_text())
    ids = {a["id"] for a in banner["alerts"]}
    assert "wh:001" in ids  # existing preserved
    assert any(i.startswith("oracle:rotation:") for i in ids)  # oracle added


def test_banner_dry_run_writes_nothing(tmp_path):
    from scripts.oracle_nightly import _step_banner

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    state = {
        "asof": "2026-07-01",
        "regime": {"breadth": 0.70},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技",
             "direction": "out", "tier": "confirmed", "state": "active_out"},
        ],
        "active_episodes": [],
        "disclaimers": {"display_only": True, "error_rates": {}},
    }
    _step_banner(state, site_dir, dry_run=True)
    assert not (site_dir / "wh_banner.json").exists()
