"""Tests for scripts/backfill_qledger_cn.py and scripts/sample_qledger_placebo.py (W1/B3).

Hermetic: synthetic events.parquet + tmp_path qledger store.
No live data, no network.

Coverage:
  - claim generation counts (pairs → registered, blocked)
  - importance-band tagging (HIGH / LOW split at median)
  - placebo determinism (same asof → same sample)
  - placebo is_placebo=True flag on every registered claim
  - placebo excluded from direction (direction==0 for all claims)
  - multi-ticker events register one claim per ticker
  - missing price → n_blocked incremented
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root on path for direct invocation.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import scripts.backfill_qledger_cn as backfill  # noqa: E402
import scripts.sample_qledger_placebo as placebo  # noqa: E402
from engine import qledger as q  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _write_events(path: Path, rows: list[dict]) -> None:
    """Write a minimal events.parquet from a list of row dicts."""
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _write_price(ticker_path: Path, start: str = "2026-06-01", n: int = 60,
                 start_px: float = 10.0) -> None:
    """Write a tiny price parquet (date index, 'close' column)."""
    idx = pd.bdate_range(start=start, periods=n)
    closes = [start_px * (1.01 ** i) for i in range(n)]
    ticker_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": closes}, index=idx).to_parquet(ticker_path)


@pytest.fixture()
def fake_root(tmp_path: Path, monkeypatch):
    """Build a minimal fake repo root with synthetic events + prices, and point
    qledger at the tmp root so we don't pollute the real ledger."""
    root = tmp_path / "repo"
    root.mkdir()

    # China events — 6 rows: 3 HIGH importance, 3 LOW, 2 with tickers
    cn_events = [
        # HIGH importance (score >= 1.0 = median of these 6 rows)
        {"event_id": "ev1", "first_seen_utc": "2026-06-21T01:00:00+00:00",
         "seendate": "2026-06-21", "title": "Title 1", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
         "source_tier": 1, "baskets": "", "tickers": "000333.SZ",
         "score": 1.5, "sentiment": 0.0, "scheduled_ref": ""},
        {"event_id": "ev2", "first_seen_utc": "2026-06-22T02:00:00+00:00",
         "seendate": "2026-06-22", "title": "Title 2", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "policy",
         "source_tier": 2, "baskets": "", "tickers": "000333.SZ,600519.SS",
         "score": 2.0, "sentiment": 1.0, "scheduled_ref": ""},
        {"event_id": "ev3", "first_seen_utc": "2026-06-23T03:00:00+00:00",
         "seendate": "2026-06-23", "title": "Title 3", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
         "source_tier": 2, "baskets": "", "tickers": "",
         "score": 1.2, "sentiment": 0.0, "scheduled_ref": ""},
        # LOW importance (score < 1.0)
        {"event_id": "ev4", "first_seen_utc": "2026-06-24T01:00:00+00:00",
         "seendate": "2026-06-24", "title": "Title 4", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
         "source_tier": 2, "baskets": "", "tickers": "600519.SS",
         "score": 0.5, "sentiment": 0.0, "scheduled_ref": ""},
        {"event_id": "ev5", "first_seen_utc": "2026-06-25T01:00:00+00:00",
         "seendate": "2026-06-25", "title": "Title 5", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
         "source_tier": 2, "baskets": "", "tickers": "MISSING.SS",
         "score": 0.6, "sentiment": 0.0, "scheduled_ref": ""},
        {"event_id": "ev6", "first_seen_utc": "2026-06-26T01:00:00+00:00",
         "seendate": "2026-06-26", "title": "Title 6", "summary": "",
         "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
         "source_tier": 2, "baskets": "", "tickers": "",
         "score": 0.7, "sentiment": 0.0, "scheduled_ref": ""},
    ]
    _write_events(root / "data" / "china_news_vector" / "events.parquet", cn_events)

    # US events — 4 rows (no score column)
    us_events = [
        {"event_id": "us1", "first_seen_utc": "2026-06-21T01:00:00+00:00",
         "seendate": "2026-06-21", "title": "US T1", "url": "http://y",
         "domain": "y", "theme": "macro", "source_tier": 1},
        {"event_id": "us2", "first_seen_utc": "2026-06-22T01:00:00+00:00",
         "seendate": "2026-06-22", "title": "US T2", "url": "http://y",
         "domain": "y", "theme": "macro", "source_tier": 2},
        {"event_id": "us3", "first_seen_utc": "2026-06-23T01:00:00+00:00",
         "seendate": "2026-06-23", "title": "US T3", "url": "http://y",
         "domain": "y", "theme": "macro", "source_tier": 2},
        {"event_id": "us4", "first_seen_utc": "2026-06-24T01:00:00+00:00",
         "seendate": "2026-06-24", "title": "US T4", "url": "http://y",
         "domain": "y", "theme": "macro", "source_tier": 2},
    ]
    _write_events(root / "data" / "news_vector" / "events.parquet", us_events)

    # Prices: bench + two stocks (000333.SZ and 600519.SS); MISSING.SS intentionally absent
    _write_price(root / "data" / "china" / "510300.SS.parquet")
    _write_price(root / "data" / "china_stocks" / "000333.SZ.parquet")
    _write_price(root / "data" / "china_stocks" / "600519.SS.parquet")

    return root


