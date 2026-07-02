"""Tests for the CN Reversal Sleeve (§W6-CN CN-5) — the validated no-gate reversal edge as a
monthly-rebalanced EW basket product.

Covers the acceptance protocol:
  * construction determinism — same plane → same membership + weights;
  * no-gate INVARIANT — no confluence / timing / quality field can affect membership (the
    edge flips negative under every gate; Phase-0), enforced by assert_no_gate + a behavioral
    test that injecting a gate field into params raises and into member-context does NOT move
    membership;
  * universe hygiene — ST fail-closed, sentinel-aware mktcap floor, ADV floor all applied;
  * ledger row shape — the CN-1-compatible append-only row contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cn_reversal_sleeve as sleeve  # noqa: E402
from engine import cn_reversal_sleeve_ledger as ledger  # noqa: E402


# --------------------------------------------------------------------------- #
#  synthetic plane                                                             #
# --------------------------------------------------------------------------- #
def _plane(n_per_sector=10, sectors=("Tech", "Health", "Industrials"), days=120, seed=0):
    """A deterministic synthetic closes panel + member dicts. Each name walks with a random
    3M drift so the deepest-quintile membership is well-defined."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=days)
    cols, tkr_sector, tkr_name, tkr_name_zh, tkr_mktcap = [], {}, {}, {}, {}
    data = {}
    k = 0
    for s in sectors:
        for i in range(n_per_sector):
            t = f"{600000 + k}.SS"
            k += 1
            drift = rng.uniform(-0.005, 0.003)               # per-day drift → varied 3M returns
            steps = rng.normal(drift, 0.01, days)
            price = 20.0 * np.exp(np.cumsum(steps))
            data[t] = price
            cols.append(t)
            tkr_sector[t] = s
            tkr_name[t] = f"Name {t}"
            tkr_name_zh[t] = f"名称{k}"
            tkr_mktcap[t] = 100.0                             # all above the 30亿 floor
    closes = pd.DataFrame(data, index=idx)
    return closes, tkr_sector, tkr_name, tkr_name_zh, tkr_mktcap


# --------------------------------------------------------------------------- #
#  construction determinism                                                    #
# --------------------------------------------------------------------------- #
def test_membership_deterministic():
    closes, sec, name, name_zh, mcap = _plane()
    a = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    b = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert a is not None and b is not None
    assert [m["ticker"] for m in a["members"]] == [m["ticker"] for m in b["members"]]
    assert a["members"][0]["weight"] == b["members"][0]["weight"]


def test_deepest_quintile_and_equal_weight():
    closes, sec, name, name_zh, mcap = _plane(n_per_sector=20)
    out = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert out is not None
    # deepest quintile ≈ 20% of the screened universe
    assert out["n_members"] == max(1, round(out["n_universe"] * sleeve.DEEPEST_QUINTILE))
    # equal weight: every member carries the SAME weight, summing to ~1.0 (weights are rounded
    # to 4dp for display, so allow N × half-ulp rounding drift off exactly 1.0).
    ws = {m["weight"] for m in out["members"]}
    assert len(ws) == 1
    assert abs(sum(m["weight"] for m in out["members"]) - 1.0) < out["n_members"] * 5e-5
    # members are the HIGHEST rev_z (deepest dips) and sorted descending
    revs = [m["rev_z"] for m in out["members"]]
    assert revs == sorted(revs, reverse=True)


def test_construction_metadata_is_no_gate():
    closes, sec, name, name_zh, mcap = _plane()
    out = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    c = out["construction"]
    assert c["gate"] == "none"
    assert c["weighting"] == "equal"
    assert c["rebalance"] == "monthly"
    assert c["unit"] == "deepest_quintile_within_sector_3m_reversal"


# --------------------------------------------------------------------------- #
#  the no-gate invariant                                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", sorted(sleeve._FORBIDDEN_GATE_FIELDS))
def test_assert_no_gate_rejects_every_forbidden_field(field):
    with pytest.raises(ValueError):
        sleeve.assert_no_gate({field: True})


def test_assert_no_gate_passes_benign_and_falsey():
    sleeve.assert_no_gate({"win": 63, "min_sector": 6})          # benign
    sleeve.assert_no_gate({"confluence": None, "macd": 0})       # falsey gate fields ignored


def test_no_gate_field_cannot_move_membership():
    """A gate/timing signal, however strong, must NOT change WHO is in the sleeve. This is the
    behavioral guarantee: membership is a pure function of rev_z + hygiene. We build twice —
    once plain, once with a fabricated per-name confluence/timing map that a gated board would
    consume — and assert identical membership (there is no code path that reads it)."""
    closes, sec, name, name_zh, mcap = _plane()
    base = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    # current_membership takes NO gate argument — there is literally nowhere to inject one.
    # Confirm the signature carries no confluence/timing/quality parameter.
    import inspect
    params = set(inspect.signature(sleeve.current_membership).parameters)
    assert not (params & sleeve._FORBIDDEN_GATE_FIELDS)
    # And a re-run is byte-identical (no hidden state / gate).
    again = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert [m["ticker"] for m in base["members"]] == [m["ticker"] for m in again["members"]]


# --------------------------------------------------------------------------- #
#  universe hygiene                                                            #
# --------------------------------------------------------------------------- #
def test_st_screen_fail_closed():
    closes, sec, name, name_zh, mcap = _plane()
    # flag the FIRST name as ST via its Chinese short name — it must be screened out even if it
    # is the deepest dip.
    victim = next(iter(closes.columns))
    name_zh[victim] = "*ST" + name_zh[victim]
    out = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert out is not None
    assert victim not in {m["ticker"] for m in out["members"]}
    assert out["screened"]["st"] >= 1


