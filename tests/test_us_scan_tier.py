"""Tests for the §4.5 US SCAN TIER — the widened seeing set ("see everything, admit
selectively").

The tier ships across four modules, and the regressions worth catching are the ones
that would let the widened set quietly become authority, quietly double-count a name,
or quietly render an unrestored store as "no runners tonight":

* ``engine/us_scan_universe.py`` — the liquidity floor. It is a DISPLAYED rule, so the
  printed sentence and the applied comparison must move together; and it must attribute
  every dropped name to exactly one reason, in evaluation order, so the counts sum to
  the store total.
* ``engine/us_context_vector.py`` — the ``tier`` discriminator. Two lanes stamp the same
  monthly part on the same night; the store is only usable for cohort work if the two
  populations never blur and no name survives twice.
* ``engine/prophet_miss_audit.py`` — the scan-tier audit + the W0 mirror. An absent store
  must be a DISCLOSED null carrying the rule that did not run, never an empty runner list.
* ``scripts/heal_shallow_caches.py`` — a splice into a live cache. Prepend-only,
  target-schema-preserving, idempotent: anything less silently rewrites data a consumer
  already trusts.

Hermetic by construction: every test passes ``root=tmp_path``/``event_rows={}``/
``with_context_dims=False`` or builds its own synthetic store under ``tmp_path``. No test
reads the repo's real ``data/`` tree, hits the network, or writes outside tmp_path
(MM_DATA_GUARD). Deterministic: prices are constructed, never randomised, and no
assertion reads a wall clock — the tier's own ``price_through`` is the store's last bar.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import prophet_miss_audit as PMA  # noqa: E402
from engine import us_context_vector as ucv  # noqa: E402
from engine import us_scan_universe as usu  # noqa: E402
from engine.confluence_tiers import MIN_HISTORY  # noqa: E402
import scripts.heal_shallow_caches as HEAL  # noqa: E402
import scripts.run_us_scan_tier as SCAN  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures — context-vector stamps (idiom copied from tests/test_us_context_vector.py)
# --------------------------------------------------------------------------- #

def _verdict(eligible=True, tier="T2", ticks=1, **extra):
    verdict = {
        "eligible": eligible,
        "tier_cascade": tier,
        "tier_sub": "just_crossed",
        "ticks": ticks,
        "bars_to_cross": None,
        "fresh_bars": 3,
        "weight": 0.8,
        "state": "crossed",
        "reason": "macd+stoch confluence",
        "provisional": False,
        "htf_s1": True,
        "htf_s2": False,
        "asof": "2026-08-03",
    }
    verdict.update(extra)
    return verdict


def _is_buyable(verdict):
    return bool(verdict.get("eligible")) and verdict.get("tier_cascade") in {
        "T1", "T2", "T3"}


@pytest.fixture
def append_kwargs(tmp_path):
    """Hermetic kwargs: nothing reads the real repo, nothing calls context_api."""
    return {
        "board_definition": "us_prophet_v1",
        "is_buyable": _is_buyable,
        "root": tmp_path,
        "event_rows": {},
        "with_context_dims": False,
    }


STAMP = "2026-08-03"


# --------------------------------------------------------------------------- #
# fixtures — synthetic census frames and synthetic whole-market stores
# --------------------------------------------------------------------------- #

#: The store's own tip, and a delisted name's frozen last bar. Both are DATA, not
#: clock reads — the floor derives price_through from the tape.
LAST = "2026-08-03"
STALE = "2021-04-16"

_CENSUS_COLUMNS = ["ticker", "bars", "last", "last_close", "mdv20"]


def _row(ticker, *, bars=900, last=LAST, last_close=50.0, mdv20=25e6):
    return {"ticker": ticker, "bars": bars, "last": last,
            "last_close": last_close, "mdv20": mdv20}


def _census(rows) -> pd.DataFrame:
    """A census frame in exactly the shape ``us_scan_universe.census`` returns."""
    return pd.DataFrame(rows, columns=_CENSUS_COLUMNS)


def _write_store_bars(root: Path, ticker: str, closes, volumes,
                      start: str = "2024-01-02") -> None:
    """One per-ticker parquet in the whole-market store, under tmp_path only."""
    store = Path(root) / usu.STORE_REL
    store.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=len(closes), name="date")
    pd.DataFrame({"close": list(closes), "volume": list(volumes)},
                 index=idx).to_parquet(store / f"{ticker}.parquet")


def _flat_name(root: Path, ticker: str, *, bars: int = 220, close: float = 10.0,
               volume: int = 1_000_000) -> None:
    """A boring liquid name that clears every leg of the floor ($10M/day)."""
    _write_store_bars(root, ticker, [close] * bars, [volume] * bars)


# --------------------------------------------------------------------------- #
# 1. the universe discriminator — two cohorts, one store, no blur
# --------------------------------------------------------------------------- #

class TestUniverseDiscriminator:
    """Regression: the two lanes stamp the SAME monthly part on the same night.

    If ``tier`` were ever dropped, defaulted for both lanes, or overwritten by the
    later stamp, every cohort study over this store would silently be reading one
    blended population — and the whole "see everything, admit selectively" claim
    would be unverifiable from the data.
    """

    def test_the_two_stamps_are_recoverable_by_tier(self, append_kwargs, tmp_path):
        curated = {"AAA": _verdict(), "BBB": _verdict(eligible=False, tier=None)}
        scan = {"SCN1": _verdict(), "SCN2": _verdict(tier="T3"),
                "SCN3": _verdict(eligible=False, tier=None)}

        assert ucv.append_candidates(curated, STAMP, tier=ucv.TIER_CURATED,
                                     **append_kwargs) == 2
        assert ucv.append_candidates(scan, STAMP, tier=ucv.TIER_SCAN,
                                     **append_kwargs) == 5

        frame = ucv.load_candidates(tmp_path)
        by_tier = frame.groupby("tier")["ticker"].apply(lambda s: sorted(s)).to_dict()
        assert set(by_tier) == {"curated", "scan"}, \
            "the two cohorts must be exactly the two documented tier strings"
        assert by_tier["curated"] == ["AAA", "BBB"]
        assert by_tier["scan"] == ["SCN1", "SCN2", "SCN3"]
        # and the constants ARE those strings — a rename is a store-schema break
        assert (ucv.TIER_CURATED, ucv.TIER_SCAN) == ("curated", "scan")

    def test_curated_stamp_defaults_to_curated_without_the_kwarg(
        self, append_kwargs, tmp_path
    ):
        """The builder's existing call passes no ``tier``; §4.5 changed nothing for it."""
        assert ucv.append_candidates({"AAA": _verdict()}, STAMP, **append_kwargs) == 1
        assert list(ucv.load_candidates(tmp_path)["tier"]) == ["curated"]

    def test_mdv20_is_carried_on_scan_rows_and_null_on_curated_rows(
        self, append_kwargs, tmp_path
    ):
        """The value the floor was applied on must be readable off the row.

        Null on curated rows is the load-bearing half: that lane never reads the
        whole-market store, so a 0.0 there would be an unmeasured number printed as
        a measurement.
        """
        ucv.append_candidates({"AAA": _verdict()}, STAMP,
                              tier=ucv.TIER_CURATED, **append_kwargs)
        ucv.append_candidates({"SCN1": _verdict()}, STAMP, tier=ucv.TIER_SCAN,
                              liquidity={"SCN1": {"mdv20_usd": 12_500_000.0}},
                              **append_kwargs)
        rows = ucv.load_candidates(tmp_path).set_index("ticker")
        assert rows.loc["SCN1"]["mdv20_usd"] == 12_500_000.0
        assert pd.isna(rows.loc["AAA"]["mdv20_usd"])


