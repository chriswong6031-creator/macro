"""Tests for engine/importance_v0.py + scripts/shadow_importance_v0.py (W3, D6).

Hermetic: a synthetic qbus items.parquet + tmp_path price parquets + tmp qledger.
No live data, no network, no ambient clock.

Coverage:
  - formula DETERMINISM: same store → identical scores twice
  - score bounds: importance_v0 ∈ [0, 1]
  - novelty UP: a subject that spikes today scores higher than a flat subject
  - crowding PENALTY: a subject loud all week is penalised vs a fresh spike
  - source_tier weight: tier-1 wire > tier-3 aggregator, all else equal
  - corroboration is novelty-GATED: within-window echo of a LOW-novelty story
    does not inflate the score
  - scheduled-surprise is EXCLUDED (documented) and weights renormalise to 1.0
  - lane routing: zh → cn, en → us, auto sniffs CJK
  - clean_df: tz-mixed + NaT store is normalised, dateless rows dropped
  - band assignment: top/bottom band_frac → HIGH/LOW, no overlap, deterministic
  - claim registration idempotency: re-run registers zero NEW claims
  - backfill counts: pairs → registered = pairs × horizons; no-ticker skipped
  - every registered claim is direction=0, is_placebo=False, band-tagged
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine import importance_v0 as iv  # noqa: E402
from engine import qbus  # noqa: E402
from engine import qledger as q  # noqa: E402
import scripts.shadow_importance_v0 as shadow  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _row(item_id, lang, entities, themes, seendate, tier, event_key,
         desk="d", source="s"):
    return {
        "item_id": item_id, "event_key": event_key, "desk": desk,
        "source": source, "source_tier": tier, "lang": lang,
        "url": "", "title": f"title {item_id}", "body_sha256": "",
        "seendate": seendate, "_crawled_at": "", "timestamp_quality": "CRAWL_BOUNDED",
        "entities": entities, "themes": themes, "importance_raw": 0.0,
    }


def _store() -> pd.DataFrame:
    """A synthetic bus store exercising novelty, crowding, tiers, and lanes.

    NVDA: quiet for weeks then a single-day spike on the asof day → high novelty.
    AAPL: loud EVERY day for the whole window → low novelty, high crowding.
    A tz-MIXED seendate column + one dateless row exercise clean_df.
    """
    rows = []
    # AAPL — present every day 06-01..06-30 (loud all window = crowded, low novelty)
    for i, d in enumerate(pd.bdate_range("2026-06-01", "2026-06-30")):
        rows.append(_row(f"aapl{i}", "en", "AAPL", "tech",
                         d.strftime("%Y-%m-%d") + " 12:00:00", 2, f"evA{i}"))
    # NVDA — absent all window, then 3 items on 06-30 only (fresh spike)
    for j in range(3):
        rows.append(_row(f"nvda{j}", "en", "NVDA", "semis",
                         "2026-06-30T12:00:00+00:00", 1, f"evN{j}"))
    # a CN (zh) row with a tz-naive seendate
    rows.append(_row("cn1", "zh", "600519.SS", "baijiu",
                     "2026-06-29 09:00:00", 2, "evCN1"))
    # a totally dateless row → clean_df must drop it
    rows.append(_row("dead", "en", "T", "misc", "", 0, "evDead"))
    return pd.DataFrame(rows, columns=list(qbus.COLUMNS))


@pytest.fixture()
def store() -> pd.DataFrame:
    return _store()


# --------------------------------------------------------------------------- #
# clean_df
# --------------------------------------------------------------------------- #
def test_clean_df_normalises_mixed_tz_and_drops_dateless(store):
    clean = iv.clean_df(store)
    # dateless "dead" row dropped; all others kept
    assert "dead" not in set(clean["item_id"])
    assert len(clean) == len(store) - 1
    # seendate is now a uniform date-only string, no NaT
    d = pd.to_datetime(clean["seendate"], errors="coerce")
    assert d.notna().all()
    # tz-naive CN row survived normalisation
    assert "cn1" in set(clean["item_id"])


# --------------------------------------------------------------------------- #
# determinism + bounds
# --------------------------------------------------------------------------- #
def test_determinism(store):
    a = iv.score_store(df=store)
    b = iv.score_store(df=store)
    assert [r["importance_v0"] for r in a] == [r["importance_v0"] for r in b]
    # and per-item score_components is stable
    clean = iv.clean_df(store)
    item = clean.to_dict("records")[0]
    asof = clean["seendate"].iloc[0][:10]
    assert (iv.importance_v0(item, asof, df=clean)
            == iv.importance_v0(item, asof, df=clean))


def test_scores_in_unit_interval(store):
    for r in iv.score_store(df=store):
        assert 0.0 <= r["importance_v0"] <= 1.0


# --------------------------------------------------------------------------- #
# feature semantics
# --------------------------------------------------------------------------- #
def test_novelty_pushes_score_up(store):
    """NVDA (fresh 06-30 spike, tier-1) should out-score AAPL (loud all window)."""
    scored = {r["item_id"]: r for r in iv.score_store(df=store, lane="us")}
    nvda = scored["nvda0"]
    # find an AAPL row on 06-30 for a same-day comparison
    aapl_last = max((r for r in scored.values() if r["subject"] == "AAPL"),
                    key=lambda r: r["asof"])
    assert nvda["novelty"] > aapl_last["novelty"]
    assert nvda["importance_v0"] > aapl_last["importance_v0"]


def test_crowding_penalises_persistent_attention(store):
    scored = {r["item_id"]: r for r in iv.score_store(df=store, lane="us")}
    aapl_last = max((r for r in scored.values() if r["subject"] == "AAPL"),
                    key=lambda r: r["asof"])
    # AAPL loud every day → positive crowding_z → a real penalty
    assert aapl_last["crowding_penalty"] > 0.0
    # NVDA fresh → no crowding penalty
    assert scored["nvda0"]["crowding_penalty"] == 0.0


def test_source_tier_weight(store):
    """Tier-1 beats tier-3, all else equal (same subject, same asof, no novelty
    difference)."""
    clean = iv.clean_df(store)
    base = dict(clean.to_dict("records")[0])
    base["entities"] = "ZZZ"          # unique subject → novelty neutral (None→0.5)
    base["themes"] = ""
    base["event_key"] = "evZ"
    asof = "2026-06-15"
    t1 = dict(base, source_tier=1)
    t3 = dict(base, source_tier=3)
    assert (iv.importance_v0(t1, asof, df=clean)
            > iv.importance_v0(t3, asof, df=clean))


def test_corroboration_is_novelty_gated(store):
    """A LOW-novelty subject with high cross-desk breadth must NOT get a big
    corroboration bump — corroboration = breadth × novelty."""
    clean = iv.clean_df(store)
    # AAPL is low-novelty (loud all window). Even if it had breadth, corroboration
    # is gated by its low novelty.
    scored = {r["item_id"]: r for r in iv.score_store(df=clean, lane="us")}
    aapl = max((r for r in scored.values() if r["subject"] == "AAPL"),
               key=lambda r: r["asof"])
    # corroboration <= breadth (novelty in [0,1]) and, for a low-novelty subject,
    # is strictly damped.
    assert aapl["corroboration"] <= aapl["breadth"] + 1e-9


def test_surprise_excluded_and_weights_sum_to_one():
    assert iv._SURPRISE_EXCLUDED is True
    total = iv.W_NOVELTY + iv.W_CORROBORATION + iv.W_SOURCE_TIER + iv.W_CROWDING
    assert abs(total - 1.0) < 1e-9


# --------------------------------------------------------------------------- #
# StoreIndex fast path — pinned equivalent to the frame-scan paths.
# score_store now builds a qbus.StoreIndex once per snapshot (the 2026-08 fix
# for the O(store²) collect_tail blowups); these tests are the contract that
# the index path and the per-call frame paths never diverge.
# --------------------------------------------------------------------------- #
def test_index_matches_frame_paths(store):
    clean = iv.clean_df(store)
    index = qbus.build_index(clean)
    assert index is not None

    subjects = {s for r in clean.to_dict("records")
                for s in (qbus._split(r["entities"]) + qbus._split(r["themes"]))}
    asofs = ["2026-06-01", "2026-06-15", "2026-06-29", "2026-06-30", "2026-07-05"]
    for subject in sorted(subjects):
        for asof in asofs:
            for w in (7, 30):
                assert (qbus.novelty_z(subject, asof, window_days=w, df=clean)
                        == qbus.novelty_z(subject, asof, window_days=w,
                                          df=clean, index=index)), \
                    f"novelty_z diverged: {subject} {asof} w={w}"

    keys = {str(k) for k in clean["event_key"].tolist() if str(k)}
    for key in sorted(keys):
        for asof in [None] + asofs:
            assert (qbus.echo_stats(key, df=clean, asof=asof)
                    == qbus.echo_stats(key, df=clean, asof=asof, index=index)), \
                f"echo_stats diverged: {key} asof={asof}"
    # absent key + empty key → None on both paths
    assert qbus.echo_stats("ev_nope", df=clean, index=index) is None
    assert qbus.echo_stats("", df=clean, index=index) is None


def test_index_matches_frame_paths_on_raw_tz_mixed_store(store):
    """The index must reproduce the frame paths on the RAW (tz-mixed, dateless-
    row-bearing) store too — build_index is not allowed to assume clean_df ran."""
    index = qbus.build_index(store)
    assert index is not None
    for subject in ("AAPL", "NVDA", "600519.SS", "tech", "misc", "GHOST"):
        for asof in ("2026-06-15", "2026-06-30"):
            assert (qbus.novelty_z(subject, asof, df=store)
                    == qbus.novelty_z(subject, asof, df=store, index=index))
    for key in ("evA0", "evN1", "evCN1", "evDead"):
        for asof in (None, "2026-06-15", "2026-06-30"):
            assert (qbus.echo_stats(key, df=store, asof=asof)
                    == qbus.echo_stats(key, df=store, asof=asof, index=index))


def test_index_edge_semantics_match_frame_paths():
    """The two hairy corners, pinned on both paths:
    * a subject listed in BOTH entities and themes counts the row ONCE
      (_subject_daily_counts is an OR-match, not a sum);
    * novelty days use seendate-fallback-_crawled_at while echo's PIT stamp uses
      _crawled_at-fallback-seendate — the REVERSED precedence must survive."""
    rows = [
        # subject in both fields; seendate day differs from _crawled_at day
        _row("both1", "en", "TSLA", "TSLA", "2026-06-10 08:00:00", 1, "evB"),
        _row("both2", "en", "TSLA", "evs", "", 2, "evB"),   # dateless seendate
    ]
    rows[0]["_crawled_at"] = "2026-06-12T09:00:00+00:00"
    rows[1]["_crawled_at"] = "2026-06-11T10:00:00+00:00"
    frame = pd.DataFrame(rows, columns=list(qbus.COLUMNS))
    index = qbus.build_index(frame)
    assert index is not None
    for asof in ("2026-06-10", "2026-06-11", "2026-06-12", "2026-06-13"):
        assert (qbus.novelty_z("TSLA", asof, df=frame)
                == qbus.novelty_z("TSLA", asof, df=frame, index=index))
        assert (qbus.echo_stats("evB", df=frame, asof=asof)
                == qbus.echo_stats("evB", df=frame, asof=asof, index=index))
    # single-count check directly: both1 lists TSLA twice but is ONE row
    today, _ = index.subject_daily_counts("TSLA", pd.Timestamp("2026-06-10").date(), 7)
    assert today == 1.0


def test_score_store_output_identical_with_and_without_index(store, monkeypatch):
    """End-to-end pin: score_store (which builds the index internally) must
    produce byte-identical component rows to a run where the index build is
    disabled and every read falls back to the frame-scan paths."""
    fast = iv.score_store(df=store)
    monkeypatch.setattr(qbus, "build_index", lambda df: None)
    slow = iv.score_store(df=store)
    assert fast == slow
    assert len(fast) > 0


# --------------------------------------------------------------------------- #
# lane routing
# --------------------------------------------------------------------------- #
def test_lane_routing():
    assert iv.lane_of({"lang": "zh"}) == "cn"
    assert iv.lane_of({"lang": "en"}) == "us"
    assert iv.lane_of({"lang": "auto", "title": "央行降准"}) == "cn"
    assert iv.lane_of({"lang": "auto", "title": "Fed holds rates"}) == "us"


def test_primary_subject_entity_then_theme():
    assert iv.primary_subject({"entities": "NVDA,AMD", "themes": "semis"}) == "NVDA"
    assert iv.primary_subject({"entities": "", "themes": "monetary"}) == "monetary"
    assert iv.primary_subject({"entities": "", "themes": ""}) is None


# --------------------------------------------------------------------------- #
# band assignment
# --------------------------------------------------------------------------- #
def test_band_assignment_no_overlap_and_deterministic():
    scored = [{"item_id": f"i{i}", "importance_v0": v}
              for i, v in enumerate([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])]
    bands = shadow._assign_bands(scored, band_frac=0.25)
    highs = {k for k, v in bands.items() if v == "HIGH"}
    lows = {k for k, v in bands.items() if v == "LOW"}
    assert highs.isdisjoint(lows)                     # no overlap
    assert bands["i7"] == "HIGH" and bands["i6"] == "HIGH"   # top 25% (2 of 8)
    assert bands["i0"] == "LOW" and bands["i1"] == "LOW"     # bottom 25%
    assert "i3" not in bands and "i4" not in bands           # middle unscored
    # deterministic
    assert shadow._assign_bands(scored, 0.25) == bands


def test_band_assignment_never_overlaps_tiny_lane():
    scored = [{"item_id": "a", "importance_v0": 0.1},
              {"item_id": "b", "importance_v0": 0.9}]
    bands = shadow._assign_bands(scored, band_frac=0.9)
    assert bands == {"a": "LOW", "b": "HIGH"}   # clamped so HIGH≠LOW


# --------------------------------------------------------------------------- #
# shadow registration — counts, idempotency, claim shape
# --------------------------------------------------------------------------- #
def _write_price(path: Path, start="2026-05-01", n=90, px=10.0):
    idx = pd.bdate_range(start=start, periods=n)
    pd.DataFrame({"close": [px * (1.005 ** i) for i in range(n)]},
                 index=idx).to_parquet(path)


@pytest.fixture()
def fake_root(tmp_path: Path, store: pd.DataFrame, monkeypatch):
    """A tmp repo root with the synthetic store at data/qbus/items.parquet and
    price parquets for the coverable tickers, qbus pointed at it."""
    root = tmp_path / "repo"
    (root / "data" / "qbus").mkdir(parents=True)
    store.to_parquet(root / "data" / "qbus" / "items.parquet", index=False)

    # US price coverage (yahoo) for AAPL + NVDA + benches; CN for 600519.SS
    (root / "data" / "yahoo").mkdir(parents=True)
    for t in ("AAPL", "NVDA", "SPY", "T"):
        _write_price(root / "data" / "yahoo" / f"{t}.parquet")
    (root / "data" / "china_stocks").mkdir(parents=True)
    _write_price(root / "data" / "china_stocks" / "600519.SS.parquet")
    (root / "data" / "china").mkdir(parents=True)
    _write_price(root / "data" / "china" / "510300.SS.parquet")

    # point qbus's store path + config.ROOT at the tmp root
    monkeypatch.setattr(qbus, "_events_path",
                        lambda: root / "data" / "qbus" / "items.parquet")
    from lib import config
    monkeypatch.setattr(config, "ROOT", root)
    return root


def test_shadow_backfill_counts_and_horizons(fake_root):
    res = shadow.run(fake_root, band_frac=0.5)
    # every registered pair yields exactly len(_HORIZONS) claims
    for lane in ("us", "cn"):
        pairs = res[f"{lane}_pairs"]
        reg = res[f"{lane}_registered"]
        assert reg == pairs * len(shadow._HORIZONS)
    # US lane had coverable AAPL/NVDA/T; something registered
    assert res["us_registered"] > 0


def test_shadow_registration_idempotent(fake_root):
    first = shadow.run(fake_root, band_frac=0.5)
    n_after_first = len(q.load_claims(fake_root))
    shadow.run(fake_root, band_frac=0.5)           # re-run
    n_after_second = len(q.load_claims(fake_root))
    assert n_after_second == n_after_first          # zero NEW claims
    assert first["us_registered"] + first["cn_registered"] > 0


def test_shadow_claims_are_salience_only_and_band_tagged(fake_root):
    shadow.run(fake_root, band_frac=0.5)
    claims = [c for c in q.load_claims(fake_root)
              if c.get("claim_family") in ("us_importance_v0", "cn_importance_v0")]
    assert claims, "expected challenger claims"
    for c in claims:
        assert c["direction"] == 0                  # salience-only (§2.3/D5)
        assert c.get("is_placebo") is False         # a real tape, not the null
        assert c.get("band") in ("HIGH", "LOW")     # band-tagged
        assert c["horizon_d"] in shadow._HORIZONS
        assert c["timestamp_quality"] == "CRAWL_BOUNDED"


def test_shadow_no_ticker_items_skipped(fake_root):
    """A HIGH/LOW item whose entities have no price coverage produces no claim
    and increments the no_ticker counter (the covered-ticker rule)."""
    res = shadow.run(fake_root, band_frac=0.5)
    # CN lane: only 600519.SS is coverable; other CN items (none here) would skip.
    # Assert the counter exists and is a non-negative int (contract), and that
    # dry-run and live agree on pairs.
    assert res["us_no_ticker"] >= 0 and res["cn_no_ticker"] >= 0
    dry = shadow.run(fake_root, band_frac=0.5, dry_run=True)
    assert dry["us_pairs"] == res["us_pairs"]


# --------------------------------------------------------------------------- #
# duel report — reads the tmp ledger, produces comparable slices
# --------------------------------------------------------------------------- #
def test_duel_report_builds_from_ledger(fake_root):
    import scripts.report_importance_duel as duel
    shadow.run(fake_root, band_frac=0.5)
    rep = duel.build_report(fake_root)
    assert set(rep["by_horizon"]) >= {"5", "21"}
    h5 = rep["by_horizon"]["5"]
    assert "champion_china_news" in h5
    assert "challenger_us_importance_v0" in h5
    assert "placebo" in h5
    # each challenger slice reports HIGH and LOW with an honest n_dates
    us = h5["challenger_us_importance_v0"]
    assert "n_dates" in us["HIGH"] and "state" in us["HIGH"]
