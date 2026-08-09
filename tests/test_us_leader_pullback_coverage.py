"""tests/test_us_leader_pullback_coverage.py — the LEADER-PULLBACK coverage publisher.

WHAT THIS SUITE IS FOR
----------------------
`engine/us_early_turn.py` (#5105) resolves the EARLY-TURN starter tier's LEADER licence
from ``site/anticipationdata/us_leader_pullback.json``.  Nothing published that file, so
the leader half of the intake was structurally incapable of admitting anything on a
production run — fail-closed, honest, and dead.

The cases here are PRODUCTION-PATH by construction.  The round-trip case writes a real
artifact with the real publisher and then makes the real consumer read it off disk and
the real originator admit off that read; the only thing redirected is WHERE ``site/``
lives, which is the house ``tmp_path`` convention.  A mock of the loader would prove the
mock.

MUTATION NOTES (what each pin actually catches) are on the cases themselves.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import prophet_bridge as pb  # noqa: E402
from engine import us_early_turn as et  # noqa: E402
from engine import us_leader_pullback as organ  # noqa: E402
from engine import us_leader_pullback_coverage as cov  # noqa: E402
from engine import us_turn_watch as tw  # noqa: E402

ASOF = "2026-07-02"           # a Thursday NYSE session

#: The GENUINE loader, captured at import time and therefore before any monkeypatch.
#: The end-to-end cases bind it to a test site root instead of replacing it with a stub —
#: the point of those cases is that the real file-reading code runs on a real file.
_REAL_LOAD_STATES = et.load_leader_pullback_states


# --------------------------------------------------------------------------- #
# Fixtures — parquet stores shaped like the real one                           #
# --------------------------------------------------------------------------- #
def _noise(n: int, seed: int, amp: float = 0.008) -> np.ndarray:
    """Deterministic multiplicative wiggle.

    LOAD-BEARING: StochRSI is a stochastic OF RSI, so a frictionless exponential has a
    constant RSI, a zero-width StochRSI range and an undefined %K.  A smooth fixture
    measures nothing and the organ correctly refuses to state it.
    """
    return np.exp(np.random.default_rng(seed).normal(0.0, amp, n))


def _leader_pullback_closes(n: int = 400, seed: int = 13) -> list[float]:
    """A high-RS leader that ran to 118 and is ten sessions into a controlled retrace.

    Mirrors ``tests/test_prophet_anticipation_intake._leader_reset_series`` — the same
    shape §6.9 R4 is about, lengthened past the organ's own 260-bar floor.
    """
    pull = (0.985, 0.972, 0.960, 0.950, 0.941, 0.933, 0.928, 0.924, 0.921, 0.919)
    up = (1.010, 1.014)
    base = n - len(pull) - len(up)
    trend = np.array([1.0 * (1.004 ** i) for i in range(base)])
    closes = list(trend * _noise(base, seed))
    closes = [c * 118.0 / closes[-1] for c in closes]      # the pullback HIGH is 118
    top = closes[-1]
    closes += [top * f for f in pull]
    low = closes[-1]
    closes += [low * f for f in up]
    return closes


def _laggard_closes(n: int = 400, seed: int = 29) -> list[float]:
    """A grinding decliner — a real member of the cross-section, never a leader."""
    down = np.array([100.0 * (0.9975 ** i) for i in range(n)])
    return list(down * _noise(n, seed, 0.010))


def _flat_benchmark(n: int = 400, seed: int = 5) -> list[float]:
    base = np.array([400.0 * (1.0005 ** i) for i in range(n)])
    return list(base * _noise(n, seed, 0.004))


def _frame(closes: list[float], end: str = ASOF, volume: float | None = 1_000_000.0
           ) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=len(closes))
    data = {"open": closes, "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes], "close": closes}
    if volume is not None:
        data["volume"] = [volume] * len(closes)
    return pd.DataFrame(data, index=idx)


def _store(tmp_path: Path, frames: dict[str, pd.DataFrame]) -> Path:
    """A ``data/`` root carrying ``yahoo/<TICKER>.parquet`` for each frame."""
    root = tmp_path / "data"
    (root / tw.DECK_STORE).mkdir(parents=True, exist_ok=True)
    for ticker, frame in frames.items():
        frame.to_parquet(root / tw.DECK_STORE / f"{ticker}.parquet")
    return root


def _universe_store(tmp_path: Path, *, n_laggards: int = 8) -> Path:
    """One leader in a controlled pullback, a benchmark, and enough laggards that the
    cross-sectional percentile is a real ranking rather than a two-name coin flip."""
    frames = {
        "LEADR": _frame(_leader_pullback_closes()),
        tw.BENCHMARK: _frame(_flat_benchmark()),
    }
    for i in range(n_laggards):
        frames[f"LAG{i}"] = _frame(_laggard_closes(seed=29 + i))
    return _store(tmp_path, frames)


@pytest.fixture()
def published(tmp_path: Path) -> tuple[Path, Path, dict]:
    """``(data_root, site_root, artifact)`` after a real publisher run."""
    data_root = _universe_store(tmp_path)
    site_root = tmp_path / "site"
    out, artifact = cov.run(data_root, site_root)
    assert out is not None, artifact["coverage"]
    return data_root, site_root, artifact


# =========================================================================== #
# 1. The contract with the consumer — the whole reason this module exists      #
# =========================================================================== #
class TestConsumerContract:
    def test_the_publisher_writes_the_exact_path_the_intake_reads(self):
        """THE DEFECT THIS SUITE EXISTS FOR.  A publisher one directory away from its
        consumer is the same as no publisher, and the failure mode is silent: the intake
        fails closed and reports 'no coverage published' either way."""
        assert cov.ARTIFACT == et._LEADER_ARTIFACT

    def test_the_schema_is_one_the_intake_accepts(self, published):
        _data, site_root, artifact = published
        assert artifact["schema"] == organ.SCHEMA
        # The consumer's own family check, reproduced here so a schema rename that
        # silently empties the map fails on this line instead of in production.
        assert artifact["schema"].startswith(et._LEADER_SCHEMA.rsplit(".", 1)[0])
        assert et.load_leader_pullback_states(site_root=site_root)

    def test_a_published_state_resolves_all_the_way_through_leader_pullback_context(
            self, published):
        """PRODUCTION PATH, no mock: the real loader reads the real file the real
        publisher wrote, and the real context function grades it."""
        _data, site_root, _artifact = published
        states = et.load_leader_pullback_states(site_root=site_root)
        ctx = et.leader_pullback_context("LEADR", states=states)
        assert ctx["source"] == "us_leader_pullback"
        assert ctx["state"] in et.LEADER_PULLBACK_CONTEXT_STATES, ctx
        assert ctx["leader_pullback"] is True
        assert ctx["construction_era"] == organ.CONSTRUCTION_ERA
        assert ctx["pullback_high"] is not None

    def test_dropping_null_keys_is_LOSSLESS_for_every_consumer_read(self, published):
        """`_compact` removes None values to keep a ~700-name nightly artifact lean.
        That is only safe because every downstream read is `Mapping.get`, which cannot
        tell an absent key from a present None.  This pins the equivalence rather than
        the intention."""
        data_root, _site, _artifact = published
        close, vol, _ = cov.load_bars("LEADR", data_root)
        rs = cov.rs_cross_section({"LEADR": close}, None)
        assert rs == {}, "no benchmark must mean no cross-section, not a fabricated one"
        full = organ.latest(close, rs_pct=pd.Series(0.95, index=close.index), volume=vol)
        compact = cov._compact(full)
        assert None not in compact.values()
        for key, value in full.items():
            assert compact.get(key) == value, key

    def test_a_name_the_organ_nulled_keeps_its_REASON_not_a_silent_absence(
            self, tmp_path):
        """A short-history name must be distinguishable from a name that is simply not
        a leader.  The organ says which; the artifact must carry that through."""
        data_root = _store(tmp_path, {
            "LEADR": _frame(_leader_pullback_closes()),
            tw.BENCHMARK: _frame(_flat_benchmark()),
            # 300 bars: past the publisher's 260 floor, so it grades — and flat enough
            # that the organ's own indicators refuse to warm.
            "FLAT": _frame([50.0] * 300),
        })
        site_root = tmp_path / "site"
        out, artifact = cov.run(data_root, site_root)
        assert out is not None
        row = artifact["states"]["FLAT"]
        assert row.get("state") is None
        assert row.get("null_reason"), row
        ctx = et.leader_pullback_context(
            "FLAT", states=et.load_leader_pullback_states(site_root=site_root))
        assert ctx["leader_pullback"] is False
        assert "nulled this name" in ctx["reason"]

    def test_a_name_the_ORGAN_RAISED_on_stays_in_the_map_as_a_named_null(
            self, tmp_path, monkeypatch):
        """Dropping it would read downstream as "outside the organ's universe" — a
        different and FALSE statement.  The organ has the name; it could not state it."""
        data_root = _universe_store(tmp_path, n_laggards=2)
        real = organ.latest

        def _boom(close, **kw):
            if float(close.iloc[-1]) > 50.0:      # the leader, never the laggards
                raise RuntimeError("synthetic organ failure")
            return real(close, **kw)

        monkeypatch.setattr(organ, "latest", _boom)
        site_root = tmp_path / "site"
        out, artifact = cov.run(data_root, site_root)
        assert out is not None
        row = artifact["states"]["LEADR"]
        assert row.get("state") is None
        assert row["null_reason"] == "organ raised: RuntimeError"
        assert row["construction_era"] == organ.CONSTRUCTION_ERA and row["asof"]
        ctx = et.leader_pullback_context(
            "LEADR", states=et.load_leader_pullback_states(site_root=site_root))
        assert "nulled this name" in ctx["reason"]
        assert "outside" not in ctx["reason"]


# =========================================================================== #
# 2. Construction — PIT, no permissive defaults                                #
# =========================================================================== #
class TestConstruction:
    def test_the_cross_section_is_the_ORGANS_own_and_is_never_invented(self, published):
        """The organ refuses to reach for a cross-section so a single-name call cannot
        leak one.  The publisher must therefore SUPPLY the organ's own construction, not
        a second RS of its own devising."""
        source = (ROOT / "engine" / "us_leader_pullback_coverage.py").read_text(
            encoding="utf-8")
        assert "organ.rs_excess_percentile" in source
        # No parallel relative-strength arithmetic in this module.
        assert "rank(" not in source and ".rank(" not in source
        assert "shift(" not in source

    def test_the_cross_section_population_is_the_PRE_REGISTERED_one(self):
        """`RS_TOP_PCT = 0.75` is a v0 pre-registered constant and a quartile is a
        statement ABOUT A POPULATION.  It was measured against the graded deck store
        (#5026, leader fires 28 -> 7), and the TURN WATCH desk's leg (d) ranks over the
        same rung — so widening this ladder would both restate the quartile and let two
        artifacts disagree about the same name on the same night.

        MEASURED GAP, recorded so the trade-off is not re-litigated from memory
        (2026-08-09, committed 2026-08-07 board): 28 of 54 Prophet candidates are absent
        from this rung; 25 of those sit on the lower rungs at the SAME adjustment basis.
        Widening is safe for the basis and would take board coverage 26/54 -> 51/54, at
        697 -> 2,994 cross-section names.  That is a §6.6 re-measurement jointly with the
        desk, not a publisher change — this test is the tripwire, not a veto.
        """
        assert cov.STORE_LADDER == (tw.DECK_STORE,)
        assert tw.STORE_LADDER[0] == tw.DECK_STORE, (
            "the desk's own first rung must stay the population this one ranks over")

    def test_the_ladder_actually_used_is_PUBLISHED(self, published):
        _data, _site, artifact = published
        assert artifact["coverage"]["store_ladder"] == list(cov.STORE_LADDER)

    def test_no_rs_means_NO_STATE_never_a_manufactured_no(self, tmp_path):
        """A missing cross-section must not read as 'not a leader'.  Mutation: make the
        publisher default rs_pct to 0.0 and this flips to a board of NONE — the exact
        shape a broken cross-section would wear if it were allowed to fail open."""
        close = _frame(_leader_pullback_closes())["close"]
        row = organ.latest(close, rs_pct=None)
        assert row["state"] is None
        assert row["null_reason"] == "rs_pct_unavailable"

    def test_the_percentile_at_a_DATE_does_not_move_when_later_bars_arrive(self):
        """PIT pin.  `rs_excess_percentile` ranks within each date, so tomorrow's bar
        cannot restate today's percentile.  Mutation: a whole-sample rank (or any
        centred/expanding normalisation) breaks this immediately."""
        n = 400
        wide = pd.DataFrame({
            "LEADR": _leader_pullback_closes(n),
            "LAG0": _laggard_closes(n, seed=29),
            "LAG1": _laggard_closes(n, seed=30),
        }, index=pd.bdate_range(end=ASOF, periods=n))
        bench = pd.Series(_flat_benchmark(n), index=wide.index)

        full = organ.rs_excess_percentile(wide, bench)
        truncated = organ.rs_excess_percentile(wide.iloc[:-25], bench.iloc[:-25])
        pd.testing.assert_frame_equal(
            full.iloc[:-25].tail(50), truncated.tail(50), check_freq=False)

    def test_the_state_at_a_SESSION_does_not_move_when_later_bars_arrive(self, tmp_path):
        """The same pin one level up: the whole publisher, run on a store truncated by
        25 sessions, must produce the state the full run produced 25 sessions ago."""
        closes = _leader_pullback_closes()
        bench = _flat_benchmark()
        wide = pd.DataFrame({"LEADR": closes},
                            index=pd.bdate_range(end=ASOF, periods=len(closes)))
        bench_s = pd.Series(bench, index=wide.index)
        rs = organ.rs_excess_percentile(wide, bench_s)["LEADR"]

        frame = organ.evaluate(wide["LEADR"], rs_pct=rs)
        cut = len(closes) - 25
        rs_cut = organ.rs_excess_percentile(wide.iloc[:cut], bench_s.iloc[:cut])["LEADR"]
        frame_cut = organ.evaluate(wide["LEADR"].iloc[:cut], rs_pct=rs_cut)
        assert frame["state"].iloc[cut - 1] == frame_cut["state"].iloc[-1]

    def test_the_close_series_is_the_one_the_TURN_WATCH_desk_evaluates(self, tmp_path):
        """`load_bars` reads close AND volume in one pass rather than paying a second
        parquet read per name — so it must normalise the close EXACTLY as
        `us_turn_watch.load_close` does.  Duplicated timestamps, an unsorted index and
        an embedded NaN are the three ways two normalisations diverge in the wild."""
        idx = list(pd.bdate_range(end=ASOF, periods=8))
        messy = pd.DataFrame(
            {"close": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0],
             "volume": [10.0] * 8},
            index=[idx[3], idx[1], idx[2], idx[0], idx[4], idx[4], idx[6], idx[5]])
        root = tmp_path / "data"
        (root / tw.DECK_STORE).mkdir(parents=True)
        messy.to_parquet(root / tw.DECK_STORE / "MESSY.parquet")

        mine, vol, store = cov.load_bars("MESSY", root)
        theirs, their_store = tw.load_close("MESSY", root, ladder=(tw.DECK_STORE,))
        assert store == their_store
        pd.testing.assert_series_equal(mine, theirs, check_names=False)
        assert vol is not None and list(vol.index) == list(mine.index)

    def test_a_store_with_no_volume_column_is_a_valid_input_not_a_crash(self, tmp_path):
        """The organ nulls its anchored VWAP with a named reason when volume is absent;
        it never fabricates one.  The publisher must let it."""
        data_root = _store(tmp_path, {
            "LEADR": _frame(_leader_pullback_closes(), volume=None),
            tw.BENCHMARK: _frame(_flat_benchmark(), volume=None),
        })
        out, artifact = cov.run(data_root, tmp_path / "site")
        assert out is not None
        row = artifact["states"]["LEADR"]
        assert row.get("avwap") is None
        assert row.get("avwap_null_reason") == "no_volume_in_store"


# =========================================================================== #
# 3. Fail-closed publishing                                                    #
# =========================================================================== #
class TestFailClosed:
    def test_a_runwide_data_failure_does_NOT_overwrite_a_good_artifact(
            self, tmp_path, capsys):
        """A board of nulls and a broken price store look identical from downstream.
        Writing one would delete real coverage AND make the outage invisible, so the
        publisher keeps yesterday's file and annotates instead."""
        data_root, site_root, _artifact = self._published(tmp_path)
        before = cov.artifact_path(site_root).read_text(encoding="utf-8")

        empty = tmp_path / "empty_data"
        (empty / tw.DECK_STORE).mkdir(parents=True)
        out, artifact = cov.run(empty, site_root)

        assert out is None
        assert artifact["coverage"]["publishable"] is False
        assert cov.artifact_path(site_root).read_text(encoding="utf-8") == before
        err = capsys.readouterr().out
        assert "::warning title=leader-pullback-coverage::" in err

    def test_a_universe_with_no_benchmark_publishes_NOTHING(self, tmp_path, capsys):
        """No benchmark means no cross-section, which means the organ can state nothing.
        That is a data failure, not a quiet tape."""
        data_root = _store(tmp_path, {"LEADR": _frame(_leader_pullback_closes())})
        out, artifact = cov.run(data_root, tmp_path / "site")
        assert out is None
        assert artifact["coverage"]["cross_section_names"] == 0
        assert artifact["coverage"]["graded"] == 1
        assert "::warning" in capsys.readouterr().out

    def test_a_collapsing_universe_is_ANNOUNCED_even_though_it_publishes(
            self, tmp_path, capsys):
        """The shrink direction is the one a detector goes blind in: half the coverage
        reads downstream exactly like half the market going quiet."""
        data_root, site_root, artifact = self._published(tmp_path, n_laggards=20)
        assert artifact["coverage"]["states_published"] >= 20
        capsys.readouterr()

        thin = _store(tmp_path / "thin", {
            "LEADR": _frame(_leader_pullback_closes()),
            tw.BENCHMARK: _frame(_flat_benchmark()),
        })
        out, _ = cov.run(thin, site_root)
        assert out is not None, "a shrink ANNOUNCES, it never blocks"
        assert "leader-pullback-coverage-shrink" in capsys.readouterr().out

    def test_the_publisher_writes_ONE_site_file_and_touches_data_not_at_all(
            self, tmp_path):
        """Nightly is the sole advancer of forward ledgers; this is a per-run site
        artifact builder.  Pinned on the FILESYSTEM, not on a source grep: an accidental
        ledger write would otherwise only surface on a night an intraday lane discarded
        it."""
        data_root = _universe_store(tmp_path)
        site_root = tmp_path / "site"

        def _tree(root: Path) -> dict[str, int]:
            return {str(p.relative_to(root)): p.stat().st_size
                    for p in sorted(root.rglob("*")) if p.is_file()}

        before = _tree(data_root)
        out, _artifact = cov.run(data_root, site_root)
        assert _tree(data_root) == before, "the publisher must never write under data/"
        assert list(_tree(site_root)) == [str(Path(*cov.ARTIFACT))]
        assert out == site_root.joinpath(*cov.ARTIFACT)

    def test_the_run_is_deterministic_on_a_frozen_store(self, tmp_path):
        """Two runs over the same bytes must produce the same bytes.  A publisher that
        drifts run to run makes every downstream diff unreadable."""
        data_root = _universe_store(tmp_path)
        first = cov.write_artifact(cov.compute_coverage(data_root), tmp_path / "a")
        second = cov.write_artifact(cov.compute_coverage(data_root), tmp_path / "b")
        one = json.loads(first.read_text(encoding="utf-8"))
        two = json.loads(second.read_text(encoding="utf-8"))
        for payload in (one, two):
            payload.pop("runtime_seconds", None)
        assert one == two

    @staticmethod
    def _published(tmp_path: Path, *, n_laggards: int = 8) -> tuple[Path, Path, dict]:
        data_root = _universe_store(tmp_path, n_laggards=n_laggards)
        site_root = tmp_path / "site"
        _out, artifact = cov.run(data_root, site_root)
        return data_root, site_root, artifact