# --------------------------------------------------------------------------- #
# 2. keep-first precedence across tiers — the anti-double-count guarantee
# --------------------------------------------------------------------------- #

class TestKeepFirstPrecedenceAcrossTiers:

    def test_a_name_in_both_tiers_survives_once_as_curated(
        self, append_kwargs, tmp_path
    ):
        """Regression: the same ticker stamped by BOTH lanes on one night.

        Two rows would double-count the name in every cohort total, and the scan row
        is the WORSE of the two — it carries no board legs, no lane and no near-miss
        reason, because the scan lane cannot see them. Keep-first must therefore
        preserve the curated row, not merely "a" row.
        """
        curated = _verdict(tier="T1", ticks=1)
        # the scan lane re-gates the same series and can legitimately differ
        scan = _verdict(tier="T3", ticks=42)

        assert ucv.append_candidates({"DUP": curated}, STAMP,
                                     tier=ucv.TIER_CURATED, **append_kwargs) == 1
        assert ucv.append_candidates({"DUP": scan}, STAMP,
                                     tier=ucv.TIER_SCAN, **append_kwargs) == 1

        frame = ucv.load_candidates(tmp_path)
        assert len(frame) == 1, "the name was stamped twice and survived twice"
        row = frame.iloc[0]
        assert row["tier"] == ucv.TIER_CURATED
        # the whole ROW is the curated one, not just its tier label
        assert row["tier_cascade"] == "T1" and row["ticks"] == 1

    def test_tier_is_deliberately_absent_from_the_dedupe_key(self):
        """Adding ``tier`` to the key would keep BOTH rows for a name in both sets.

        The key is the fence; ``tier`` is a payload column. If a later change adds it
        here "for completeness", keep-first stops firing on cross-tier collisions and
        every cohort count double-counts the overlap. That is the exact defect this
        pin exists to catch, so the assertion is on the key itself, not on a symptom.
        """
        assert ucv.DEDUPE_KEY == ("stamp_date", "ticker", "board_definition")
        assert "tier" not in ucv.DEDUPE_KEY


# --------------------------------------------------------------------------- #
# 3. the floor is applied exactly as printed
# --------------------------------------------------------------------------- #

