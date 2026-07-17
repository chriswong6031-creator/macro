"""Tests for the D3-W3.1 proxy registry + `record_series` kernel extension.

Five acceptance areas (per the wave spec / D3_FLAGSHIPS.md §1/§1.5/§2):

  (1) REGISTRY SCHEMA — every cycle resolves to a well-formed band list; the
      MEASURED/FRAME/proxy invariants hold; the census matches the D3 §1.2 table;
      the NP-3 "PL trap" is closed (a futures_cont band can never plot an equity).
  (2) record_series FREQ / INVERT / zz_abs — synthetic-series behaviour:
      • daily sine  → clean alternating turns
      • inverted V  → a V-trough in the RAW series shows as a PEAK in plotted space,
        and turns[].px re-inverts to the ORIGINAL units
      • monthly sine at freq="M" → month-end bars, now.freq=="M"
      • zz_abs on a bounded diffusion series → abs-threshold pivots, mag_abs present
      • zz_standardize on a TRENDING level → scale-stable σ-unit turns (the INDPRO fix)
  (3) _record_core BYTE-IDENTITY — the daily special case delegates to record_series
      with zero behaviour change (dict-equality on a synthetic sector series).
  (4) FITNESS GATE MATH — Wilson lower bound, match/offset gating, and AUTO-DEMOTION
      when the point rate or offset fails (synthetic hand-turn sets, no disk needed).
  (5) HAZARD FEATURES / freq stamp — every non-daily / non-sector stamp carries
      now.freq and now.hazard_features with family="flagship".

Registry-resolution tests are guarded on data presence so the suite still runs in a
data-less checkout (they skip rather than fail).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import cycle_proxies as cp
from engine import sector_cycles as sc


# ── synthetic-series helpers ─────────────────────────────────────────────────
def _sine(n_years=20, freq="D", amp=0.4, period_yrs=2.0, drift=0.0, level=100.0):
    """A clean cyclical level series: level * (1 + amp*sin) * exp(drift*t)."""
    per = 252 if freq == "D" else 12
    n = int(n_years * per)
    idx = pd.date_range("2000-01-03", periods=n, freq=("B" if freq == "D" else "ME"))
    t = np.arange(n) / per
    s = level * (1.0 + amp * np.sin(2 * np.pi * t / period_yrs)) * np.exp(drift * t)
    return pd.Series(s, index=idx)


def _vee(n=800, level=5.0, depth=3.0):
    """A single V: falls to a trough at the midpoint, recovers.  Used for invert tests —
    a V-TROUGH in the raw series is a PEAK once inverted (1/x)."""
    idx = pd.date_range("2005-01-03", periods=n, freq="B")
    x = np.linspace(-1, 1, n)
    s = level - depth * (1 - np.abs(x))          # min (trough) at the centre
    return pd.Series(s, index=idx)


# ── (1) REGISTRY SCHEMA ──────────────────────────────────────────────────────
def test_registry_every_band_wellformed():
    """Every band carries the full schema keys with legal values."""
    legal_tiers = {"measured", "frame"}
    legal_basis = {"spot", "futures_cont", "fred_level", "etf_tr", "etf_px",
                   "index_px", "equity_px", None}
    for cid, spec in cp.REGISTRY.items():
        assert "name" in spec and "bands" in spec, cid
        assert spec["bands"], f"{cid} has no bands"
        for b in spec["bands"]:
            assert b["tier"] in legal_tiers, (cid, b["tier"])
            assert b["basis"] in legal_basis, (cid, b["basis"])
            # frame bands are seriesless; measured bands name a series
            if b["tier"] == "frame":
                assert b["series"] is None, f"{cid} frame band names a series"
            else:
                assert b["series"] is not None, f"{cid} measured band has no series"
                assert b["freq"] in ("D", "M"), (cid, b["freq"])


def test_proxy_bands_are_timing_only():
    """Ruling A17: every proxy band is tier 'measured' with position_gauge=False and a
    fitness dict; every non-proxy measured band gauges position."""
    for cid, band in cp.measured_bands():
        if band["proxy"]:
            assert band["tier"] == "measured", cid
            assert band["position_gauge"] is False, f"{cid} proxy must suppress position"
            assert band["fitness"] is not None, f"{cid} proxy needs a fitness gate"
        else:
            assert band["position_gauge"] is True, cid
            assert band["fitness"] is None, cid


def test_census_matches_d3_table():
    """The as-built census matches the D3 §1.2 TABLE (16 daily MEASURED/DUAL rows across
    the 23 cycles + the spx flagship; 2 proxy; 1 monthly; 4 frame-only; 6 frame bands)."""
    reg = cp._serialisable_registry()
    c = reg["census"]
    assert c["measured"] == 17          # 12 pure daily + 4 DUAL measured + spx
    assert c["measured_proxy"] == 2     # memory, uranium
    assert c["measured_monthly"] == 1   # business
    assert c["frame_only"] == 4         # housing, shipping, lithium, iron-ore
    assert c["dual"] == 6               # 4 DUAL cards + 2 proxy-cards-with-frame-overlay
    assert c["frame"] == 10             # 4 dual-secular + 4 frame-only + 2 proxy overlays


def test_np3_pl_trap_closed():
    """NP-3: a futures_cont band that names a NON-futures ticker (a naked 'PL' = Planet
    Labs equity) must raise ProxyMissing, never silently resolve an equity tape."""
    trap = {"band": "intermediate", "tier": "measured", "basis": "futures_cont",
            "series": ["yahoo:PL"], "invert": False, "kernel": {}, "proxy": False}
    with pytest.raises(cp.ProxyMissing, match="NP-3"):
        cp.load_series(trap)
    # the real pgms band pins the '=F' future and passes the guard
    pgms = cp.REGISTRY["pgms"]["bands"][0]
    assert pgms["basis"] == "futures_cont"
    _, tick = cp._split_ref(pgms["series"] if isinstance(pgms["series"], str)
                            else pgms["series"][0])
    assert "=F" in tick or tick.endswith("_F")


def test_frame_band_load_series_undefined():
    """A frame-only band has series=None → load_series is undefined and raises."""
    frame = cp.REGISTRY["housing"]["bands"][0]
    assert frame["tier"] == "frame" and frame["series"] is None
    with pytest.raises(cp.ProxyMissing):
        cp.load_series(frame)


@pytest.mark.skipif(cp.store.read("yahoo", "SOXX") is None,
                    reason="no on-disk yahoo data in this checkout")
def test_every_measured_band_resolves():
    """Data-dependent: every measured band's declared ref resolves to a non-empty tape."""
    for cid, band in cp.measured_bands():
        s = cp.load_series(band)
        assert len(s) > 60, f"{cid}: only {len(s)} rows"
        assert s.attrs.get("ref"), cid


