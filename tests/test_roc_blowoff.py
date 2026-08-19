"""tests/test_roc_blowoff.py — the "Blow-off risk" display chip (engine/roc_blowoff.py).

WHAT THIS PINS

1. THE MIRROR IS REAL, NOT ASSERTED.  The chip prints rates measured by
   ``research/prophet_us_audit/roc_extremes_battery.py``'s S-ROC12-TERM detector
   (top-proximity 24.18% vs 19.32%, diff +4.86pp CI [+1.93,+8.11], n=22,014).  Those
   numbers describe the population THAT detector selects, so the module must select the
   same bars.  ``test_fire_mask_is_identical_to_the_battery_detector`` imports the
   battery by path and compares the two fire masks cell-for-cell on a panel that
   actually fires — a re-tuned window here turns the printed rate into a claim about a
   population nobody measured, and that is the failure this test exists to catch.

2. EACH LEG CAN VETO ON ITS OWN.  The three must-not-fire fixtures are the must-fire
   series with exactly ONE leg disarmed, and each asserts the other two legs are still
   armed.  A test that only checked "does not fire" would pass on a module that had
   stopped firing at all; these pin WHICH leg said no.

3. ZERO SCORE AUTHORITY IS ENFORCED, NOT DECLARED.  ``score_rows`` output is compared
   byte-for-byte between a pool carrying the chip and the same pool without it, on a
   pool proven non-degenerate first (multiple distinct scores, >1 stage, >=1 featured
   row) — otherwise "identical" would be a statement about an empty comparison.

4. THE TWO SURFACES CANNOT DRIFT.  The board card and the per-stock page carry the copy
   literally (house idiom: board copy lives in the template), so the module owns the
   canonical strings and this file asserts both surfaces still match them.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import roc_blowoff as RB          # noqa: E402
from engine import us_board_rank as ubr       # noqa: E402

BATTERY = ROOT / "research" / "prophet_us_audit" / "roc_extremes_battery.py"
RESULTS = ROOT / "research" / "prophet_us_audit" / "roc_extremes_battery_results.json"
DASHBOARD = ROOT / "templates" / "dashboard.html.j2"
#: The nightly us-board card loop moved out of dashboard.html.j2 into this
#: partial when the board gained its server-side tier split
#: (docs/TIER_PREVIEW_PATTERN.md): the free shell and the /premiumdata/ payload
#: render cards from ONE source so they cannot drift. Source-anchor checks below
#: read the pair, because together they are the dashboard's card markup.
US_BOARD_CARDS = ROOT / "templates" / "_us_board_cards.html.j2"
STOCK_PAGE = ROOT / "templates" / "stock.html.j2"


def _dashboard_src() -> str:
    """dashboard.html.j2 plus the us-board card partial it includes."""
    return (DASHBOARD.read_text(encoding="utf-8")
            + US_BOARD_CARDS.read_text(encoding="utf-8"))


def _battery():
    """Import the research instrument by path (it lives outside any package)."""
    spec = importlib.util.spec_from_file_location("roc_extremes_battery", BATTERY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# fixtures — one FIRE series, and three copies with exactly one leg disarmed
# ---------------------------------------------------------------------------
# a 5-day +4% burst then a long bleed: arms the burst-mover leg (own p97 of roc5 ~ +21%)
BURST_CYCLE = [0.04] * 5 + [-0.0095] * 20
# a drift that never produces a 15% week: the burst-mover leg stays down
QUIET_CYCLE = [0.0015] * 25
HIST_BARS = 340                # >= MIN_BARS even before the closing run is appended
SURGE = [0.03] * 12            # roc12 = +42.6% — the top of its own trailing history
NEAR_SURGE = [0.014] * 12      # roc12 percentile ~0.98: past p95, short of p99
SPIKE_BACK = 40                # a one-bar spike this many bars before the end
SPIKE_MULT = 2.2


def _px(rets) -> pd.Series:
    values = 100.0 * np.cumprod(1.0 + np.asarray(rets, dtype=float))
    return pd.Series(values, index=pd.bdate_range("2015-01-05", periods=len(values)))


def _repeat(block: list[float], n: int) -> list[float]:
    out: list[float] = []
    while len(out) < n:
        out.extend(block)
    return out[:n]


def _noisy_burst_history() -> list[float]:
    """Burst cycles plus small SEEDED noise.

    The noise is load-bearing, not decoration: a perfectly periodic cycle gives roc12
    only a handful of distinct values, so its own-history percentile jumps straight from
    ~0.68 to 1.00 and the "p95 but not p99" fixture below cannot exist at all.
    """
    rng = np.random.default_rng(20260805)
    return list(np.asarray(_repeat(BURST_CYCLE, HIST_BARS))
                + rng.normal(0.0, 0.006, HIST_BARS))


def _fire_series() -> pd.Series:
    return _px(_noisy_burst_history() + SURGE)


def _last(series: pd.Series) -> pd.Series:
    return RB.legs(series).iloc[-1]


# ---------------------------------------------------------------------------
# 1. the mirror: identical to the battery detector, on a panel that fires
# ---------------------------------------------------------------------------
class TestMirrorsTheBatteryDetector:
    def _panel(self) -> pd.DataFrame:
        rng = np.random.default_rng(11)
        cols = {}
        for i in range(10):
            rets = rng.normal(0.001, 0.03, 1400)
            for start in range(200, 1400, 90):       # inject burst weeks
                rets[start:start + 5] = 0.05
            cols[f"T{i}"] = 100.0 * np.cumprod(1.0 + rets)
        return pd.DataFrame(cols, index=pd.bdate_range("2018-01-02", periods=1400))

    def test_fire_mask_is_identical_to_the_battery_detector(self):
        panel = self._panel()
        battery_fire = _battery().roc12_term_legs(panel)["fire"].to_numpy()
        mine = pd.DataFrame(
            {t: RB.legs(panel[t])["blowoff_risk"] for t in panel.columns}).to_numpy()
        # non-vacuity first: a comparison of two all-False masks proves nothing
        assert battery_fire.sum() > 50, (
            f"fixture panel fired only {battery_fire.sum()} times — too few for the "
            "mask comparison below to mean anything")
        assert (battery_fire == mine).all(), (
            f"{int((battery_fire != mine).sum())} cells differ from the battery's fire "
            "mask — the chip's printed rates belong to the battery's population, so a "
            "drifted construction makes the copy false")

    def test_each_leg_is_identical_to_the_battery_leg(self):
        panel = self._panel()
        legs = _battery().roc12_term_legs(panel)
        pairs = {
            "burst_mover": legs["legs"]["burst_mover_p97_roc5_ge_15pct"],
            "near_high_63": legs["legs"]["within_5pct_of_63d_high"],
            "roc12_ge_own_p99": legs["legs"]["roc12_ge_own_p99"],
        }
        for name, battery_leg in pairs.items():
            mine = pd.DataFrame(
                {t: RB.legs(panel[t])[name] for t in panel.columns}).to_numpy()
            assert (battery_leg.to_numpy() == mine).all(), f"leg {name} drifted"
        battery_pctile = legs["roc12_pctile"].to_numpy()
        mine_pctile = pd.DataFrame(
            {t: RB.legs(panel[t])["roc12_pctile"] for t in panel.columns}).to_numpy()
        both = np.isfinite(battery_pctile) & np.isfinite(mine_pctile)
        assert np.nanmax(np.abs(battery_pctile[both] - mine_pctile[both])) == 0.0

    def test_constants_match_the_battery_defaults(self):
        """A default changed in the battery must not leave this module silently behind."""
        defaults = _battery().roc12_term_legs.__defaults__
        # roc12_term_legs(C, *, mover_min, near_high, fire_q, ctrl)
        kwdefaults = _battery().roc12_term_legs.__kwdefaults__ or {}
        assert kwdefaults.get("mover_min") == RB.MOVER_MIN
        assert kwdefaults.get("near_high") == RB.NEAR_HIGH
        assert kwdefaults.get("fire_q") == RB.FIRE_Q
        assert tuple(kwdefaults.get("ctrl")) == RB.CONTROL_BAND
        assert defaults is None or defaults == ()


# ---------------------------------------------------------------------------
# 2. construction — one must-fire, three single-leg must-not-fires
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_must_fire(self):
        row = _last(_fire_series())
        assert bool(row["burst_mover"]) is True
        assert bool(row["near_high_63"]) is True
        assert bool(row["roc12_ge_own_p99"]) is True
        assert bool(row["blowoff_risk"]) is True

    def test_no_burst_mover_history_does_not_fire(self):
        """Same closing run, a history that never produced a 15% week."""
        row = _last(_px(_repeat(QUIET_CYCLE, HIST_BARS) + SURGE))
        assert bool(row["burst_mover"]) is False
        # the other two legs stay ARMED — so the veto is provably the mover leg
        assert bool(row["near_high_63"]) is True
        assert bool(row["roc12_ge_own_p99"]) is True
        assert bool(row["blowoff_risk"]) is False

    def test_not_near_the_63d_high_does_not_fire(self):
        """A one-bar spike inside the 63-session window lifts the high out of reach."""
        series = _fire_series().copy()
        series.iloc[len(series) - SPIKE_BACK] *= SPIKE_MULT
        row = _last(series)
        assert bool(row["near_high_63"]) is False
        assert bool(row["burst_mover"]) is True
        assert bool(row["roc12_ge_own_p99"]) is True
        assert bool(row["blowoff_risk"]) is False

    def test_p95_but_not_p99_does_not_fire(self):
        """The control-band case: extreme enough to notice, short of the measured gate."""
        row = _last(_px(_noisy_burst_history() + NEAR_SURGE))
        pctile = float(row["roc12_pctile"])
        assert 0.95 <= pctile < 0.99, f"fixture drifted out of the p95-p99 band: {pctile}"
        assert bool(row["roc12_ge_own_p99"]) is False
        assert bool(row["burst_mover"]) is True
        assert bool(row["near_high_63"]) is True
        assert bool(row["blowoff_risk"]) is False

    def test_backward_only(self):
        """Mutating bars AFTER k must not move the read AT k (the W8 lookahead lesson)."""
        series = _fire_series()
        k = len(series) - 1
        before = RB.legs(series).iloc[k]
        future = series.copy()
        future.iloc[k] = float(future.iloc[k])          # k itself untouched
        extended = pd.concat([future, pd.Series(
            [float(future.iloc[-1]) * 3.0] * 20,
            index=pd.bdate_range(future.index[-1] + pd.Timedelta(days=1), periods=20))])
        after = RB.legs(extended).iloc[k]
        for field in ("roc12", "roc12_pctile", "burst_mover", "near_high_63",
                      "roc12_ge_own_p99", "blowoff_risk"):
            assert before[field] == after[field] or (
                pd.isna(before[field]) and pd.isna(after[field])), (
                f"{field} at bar {k} changed when only LATER bars were added")


# ---------------------------------------------------------------------------
# 3. assess() — the display contract
# ---------------------------------------------------------------------------
class TestAssess:
    def test_fields_and_types(self):
        out = RB.assess(_fire_series())
        assert set(out) == {"asof", *RB.FIELDS}
        assert out["blowoff_risk"] is True
        assert isinstance(out["burst_mover"], bool)
        assert isinstance(out["near_high_63"], bool)
        assert 0.0 <= out["roc12_pctile"] <= 1.0

    def test_min_bars_is_the_measured_panel_floor(self):
        """Pinned by VALUE and against the battery — not read back off the module.

        ``short = series[-(RB.MIN_BARS - 1):]`` would shrink with the constant and pass
        for any floor at all; the literal below is what makes the next test bite.
        """
        assert RB.MIN_BARS == 300
        assert RB.MIN_BARS == _battery().MIN_BARS

    def test_short_history_gets_no_read_rather_than_a_false_default(self):
        """Under the battery's own panel floor there is NO measurement to display."""
        short = _fire_series().iloc[-299:]          # literal, deliberately
        assert RB.assess(short) is None
        assert RB.assess(_fire_series().iloc[-300:]) is not None

    def test_asof_is_the_stores_last_bar_not_the_wall_clock(self):
        series = _fire_series()
        out = RB.assess(series)
        assert out["asof"] == str(series.index[-1].date())
        # a store that stopped updating yields a STALE asof, never today's date
        stale = series.iloc[:-40]
        assert RB.assess(stale)["asof"] == str(stale.index[-1].date())

    def test_tail_truncation_is_exact(self):
        """assess() computes on a fixed tail for speed; that must be exact, not close."""
        series = _fire_series()
        long = pd.concat([_px(_repeat(BURST_CYCLE, 2000)) * 0.01, series])
        long.index = pd.bdate_range("2005-01-03", periods=len(long))
        assert len(long) > RB.TAIL_BARS * 3
        full = RB.legs(long).iloc[-1]
        tailed = RB.assess(long)
        assert tailed["blowoff_risk"] is bool(full["blowoff_risk"])
        assert tailed["burst_mover"] is bool(full["burst_mover"])
        assert tailed["near_high_63"] is bool(full["near_high_63"])
        assert tailed["roc12_pctile"] == round(float(full["roc12_pctile"]), 4)

    def test_tail_bars_covers_the_longest_lookback(self):
        assert RB.TAIL_BARS >= RB.RANK_WINDOW + RB.ROC12_N
        assert RB.TAIL_BARS >= RB.HIGH_WINDOW