class TestLiquidityFloorAttribution:
    """Regression: a floor whose effect is not printed is a hidden universe change."""

    #: One census covering every exclusion path plus three keepers. Two names fail
    #: TWO conditions each, so evaluation-order attribution is observable in the
    #: histogram rather than only in the docstring.
    @staticmethod
    def _mixed_census() -> pd.DataFrame:
        return _census([
            _row("KEEP1", bars=400, last_close=50.0, mdv20=25e6),
            _row("KEEP2", bars=250, last_close=12.0, mdv20=8e6),
            _row("KEEP3", bars=900, last_close=4.0, mdv20=6e6),
            _row("DELISTED", last=STALE),
            _row("YOUNG", bars=30),
            _row("PENNY", last_close=1.25),
            _row("ILLIQUID", mdv20=250_000.0),
            # fails not_trading AND thin_history — must be counted ONCE, as the first
            _row("STALE_AND_THIN", bars=30, last=STALE),
            # fails price AND liquidity — must be counted ONCE, as the first
            _row("PENNY_AND_ILLIQUID", last_close=0.50, mdv20=100.0),
            # unmeasurable legs: a null close / a name with < MDV_WINDOW dollar bars
            _row("NO_CLOSE", last_close=None),
            _row("NO_MDV", mdv20=None),
        ])

    def test_every_excluded_name_lands_in_its_own_reason_bucket(self):
        kept, disclosure = usu.apply_floor(self._mixed_census())
        assert kept == ["KEEP1", "KEEP2", "KEEP3"]
        assert disclosure["excluded_by_reason"] == {
            usu.EXC_NOT_TRADING: 2,          # DELISTED + STALE_AND_THIN
            usu.EXC_THIN_HISTORY: 1,         # YOUNG only
            usu.EXC_PRICE_FLOOR: 3,          # PENNY + PENNY_AND_ILLIQUID + NO_CLOSE
            usu.EXC_LIQUIDITY_FLOOR: 2,      # ILLIQUID + NO_MDV
        }

    def test_a_name_failing_two_conditions_is_counted_under_the_first(self):
        """The counts above are the proof, so state the inverse explicitly.

        STALE_AND_THIN is both stale and short; THIN_HISTORY must stay at 1 (YOUNG
        alone). PENNY_AND_ILLIQUID is both sub-$3 and illiquid; LIQUIDITY_FLOOR must
        stay at 2 (ILLIQUID + NO_MDV). If attribution ever stopped short-circuiting,
        these two buckets inflate and the reasons stop summing to the store total.
        """
        _kept, disclosure = usu.apply_floor(self._mixed_census())
        reasons = disclosure["excluded_by_reason"]
        assert reasons[usu.EXC_THIN_HISTORY] == 1
        assert reasons[usu.EXC_LIQUIDITY_FLOOR] == 2

    def test_no_name_is_lost_between_kept_and_excluded(self):
        kept, disclosure = usu.apply_floor(self._mixed_census())
        assert disclosure["store_n"] == 11
        assert disclosure["kept_n"] == len(kept) == 3
        assert disclosure["excluded_n"] == 8
        assert disclosure["kept_n"] + disclosure["excluded_n"] == disclosure["store_n"]
        assert sum(disclosure["excluded_by_reason"].values()) == disclosure["excluded_n"]

    def test_price_through_is_the_tape_not_a_wall_clock(self):
        """The tip is the MODE of the store's last bars — never today's date."""
        _kept, disclosure = usu.apply_floor(self._mixed_census())
        assert disclosure["price_through"] == LAST

    def test_the_printed_rule_names_the_constants_it_applies(self):
        text = usu.floor_rule_text()
        assert f"{MIN_HISTORY} bars" in text
        assert f"${usu.MIN_PRICE_USD:,.0f}" in text          # "$3"
        assert f"${usu.MIN_MDV20_USD / 1e6:,.0f}M" in text   # "$5M"
        assert f"last {usu.MDV_WINDOW} bars" in text
        # the disclosure ships the SAME sentence, not a transcription of it
        _kept, disclosure = usu.apply_floor(self._mixed_census())
        assert disclosure["rule"] == text

    def test_the_printed_rule_cannot_drift_from_the_applied_one(self, monkeypatch):
        """Move the constant; the sentence AND the verdicts must both move.

        This is the pin that makes the disclosure trustworthy: a rule transcribed
        beside the constants (rather than built from them) would keep printing "$5M"
        while silently gating at $20M, and every reader of the artifact would be
        looking at the wrong universe definition.
        """
        assert "$5M" in usu.floor_rule_text()
        kept_before, before = usu.apply_floor(self._mixed_census())
        assert kept_before == ["KEEP1", "KEEP2", "KEEP3"]

        monkeypatch.setattr(usu, "MIN_MDV20_USD", 20_000_000.0)

        text = usu.floor_rule_text()
        assert "$20M" in text and "$5M" not in text
        kept_after, after = usu.apply_floor(self._mixed_census())
        assert after["rule"] == text
        assert after["min_mdv20_usd"] == 20_000_000.0
        # KEEP2 ($8M) and KEEP3 ($6M) now fail the raised floor — the APPLIED rule
        # moved with the printed one, which is the whole assertion.
        assert kept_after == ["KEEP1"]
        assert after["excluded_by_reason"][usu.EXC_LIQUIDITY_FLOOR] == \
            before["excluded_by_reason"][usu.EXC_LIQUIDITY_FLOOR] + 2


