"""W1-B — the US board's three fail-OPEN disclosures, each pinned by its own signature.

Every case here reproduces a shape measured on committed artifacts during the frozen week
2026-08-01→08-06, when `site/factordata/us_standouts.json` carried `as_of 2026-07-31` on
all 16 renders while CN/HK/CA read 08-06. The board was not merely stale — it was stale
AND SAYING IT WAS FRESH, in three independent places:

  1. ``days_since_signal`` measured from the 3D bucket's OPEN label aged fresh turns past
     the fresh-only filter (APH/FCX published 4 against a knowable 2), while the same
     field's NEGATIVE values — six rows at −5, HD among them, whose real last marker was
     2026-04-27 — sailed THROUGH that filter because it was bounded only above;
  2. the LIMITED sentinel (a record the model refused to analyse) published as
     ``score 14 · no_setup · "No setup" / 暂无买点`` off ``trigger 0.400 × fuel 0.000`` —
     nine gold/silver miners carried exactly that on every stamp while AEM ran +13.9%;
  3. a missing (gitignored) ``data/russell_breadth/_closes_cache.parquet`` dropped ~1,400
     small caps — GOLD, SSRM, UUUU among them — behind a ::warning no consumer can read.

The staleness fail-open (majority vs max over member reach) is pinned next door, in
``tests/test_csp_w5_board_staleness.py::TestComputeBoardStaleness``.

Program: research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md §0 G0.2/G0.3/G0.4.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine import name_score as ns          # noqa: E402
from engine import signal_gate as sg          # noqa: E402
from engine import signal_quality as sq       # noqa: E402
from engine import us_board_rank as ubr       # noqa: E402

STOCKTABLE_JS = REPO / "templates" / "stocktable.js"
SITE_STOCKTABLE_JS = REPO / "site" / "stocktable.js"

_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


# --------------------------------------------------------------------------- #
# G0.3 — the LIMITED sentinel is a printed NULL, never a confident low score
# --------------------------------------------------------------------------- #
# The exact published signature, read off the 2026-08-01→08-06 stamps.
_MINER_SIGNATURE = {"score": 14, "tier": "no_setup", "band_en": "No setup",
                    "band_zh": "暂无买点", "fuel": 0.0, "trigger": 0.4}


def _limited_rec(ticker: str = "AEM") -> dict:
    """The sentinel exactly as ``scripts.build_stock_library._limited_rec`` emits it."""
    return {"ticker": ticker, "name": ticker, "sector": "Materials",
            "asof": "2026-08-06", "listed": "2026-02-02", "history_days": 128,
            "limited": True, "ladder": {"state": "LIMITED"}}


class TestLimitedRecordIsAPrintedNull:
    def test_limited_record_carries_no_score(self):
        got = ns.potential_score(_limited_rec(), market="US", edge_z=None)
        assert got["score"] is None
        assert got["scored"] is False
        assert got["not_scored_reason"] == ns.REASON_LIMITED

    def test_the_miner_signature_is_unreachable(self):
        """The published 2026-08 signature, field by field. Pre-fix this scored 16 with
        ``trigger 0.400`` and ``fuel 0.000`` — a null wearing a measurement's clothes."""
        got = ns.potential_score(_limited_rec(), market="US", edge_z=None)
        assert got["tier"] != _MINER_SIGNATURE["tier"]
        assert got["band_en"] != _MINER_SIGNATURE["band_en"]
        assert got["band_zh"] != _MINER_SIGNATURE["band_zh"]
        # 0.0 fuel and 0.4 trigger were the two fabricated legs: a null is not a zero.
        assert got["components"]["fuel"] is None
        assert got["components"]["trigger"] is None
        assert all(v is None for v in got["components"].values())

    def test_band_is_not_the_red_low_band(self):
        """`low` renders through var(--down). Red is a claim about the name, and the
        whole point of the null is that no claim is being made."""
        got = ns.potential_score(_limited_rec(), market="US")
        assert got["band"] == ns.NOT_SCORED_BAND
        assert got["band"] not in {"low", "neutral", "constructive", "high"}

    def test_no_forward_grading_call_is_emitted(self):
        """``build_stock_library._collect_potential_calls`` keys on ``call`` — a record
        with no score must never accrue a PIT row in the name-score ledger."""
        assert ns.potential_score(_limited_rec(), market="US")["call"] is None

    def test_collect_potential_calls_skips_the_null(self):
        from scripts.build_stock_library import _collect_potential_calls

        rec = _limited_rec()
        rec["conviction"] = {"potential": ns.potential_score(rec, market="US")}
        scored = {"ticker": "NEM", "tech": {"price": 61.0}, "asof": "2026-08-06",
                  "ladder": {"state": "FRESH BUY"},
                  "conviction": {}}
        scored["conviction"]["potential"] = ns.potential_score(scored, market="US")
        calls = _collect_potential_calls([("AEM", rec), ("NEM", scored)])
        assert [c["ticker"] for c in calls] == ["NEM"]

    def test_unknown_cycle_state_is_not_a_mid_band_trigger(self):
        """The root cause: ``_TRIGGER.get(state, 0.4)``. Any state the map has never
        heard of used to inherit a mid-band gate and publish as a real reading."""
        rec = {"ticker": "X", "ladder": {"state": "SOMETHING NEW"},
               "tech": {"off_52w_high_pct": -30.0, "pct_vs_200dma": -12.0}}
        got = ns.potential_score(rec, market="US")
        assert got["score"] is None
        assert got["not_scored_reason"] == ns.REASON_UNKNOWN_STATE

    def test_empty_ladder_state_is_not_scorable(self):
        got = ns.potential_score({"ticker": "X", "ladder": {}}, market="US")
        assert got["score"] is None

    def test_recognized_but_unpriced_state_keeps_its_published_score(self):
        """CONFIRMING TURN is a real ``cycles.LADDER`` member that ``_TRIGGER`` does not
        price. Closing the fail-open must NOT silently re-price it — moving a published
        score is a prereg + gauntlet change, not a bug fix. It stays at 0.40."""
        rec = {"ticker": "X", "ladder": {"state": "CONFIRMING TURN"},
               "tech": {"off_52w_high_pct": -20.0, "pct_vs_200dma": -9.0}}
        got = ns.potential_score(rec, market="US")
        assert got["score"] == 29, "a documented-unpriced state must keep its number"
        assert got["components"]["trigger"] == 0.4

    def test_a_scorable_record_is_unchanged(self):
        rec = {"ticker": "NEM", "ladder": {"state": "FRESH BUY"},
               "tech": {"off_52w_high_pct": -30.0, "pct_vs_200dma": -11.0}}
        got = ns.potential_score(rec, market="US", edge_z=0.0)
        assert isinstance(got["score"], int) and got["score"] > 0
        assert got["scored"] is True
        assert got["call"]["ticker"] == "NEM"

    def test_null_disclosure_is_bilingual_and_natural(self):
        """Plain words in both languages; the ZH twin is Chinese, not a gloss on the
        English shape (no latin letters, no untranslated stat names)."""
        got = ns.potential_score(_limited_rec(), market="US")
        for key in ("band_zh", "note_zh"):
            text = got[key]
            assert text, f"{key} missing"
            assert not re.search(r"[A-Za-z]", text), f"{key} carries English: {text!r}"
        assert got["note_en"] and got["band_en"]
        # banned front-facing vocabulary (glance-tier copy law)
        blob = " ".join([got["band_en"], got["note_en"]]).lower()
        for word in ("validated", "sentinel", "limited record", "null", "trigger"):
            assert word not in blob, f"internal vocabulary leaked: {word}"