# ---------------------------------------------------------------------------
# 3b. builder wiring — the read is actually stamped, and only where it was measured
# ---------------------------------------------------------------------------
class TestBuilderWiring:
    def test_one_stamps_the_read_on_an_equity_rec(self):
        from scripts import build_stock_library as bsl
        series = _fire_series()
        rec = bsl._one("TEST", series, series * 1.01, "Test Corp",
                       "Information Technology")
        assert rec is not None
        assert rec["blowoff"]["blowoff_risk"] is True
        assert rec["blowoff"]["asof"] == str(series.index[-1].date())

    def test_crypto_gets_no_read_at_all(self):
        """The battery's panel was the US equity book.

        A crypto name would be a read on a population that was never measured, so it
        carries no key rather than a quiet False — absent and "measured, quiet" are
        different claims and the surface must be able to tell them apart.
        """
        from scripts import build_stock_library as bsl
        series = _fire_series()
        rec = bsl._one("BTC-USD", series, series * 1.01, "Bitcoin", "")
        assert rec is not None
        assert "blowoff" not in rec

    def test_the_stage_and_attach_hops_are_still_wired(self):
        """DELETION GUARD, and only that — a source-anchor check, not a behaviour test.

        The two ends of the chain are covered functionally (``_one`` above stamps the
        rec; the render tests below prove the template reads ``n.blowoff.blowoff_risk``).
        The middle hop lives inside ``main()``, which no test can drive, so this pins
        that the stage/attach lines still exist and still agree on ONE key name.
        """
        src = (ROOT / "scripts" / "build_stock_library.py").read_text(encoding="utf-8")
        assert 'rec["blowoff"] = _bo' in src, "Loop A stamp removed"
        assert "_blowoff_map[ticker] = _bo_rec" in src, "staging hop removed"
        assert 'r["blowoff"] = _bo' in src, "board-row attach removed"
        assert "n.get('blowoff')" in _dashboard_src(), \
            "the template reads a different key than the builder writes"