# --------------------------------------------------------------------------- #
# 4. boundary values — the floor is inclusive, and one tick below is out
# --------------------------------------------------------------------------- #

class TestFloorBoundaries:
    """Regression: a ``>`` written where the rule says ``>=`` silently shrinks the
    universe by exactly the names sitting on the printed threshold."""

    def test_a_name_exactly_on_each_threshold_is_kept(self):
        kept, _ = usu.apply_floor(_census([
            _row("AT_PRICE", last_close=usu.MIN_PRICE_USD),
            _row("AT_MDV", mdv20=usu.MIN_MDV20_USD),
            _row("AT_BARS", bars=MIN_HISTORY),
        ]))
        assert kept == ["AT_BARS", "AT_MDV", "AT_PRICE"]

    def test_one_tick_below_each_threshold_is_excluded(self):
        kept, disclosure = usu.apply_floor(_census([
            _row("KEEPER"),                                        # majority -> the tip
            _row("KEEPER2"),
            _row("UNDER_PRICE", last_close=usu.MIN_PRICE_USD - 0.01),
            _row("UNDER_MDV", mdv20=usu.MIN_MDV20_USD - 1.0),
            _row("UNDER_BARS", bars=MIN_HISTORY - 1),
        ]))
        assert kept == ["KEEPER", "KEEPER2"]
        assert disclosure["excluded_by_reason"] == {
            usu.EXC_PRICE_FLOOR: 1,
            usu.EXC_LIQUIDITY_FLOOR: 1,
            usu.EXC_THIN_HISTORY: 1,
        }


# --------------------------------------------------------------------------- #
# 5. mdv20 is the MEDIAN, not the mean
# --------------------------------------------------------------------------- #

class TestMedianDollarVolume:

    def test_one_halt_and_dump_session_cannot_buy_a_name_into_the_universe(
        self, tmp_path
    ):
        """Regression: ``.mean()`` written where the rule says ``median``.

        SPIKE trades $100k a day and prints ONE $200M session inside the 20-bar
        window — the exact shape of a halt-and-dump. Its MEAN dollar volume clears
        the $5M floor comfortably; its median does not. A mean would admit it, and
        the tier would then be reporting "runners" off tape nobody can trade.
        """
        bars = 220
        thin_vol = [10_000] * bars
        thin_vol[-5] = 20_000_000                      # the single spike session
        _write_store_bars(tmp_path, "SPIKE", [10.0] * bars, thin_vol)
        _flat_name(tmp_path, "STEADY")                 # honest $10M/day control

        frame = usu.census(tmp_path).set_index("ticker")
        # the mean the code must NOT be using — asserted, not assumed
        spike_dollars = pd.Series([10.0 * v for v in thin_vol[-usu.MDV_WINDOW:]])
        assert spike_dollars.mean() > usu.MIN_MDV20_USD
        assert spike_dollars.median() < usu.MIN_MDV20_USD
        assert frame.loc["SPIKE"]["mdv20"] == spike_dollars.median() == 100_000.0
        assert frame.loc["STEADY"]["mdv20"] == 10_000_000.0

        kept, disclosure = usu.apply_floor(usu.census(tmp_path))
        assert kept == ["STEADY"]
        assert disclosure["excluded_by_reason"] == {usu.EXC_LIQUIDITY_FLOOR: 1}

    def test_a_name_with_fewer_than_the_window_of_bars_has_a_null_mdv(self, tmp_path):
        """Below MDV_WINDOW there is nothing to take a median OF — null, not a
        partial-window number dressed up as one."""
        short = usu.MDV_WINDOW - 1
        _write_store_bars(tmp_path, "TINY", [10.0] * short, [1_000_000] * short)
        row = usu.census(tmp_path).set_index("ticker").loc["TINY"]
        assert row["mdv20"] is None or pd.isna(row["mdv20"])


# --------------------------------------------------------------------------- #
# 6. the two tiers are disjoint BY CONSTRUCTION
# --------------------------------------------------------------------------- #