class TestTheNullSurvivesItsConsumers:
    """A printed null is only printed if the surfaces downstream of it say so."""

    def test_the_stock_page_says_not_scored_rather_than_a_dash(self):
        """``stockview.js`` renders ``d.name_label || d.band_en``, so a band missing from
        ``_NAME_LABEL`` would fall back to the em dash and HIDE the refusal."""
        from engine.stock_view import _NAME_LABEL

        en, zh = _NAME_LABEL[ns.NOT_SCORED_BAND]
        assert en not in ("—", "")
        assert zh not in ("—", "")
        assert not re.search(r"[A-Za-z]", zh)

    def test_an_unscored_band_is_never_page_state_ok(self):
        """``_conflict``'s fall-through is ``ok``. A page that could not read the name
        has not judged it acceptable."""
        from engine.stock_view import _conflict

        state, _ = _conflict({"band": ns.NOT_SCORED_BAND}, [])
        assert state == "neutral"

    def test_the_table_sorts_a_null_score_last_not_as_zero(self):
        """``sortRows`` must keep nulls at the bottom in BOTH directions — a null that
        parses as 0 would rank an unscorable name above a genuinely weak one."""
        src = STOCKTABLE_JS.read_text(encoding="utf-8")
        assert "var anull = (av == null), bnull = (bv == null);" in src
        assert "if (anull) return 1;" in src and "if (bnull) return -1;" in src

    def test_the_unscored_band_has_its_own_style(self):
        """It must not borrow `low` (red = a claim) or `neutral` (a reading)."""
        css = (REPO / "templates" / "_stock_decision.css.j2").read_text(encoding="utf-8")
        assert f".sv-band-{ns.NOT_SCORED_BAND}" in css


