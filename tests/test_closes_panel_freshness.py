"""Per-column freshness across the US breadth close-cache readers.

Closes the chip left open by research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md
§4 (3): the ~19 consumers of data/{breadth,smallcap_breadth,midcap_breadth,
russell_breadth}/_closes_cache.parquet that read the same union-forever archives with
no freshness handling.

Two distinct defects are pinned here, and they need different fixes:

  1. MERGE (lib/closes_panel.py) — the caches are union-forever by design, so an index
     migrant keeps a column in the tier it LEFT, frozen on its exit date, while the tier
     it JOINED carries a live one. Every reader merged with a fixed tier order and kept
     the FIRST duplicate, i.e. the DEAD column, discarding a live one from the same
     merge. Freshness now wins; tier order only breaks ties.

  2. RESURRECTION (engine/equity_factors.py) — `px.ffill().iloc[-1]` carries a genuinely
     dead feed's last close to the panel tip and publishes it as today's price, feeding
     mktcap -> value yields -> composite rank. Measured at the 2026-07-31 vintage: FLEX
     ffilled to 147.61 against a true 113.75 (+29.8%).

The tests use synthetic panels so the arithmetic is deterministic; the merge and the
gate are the REAL ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.closes_panel import merge_close_caches  # noqa: E402

_TIERS = ("breadth", "smallcap_breadth", "midcap_breadth")


def _write(tmp: Path, group: str, frame: pd.DataFrame) -> None:
    d = tmp / group
    d.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(d / "_closes_cache.parquet")


def _sessions(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2026-01-05", periods=n)


class TestFreshestColumnWins:
    """Defect 1 — tier order must not hand a migrant its dead column."""

    def test_live_column_beats_a_frozen_one_in_an_earlier_tier(self, tmp_path):
        idx = _sessions(40)
        dead = pd.Series(np.arange(40, dtype=float), index=idx)
        dead.iloc[20:] = np.nan                      # left the index on session 20
        live = pd.Series(np.arange(40, dtype=float), index=idx)
        live.iloc[:20] = np.nan                      # joined the new tier there
        _write(tmp_path, "breadth", pd.DataFrame({"MIG": dead}))
        _write(tmp_path, "midcap_breadth", pd.DataFrame({"MIG": live}))

        panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        # keep-first would have taken `breadth` and gone NaN at the tip.
        assert meta["source"]["MIG"] == "midcap_breadth"
        assert panel["MIG"].last_valid_index() == idx[-1]
        assert meta["behind"]["MIG"] == 0
        assert "MIG" in meta["rescued"]

    def test_tier_order_still_breaks_ties(self, tmp_path):
        """Unchanged behaviour for every ticker that is NOT a migrant — both columns
        equally fresh means the caller's priority order still decides."""
        idx = _sessions(30)
        _write(tmp_path, "breadth", pd.DataFrame({"AAA": pd.Series(1.0, index=idx)}))
        _write(tmp_path, "midcap_breadth", pd.DataFrame({"AAA": pd.Series(2.0, index=idx)}))

        panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert meta["source"]["AAA"] == "breadth"
        assert panel["AAA"].iloc[-1] == 1.0
        assert not meta["rescued"]

    def test_column_coverage_is_invariant(self, tmp_path):
        """The merge may never SHRINK the ticker set — an admission lane that loses its
        price source is structurally ungradeable forever
        (tests/test_us_board_ledger_continuity.py Section 1)."""
        idx = _sessions(30)
        _write(tmp_path, "breadth",
               pd.DataFrame({"AAA": pd.Series(1.0, index=idx),
                             "SHARED": pd.Series(1.0, index=idx)}))
        _write(tmp_path, "midcap_breadth",
               pd.DataFrame({"BBB": pd.Series(2.0, index=idx),
                             "SHARED": pd.Series(2.0, index=idx)}))

        panel, _ = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert set(panel.columns) == {"AAA", "BBB", "SHARED"}

    def test_a_column_with_data_beats_a_never_populated_one(self, tmp_path):
        """The in-constituents FI/MMC case: an all-NaN column must never win."""
        idx = _sessions(30)
        _write(tmp_path, "breadth", pd.DataFrame({"XYZ": pd.Series(np.nan, index=idx)}))
        _write(tmp_path, "midcap_breadth", pd.DataFrame({"XYZ": pd.Series(5.0, index=idx)}))

        panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert meta["source"]["XYZ"] == "midcap_breadth"
        assert panel["XYZ"].iloc[-1] == 5.0

    def test_never_populated_everywhere_is_reported_not_dropped(self, tmp_path):
        idx = _sessions(30)
        _write(tmp_path, "breadth", pd.DataFrame({"DEAD": pd.Series(np.nan, index=idx)}))

        panel, meta = merge_close_caches(("breadth",), data_dir=tmp_path)

        assert "DEAD" in panel.columns          # never fail-dark (CSP-R1)
        assert meta["behind"]["DEAD"] == -1     # sentinel, distinct from "0 days behind"


