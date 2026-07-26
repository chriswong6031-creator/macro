"""tests/test_prophet_options_context.py — OEU M-PRO display-tier options context.

M-PRO attaches options context to the Prophet / stock-picking surfaces through five
hook points and NOTHING ELSE. The lane's whole risk is that a caveat quietly becomes
an authority, so the suite is written fence-first:

  A. THE FENCE (the tests that matter). entry_read()'s verdict `key` is byte-identical
     with and without options context; the caveat list is the only thing that moves.
     No signal/gate/scoring module imports the options-context module at all.
  B. Null-safety baseline. Absent stores, absent tickers, malformed manifests and
     empty greeks all degrade to "no flag / no sentence / no receipt" — never a
     placeholder, never an exception, never a changed layout.
  C. Thresholds + honesty. A wall we cannot score is not shown; an IV percentile over
     too few observations is not shown; the short history is disclosed INSIDE the
     sentence that makes the claim.
  D. Bilingual + house law. Every EN string ships a distinct ZH pair, and the word
     "validated" appears in none of them.
  E. Render. The ⚠ popover on the Prophet card carries the folded options rows in
     both languages, and a card WITHOUT coverage renders byte-identically to a
     pre-M-PRO card.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jinja2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.leader_lifecycle import (  # noqa: E402
    ENTRY_CAVEAT_EARNINGS,
    ENTRY_CAVEAT_IV_ELEVATED,
    ENTRY_CAVEAT_PIN_RISK,
    STATE_CATALYST_WINDOW,
    STATE_CROWDED,
    STATE_QUIET_ACCUMULATION,
    entry_read,
)
from engine.prophet_bridge import _build_thesis, _build_thesis_zh  # noqa: E402
from lib import options_context as oc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

def _manifest_row(**over) -> dict:
    row = {
        "key": "ACME", "spot": 100.0,
        "call_wall": 102.0, "call_wall_band": "very_strong",
        "put_wall": 95.0, "put_wall_band": "strong",
        "max_pain": 100.0, "gamma_flip": 99.0, "asof": "2026-07-25",
    }
    row.update(over)
    return row


def _write_manifest(site: Path, rows: list[dict]) -> Path:
    (site / "gex").mkdir(parents=True, exist_ok=True)
    p = site / "gex" / "index.json"
    p.write_text(json.dumps(rows))
    return p


def _iv(rank_pct=92.0, n_obs=29, history_days=34, young=True) -> dict:
    return {"rank_pct": rank_pct, "n_obs": n_obs,
            "history_days": history_days, "young": young}


def _candidate(**over) -> dict:
    b = {
        "ticker": "ACME",
        "conviction": {"score": 78, "band": "high", "drivers": ["revisions"],
                       "cautions": [], "trust_tier": {"en": "solid", "zh": "稳健"}},
        "entry_signal": {"above200": True, "spot": 100.0, "entry_grade": "solid"},
        "hold": {},
    }
    b.update(over)
    return b


# =========================================================================== #
# A. THE FENCE                                                                #
# =========================================================================== #

class TestFence:
    """Options context de-escalates and explains. It never decides."""

    @pytest.mark.parametrize("state", [
        STATE_CATALYST_WINDOW, STATE_QUIET_ACCUMULATION, STATE_CROWDED,
    ])
    @pytest.mark.parametrize("evidence", [
        {},
        {"extension_extreme": True},
        {"below_200dma_12m": True},
        {"monthly_rsi_80": True, "drawdown_25pct": True},
    ])
    def test_verdict_key_is_unchanged_by_options_context(self, state, evidence):
        """The stance is set by the same chips it always was."""
        base = entry_read(state, evidence)
        with_opts = entry_read(
            state, evidence,
            options_context={"wall_overhead": True, "iv_elevated": True},
        )
        assert with_opts["key"] == base["key"]
        assert with_opts["basis"] == base["basis"]
        assert with_opts["extension_pct_50d"] == base["extension_pct_50d"]

    def test_absent_context_is_byte_identical_to_pre_mpro(self):
        """A name with no options coverage reads exactly as it did before."""
        ev = {"extension_extreme": True}
        assert entry_read(STATE_CATALYST_WINDOW, ev) == entry_read(
            STATE_CATALYST_WINDOW, ev, options_context=None)
        assert entry_read(STATE_CATALYST_WINDOW, ev) == entry_read(
            STATE_CATALYST_WINDOW, ev, options_context={})
        assert entry_read(STATE_CATALYST_WINDOW, ev, options_context={
            "wall_overhead": False, "iv_elevated": False})["caveats"] == []

    def test_caveats_are_appended_when_true(self):
        r = entry_read(STATE_CATALYST_WINDOW, {},
                       options_context={"wall_overhead": True, "iv_elevated": True})
        assert ENTRY_CAVEAT_PIN_RISK in r["caveats"]
        assert ENTRY_CAVEAT_IV_ELEVATED in r["caveats"]
        assert r["key"] == "staged"

    def test_caveats_are_tri_state_honest(self):
        """None never counts as True — same Kleene discipline as every other chip."""
        r = entry_read(STATE_CATALYST_WINDOW, {},
                       options_context={"wall_overhead": None, "iv_elevated": None})
        assert r["caveats"] == []

    def test_options_caveats_coexist_with_earnings(self):
        r = entry_read(
            STATE_CATALYST_WINDOW, {},
            de_escalations={"earnings_within_14d": True},
            options_context={"wall_overhead": True, "iv_elevated": False},
        )
        assert r["caveats"] == [ENTRY_CAVEAT_EARNINGS, ENTRY_CAVEAT_PIN_RISK]

    def test_entry_signal_never_reaches_the_options_context(self):
        """engine/entry_signal.py is the buy/near/wait authority — it must not import,
        mention, or otherwise be able to see this module."""
        path = ROOT / "engine" / "entry_signal.py"
        assert path.exists(), "entry_signal.py moved — re-point this fence test"
        assert "options_context" not in path.read_text()

    def test_state_machine_source_is_untouched(self):
        """The K-of-N counters and classify() may not reference options context."""
        src = (ROOT / "engine" / "leader_lifecycle.py").read_text()
        start = src.index("def classify(")
        body = src[start:]
        for token in ("options_context", "gex_pin_risk", "iv_rank_elevated",
                      "wall_overhead", "iv_elevated"):
            assert token not in body, f"classify() and below reference {token!r}"

    def test_options_caveats_are_absent_from_every_k_of_n_chip_set(self):
        from engine import leader_lifecycle as ll
        chip_sets = [v for k, v in vars(ll).items()
                     if k.endswith("_CHIPS") and isinstance(v, (list, tuple, set))]
        assert chip_sets, "no chip sets found — re-point this fence test"
        for cs in chip_sets:
            assert "gex_pin_risk" not in cs
            assert "iv_rank_elevated" not in cs

    def test_select_candidates_is_untouched_by_options_context(self):
        """The pick rule must not see options data — same ids, same order."""
        from engine import prophet_bridge as pb
        src = Path(pb.__file__).read_text()
        start = src.index("def select_candidates(")
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        for token in ("options_context", "_wall_map", "wall", "iv_rank", "structure"):
            assert token not in body, f"select_candidates references {token!r}"


# =========================================================================== #
# B. NULL-SAFETY BASELINE                                                     #
# =========================================================================== #

class TestNullSafety:

    def test_walls_absent_manifest(self, tmp_path):
        assert oc.load_gex_walls(tmp_path) == {}

    def test_walls_malformed_manifest(self, tmp_path):
        (tmp_path / "gex").mkdir()
        (tmp_path / "gex" / "index.json").write_text("{not json")
        assert oc.load_gex_walls(tmp_path) == {}

    def test_walls_wrong_shape(self, tmp_path):
        (tmp_path / "gex").mkdir()
        (tmp_path / "gex" / "index.json").write_text('{"key": "ACME"}')
        assert oc.load_gex_walls(tmp_path) == {}

    def test_walls_row_without_key_is_skipped(self, tmp_path):
        _write_manifest(tmp_path, [{"spot": 1.0}, _manifest_row()])
        walls = oc.load_gex_walls(tmp_path)
        assert list(walls) == ["ACME"]

    def test_walls_tolerate_null_numbers(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(spot=None, call_wall=None)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert ctx["spot"] is None and ctx["call_wall_dist_pct"] is None
        assert oc.wall_flag(ctx) is None

    def test_iv_rank_absent_store(self, tmp_path):
        assert oc.load_iv_rank(["ACME"], tmp_path) == {}

    def test_iv_rank_missing_ticker(self, tmp_path):
        (tmp_path / "polygon_gex").mkdir()
        assert oc.load_iv_rank(["ACME", "", None], tmp_path) == {}

    def test_no_coverage_means_no_flags(self):
        assert oc.board_flags("NOPE", {}, {}) == []
        assert oc.board_flags("NOPE", None, None) == []

    def test_no_coverage_means_no_thesis_sentence(self):
        assert oc.dealer_context_sentence(None) is None
        assert oc.dealer_context_sentence({}) is None

    def test_thesis_unchanged_without_context(self):
        b = _candidate()
        assert _build_thesis("ACME", b) == _build_thesis("ACME", b, None)
        assert _build_thesis_zh("ACME", b) == _build_thesis_zh("ACME", b, None)
        assert _build_thesis("ACME", b, {}) == _build_thesis("ACME", b)

    def test_receipt_needs_at_least_one_input(self):
        assert oc.structure_receipt(None, None) is None
        assert oc.structure_receipt(None, None, None, None) is None


# =========================================================================== #
# C. THRESHOLDS + HONESTY                                                     #
# =========================================================================== #

class TestWallFlag:

    def test_fires_for_a_scorable_wall_just_overhead(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(call_wall=102.0)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert oc.wall_overhead(ctx) is True
        en, zh = oc.wall_flag(ctx)
        assert "2.0%" in en and "2.0%" in zh

    def test_silent_when_the_wall_is_too_far(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(call_wall=140.0)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert oc.wall_overhead(ctx) is False
        assert oc.wall_flag(ctx) is None

    def test_silent_when_the_wall_is_below_spot(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(call_wall=90.0)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert oc.wall_flag(ctx) is None

    @pytest.mark.parametrize("band", [None, "faint", "weak", "unknown"])
    def test_silent_when_the_wall_cannot_be_scored(self, tmp_path, band):
        """We do not put a wall in front of a reader that the model could not rate."""
        _write_manifest(tmp_path, [_manifest_row(call_wall_band=band)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert oc.wall_flag(ctx) is None

    def test_distance_is_measured_against_spot(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(spot=200.0, call_wall=204.0)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        assert ctx["call_wall_dist_pct"] == pytest.approx(2.0)

    def test_stamps_the_manifest_as_of_date(self, tmp_path):
        """An undated wall flag has no staleness gate — dealer_context_sentence
        already stamps the same field for the same reason (#F2-07)."""
        _write_manifest(tmp_path, [_manifest_row(call_wall=102.0, asof="2026-07-09")])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        en, zh = oc.wall_flag(ctx)
        assert "2026-07-09" in en and "2026-07-09" in zh

    def test_silent_asof_omits_the_stamp_rather_than_a_blank_parenthetical(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(call_wall=102.0, asof=None)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        en, zh = oc.wall_flag(ctx)
        assert "(as of" not in en
        assert "截至" not in zh


class TestIvFlag:

    def test_fires_at_the_top_of_its_own_history(self):
        """The sample size disclosed is n_obs (the row count the percentile was
        actually computed over), not history_days (the calendar span) — a name
        with gaps has fewer rows than days, and the claim must name the real
        sample (#F2-06)."""
        en, zh = oc.iv_flag(_iv(rank_pct=92.0, n_obs=34, history_days=48))
        assert "34-session" in en and "34次" in zh
        assert "48" not in en and "48" not in zh
        assert "top of" not in en, "an 80th-percentile cut is not a literal maximum"
        assert "in the top fifth of" in en

    def test_discloses_the_short_history_in_the_same_sentence(self):
        """The claim and its caveat must arrive together — no hidden sample size."""
        en, zh = oc.iv_flag(_iv())
        assert "short history" in en
        assert "历史尚短" in zh

    def test_silent_below_the_threshold(self):
        assert oc.iv_flag(_iv(rank_pct=79.9)) is None
        assert oc.iv_elevated(_iv(rank_pct=79.9)) is False

    def test_silent_on_too_few_observations(self):
        """A percentile over a handful of days is noise; print nothing."""
        assert oc.iv_flag(_iv(rank_pct=100.0, n_obs=oc.IV_MIN_OBS - 1)) is None

    def test_screener_convention_is_shared(self):
        """Prophet and the options screener must not disagree about 'young'."""
        from scripts.build_options_screener import YOUNG_THRESHOLD_DAYS
        assert oc.YOUNG_THRESHOLD_DAYS == YOUNG_THRESHOLD_DAYS


class TestBoardFlags:

    def test_at_most_two_rows_wall_first(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row()])
        walls = oc.load_gex_walls(tmp_path)
        rows = oc.board_flags("ACME", walls, {"ACME": _iv()})
        assert len(rows) == 2
        assert "ceiling" in rows[0][0]
        assert "bigger move" in rows[1][0]

    def test_partial_coverage_yields_one_row(self, tmp_path):
        _write_manifest(tmp_path, [_manifest_row(call_wall_band="faint")])
        walls = oc.load_gex_walls(tmp_path)
        assert len(oc.board_flags("ACME", walls, {"ACME": _iv()})) == 1


class TestDealerSentence:

    def test_stamps_the_as_of_date_and_uses_past_tense(self, tmp_path):
        """A thesis is written once and read for weeks — the level must carry a date."""
        _write_manifest(tmp_path, [_manifest_row(call_wall=104.0)])
        ctx = oc.load_gex_walls(tmp_path)["ACME"]
        en, zh = oc.dealer_context_sentence(ctx, entry=100.0)
        assert "2026-07-25" in en and "2026-07-25" in zh
        assert " sat at " in en
        assert "$104.00" in en

    def test_refuses_to_read_as_a_target(self):
        en, zh = oc.dealer_context_sentence(_manifest_row(call_wall=103.0), entry=100.0)
        assert "not a target" in en
        assert "并非目标价" in zh

    def test_silent_when_the_wall_is_far_above_the_entry(self):
        assert oc.dealer_context_sentence(_manifest_row(call_wall=500.0), entry=100.0) is None

    def test_falls_back_to_spot_when_no_entry_given(self):
        assert oc.dealer_context_sentence(_manifest_row(call_wall=102.0)) is not None


class TestStructureReceipt:

    def test_liquid_band(self):
        r = oc.structure_receipt(10.0, 10.2, 4000)
        assert r["band"] == "liquid"
        assert r["spread_pct"] == pytest.approx(2.0)

    def test_wide_spread_wins_over_deep_open_interest(self):
        """The warning a reader needs is the one that costs them money."""
        r = oc.structure_receipt(1.0, 1.5, 90000)
        assert r["band"] == "wide"

    def test_thin_open_interest(self):
        r = oc.structure_receipt(10.0, 10.2, 12)
        assert r["band"] == "thin"

    def test_honest_middle(self):
        r = oc.structure_receipt(10.0, 11.0, 200)
        assert r["band"] == "workable"

    def test_open_interest_vintage_is_labelled(self):
        r = oc.structure_receipt(10.0, 10.2, 4000)
        assert "prior" in (r["oi_vintage"] or "")
        assert "prior session" in r["note_en"]
        assert "上一交易日" in r["note_zh"]

    def test_iv_percentile_rides_with_its_sample_size(self):
        r = oc.structure_receipt(10.0, 10.2, 4000, 0.283, _iv(rank_pct=89.3))
        assert r["iv_pct"] == pytest.approx(28.3)
        assert "34-day record" in r["note_en"]
        assert "short history" in r["note_en"]
        assert "34日记录" in r["note_zh"]

    def test_iv_percentile_suppressed_on_thin_history(self):
        r = oc.structure_receipt(10.0, 10.2, 4000, 0.283, _iv(n_obs=5))
        assert "percentile" not in r["note_en"]
        assert r["iv_pct"] == pytest.approx(28.3)

    def test_receipt_declares_its_own_authority_tier(self):
        assert oc.structure_receipt(10.0, 10.2, 4000)["authority_tier"] == "display"

    def test_missing_open_interest_still_yields_a_receipt(self):
        r = oc.structure_receipt(10.0, 10.2, None)
        assert r is not None and r["open_interest"] is None

    def test_crossed_or_absent_quotes_do_not_fabricate_a_spread(self):
        r = oc.structure_receipt(11.0, 10.0, 4000)
        assert r["spread_pct"] is None


# =========================================================================== #
# D. BILINGUAL + HOUSE LAW                                                    #
# =========================================================================== #

def _all_strings() -> list[tuple[str, str]]:
    ctx = _manifest_row(call_wall=102.0)
    ctx["call_wall_dist_pct"] = 2.0
    pairs = [oc.wall_flag(ctx), oc.iv_flag(_iv()), oc.dealer_context_sentence(ctx, 100.0)]
    r = oc.structure_receipt(10.0, 10.2, 4000, 0.283, _iv())
    pairs.append((r["band_en"], r["band_zh"]))
    pairs.append((r["note_en"], r["note_zh"]))
    return [p for p in pairs if p]


class TestHouseLaw:

    def test_every_string_ships_a_zh_pair(self):
        pairs = _all_strings()
        assert len(pairs) == 5
        for en, zh in pairs:
            assert en and zh
            assert en != zh, en

    def test_zh_half_is_actually_chinese(self):
        for en, zh in _all_strings():
            assert any("一" <= ch <= "鿿" for ch in zh), zh

    def test_the_word_validated_appears_nowhere(self):
        for en, zh in _all_strings():
            assert "validated" not in en.lower()
            assert "已验证" not in zh
        src = (ROOT / "lib" / "options_context.py").read_text()
        assert "validated" not in src.lower()

    def test_no_raw_jargon_on_the_reader_facing_strings(self):
        """Plain words on the surface; the technical names stay in the code."""
        banned = ("GEX", "gamma exposure", "IV rank", "iv_rank", "gex_pin_risk",
                  "iv_rank_elevated", "rank_pct", "call_wall", "net_gex")
        for en, zh in _all_strings():
            for token in banned:
                assert token not in en, f"{token!r} leaked into {en!r}"
                assert token not in zh, f"{token!r} leaked into {zh!r}"

    def test_thesis_sentence_lands_before_the_honesty_footer(self):
        b = _candidate()
        ctx = _manifest_row(call_wall=102.0)
        ctx["call_wall_dist_pct"] = 2.0
        out = _build_thesis("ACME", b, ctx)
        assert "Options positioning" in out
        assert out.index("Options positioning") < out.index("DISPLAY-ONLY")
        out_zh = _build_thesis_zh("ACME", b, ctx)
        assert "期权持仓" in out_zh
        assert out_zh.index("期权持仓") < out_zh.index("仅供展示")

    def test_thesis_gains_exactly_one_sentence(self):
        b = _candidate()
        ctx = _manifest_row(call_wall=102.0)
        ctx["call_wall_dist_pct"] = 2.0
        base = _build_thesis("ACME", b)
        out = _build_thesis("ACME", b, ctx)
        assert out.count(". ") == base.count(". ") + 1


# =========================================================================== #
# E. RENDER                                                                   #
# =========================================================================== #

def _render_card(**over) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    tpl = env.from_string(
        "{% import '_prophet_card.html.j2' as pv %}{{ pv.pv_card(cx) }}")
    cx = {
        "href": "stock.html#ACME", "tk": "ACME", "mkt": "us", "name": "Acme Corp",
        "sec": "Industrials", "sec_zh": "工业", "price_txt": "$100.00",
        "verb": "buy", "edge": 81, "stage": 3, "spark": "",
        "zone_kind": "active", "zone_lo": "$98.00", "zone_hi": "$101.00",
        "date": "2026-07-25", "flags": [], "triage": False,
    }
    cx.update(over)
    return tpl.render(cx=cx)


class TestCardRender:
    """The macro in isolation: options rows are ordinary caution rows."""

    def test_options_rows_render_in_both_languages(self):
        rows = oc.board_flags(
            "ACME",
            {"ACME": {"call_wall_dist_pct": 1.3, "call_wall_band": "very_strong"}},
            {"ACME": _iv()},
        )
        html = _render_card(flags=[list(r) for r in rows])
        assert "⚠ 2" in html
        assert "Options ceiling 1.3% above" in html
        assert "上方1.3%有期权天花板" in html
        assert "Options pricing a bigger move than usual" in html
        assert "期权定价高于平常的波动" in html

    def test_no_flags_means_no_caution_chip_at_all(self):
        html = _render_card(flags=[])
        assert "pv-cau" not in html
        assert "⚠" not in html

    def test_options_rows_fold_into_the_existing_caution_popover(self):
        """No new chip, no new layout slot — one ⚠ count for every caution."""
        html = _render_card(flags=[
            ["Earnings in 6d", "财报还有6天"],
            ["Options ceiling 1.3% above — price tends to stall", "上方1.3%有期权天花板"],
        ])
        assert html.count("pv-cau-btn") == 1
        assert "⚠ 2" in html


class TestBoardPageRender:
    """The real us_stocks.html render path — the acceptance baseline lives here.

    Reuses the fixture view-model from tests/test_dashboard_template_render.py so the
    two suites cannot drift: same env, same vm, same `render(**vm, mode=...)` shape
    build_site.py uses.
    """

    @staticmethod
    def _html(options_flags=None) -> str:
        from tests.test_dashboard_template_render import _base_vm, _env
        vm = _base_vm()
        rows = vm["us_standouts"]["buy"]
        if options_flags is not None:
            rows[0] = dict(rows[0], options_flags=options_flags)
        return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")

    OPT_ROWS = [
        ["Options ceiling 1.3% above — price tends to stall where dealer hedging"
         " is heaviest", "上方1.3%有期权天花板 — 价格倾向在做市商对冲最重处停滞"],
        ["Options pricing a bigger move than usual — top of its own 34-day record"
         " (short history)", "期权定价高于平常的波动 — 处于自身34日记录的高位（历史尚短）"],
    ]

    def test_uncovered_board_is_byte_identical_to_pre_mpro(self):
        """ACCEPTANCE BASELINE: a board with no options coverage renders EXACTLY as
        it did before this lane — the new template loop over an absent key is a
        no-op, so the two renders must match byte for byte."""
        assert self._html() == self._html(options_flags=[])

    def test_no_options_copy_leaks_onto_an_uncovered_board(self):
        html = self._html()
        assert "Options ceiling" not in html
        assert "期权天花板" not in html

    def test_covered_card_carries_both_rows_in_both_languages(self):
        html = self._html(options_flags=self.OPT_ROWS)
        assert "Options ceiling 1.3% above" in html
        assert "上方1.3%有期权天花板" in html
        assert "Options pricing a bigger move than usual" in html
        assert "期权定价高于平常的波动" in html

    def test_covered_card_only_moves_the_caution_count(self):
        """One card gains two ⚠ rows; nothing else about the page changes size
        in a structural way (same number of cards, same caution chips elsewhere)."""
        before, after = self._html(), self._html(options_flags=self.OPT_ROWS)
        assert before.count('class="pvcard') == after.count('class="pvcard')
        assert after.count("pv-cau-btn") == before.count("pv-cau-btn") + 1


class TestBoardAttach:
    """build_site._attach_board_display_chips is the ONE place flags are derived."""

    def test_attach_is_fail_open_without_stores(self, tmp_path):
        from scripts.build_site import _attach_board_display_chips
        doc = {"buy": [{"ticker": "ACME"}, {"ticker": "NOPE"}]}
        out = _attach_board_display_chips(tmp_path, doc)
        for card in out["buy"]:
            assert "options_flags" not in card or card["options_flags"] == []

    def test_attach_folds_wall_rows_for_covered_names(self, tmp_path):
        from scripts.build_site import _attach_board_display_chips
        _write_manifest(tmp_path, [_manifest_row(key="ACME", call_wall=101.5)])
        doc = {"buy": [{"ticker": "ACME"}, {"ticker": "NOPE"}]}
        out = _attach_board_display_chips(tmp_path, doc)
        acme, nope = out["buy"]
        assert len(acme["options_flags"]) == 1
        assert acme["options_flags"][0][0].startswith("Options ceiling 1.5%")
        assert "options_flags" not in nope

    def test_attach_passes_none_through(self, tmp_path):
        from scripts.build_site import _attach_board_display_chips
        assert _attach_board_display_chips(tmp_path, None) is None


class TestLeaderRadarRender:

    def test_caveat_copy_is_plain_word_and_bilingual(self):
        src = (ROOT / "templates" / "leader_radar.html.j2").read_text()
        assert "_opt_cav" in src
        assert "Options ceiling just above" in src
        assert "上方紧邻期权天花板" in src
        assert "Options pricing a bigger move than usual" in src
        assert "期权定价高于平常的波动" in src

    def test_no_raw_caveat_slug_reaches_the_reader(self):
        """`gex_pin_risk` may appear as a lookup key, never as rendered copy."""
        src = (ROOT / "templates" / "leader_radar.html.j2").read_text()
        for line in src.splitlines():
            if "gex_pin_risk" in line:
                assert "in _cv" in line, line