# --------------------------------------------------------------------------- #
# G0.4 — age is measured from the bucket's LAST session, and never runs negative
#        into the fresh filter
# --------------------------------------------------------------------------- #
def _synth_closes(n: int = 400, seed: int = 7) -> pd.Series:
    idx = pd.bdate_range("2024-01-02", periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 + np.cumsum(rng.normal(0, 1.0, n)), index=idx)


class TestKnowabilityAnchoredAge:
    def test_marker_last_session_is_the_bucket_close_not_its_open_label(self):
        """R-SQ2: a §7 marker is LABELLED with its bucket's OPEN date, so the label
        precedes the bar that closed the bucket by up to two sessions. That gap is the
        whole APH/FCX defect — 4 published against a knowable 2."""
        close = _synth_closes()
        grid = sq._tf_grid(close, 3, "US")
        gaps = []
        for label in list(grid.last_session.index)[5:40]:
            got = sq.marker_last_session(close, label)
            assert got == pd.Timestamp(grid.last_session.loc[label])
            gaps.append(int((close.index > pd.Timestamp(label)).sum()
                            - (close.index > got).sum()))
        # 2 sessions is the bucket span; a bucket straddling a market holiday holds one
        # extra business-day ROW that is not an NYSE session, so this row-count reads 3
        # on those. Either way the label understates the age by at least two bars.
        assert 2 <= max(gaps) <= 3, "a 3-session bucket must span 2 sessions past its label"
        assert all(g >= 2 for g in gaps), "the knowable anchor can never precede the label"

    def test_marker_last_session_is_not_confirmation_date(self):
        """The two anchors answer different questions and must not be swapped.
        ``confirmation_date`` walks CONFIRM_BARS buckets further so a forward RETURN is
        not graded off its own answer; an AGE measured from there would read NEGATIVE on
        every genuinely fresh marker."""
        close = _synth_closes()
        # confirmation_date walks the signal_frame index (which drops warmup/flat buckets),
        # so the label must come from there, not from the raw grid.
        frame = sq.signal_frame(close).dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        label = list(frame.index)[20]
        last = sq.marker_last_session(close, label)
        confirm = sq.confirmation_date(close, label)
        assert last is not None and confirm is not None
        assert confirm > last, "confirmation_date must sit further forward than the bucket close"
        assert (close.index > confirm).sum() < (close.index > last).sum()

    def test_marker_last_session_refuses_a_non_label(self):
        close = _synth_closes()
        assert sq.marker_last_session(close, "2019-01-02") is None
        assert sq.marker_last_session(close, None) is None
        assert sq.marker_last_session(close, "not-a-date") is None
        assert sq.marker_last_session(pd.Series(dtype=float), "2024-02-01") is None

    def test_knowable_bars_is_never_older_than_fresh_bars(self):
        close = _synth_closes()
        grid = sq._tf_grid(close, 3, "US")
        strictly_smaller = 0
        for label in list(grid.last_session.index)[5:40]:
            marker = {"date": str(pd.Timestamp(label).date()), "type": "buy"}
            open_anchored = sg._bars_since(close, marker)
            knowable = sg._knowable_bars(close, marker, market_of="AAPL")
            assert knowable is not None
            assert knowable <= open_anchored
            strictly_smaller += int(knowable < open_anchored)
        assert strictly_smaller, "the two anchors never disagreed — the fix is inert"

    def test_knowable_bars_fails_closed_on_an_underivable_anchor(self):
        close = _synth_closes()
        assert sg._knowable_bars(close, {"date": "2019-01-02"}, market_of="AAPL") is None
        assert sg._knowable_bars(close, {}, market_of="AAPL") is None
        assert sg._knowable_bars(close, None, market_of="AAPL") is None

    def test_signal_age_prefers_the_knowable_count(self):
        """The APH/FCX row, both ways round: 4 sessions is outside the board's
        ``FRESH_DAYS = 2`` window; 2 is inside it."""
        verdict = {"fresh_bars": 4, "fresh_bars_knowable": 2}
        age, basis = ubr.signal_age(verdict, "2026-08-03", "2026-08-05")
        assert (age, basis) == (2, ubr.BASIS_SESSIONS)
        assert age <= 2, "the knowable age must clear the fresh window the label failed"

    def test_signal_age_falls_back_when_the_anchor_is_undeliverable(self):
        """A verdict built before the field existed, or one where the bucket label was
        not derivable, keeps the old answer rather than losing its age."""
        assert ubr.signal_age({"fresh_bars": 4}, "2026-08-03", "2026-08-05") == (
            4, ubr.BASIS_SESSIONS)
        assert ubr.signal_age({"fresh_bars": 4, "fresh_bars_knowable": None},
                              "2026-08-03", "2026-08-05") == (4, ubr.BASIS_SESSIONS)

    def test_fresh_bars_itself_is_untouched(self):
        """``fresh_bars`` gates eligibility and FRESH_TICKS across five boards; this lane
        adds a field, it does not re-anchor that one (blast radius owed per
        research/SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md §4)."""
        close = _synth_closes()
        grid = sq._tf_grid(close, 3, "US")
        label = list(grid.last_session.index)[20]
        marker = {"date": str(pd.Timestamp(label).date()), "type": "buy"}
        assert sg._bars_since(close, marker) == int(
            (close.index > pd.Timestamp(label)).sum())

    def test_verdict_key_allowlist_carries_the_new_field(self):
        assert "fresh_bars_knowable" in sg._VERDICT_KEYS
        assert "fresh_bars" in sg._VERDICT_KEYS


