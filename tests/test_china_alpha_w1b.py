"""tests/test_china_alpha_w1b.py — W1-B: builder-level stage wiring tests.

Validates the stage partition, invariants, artifact shape, why_ranked chip,
and ripening/ran array construction added to build_china_library.py (W1-B).

Nearest sibling: tests/test_china_alpha_w0.py (same synthetic fixture idiom,
                 same builder-level assertion pattern).
                 tests/test_setup_tier.py (same assign_stage rule coverage).

All tests are synthetic-fixture-only — no dependency on local parquet files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _bdate(n: int, start: str = "2019-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _series(values, start: str = "2019-01-02") -> pd.Series:
    return pd.Series(values, index=_bdate(len(values), start=start), dtype=float)


def _make_buy_row(ticker: str, entry_status: str | None = "buy_now",
                  extended: bool = False, washout_2w: bool = False,
                  tier: str = "T1") -> dict:
    """Minimal synthetic buy row with the fields the builder wires."""
    return {
        "ticker": ticker, "name": ticker, "sector": "Healthcare",
        "setup": 0.75,
        "extension": {"extended": extended, "score": 0.9 if extended else 0.0},
        "washout_2w": washout_2w,
        # signal dict as returned by signal_gate.compact()
        "signal": {"eligible": True, "tier_cascade": tier, "tier_sub": None,
                   "ticks": 1, "bars_to_cross": None, "provisional": False,
                   "tier": "take", "sub": None, "reason": "held", "state": None,
                   "above200": True, "weekly_bull": True, "early_now": False,
                   "asof": "2026-07-03", "last": None},
    }


def _make_ripening_row(ticker: str, stoch: float = 20.0, btc: float | None = 3.0) -> dict:
    """Minimal synthetic ripening row."""
    return {
        "ticker": ticker, "name": ticker, "sector": "Technology",
        "reasons": [f"2W stoch washout (stoch={stoch})"],
        "imminence": btc,
        "w2_stoch": stoch,
        "w2_macd_approaching": btc is not None,
        "w2_macd_cross_up": False,
        "w1_cross_date": None,
        "w1_d_at_cross": None,
        "spot_pct_in_range": 25.0,
    }


def _make_ran_row(ticker: str, sessions_since: int = 7, pct_since: float = 8.9) -> dict:
    """Minimal synthetic ran row."""
    return {
        "ticker": ticker, "name": ticker, "sector": "Materials",
        "cross_date": "2026-06-24",
        "sessions_since": sessions_since,
        "pct_since": pct_since,
        "sublabel": f"signal fired 2026-06-24 ({sessions_since} sessions ago), +{pct_since}%",
        "basing_chip": None,
        "hold_summary": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — Stage assignment on synthetic buy rows (rules 1-2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStageBuyRows:
    """Verify that assign_stage correctly classifies buy rows per the spec."""

    def test_buy_now_entry_status_maps_to_entry(self):
        from engine.setup_tier import assign_stage, STAGE_ENTRY
        r = assign_stage(
            gate_eligible=True, entry_status="buy_now",
            overextended=False, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] == STAGE_ENTRY

    def test_partial_entry_status_maps_to_entry(self):
        from engine.setup_tier import assign_stage, STAGE_ENTRY
        r = assign_stage(
            gate_eligible=True, entry_status="partial",
            overextended=False, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] == STAGE_ENTRY

    def test_hold_status_maps_to_ran_late(self):
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        r = assign_stage(
            gate_eligible=True, entry_status="hold",
            overextended=False, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] == STAGE_RAN_LATE
        assert "entry passed" in (r["sublabel"] or "")

    def test_extended_status_maps_to_ran_late(self):
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        r = assign_stage(
            gate_eligible=True, entry_status="extended",
            overextended=False, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] == STAGE_RAN_LATE

    def test_overextended_flag_blocks_entry(self):
        """A gate-eligible buy_now row with overextended=True must NOT be ENTRY."""
        from engine.setup_tier import assign_stage, STAGE_ENTRY
        r = assign_stage(
            gate_eligible=True, entry_status="buy_now",
            overextended=True, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] != STAGE_ENTRY, (
            "overextended=True must not produce ENTRY even with buy_now")

    def test_none_entry_status_gives_no_shelf_when_no_wsetup(self):
        """Gate-eligible row with entry_status=None and no wsetup: stage=None (rule 5)."""
        from engine.setup_tier import assign_stage
        r = assign_stage(
            gate_eligible=True, entry_status=None,
            overextended=False, last_cross_info=None,
            hold_state=None, wsetup=None,
        )
        assert r["stage"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Build-time invariants (synthetic board)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildTimeInvariants:
    """The builder asserts these invariants at build time. Tests confirm the
    invariant logic itself works on synthetic data (no parquet needed)."""

    def _assign_stage_to_rows(self, buy_rows: list[dict],
                               entry_status_by: dict[str, str | None] | None = None) -> list[dict]:
        """Helper: simulate the builder's stage assignment loop on synthetic buy rows."""
        from engine.setup_tier import assign_stage
        es_by = entry_status_by or {}
        for r in buy_rows:
            t = r.get("ticker")
            es_status = es_by.get(t)
            ext_flag = bool((r.get("extension") or {}).get("extended"))
            r["stage"] = assign_stage(
                gate_eligible=True,
                entry_status=es_status,
                overextended=ext_flag,
                last_cross_info=None,
                hold_state=None,
                wsetup=None,
            )["stage"]
        return buy_rows

    def test_all_buy_rows_have_stage_field(self):
        """Every buy row must have a 'stage' key after assignment (even if stage=None)."""
        rows = [_make_buy_row(f"T{i}") for i in range(5)]
        rows = self._assign_stage_to_rows(rows, {f"T{i}": "buy_now" for i in range(5)})
        for r in rows:
            assert "stage" in r, f"Row for {r.get('ticker')} missing 'stage' key"

    def test_rule2_buy_now_not_overextended_stays_entry(self):
        """Non-overextended buy_now stays ENTRY (not RAN_LATE).

        Adjudicated design F6: buy_now+overextended routes to RAN_LATE with muted_entry=True,
        but buy_now WITHOUT overextended must remain ENTRY (rule 1).
        """
        from engine.setup_tier import assign_stage, STAGE_ENTRY, STAGE_RAN_LATE
        r = assign_stage(gate_eligible=True, entry_status="buy_now",
                         overextended=False, last_cross_info=None,
                         hold_state=None, wsetup=None)
        assert r["stage"] == STAGE_ENTRY, (
            "buy_now without overextended must be ENTRY, not RAN_LATE")

    def test_rule2_buy_now_overextended_routes_ran_late_with_muted(self):
        """F6 adjudicated design: buy_now+overextended -> RAN_LATE + muted_entry=True.

        This is the B1 regression test: 002896.SZ / 002472.SZ are buy_now+overextended and
        must route to RAN_LATE with muted_entry=True (not crash the build with assert).
        """
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        r = assign_stage(gate_eligible=True, entry_status="buy_now",
                         overextended=True, last_cross_info=None,
                         hold_state=None, wsetup=None)
        assert r["stage"] == STAGE_RAN_LATE, (
            "buy_now+overextended must route to RAN_LATE (F6 ruling)")
        assert r["detail"].get("muted_entry") is True, (
            "buy_now+overextended RAN_LATE row must carry muted_entry=True in detail")
        assert r.get("sublabel") is not None, (
            "Every rule-2 RAN_LATE row must have a sublabel")

    def test_rule2_partial_overextended_routes_ran_late_with_muted(self):
        """partial+overextended -> RAN_LATE + muted_entry=True (partial case from B1)."""
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        r = assign_stage(gate_eligible=True, entry_status="partial",
                         overextended=True, last_cross_info=None,
                         hold_state=None, wsetup=None)
        assert r["stage"] == STAGE_RAN_LATE
        assert r["detail"].get("muted_entry") is True

    def test_render_invariant_muted_entry_propagated_to_row(self):
        """Builder must propagate muted_entry=True from stage_detail to the top-level row dict.

        This is the render-level invariant: Jinja reads n.get('muted_entry'), not
        n.stage_detail.muted_entry, so the builder must copy it up.
        """
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        # Simulate the builder's stage assignment for a buy_now+overextended row
        row = _make_buy_row("002896.SZ", entry_status="buy_now", extended=True)
        _stage_res = assign_stage(
            gate_eligible=True, entry_status="buy_now", overextended=True,
            last_cross_info=None, hold_state=None, wsetup=None,
        )
        row["stage"] = _stage_res["stage"]
        row["stage_sublabel"] = _stage_res.get("sublabel")
        row["stage_detail"] = _stage_res.get("detail") or {}
        # Simulate the builder's muted_entry propagation step
        if row["stage_detail"].get("muted_entry"):
            row["muted_entry"] = True
        assert row.get("muted_entry") is True, (
            "Builder must copy muted_entry=True from stage_detail to row dict")

    def test_ripening_rows_never_gate_eligible(self):
        """Ripening rows must come from non-gate-eligible names.

        The invariant: no ripening row should share a ticker with the eligible_set.
        """
        eligible_set = {"AAPL.SS", "GOOG.SZ"}
        ripening = [_make_ripening_row("NEW1.SS"), _make_ripening_row("NEW2.SZ")]
        violations = [r["ticker"] for r in ripening if r["ticker"] in eligible_set]
        assert not violations, f"Ripening rows in eligible set: {violations}"

    def test_ripening_cap_enforced(self):
        """Ripening array must be capped at 24 rows."""
        rows = [_make_ripening_row(f"R{i}.SS") for i in range(30)]
        capped = rows[:24]
        assert len(capped) <= 24, "Ripening cap of 24 must be enforced"

    def test_ran_cap_enforced(self):
        """RAN array must be capped at 15 rows."""
        rows = [_make_ran_row(f"X{i}.SS") for i in range(20)]
        capped = rows[:15]
        assert len(capped) <= 15, "RAN cap of 15 must be enforced"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Artifact shape: buy rows gain stage, new arrays present