class TestStitchIsMeasurementGated:
    """The naive repair loses history: a migrant's new column starts on the migration
    date, so vol/beta (min_price_history_d=150) go NaN. History is restored ONLY from a
    donor column proven bit-identical on the overlap — never across a basis difference
    (the #2120 seam class)."""

    def _pair(self, tmp_path, donor_scale: float):
        idx = _sessions(60)
        base = pd.Series(np.linspace(10.0, 20.0, 60), index=idx)
        dead = base.copy()
        dead.iloc[45:] = np.nan                  # long history, stops early
        live = base.copy() * 1.0
        live.iloc[:40] = np.nan                  # short history, runs to the tip
        _write(tmp_path, "breadth", pd.DataFrame({"MIG": dead * donor_scale}))
        _write(tmp_path, "midcap_breadth", pd.DataFrame({"MIG": live}))
        return idx

    def test_identical_basis_restores_the_pre_migration_history(self, tmp_path):
        idx = self._pair(tmp_path, donor_scale=1.0)

        panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert "MIG" in meta["stitched"]
        assert panel["MIG"].notna().sum() == 60           # full span, not just the live 20
        assert panel["MIG"].last_valid_index() == idx[-1]
        # and no fabricated jump anywhere across the junction
        assert panel["MIG"].pct_change().abs().max() < 0.05

    def test_a_different_adjustment_basis_is_never_spliced(self, tmp_path):
        """CPB's real shape: the two lanes differ by a constant 1.69%. Stitching would
        manufacture a fake one-day return, so the live column is kept whole and the
        shorter history is accepted instead."""
        self._pair(tmp_path, donor_scale=1.0169)

        panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert "MIG" not in meta["stitched"]
        assert panel["MIG"].notna().sum() == 20           # live column only
        assert meta["source"]["MIG"] == "midcap_breadth"

    def test_too_little_overlap_is_not_evidence_of_a_shared_basis(self, tmp_path):
        idx = _sessions(60)
        base = pd.Series(np.linspace(10.0, 20.0, 60), index=idx)
        dead = base.copy()
        dead.iloc[42:] = np.nan
        live = base.copy()
        live.iloc[:40] = np.nan          # only 2 overlapping sessions
        _write(tmp_path, "breadth", pd.DataFrame({"MIG": dead}))
        _write(tmp_path, "midcap_breadth", pd.DataFrame({"MIG": live}))

        _panel, meta = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert "MIG" not in meta["stitched"]


class TestDegradesNeverCrashes:
    def test_missing_group_is_skipped(self, tmp_path):
        idx = _sessions(10)
        _write(tmp_path, "breadth", pd.DataFrame({"AAA": pd.Series(1.0, index=idx)}))

        panel, meta = merge_close_caches(_TIERS, data_dir=tmp_path)

        assert list(panel.columns) == ["AAA"]
        assert meta["tip"] == idx[-1]

    def test_no_groups_at_all_returns_empty_not_an_exception(self, tmp_path):
        panel, meta = merge_close_caches(_TIERS, data_dir=tmp_path)

        assert panel.empty
        assert meta["tip"] is None

    def test_a_corrupt_cache_does_not_kill_the_merge(self, tmp_path):
        idx = _sessions(10)
        _write(tmp_path, "breadth", pd.DataFrame({"AAA": pd.Series(1.0, index=idx)}))
        bad = tmp_path / "midcap_breadth"
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "_closes_cache.parquet").write_bytes(b"not a parquet")

        panel, _ = merge_close_caches(("breadth", "midcap_breadth"), data_dir=tmp_path)

        assert list(panel.columns) == ["AAA"]


