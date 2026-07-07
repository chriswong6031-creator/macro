"""IX-1 substrate acceptance tests for the index-level hazard panel (v0).

Tests:
1. Schema parity: panel_index_v0.parquet has EXACTLY the member panel columns
   (same order, same dtypes) plus the four covariate columns; families/ids match v0 spec.
2. Detector-parameter parity: the index ZigZag pct is the us_sector value.
3. Label conventions: y1/y3/y6 at a known synthetic pivot (via the SAME imported
   row builder the real build uses).
4. Covariate join is PIT-pure: values at t are unchanged when later months are
   appended to the member panel and the sync gauge.
5. Covariate math matches the FT-4 definitions on a hand-computable cross-section.
6. index_km fallback: <min_rows rows per direction → family-pooled rate with
   source label; >=min_rows → entity rate.
7. Determinism: covariate attach and KM table are bit-identical across runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

from engine.index_km import KM_MIN_ROWS_DEFAULT, index_km_table, km_predict_index
from scripts.build_hazard_panel import (
    ZZ_PCT_US,
    _build_instrument_rows,
    _detect_turns_for_instrument,
)
from scripts.build_index_hazard_panel import (
    BLOC_IDS,
    COVARIATE_COLS,
    INDEX_FAMILY,
    ZZ_PCT_INDEX,
    attach_index_covariates,
    sync_series_from_gauge,
)

_MEMBER_PANEL = _REPO / "data/hazard/panel_price_c4414dcb.parquet"
_INDEX_PANEL = _REPO / "data/hazard/panel_index_v0.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _zigzag_close(swings: list[tuple[int, float]], start: str = "2000-01-03",
                  p0: float = 100.0) -> pd.Series:
    """Deterministic piecewise-exponential daily close: each (n_days, total_return)
    leg moves the price monotonically by total_return over n_days business days."""
    vals, p = [], p0
    for n_days, ret in swings:
        step = (1.0 + ret) ** (1.0 / n_days)
        for _ in range(n_days):
            p *= step
            vals.append(p)
    idx = pd.date_range(start, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx)


def _mini_member_panel(months: list[str], ids: list[str], family: str,
                       pos_by_id: dict[str, float]) -> pd.DataFrame:
    """Member-panel-shaped frame with one (id, month) row (single direction)."""
    rows = []
    for mth in months:
        for iid in ids:
            rows.append({
                "date": pd.Timestamp(mth), "id": iid, "family": family,
                "direction": "up", "pos_osc": pos_by_id[iid],
            })
    return pd.DataFrame(rows)


def _mini_index_rows(months: list[str], family: str = "us_market",
                     iid: str = "SPY") -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": pd.Timestamp(mth), "id": iid, "family": family} for mth in months]
    )


def _km_panel(rows_spec: list[tuple[str, str, str, int, float]]) -> pd.DataFrame:
    """rows_spec: (id, family, direction, n_rows, y3_rate). y1=0, y6=y3 for simplicity."""
    rows = []
    for iid, fam, direction, n, rate in rows_spec:
        n_events = int(round(n * rate))
        for i in range(n):
            y3 = 1 if i < n_events else 0
            rows.append({
                "id": iid, "family": fam, "direction": direction,
                "y1": 0, "y3": y3, "y6": y3,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1+2. Schema parity with the member panel / detector-parameter parity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (_MEMBER_PANEL.exists() and _INDEX_PANEL.exists()),
                    reason="committed panel artifacts required")
def test_schema_parity_with_member_panel():
    member = pd.read_parquet(_MEMBER_PANEL)
    index = pd.read_parquet(_INDEX_PANEL)

    # Exact column order: member schema first, then the four covariates.
    assert list(index.columns) == list(member.columns) + COVARIATE_COLS

    # Exact dtype parity on the shared columns (so W4.2 fit machinery drops in).
    for col in member.columns:
        assert index[col].dtype == member[col].dtype, (
            f"dtype mismatch on {col}: index={index[col].dtype} member={member[col].dtype}"
        )

    # v0 universe: 8 entities, families as specified.
    assert set(index["id"].unique()) == set(INDEX_FAMILY)
    assert set(index["family"].unique()) == {"us_market", "bloc"}
    assert (index.loc[index["id"] == "SPY", "family"] == "us_market").all()
    for iid in BLOC_IDS:
        assert (index.loc[index["id"] == iid, "family"] == "bloc").all()

    # Same epoch stamp as the member panel (identical detector config).
    assert index["turn_def_version"].iloc[0] == member["turn_def_version"].iloc[0]

    # Label sanity on the real artifact.
    assert ((index["y1"] <= index["y3"]) & (index["y3"] <= index["y6"])).all()
    assert index.loc[index["censored"] == 1, ["y1", "y3", "y6"]].to_numpy().sum() == 0


def test_index_zigzag_pct_is_us_sector_param():
    """The documented v0 choice: SPY (and blocs) use the us_sector threshold."""
    assert ZZ_PCT_INDEX == ZZ_PCT_US == 14.0


# ---------------------------------------------------------------------------
# 3. Label conventions at a known synthetic pivot
# ---------------------------------------------------------------------------

def test_y_labels_at_known_synthetic_pivot():
    """Three large alternating legs; every row's y1/y3/y6 must equal the horizon
    indicator of its own event_date, and rows near a known pivot get y3=1."""
    # ~12m up +80%, ~7m down -30%, ~12m up +80%, ~7m down -30%, ~9m up tail
    close = _zigzag_close([(252, 0.80), (147, -0.30), (252, 0.80), (147, -0.30), (189, 0.50)])
    turns = _detect_turns_for_instrument(close, "SYN", ZZ_PCT_INDEX)
    confirmed = [t for t in turns if not t.get("provisional")]
    assert len(confirmed) >= 3, "synthetic zigzag must produce confirmed turns"

    month_ends = pd.date_range(close.index.min(), close.index.max(), freq="ME")
    rows = _build_instrument_rows(
        iid="SYN", family="us_market", close=close, pct=ZZ_PCT_INDEX,
        month_ends=month_ends, all_turns=turns,
        per_id_medians_fn=lambda iid, t: {"up": None, "n_up": 0, "down": None, "n_down": 0},
        family_median_fn=lambda direction, t: None,
        regime_hist=pd.DataFrame(index=pd.DatetimeIndex([])),
        bench_close=None,
        turn_def_ver="test", engine_fp="test",
    )
    assert len(rows) > 0
    df = pd.DataFrame(rows)

    # Label convention: y_h == 1 iff event_date <= date + h months (censored → all 0).
    for h in (1, 3, 6):
        expect = df.apply(
            lambda r: int(pd.notnull(r["event_date"])
                          and r["event_date"] <= r["date"] + pd.DateOffset(months=h)),
            axis=1,
        )
        assert (df[f"y{h}"] == expect).all(), f"y{h} deviates from label convention"

    # At a KNOWN pivot: rows dated within (pivot-3m, pivot) in the leg that ends
    # at that pivot must carry y3=1.
    events = df.loc[df["event_date"].notna(), "event_date"].unique()
    assert len(events) >= 1
    ev = pd.Timestamp(sorted(events)[0])
    near = df[(df["event_date"] == ev) & (df["date"] < ev)
              & (df["date"] >= ev - pd.DateOffset(months=3))]
    assert len(near) > 0 and (near["y3"] == 1).all()

    # Open final leg → censored rows with zero labels.
    tail = df[df["censored"] == 1]
    assert len(tail) > 0
    assert tail[["y1", "y3", "y6"]].to_numpy().sum() == 0


# ---------------------------------------------------------------------------
# 4. Covariate join PIT purity
# ---------------------------------------------------------------------------

def test_covariate_join_pit_pure_under_append():
    """Covariates at month t must be identical before/after appending later months."""
    early = ["2020-01-31", "2020-02-29", "2020-03-31"]
    late = ["2020-04-30", "2020-05-31"]
    ids = ["XLK", "XLF", "XLE"]
    pos = {"XLK": 80.0, "XLF": 25.0, "XLE": 55.0}

    member_early = _mini_member_panel(early, ids, "us_sector", pos)
    gauge_early = {"families": {"us_sector": [
        {"date": m, "sync": 0.42, "n": 3} for m in early
    ]}}
    idx_rows = _mini_index_rows(early)

    out1 = attach_index_covariates(idx_rows, member_early, gauge_early)

    # Append later months with DIFFERENT cross-section values.
    pos_late = {"XLK": 10.0, "XLF": 90.0, "XLE": 90.0}
    member_full = pd.concat(
        [member_early, _mini_member_panel(late, ids, "us_sector", pos_late)],
        ignore_index=True,
    )
    gauge_full = {"families": {"us_sector": (
        gauge_early["families"]["us_sector"]
        + [{"date": m, "sync": 0.99, "n": 3} for m in late]
    )}}
    out2 = attach_index_covariates(_mini_index_rows(early + late), member_full, gauge_full)

    merged = out2[out2["date"].isin(pd.to_datetime(early))].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        out1[COVARIATE_COLS].reset_index(drop=True), merged[COVARIATE_COLS]
    )


def test_covariate_math_matches_ft4_definitions():
    """Hand-computable cross-section: breadth thresholds >=70 / <=30, std/100, gauge sync."""
    months = ["2020-01-31"]
    ids = ["A", "B", "C", "D"]
    pos = {"A": 75.0, "B": 70.0, "C": 30.0, "D": 45.0}
    member = _mini_member_panel(months, ids, "us_sector", pos)
    gauge = {"families": {"us_sector": [{"date": "2020-01-31", "sync": 0.5}]}}
    out = attach_index_covariates(_mini_index_rows(months), member, gauge)
    row = out.iloc[0]
    vals = np.array([75.0, 70.0, 30.0, 45.0])
    assert row["phase_breadth_late"] == pytest.approx(0.5)    # 75, 70 are >= 70
    assert row["phase_breadth_early"] == pytest.approx(0.25)  # 30 is <= 30
    assert row["pos_dispersion"] == pytest.approx(float(np.std(vals)) / 100.0)
    assert row["sync_family"] == pytest.approx(0.5)


def test_bloc_cross_section_excludes_blocs():
    """Bloc rows must use the pure-country cross-section (blocs excluded)."""
    months = ["2020-01-31"]
    ids = ["EWJ", "EWG", "EFA"]  # EFA is a bloc inside the member country family
    pos = {"EWJ": 80.0, "EWG": 80.0, "EFA": 10.0}
    member = _mini_member_panel(months, ids, "country", pos)
    gauge = {"families": {"country": [{"date": "2020-01-31", "sync": 0.7}]}}
    out = attach_index_covariates(
        _mini_index_rows(months, family="bloc", iid="EFA"), member, gauge
    )
    # If EFA leaked into its own cross-section, breadth_late would be 2/3.
    assert out.iloc[0]["phase_breadth_late"] == pytest.approx(1.0)


def test_sync_series_from_gauge_shape():
    gauge = {"families": {"us_sector": [
        {"date": "1999-09-30", "sync": 0.9572, "n": 3},
        {"date": "1999-10-31", "sync": None, "n": 4},   # null sync skipped
        {"date": "1999-11-30", "sync": 0.2359, "n": 6},
    ]}}
    s = sync_series_from_gauge(gauge, "us_sector")
    assert list(s.index) == [pd.Timestamp("1999-09-30"), pd.Timestamp("1999-11-30")]
    assert s.iloc[0] == pytest.approx(0.9572)
    assert sync_series_from_gauge(gauge, "nope").empty


# ---------------------------------------------------------------------------
# 6. index_km fallback logic
# ---------------------------------------------------------------------------

def test_index_km_entity_vs_family_fallback():
    panel = _km_panel([
        ("BIG",  "bloc", "up", 50, 0.40),   # >= 30 rows → entity rate
        ("TINY", "bloc", "up", 10, 0.90),   # < 30 rows → family-pooled fallback
    ])
    tbl = index_km_table(panel, min_rows=KM_MIN_ROWS_DEFAULT)

    big = tbl["entities"]["BIG"]["up"]["horizons"][3]
    assert big["source"] == "entity"
    assert big["p"] == pytest.approx(0.40)
    assert big["n"] == 50 and big["events"] == 20

    fam = tbl["families"]["bloc"]["up"][3]
    assert fam["n"] == 60 and fam["events"] == 29  # 20 + 9

    tiny = tbl["entities"]["TINY"]["up"]["horizons"][3]
    assert tiny["source"] == "family_pooled"
    assert tiny["p"] == pytest.approx(29 / 60)
    assert tiny["own_n"] == 10 and tiny["own_events"] == 9  # own counts stay auditable

    # Direction with NO family rows at all → global fallback.
    panel2 = pd.concat(
        [panel, _km_panel([("LONE", "solo_family", "down", 5, 0.2)])],
        ignore_index=True,
    )
    tbl2 = index_km_table(panel2)
    lone = tbl2["entities"]["LONE"]["down"]["horizons"][3]
    # solo_family HAS down rows (its own), so it stays family_pooled...
    assert lone["source"] == "family_pooled"
    # ...but LONE has no 'up' rows: family empty for up → global.
    lone_up = tbl2["entities"]["LONE"]["up"]["horizons"][3]
    assert lone_up["source"] == "global"
    assert lone_up["p"] == pytest.approx(29 / 60)


def test_index_km_requires_columns():
    with pytest.raises(ValueError, match="missing columns"):
        index_km_table(pd.DataFrame({"id": ["A"], "family": ["f"]}))


def test_km_predict_index_matches_table():
    panel = _km_panel([
        ("BIG",  "bloc", "up", 40, 0.50),
        ("TINY", "bloc", "up", 5, 0.0),
    ])
    tbl = index_km_table(panel)
    rows = pd.DataFrame([
        {"id": "BIG",  "family": "bloc", "direction": "up"},
        {"id": "TINY", "family": "bloc", "direction": "up"},
        {"id": "NEW",  "family": "bloc", "direction": "up"},      # unseen id → family
        {"id": "NEW2", "family": "nofam", "direction": "up"},     # unseen family → global
    ])
    preds = km_predict_index(tbl, rows)
    assert preds[3][0] == pytest.approx(0.50)                     # entity rate
    assert preds[3][1] == pytest.approx(tbl["families"]["bloc"]["up"][3]["p"])
    assert preds[3][2] == pytest.approx(tbl["families"]["bloc"]["up"][3]["p"])
    assert preds[3][3] == pytest.approx(tbl["global"]["up"][3]["p"])


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------

def test_covariate_attach_deterministic():
    months = ["2020-01-31", "2020-02-29"]
    member = _mini_member_panel(months, ["XLK", "XLF"], "us_sector",
                                {"XLK": 71.0, "XLF": 29.0})
    gauge = {"families": {"us_sector": [{"date": m, "sync": 0.33} for m in months]}}
    a = attach_index_covariates(_mini_index_rows(months), member, gauge)
    b = attach_index_covariates(_mini_index_rows(months), member, gauge)
    pd.testing.assert_frame_equal(a, b)


def test_index_km_deterministic():
    panel = _km_panel([
        ("BIG", "bloc", "up", 50, 0.40),
        ("TINY", "bloc", "down", 10, 0.90),
    ])
    assert index_km_table(panel) == index_km_table(panel)
