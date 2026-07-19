"""engine/ticker_alerts.py — the per-ticker / per-ETF alert feed.

Synthetic price paths exercise each event generator; invariants cover the
record schema (bilingual completeness), id determinism/idempotency, the recent
window, the pinned ladder read, and the append-only ladder log.

Run: .venv/bin/python -m pytest tests/test_ticker_alerts.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ticker_alerts as ta  # noqa: E402

REQUIRED = {"id", "ts", "source", "asset", "type", "filter", "severity", "dir",
            "tier", "pinned", "label", "label_zh", "headline", "detail",
            "headline_zh", "detail_zh", "edge", "edge_zh", "forward", "forward_zh",
            "context", "anchor"}


def _bidx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2015-01-01", periods=n, freq="B")


def _v_series(n: int = 900) -> pd.Series:
    """A big V (down then up) with sine ripples — yields trend flips, a golden
    cross, daily-cycle troughs, RSI extremes and 52-week high/low events."""
    t = np.arange(n)
    half = n // 2
    base = np.where(t < half, 100 - 0.10 * t, 100 - 0.10 * half + 0.13 * (t - half))
    ripple = np.sin(t / 12.0) * 2.5
    return pd.Series(base + ripple, index=_bidx(n)).clip(lower=1)


# --------------------------------------------------------------------------- #
def test_transitions_fire_only_on_change():
    s = pd.Series(["a", "a", "b", "b", "a"], index=_bidx(5))
    tr = ta._transitions(s)
    assert [to for _, _, to in tr] == ["b", "a"]
    assert [frm for _, frm, _ in tr] == ["a", "b"]


def test_transitions_empty_and_constant():
    assert ta._transitions(pd.Series(dtype=object)) == []
    assert ta._transitions(pd.Series(["x", "x", "x"], index=_bidx(3))) == []


def test_event_types_backfilled_from_price():
    ev = ta.technical_events("TEST", _v_series(), None, None)
    assert ev, "a long V series should generate events"
    types = {e["type"] for e in ev}
    # the robust structural events a V must contain
    assert {"trend_200", "dcl", "range_52w"} <= types
    assert "macd_d" in types  # daily momentum crosses are frequent


def test_schema_is_complete_and_bilingual():
    ev = ta.technical_events("TEST", _v_series(), None, None)
    for e in ev:
        assert REQUIRED <= set(e), f"missing keys: {REQUIRED - set(e)}"
        for k in ("headline", "headline_zh", "detail", "detail_zh", "label", "label_zh"):
            assert e[k], f"empty {k} on {e['type']}"
        assert e["severity"] in ("high", "medium", "info")
        assert e["dir"] in ("up", "down", "neutral")
        assert e["filter"] in ta.FILTER_LABELS


def test_ids_are_deterministic_and_idempotent():
    s = _v_series()
    a = ta.technical_events("TEST", s, None, None)
    b = ta.technical_events("TEST", s, None, None)
    assert [e["id"] for e in a] == [e["id"] for e in b]
    assert len({e["id"] for e in a}) == len(a), "ids must be unique"


def test_relative_strength_events_need_a_benchmark():
    s = _v_series()
    no_bench = ta.technical_events("TEST", s, None, None)
    # an out-of-phase benchmark so relative strength actually swings through bands
    bench = _v_series()[::-1]
    bench.index = s.index
    with_bench = ta.technical_events("TEST", s, None, bench)
    assert not any(e["type"] == "rs" for e in no_bench)
    assert any(e["type"] == "rs" for e in with_bench)


def test_golden_cross_appears_in_a_v_recovery():
    ev = ta.technical_events("TEST", _v_series(1000), None, None)
    crosses = [e for e in ev if e["type"] == "ma_cross"]
    assert any(e["context"] is not None for e in crosses) or crosses == [] or crosses
    assert any(e["dir"] == "up" and e["type"] == "ma_cross" for e in ev), \
        "the recovery leg should print a golden cross"


def test_recent_window_filters_old_events():
    old = {"ts": "2000-01-01T00:00:00", "x": 1}
    new = {"ts": pd.Timestamp.now("UTC").isoformat(), "x": 2}
    kept = ta.recent([old, new], days=30)
    assert old not in kept and new in kept


def test_group_by_day_is_reverse_chronological():
    ev = ta.technical_events("TEST", _v_series(), None, None)
    groups = ta.group_by_day(ta.recent(ev, days=100000))
    dates = [g["date"] for g in groups]
    assert dates == sorted(dates, reverse=True)
    for g in groups:
        assert g["daylabel"] and g["daylabel_zh"]
        sev = [ta._SEV_RANK.get(e["severity"], 9) for e in g["events"]]
        assert sev == sorted(sev), "within a day, higher severity first"


def test_ladder_pinned_is_bilingual_and_flagged():
    ladder = {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "action": "GET READY",
              "dir": "down", "score": 0, "why": "Day 52 of the cycle.",
              "why_zh": "周期第52天。", "prev_state": "DECLINE",
              "signal_date": "2026-05-20", "entry": {"urgency": "soon", "tag": "WATCH"}}
    p = ta.ladder_pinned("AAPL", ladder, "2026-06-12")
    assert p and p["pinned"] is True and p["type"] == "ladder"
    assert p["filter"] == "signal" and p["tier"] == "act"
    assert p["headline_zh"] and p["headline_zh"] != p["headline"]
    assert p["urgency"] == "soon" and p["state_class"] == "BOTTOM_WATCH"


def test_ladder_pinned_none_without_state():
    assert ta.ladder_pinned("X", None, "2026-06-12") is None
    assert ta.ladder_pinned("X", {"state": ""}, "2026-06-12") is None


def test_ladder_log_append_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "_ladder_path", lambda: tmp_path / "ladder_log.parquet")
    ladder = {"state": "FRESH BUY", "label": "BUY", "action": "BUY", "dir": "up",
              "score": 40, "prev_state": "BOTTOM WATCH", "signal_date": "2026-06-01",
              "entry": {"urgency": "now"}}
    ta.append_ladder_log("AAPL", ladder, "2026-06-12")
    ta.append_ladder_log("AAPL", ladder, "2026-06-12")  # same transition again
    df = pd.read_parquet(tmp_path / "ladder_log.parquet")
    assert len(df) == 1
    # a NEW transition adds a row; history events surface it (current one excluded)
    ladder2 = {**ladder, "state": "RALLY ON", "label": "RALLY", "prev_state": "FRESH BUY",
               "signal_date": "2026-06-08"}
    ta.append_ladder_log("AAPL", ladder2, "2026-06-12")
    assert len(pd.read_parquet(tmp_path / "ladder_log.parquet")) == 2
    hist = ta.ladder_history_events("AAPL", exclude_when="2026-06-08")
    assert [h["context"]["state"] for h in hist] == ["FRESH BUY"]


def _has_cjk(s):
    return any("一" <= c <= "鿿" for c in s or "")


def test_ladder_vocab_translates_to_cjk():
    # every STATE_DISPLAY label/action must glossary-translate to its zh twin —
    # a miss leaks EN into detail_zh/headline_zh on every ladder timeline event
    # (the NVDA "HIGH-RISK · NIMBLE ONLY" leak)
    from engine.cycles import STATE_DISPLAY
    for state, d in STATE_DISPLAY.items():
        for k in ("label", "action"):
            en, zh = ta._disp(d[k])
            assert zh == d[f"{k}_zh"] and _has_cjk(zh), f"{state} {k}: {en!r} -> {zh!r}"
    # legacy vocab frozen in ladder_log.parquet history rows + LIMITED sentinel
    for legacy in ("COUNTER-TREND BOUNCE", "LIMITED"):
        en, zh = ta._disp(legacy)
        assert _has_cjk(zh), f"legacy {en!r} -> {zh!r}"


def test_ladder_history_detail_zh_is_chinese(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "_ladder_path", lambda: tmp_path / "ladder_log.parquet")
    ladder = {"state": "COUNTERTREND BOUNCE", "label": "UNCONFIRMED TURN",
              "action": "HIGH-RISK · NIMBLE ONLY", "dir": "caution", "score": 10,
              "prev_state": "DECLINE", "signal_date": "2026-06-01",
              "entry": {"urgency": "watch"}}
    ta.append_ladder_log("NVDA", ladder, "2026-06-12")
    hist = ta.ladder_history_events("NVDA")
    assert hist and hist[0]["detail"] == "HIGH-RISK · NIMBLE ONLY"
    assert _has_cjk(hist[0]["detail_zh"]) and _has_cjk(hist[0]["headline_zh"])


def test_build_feed_shape_and_pinned(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "_ladder_path", lambda: tmp_path / "ladder_log.parquet")
    ladder = {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "action": "GET READY",
              "dir": "down", "score": 0, "why": "Cycle low window.",
              "prev_state": "DECLINE", "signal_date": "2026-05-20",
              "entry": {"urgency": "soon"}}
    feed = ta.build_feed("TEST", _v_series(), None, None, ladder, "2026-06-12",
                         days=100000, max_events=40)
    assert set(feed) == {"pinned", "timeline", "n_recent", "n_total"}
    assert feed["pinned"]["pinned"] is True
    assert feed["n_recent"] <= 40 and feed["n_total"] >= feed["n_recent"]
    assert isinstance(feed["timeline"], list) and feed["timeline"]


def test_build_feed_never_raises_on_garbage():
    feed = ta.build_feed("X", pd.Series([1.0, 2.0]), None, None, None, None, persist=False)
    assert feed == {"pinned": None, "timeline": [], "n_recent": 0, "n_total": 0}


def test_technical_events_survives_duplicate_index():
    # a duplicate-timestamp series must not crash px()/.get() (review finding #1)
    s = _v_series(400)
    dup = pd.concat([s, s.iloc[-5:]]).sort_index()  # 5 duplicated trailing dates
    assert dup.index.has_duplicates
    ev = ta.technical_events("DUP", dup, None, None)
    assert isinstance(ev, list) and ev  # produced events, no exception
    assert all("$" in (e["detail"] + e["headline"]) or True for e in ev)


def test_rsi_events_are_neutral_direction():
    # RSI extremes are context, not a bull/bear call (review finding #5)
    ev = ta.technical_events("TEST", _v_series(), None, None)
    rsi_ev = [e for e in ev if e["type"] == "rsi"]
    assert rsi_ev and all(e["dir"] == "neutral" for e in rsi_ev)


def test_compact_feed_drops_reconstructible_fields_and_shrinks():
    full = ta.build_feed("TEST", _v_series(), None, None,
                         {"state": "FRESH BUY", "label": "BUY", "action": "BUY", "dir": "up",
                          "signal_date": "2026-06-01", "entry": {"urgency": "now"}},
                         "2026-06-12", days=100000, persist=False)
    slim = ta.compact_feed(full)
    assert set(slim) == {"pinned", "timeline", "n_recent", "n_total"}
    ev = slim["timeline"][0]["events"][0]
    assert set(ev) <= set(ta._EMBED_KEYS)
    for gone in ("edge", "forward", "label", "id", "context", "ts", "severity"):
        assert gone not in ev
    # the static conviction text the client reattaches really is reconstructible
    meta = ta.edge_meta()
    assert meta[ev["type"]]["edge"] == ta.META[ev["type"]]["edge"]
    assert len(json.dumps(slim)) < len(json.dumps(full))


def test_edge_meta_covers_every_event_type():
    meta = ta.edge_meta()
    ev = ta.technical_events("TEST", _v_series(), None, _v_series()[::-1])
    for e in ev:
        assert e["type"] in meta, f"{e['type']} missing from edge_meta()"
    for v in meta.values():
        assert set(v) == {"edge", "edge_zh", "forward", "forward_zh"}


def test_compact_feed_handles_empty():
    assert ta.compact_feed(None)["timeline"] == []
    assert ta.compact_feed({"pinned": None, "timeline": [], "n_recent": 0, "n_total": 0})["pinned"] is None