class TestStalePriceGate:
    """Defect 2 — a genuinely dead feed must not be ffilled into a live quote."""

    def _px(self, frozen_days: int, n_names: int = 10) -> pd.DataFrame:
        idx = pd.bdate_range("2026-01-05", periods=60)
        data = {f"OK{i}": pd.Series(np.linspace(10, 20, 60), index=idx)
                for i in range(n_names)}
        dead = pd.Series(np.linspace(10, 20, 60), index=idx)
        # NaN the tail so the last valid bar is `frozen_days` calendar days behind.
        cutoff = idx[-1] - pd.Timedelta(days=frozen_days)
        dead[dead.index > cutoff] = np.nan
        data["FROZEN"] = dead
        return pd.DataFrame(data, index=idx)

    def test_a_feed_past_the_7_day_law_is_flagged(self, capsys):
        from engine.equity_factors import _stale_price_columns

        stale = _stale_price_columns(self._px(frozen_days=30))

        assert stale == {"FROZEN"}
        out = capsys.readouterr().out
        assert out.startswith("::warning") or "\n::warning" in out

    def test_a_feed_inside_the_law_is_untouched(self):
        from engine.equity_factors import _stale_price_columns

        # 7 calendar days is the worst structural NYSE closure and passes (strict `>`).
        assert _stale_price_columns(self._px(frozen_days=7)) == set()

    def test_the_law_is_imported_not_restated(self):
        """One staleness constant across the ledger gate, scan admission and here."""
        from engine.name_score_grader import _MAX_BAR_LAG_DAYS

        assert _MAX_BAR_LAG_DAYS == 7

    def test_mass_staleness_disarms_the_gate_rather_than_blanking_the_page(self, capsys):
        """R2 circuit breaker: a universe-wide freeze is a collector outage, and
        stripping most of the factor page would itself be fail-dark (CSP-R1)."""
        from engine.equity_factors import _stale_price_columns

        idx = pd.bdate_range("2026-01-05", periods=60)
        cutoff = idx[-1] - pd.Timedelta(days=30)
        cols = {}
        for i in range(10):                      # 8/10 stale = 80%, over the 20% breaker
            s = pd.Series(np.linspace(10, 20, 60), index=idx)
            if i < 8:
                s[s.index > cutoff] = np.nan
            cols[f"N{i}"] = s

        stale = _stale_price_columns(pd.DataFrame(cols, index=idx))

        assert stale == set()                    # DISARMED, nothing demoted
        assert "disarmed" in capsys.readouterr().out

    def test_an_all_nan_column_is_not_counted_as_a_demotion(self):
        """A never-populated column carries no price to resurrect either way."""
        from engine.equity_factors import _stale_price_columns

        px = self._px(frozen_days=0)
        px["NEVER"] = np.nan

        assert "NEVER" not in _stale_price_columns(px)

    def test_empty_panel_fails_open(self):
        from engine.equity_factors import _stale_price_columns

        assert _stale_price_columns(pd.DataFrame()) == set()


class TestStalePriceNeverReachesAFactor:
    """The end-to-end shape the defect actually took: a dead feed's ffilled close
    becoming `price` -> mktcap -> value, and a dead feed's two ffilled endpoints
    becoming a fabricated 0.0% trailing return in the leadership spreads."""

    def test_ffill_would_resurrect_but_the_gate_nulls_it(self):
        from engine.equity_factors import _stale_price_columns

        idx = pd.bdate_range("2026-01-05", periods=60)
        # 10 live names against 1 dead one keeps the stale share under the 20% breaker,
        # so the gate stays ARMED and this exercises the demotion rather than the disarm.
        px = pd.DataFrame({f"LIVE{i}": pd.Series(np.linspace(10, 20, 60), index=idx)
                           for i in range(10)})
        dead = pd.Series(np.linspace(10, 20, 60), index=idx)
        dead[dead.index > idx[-1] - pd.Timedelta(days=30)] = np.nan
        px["DEAD"] = dead
        frozen_close = float(dead.dropna().iloc[-1])

        stale = _stale_price_columns(px)
        last_px = px.ffill().iloc[-1]
        assert last_px["DEAD"] == pytest.approx(frozen_close)   # the resurrection
        last_px[list(stale)] = np.nan                           # the gate

        assert pd.isna(last_px["DEAD"])
        assert last_px["LIVE0"] == pytest.approx(20.0)          # live names untouched

    def test_a_feed_dead_longer_than_the_window_fabricates_a_flat_return(self):
        """Both trailing endpoints ffill to the same stale close -> exactly 0.0, which
        would then be averaged into a quintile leadership spread as if it were real."""
        from engine.equity_factors import _stale_price_columns

        idx = pd.bdate_range("2026-01-05", periods=60)
        dead = pd.Series(np.linspace(10, 20, 60), index=idx)
        dead.iloc[30:] = np.nan                  # dead for the last 30 sessions
        # live company so the stale share stays under the 20% breaker (gate ARMED)
        px = pd.DataFrame({f"LIVE{i}": pd.Series(np.linspace(10, 20, 60), index=idx)
                           for i in range(10)})
        px["DEAD"] = dead

        lw = 20                                  # window shorter than the freeze
        trailing = (px.ffill().iloc[-1] / px.ffill().iloc[-lw] - 1.0)
        assert trailing["DEAD"] == pytest.approx(0.0)           # fabricated flat

        trailing[list(_stale_price_columns(px))] = np.nan
        assert pd.isna(trailing["DEAD"])