class TestDisjointTiers:

    def test_resolve_never_returns_a_curated_name_and_prints_the_subtraction(
        self, tmp_path
    ):
        """Regression: a curated name leaking into the scan set.

        It would be stamped twice (keep-first hides one silently) and counted as an
        "off-index runner" the curated frame never saw — when in fact it was in the
        frame all along. ``curated_overlap_n`` is what makes the subtraction a
        printed number instead of an invisible one, so the accounting identity is
        pinned alongside the membership check.
        """
        for ticker in ("CURA", "CURB", "SCNA", "SCNB"):
            _flat_name(tmp_path, ticker)

        scan, disclosure = usu.resolve(tmp_path, curated={"CURA", "CURB", "GHOST"})
        assert scan == ["SCNA", "SCNB"]
        assert not {"CURA", "CURB"} & set(scan)
        assert disclosure["kept_n"] == 4
        assert disclosure["curated_n"] == 3            # GHOST is not in the store
        assert disclosure["curated_overlap_n"] == 2
        assert disclosure["scan_n"] == 2
        assert disclosure["scan_n"] + disclosure["curated_overlap_n"] == \
            disclosure["kept_n"]

    def test_no_curated_set_subtracts_nothing(self, tmp_path):
        for ticker in ("SCNA", "SCNB"):
            _flat_name(tmp_path, ticker)
        scan, disclosure = usu.resolve(tmp_path)
        assert scan == ["SCNA", "SCNB"]
        assert disclosure["curated_overlap_n"] == 0
        assert disclosure["scan_n"] == disclosure["kept_n"] == 2


# --------------------------------------------------------------------------- #
# 7. an unrestored store is a DISCLOSED NULL, never an empty result
# --------------------------------------------------------------------------- #

class TestStoreAbsentIsADisclosedNull:
    """Regression: the lane runs without the 617 MB store restored.

    Every path must say "not measured". An empty runner list with ``available``
    unset reads as "no off-index runners tonight" — a confident finding built out of
    a missing input (#4485 null-is-not-false).
    """

    @staticmethod
    def _sidecars_only(tmp_path: Path) -> Path:
        """The real checkout shape: the directory EXISTS, carrying only JSON sidecars."""
        store = tmp_path / usu.STORE_REL
        store.mkdir(parents=True, exist_ok=True)
        (store / usu.MANIFEST_NAME).write_text(
            json.dumps({"n_tickers": 20476, "latest_date": LAST}), encoding="utf-8")
        return tmp_path

    def test_store_available_is_false_for_a_sidecar_only_checkout(self, tmp_path):
        assert usu.store_available(tmp_path) is False           # no directory at all
        root = self._sidecars_only(tmp_path)
        assert usu.store_available(root) is False, \
            "a directory holding only sidecars is NOT a restored store"
        _flat_name(root, "REAL")
        assert usu.store_available(root) is True

    def test_apply_floor_on_an_empty_census_names_the_null(self, tmp_path):
        root = self._sidecars_only(tmp_path)
        kept, disclosure = usu.apply_floor(usu.census(root))
        assert kept == []
        assert disclosure["null_reason"]
        assert usu.STORE_REL in disclosure["null_reason"]
        assert disclosure["store_n"] == 0
        assert disclosure["price_through"] is None
        # the rule is present even though nothing ran against it
        assert disclosure["rule"] == usu.floor_rule_text()

    def test_scan_tier_audit_is_a_null_carrying_the_rule_that_did_not_run(
        self, tmp_path
    ):
        root = self._sidecars_only(tmp_path)
        doc = PMA.build_scan_tier_audit(root)
        assert doc["available"] is False
        assert doc["null_reason"] and usu.STORE_REL in doc["null_reason"]
        assert doc["runners"] == []
        assert doc["summary"] == {}
        # A reader must be able to see WHICH rule was not applied; without this the
        # null is unactionable ("something did not run") rather than a measurement gap.
        assert doc["floor"]["rule"] == usu.floor_rule_text()
        assert doc["schema"] == PMA.SCAN_SCHEMA
        assert doc["tier"] == "ops_telemetry"
        assert doc["authority"].startswith("none")
        json.dumps(doc)          # the artifact must still serialise

    def test_the_null_document_survives_a_missing_directory_too(self, tmp_path):
        doc = PMA.build_scan_tier_audit(tmp_path)
        assert doc["available"] is False and doc["runners"] == []
        assert doc["floor"]["rule"]


# --------------------------------------------------------------------------- #
# 8. the miss-audit keys stay ADDITIVE
# --------------------------------------------------------------------------- #

#: The six documented forward-log fields. ``scan_tier_asof`` rides with the figures
#: because the block is MIRRORED from a lane that runs later — without it, a series
#: plotted from this log silently mixes same-night and previous-night values.
_SCAN_ROW_KEYS = {
    "scan_tier_available", "scan_tier_asof", "scan_tier_scan_n",
    "scan_tier_runners_n", "scan_tier_runners_eligible_today_n",
    "scan_tier_runners_never_eligible_n",
}