# ── (2) record_series FREQ / INVERT / zz_abs ─────────────────────────────────
def test_daily_sine_alternating_turns():
    s = _sine(n_years=16, freq="D", period_yrs=2.0)
    rec = sc.record_series(s, win_start=s.index[0], last_ts=s.index[-1],
                           freq="D", family="flagship")
    turns = [t for t in rec["turns"] if not t.get("provisional")]
    kinds = [t["k"] for t in turns]
    # a clean sine must alternate peak/trough
    for a, b in zip(kinds, kinds[1:]):
        assert a != b, "consecutive same-kind pivots on a clean sine"
    assert len(turns) >= 8, f"only {len(turns)} turns on 16y of 2y sine"


def test_invert_mirrors_turns_and_reinverts_px():
    """A V-TROUGH in the raw series becomes a PEAK in inverted (1/x) plotted space, and
    turns[].px is reported back in ORIGINAL units."""
    raw = _vee(n=900, level=6.0, depth=4.0)          # trough at the centre (~level 2)
    rec = sc.record_series(raw, win_start=raw.index[0], last_ts=raw.index[-1],
                           freq="D", invert=True, zz_pct=8.0, family="flagship")
    turns = [t for t in rec["turns"] if not t.get("provisional")]
    # the deepest raw point is the centre; inverted, that is the HIGHEST → a PEAK
    mid_peaks = [t for t in turns if t["k"] == "peak"]
    assert mid_peaks, "inverted V produced no peak at the raw trough"
    # px re-inverted to ORIGINAL units → near the raw trough level (~2), NOT ~0.5 (1/x space)
    peak_px = mid_peaks[len(mid_peaks) // 2]["px"]
    assert 1.0 < peak_px < 4.0, f"px {peak_px} not re-inverted to raw units"


def test_monthly_freq_stamp_and_bars():
    s = _sine(n_years=30, freq="M", period_yrs=4.0)
    rec = sc.record_series(s, win_start=s.index[0], last_ts=s.index[-1],
                           freq="M", family="flagship")
    assert rec is not None
    assert rec["now"]["freq"] == "M"
    # no daily ladder on a monthly series
    assert rec["now"].get("timing_state") in (None, "", "—")


def test_monthly_min_bars_guard():
    """freq='M' needs >=72 bars; a 5y monthly series (60 bars) returns None."""
    short = _sine(n_years=5, freq="M")
    assert sc.record_series(short, win_start=short.index[0], last_ts=short.index[-1],
                            freq="M") is None


def test_zz_abs_bounded_series():
    """abs-threshold ZigZag on a BOUNDED diffusion series (a z-scored composite proxy);
    mag_abs is stamped and pivots alternate."""
    # a bounded oscillation centred at 50 in [47, 53] — % of level is meaningless here
    # (a diffusion index like ISM PMI); positive so the rebase base is well-defined.
    idx = pd.date_range("2000-01-31", periods=360, freq="ME")
    t = np.arange(360) / 12.0
    s = 50.0 + 3.0 * np.sin(2 * np.pi * t / 3.0)
    ser = pd.Series(s, index=idx)
    rec = sc.record_series(ser, win_start=ser.index[0], last_ts=ser.index[-1],
                           freq="M", zz_abs=1.5, family="flagship")
    turns = [t for t in rec["turns"] if not t.get("provisional")]
    assert turns, "abs-ZigZag found no turns on a bounded oscillation"
    assert all(t.get("mag_abs") is not None for t in turns[1:]), "mag_abs not stamped"


def test_zz_standardize_stabilizes_trending_level():
    """The INDPRO fix (§2.3): a raw abs threshold OVER-SEGMENTS a trending level; running
    the abs-ZigZag on a causal z-score (zz_standardize=True) yields far fewer, scale-stable
    turns, and turns[].px is mapped back to the RAW level units."""
    # Faithful to INDPRO's character: a steep secular trend (~4 → ~110, a 28x range like
    # 1919→today) with a fixed-amplitude Kitchin cycle + small noise ON TOP.  At the HIGH
    # end a 1.5-pt raw-abs threshold trips on every tiny wiggle (over-segmenting); a σ-unit
    # threshold on the causal z-score is scale-stable across the whole tape.
    n = 360
    idx = pd.date_range("1990-01-31", periods=n, freq="ME")
    t = np.arange(n) / 12.0
    rng = np.random.default_rng(7)
    trend_lvl = 4.0 * np.exp(0.11 * t)                 # ~4 → ~110 over 30y
    cycle = 3.0 * np.sin(2 * np.pi * t / 4.0)          # fixed-amplitude ~4y Kitchin
    noise = rng.normal(0, 0.8, n)                      # short-period wiggle
    trend = pd.Series(np.maximum(trend_lvl + cycle + noise, 0.5), index=idx)
    kw = dict(win_start=trend.index[0], last_ts=trend.index[-1], freq="M",
              zz_abs=1.5, trend_span=60, family="flagship")
    raw_rec = sc.record_series(trend, **kw)                       # raw-abs (over-segments)
    std_rec = sc.record_series(trend, zz_standardize=True, **kw)  # standardized
    n_raw = len([t for t in raw_rec["turns"] if not t.get("provisional")])
    n_std = len([t for t in std_rec["turns"] if not t.get("provisional")])
    assert n_std < n_raw, f"standardized ({n_std}) not fewer than raw-abs ({n_raw})"
    # px mapped back to raw units: a level series that reaches ~110, not σ-units (~±3)
    pxs = [t["px"] for t in std_rec["turns"] if t.get("px")]
    assert max(pxs) > 20.0, f"px {max(pxs)} looks like z-units, not the raw level"


# ── (3) _record_core BYTE-IDENTITY ───────────────────────────────────────────
def test_record_core_delegates_byte_identical():
    """_record_core(full, ...) must equal record_series(full, ..., freq='D') exactly —
    the daily special case is a pure delegation (this is the invariant the three engine
    pages regression-test at the JSON level; here we assert it at the dict level)."""
    s = _sine(n_years=18, freq="D", period_yrs=2.5, drift=0.02)
    ws, lt = s.index[0], s.index[-1]
    core = sc._record_core(s, win_start=ws, last_ts=lt, series_id="synthetic")
    direct = sc.record_series(s, win_start=ws, last_ts=lt, freq="D",
                              zz_pct=sc._ZZ_PCT, series_id="synthetic")
    assert core == direct, "record_core diverged from record_series(freq='D')"
    # the daily sector default must NOT carry the additive W3.1 stamps (byte-identity)
    assert "freq" not in core["now"], "daily sector path leaked now.freq (breaks byte-id)"
    assert "hazard_features" not in core["now"]


# ── (4) FITNESS GATE MATH ────────────────────────────────────────────────────
def test_wilson_lower_bounds():
    assert cp._wilson_lower(0, 0) == 0.0
    # 8/10 → point 0.8, Wilson lower ~0.49 (small n pulls it well below the point)
    wl = cp._wilson_lower(8, 10)
    assert 0.4 < wl < 0.6, wl
    # perfect 20/20 → high lower bound
    assert cp._wilson_lower(20, 20) > 0.8
    # lower bound never exceeds the point estimate
    assert cp._wilson_lower(7, 10) <= 0.7


def _synthetic_band(**kernel):
    return {"band": "intermediate", "tier": "measured", "basis": "equity_px",
            "invert": False, "freq": "D", "proxy": True, "position_gauge": False,
            "kernel": kernel or {"zz_pct": 8.0},
            "fitness": {"kind": "test", "match_rate_min": 0.7, "offset_max_months": 6}}


def test_fitness_pass_and_demote(monkeypatch):
    """validate_proxy: a proxy whose engine turns line up with the hand turns PASSES
    (demote=False); one whose turns are far off AUTO-DEMOTES (demote=True)."""
    band = _synthetic_band(zz_pct=8.0)
    # a clean 2.5y-period sine → engine turns roughly every ~1.25y; hand turns placed ON
    # those extrema pass, hand turns placed at the wrong dates fail.
    tape = _sine(n_years=20, freq="D", period_yrs=2.5)
    monkeypatch.setattr(cp, "load_series", lambda b: tape.copy())

    # derive the engine's own turns, then feed a subset back as "hand" turns → must PASS
    rec = sc.record_series(tape, win_start=tape.index[0], last_ts=tape.index[-1],
                           freq="D", zz_pct=8.0, family="flagship")
    eng = [t for t in rec["turns"] if not t.get("provisional")]
    hand_good = [{"t": t["t"], "k": t["k"]} for t in eng[2:8]]
    v_pass = cp.validate_proxy("test", band, hand_good, period_central_yrs=2.5)
    assert v_pass["pass"] is True and v_pass["demote"] is False
    assert v_pass["match_rate"] >= 0.7

    # hand turns deliberately mis-dated by ~1 full period AND wrong kind at each slot →
    # match_rate collapses → AUTO-DEMOTE
    hand_bad = [{"t": "2001-06", "k": "peak"}, {"t": "2001-07", "k": "peak"},
                {"t": "2001-08", "k": "peak"}, {"t": "2001-09", "k": "peak"}]
    v_demote = cp.validate_proxy("test", band, hand_bad, period_central_yrs=2.5)
    assert v_demote["demote"] is True and v_demote["pass"] is False


def test_fitness_low_confidence_flag(monkeypatch):
    """A tiny-n proxy that passes the POINT gate but whose Wilson lower bound sits below
    the threshold is flagged low_confidence (A6) rather than hard-failing on n."""
    band = _synthetic_band(zz_pct=8.0)
    tape = _sine(n_years=20, freq="D", period_yrs=2.5)
    monkeypatch.setattr(cp, "load_series", lambda b: tape.copy())
    rec = sc.record_series(tape, win_start=tape.index[0], last_ts=tape.index[-1],
                           freq="D", zz_pct=8.0, family="flagship")
    eng = [t for t in rec["turns"] if not t.get("provisional")]
    hand = [{"t": t["t"], "k": t["k"]} for t in eng[2:5]]   # only 3 hand turns
    v = cp.validate_proxy("test", band, hand, period_central_yrs=2.5)
    if v["pass"]:
        # with n=3 the Wilson lower bound is far below 0.7 → low_confidence must fire
        assert v["match_rate_wilson_lo"] < 0.7
        assert v["low_confidence"] is True


# ── (5) HAZARD FEATURES / freq stamp ─────────────────────────────────────────
def test_hazard_features_on_flagship_stamp():
    s = _sine(n_years=16, freq="D", period_yrs=2.0)
    rec = sc.record_series(s, win_start=s.index[0], last_ts=s.index[-1],
                           freq="D", family="flagship")
    hf = rec["now"]["hazard_features"]
    for k in ("age_since_turn_bars", "pos", "osc_slope", "median_half_yrs",
              "n_turns_all", "freq", "family"):
        assert k in hf, f"hazard_features missing {k}"
    assert hf["family"] == "flagship" and hf["freq"] == "D"
    assert rec["now"]["freq"] == "D"


# ── (6) STALENESS SEMANTICS — per-band degrade, structural fatal ─────────────
# House law: one stale tape degrades its own band (ok=False + report['stale']);
# it NEVER aborts the page.  Only STRUCTURAL failures (unresolvable/missing tape)
# raise under strict.  Regression for the 2026-07-16/17 INDPRO freeze: the G.17
# release calendar makes a 75d monthly limit trip 1-2 days/month, and one trip
# froze all 24 cycle.html cards for days.

def _fake_tape(days_old: int, n: int = 400) -> pd.Series:
    """A synthetic tape whose LAST stamp is exactly `days_old` calendar days behind
    the same UTC-normalized 'today' registry_report uses.  Index freq is irrelevant —
    the staleness gate only reads index.max()."""
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    idx = pd.date_range(end=today - pd.Timedelta(days=days_old), periods=n, freq="D")
    s = pd.Series(np.linspace(90.0, 110.0, n), index=idx)
    s.attrs["ref"] = "test:FAKE"
    return s


def test_stale_band_degrades_never_raises(monkeypatch):
    """A stale monthly tape is flagged (ok=False, report['stale']) but strict
    registry_report does NOT raise — staleness is not a structural error."""
    monkeypatch.setattr(cp, "load_series",
                        lambda band: _fake_tape(400 if band["freq"] == "M" else 0))
    rep = cp.registry_report(strict=True)          # must not raise
    assert rep["errors"] == []
    assert rep["stale"], "a 400d-old monthly tape must be flagged stale"
    biz = rep["bands"]["business.intermediate"]
    assert biz["found"] is True and biz["ok"] is False
    assert biz["stale_days"] == 400
    # fresh daily bands are untouched by the stale monthly one
    assert rep["bands"]["semis.intermediate"]["ok"] is True


def test_per_band_stale_limit_override(monkeypatch):
    """business/INDPRO declares stale_limit_days=85: an 80d-old tape (which the old
    75d monthly default aborted the whole page on) is now healthy.  The override is
    per-band — it does not loosen any other band's limit."""
    monkeypatch.setattr(cp, "load_series",
                        lambda band: _fake_tape(80 if band["freq"] == "M" else 0))
    rep = cp.registry_report(strict=True)
    biz = rep["bands"]["business.intermediate"]
    assert biz["stale_limit"] == 85
    assert biz["ok"] is True
    assert rep["stale"] == [] and rep["errors"] == []
    # every non-override band still carries the freq default
    for key, e in rep["bands"].items():
        if key != "business.intermediate":
            assert e["stale_limit"] == (cp._STALE_MAX_M if e["freq"] == "M"
                                        else cp._STALE_MAX_D), key


def test_missing_tape_still_structural_fatal(monkeypatch):
    """An unresolvable tape remains a STRUCTURAL error: strict raises; non-strict
    records it under report['errors'] (not report['stale'])."""
    def _boom(band):
        raise cp.ProxyMissing("no data on disk (simulated)")
    monkeypatch.setattr(cp, "load_series", _boom)
    with pytest.raises(cp.ProxyMissing, match="structural"):
        cp.registry_report(strict=True)
    rep = cp.registry_report(strict=False)
    assert rep["errors"] and rep["stale"] == []
    assert all(e["found"] is False for e in rep["bands"].values())