class TestNegativeAgeStaysVisibleButIsNotFresh:
    def test_the_engine_still_publishes_the_negative_value(self):
        """HD's row: a signal stamped AFTER the board's own session is a data fault, and
        clamping it to 0 would convert the fault into fake freshness. It stays visible."""
        assert ubr.days_since_signal("2026-08-11", "2026-08-06") == -5

    def test_signal_age_never_launders_a_negative_session_count(self):
        """A negative SESSION count is not a session count. It must not be reported as
        one — the resolver falls through to the disclosed calendar basis."""
        age, basis = ubr.signal_age({"fresh_bars": -3, "fresh_bars_knowable": -3},
                                    "2026-08-11", "2026-08-06")
        assert basis == ubr.BASIS_CALENDAR
        assert age == -5


# --------------------------------------------------------------------------- #
# G0.4 (consumer half) — the fresh-only filter is bounded on BOTH sides
# --------------------------------------------------------------------------- #
_ISFRESH_RE = re.compile(r"function _isFresh\(row\) \{.*?\n  \}", re.DOTALL)


class TestFreshFilterIsBoundedBothSides:
    def test_the_filter_routes_through_the_shared_predicate(self):
        src = STOCKTABLE_JS.read_text(encoding="utf-8")
        assert "filters.freshOnly && !_isFresh(r)" in src
        # the open-below form must be gone from the filter path entirely
        assert "days_since_signal <= FRESH_DAYS" not in src

    def test_the_predicate_bounds_below(self):
        src = STOCKTABLE_JS.read_text(encoding="utf-8")
        body = _ISFRESH_RE.search(src)
        assert body, "_isFresh not found in templates/stocktable.js"
        assert "age >= 0" in body.group(0)
        assert "age <= FRESH_DAYS" in body.group(0)

    def test_the_paired_site_copy_matches(self):
        """Plain-copy asset law: templates/stocktable.js ships as site/stocktable.js."""
        assert STOCKTABLE_JS.read_bytes() == SITE_STOCKTABLE_JS.read_bytes()

    @_needs_node
    def test_runtime_behaviour_of_the_predicate(self):
        """The six measured rows (HD, ASML, ELV, TSM, TJX, AEP at −5) must be OUT."""
        src = STOCKTABLE_JS.read_text(encoding="utf-8")
        body = _ISFRESH_RE.search(src).group(0)
        harness = (
            "var FRESH_DAYS = 2;\n" + body + "\n"
            "var cases = [-5, -1, 0, 1, 2, 3, null, undefined];\n"
            "console.log(JSON.stringify(cases.map(function(a){\n"
            "  return _isFresh({days_since_signal: a});\n"
            "})));\n"
        )
        res = subprocess.run([shutil.which("node"), "-e", harness],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr
        got = json.loads(res.stdout.strip())
        assert got == [False, False, True, True, True, False, False, False]


# --------------------------------------------------------------------------- #
# The user-facing disclosure the fixed staleness block finally reaches
# --------------------------------------------------------------------------- #
DASHBOARD = REPO / "templates" / "dashboard.html.j2"


def _stale_banner_block() -> str:
    lines = DASHBOARD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if "_su.staleness.get('delayed')" in ln)
    end = next(i for i, ln in enumerate(lines[start:], start) if ln.strip() == "{% endif %}")
    return "\n".join(lines[start:end + 1])


