"""Tests for engine/qbus.py — the unified item/event store.

Covers: schema normalization + timestamp_quality enum, event_key clustering on a
paraphrase set (shared-subject gate + shingle similarity), keep-FIRST PIT
discipline on append, novelty_z math (injected asof + df), and echo_stats
cross-desk corroboration. Storage is redirected to a tmp path so no tracked
parquet is touched.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import qbus  # noqa: E402


def _row(**kw):
    base = {"desk": "financial_news", "source": "reuters", "url": "", "title": "",
            "seendate": "2026-06-19T12:00:00+00:00", "_crawled_at": "2026-06-19T12:05:00+00:00",
            "entities": [], "themes": [], "lang": "en"}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# schema + timestamp_quality
# --------------------------------------------------------------------------- #
def test_normalize_row_fills_defaults():
    r = qbus.normalize_row(_row(title="Fed holds rates", url="https://reuters.com/x",
                                entities=["SPY"], themes=["monetary"]))
    assert set(r.keys()) == set(qbus.COLUMNS)
    assert r["item_id"] and len(r["item_id"]) == 16
    assert r["source_tier"] == 1                      # reuters.com host
    assert r["timestamp_quality"] == "CRAWL_BOUNDED"  # default
    assert r["entities"] == "SPY" and r["themes"] == "monetary"


def test_normalize_row_bad_timestamp_quality_defaults():
    r = qbus.normalize_row(_row(title="x", timestamp_quality="NONSENSE"))
    assert r["timestamp_quality"] == "CRAWL_BOUNDED"


def test_normalize_row_valid_timestamp_quality_kept():
    r = qbus.normalize_row(_row(title="x", timestamp_quality="DISCLOSURE_DATE"))
    assert r["timestamp_quality"] == "DISCLOSURE_DATE"


def test_body_sha256():
    assert qbus.body_sha256("") == ""
    assert qbus.body_sha256(None) == ""
    assert len(qbus.body_sha256("hello")) == 64


# --------------------------------------------------------------------------- #
# event_key clustering — paraphrase set
# --------------------------------------------------------------------------- #
def test_event_key_clusters_paraphrases_sharing_subject():
    rows = [
        _row(title="Fed holds interest rates steady", entities=["SPY"], themes=["monetary"],
             source="reuters", url="https://reuters.com/a"),
        _row(title="Fed holds interest rates steady in June", entities=["SPY"], themes=["monetary"],
             source="ap", url="https://apnews.com/b"),
        _row(title="OPEC agrees to cut oil output", entities=["XLE"], themes=["energy"],
             source="reuters", url="https://reuters.com/c"),
    ]
    out = qbus.assign_event_keys(rows, thresh=0.5, window_days=3)
    keys = [r["event_key"] for r in out]
    assert keys[0] == keys[1]        # the two Fed paraphrases collapse
    assert keys[2] != keys[0]        # OPEC is a distinct event


def test_event_key_requires_shared_subject():
    # identical-ish titles but NO shared entity/theme should not merge.
    rows = [
        _row(title="Prices rise sharply", entities=["AAA"], themes=["t1"],
             url="https://a.com/1"),
        _row(title="Prices rise sharply", entities=["BBB"], themes=["t2"],
             url="https://b.com/2"),
    ]
    out = qbus.assign_event_keys(rows, thresh=0.5, window_days=3)
    assert out[0]["event_key"] != out[1]["event_key"]


def test_event_key_window_gate():
    # same story, but crawl days too far apart → not one event.
    rows = [
        _row(title="Fed holds rates steady", entities=["SPY"], themes=["monetary"],
             seendate="2026-06-01T00:00:00+00:00", _crawled_at="2026-06-01T00:00:00+00:00"),
        _row(title="Fed holds rates steady", entities=["SPY"], themes=["monetary"],
             seendate="2026-06-20T00:00:00+00:00", _crawled_at="2026-06-20T00:00:00+00:00",
             url="https://x.com/2"),
    ]
    out = qbus.assign_event_keys(rows, thresh=0.5, window_days=3)
    assert out[0]["event_key"] != out[1]["event_key"]


def test_event_key_deterministic_regardless_of_order():
    a = _row(title="Fed holds rates steady", entities=["SPY"], themes=["monetary"],
             source="ap", url="https://apnews.com/a", source_tier=2)
    b = _row(title="Fed holds rates steady now", entities=["SPY"], themes=["monetary"],
             source="reuters", url="https://reuters.com/b", source_tier=1)
    k1 = {r["item_id"]: r["event_key"] for r in qbus.assign_event_keys([a, b], 0.4, 3)}
    k2 = {r["item_id"]: r["event_key"] for r in qbus.assign_event_keys([b, a], 0.4, 3)}
    assert k1 == k2   # representative (lowest tier) fixes the key regardless of order


# --------------------------------------------------------------------------- #
# append — keep-FIRST PIT discipline
# --------------------------------------------------------------------------- #
def test_append_keep_first_on_item_id(tmp_path, monkeypatch):
    p = tmp_path / "items.parquet"
    monkeypatch.setattr(qbus, "_events_path", lambda: p)
    first = qbus.append_items([_row(title="Rate cut", url="https://reuters.com/x",
                                    entities=["SPY"], seendate="2026-06-19T00:00:00+00:00")])
    assert first is not None and len(first) == 1
    orig_seen = first.iloc[0]["seendate"]
    # a restatement of the SAME item (same host+title → same item_id) with a LATER
    # seendate must NOT overwrite the original print.
    merged = qbus.append_items([_row(title="Rate  cut!", url="https://reuters.com/x",
                                     entities=["SPY"], seendate="2026-06-25T00:00:00+00:00")])
    assert len(merged) == 1
    assert merged.iloc[0]["seendate"] == orig_seen


def test_read_items_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(qbus, "_events_path", lambda: tmp_path / "nope.parquet")
    assert qbus.read_items() is None


# --------------------------------------------------------------------------- #
# novelty_z
# --------------------------------------------------------------------------- #
def _mk_df(rows):
    return pd.DataFrame([qbus.normalize_row(r) for r in rows], columns=list(qbus.COLUMNS))


def test_novelty_z_spike_is_positive():
    # subject "NVDA" quiet for a month (1/day baseline), then 6 items today.
    rows = []
    for d in range(1, 30):
        rows.append(_row(title=f"nvidia note {d}", entities=["NVDA"],
                         seendate=f"2026-05-{d:02d}T00:00:00+00:00",
                         _crawled_at=f"2026-05-{d:02d}T00:00:00+00:00",
                         url=f"https://x.com/{d}"))
    for k in range(6):
        rows.append(_row(title=f"nvidia breaking {k}", entities=["NVDA"],
                         seendate="2026-06-01T00:00:00+00:00",
                         _crawled_at="2026-06-01T00:00:00+00:00",
                         url=f"https://y.com/{k}"))
    df = _mk_df(rows)
    z = qbus.novelty_z("NVDA", date(2026, 6, 1), window_days=31, df=df)
    assert z is not None and z > 1.0


def test_novelty_z_flat_returns_zero_or_low():
    rows = [_row(title=f"note {d}", entities=["AAA"],
                 seendate=f"2026-05-{d:02d}T00:00:00+00:00",
                 _crawled_at=f"2026-05-{d:02d}T00:00:00+00:00",
                 url=f"https://x.com/{d}") for d in range(1, 20)]
    # today (06-01) matches the flat baseline level (also 1) → not novel.
    rows.append(_row(title="note today", entities=["AAA"],
                     seendate="2026-06-01T00:00:00+00:00",
                     _crawled_at="2026-06-01T00:00:00+00:00", url="https://x.com/today"))
    df = _mk_df(rows)
    z = qbus.novelty_z("AAA", date(2026, 6, 1), window_days=31, df=df)
    assert z is not None and z <= 1.0


def test_novelty_z_none_on_empty():
    assert qbus.novelty_z("X", date(2026, 6, 1), df=_mk_df([])) is None


def test_novelty_z_unknown_subject_returns_none():
    """A subject entirely absent from the store is 'no evidence', not z=0.0.
    (W1C fix 1: no-evidence honesty — today==0 AND mean==0 → None, not 0.0)"""
    # Build a df that has only "KNOWN" entity so "UNKNOWN" has zero history AND
    # zero today count.
    rows = [_row(title=f"note {d}", entities=["KNOWN"],
                 seendate=f"2026-05-{d:02d}T00:00:00+00:00",
                 _crawled_at=f"2026-05-{d:02d}T00:00:00+00:00",
                 url=f"https://x.com/{d}") for d in range(1, 20)]
    df = _mk_df(rows)
    z = qbus.novelty_z("UNKNOWN", date(2026, 6, 1), window_days=31, df=df)
    assert z is None, f"expected None for entirely absent subject, got {z!r}"


def test_novelty_z_flat_nonzero_returns_zero():
    """When ALL window days have the same nonzero count AND today matches it, z=0.0.
    This is genuinely 'not novel', so 0.0 is correct (not None).
    The flat branch (sd<=1e-9) fires when every day in the window has identical count.
    (W1C fix 1: contrast with absent-subject case — mean>0, today==mean → 0.0 not None)"""
    # Inject EXACTLY 2 items per day for EVERY day in the 7-day trailing window so that
    # all days have equal count → sd = 0 → the flat branch fires.
    from datetime import timedelta
    asof = date(2026, 6, 1)
    window = 7
    rows = []
    for delta in range(1, window + 1):  # days 1..7 before asof
        d = asof - timedelta(days=delta)
        for k in range(2):
            rows.append(_row(title=f"aaa {delta}-{k}", entities=["AAA"],
                             seendate=f"{d.isoformat()}T00:00:00+00:00",
                             _crawled_at=f"{d.isoformat()}T00:00:00+00:00",
                             url=f"https://x.com/{delta}-{k}"))
    # today: also 2 items — matches the flat baseline exactly
    for k in range(2):
        rows.append(_row(title=f"aaa today {k}", entities=["AAA"],
                         seendate=f"{asof.isoformat()}T00:00:00+00:00",
                         _crawled_at=f"{asof.isoformat()}T00:00:00+00:00",
                         url=f"https://x.com/today-{k}"))
    df = _mk_df(rows)
    z = qbus.novelty_z("AAA", asof, window_days=window, df=df)
    # All window days = 2 items → sd=0, mean=2, today=2 → today not > mean → 0.0
    assert z is not None and z == 0.0, f"expected 0.0 for flat-nonzero match, got {z!r}"


def test_novelty_z_drop_to_zero_on_flat_nonzero_baseline_returns_zero():
    """Flat NONZERO window but today has NO items (attention dropped away):
    mean>0 branch must return 0.0 — this is evidence of quiet, not absence of
    evidence, so it must NOT become None (and must not hit the 3.0 spike branch).
    (W1C fix 1 edge case: today=0, mean>0, sd=0)"""
    from datetime import timedelta
    asof = date(2026, 6, 1)
    window = 7
    rows = []
    for delta in range(1, window + 1):
        d = asof - timedelta(days=delta)
        rows.append(_row(title=f"bbb {delta}", entities=["BBB"],
                         seendate=f"{d.isoformat()}T00:00:00+00:00",
                         _crawled_at=f"{d.isoformat()}T00:00:00+00:00",
                         url=f"https://x.com/bbb-{delta}"))
    # no rows for asof itself → today = 0 against a flat baseline of 1/day
    df = _mk_df(rows)
    z = qbus.novelty_z("BBB", asof, window_days=window, df=df)
    assert z == 0.0, f"expected 0.0 for drop-to-zero on nonzero flat baseline, got {z!r}"


def test_novelty_z_spike_over_zero_baseline_returns_3():
    """Subject with zero history but nonzero today → 3.0 (maximally novel).
    (W1C fix 1: today > mean in the flat branch)"""
    rows = []
    # No history for "NEWCO" in the trailing window
    for d in range(1, 20):
        rows.append(_row(title=f"other {d}", entities=["OTHER"],
                         seendate=f"2026-05-{d:02d}T00:00:00+00:00",
                         _crawled_at=f"2026-05-{d:02d}T00:00:00+00:00",
                         url=f"https://x.com/{d}"))
    # today: 4 NEWCO items (spike from zero)
    for k in range(4):
        rows.append(_row(title=f"newco breaking {k}", entities=["NEWCO"],
                         seendate="2026-06-01T00:00:00+00:00",
                         _crawled_at="2026-06-01T00:00:00+00:00",
                         url=f"https://x.com/newco{k}"))
    df = _mk_df(rows)
    z = qbus.novelty_z("NEWCO", date(2026, 6, 1), window_days=31, df=df)
    assert z == 3.0, f"expected 3.0 for spike over zero baseline, got {z!r}"


def test_novelty_z_survives_tz_mixed_store():
    # live-store shape: EN rows carry tz-aware ISO stamps while CN rows carry
    # tz-NAIVE strings in the SAME seendate column, with tz-aware rows FIRST.
    # Row order matters: plain pd.to_datetime(errors="coerce") locks onto the
    # format of the first value and NaT-ed every naive row after it, silently
    # nulling the whole CN lane; the naive-side subject must still get a real z.
    rows = []
    for d in range(1, 10):  # tz-aware rows first, as on the live store
        rows.append(_row(title=f"spy note {d}", entities=["SPY"],
                         seendate=f"2026-05-{d:02d}T12:00:00+00:00",
                         _crawled_at=f"2026-05-{d:02d}T12:05:00+00:00",
                         url=f"https://en.example/{d}"))
    for d in range(1, 30):  # naive-tz baseline for the CN-lane subject
        rows.append(_row(title=f"pboc note {d}", entities=["PBOC"], lang="zh",
                         seendate=f"2026-05-{d:02d} 09:30:00",
                         _crawled_at=f"2026-05-{d:02d} 09:35:00",
                         url=f"https://cn.example/{d}"))
    for k in range(6):      # naive-tz spike on the asof day
        rows.append(_row(title=f"pboc breaking {k}", entities=["PBOC"], lang="zh",
                         seendate="2026-06-01 08:00:00",
                         _crawled_at="2026-06-01 08:05:00",
                         url=f"https://cn.example/b{k}"))
    df = _mk_df(rows)
    z = qbus.novelty_z("PBOC", date(2026, 6, 1), window_days=31, df=df)
    assert z is not None and z > 1.0


def test_novelty_z_ignores_dateless_rows_without_raising():
    # dateless rows (NaT for BOTH seendate and _crawled_at — the stale
    # news_vector accrual) must neither raise on the NaT-vs-date comparison
    # (which swallowed into None) nor count toward the volume basis.
    rows = [_row(title=f"note {d}", entities=["AAA"],
                 seendate=f"2026-05-{d:02d} 10:00:00",
                 _crawled_at=f"2026-05-{d:02d} 10:00:00",
                 url=f"https://x.com/{d}") for d in range(1, 30)]
    rows.append(_row(title="note today", entities=["AAA"],
                     seendate="2026-06-01 10:00:00",
                     _crawled_at="2026-06-01 10:00:00", url="https://x.com/today"))
    for k in range(5):  # matched-subject dateless rows
        rows.append(_row(title=f"stale accrual {k}", entities=["AAA"],
                         seendate="", _crawled_at="",
                         url=f"https://stale.example/{k}"))
    df = _mk_df(rows)
    z = qbus.novelty_z("AAA", date(2026, 6, 1), window_days=31, df=df)
    # flat 1/day baseline and 1 real item today: if the dateless rows leaked
    # into today's count the z would spike; if they raised, z would be None.
    assert z is not None and z <= 1.0


# --------------------------------------------------------------------------- #
# echo_stats
# --------------------------------------------------------------------------- #
def test_echo_stats_cross_desk_breadth():
    rows = [
        _row(title="Fed holds rates steady", desk="financial_news", source="reuters",
             entities=["SPY"], themes=["monetary"], url="https://reuters.com/a"),
        _row(title="Fed holds rates steady now", desk="china_news_intel", source="jin10",
             entities=["SPY"], themes=["monetary"], url="https://jin10.com/b"),
        _row(title="Fed holds rates steady in June", desk="financial_news", source="ap",
             entities=["SPY"], themes=["monetary"], url="https://apnews.com/c"),
    ]
    clustered = qbus.assign_event_keys(rows, thresh=0.4, window_days=3)
    df = pd.DataFrame(clustered, columns=list(qbus.COLUMNS))
    key = clustered[0]["event_key"]
    st = qbus.echo_stats(key, df=df)
    assert st is not None
    assert st["n_desks"] == 2 and st["breadth"] == 2
    assert st["n_sources"] == 3 and st["n_items"] == 3


def test_echo_stats_missing_key():
    assert qbus.echo_stats("nope", df=_mk_df([_row(title="x", entities=["A"])])) is None