# =========================================================================== #
# 4. Disclosure                                                                #
# =========================================================================== #
class TestDisclosure:
    def test_the_artifact_is_era_stamped_and_display_tier(self, published):
        _data, _site, artifact = published
        assert artifact["selection_era"] == tw.SELECTION_ERA == "anticipation-v1-2026-08-08"
        assert artifact["construction_era"] == organ.CONSTRUCTION_ERA
        assert artifact["authority"]["tier"] == "display"
        assert artifact["authority"]["may_rank"] is False
        assert artifact["authority"]["may_gate"] is False
        assert artifact["authority"]["may_size"] is False
        assert artifact["authority"]["may_escalate"] is False

    def test_every_disclosure_line_ships_with_its_ZH_half(self, published):
        _data, _site, artifact = published
        assert artifact["disclosure"] and artifact["disclosure_zh"]
        assert artifact["disclosure_zh"] != artifact["disclosure"]
        assert any("一" <= ch <= "鿿" for ch in artifact["disclosure_zh"])

    def test_the_session_stamp_is_the_MAJORITY_never_the_max(self, tmp_path):
        """A max() stamp fails OPEN: one instrument reaching a later date makes the
        whole artifact read fresh while the tape it is computed on is behind."""
        ahead = _frame(_laggard_closes(seed=77),
                       end=str((pd.Timestamp(ASOF) + pd.offsets.BDay(3)).date()))
        data_root = _store(tmp_path, {
            "LEADR": _frame(_leader_pullback_closes()),
            "LAG0": _frame(_laggard_closes(seed=29)),
            "LAG1": _frame(_laggard_closes(seed=30)),
            "AHEAD": ahead,
            tw.BENCHMARK: _frame(_flat_benchmark()),
        })
        _out, artifact = cov.run(data_root, tmp_path / "site")
        assert artifact["data_session"] == ASOF
        assert artifact["max_session"] > ASOF
        assert "newer bar" in (artifact["session_note"] or "")

    def test_coverage_counts_the_population_it_actually_stated(self, published):
        _data, _site, artifact = published
        c = artifact["coverage"]
        assert c["states_published"] == len(artifact["states"])
        assert c["graded"] == c["states_published"]
        assert c["cross_section_names"] == c["graded"]
        assert sum(c["state_counts"].values()) + sum(c["null_counts"].values()) == \
            c["states_published"]
        assert c["min_bars"] == organ.MIN_HISTORY_BARS == 260

    def test_github_annotations_start_the_line_and_are_not_logged(self):
        """House law: `log.warning("::warning ...")` emits `WARNING ::warning ...` and
        GitHub silently drops it — the call reviews as an alarm, runs clean, and produces
        nothing in the Actions summary.  It shipped dead five times before #3587."""
        for rel in ("engine/us_leader_pullback_coverage.py",
                    "scripts/build_leader_pullback_coverage.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if "::warning" in stripped or "::error" in stripped:
                    assert "log." not in stripped, (rel, line)
                # An annotation opening a string literal must open a print() line.
                if any(tok in stripped for tok in ('"::', "'::", 'f"::', "f'::")):
                    assert stripped.startswith("print("), (rel, line)
            # `flush` is load-bearing: stdout is block-buffered when piped in CI, so an
            # unflushed annotation on a step that is later killed never reaches the log.
            tree = ast.parse(text)
            annotations = 0
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "print" and node.args):
                    continue
                head = node.args[0]
                if isinstance(head, ast.JoinedStr) and head.values:
                    head = head.values[0]
                if not (isinstance(head, ast.Constant)
                        and isinstance(head.value, str)
                        and head.value.startswith("::")):
                    continue
                annotations += 1
                assert any(kw.arg == "flush" and getattr(kw.value, "value", None) is True
                           for kw in node.keywords), (rel, node.lineno)
            assert annotations >= 1, rel


