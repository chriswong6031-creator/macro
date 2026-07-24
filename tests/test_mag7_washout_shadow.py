"""MWR-W1 — shadow book, confluence sidecar, world-state lobe (pure accrual).

Synthetic-store tests mirroring test_mag7_washout's root=tmp convention. The
nightly-sole-advancer sentinel is exercised via COLLECT_LANE (ledger_lane)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.mag7_washout import M7
from engine.mag7_washout_shadow import BASELINE_FWD63, SCHEMA, update

M7SET = list(M7)


def _write_members(root: Path, closes: pd.Series) -> None:
    d = root / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"open": closes, "high": closes * 1.01,
                       "low": closes * 0.99, "close": closes, "volume": 1e6})
    for t in M7SET:
        df.to_parquet(d / f"{t}.parquet")


def _ramp_series(n: int = 400, recover_at: int = 300) -> pd.Series:
    """Flat-ish walk, then a strong +1.2%/session recovery leg from recover_at —
    entries taken inside the leg grade HIT (ret63 ≈ +[large], adverse ≈ 0)."""
    rng = np.random.default_rng(1)
    px = list(100 * np.cumprod(1 + rng.normal(0, 0.002, recover_at)))
    for i in range(n - recover_at):
        px.append(px[-1] * 1.012)
    return pd.Series(px, index=pd.bdate_range("2024-01-02", periods=n))


def _seed_trigger(root: Path, when: str, extra: dict | None = None) -> None:
    base = root / "mag7_washout"
    base.mkdir(parents=True, exist_ok=True)
    row = {"tf": "2W_stochrsi", "date": when, "as_of": when, **(extra or {})}
    with (base / "triggers.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _nightly(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")


# ── shadow book ──────────────────────────────────────────────────────────────

def test_matured_book_rows_and_grades(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _ramp_series()
    _write_members(tmp_path, s)
    trigger_date = str(s.index[310].date())  # inside the recovery leg, >63td left
    _seed_trigger(tmp_path, trigger_date, {"policy": "cutting", "midterm_yr": False})
    out = update(root=tmp_path, gate={"as_of": str(s.index[-1].date())})
    assert out is not None
    book = tmp_path / "mag7_washout" / "shadow_book.jsonl"
    rows = [json.loads(l) for l in book.read_text().splitlines()]
    assert len(rows) == 1 + len(M7SET)  # EW + 7 members
    assert {r["instrument"] for r in rows} == {"EW", *M7SET}
    for r in rows:
        assert r["schema"] == SCHEMA
        assert r["trigger_date"] == trigger_date
        assert r["entry_date"] > trigger_date          # next-session close basis
        assert r["ret63"] > BASELINE_FWD63             # ramp leg → HIT territory
        assert r["adverse63"] > -10
        assert r["grade"] == "HIT"
        assert r["policy"] == "cutting"                # env tags carried
        assert r["gauntlet_row"] is (r["instrument"] == "EW")


def test_book_append_is_idempotent(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _ramp_series()
    _write_members(tmp_path, s)
    _seed_trigger(tmp_path, str(s.index[310].date()))
    update(root=tmp_path, gate={})
    book = tmp_path / "mag7_washout" / "shadow_book.jsonl"
    n = len(book.read_text().splitlines())
    st = update(root=tmp_path, gate={})
    assert len(book.read_text().splitlines()) == n
    assert st["book"]["rows"] == n and st["book"]["gauntlet_rows"] == 1


def test_sentinel_off_appends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    s = _ramp_series()
    _write_members(tmp_path, s)
    _seed_trigger(tmp_path, str(s.index[310].date()))
    out = update(root=tmp_path, gate={})
    assert out is not None
    assert not (tmp_path / "mag7_washout" / "shadow_book.jsonl").exists()


def test_unmatured_trigger_is_open_position(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _ramp_series()
    _write_members(tmp_path, s)
    _seed_trigger(tmp_path, str(s.index[-20].date()))  # only ~19 sessions of forward tape
    out = update(root=tmp_path, gate={})
    assert not (tmp_path / "mag7_washout" / "shadow_book.jsonl").exists()
    assert len(out["open_positions"]) == 1 + len(M7SET)
    p0 = out["open_positions"][0]
    assert 0 < p0["sessions_held"] < 63 and "mtm_pct" in p0


# ── prophet confluence sidecar ───────────────────────────────────────────────

def test_confluence_stamps_only_m7_and_dedups(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _ramp_series()
    _write_members(tmp_path, s)
    snapdir = tmp_path / "us_board_ledger"
    snapdir.mkdir(parents=True)
    snap = {"as_of": "2026-07-24", "rank_by": "x", "lanes": {
        "entry_open": [{"ticker": "AAPL", "lane": "entry_open"},
                       {"ticker": "HWM", "lane": "entry_open"}],
        "setting_up": [{"ticker": "TSLA", "lane": "setting_up"}]}}
    (snapdir / "snapshots_v2.jsonl").write_text(json.dumps(snap) + "\n")
    gate = {"state": "idle", "armed": False, "members_washed": 0,
            "basket": {"stoch2w_k": 55.1}}
    out = update(root=tmp_path, gate=gate)
    assert out["confluence_stamped"] == 2  # AAPL + TSLA, never HWM
    side = tmp_path / "mag7_washout" / "prophet_confluence.jsonl"
    rows = [json.loads(l) for l in side.read_text().splitlines()]
    assert {r["ticker"] for r in rows} == {"AAPL", "TSLA"}
    assert all(r["mwr_state"] == "idle" and r["stoch2w_k"] == 55.1 for r in rows)
    out2 = update(root=tmp_path, gate=gate)   # same snapshot → no re-stamp
    assert out2["confluence_stamped"] == 0
    assert len(side.read_text().splitlines()) == 2


# ── world-state lobe ─────────────────────────────────────────────────────────

def test_world_state_lobe_composes_and_nulls(tmp_path):
    from engine.neuralweb.world_state import _compose_mag7_washout
    null = _compose_mag7_washout(root=tmp_path)
    assert null["display_only"] is True and null["is_context_only"] is True
    assert null["state"] is None
    base = tmp_path / "data" / "mag7_washout"
    base.mkdir(parents=True)
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-07-23", "state": "idle", "armed": False,
        "members_washed": 0, "basket": {"stoch2w_k": 55.1, "stoch2w_d": 56.4}}))
    (base / "triggers.jsonl").write_text(
        json.dumps({"tf": "2W_stochrsi", "date": "2026-04-10"}) + "\n")
    block = _compose_mag7_washout(root=tmp_path)
    assert block["state"] == "idle" and block["stoch2w_k"] == 55.1
    assert block["last_trigger"] == {"tf": "2W_stochrsi", "date": "2026-04-10"}
    assert block["display_only"] is True and block["is_context_only"] is True


def test_fail_open_without_stores(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    out = update(root=tmp_path, gate={})
    assert out is not None and out["book"]["rows"] == 0


# ── notify source (f) — MWR trigger operator ping (§7 W1b) ──────────────────

def test_notify_source_f_detects_dedups_and_copy(tmp_path, monkeypatch):
    import scripts.notify_turn_events as NTE
    trig = tmp_path / "triggers.jsonl"
    trig.write_text(json.dumps({"tf": "2W_stochrsi", "date": "2026-07-20",
                                "stoch2w_k": 14.2, "regime": "cutting"}) + "\n")
    monkeypatch.setattr(NTE, "_MWR_TRIGGERS_PATH", trig)
    state: dict = {}
    res = NTE._detect_mwr_trigger(state, "2026-07-22")
    assert len(res) == 1
    subject, msg = res[0]
    assert subject == "2W_stochrsi|2026-07-20"
    # Amendment 2: regime clear → actionable copy; still never buy/sell words
    assert "TRIGGERED" in msg and "ACTIONABLE" in msg and "kill-switch" in msg
    assert "buy" not in msg.lower() and "sell" not in msg.lower()
    # once-ever dedup (bar-date keyed)
    NTE._mark_fired(state, "mwr_trigger", subject, "2026-07-20")
    assert NTE._detect_mwr_trigger(state, "2026-07-22") == []
    # stale rows (>5 calendar days) never replay on later runs
    assert NTE._detect_mwr_trigger({}, "2026-08-30") == []


def test_notify_veto_and_unknown_copy(tmp_path, monkeypatch):
    import scripts.notify_turn_events as NTE
    trig = tmp_path / "triggers.jsonl"
    rows = [{"tf": "2W_stochrsi", "date": "2026-07-20", "regime": "hike_accel"},
            {"tf": "3D_rsimacd", "date": "2026-07-21"}]  # no regime tag
    trig.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(NTE, "_MWR_TRIGGERS_PATH", trig)
    res = dict(NTE._detect_mwr_trigger({}, "2026-07-22"))
    veto_msg = res["2W_stochrsi|2026-07-20"]
    assert "VETOED" in veto_msg and "accelerating-tightening" in veto_msg
    assert "ACTIONABLE" not in veto_msg
    unknown_msg = res["3D_rsimacd|2026-07-21"]
    assert "Regime tag unavailable" in unknown_msg and "manually" in unknown_msg