class TestMissAuditKeysAreAdditive:

    def test_absent_scan_artifact_is_a_named_null_and_a_degraded_row(self, tmp_path):
        """Regression: the W0 document swallowing the scan lane's absence.

        W0 MIRRORS an artifact a later lane writes. On a night the scan lane never
        ran, the mirror must say so and name the path — otherwise W0 ships a
        scan-tier block full of nulls that reads as "measured, nothing there".
        """
        degraded: list[dict] = []
        cov = PMA.scan_tier_coverage(tmp_path, degraded)
        assert cov["available"] is False
        assert cov["null_reason"] and PMA.SCAN_ARTIFACT_REL in cov["null_reason"]
        assert cov["asof"] is None
        named = [d for d in degraded if d["input"] == PMA.SCAN_ARTIFACT_REL]
        assert named, "a null must be disclosed against the input that produced it"
        assert named[0]["reason"] and named[0]["severity"] == "structural"

    def test_coverage_mirrors_the_artifact_and_never_recomputes_it(self, tmp_path):
        """The mirror is a READ. Its asof is the artifact's own price_through, which
        may legitimately trail W0's — pinned so the two dates can never be conflated."""
        artifact = tmp_path / PMA.SCAN_ARTIFACT_REL
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({
            "schema": PMA.SCAN_SCHEMA, "available": True, "null_reason": None,
            "price_through": "2026-08-02",
            "floor": {"rule": usu.floor_rule_text()},
            "summary": {"store_n": 20476, "scan_n": 2515, "runners_n": 150,
                        "runners_eligible_today_n": 12,
                        "runners_never_eligible_n": 61},
            "excluder_family_hist": {"not_topped_veto": 90},
        }), encoding="utf-8")

        degraded: list[dict] = []
        cov = PMA.scan_tier_coverage(tmp_path, degraded)
        assert degraded == [], "a readable artifact is not a degradation"
        assert cov["available"] is True
        assert cov["asof"] == "2026-08-02"
        assert cov["scan_n"] == 2515 and cov["runners_n"] == 150
        assert cov["floor_rule"] == usu.floor_rule_text()
        assert cov["excluder_family_hist"] == {"not_topped_veto": 90}

    def test_row_fields_are_exactly_the_six_documented_keys(self):
        """Regression: a renamed or dropped key silently ends the forward SERIES.

        These names are the columns a reader plots out of the JSONL; a rename does not
        error, it just starts a second, unjoinable column beside the old one.
        """
        row = PMA.scan_tier_row_fields({})
        assert set(row) == _SCAN_ROW_KEYS
        assert all(k.startswith("scan_tier_") for k in row), \
            "the block must stay in its own namespace — additive, never a collision"

    def test_row_fields_are_null_safe_on_a_doc_with_no_block(self):
        """The forward log must never be the thing that takes the nightly down."""
        row = PMA.scan_tier_row_fields({})
        assert row["scan_tier_available"] is False
        assert all(row[k] is None for k in _SCAN_ROW_KEYS - {"scan_tier_available"})
        json.dumps(row)          # still one JSONL line

        # a doc whose block is itself the disclosed null
        row = PMA.scan_tier_row_fields(
            {"scan_tier": {"available": False, "asof": None,
                           "null_reason": "artifact absent"}})
        assert row["scan_tier_available"] is False
        assert row["scan_tier_scan_n"] is None

    def test_row_fields_carry_the_mirrored_figures_when_present(self):
        block = {"available": True, "asof": "2026-08-02", "scan_n": 2515,
                 "runners_n": 150, "runners_eligible_today_n": 12,
                 "runners_never_eligible_n": 61}
        row = PMA.scan_tier_row_fields({"scan_tier": block})
        assert row["scan_tier_available"] is True
        assert row["scan_tier_asof"] == "2026-08-02"
        assert row["scan_tier_scan_n"] == 2515
        assert row["scan_tier_runners_never_eligible_n"] == 61


# --------------------------------------------------------------------------- #
# 9. forward-log idempotency
# --------------------------------------------------------------------------- #

def _scan_doc(price_through: str = "2026-08-03") -> dict:
    return {
        "schema": PMA.SCAN_SCHEMA,
        "available": True,
        "null_reason": None,
        "price_through": price_through,
        "floor": {"rule": usu.floor_rule_text()},
        "summary": {"store_n": 20476, "floored_n": 3980, "curated_overlap_n": 1465,
                    "scan_n": 2515, "panel_n": 2500, "runners_n": 150,
                    "runners_eligible_today_n": 12, "runners_never_eligible_n": 61,
                    "runners_never_eligible_pct": 0.4067},
        "excluder_family_hist": {"not_topped_veto": 90, "ELIGIBLE": 12},
        "degraded": [],
    }


class TestForwardLogIdempotency:

    def test_a_same_night_rerun_appends_nothing(self, tmp_path):
        """Regression: a re-run double-counting the night.

        The scan lane can legitimately be re-run (a timeout, a manual heal). The log
        is keyed on ``price_through``, so a second run over the same tape must be a
        no-op — otherwise every series computed off this file is weighted by how many
        times each night happened to be re-run.
        """
        log = tmp_path / "forward_log.jsonl"
        assert SCAN._append_scan_log(_scan_doc(), log) is True
        assert SCAN._append_scan_log(_scan_doc(), log) is False
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        assert len(rows) == 1
        assert rows[0]["price_through"] == "2026-08-03"
        assert rows[0]["scan_n"] == 2515 and rows[0]["runners_n"] == 150
        assert rows[0]["excluder_family_hist"] == {"not_topped_veto": 90, "ELIGIBLE": 12}
        assert rows[0]["degraded_n"] == 0

    def test_a_new_tape_date_does_advance(self, tmp_path):
        log = tmp_path / "forward_log.jsonl"
        assert SCAN._append_scan_log(_scan_doc("2026-08-03"), log) is True
        assert SCAN._append_scan_log(_scan_doc("2026-08-04"), log) is True
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        assert [r["price_through"] for r in rows] == ["2026-08-03", "2026-08-04"]

    def test_a_corrupt_line_does_not_blind_the_idempotency_check(self, tmp_path):
        """A half-written line must not make the guard forget the night it holds."""
        log = tmp_path / "forward_log.jsonl"
        SCAN._append_scan_log(_scan_doc(), log)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        assert SCAN._append_scan_log(_scan_doc(), log) is False