# =========================================================================== #
# 5. END TO END — the publisher licenses a real origination                    #
# =========================================================================== #
class TestEndToEnd:
    def test_the_published_artifact_licenses_an_EARLY_TURN_starter(
            self, tmp_path, monkeypatch):
        """THE WHOLE POINT, end to end and unmocked at every seam that matters.

        The publisher writes the artifact from a parquet store; `originate_plans` — the
        real nightly originator — resolves the leader licence by READING THAT FILE
        through the real `load_leader_pullback_states`, and admits the name as an
        EARLY-TURN starter.  The only redirection is the site root.

        Its mutation half is the next case: delete the artifact, change nothing else,
        and the identical board row stops admitting.
        """
        data_root = _universe_store(tmp_path)
        site_root = tmp_path / "site"
        out, _artifact = cov.run(data_root, site_root)
        assert out is not None and out.exists()

        prices = _frame(_leader_pullback_closes())
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        monkeypatch.setattr(et, "load_basket_turn_membership", lambda *a, **k: {})
        # NOT a stub: the REAL loader, bound to the site root the publisher wrote to.
        monkeypatch.setattr(et, "load_leader_pullback_states",
                            lambda *a, **k: _REAL_LOAD_STATES(site_root=site_root))

        stats: dict = {}
        plans = self._originate(tmp_path, prices, stats)
        assert plans, "the board row must originate at all"
        assert plans[0]["admission_class"] == pb.ADMISSION_CLASS_EARLY_TURN
        assert stats["early_turn_starters"] == ["LEADR"]
        # WHICH organ licensed it, stamped on the plan the nightly publishes.
        assert plans[0]["early_turn"]["leader_pullback_source"] == "us_leader_pullback"
        assert "leader pullback" in plans[0]["early_turn"]["reason"]
        licensed = plans[0]["entry_zone"]["leader_pullback"]
        assert licensed["state"] in et.LEADER_PULLBACK_CONTEXT_STATES
        assert licensed["construction_era"] == organ.CONSTRUCTION_ERA
        # The zone law fires off that licence: reset band, chase line at the organ's own
        # pullback high — the ADAM acceptance shape.
        zone = plans[0]["entry_zone"]
        assert zone["zone_class"] == pb.ZONE_CLASS_RESET_BAND
        assert zone["stance"] == pb.ZONE_STANCE_STARTER
        assert zone["chase_above"] == pytest.approx(licensed["pullback_high"], rel=1e-6)
        # The receipt separating "covered and did not qualify" from "not covered".
        assert stats["leader_pullback_coverage"] == {
            "map_tickers": 10, "plans": 1, "with_organ_state": 1,
            "outside_organ_universe": 0, "no_coverage_published": 0, "licensed": 1}

    def test_with_the_artifact_ABSENT_the_identical_row_admits_NOTHING(
            self, tmp_path, monkeypatch):
        """The mutation half — and the state of the world before this publisher existed.
        Without it the case above passes on the signature alone and the whole publisher
        could be deleted unnoticed."""
        site_root = tmp_path / "site"       # never written to
        prices = _frame(_leader_pullback_closes())
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        monkeypatch.setattr(et, "load_basket_turn_membership", lambda *a, **k: {})
        monkeypatch.setattr(et, "load_leader_pullback_states",
                            lambda *a, **k: _REAL_LOAD_STATES(site_root=site_root))

        stats: dict = {}
        plans = self._originate(tmp_path, prices, stats)
        assert plans
        assert plans[0]["admission_class"] != pb.ADMISSION_CLASS_EARLY_TURN
        assert stats.get("early_turn_starters") in (None, [])
        assert plans[0]["early_turn"]["leader_pullback_source"] == "unavailable"
        assert "published no coverage" in (
            plans[0]["entry_zone"]["leader_pullback"]["reason"])
        # And the zone law cannot apply either — the licence is what unlocks it.
        assert plans[0]["entry_zone"]["zone_class"] != pb.ZONE_CLASS_RESET_BAND
        # The receipt says WHICH zero this is: nothing published, not "nothing qualified".
        receipt = stats["leader_pullback_coverage"]
        assert receipt["no_coverage_published"] == receipt["plans"] == 1
        assert receipt["with_organ_state"] == 0 and receipt["licensed"] == 0

    @staticmethod
    def _originate(tmp_path: Path, prices: pd.DataFrame, stats: dict) -> list[dict]:
        """One ``us_standouts.json`` buy row, shaped like the live artifact, through the
        REAL originator.  Same shape as ``test_prophet_anticipation_intake._buy``."""
        spot = float(prices["close"].iloc[-1])
        standouts = {
            "as_of": ASOF,
            "staleness": {"price_through": ASOF, "delayed": False, "unknown": False,
                          "basis": "panel_majority",
                          "inputs": {"panel": {"mixed_vintage": False}}},
            "gate_go": False,
            "buy": [{
                "ticker": "LEADR",
                "dir": "up",
                "lane": "continuation",
                "prophet": {"version": "us_prophet_v1", "score": 80.0},
                "conviction": {"score": 70, "band": "neutral", "drivers": ["momentum"],
                               "cautions": ["macro risk"],
                               "trust_tier": {"en": "tier-2"}},
                "entry_signal": {
                    "act_level": 3, "status": "buy_now", "spot": spot, "atr_pct": 2.0,
                    "entry_grade": "solid",
                    "buy_zone": {"low": spot * 0.97, "high": spot,
                                 "pct_from_spot": -1.5},
                    "chase_above": spot * 1.01,
                    "timing": {"opens_in_days_lo": 0, "opens_in_days_hi": None},
                },
                "hold": {"state": "HOLD", "anchor": ASOF, "invalidation": spot * 0.9},
                "signal_asof": ASOF,
                "signal": {"tier_cascade": "T2"},
            }],
        }
        path = tmp_path / "us_standouts.json"
        path.write_text(json.dumps(standouts), encoding="utf-8")
        return pb.originate_plans(
            standouts_path=path, asof=ASOF, existing_ids=set(),
            thetadata_store=None, active_keys=set(), intake_stats=stats)