def _render_banner(stale: dict | None) -> str:
    import jinja2

    tpl = jinja2.Environment().from_string(_stale_banner_block())
    return tpl.render(_su={"staleness": stale} if stale is not None else {}).strip()


class TestDelayedBoardBanner:
    def test_nothing_renders_on_a_fresh_board(self):
        assert _render_banner({"delayed": False, "price_through": "2026-08-06",
                               "age_days": 0, "sessions_behind": 0}) == ""
        assert _render_banner(None) == ""

    def test_delayed_board_states_the_vintage_in_both_languages(self):
        out = _render_banner({"delayed": True, "price_through": "2026-07-31",
                              "age_days": 6, "sessions_behind": 4, "unknown": False})
        assert "2026-07-31" in out
        assert "4 sessions behind" in out
        assert 'class="l-en"' in out and 'class="l-zh"' in out
        assert "落后 4 个交易日" in out

    def test_the_sentinel_phrase_contract_is_intact(self):
        """scripts/freshness_sentinel.py::_DELAY_RE reads the delayed-board vintage out
        of the RENDERED English. Rewording this line without keeping the phrase turns the
        ops sentinel blind with no test failing anywhere near it."""
        from scripts.freshness_sentinel import _DELAY_RE

        out = _render_banner({"delayed": True, "price_through": "2026-07-31",
                              "age_days": 6, "sessions_behind": 4, "unknown": False})
        assert _DELAY_RE.findall(out) == ["2026-07-31"]

    def test_an_undatable_board_gets_its_own_plain_words(self):
        """The fail-closed sentinel reaches the UI: `delayed` with no `price_through`
        must not render "prices as of ?"."""
        out = _render_banner({"delayed": True, "price_through": None, "age_days": None,
                              "sessions_behind": None, "unknown": True})
        assert out, "the unknown branch rendered nothing"
        assert "?" not in out
        assert "None" not in out
        assert 'class="l-zh"' in out

    def test_the_copy_is_glance_tier(self):
        """No internal state names, no untranslated stat names, no refutation vocabulary
        (operator 2026-07-27), and never the word 'validated'."""
        out = _render_banner({"delayed": True, "price_through": "2026-07-31",
                              "age_days": 6, "sessions_behind": 4, "unknown": False})
        lowered = out.lower()
        for banned in ("validated", "majority_through", "price_through", "staleness",
                       "falsifier", "refuted", "证伪", "fail-closed", "panel"):
            assert banned.lower() not in lowered, f"banned copy: {banned}"