# --------------------------------------------------------------------------- #
# 10. shallow-cache heal — prepend only, schema preserved, idempotent
# --------------------------------------------------------------------------- #

_DONOR_BARS = 500
_TARGET_BARS = 20


def _heal_world(tmp_path: Path) -> dict:
    """A shallow ``data/yahoo`` target over a deep ``data/baskets/ohlcv`` donor.

    The donor deliberately COVERS the target's own 20 dates with DIFFERENT values, so
    "prepend only, never overwrite" is observable: if the splice ever reached behind
    the target's first date, the surviving tail would carry donor numbers.
    """
    idx = pd.bdate_range("2024-01-01", periods=_DONOR_BARS, name="date")
    donor = pd.DataFrame({
        "open": [9.0 + i * 0.1 for i in range(_DONOR_BARS)],
        "high": [11.0 + i * 0.1 for i in range(_DONOR_BARS)],
        "low": [8.0 + i * 0.1 for i in range(_DONOR_BARS)],
        "close": [10.0 + i * 0.1 for i in range(_DONOR_BARS)],
        "volume": [1_000 + i for i in range(_DONOR_BARS)],
    }, index=idx)
    tail = idx[-_TARGET_BARS:]
    target = pd.DataFrame({
        "close_price": [900.0 + j for j in range(_TARGET_BARS)],
        "close": [900.0 + j for j in range(_TARGET_BARS)],
        "volume": [5_000 + j for j in range(_TARGET_BARS)],
    }, index=tail)

    (tmp_path / "data" / "baskets" / "ohlcv").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "yahoo").mkdir(parents=True, exist_ok=True)
    donor.to_parquet(tmp_path / "data" / "baskets" / "ohlcv" / "FOO.parquet")
    target.to_parquet(tmp_path / "data" / "yahoo" / "FOO.parquet")
    return {"donor": donor, "path": tmp_path / "data" / "yahoo" / "FOO.parquet"}