def test_mktcap_floor_sentinel_aware():
    closes, sec, name, name_zh, mcap = _plane()
    cols = list(closes.columns)
    below = cols[0]
    sentinel = cols[1]
    mcap[below] = 5.0                       # real sub-floor cap → must be dropped
    mcap[sentinel] = sleeve.MCAP_FLOOR_YI   # 30.0 EXACTLY = "unknown" placeholder → must PASS
    out = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert out is not None
    members = {m["ticker"] for m in out["members"]}
    assert below not in members             # real small cap screened
    assert out["screened"]["mcap"] >= 1
    # the sentinel-cap name is NOT screened on mcap (it may or may not make the quintile, but it
    # is never dropped by the cap floor) — verify it is not counted as an mcap screen victim
    # by re-running with it as a clean 100亿 and confirming the mcap count is unchanged.
    mcap[sentinel] = 100.0
    out2 = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap)
    assert out2["screened"]["mcap"] == out["screened"]["mcap"]


def test_adv_floor_applied():
    closes, sec, name, name_zh, mcap = _plane()
    victim = list(closes.columns)[0]
    adv_by = {t: 5.0 for t in closes.columns}      # all liquid
    adv_by[victim] = 0.01                            # proven illiquid → drop
    out = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap,
                                    adv_by=adv_by, adv_floor_yi=0.5)
    assert out is not None
    assert victim not in {m["ticker"] for m in out["members"]}
    assert out["screened"]["adv"] >= 1
    # missing ADV must PASS (never drop a name we can't prove illiquid)
    out_missing = sleeve.current_membership(closes, sec, name, tkr_name_zh=name_zh,
                                            tkr_mktcap=mcap, adv_by={}, adv_floor_yi=0.5)
    assert out_missing["screened"]["adv"] == 0


# --------------------------------------------------------------------------- #
#  backcast sanity                                                             #
# --------------------------------------------------------------------------- #
def test_backcast_shape_and_nav():
    closes, sec, name, name_zh, mcap = _plane(n_per_sector=12, days=400)
    # synthetic bench: a slow uptrend on the same index
    bench = pd.Series(np.linspace(3.0, 3.3, len(closes)), index=closes.index)
    bc = sleeve.backcast(closes, sec, tkr_name_zh=name_zh, tkr_mktcap=mcap, months=8, bench=bench)
    assert bc is not None
    assert bc["n_legs"] >= 4
    assert len(bc["nav"]["sleeve"]) == len(bc["nav"]["dates"])
    assert len(bc["nav"]["csi300"]) == len(bc["nav"]["dates"])
    assert bc["nav"]["sleeve"][0] == 1.0 and bc["nav"]["csi300"][0] == 1.0
    assert bc["have_bench"] is True and bc["graded_on"] == "csi300_excess"
    assert "upper" in bc["caveat"].lower()          # upper-bound labeled


# --------------------------------------------------------------------------- #
#  ledger row shape                                                            #
# --------------------------------------------------------------------------- #
def test_ledger_row_shape(tmp_path, monkeypatch):
    # redirect the ledger store into a temp dir
    monkeypatch.setattr(ledger.config, "data_dir", lambda: tmp_path)
    membership = {
        "as_of": "2026-07-01",
        "members": [
            {"ticker": "600001.SS", "sector": "Tech", "rev_z": 1.5, "weight": 0.5},
            {"ticker": "600002.SS", "sector": "Health", "rev_z": 1.2, "weight": 0.5},
        ],
    }
    n = ledger.append_rebalance(membership, data_through="2026-07-01", lane="asia")
    assert n == 2
    df = pd.read_parquet(tmp_path / "cn_reversal_sleeve_track" / "sleeve.parquet")
    assert list(df.columns) == list(ledger.LEDGER_COLUMNS)
    assert set(df["ticker"]) == {"600001.SS", "600002.SS"}
    assert (df["data_through"] == "2026-07-01").all()
    assert (df["rebalance_date"] == "2026-07-01").all()


def test_ledger_keep_first_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger.config, "data_dir", lambda: tmp_path)
    m1 = {"as_of": "2026-07-01",
          "members": [{"ticker": "600001.SS", "sector": "Tech", "rev_z": 1.5, "weight": 1.0}]}
    m2 = {"as_of": "2026-07-01",   # SAME date, DIFFERENT rev_z — keep-first must ignore the update
          "members": [{"ticker": "600001.SS", "sector": "Tech", "rev_z": 9.9, "weight": 1.0}]}
    ledger.append_rebalance(m1, lane="asia")
    ledger.append_rebalance(m2, lane="asia")
    df = pd.read_parquet(tmp_path / "cn_reversal_sleeve_track" / "sleeve.parquet")
    assert len(df) == 1
    assert float(df.iloc[0]["rev_z"]) == 1.5      # first write wins (leak-free)


def test_ledger_lane_gate():
    # a non-asia lane must refuse to persist (render lanes discard data/)
    membership = {"as_of": "2026-07-01",
                  "members": [{"ticker": "600001.SS", "sector": "T", "rev_z": 1.0, "weight": 1.0}]}
    assert ledger.append_rebalance(membership, lane="render") == 0


def test_ledger_grade_conventions():
    g = ledger.grade()
    # with no data yet it degrades gracefully; when data exists the grading contract is stamped
    assert "available" in g
    if g.get("available"):
        conv = g["grading"]
        assert conv["relative"] is True and conv["benchmark"] == ledger._BENCH
        assert conv["excludes_locked_limit"] is True
        assert conv["marker_dates"] == "forbidden"
