"""The extension panel must not mix a 5-session equity calendar with 24/7 crypto.

``scripts/build_stock_library`` builds its panel from the whole library universe, which
carries both equities and the ``yahoo.tickers.crypto`` names, so one panel is indexed on
the UNION of the two calendars.  That broke the read in two ways:

  * ``engine.extension.extension_signals`` used to take ONE global ``.iloc[-1]`` and
    drop every ticker whose latest cell was NaN, so on any build whose newest calendar
    date is not an equity session — every weekend, every US market holiday — ``ext_map``
    collapsed to the crypto names alone.  Downstream that zeroed the ``us_prophet_v1``
    runway leg and stripped the ez-term and the parabolic/stretched grade floor out of
    ``conviction.risk.components.ext``.  That HALF is now healed inside the module:
    the read anchors to the newest row clearing ``ANCHOR_COVERAGE_FLOOR``, and a
    crypto-only row is far under the floor, so it is skipped.
  * the union index still injects ~189 all-NaN weekend rows into every 200-row window,
    so ``px.rolling(200)`` averages far fewer real sessions and NO equity's ext_z is the
    back-tested quantity.  The floor cannot see that, and it never will.

And the anchor adds two more reasons to split.  Walking back to the last well-covered
row means the mixed panel reads CRYPTO off the equity Friday too, throwing away the
Saturday and Sunday sessions crypto actually traded — and over a LONG weekend the walk
back is more than ``ANCHOR_MAX_AGE`` rows, so the mixed panel serves nothing at all
rather than backdating the whole universe.  (Measured on the committed
``data/intl_search/closes.parquet``, a real union-of-calendars store: ~11% of its
sessions land in a coverage band that is empty on every single-calendar store —
tests/test_extension.py::TestTheFloorIsCalibratedOnRealSessions.)

The equity side of the fixture carries more than ``ANCHOR_MIN_LIVE`` names ON PURPOSE:
below that count the anchor stops applying a panel rule at all (a fraction floor over a
handful of names is a per-name gate), so a 3-name fixture would exercise a different
code path from the ~3,000-name universe these tests claim to model.

These tests pin the split, and they pin the surviving DEFECT too: the mixed-panel
assertions fail loudly if someone feeds one panel again, so the fix cannot be reverted
quietly.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.build_stock_library as bsl
from engine.extension import ANCHOR_MIN_LIVE, extension_signals
from scripts.build_stock_library import _crypto_tickers, _panel_asof, extension_panels

CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD"]
# AAA/BBB/CCC stay first — TestNoCryptoInTheEquityPanel moves AAA to the crypto side to
# prove the split follows config.  The rest exist so the equity panel clears
# ANCHOR_MIN_LIVE and the anchor runs its PANEL rule, as it does on the real universe.
EQUITIES = ["AAA", "BBB", "CCC"] + [f"EQ{i:02d}" for i in range(ANCHOR_MIN_LIVE + 4)]


def _series(index, start=100.0, drift=0.0009, seed=0):
    """Deterministic compounding walk — no RNG state shared between calls."""
    rng = np.random.default_rng(seed)
    steps = drift + rng.normal(0, 0.004, len(index))
    return pd.Series(start * np.cumprod(1.0 + steps), index=index)


def _panel(*, equity_end: str, crypto_end: str, sessions: int = 420):
    """A universe-shaped close matrix: equities on business days ending
    ``equity_end``, crypto on EVERY day through ``crypto_end`` — exactly the shape
    ``pd.concat({t: c for (t, c, *_) in universe()}, axis=1)`` produces."""
    eq_idx = pd.bdate_range(end=equity_end, periods=sessions)
    cx_idx = pd.date_range(end=crypto_end, periods=int(sessions * 1.45), freq="D")
    cols = {t: _series(eq_idx, seed=i) for i, t in enumerate(EQUITIES)}
    cols.update({t: _series(cx_idx, seed=100 + i) for i, t in enumerate(CRYPTO)})
    return pd.concat(cols, axis=1, sort=False).sort_index()


@pytest.fixture(autouse=True)
def _pin_crypto_config(monkeypatch):
    """`_crypto_tickers` reads config.yml; pin it so the tests describe the split, not
    whatever the repo config happens to hold today."""
    from lib import config
    monkeypatch.setattr(
        config, "load", lambda: {"yahoo": {"tickers": {"crypto": list(CRYPTO)}}})


# --------------------------------------------------------------------------- #
# 1. the bug this exists to prevent
# --------------------------------------------------------------------------- #

class TestWeekendCollision:
    """Friday equities + Sunday crypto — the shape of 6 of every 21 builds."""

    # 2026-07-31 is a Friday, 2026-08-02 the Sunday after it.
    PANEL = dict(equity_end="2026-07-31", crypto_end="2026-08-02")

    def test_one_mixed_panel_still_misreads_every_equity(self):
        """The defect, pinned — in the form it takes now that ``extension_signals``
        anchors by coverage and declares its age.  A crypto-only Sunday row is far
        under the floor, so it no longer blanks the equities board-wide; what is left
        is what the anchor cannot reach:

          * ~189 all-NaN weekend rows inside every 200-row window, so every equity's
            ext_z off the mixed panel differs from its own-calendar value; and
          * the anchor drops back to the last EQUITY session, so crypto — which traded
            on Saturday and Sunday — is read two days stale, and says so.

        If this stops failing the split is no longer needed; and if it stops holding,
        the test below is measuring nothing."""
        mixed = _panel(**self.PANEL)
        assert str(mixed.index.max().date()) == "2026-08-02"      # a Sunday
        out = extension_signals(mixed)
        eq, cx = extension_panels(mixed)
        own = extension_signals(eq)
        own.update(extension_signals(cx))
        assert set(EQUITIES) <= set(out) & set(own)
        assert all(out[t]["ext_z"] != own[t]["ext_z"] for t in EQUITIES), \
            {t: (out[t]["ext_z"], own[t]["ext_z"]) for t in EQUITIES}
        # the whole mixed read is stamped with the equity Friday — crypto's own
        # Saturday and Sunday sessions are simply gone, and the age discloses it
        assert {v["ext_asof"] for v in out.values()} == {"2026-07-31"}
        assert {v["ext_age"] for v in out.values()} == {2}
        assert {own[t]["ext_asof"] for t in CRYPTO} == {"2026-08-02"}
        assert {own[t]["ext_age"] for t in CRYPTO} == {0}

    def test_split_panels_keep_full_equity_coverage(self):
        eq, cx = extension_panels(_panel(**self.PANEL))
        ext = extension_signals(eq)
        ext.update(extension_signals(cx))
        assert set(EQUITIES) <= set(ext), "every equity must carry a reading"
        assert set(CRYPTO) <= set(ext), "crypto keeps its own reading"
        assert len(ext) == len(EQUITIES) + len(CRYPTO)

    def test_each_panel_ends_on_its_own_calendar(self):
        eq, cx = extension_panels(_panel(**self.PANEL))
        assert str(eq.index.max().date()) == "2026-07-31"         # last equity session
        assert str(cx.index.max().date()) == "2026-08-02"         # crypto ran on

    def test_the_equity_panel_carries_no_weekend_rows(self):
        """Not cosmetic: extension_signals' windows are ROW counts, so all-NaN weekend
        rows inside a 200-row window shorten the SMA200 to ~138 real sessions."""
        eq, _cx = extension_panels(_panel(**self.PANEL))
        assert not eq.isna().all(axis=1).any()
        assert set(eq.index.dayofweek) <= {0, 1, 2, 3, 4}

    def test_the_split_is_a_partition_of_the_columns(self):
        panel = _panel(**self.PANEL)
        eq, cx = extension_panels(panel)
        assert list(eq.columns) + list(cx.columns) == sorted(
            list(eq.columns) + list(cx.columns), key=list(panel.columns).index)
        assert set(eq.columns) | set(cx.columns) == set(panel.columns)
        assert not (set(eq.columns) & set(cx.columns))


# --------------------------------------------------------------------------- #
# 2. the long-weekend / holiday shape that `.iloc[:-1]` cannot handle
# --------------------------------------------------------------------------- #

class TestMondayHoliday:
    """Crypto three days ahead of equities: Friday close, then Sat + Sun + a Monday
    market holiday. Dropping ONE trailing row would still leave a crypto-only tail."""

    # 2026-07-31 Fri; crypto runs Sat 08-01, Sun 08-02, holiday Mon 08-03.
    PANEL = dict(equity_end="2026-07-31", crypto_end="2026-08-03")

    def test_three_crypto_only_rows_leave_one_mixed_panel_with_no_read_at_all(self):
        """Past ANCHOR_MAX_AGE the mixed panel cannot be served: the last well-covered
        row is the equity Friday, three rows back, and publishing the whole universe
        off it as today's reading is exactly what the age cap forbids.  So on ONE panel
        a long weekend costs the board its extension read entirely — the strongest form
        of the argument for splitting."""
        mixed = _panel(**self.PANEL)
        trailing = mixed[EQUITIES].isna().all(axis=1).iloc[-3:]
        assert trailing.all(), "fixture must carry 3 crypto-only rows"
        assert extension_signals(mixed) == {}
        # ...and the trap no positional rule can avoid, in its current form: dropping
        # ONE trailing row lands the panel back inside the age cap, so the same universe
        # flips from "withheld" to "served" — off the Friday, two days stale, crypto
        # included.  A mixed panel's read is a function of how the weekend fell, which
        # is precisely the property a split removes.
        one_back = extension_signals(mixed.iloc[:-1])
        assert set(one_back) == set(EQUITIES) | set(CRYPTO)
        assert {v["ext_asof"] for v in one_back.values()} == {"2026-07-31"}
        assert {v["ext_age"] for v in one_back.values()} == {2}
        # split, crypto keeps the sessions it actually traded and the equities are read
        eq, cx = extension_panels(mixed)
        assert {v["ext_asof"] for v in extension_signals(cx).values()} == {"2026-08-03"}
        assert {v["ext_asof"] for v in extension_signals(eq).values()} == {"2026-07-31"}

    def test_the_refusal_to_serve_is_announced(self, capsys):
        extension_signals(_panel(**self.PANEL))
        warn = [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-anchor-uncovered" in ln]
        assert warn, "a panel that serves nothing must say why"

    def test_split_panels_are_unaffected_by_the_holiday_gap(self):
        eq, cx = extension_panels(_panel(**self.PANEL))
        ext = extension_signals(eq)
        ext.update(extension_signals(cx))
        assert set(EQUITIES) <= set(ext)
        assert set(CRYPTO) <= set(ext)
        assert str(eq.index.max().date()) == "2026-07-31"
        assert str(cx.index.max().date()) == "2026-08-03"

    def test_a_weekday_build_reads_the_same_equities_as_a_weekend_build(self):
        """The heal must not depend on WHEN the build runs: the equity readings from a
        Friday-ending panel and from the same panel seen on Monday are identical."""
        weekday = extension_panels(
            _panel(equity_end="2026-07-31", crypto_end="2026-07-31"))[0]
        weekend = extension_panels(_panel(**self.PANEL))[0]
        a = {t: v for t, v in extension_signals(weekday).items() if t in EQUITIES}
        b = {t: v for t, v in extension_signals(weekend).items() if t in EQUITIES}
        assert a == b and set(a) == set(EQUITIES)


# --------------------------------------------------------------------------- #
# 3. the regression pin: no crypto column may reach the equity read
# --------------------------------------------------------------------------- #

class TestNoCryptoInTheEquityPanel:

    def test_the_equity_panel_excludes_every_configured_crypto_ticker(self):
        eq, cx = extension_panels(_panel(equity_end="2026-07-31",
                                         crypto_end="2026-08-02"))
        assert not (set(eq.columns) & set(CRYPTO))
        assert set(cx.columns) == set(CRYPTO)

    def test_the_exclusion_follows_config_and_is_not_a_hardcoded_list(self, monkeypatch):
        """A literal {BTC-USD, ETH-USD, SOL-USD} would rot the day a coin is added to
        config.yml. Add a fourth and it must land on the crypto side with no code edit."""
        from lib import config
        monkeypatch.setattr(config, "load", lambda: {
            "yahoo": {"tickers": {"crypto": [*CRYPTO, "AAA"]}}})
        assert "AAA" in _crypto_tickers()
        eq, cx = extension_panels(_panel(equity_end="2026-07-31",
                                         crypto_end="2026-08-02"))
        assert "AAA" in set(cx.columns) and "AAA" not in set(eq.columns)

    def test_an_unreadable_config_degrades_to_one_panel_instead_of_crashing(
            self, monkeypatch):
        from lib import config

        def _boom():
            raise RuntimeError("config.yml unreadable")

        monkeypatch.setattr(config, "load", _boom)
        assert _crypto_tickers() == frozenset()
        eq, cx = extension_panels(_panel(equity_end="2026-07-31",
                                         crypto_end="2026-08-02"))
        assert cx.empty and len(eq.columns) == len(EQUITIES) + len(CRYPTO)


# --------------------------------------------------------------------------- #
# 4. shape / degradation contract
# --------------------------------------------------------------------------- #

class TestPanelContract:

    def test_empty_and_none_inputs_return_two_empty_frames(self):
        for arg in (None, pd.DataFrame()):
            eq, cx = extension_panels(arg)
            assert eq.empty and cx.empty

    def test_an_all_equity_universe_leaves_the_crypto_panel_empty(self):
        idx = pd.bdate_range(end="2026-07-31", periods=420)
        eq, cx = extension_panels(
            pd.concat({t: _series(idx, seed=i) for i, t in enumerate(EQUITIES)}, axis=1))
        assert cx.empty and list(eq.columns) == EQUITIES
        assert extension_signals(cx) == {}          # the caller's `if not empty` guard

    def test_the_split_is_deterministic(self):
        panel = _panel(equity_end="2026-07-31", crypto_end="2026-08-02")
        first = [extension_signals(p) for p in extension_panels(panel)]
        second = [extension_signals(p) for p in extension_panels(panel)]
        assert first == second
        assert all(first)

    def test_panel_asof_labels_each_calendar_and_never_raises(self):
        eq, cx = extension_panels(_panel(equity_end="2026-07-31",
                                         crypto_end="2026-08-02"))
        assert _panel_asof(eq) == "2026-07-31"
        assert _panel_asof(cx) == "2026-08-02"
        assert _panel_asof(pd.DataFrame()) == "—"
        assert _panel_asof(None) == "—"


# --------------------------------------------------------------------------- #
# 5. the WIRING, not just the helper
# --------------------------------------------------------------------------- #

def _calls(func_name: str) -> list[list[str]]:
    """Every call to `func_name` in build_stock_library, as unparsed argument lists.
    Structural (AST), not a substring grep: a comment mentioning the name cannot
    satisfy it and reformatting the call cannot break it."""
    tree = ast.parse(Path(bsl.__file__).read_text())
    return [[ast.unparse(a) for a in n.args]
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == func_name]


class TestBuilderWiring:
    """A helper-only test is vacuous if the builder stops calling the helper: reverting
    the call site to `extension_signals(_ext_closes)` leaves every test above green."""

    def test_the_mixed_universe_panel_never_reaches_extension_signals(self):
        fed = _calls("extension_signals")
        assert fed, "no extension_signals call found — this guard would be vacuous"
        flat = [a for args in fed for a in args]
        assert "_ext_closes" not in flat, (
            "build_stock_library is feeding the mixed equity+crypto universe panel to "
            "extension_signals again — on a weekend/holiday build that reads crypto-only. "
            "Split it with extension_panels() first.")
        assert set(flat) == {"_ext_eq", "_ext_cx"}, flat

    def test_the_builder_actually_splits_the_panel(self):
        assert _calls("extension_panels") == [["_ext_closes"]]

    def test_lottery_and_dispersion_still_read_the_WHOLE_universe_panel(self):
        """Blast-radius pin. lottery_map's windowed `.max()` skips NaN, so it is immune
        to the calendar mix and must keep its full-universe panel — narrowing it here
        would silently change a validated input that this fix never touched."""
        src = Path(bsl.__file__).read_text()
        assert "lottery_map = (_ext_closes.pct_change()" in src
        assert "dispersion.assess(_ext_closes.pct_change(" in src