# ---------------------------------------------------------------------------
# 4. authority hygiene — the chip changes NOTHING about rank / stage / featured
# ---------------------------------------------------------------------------
def _pool() -> list[dict]:
    def row(ticker, status, tier, ticks, alpha, sector, ext_z):
        return {
            "ticker": ticker, "name": f"{ticker} Inc", "sector": sector,
            "alpha": alpha, "ext_z": ext_z,
            "entry_signal": {"status": status},
            "signal": {"eligible": True, "tier_cascade": tier, "ticks": ticks,
                       "provisional": False, "above200": True, "weekly_bull": True,
                       "asof": "2026-07-31"},
        }
    return [
        row("AAA", "buy_now", "T2", 0, 2.4, "Information Technology", 0.4),
        row("BBB", "partial", "T1", 1, 1.5, "Health Care", 1.1),
        row("CCC", "watch", "T3", 5, 0.2, "Information Technology", 0.9),
        row("DDD", "buy_now", "T1", 2, -0.7, "Energy", 2.6),
        row("EEE", "extended", "T2", 1, 0.9, "Financials", 1.8),
        row("FFF", "buy_soon", "T2", 1, 1.9, "Industrials", 0.2),
    ]


_AUTHORITY_KEYS = ("stage", "prophet", "featured", "featured_blocked_by", "score_rank",
                   "display_rank", "signal_asof", "days_since_signal",
                   "days_since_signal_basis", "new")


