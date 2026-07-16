"""tests/test_gex_history_snapshot.py — dated per-strike GEX snapshot key derivation.

WP-GEX-SNAPSHOTS (research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md §7):
options_hub/gex/{ROOT}.json is overwritten in place nightly (that key is
UNCHANGED — consumers depend on it); the builder additionally retains the same
payload under a dated key options_hub/gex_history/{ROOT}/{YYYY-MM-DD}.json so
per-strike topology survives as point-in-time history for the
Exposure-by-Strike scrubber + S-TOPO-SIGMA.

Covers the pure helper _gex_history_relpath in scripts/build_options_hub_nightly:
  1. dated key derives from the payload's asof (session date), never wall clock
  2. empty by_strike → None (never write empty history)
  3. missing by_strike key → None
  4. missing asof → None
  5. full R2 key composition under R2_PREFIX

Hermetic: pure-function level — no parquet store, no network, no R2.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# ── ensure repo root on path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.build_options_hub_nightly as builder


def _gex_payload(asof: str = "2025-01-10", with_strikes: bool = True) -> dict:
    """Minimal options_hub.gex/v1-shaped payload (mirrors TestCompletenessGuard)."""
    return {
        "schema": "options_hub.gex/v1",
        "asof": asof,
        "root": "SPY",
        "spot_ref": 500.0,
        "by_strike": [{"strike": 500.0, "gex_bn": 1.23}] if with_strikes else [],
        "coverage": {"n_contracts": 1 if with_strikes else 0, "asof": asof,
                     "oi_date": "t-1", "n_days": 1, "since": asof},
    }


class TestGexHistoryRelpath:
    """Key/date derivation + empty-payload guard for the dated GEX snapshot."""

    def test_key_derives_from_payload_asof(self):
        rel = builder._gex_history_relpath("SPY", _gex_payload(asof="2025-01-10"))
        assert rel == "gex_history/SPY/2025-01-10.json"

    def test_key_uses_session_date_not_wall_clock(self):
        """A delayed/manual re-run must land on the payload's session date."""
        stale_session = "2020-06-15"  # far from any plausible run date
        rel = builder._gex_history_relpath("QQQ", _gex_payload(asof=stale_session))
        assert rel == f"gex_history/QQQ/{stale_session}.json"
        assert str(date.today()) not in rel, "dated key must never use wall clock"

    def test_empty_by_strike_skips(self):
        """Empty by_strike → no dated write (never write empty history)."""
        assert builder._gex_history_relpath("SPY", _gex_payload(with_strikes=False)) is None

    def test_missing_by_strike_key_skips(self):
        assert builder._gex_history_relpath("SPY", {"asof": "2025-01-10"}) is None

    def test_missing_asof_skips(self):
        payload = _gex_payload()
        payload.pop("asof")
        assert builder._gex_history_relpath("SPY", payload) is None

    def test_r2_key_composition(self):
        """Full R2 key = R2_PREFIX + relpath → options_hub/gex_history/{ROOT}/{date}.json."""
        rel = builder._gex_history_relpath("IWM", _gex_payload(asof="2025-01-10"))
        assert f"{builder.R2_PREFIX}{rel}" == "options_hub/gex_history/IWM/2025-01-10.json"
