"""W3-C4 — dollar three-prong tests (REER N=1 CONFIRMED, dollar-lean DISPLAY chip,
CNH-basis INVERTED graveyard) + the ledger-consistency / not-wired guarantees.

The C4 channel graded:
  * c4_reer_value  — CONFIRMED on a SEPARATE single-trial budget (N=1). VERDICT is
    RECORDED but NO scorer consumes it this wave (P1: no consumer wiring).
  * c4b dollar_desk lean → a DISPLAY-ONLY bilingual context chip on dollar-sensitive US
    sectors (P2). Honest labels, t() dual-span in content, fail-soft.
  * c4_cnh_basis   — INVERTED (residual predicts the WRONG sign vs the existing raw usdcnh
    RORO leg). Graveyard, kill=True, weight 0 → NOT wired (P3).

These lock in:
  1. REER builder causality — a spike on the LAST (unlagged) REER bar must not move the
     as-of value factor (publication-lag + trailing windows → no look-ahead);
  2. CNH builder causality — the basis-z de-risk position acts next-bar (shift(1)); a spike
     on the final bar cannot change the already-realized strategy returns;
  3. display chip — honest headwind/tailwind labeling from the MEASURED lean, bilingual
     fields present, and fail-soft (unmapped sector / missing data → None);
  4. ledger consistency — the shipped C4 rows match the deterministic re-grade verdicts,
     the CNH graveyard row is weight 0 via intl_feed (nothing sizes off it), and the
     CONFIRMED REER row is surfaced at its cap by the registry but no scorer imports the
     feed (the not-wired guarantee).

Run: python -m pytest tests/test_c4_dollar.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.build_site as bsite  # noqa: E402
import scripts.c4_cnh_basis as cnh  # noqa: E402
import scripts.c4_reer_value as reer  # noqa: E402
from engine import intl_claims  # noqa: E402
from engine import intl_feed as feed  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. REER builder causality — no look-ahead through the value factor
# --------------------------------------------------------------------------- #
def _synth_reer(n: int = 400, seed: int = 7):
    """A monthly REER + a daily index on which _value_factor is evaluated."""
    rng = np.random.default_rng(seed)
    m_idx = pd.date_range("2010-01-31", periods=n, freq="ME")
    reer_s = pd.Series(100.0 * (1 + rng.normal(0, 0.01, n)).cumprod(), index=m_idx)
    d_idx = pd.date_range("2010-01-01", periods=n * 21, freq="B")
    return reer_s, d_idx


def test_reer_value_no_lookahead():
    """The publication lag (PUB_LAG_D) + trailing windows mean the LAST monthly REER print
    cannot influence any already-visible daily value. Perturbing the final REER bar must
    leave every value observation strictly before its publication date UNCHANGED."""
    reer_s, d_idx = _synth_reer()
    base = reer._value_factor(reer_s, d_idx)
    r2 = reer_s.copy()
    r2.iloc[-1] = r2.iloc[-1] * 1.30                       # absurd spike on the final print
    pert = reer._value_factor(r2, d_idx)
    # any daily value dated at least PUB_LAG_D before the perturbed month cannot have seen it
    cutoff = reer_s.index[-1] - pd.Timedelta(days=reer.PUB_LAG_D + 5)
    a = base[base.index <= cutoff].dropna()
    b = pert.reindex(a.index)
    assert np.allclose(a.to_numpy(), b.to_numpy(), equal_nan=True)


def test_reer_value_sign_cheap_is_bullish():
    """A cheap dollar (REER far BELOW its long-run mean) must produce a POSITIVE value
    score (bullish-USD), and a rich dollar a negative one — the signed convention the
    de-risk direction depends on."""
    d_idx = pd.date_range("2005-01-01", periods=1800, freq="B")
    m_idx = pd.date_range("2005-01-31", periods=90, freq="ME")
    # a REER that ramps UP then collapses: the tail is 'cheap' vs its trailing mean
    lvl = np.concatenate([np.linspace(120, 120, 60), np.linspace(120, 80, 30)])
    reer_s = pd.Series(lvl, index=m_idx)
    v = reer._value_factor(reer_s, d_idx).dropna()
    assert v.iloc[-1] > 0                                   # cheap tail → bullish-USD value


def test_reer_builder_contract():
    """The harness builder returns the required keys or a fail-soft {'error': ...}."""
    out = reer.builder({"id": "c4_reer_value"})
    assert isinstance(out, dict)
    if "error" not in out:
        assert {"signal", "strat_ret", "bench_ret", "target_dd", "basis"} <= set(out)


# --------------------------------------------------------------------------- #
# 2. CNH builder causality — the de-risk position acts next-bar
# --------------------------------------------------------------------------- #
def test_cnh_basis_z_causal():
    """_z uses only trailing windows: a spike on the FINAL bar changes only that bar's z,
    never a prior one (no look-ahead in the basis z-score)."""
    idx = pd.date_range("2015-01-01", periods=500, freq="B")
    s = pd.Series(np.random.default_rng(1).normal(0, 1, 500).cumsum(), index=idx)
    z0 = cnh._z(s)
    s2 = s.copy()
    s2.iloc[-1] = s2.iloc[-1] + 20.0
    z1 = cnh._z(s2)
    assert np.allclose(z0.iloc[:-1].to_numpy(), z1.iloc[:-1].to_numpy(), equal_nan=True)


def test_cnh_builder_contract():
    out = cnh.builder({"id": "c4_cnh_basis"})
    assert isinstance(out, dict)
    if "error" not in out:
        assert {"signal", "strat_ret", "bench_ret", "target_dd", "basis"} <= set(out)
        # the deciding orthogonality basis is the EXISTING raw usdcnh leg (exactly one)
        assert isinstance(out["basis"], list) and len(out["basis"]) == 1


# --------------------------------------------------------------------------- #
# 3. display chip — honest labels, bilingual, fail-soft (P2)
# --------------------------------------------------------------------------- #
def _write_latest(tmp_path: Path, dollar_desk: dict | None) -> Path:
    d = tmp_path / "forex"
    d.mkdir(parents=True, exist_ok=True)
    payload = {} if dollar_desk is None else {"dollar_desk": dollar_desk}
    (d / "latest.json").write_text(json.dumps(payload))
    return tmp_path


def test_chip_headwind_when_dollar_supportive(tmp_path, monkeypatch):
    """A dollar-SUPPORTIVE backdrop (lean_net >= 2) on a dollar-sensitive sector renders a
    HEADWIND chip with the correct tone + bilingual lean text."""
    monkeypatch.setattr(bsite.config, "data_dir", lambda: tmp_path)
    _write_latest(tmp_path, {"lean": "dollar-supportive backdrop",
                             "lean_zh": "偏多美元背景", "lean_net": 3, "lean_n": 3})
    ctx = bsite._dollar_context(tmp_path, "XLE")
    assert ctx is not None
    assert ctx["tone"] == "headwind" and ctx["arrow"] == "▼"
    assert ctx["chip_en"] == "Dollar headwind" and ctx["chip_zh"] == "美元逆风"
    assert ctx["lean_zh"] == "偏多美元背景"                 # bilingual carried through
    assert ctx["note_en"] and ctx["note_zh"]               # both languages present


def test_chip_tailwind_when_dollar_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(bsite.config, "data_dir", lambda: tmp_path)
    _write_latest(tmp_path, {"lean": "dollar-soft backdrop",
                             "lean_zh": "偏空美元背景", "lean_net": -3, "lean_n": 3})
    ctx = bsite._dollar_context(tmp_path, "XLK")
    assert ctx is not None and ctx["tone"] == "tailwind" and ctx["arrow"] == "▲"


def test_chip_neutral_when_mixed(tmp_path, monkeypatch):
    monkeypatch.setattr(bsite.config, "data_dir", lambda: tmp_path)
    _write_latest(tmp_path, {"lean": "mixed backdrop", "lean_zh": "分化背景",
                             "lean_net": 0, "lean_n": 2})
    ctx = bsite._dollar_context(tmp_path, "XLB")
    assert ctx is not None and ctx["tone"] == "neutral" and ctx["arrow"] == "◇"


def test_chip_failsoft_unmapped_sector(tmp_path, monkeypatch):
    """A non-dollar-sensitive sector (not in the map) → None (no chip), never a crash."""
    monkeypatch.setattr(bsite.config, "data_dir", lambda: tmp_path)
    _write_latest(tmp_path, {"lean": "dollar-supportive backdrop", "lean_net": 3})
    assert bsite._dollar_context(tmp_path, "XLF") is None   # financials not in the map
    assert bsite._dollar_context(tmp_path, "XLU") is None   # utilities not in the map


def test_chip_failsoft_missing_data(tmp_path, monkeypatch):
    """Missing latest.json or no lean → None (fail-soft), even for a mapped sector."""
    monkeypatch.setattr(bsite.config, "data_dir", lambda: tmp_path)
    assert bsite._dollar_context(tmp_path, "XLE") is None   # no latest.json at all
    _write_latest(tmp_path, {})                             # dollar_desk absent
    assert bsite._dollar_context(tmp_path, "XLE") is None
    _write_latest(tmp_path, {"lean": None})                 # desk present, no lean
    assert bsite._dollar_context(tmp_path, "XLE") is None


# --------------------------------------------------------------------------- #
# 4. ledger consistency + the not-wired / graveyard guarantees
# --------------------------------------------------------------------------- #
def _backfill_row(cid: str) -> dict:
    row = next((r for r in intl_claims.BACKFILL if r["id"] == cid), None)
    assert row is not None, f"{cid} missing from BACKFILL"
    return row


def test_reer_backfill_confirmed_and_recorded():
    """The shipped REER row records the CONFIRMED verdict + the N=1 gate numbers, and its
    notes state NO consumer wiring this wave (P1)."""
    r = _backfill_row("c4_reer_value")
    assert r["verdict"] == "CONFIRMED" and r["kill"] is False
    assert r["weight_cap"] == pytest.approx(0.1333, abs=1e-4)
    assert r["metrics"]["dsr"] >= 0.90                     # cleared the N=1 door
    assert r["metrics"]["orthogonal_partial"] < 0          # correct de-risk sign
    # the note must not over-claim consumer wiring
    assert "NO CONSUMER WIRING" in r["notes"]
    assert "LIVE in engine/intl_feed" not in r["notes"]


def test_cnh_backfill_inverted_graveyard():
    """The CNH row is the truthful negative: INVERTED, kill=True, weight 0, wrong-signed
    residual (the decider)."""
    r = _backfill_row("c4_cnh_basis")
    assert r["verdict"] == "INVERTED" and r["kill"] is True
    assert r["weight_cap"] == 0.0
    assert r["metrics"]["orthogonal_partial"] > 0          # WRONG sign for a de-risk leg
    assert r["metrics"]["dsr"] < 0.90                      # fails the promotion door


def _write_ledger(tmp_path: Path, features: list[dict]) -> Path:
    d = tmp_path / "data" / "intl_bridge"
    d.mkdir(parents=True)
    (d / "ledger.json").write_text(json.dumps(
        {"asof": "2026-07-02", "family": "intl_bridge", "features": features}))
    return tmp_path


def _fresh_parquet(tmp_path: Path, group: str, name: str, age_days: int) -> None:
    d = tmp_path / "data" / group
    d.mkdir(parents=True, exist_ok=True)
    safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
    idx = pd.to_datetime([date.today() - timedelta(days=age_days)])
    pd.DataFrame({"close": [1.0]}, index=idx).to_parquet(d / f"{safe}.parquet")


def test_cnh_graveyard_is_zero_weight(tmp_path):
    """INVERTED + kill=True → intl_feed weight 0: nothing sizes off the CNH basis (the
    China RORO frame is provably unaffected)."""
    row = {"id": "c4_cnh_basis", "channel": "C4", "direction": "de-risk",
           "verdict": "INVERTED", "weight_cap": 0.0,
           "source_series": ["yahoo/CNH_F", "fred/DEXCHUS"], "freshness_sla_days": 21,
           "kill": True, "notes": "graveyard"}
    root = _write_ledger(tmp_path, [row])
    _fresh_parquet(tmp_path, "yahoo", "CNH_F", 1)
    _fresh_parquet(tmp_path, "fred", "DEXCHUS", 5)
    st = feed.features(root=root)["c4_cnh_basis"]
    assert st["weight"] == 0.0


def test_reer_confirmed_surfaced_but_no_scorer_consumes(tmp_path):
    """The CONFIRMED REER leg is surfaced by the Layer-2 registry at its full cap (fresh
    data), proving the verdict IS live in the ledger — while separately, NO scoring-core
    module imports the feed, so nothing actually sizes on it this wave (P1)."""
    row = {"id": "c4_reer_value", "channel": "C4", "direction": "de-risk",
           "verdict": "CONFIRMED", "weight_cap": 0.1333,
           "source_series": ["fred/DTWEXBGS", "fred/RBUSBIS"], "freshness_sla_days": 90,
           "kill": False, "notes": "recorded, not wired"}
    root = _write_ledger(tmp_path, [row])
    _fresh_parquet(tmp_path, "fred", "DTWEXBGS", 3)
    _fresh_parquet(tmp_path, "fred", "RBUSBIS", 40)         # < 90d SLA → fresh enough
    st = feed.features(root=root)["c4_reer_value"]
    assert st["weight"] == pytest.approx(0.1333)           # surfaced at its cap (CONFIRMED)
    # the not-wired guarantee: no scoring-core module imports intl_feed / intl_sleeve
    scorers = ["conditions.py", "china_conditions.py", "stock_score.py",
               "basket_score.py", "playbook.py", "name_score.py"]
    eng = ROOT / "engine"
    for fn in scorers:
        p = eng / fn
        if p.exists():
            txt = p.read_text()
            assert "intl_feed" not in txt and "intl_sleeve" not in txt, \
                f"{fn} unexpectedly imports the intl feed (would wire C4)"


def test_china_conditions_roro_unchanged():
    """P3 refusal: the existing raw usdcnh RORO leg is present and NO cnh_basis leg was
    added to the China RORO frame."""
    txt = (ROOT / "engine" / "china_conditions.py").read_text()
    assert 'legs["usdcnh"]' in txt                          # the existing leg survives
    assert "cnh_basis" not in txt                           # no second basis leg wired