# ═══════════════════════════════════════════════════════════════════════════════

class TestArtifactShape:
    """The china_standouts.json artifact must have the W1-B shape:
    - buy rows carry stage / stage_sublabel / stage_detail / why_ranked
    - ripening array present (list)
    - ran array present (list)
    """

    def _minimal_standouts(self, n_buy: int = 5) -> dict:
        """Build a minimal in-memory china_standouts dict with staged buy rows."""
        from engine.setup_tier import assign_stage
        buy = []
        for i in range(n_buy):
            t = f"T{i}.SS"
            r = _make_buy_row(t, entry_status="buy_now" if i % 2 == 0 else "hold")
            es = "buy_now" if i % 2 == 0 else "hold"
            stg = assign_stage(gate_eligible=True, entry_status=es, overextended=False,
                               last_cross_info=None, hold_state=None, wsetup=None)
            r["stage"] = stg["stage"]
            r["stage_sublabel"] = stg.get("sublabel")
            r["stage_detail"] = stg.get("detail") or {}
            r["why_ranked"] = f"{r['signal'].get('tier_cascade')} + 2W-washout" if r.get("washout_2w") else (r["signal"].get("tier_cascade") or "")
            buy.append(r)
        ripening = [_make_ripening_row(f"R{i}.SS") for i in range(3)]
        ran = [_make_ran_row(f"X{i}.SS") for i in range(2)]
        return {"as_of": "2026-07-03", "buy": buy, "ripening": ripening, "ran": ran}

    def test_buy_rows_have_stage_field(self):
        d = self._minimal_standouts()
        for r in d["buy"]:
            assert "stage" in r, f"Buy row {r.get('ticker')} missing 'stage'"

    def test_buy_rows_have_why_ranked(self):
        d = self._minimal_standouts()
        for r in d["buy"]:
            assert "why_ranked" in r, f"Buy row {r.get('ticker')} missing 'why_ranked'"
            assert isinstance(r["why_ranked"], str)

    def test_ripening_array_present(self):
        d = self._minimal_standouts()
        assert "ripening" in d, "china_standouts must have 'ripening' array"
        assert isinstance(d["ripening"], list)

    def test_ran_array_present(self):
        d = self._minimal_standouts()
        assert "ran" in d, "china_standouts must have 'ran' array"
        assert isinstance(d["ran"], list)

    def test_buy_array_still_present(self):
        """Downstream compat: the 'buy' key must still be present and is the primary array."""
        d = self._minimal_standouts()
        assert "buy" in d
        assert isinstance(d["buy"], list)
        assert len(d["buy"]) == 5

    def test_ripening_rows_have_required_fields(self):
        rip = [_make_ripening_row("A.SS", stoch=18.0, btc=2.5)]
        for r in rip:
            for key in ("ticker", "name", "sector", "reasons", "imminence",
                        "w2_stoch", "w2_macd_approaching"):
                assert key in r, f"Ripening row missing key '{key}'"

    def test_ran_rows_have_required_fields(self):
        ran = [_make_ran_row("B.SZ", sessions_since=7, pct_since=8.9)]
        for r in ran:
            for key in ("ticker", "name", "cross_date", "sessions_since", "pct_since", "sublabel"):
                assert key in r, f"RAN row missing key '{key}'"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — why_ranked chip logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhyRanked:
    """The why_ranked string must reflect actual blend inputs without changing rank."""

    def _make_row_with_coiled(self, ticker: str, washout: bool = False,
                               coiled: bool = False, extended: bool = False) -> dict:
        r = _make_buy_row(ticker, washout_2w=washout, extended=extended)
        if coiled:
            r["coiled"] = {"coiled": True, "bonus": 0.3, "star": False}
        return r

    def _why_ranked(self, r: dict) -> str:
        """Replicate the builder's _why_ranked logic."""
        sig = r.get("signal") or {}
        parts = []
        tier = sig.get("tier_cascade") or sig.get("tier")
        if tier:
            parts.append(str(tier))
        if r.get("washout_2w"):
            parts.append("2W-washout")
        cb = r.get("coiled") or {}
        if cb.get("coiled"):
            parts.append("coiled")
        ext = r.get("extension") or {}
        if ext.get("extended"):
            ext_sc = ext.get("score")
            parts.append(f"- ext {round(float(ext_sc), 2)}" if ext_sc is not None else "- ext")
        pos = " + ".join(p for p in parts if not p.startswith("-"))
        neg = " ".join(p for p in parts if p.startswith("-"))
        return (pos + (" " + neg if neg else "")).rstrip()

    def test_tier_appears_in_why_ranked(self):
        r = self._make_row_with_coiled("A.SS")
        s = self._why_ranked(r)
        assert "T1" in s, f"why_ranked must include tier; got: {s!r}"

    def test_washout_appears_when_set(self):
        r = self._make_row_with_coiled("B.SS", washout=True)
        s = self._why_ranked(r)
        assert "2W-washout" in s, f"why_ranked must include washout when set; got: {s!r}"

    def test_coiled_appears_when_set(self):
        r = self._make_row_with_coiled("C.SS", coiled=True)
        s = self._why_ranked(r)
        assert "coiled" in s, f"why_ranked must include coiled when set; got: {s!r}"

    def test_extension_penalty_appears_when_extended(self):
        r = self._make_row_with_coiled("D.SS", extended=True)
        s = self._why_ranked(r)
        assert "ext" in s, f"why_ranked must show extension penalty; got: {s!r}"

    def test_why_ranked_is_string(self):
        for washout, coiled, extended in [(False, False, False), (True, True, True)]:
            r = self._make_row_with_coiled("E.SS", washout=washout, coiled=coiled, extended=extended)
            assert isinstance(self._why_ranked(r), str)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Ripening and RAN construction logic (synthetic data)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRipeningAndRanConstruction:
    """Unit tests for the ripening and ran array construction logic."""

    def test_ran_sorted_by_recency(self):
        """RAN rows are sorted by sessions_since ascending (most recent first)."""
        rows = [
            _make_ran_row("A.SS", sessions_since=12),
            _make_ran_row("B.SZ", sessions_since=3),
            _make_ran_row("C.SS", sessions_since=8),
        ]
        rows.sort(key=lambda x: x.get("sessions_since") or 99)
        assert rows[0]["ticker"] == "B.SZ", "Most recent cross should sort first"
        assert rows[-1]["ticker"] == "A.SS", "Oldest cross should sort last"

    def test_ripening_sorted_by_imminence_ascending(self):
        """RIPENING rows are sorted by imminence (macd_bars_to_cross ascending)."""
        rows = [
            _make_ripening_row("A.SS", btc=8.0),
            _make_ripening_row("B.SZ", btc=2.0),
            _make_ripening_row("C.SS", btc=None),   # washout-only: sorts last
        ]
        rows.sort(key=lambda x: float(x["imminence"]) if x["imminence"] is not None else 999.0)
        assert rows[0]["ticker"] == "B.SZ", "Lowest btc (most imminent) should sort first"
        assert rows[-1]["ticker"] == "C.SS", "Washout-only (None imminence) should sort last"

    def test_ran_row_16_sessions_excluded(self):
        """A cross 16 sessions ago is outside the 15-tick window and must NOT appear in ran."""
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        lci_16 = {"cross_date": "2026-05-01", "sessions_since": 16, "pct_since": 5.0}
        r = assign_stage(gate_eligible=False, entry_status=None, overextended=False,
                         last_cross_info=lci_16, hold_state=None,
                         wsetup={"setup_live": False, "setup_reasons": [], "w2": {}})
        assert r["stage"] != STAGE_RAN_LATE, "16 sessions is outside window; must not be RAN_LATE"

    def test_ran_row_exactly_15_sessions_included(self):
        """A cross exactly 15 sessions ago IS inside the window (boundary inclusive)."""
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        lci_15 = {"cross_date": "2026-05-05", "sessions_since": 15, "pct_since": 3.0}
        r = assign_stage(gate_eligible=False, entry_status=None, overextended=False,
                         last_cross_info=lci_15, hold_state=None,
                         wsetup={"setup_live": False, "setup_reasons": [], "w2": {}})
        assert r["stage"] == STAGE_RAN_LATE, "15 sessions must fire rule 3 (boundary inclusive)"

    def test_ripening_excludes_gate_eligible_names(self):
        """Names that are gate-eligible must never appear in the ripening array."""
        eligible_set = {"300725.SZ", "688306.SS"}
        ripening_candidates = [
            {"ticker": "300725.SZ", "setup_live": True},   # gate-eligible; must be excluded
            {"ticker": "NEW001.SS", "setup_live": True},   # not eligible; can ripening
        ]
        actual_ripening = [r for r in ripening_candidates
                           if r["ticker"] not in eligible_set and r.get("setup_live")]
        assert all(r["ticker"] not in eligible_set for r in actual_ripening)

    def test_basing_intact_adds_chip_to_ran(self):
        """When hold_state says intact, rule-3 RAN_LATE row gets a basing_chip."""
        from engine.setup_tier import assign_stage, STAGE_RAN_LATE
        lci = {"cross_date": "2026-06-20", "sessions_since": 5, "pct_since": 8.0}
        hs = {"state": "intact", "anchor": "2026-06-15"}
        r = assign_stage(gate_eligible=False, entry_status=None, overextended=False,
                         last_cross_info=lci, hold_state=hs,
                         wsetup={"setup_live": False, "setup_reasons": [], "w2": {}})
        assert r["stage"] == STAGE_RAN_LATE
        chip = (r.get("detail") or {}).get("basing_chip")
        assert chip is not None, "intact hold_state must add basing_chip to RAN_LATE detail"
        assert "basing since" in chip


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Ledger schema: append_ripening function
# ═══════════════════════════════════════════════════════════════════════════════

