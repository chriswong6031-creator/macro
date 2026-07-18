"""Regime-snap / narrative-relief detector (engine/regime_snap.py) — DISPLAY-ONLY.

Hermetic: builds a synthetic conditions-style frame (no parquet store, no network)
so the trigger logic is tested deterministically. The historical event verification
lives in scripts/regime_snap_history.py (needs the data store).

The on-page relief-radar strip is GONE: #2670 deleted the legacy #now-board news
panel from templates/dashboard.html.j2 (its news role moved to the mx5/AI-Brief
surfaces) and no template renders regime_snap anymore. The detector, the veto and
the build_site view/persist wiring all remain live — regime_snap.json still feeds
the AI-desk leg — so only the card-render tests were removed here."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import regime_snap as rs  # noqa: E402

CFG = {}  # -> all _DEFAULTS (window_d 2, fear_min .40, require_capitulation True, ...)
_ROOT = Path(__file__).resolve().parent.parent


# Snapshot-shaped payloads for the veto tests (mirror snap_snapshot() output).
_FIRING = {
    "snap": True, "status": "firing", "relief_magnitude": 72, "magnitude_band": "large",
    "roro": 0.55, "cap_recent": True, "fear_built": 0.80, "roro_velocity": 0.90,
    "vel_pctile": 0.97, "legs_up": 5, "legs_total": 7,
    "flipped_legs": ["vix", "hy_oas"],
    "flipped_legs_named": [{"key": "vix", "en": "VIX", "zh": "波动率 VIX"},
                           {"key": "hy_oas", "en": "HY credit spread", "zh": "高收益信用利差"}],
    "days_since_last_snap": 40, "min_legs": 4, "fear_rebuilding": False, "vix_term": 1.05,
    "gates": {"velocity": True, "legs": True, "fear": True, "washout": True},
}
_DORMANT = {
    "snap": False, "status": "dormant", "relief_magnitude": None, "magnitude_band": None,
    "roro": 0.10, "cap_recent": False, "fear_built": 0.20, "roro_velocity": 0.05,
    "vel_pctile": 0.40, "legs_up": 1, "legs_total": 7,
    "flipped_legs": [], "flipped_legs_named": [], "days_since_last_snap": 120,
    "min_legs": 4, "fear_rebuilding": False, "vix_term": 0.85,
    "gates": {"velocity": False, "legs": False, "fear": False, "washout": False},
}


def _synthetic_frame(n: int = 700) -> pd.DataFrame:
    """A long calm stretch, then a fear washout, then a broad risk-on thrust —
    the post-washout relief fingerprint the detector should fire on."""
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(0)
    roro = rng.normal(0, 0.05, n)
    roro[n - 12:n - 6] = np.linspace(-0.2, -1.3, 6)        # fear dip
    roro[n - 6:n] = np.linspace(-1.3, 0.6, 6)              # sharp recovery thrust
    roro = pd.Series(roro, index=idx)
    cf = pd.DataFrame({"roro": roro}, index=idx)
    # 7 signed legs tracking roro (so the thrust flips all of them together)
    for k in rs._LEG_KEYS:
        cf[f"roro_{k}"] = (roro + rng.normal(0, 0.02, n)).to_numpy()
    # fear gauges: calm by default, spiked across the washout window (build whole
    # arrays — pandas 3.0 copy-on-write makes chained .iloc assignment a no-op)
    fw = slice(n - 12, n - 6)
    for col, calm, fear in [("vrp_pctile", 0.30, 0.95), ("skew_pctile", 0.20, 0.90),
                            ("vix_term", 0.85, 1.05), ("capitulation_score", 0.0, 2.0)]:
        arr = np.full(n, calm)
        arr[fw] = fear
        cf[col] = arr
    return cf


def test_columns_and_ranges():
    sf = rs.snap_frame(_synthetic_frame(), CFG)
    for col in ("roro", "roro_velocity", "vel_pctile", "legs_up", "legs_total",
                "fear_index", "fear_built", "cap_recent", "snap", "relief_magnitude"):
        assert col in sf.columns, col
    assert set(sf["snap"].unique()) <= {0, 1}
    assert sf["relief_magnitude"].between(0, 100).all()
    assert (sf.loc[sf["snap"] == 0, "relief_magnitude"] == 0).all()  # magnitude only on fires


def test_fires_on_post_washout_thrust():
    sf = rs.snap_frame(_synthetic_frame(), CFG)
    assert sf["snap"].iloc[-6:].sum() >= 1, "should fire during the post-washout thrust"
    last_fire = sf[sf["snap"] == 1].iloc[-1]
    assert last_fire["legs_up"] >= 4
    assert last_fire["roro_velocity"] > 0
    assert last_fire["relief_magnitude"] > 0


def test_quiet_period_does_not_fire():
    sf = rs.snap_frame(_synthetic_frame(), CFG)
    # the long calm stretch (well clear of warmup and the terminal washout)
    assert sf["snap"].iloc[300:600].sum() == 0


def test_capitulation_gate_blocks_without_washout():
    """Same thrust, but no capitulation washout -> the relief gate must block it."""
    cf = _synthetic_frame()
    cf["capitulation_score"] = 0.0
    sf = rs.snap_frame(cf, CFG)
    assert sf["snap"].iloc[-6:].sum() == 0


def test_degrades_without_optional_columns():
    """No roro at all -> no crash, no fires; missing capitulation -> gate is no-op."""
    idx = pd.bdate_range("2020-01-01", periods=300)
    empty = pd.DataFrame(index=idx)
    sf = rs.snap_frame(empty, CFG)
    assert (sf["snap"] == 0).all()
    assert rs.snap_snapshot(empty, CFG) is None


def test_snapshot_shape():
    snap = rs.snap_snapshot(_synthetic_frame(), CFG)
    assert snap is not None
    for key in ("snap", "relief_magnitude", "fear_built", "roro_velocity",
                "vel_pctile", "legs_up", "legs_total", "flipped_legs",
                "days_since_last_snap", "fear_rebuilding", "vix_term"):
        assert key in snap, key
    assert isinstance(snap["flipped_legs"], list)


def test_never_scored_invariant():
    """DISPLAY-ONLY: the scoring path must not import the detector (mirrors the
    anti-dampener discipline — nothing in axes/regime reads regime_snap)."""
    for mod in ("engine/axes.py", "engine/regime.py"):
        src = (_ROOT / mod).read_text()
        assert not re.search(r"\bregime_snap\b", src), f"{mod} must not reference regime_snap"


def test_view_wired_into_build_site():
    from scripts import build_site as bs
    assert hasattr(bs, "regime_snap_view")
    src = (_ROOT / "scripts" / "build_site.py").read_text()
    assert "regime_snap_view(_cf)" in src and "regime_snap=_rs_view" in src
    # the triggered veto is still attached + persisted (AI-desk artifact / grading
    # log) even though the on-page strip is gone (#518 declutter, panel deleted #2670)
    assert 'regime_snap_veto.assess(' in src
    assert 'regime_snap.json' in src
    view = bs.regime_snap_view(_synthetic_frame())
    assert view is not None
    assert view["status"] in {"firing", "building", "dormant"}
    assert set(view["gates"]) == {"velocity", "legs", "fear", "washout"}
    assert isinstance(view["flipped_legs_named"], list)


# ---- AI knife-vs-dip veto (engine/regime_snap_veto.py) ----------------------
def _fake_call(reply):
    """Stand-in for master_brain._call_model so the veto runs without an API key."""
    captured = {}
    def call(system, user, cfg):
        captured["system"], captured["user"], captured["cfg"] = system, user, cfg
        return reply, None
    return call, captured


def test_veto_triggered_parses_and_is_grounded():
    from engine import regime_snap_veto as veto
    reply = ('{"lean":"fragile","confidence":"medium","checks":'
             '{"catalyst":"verbal ceasefire, unsigned","premium":"mostly unwound",'
             '"washout":"real","follow_through":"likely fades"},'
             '"read":"Verbal de-escalation; fragile."}')
    call, cap = _fake_call(reply)
    v = veto.assess(_FIRING, call=call, persist=False,
                    headlines={"headlines": [{"title": "Ceasefire framework agreed"}]},
                    drivers={"verdict": "clear", "driver": "oil_shock"}, regime="Goldilocks")
    assert v is not None
    assert v["lean"] == "fragile" and v["confidence"] == "medium"
    assert v["is_context_only"] is True and v["checks"]["catalyst"].startswith("verbal")
    # grounded: the prompt carries the snap state and the actual headline (no fabrication)
    assert "Ceasefire framework agreed" in cap["user"] and "firing" in cap["user"]


def test_veto_none_when_dormant():
    from engine import regime_snap_veto as veto
    call, _ = _fake_call('{"lean":"durable"}')
    assert veto.assess(_DORMANT, call=call, persist=False) is None


def test_veto_none_when_llm_unavailable():
    from engine import regime_snap_veto as veto
    assert veto.assess(_FIRING, call=lambda s, u, c: (None, "no_client_or_key"),
                       persist=False) is None


def test_veto_none_on_bad_lean():
    from engine import regime_snap_veto as veto
    call, _ = _fake_call('{"lean":"moon","confidence":"high"}')
    assert veto.assess(_FIRING, call=call, persist=False) is None


def test_veto_never_scored_invariant():
    # the veto reads the detector, NEVER the reverse — scoring/detection must not import it
    for mod in ("engine/axes.py", "engine/regime.py", "engine/regime_snap.py"):
        assert "regime_snap_veto" not in (_ROOT / mod).read_text(), mod