# --------------------------------------------------------------------------- #
# backfill_qledger_cn tests
# --------------------------------------------------------------------------- #

class TestBackfillCn:
    def test_dry_run_counts(self, fake_root):
        """dry-run: n_tagged=3, pairs=4 (ev1:1, ev2:2, ev4:1), n_blocked=1 (ev5 MISSING),
        n_registered = 4 pairs × 2 horizons = 8 (ev5 MISSING → 1 blocked, 1×2=2 not registered)."""
        result = backfill.run(fake_root, dry_run=True)
        assert result["n_events"] == 6
        # tagged = rows where tickers != "" = ev1, ev2, ev4, ev5 = 4
        assert result["n_tagged"] == 4
        # pairs = ev1(1) + ev2(2) + ev4(1) + ev5(1) = 5
        assert result["n_pairs"] == 5
        # blocked = ev5 (MISSING.SS not in china_stocks)
        assert result["n_blocked"] == 1
        # registered (dry) = (5 - 1) pairs * 2 horizons = 8
        assert result["n_registered"] == 8
        assert result["n_rejected"] == 0

    def test_writes_to_ledger(self, fake_root):
        """Non-dry-run: claims land in data/qledger/claims.jsonl."""
        backfill.run(fake_root, dry_run=False)
        claims_path = fake_root / "data" / "qledger" / "claims.jsonl"
        assert claims_path.exists()
        claims = q.load_claims(fake_root)
        # 4 pairs * 2 horizons = 8 claims
        assert len(claims) == 8

    def test_idempotent(self, fake_root):
        """Running twice does not duplicate claims."""
        backfill.run(fake_root)
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert len(claims) == 8

    def test_importance_band_tagging(self, fake_root):
        """HIGH band for score >= median (1.0), LOW for below."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        # All claims from ev1 (score=1.5>=1.0) should be HIGH
        ev1_claims = [c for c in claims if c.get("event_id") == "ev1"]
        assert ev1_claims, "No claims for ev1"
        assert all(c.get("importance_band") == "HIGH" for c in ev1_claims)
        # ev4 (score=0.5<1.0) should be LOW
        ev4_claims = [c for c in claims if c.get("event_id") == "ev4"]
        assert ev4_claims, "No claims for ev4"
        assert all(c.get("importance_band") == "LOW" for c in ev4_claims)

    def test_direction_is_zero(self, fake_root):
        """All claims have direction=0 (salience-only, D5)."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert all(c.get("direction") == 0 for c in claims)

    def test_bench_is_csi300(self, fake_root):
        """All CN event claims use 510300.SS as bench."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert all(c.get("bench") == "510300.SS" for c in claims)

    def test_both_horizons_registered(self, fake_root):
        """Each (event,ticker) pair gets one claim per horizon (5 and 21)."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        # ev1 → ticker 000333.SZ, 2 horizons
        ev1_claims = [c for c in claims if c.get("event_id") == "ev1"]
        horizons = sorted(c["horizon_d"] for c in ev1_claims)
        assert horizons == [5, 21]

    def test_multiticker_event(self, fake_root):
        """ev2 has two tickers → 4 claims (2 tickers × 2 horizons)."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        ev2_claims = [c for c in claims if c.get("event_id") == "ev2"]
        assert len(ev2_claims) == 4
        scopes = {c["scope"]["key"] for c in ev2_claims}
        assert scopes == {"000333.SZ", "600519.SS"}

    def test_status_open(self, fake_root):
        """Registered claims have status=open (not rejected)."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        rejected = [c for c in claims if c.get("status") == "rejected"]
        assert rejected == [], f"Unexpected rejections: {rejected}"

    def test_blocked_ticker_excluded(self, fake_root):
        """ev5's MISSING.SS ticker produces n_blocked but no claim."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        missing_claims = [c for c in claims if c.get("scope", {}).get("key") == "MISSING.SS"]
        assert missing_claims == []

    def test_timestamp_quality(self, fake_root):
        """All claims use CRAWL_BOUNDED timestamp_quality."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert all(c.get("timestamp_quality") == "CRAWL_BOUNDED" for c in claims)

    def test_event_id_in_extra(self, fake_root):
        """event_id is stored on each claim for traceability."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert all("event_id" in c for c in claims)

    def test_importance_score_in_extra(self, fake_root):
        """importance_score is stored on each claim."""
        backfill.run(fake_root)
        claims = q.load_claims(fake_root)
        assert all("importance_score" in c for c in claims)


# --------------------------------------------------------------------------- #
# sample_qledger_placebo tests
# --------------------------------------------------------------------------- #

class TestPlaceboSampler:
    def test_dry_run_samples_k(self, fake_root):
        """Samples up to K events split across CN and US corpora."""
        result = placebo.run(fake_root, asof="2026-07-02", k=6, dry_run=True)
        assert result["n_sampled"] == 6
        # Each sampled event with tickers registers 2 horizons; no-ticker registers 2 horizons too
        assert result["n_registered"] > 0

    def test_deterministic_across_runs(self, fake_root):
        """Same asof → identical n_registered (deterministic RNG seed)."""
        r1 = placebo.run(fake_root, asof="2026-07-02", k=6, dry_run=True)
        r2 = placebo.run(fake_root, asof="2026-07-02", k=6, dry_run=True)
        assert r1["n_registered"] == r2["n_registered"]
        assert r1["n_sampled"] == r2["n_sampled"]

    def test_different_asof_different_sample(self, fake_root):
        """Different asof dates produce different RNG seeds (determinism check)."""
        seed1 = placebo._asof_seed("2026-07-02")
        seed2 = placebo._asof_seed("2026-07-03")
        assert seed1 != seed2

    def test_writes_placebo_claims(self, fake_root):
        """Placebo claims are persisted with is_placebo=True."""
        placebo.run(fake_root, asof="2026-07-02", k=4)
        claims = q.load_claims(fake_root)
        placebo_claims = [c for c in claims if c.get("is_placebo") is True]
        assert placebo_claims, "No placebo claims written"

    def test_all_placebo_direction_zero(self, fake_root):
        """All placebo claims have direction=0 (salience-only)."""
        placebo.run(fake_root, asof="2026-07-02", k=4)
        claims = q.load_claims(fake_root)
        placebo_claims = [c for c in claims if c.get("is_placebo") is True]
        assert all(c.get("direction") == 0 for c in placebo_claims)

    def test_cn_placebo_uses_csi300_bench(self, fake_root):
        """CN placebo claims use 510300.SS as bench."""
        placebo.run(fake_root, asof="2026-07-02", k=4)
        claims = q.load_claims(fake_root)
        cn_placebo = [c for c in claims
                      if c.get("is_placebo") and c.get("corpus") == "cn"]
        if cn_placebo:
            assert all(c["bench"] == "510300.SS" for c in cn_placebo)

    def test_us_placebo_uses_spy_bench(self, fake_root):
        """US placebo claims use SPY as bench."""
        placebo.run(fake_root, asof="2026-07-02", k=6)
        claims = q.load_claims(fake_root)
        us_placebo = [c for c in claims
                      if c.get("is_placebo") and c.get("corpus") == "us"]
        if us_placebo:
            assert all(c["bench"] == "SPY" for c in us_placebo)

    def test_sampled_on_recorded(self, fake_root):
        """sampled_on field records the run's asof date."""
        asof = "2026-07-02"
        placebo.run(fake_root, asof=asof, k=4)
        claims = q.load_claims(fake_root)
        placebo_claims = [c for c in claims if c.get("is_placebo")]
        assert all(c.get("sampled_on") == asof for c in placebo_claims)

    def test_placebo_idempotent(self, fake_root):
        """Running placebo sampler twice for same asof does not duplicate claims."""
        placebo.run(fake_root, asof="2026-07-02", k=4)
        n_first = len(q.load_claims(fake_root))
        placebo.run(fake_root, asof="2026-07-02", k=4)
        n_second = len(q.load_claims(fake_root))
        assert n_first == n_second

    def test_placebo_low_importance_only(self, fake_root):
        """CN placebo only samples from events with score < median."""
        # With our 6-event fixture, median = 1.0; LOW = ev4(0.5), ev5(0.6), ev6(0.7)
        # All CN placebo claims must have importance_score < 1.0
        placebo.run(fake_root, asof="2026-07-02", k=4)
        claims = q.load_claims(fake_root)
        cn_placebo = [c for c in claims
                      if c.get("is_placebo") and c.get("corpus") == "cn"]
        for c in cn_placebo:
            score = c.get("importance_score", 0.0)
            assert score < 1.0, f"CN placebo claim has HIGH-importance score {score}: {c}"

    def test_cn_low_corpus_size(self, fake_root):
        """CN low-importance pool has expected size (score < median)."""
        df = pd.read_parquet(fake_root / "data" / "china_news_vector" / "events.parquet")
        threshold = float(df["score"].median())
        low_cn = df[df["score"] < threshold]
        assert len(low_cn) == 3  # ev4, ev5, ev6

    # ---------------------------------------------------------------------- #
    # W1 placebo-strength tests (D3 bias correction)
    # ---------------------------------------------------------------------- #

    def test_covered_ticker_preference(self, fake_root):
        """Sampler biases toward LOW events with covered tickers before falling back.

        Fixture LOW events:
          ev4 (score=0.5): ticker=600519.SS → has price → covered
          ev5 (score=0.6): ticker=MISSING.SS → no price → uncovered
          ev6 (score=0.7): no tickers at all → uncovered

        With k_cn=3 we can fill all 3 from the LOW pool (1 covered, 2 uncovered).
        The covered event (ev4) MUST appear in the CN sample.
        We verify by checking that at least one CN placebo entity claim has
        scope.key == '600519.SS' (ev4's ticker).
        """
        # k=6 → k_cn=3, k_us=3; CN low pool = ev4(covered), ev5(uncovered), ev6(uncovered)
        placebo.run(fake_root, asof="2026-07-02", k=6)
        claims = q.load_claims(fake_root)
        cn_placebo = [c for c in claims if c.get("is_placebo") and c.get("corpus") == "cn"]
        # 600519.SS (ev4's covered ticker) should appear as an entity claim
        entity_keys = {c["scope"]["key"] for c in cn_placebo if c["scope"]["type"] == "entity"}
        assert "600519.SS" in entity_keys, (
            f"Expected covered ticker 600519.SS in CN placebo entity claims; got {entity_keys}"
        )

    def test_fallback_accounting(self, fake_root):
        """n_fallback counts events that landed on the no-covered-ticker path."""
        # k=6 → k_cn=3: 1 covered (ev4), 2 uncovered (ev5, ev6) → n_cn_fallback=2
        # k_us=3: US events have no tickers at all → all 3 are fallback → n_us_fallback=3
        # total n_fallback = 5
        result = placebo.run(fake_root, asof="2026-07-02", k=6, dry_run=True)
        assert "n_fallback" in result, "n_fallback key missing from run() summary"
        # CN: 2 fallback (ev5+ev6); US: 3 fallback (no tickers in fixture)
        assert result["n_fallback"] == 5, (
            f"Expected n_fallback=5, got {result['n_fallback']}"
        )

    def test_fallback_accounting_all_covered(self, fake_root):
        """When covered pool satisfies demand fully, n_fallback == 0.

        Extend fixture with a new events file that has only covered tickers.
        """
        # Write a fresh CN events parquet with only covered low-importance events
        all_covered_events = [
            {"event_id": f"cov{i}", "first_seen_utc": "2026-06-21T01:00:00+00:00",
             "seendate": "2026-06-21", "title": f"T{i}", "summary": "",
             "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
             "source_tier": 2, "baskets": "", "tickers": "600519.SS",
             "score": 0.1 * i, "sentiment": 0.0, "scheduled_ref": ""}
            for i in range(1, 11)  # 10 low events all with covered ticker
        ]
        # Add 2 HIGH events to set median above 0
        all_covered_events += [
            {"event_id": "high1", "first_seen_utc": "2026-06-22T01:00:00+00:00",
             "seendate": "2026-06-22", "title": "High1", "summary": "",
             "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
             "source_tier": 1, "baskets": "", "tickers": "000333.SZ",
             "score": 2.0, "sentiment": 1.0, "scheduled_ref": ""},
            {"event_id": "high2", "first_seen_utc": "2026-06-23T01:00:00+00:00",
             "seendate": "2026-06-23", "title": "High2", "summary": "",
             "url": "http://x", "domain": "x", "source": "s", "theme": "macro",
             "source_tier": 1, "baskets": "", "tickers": "000333.SZ",
             "score": 3.0, "sentiment": 1.0, "scheduled_ref": ""},
        ]
        df = pd.DataFrame(all_covered_events)
        events_path = fake_root / "data" / "china_news_vector" / "events.parquet"
        df.to_parquet(events_path, index=False)

        result = placebo.run(fake_root, asof="2026-07-03", k=4, dry_run=True)
        # CN covered pool has 10 events (all low, all 600519.SS covered), US has 0 tickers
        # k_cn=2, k_us=2 → CN gets 2 covered, US gets 2 uncovered → total fallback = 2
        assert result["n_fallback"] <= 2, (
            f"Expected n_fallback<=2 (only US fallback), got {result['n_fallback']}"
        )

    def test_covered_ticker_entity_not_bench_basket(self, fake_root):
        """Covered-ticker placebo claims must be entity-scope (not bench basket).

        The bench-basket path (scope_key == bench ticker) produces excess ≡ 0.
        Entity claims against real tickers produce non-degenerate |excess|.
        """
        placebo.run(fake_root, asof="2026-07-02", k=6)
        claims = q.load_claims(fake_root)
        cn_placebo = [c for c in claims if c.get("is_placebo") and c.get("corpus") == "cn"]
        entity_claims = [c for c in cn_placebo if c["scope"]["type"] == "entity"]
        # ev4 → 600519.SS with 2 horizons = 2 entity claims minimum
        assert len(entity_claims) >= 2, (
            f"Expected ≥2 entity-scope CN placebo claims; got {len(entity_claims)}: "
            f"{[c['scope'] for c in cn_placebo]}"
        )
        # Confirm those entity claims are NOT pointing at the bench itself
        bench_keys = {placebo._CN_BENCH, placebo._US_BENCH}
        for c in entity_claims:
            assert c["scope"]["key"] not in bench_keys, (
                f"Entity placebo claim scope.key is the bench (degenerate): {c['scope']}"
            )

    def test_placebo_path_field_recorded(self, fake_root):
        """placebo_path field records 'covered_ticker' or 'fallback_no_ticker'."""
        placebo.run(fake_root, asof="2026-07-02", k=6)
        claims = q.load_claims(fake_root)
        placebo_claims = [c for c in claims if c.get("is_placebo")]
        valid_paths = {"covered_ticker", "fallback_no_ticker"}
        for c in placebo_claims:
            path = c.get("placebo_path")
            assert path in valid_paths, (
                f"placebo_path={path!r} not in {valid_paths}: {c}"
            )
        # At least one claim on covered_ticker path (ev4 → 600519.SS)
        covered_path_claims = [c for c in placebo_claims if c.get("placebo_path") == "covered_ticker"]
        assert covered_path_claims, "Expected at least one claim with placebo_path='covered_ticker'"

    def test_determinism_covered_sample(self, fake_root):
        """Same asof produces identical sampled event ids across two dry runs."""
        import scripts.sample_qledger_placebo as _p
        import random

        asof = "2026-07-04"
        rng1 = random.Random(_p._asof_seed(asof))
        rng2 = random.Random(_p._asof_seed(asof))

        cn_low = _p._load_cn_low_importance(fake_root)
        us_all = _p._load_us_events(fake_root)
        k = 6

        sample1, _ = _p._biased_sample(cn_low, k - k // 2, rng1, "cn", fake_root)
        sample2, _ = _p._biased_sample(cn_low, k - k // 2, rng2, "cn", fake_root)

        assert sorted(sample1.index.tolist()) == sorted(sample2.index.tolist()), (
            "Same asof seed produced different CN samples — not deterministic"
        )

    def test_idempotency_covered_ticker(self, fake_root):
        """Re-running placebo for same asof after the fix does not duplicate claims."""
        placebo.run(fake_root, asof="2026-07-02", k=6)
        n_after_first = len(q.load_claims(fake_root))
        placebo.run(fake_root, asof="2026-07-02", k=6)
        n_after_second = len(q.load_claims(fake_root))
        assert n_after_first == n_after_second, (
            f"Duplicate claims created: {n_after_first} → {n_after_second}"
        )