class TestZeroScoreAuthority:
    def test_blowoff_risk_is_declared_scoreless(self):
        assert "blowoff_risk" in ubr.ZERO_SCORE_AUTHORITY

    def test_declaration_reaches_the_shipped_artifact_block(self):
        scored = ubr.score_rows(_pool(), board_asof="2026-07-31")
        assert "blowoff_risk" in scored[0]["prophet"]["zero_score_authority"]

    def test_rank_stage_and_featured_are_byte_identical_with_and_without_the_chip(self):
        plain = ubr.score_rows(copy.deepcopy(_pool()), board_asof="2026-07-31")

        # NON-VACUITY: an identity claim over a degenerate board proves nothing.
        assert len({r["prophet"]["score"] for r in plain}) > 1, "all scores equal"
        assert len({r["stage"] for r in plain}) > 1, "all rows in one stage"
        assert any(r["featured"] for r in plain), "no row featured — featuring untested"

        chipped_rows = copy.deepcopy(_pool())
        fired = RB.assess(_fire_series())
        assert fired["blowoff_risk"] is True
        for row in chipped_rows:
            row["blowoff"] = dict(fired)
        chipped = ubr.score_rows(chipped_rows, board_asof="2026-07-31")

        def authority_view(rows):
            return [
                {"ticker": r["ticker"],
                 **{k: r.get(k) for k in _AUTHORITY_KEYS}}
                for r in rows
            ]

        assert json.dumps(authority_view(plain), sort_keys=True, default=str) == \
            json.dumps(authority_view(chipped), sort_keys=True, default=str), (
            "adding the blow-off chip moved a score, a stage, an order or a featured "
            "flag — the chip is display-tier and must move none of them")
        # order itself, not just the per-row fields
        assert [r["ticker"] for r in plain] == [r["ticker"] for r in chipped]