class TestShallowCacheHeal:

    def test_the_shallow_target_is_found_below_the_depth_floor(self, tmp_path):
        _heal_world(tmp_path)
        found = HEAL.shallow_targets(tmp_path)
        assert ("data/yahoo", "FOO", _TARGET_BARS) in found
        assert HEAL.DEPTH_FLOOR == MIN_HISTORY, \
            "the floor is confluence's own MIN_HISTORY, never a second constant"

    def test_plan_prepends_only_rows_strictly_before_the_target_start(self, tmp_path):
        """Regression: an inclusive boundary would overwrite the target's own first
        bar with donor tape — the no-overwrite-gate law, one row wide."""
        world = _heal_world(tmp_path)
        plan = HEAL.plan_heal(tmp_path, "FOO", "data/yahoo")
        assert plan is not None
        first = world["donor"].index[-_TARGET_BARS]
        assert plan["donor"] == "data/baskets/ohlcv"
        assert plan["target_bars"] == _TARGET_BARS
        assert plan["prepend_bars"] == _DONOR_BARS - _TARGET_BARS
        assert plan["result_bars"] == _DONOR_BARS
        assert plan["target_first"] == str(first)[:10]
        assert plan["_head"].index.max() < first, "the splice reached the target's own rows"

    def test_apply_leaves_every_original_row_byte_identical(self, tmp_path):
        world = _heal_world(tmp_path)
        before = pd.read_parquet(world["path"])
        plan = HEAL.plan_heal(tmp_path, "FOO", "data/yahoo")
        assert HEAL.apply_heal(plan) == _DONOR_BARS

        healed = pd.read_parquet(world["path"])
        assert len(healed) == _DONOR_BARS
        assert_frame_equal(healed.tail(_TARGET_BARS), before)

    def test_the_targets_column_set_is_preserved_exactly(self, tmp_path):
        """Regression: donor columns leaking into a schema other readers parse.

        ``data/baskets/ohlcv`` carries open/high/low; adding them here would change a
        cache's shape without any consumer asking for it.
        """
        world = _heal_world(tmp_path)
        before = pd.read_parquet(world["path"])
        HEAL.apply_heal(HEAL.plan_heal(tmp_path, "FOO", "data/yahoo"))
        healed = pd.read_parquet(world["path"])
        assert list(healed.columns) == list(before.columns) == \
            ["close_price", "close", "volume"]
        assert not {"open", "high", "low"} & set(healed.columns)

    def test_close_price_is_filled_through_the_declared_alias(self, tmp_path):
        """``data/yahoo`` carries close_price, donors do not — the alias is the ONLY
        reason this donor qualifies at all, so pin both the mapping and the values."""
        world = _heal_world(tmp_path)
        assert HEAL.COLUMN_ALIASES == {"close_price": "close"}
        HEAL.apply_heal(HEAL.plan_heal(tmp_path, "FOO", "data/yahoo"))
        healed = pd.read_parquet(world["path"])

        n = _DONOR_BARS - _TARGET_BARS
        # check_freq: the in-memory donor index carries a BusinessDay freq that a
        # parquet round-trip drops. The VALUES and the dates are what is under test.
        donor_close = world["donor"]["close"].iloc[:n]
        assert_series_equal(healed["close_price"].iloc[:n], donor_close,
                            check_names=False, check_freq=False)
        assert_series_equal(healed["close"].iloc[:n], donor_close,
                            check_names=False, check_freq=False)

    def test_a_second_heal_is_a_no_op(self, tmp_path):
        """Idempotent BY CONSTRUCTION: the healed file is at the depth floor, so the
        next night's sweep does not see it at all — and even a forced re-plan finds
        nothing earlier to add."""
        _heal_world(tmp_path)
        HEAL.apply_heal(HEAL.plan_heal(tmp_path, "FOO", "data/yahoo"))
        assert "FOO" not in {t for _d, t, _b in HEAL.shallow_targets(tmp_path)}
        assert HEAL.plan_heal(tmp_path, "FOO", "data/yahoo") is None

    def test_a_donor_that_cannot_source_a_column_is_skipped_not_half_written(
        self, tmp_path
    ):
        """Regression: a partial splice leaving NaN holes in a column a reader parses
        as complete. ``adj_close`` has no donor source and no alias, so the ONLY
        correct outcome is to leave the file alone."""
        _heal_world(tmp_path)
        idx = pd.bdate_range("2024-01-01", periods=_DONOR_BARS, name="date")
        pd.DataFrame({
            "open": [9.0] * _DONOR_BARS, "high": [11.0] * _DONOR_BARS,
            "low": [8.0] * _DONOR_BARS, "close": [10.0] * _DONOR_BARS,
            "volume": [1_000] * _DONOR_BARS,
        }, index=idx).to_parquet(tmp_path / "data" / "baskets" / "ohlcv" / "BAR.parquet")
        tail = idx[-_TARGET_BARS:]
        bar_path = tmp_path / "data" / "yahoo" / "BAR.parquet"
        pd.DataFrame({
            "close": [900.0] * _TARGET_BARS,
            "volume": [5_000] * _TARGET_BARS,
            "adj_close": [899.0] * _TARGET_BARS,     # no donor column, no alias
        }, index=tail).to_parquet(bar_path)

        digest = hashlib.sha256(bar_path.read_bytes()).hexdigest()
        assert HEAL.plan_heal(tmp_path, "BAR", "data/yahoo") is None
        assert hashlib.sha256(bar_path.read_bytes()).hexdigest() == digest, \
            "an unhealable target must not be touched at all"
        # and it stays on the shallow list — unhealable is not the same as healed
        assert "BAR" in {t for _d, t, _b in HEAL.shallow_targets(tmp_path)}


# --------------------------------------------------------------------------- #
# 11. the scan stamp obeys the nightly-is-the-sole-advancer law
# --------------------------------------------------------------------------- #

class TestScanStampNightlyGate:
    """The scan lane is a SECOND writer into the forward store — the gate has to hold
    for it exactly as it does for the curated stamp, or an intraday/render lane can
    advance a ledger whose ``data/`` writes are discarded anyway."""

    @pytest.mark.parametrize("lane", [None, "intraday", "render", "weekly"])
    def test_a_non_nightly_lane_stamps_nothing(
        self, lane, append_kwargs, tmp_path, monkeypatch
    ):
        # conftest arms COLLECT_LANE=nightly for EVERY test — remove both names, or
        # this test passes for the wrong reason.
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        if lane is not None:
            monkeypatch.setenv("COLLECT_LANE", lane)

        verdicts = {"SCN1": _verdict(), "SCN2": _verdict(tier="T3")}
        assert ucv.append_candidates(
            verdicts, STAMP, tier=ucv.TIER_SCAN,
            liquidity={"SCN1": {"mdv20_usd": 9e6}}, **append_kwargs) == 0
        assert not ucv._part_path(STAMP, tmp_path).exists()

        # POSITIVE CONTROL, in the same test on purpose: append_candidates returns 0
        # on ANY failure (it swallows exceptions by contract), so a 0 above proves
        # nothing unless the identical call writes when the lane IS nightly.
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert ucv.append_candidates(
            verdicts, STAMP, tier=ucv.TIER_SCAN,
            liquidity={"SCN1": {"mdv20_usd": 9e6}}, **append_kwargs) == 2
        assert ucv._part_path(STAMP, tmp_path).exists()
        assert set(ucv.load_candidates(tmp_path)["tier"]) == {ucv.TIER_SCAN}