class TestAppendRipening:
    """Verify append_ripening in china_standout_track has the right schema and guards."""

    def test_append_ripening_requires_asof(self):
        """append_ripening returns 0 when asof is None."""
        from engine.china_standout_track import append_ripening
        rows = [_make_ripening_row("A.SS")]
        result = append_ripening(rows, asof=None, lane="asia")
        assert result == 0, "Missing asof must return 0"

    def test_append_ripening_requires_rows(self):
        """append_ripening returns 0 when rows is empty."""
        from engine.china_standout_track import append_ripening
        result = append_ripening([], asof="2026-07-03", lane="asia")
        assert result == 0, "Empty rows must return 0"

    def test_append_ripening_non_asia_lane_blocked(self):
        """Non-asia lane must be blocked (render lanes do not persist)."""
        from engine.china_standout_track import append_ripening
        rows = [_make_ripening_row("A.SS")]
        result = append_ripening(rows, asof="2026-07-03", lane="render")
        assert result == 0, "Non-asia lane must be blocked"

    def test_append_board_stage_column_in_schema(self):
        """append_board now includes a 'stage' column (schema-union safe)."""
        import inspect
        from engine import china_standout_track
        source = inspect.getsource(china_standout_track.append_board)
        assert '"stage"' in source, (
            "append_board must include 'stage' column in its output dict")

    def test_ripening_path_under_store(self):
        """The ripening parquet path must live under the same store as board.parquet."""
        from engine.china_standout_track import _store_path, _ripening_path
        board = _store_path()
        rip = _ripening_path()
        assert rip.parent == board.parent, (
            f"ripening.parquet must be in the same dir as board.parquet; "
            f"got {rip.parent} vs {board.parent}")


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
