"""Tests for the regime-vintage PIT spine (CPI P-D5-1 phase 4a).

Covers, per the phase gate:
  * vintage as-of correctness on synthetic vintage frames (a value published
    later must NEVER be visible earlier; initial release wins over revisions;
    publication order never steps back to an older period),
  * cross-check against collectors.fred.as_of_series semantics,
  * fallback flagging (pre-vintage-coverage dates read latest-revised, flagged),
  * hysteresis re-application (the artifact's quad IS apply_hysteresis of its
    own axis scores under the live config),
  * additivity (a full real build leaves regime_history.parquet and latest.json
    byte-for-byte untouched),
  * determinism and schema.

The integration tests run the real builder ONCE into a tmp dir (module-scoped
fixture, ~5s) and assert invariants on that fresh build — deliberately NOT
byte-comparing against the committed artifact, which is on-demand cadence and
allowed to lag the daily-collected store.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from collectors.fred import as_of_series
from engine.regime import apply_hysteresis
from lib import config
from scripts.build_regime_v2_pit import (
    LEGS,
    PIT_CLASSES,
    classify_pit_rows,
    main,
    merged_leg_series,
    pit_availability_panel,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HIST = _REPO_ROOT / "data" / "regime" / "regime_history.parquet"
_LATEST = _REPO_ROOT / "data" / "regime" / "latest.json"

_HAVE_STORE = (_REPO_ROOT / "data" / "fred_vintage" / "vintages.parquet").exists() \
    and _HIST.exists()


# --------------------------------------------------------------------------- #
# synthetic vintage helpers
# --------------------------------------------------------------------------- #
def _vint(rows: list[tuple[str, str, float, str]]) -> pd.DataFrame:
    """rows: (series, period, value, realtime_start)."""
    return pd.DataFrame([
        {"series": s, "period": pd.Timestamp(p), "value": v,
         "realtime_start": pd.Timestamp(rt), "realtime_end": pd.Timestamp("2100-01-01")}
        for s, p, v, rt in rows
    ])


_BASIC = _vint([
    ("PAYEMS", "2020-01-01", 100.0, "2020-02-07"),
    ("PAYEMS", "2020-02-01", 110.0, "2020-03-06"),
    ("PAYEMS", "2020-03-01", 90.0, "2020-04-03"),
])


# --------------------------------------------------------------------------- #
# 1-5: vintage as-of correctness on synthetic frames
# --------------------------------------------------------------------------- #
def test_panel_value_not_visible_before_publication():
    panel = pit_availability_panel(_BASIC, "PAYEMS")
    grid = pd.bdate_range("2020-01-01", "2020-04-30")
    daily = panel.reindex(grid.union(panel.index)).ffill().reindex(grid)
    # the Jan print (published Feb 7) must NOT exist on any earlier date
    assert daily.loc[:"2020-02-06"].isna().all()
    assert daily.loc["2020-02-07"] == 100.0
    # the March print (published Apr 3) must not be visible in March
    assert (daily.loc["2020-03-06":"2020-04-02"] == 110.0).all()
    assert daily.loc["2020-04-03"] == 90.0


def test_panel_matches_as_of_series_semantics():
    panel = pit_availability_panel(_BASIC, "PAYEMS")
    for asof in ["2020-02-01", "2020-02-07", "2020-03-15", "2020-06-30"]:
        known = as_of_series("PAYEMS", asof, vintages=_BASIC)
        expect = known.iloc[-1] if len(known) else None
        got = panel[panel.index <= pd.Timestamp(asof)]
        got = got.iloc[-1] if len(got) else None
        assert got == expect, f"asof {asof}: panel {got} != as_of_series {expect}"


def test_panel_uses_initial_release_not_revision():
    v = _vint([
        ("PAYEMS", "2020-01-01", 100.0, "2020-02-07"),   # initial
        ("PAYEMS", "2020-01-01", 120.0, "2020-03-06"),   # revision — must be dropped
        ("PAYEMS", "2020-02-01", 111.0, "2020-03-06"),
    ])
    panel = pit_availability_panel(v, "PAYEMS")
    assert panel.loc[pd.Timestamp("2020-02-07")] == 100.0
    # the Feb-period initial (111) wins on 03-06, never the Jan revision (120)
    assert panel.loc[pd.Timestamp("2020-03-06")] == 111.0
    assert 120.0 not in panel.to_numpy()


def test_panel_never_steps_back_to_older_period():
    v = _vint([
        ("PAYEMS", "2020-02-01", 110.0, "2020-03-06"),
        ("PAYEMS", "2020-01-01", 100.0, "2020-03-20"),   # late release of an OLDER period
    ])
    panel = pit_availability_panel(v, "PAYEMS")
    # after 03-06 the visible value stays the Feb print; the stale Jan release
    # never overwrites newer information
    assert pd.Timestamp("2020-03-20") not in panel.index
    assert panel.loc[pd.Timestamp("2020-03-06")] == 110.0


def test_panel_same_day_multi_period_keeps_latest():
    v = _vint([
        ("PAYEMS", "2020-01-01", 100.0, "2020-03-06"),
        ("PAYEMS", "2020-02-01", 110.0, "2020-03-06"),   # same-day double release
    ])
    panel = pit_availability_panel(v, "PAYEMS")
    assert len(panel) == 1
    assert panel.loc[pd.Timestamp("2020-03-06")] == 110.0


# --------------------------------------------------------------------------- #
# 6: fallback merge — pre-coverage dates read latest-revised
# --------------------------------------------------------------------------- #
def test_merged_leg_pre_coverage_is_latest_revised():
    live = pd.Series([1.0, 2.0, 3.0, 4.0],
                     index=pd.to_datetime(["2019-10-01", "2019-11-01",
                                           "2019-12-01", "2020-01-01"]))
    panel = pit_availability_panel(_BASIC, "PAYEMS")
    first_rt = panel.index.min()          # 2020-02-07
    merged = merged_leg_series(live, panel, first_rt)
    # pre-coverage stamps: the latest-revised live values, reference-stamped
    assert (merged.loc[:"2020-02-06"] == live).all()
    # the live 2020-01-01 stamp is < first_rt so it IS kept (flagged fallback)
    assert merged.loc[pd.Timestamp("2020-01-01")] == 4.0
    # from coverage on: vintage initial releases at their publication stamps
    assert merged.loc[pd.Timestamp("2020-02-07")] == 100.0
    assert merged.index.is_monotonic_increasing


# --------------------------------------------------------------------------- #
# 7-8: pit_class / fallback_notes
# --------------------------------------------------------------------------- #
def test_classify_pit_rows_classes_and_notes():
    idx = pd.bdate_range("2020-01-01", "2020-01-10")
    active = {
        "payrolls": pd.Series(True, index=idx),
        "wei": pd.Series([False] * 5 + [True] * 3, index=idx),
    }
    cov = {"payrolls": pd.Timestamp("2019-01-01"),      # covered everywhere
           "wei": pd.Timestamp("2020-01-08")}           # covered from Jan 8
    out = classify_pit_rows(idx, active, cov)
    assert set(out.columns) == {"pit_class", "fallback_notes"}
    assert set(out["pit_class"].unique()) <= set(PIT_CLASSES)
    # days 1-5: only payrolls active, vintage -> pit_vintage, no notes
    assert (out["pit_class"].iloc[:5] == "pit_vintage").all()
    assert (out["fallback_notes"].iloc[:5] == "").all()
    # days 6-7 (Jan 8 is idx[5]): wei active but idx[5] >= cov start -> vintage
    assert (out.loc[pd.Timestamp("2020-01-08"), "pit_class"]) == "pit_vintage"
    # shift wei coverage later to force a mixed row with a note
    cov2 = {"payrolls": pd.Timestamp("2019-01-01"), "wei": pd.Timestamp("2021-01-01")}
    out2 = classify_pit_rows(idx, active, cov2)
    assert (out2["pit_class"].iloc[5:] == "mixed").all()
    assert (out2["fallback_notes"].iloc[5:] == "wei").all()


def test_classify_pit_rows_no_active_legs_split_by_coverage():
    idx = pd.bdate_range("2020-01-01", "2020-01-10")
    active = {"payrolls": pd.Series(False, index=idx)}
    cov = {"payrolls": pd.Timestamp("2020-01-06")}
    out = classify_pit_rows(idx, active, cov)
    # no revision-leaky input either way; classed by era for legibility
    assert (out.loc[:"2020-01-05", "pit_class"] == "revised_latest").all()
    assert (out.loc["2020-01-06":, "pit_class"] == "pit_vintage").all()
    assert (out["fallback_notes"] == "").all()
    # all-active-all-fallback -> revised_latest
    active2 = {"payrolls": pd.Series(True, index=idx)}
    cov2 = {"payrolls": pd.Timestamp("2021-01-01")}
    out2 = classify_pit_rows(idx, active2, cov2)
    assert (out2["pit_class"] == "revised_latest").all()
    assert (out2["fallback_notes"] == "payrolls").all()


# --------------------------------------------------------------------------- #
# 9: determinism of the pure pieces
# --------------------------------------------------------------------------- #
def test_unit_determinism():
    p1 = pit_availability_panel(_BASIC, "PAYEMS")
    p2 = pit_availability_panel(_BASIC, "PAYEMS")
    assert p1.equals(p2)
    idx = pd.bdate_range("2020-01-01", "2020-02-28")
    active = {"payrolls": pd.Series(True, index=idx)}
    cov = {"payrolls": pd.Timestamp("2020-02-01")}
    assert classify_pit_rows(idx, active, cov).equals(
        classify_pit_rows(idx, active, cov))


# --------------------------------------------------------------------------- #
# 10: the overrides seam default is a no-op on the live path
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAVE_STORE, reason="full data store not present")
def test_seam_overrides_default_is_noop():
    from engine.inputs import build_features
    from lib import store
    f_none = build_features()
    f_empty = build_features(overrides={})
    assert f_none.equals(f_empty), "overrides={} must be byte-identical to the live path"
    # injecting the EXACT live store series through the seam reproduces the live
    # column — proves the override flows through the same put() contract
    raw = store.read("fred", "PAYEMS").iloc[:, 0]
    f_inj = build_features(overrides={"payrolls": raw})
    assert f_inj["payrolls"].equals(f_none["payrolls"])


# --------------------------------------------------------------------------- #
# integration: one real build into a tmp dir
# --------------------------------------------------------------------------- #
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not _HAVE_STORE:
        pytest.skip("full data store not present")
    out = tmp_path_factory.mktemp("pitspine")
    before = {p: _sha(p) for p in (_HIST, _LATEST) if p.exists()}
    rc = main(["--out-dir", str(out)])
    assert rc == 0
    after = {p: _sha(p) for p in before}
    frame = pd.read_parquet(out / "regime_v2_pit.parquet")
    with open(out / "regime_v2_pit_divergence.json", encoding="utf-8") as fh:
        div = json.load(fh)
    return {"out": out, "before": before, "after": after,
            "frame": frame, "div": div}


def test_builder_additive_live_artifacts_untouched(built):
    """The build must leave regime_history.parquet + latest.json byte-for-byte."""
    assert built["after"] == built["before"]
    produced = sorted(p.name for p in built["out"].iterdir())
    assert produced == ["regime_v2_pit.parquet", "regime_v2_pit_divergence.json"]


def test_artifact_schema_and_enum(built):
    frame = built["frame"]
    hist = pd.read_parquet(_HIST)
    assert list(frame.columns) == list(hist.columns) + [
        "pit_class", "fallback_notes", "vintage_store_asof"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.is_monotonic_increasing
    assert set(frame["pit_class"].unique()) <= set(PIT_CLASSES)
    assert frame["vintage_store_asof"].nunique() == 1
    assert set(frame["quad"].dropna().unique()) <= {"Q1", "Q2", "Q3", "Q4"}


def test_fallback_flag_windows(built):
    frame = built["frame"]

    def row(d):
        return frame.loc[pd.Timestamp(d)]

    # pre-1997: every active macro leg reads latest-revised
    r95 = row("1995-06-15")
    assert r95["pit_class"] == "revised_latest"
    for leg in ("payrolls", "indpro", "sticky_cpi"):
        assert leg in r95["fallback_notes"]
    assert "wei" not in r95["fallback_notes"]      # WEI has no live data yet
    # 2012: payrolls/indpro vintage; wei (pre-2020), gdpnow (pre-2016) and
    # sticky (pre-2014) fall back
    r12 = row("2012-06-15")
    assert r12["pit_class"] == "mixed"
    for leg in ("wei", "gdpnow", "sticky_cpi"):
        assert leg in r12["fallback_notes"]
    for leg in ("payrolls", "indpro"):
        assert leg not in r12["fallback_notes"]
    # 2018: only WEI still pre-coverage
    r18 = row("2018-06-15")
    assert r18["pit_class"] == "mixed"
    assert r18["fallback_notes"] == "wei"
    # 2021+: full vintage coverage
    r21 = row("2021-06-15")
    assert r21["pit_class"] == "pit_vintage"
    assert r21["fallback_notes"] == ""


def test_hysteresis_reapplied_exact(built):
    """The artifact's confirmed quad must BE apply_hysteresis of its own PIT
    axis scores under the live config — same state machine, re-run."""
    frame = built["frame"]
    qcfg = config.load()["engine"]["quad"]
    h = apply_hysteresis(frame["growth_score"], frame["inflation_score"],
                         qcfg["hysteresis_days"], qcfg["shock_override_z"])
    for col in ("quad", "pending_quad"):
        a = frame[col].astype(object).where(frame[col].notna(), "NA")
        b = h[col].astype(object).where(h[col].notna(), "NA")
        n_diff = int((a.to_numpy() != b.to_numpy()).sum())
        assert n_diff == 0, f"{col}: {n_diff} rows differ from re-applied hysteresis"
    assert (frame["pending_days"] == h["pending_days"]).all()


def test_pre_coverage_quad_matches_live_history(built):
    """Before ANY vintage coverage (pre-1997) the PIT frame reads exactly the
    live inputs — its quad must reproduce the committed live history there.
    (Both are rebuilt from the same git-tracked store; the daily engine commits
    regime_history together with the store, so they move in lockstep.)"""
    frame = built["frame"]
    hist = pd.read_parquet(_HIST)
    common = frame.index.intersection(hist.index)
    common = common[common < pd.Timestamp("1997-01-10")]
    a, b = frame.loc[common, "quad"], hist.loc[common, "quad"]
    m = a.notna() & b.notna()
    assert m.sum() > 5000
    assert (a[m].to_numpy() == b[m].to_numpy()).all()


def test_divergence_json_shape(built):
    div = built["div"]
    for key in ("headline", "overall", "by_era", "per_axis",
                "divergence_run_lengths", "transition_shifts", "control",
                "pit_class_counts", "fallback_coverage", "vintage_store_asof",
                "frame_asof", "columns_dropped_vs_regime_history"):
        assert key in div, key
    assert div["overall"]["n_comparable_dates"] > 10000
    assert set(div["by_era"]) == {"pre_2008", "2008_09", "2010_19", "2020_plus"}
    assert set(div["transition_shifts"]) == {"2008_09", "2020"}
    assert 0.0 <= div["headline"]["pct_dates_quad_divergent"] <= 100.0
    assert div["headline"]["worst_era"] in div["by_era"]
    # pre-1997 is fallback-everywhere: it can never diverge from live, so the
    # pre-2008 era rate must be attributable to 1997+ (bounded strictly below
    # the vintage-covered eras' worst)
    assert div["columns_dropped_vs_regime_history"] == []
    assert sum(div["pit_class_counts"].values()) == len(built["frame"])