# ---------------------------------------------------------------------------
# 5. copy — present in EN and zh on BOTH surfaces, and never in a title=
# ---------------------------------------------------------------------------
CHIP_MARKUP = '<span class="pv-mk-i pv-mk-blow"'


def _stocks_html(*, fires: bool) -> str:
    """Render us_stocks.html with one board row whose chip does / does not fire.

    Rendered, not grepped.  A raw file scan for the copy is satisfied by the copy-fence
    COMMENT that sits beside the chip in dashboard.html.j2 — verified: renaming the chip
    label left a file-text assertion green.  Only the rendered card proves the wiring.
    """
    from tests.test_dashboard_template_render import _base_vm, _board_row, _env

    def row(ticker, blowoff_risk):
        return _board_row(
            ticker=ticker, name=f"{ticker} Corp", stage="live", lane="continuation",
            entry_signal={"status": "buy_now"},
            blowoff={"asof": "2026-07-31", "roc12_pctile": 1.0, "burst_mover": True,
                     "near_high_63": True, "blowoff_risk": blowoff_risk},
        )

    vm = _base_vm()
    vm["us_standouts"] = {"buy": [row("AAA", fires), row("BBB", False)], "eligible": 2}
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


class TestChipCopy:
    def test_board_card_renders_the_chip_in_both_languages_when_it_fires(self):
        html = _stocks_html(fires=True)
        assert html.count(CHIP_MARKUP) == 1, (
            "expected exactly one blow-off chip: one row fires, the other does not")
        assert f'<span class="l-en">{RB.CHIP_EN}</span>' in html
        assert f'<span class="l-zh">{RB.CHIP_ZH}</span>' in html
        assert f'data-tip-en="{RB.HOVER_EN}"' in html
        assert f'data-tip-zh="{RB.HOVER_ZH}"' in html

    def test_board_card_renders_no_chip_when_the_read_is_quiet(self):
        html = _stocks_html(fires=False)
        # full markup string, never the bare class token: pv_css() ships .pv-mk-blow on
        # every render, so `'pv-mk-blow' in html` would be true with nothing rendered.
        assert CHIP_MARKUP not in html
        assert f'<span class="l-en">{RB.CHIP_EN}</span>' not in html
        assert f'<span class="l-zh">{RB.CHIP_ZH}</span>' not in html

    def test_stock_page_carries_the_chip_in_both_languages(self):
        """The per-stock page bakes the copy into its renderer (client-side fill)."""
        text = STOCK_PAGE.read_text(encoding="utf-8")
        block = text[text.index("var boEl = document.getElementById('r_blowoff');"):]
        block = block[:block.index("boEl.style.display = 'none'")]
        for literal, what in ((RB.CHIP_EN, "EN label"), (RB.CHIP_ZH, "zh label"),
                              (RB.HOVER_EN, "EN hover"), (RB.HOVER_ZH, "zh hover")):
            assert literal in block, (
                f"{what} missing from the r_blowoff renderer — the module owns the "
                "canonical copy and the two surfaces must not drift apart")
        assert '<span id="r_blowoff" class="bochip"' in text

    def test_hover_copy_states_the_measured_rates_and_refuses_a_stance(self):
        """The chip may state its measurement and nothing more."""
        assert "24%" in RB.HOVER_EN and "19%" in RB.HOVER_EN
        assert "2.5pp" in RB.HOVER_EN
        # the honest denominator: most fires are NOT the top, and the copy says so
        assert "3 of 4" in RB.HOVER_EN
        assert "not a sell signal" in RB.HOVER_EN
        assert "不是卖出信号" in RB.HOVER_ZH
        assert "24%" in RB.HOVER_ZH and "19%" in RB.HOVER_ZH

    def test_copy_carries_no_internal_names_or_slugs(self):
        for text in (RB.CHIP_EN, RB.CHIP_ZH, RB.HOVER_EN, RB.HOVER_ZH):
            lowered = text.lower()
            for banned in ("s-roc12", "roc12", "roc(12)", "battery", "p99", "pctile",
                           "ext_z", "percentile", "validated", "falsif", "证伪"):
                assert banned not in lowered, f"internal vocabulary leaked: {banned!r}"

    def test_label_never_collides_with_the_ext_z_extended_copy(self):
        """A different measurement may not wear the ext_z family's word.

        ext_z already owns "Extended" here (engine/stock_score conviction verdict, the
        board's stretched/parabolic flag rows, the legacy .ent-warn chip). Both reads can
        fire on ONE card, so a shared word would make the card argue with itself.
        """
        assert "extended" not in RB.CHIP_EN.lower()
        assert "extended" not in RB.HOVER_EN.lower()
        assert RB.CHIP_EN == "Blow-off risk"
        assert RB.CHIP_ZH == "冲顶风险"
        # …and the RENDERED chip, not just the constant
        html = _stocks_html(fires=True)
        start = html.index(CHIP_MARKUP)
        chip = html[start:html.index("</span>", html.index(">", start))]
        assert "Extended" not in chip and "过度拉伸" not in chip

    @pytest.mark.parametrize("path", [DASHBOARD, STOCK_PAGE])
    def test_hover_copy_is_never_a_translated_title_attribute(self, path):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"title\s*=\s*([\"'])(.*?)\1", text, re.S):
            body = match.group(2)
            assert RB.HOVER_EN not in body and RB.HOVER_ZH not in body
            assert RB.CHIP_ZH not in body

    def test_hover_rides_the_house_hover_card_attributes_on_both_surfaces(self):
        assert f'data-tip-zh="{RB.HOVER_ZH}"' in _stocks_html(fires=True)
        stock = STOCK_PAGE.read_text(encoding="utf-8")
        assert "boEl.setAttribute('data-tip-en'" in stock
        assert "boEl.setAttribute('data-tip-zh'" in stock
        assert "boEl.title" not in stock


# ---------------------------------------------------------------------------
# 6. the copy's numbers are the committed measurement, not remembered ones
# ---------------------------------------------------------------------------
class TestCopyMatchesTheCommittedEvidence:
    def test_rates_in_the_hover_round_to_the_results_json(self):
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
        term = results["S_ROC12_TERM"]
        assert results["verdicts"]["S_ROC12_TERM"]["verdict"] == "POSITIVE"
        proximity = term["top_proximity"]
        assert round(proximity["event_pct"]) == 24, proximity["event_pct"]
        assert round(proximity["control_pct"]) == 19, proximity["control_pct"]
        low, high = proximity["month_block"]["ci95"]
        assert low > 0, "the measured difference no longer excludes zero"
        drawdown = term["variants"]["p99_vs_p80_90"]["21"]["frames"]["dd"]
        assert round(abs(drawdown["delta_median_pp"]), 1) == 2.5, drawdown
        # "3 of 4 such extremes are still not the top" must stay true of the measurement
        assert round((100.0 - proximity["event_pct"]) / 25.0) == 3