# --------------------------------------------------------------------------- #
# The universe drop must land in the ARTIFACT, not only in a CI annotation
# --------------------------------------------------------------------------- #
def _write_breadth_group(root: Path, group: str, tickers: list[str]) -> None:
    d = root / group
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2026-01-02", periods=40)
    pd.DataFrame({t: np.linspace(10.0, 20.0, len(idx)) for t in tickers},
                 index=idx).to_parquet(d / "_closes_cache.parquet")
    pd.DataFrame({"name": [f"{t} Inc" for t in tickers],
                  "sector": ["Materials"] * len(tickers)},
                 index=pd.Index(tickers, name="ticker")).to_parquet(
        d / "constituents.parquet")


@pytest.fixture()
def _isolated_universe(tmp_path, monkeypatch):
    """A data dir with the three S&P breadth groups present and russell ABSENT —
    the gitignored-cache shape that silently drops ~1,400 small caps."""
    import scripts.build_stock_library as bsl

    (tmp_path / "stocks").mkdir()          # present-but-empty deep-history store
    _write_breadth_group(tmp_path, "breadth", ["AAA", "BBB"])
    _write_breadth_group(tmp_path, "smallcap_breadth", ["CCC"])
    _write_breadth_group(tmp_path, "midcap_breadth", ["DDD"])
    monkeypatch.setattr(bsl.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bsl.config, "load",
                        lambda: {"yahoo": {"tickers": {"sectors": [], "extras": []}},
                                 "stock_search": {}})
    return bsl


class TestUniverseSourceDisclosure:
    def test_missing_russell_cache_is_disclosed_in_the_artifact(self, _isolated_universe,
                                                                capsys):
        bsl = _isolated_universe
        bsl.universe()
        src = bsl.universe_sources()

        assert src["complete"] is False
        assert src["missing"] == ["russell_breadth"]
        by_id = {g["id"]: g for g in src["groups"]}
        assert by_id["russell_breadth"]["status"] == "missing"
        assert by_id["russell_breadth"]["members"] == 0
        # the groups that DID load are counted, so a consumer can see the shortfall
        assert by_id["breadth"]["status"] == "ok" and by_id["breadth"]["members"] == 2
        assert src["total"] == 4

        # the loud line-start annotation is kept alongside the artifact disclosure
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") and "russell_breadth" in line
                   for line in out.splitlines()), out

    def test_the_disclosure_is_bilingual(self, _isolated_universe):
        bsl = _isolated_universe
        bsl.universe()
        missing = [g for g in bsl.universe_sources()["groups"]
                   if g["status"] != "ok"][0]
        assert missing["note_en"] and missing["note_zh"]
        assert not re.search(r"[A-Za-z]", missing["note_zh"].replace("2000", ""))

    def test_a_complete_universe_reports_complete(self, tmp_path, monkeypatch):
        import scripts.build_stock_library as bsl

        (tmp_path / "stocks").mkdir()
        for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
            _write_breadth_group(tmp_path, grp, [f"{grp[:2].upper()}X"])
        monkeypatch.setattr(bsl.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(bsl.config, "load",
                            lambda: {"yahoo": {"tickers": {"sectors": [], "extras": []}},
                                     "stock_search": {}})
        bsl.universe()
        src = bsl.universe_sources()
        assert src["complete"] is True
        assert src["missing"] == []

    def test_every_group_reports_even_when_it_loads(self, _isolated_universe):
        """Silence is what made the drop invisible — a group that loaded must still be
        on the record, or 'complete' is unfalsifiable."""
        bsl = _isolated_universe
        bsl.universe()
        ids = [g["id"] for g in bsl.universe_sources()["groups"]]
        for expected in ("stocks_deep", "breadth", "smallcap_breadth",
                         "midcap_breadth", "russell_breadth", "curated_extras"):
            assert expected in ids
