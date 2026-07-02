"""W4 · US Risk-Radar Tier-B GLOBAL breadth leg (INTL Fix Masterplan §5 C3 → INTL-38).

The C3 global-breadth barometer (% of data/intl_etf country ETFs > 200dma, causal 504d
percentile) is wired into engine/risk_radar.py as a **Tier-B** leg — display/escalator-only,
forward-graded before it is ever trusted (measured-weights, not priors).

Guards:
  1. Leg reads from the intl_etf store using the exact C3 construction (% > 200dma).
  2. Degrade-don't-crash: the leg ABSENTS itself (never crashes, never a frozen read) when
     the store is missing, stale (>8d), or thin (<10 alive ETFs).
  3. Composite UNCHANGED when the leg is absent — the Tier-A sub-scores that ORIGINATE the
     US state are byte-identical with and without the global leg (it is purely additive).
  4. Tier-B contract: 'global' is Tier-B; it can ESCALATE a hot Tier-A read but can NEVER
     originate a US state from calm (identical guardrail to the vol Tier-B scare).
  5. The leg is labelled + carries its C3 validation ref on the firing-leg dict.
  6. The leg enters ACCRUING (unvalidated as a US-radar leg) — it is NOT counted as a
     validated leading leg by _is_validated, so it can never arm the conjunction escalator.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from engine import risk_radar as rr
from lib import config


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_etf_store(n_etfs: int, n_rows: int, last_date, seed: int = 0) -> Path:
    """Write n_etfs synthetic close-only parquets into <tmp>/intl_etf/ ending at last_date."""
    d = Path(tempfile.mkdtemp())
    etf = d / "intl_etf"
    etf.mkdir()
    idx = pd.bdate_range(end=pd.Timestamp(last_date), periods=n_rows)
    rng = np.random.default_rng(seed)
    for i in range(n_etfs):
        px = 100.0 * (1 + rng.normal(0.0003, 0.012, n_rows)).cumprod()
        pd.DataFrame({"close": px}, index=idx).to_parquet(etf / f"EW{chr(65 + i)}.parquet")
    return d


def _sigs(**legs):
    """A 2-row causal-percentile signal frame for compute() (uses .iloc[-1])."""
    idx = pd.to_datetime(["2026-06-22", "2026-06-23"])
    return pd.DataFrame({leg: [v, v] for leg, v in legs.items()}, index=idx)


# --------------------------------------------------------------------------- #
# 1. construction — % > 200dma, causal
# --------------------------------------------------------------------------- #
def test_breadth_reads_from_store():
    d = _make_etf_store(15, 600, pd.Timestamp.today().normalize())
    with mock.patch.object(config, "data_dir", return_value=d):
        gb = rr._global_breadth_raw()
    assert gb is not None
    assert (gb.dropna() >= 0.0).all() and (gb.dropna() <= 1.0).all()
    assert len(gb) > 100


def test_breadth_is_causal_no_lookahead():
    """Truncating the store to an earlier as-of must not change earlier breadth values
    (the 200dma + panel mean use only trailing data). The stale guard is widened for this
    test so the truncated (older-ending) store still emits — we test causality, not staleness."""
    d = _make_etf_store(15, 600, pd.Timestamp.today().normalize(), seed=7)
    with mock.patch.object(config, "data_dir", return_value=d), \
            mock.patch.object(rr, "_GB_STALE_DAYS", 10_000):
        full = rr._global_breadth_raw()
    # rewrite the store truncated 50 bars earlier
    etf = d / "intl_etf"
    for p in etf.glob("*.parquet"):
        df = pd.read_parquet(p).iloc[:-50]
        df.to_parquet(p)
    with mock.patch.object(config, "data_dir", return_value=d), \
            mock.patch.object(rr, "_GB_STALE_DAYS", 10_000):
        trunc = rr._global_breadth_raw()
    common = full.index.intersection(trunc.index)
    # last 200 shared dates must match exactly (no future data leaked into the past)
    tail = common[-200:]
    assert np.allclose(full.reindex(tail).to_numpy(), trunc.reindex(tail).to_numpy(), equal_nan=True)


# --------------------------------------------------------------------------- #
# 2. degrade-don't-crash: stale / thin / missing → leg absent
# --------------------------------------------------------------------------- #
def test_leg_absent_when_store_missing():
    d = Path(tempfile.mkdtemp())      # no intl_etf/ dir
    with mock.patch.object(config, "data_dir", return_value=d):
        assert rr._global_breadth_raw() is None


def test_leg_absent_when_stale():
    """Last obs older than _GB_STALE_DAYS → the leg zeroes itself (no frozen breadth carried)."""
    stale = pd.Timestamp.today().normalize() - pd.Timedelta(days=rr._GB_STALE_DAYS + 22)
    d = _make_etf_store(15, 600, stale)
    with mock.patch.object(config, "data_dir", return_value=d):
        assert rr._global_breadth_raw() is None


def test_leg_absent_when_thin_panel():
    """Fewer than _GB_PANEL_MIN alive ETFs on the last date → the leg zeroes itself."""
    d = _make_etf_store(rr._GB_PANEL_MIN - 5, 600, pd.Timestamp.today().normalize())
    with mock.patch.object(config, "data_dir", return_value=d):
        assert rr._global_breadth_raw() is None


def test_leading_signals_omits_leg_when_absent():
    """leading_signals() must simply not carry the column when the store is unusable — no crash."""
    d = Path(tempfile.mkdtemp())
    with mock.patch.object(config, "data_dir", return_value=d):
        sigs = rr.leading_signals()
    assert "global_breadth" not in sigs.columns


# --------------------------------------------------------------------------- #
# 3. composite UNCHANGED when the leg is absent
# --------------------------------------------------------------------------- #
def test_tierA_composite_identical_with_and_without_global_leg():
    """The Tier-A sub-scores that ORIGINATE the state must be byte-identical whether or not the
    global-breadth leg is present — the leg is purely additive (Tier-B)."""
    sigs = rr.leading_signals()
    if "global_breadth" not in sigs.columns:      # store present in this env; guard anyway
        sigs = sigs.assign(global_breadth=0.99)
    with_gb = rr.compute(sigs=sigs)
    without_gb = rr.compute(sigs=sigs.drop(columns=["global_breadth"]))
    a_with = {s["scare"]: s["score"] for s in with_gb["scares"] if s["tier"] == "A"}
    a_no = {s["scare"]: s["score"] for s in without_gb["scares"] if s["tier"] == "A"}
    assert a_with == a_no
    # the state itself is originated by Tier-A only → identical
    assert with_gb["state"] == without_gb["state"]


# --------------------------------------------------------------------------- #
# 4. Tier-B contract: escalate-only, never originate from calm
# --------------------------------------------------------------------------- #
def test_global_scare_is_tierB():
    out = rr.compute(sigs=_sigs(global_breadth=0.99), gate={"met": True})
    g = next((s for s in out["scares"] if s["scare"] == "global"), None)
    assert g is not None and g["tier"] == "B"


def test_global_leg_cannot_originate_state_from_calm():
    """With ONLY the global-breadth leg screaming and every Tier-A leg calm, the state stays
    calm — a Tier-B leg can escalate a hot Tier-A read but never originate one (like vol)."""
    out = rr.compute(sigs=_sigs(global_breadth=0.99), gate={"met": True})
    assert out["state"] == "calm"


def test_global_leg_escalates_hot_tierA():
    """A hot Tier-A read (growth at caution) + a screaming global leg escalates one step
    (mirrors the vol Tier-B escalation path). Gate met so the loud tier is permitted."""
    base = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95), gate={"met": True})
    esc = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95, global_breadth=0.99),
                     gate={"met": True})
    assert rr._STATE_ORDER.index(esc["state"]) >= rr._STATE_ORDER.index(base["state"])
    assert esc["state"] in ("elevated", "risk-off")


# --------------------------------------------------------------------------- #
# 5. label + validation ref on the firing leg
# --------------------------------------------------------------------------- #
def test_global_leg_carries_validation_ref():
    out = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95, global_breadth=0.99),
                     gate={"met": True})
    g = next(s for s in out["scares"] if s["scare"] == "global")
    leg = next(l for l in g["firing_legs"] if l["leg"] == "global_breadth")
    assert "C3" in leg.get("validation_ref", "")
    assert "intl-global-breadth-phase0" in leg["validation_ref"]
    assert leg["accruing"] is True


# --------------------------------------------------------------------------- #
# 6. accruing → not a validated leading leg (cannot arm the conjunction escalator)
# --------------------------------------------------------------------------- #
def test_global_leg_is_not_validated():
    assert rr._is_validated("global_breadth") is False


def test_snapshot_never_raises_with_leg():
    out = rr.snapshot()
    assert isinstance(out, dict) and out["schema"] == "risk_radar.v2"
    # if the intl_etf store is present in this env, the leg should be one of the scares
    scare_keys = {s["scare"] for s in out.get("scares", [])}
    assert "global" in scare_keys or out.get("state") is None or "global_breadth" not in rr.leading_signals().columns
