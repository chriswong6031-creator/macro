"""Hermetic tests for engine/radar_ic.py — the Divergence Radar IC harness.

All tests are self-contained (tmp_path, synthetic data, monkeypatched prices).
No live data, no network, no side-effects on the real store.

Key assertions:
  1. snapshot() appends correctly from radar.json + radar_ticker.json; idempotent.
  2. compute_ic() → n_matured:0 + accruing note when snapshots are too fresh.
  3. compute_ic() with synthetic matured obs (monotonic edge↔return) → ic_all > 0.
  4. Hit-rate buckets: high-edge → higher hit-rate in a controlled setup.
  5. Directional accuracy: POSITIVE_DIVERGENCE correctly counted.
  6. _spearman_ic: known monotonic → 1.0; constant → None.
  7. build script degrades cleanly when site files absent.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from engine import radar_ic as ric


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_radar_json(tmp_path: Path, flags: list[dict]) -> None:
    """Write a minimal radar.json to site/basketdata/."""
    p = tmp_path / "site" / "basketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "radar.json").write_text(json.dumps({"flags": flags}))


def _write_radar_ticker_json(tmp_path: Path, tickers: list[dict]) -> None:
    p = tmp_path / "site" / "basketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "radar_ticker.json").write_text(json.dumps({"tickers": tickers}))


def _write_membership(tmp_path: Path, mapping: dict[str, str]) -> None:
    """mapping: {basket_id: etf_proxy}"""
    d = tmp_path / "data" / "baskets"
    d.mkdir(parents=True, exist_ok=True)
    baskets = {k: {"etf_proxy": v} for k, v in mapping.items()}
    (d / "membership.json").write_text(json.dumps({"baskets": baskets}))


def _price_parquet(tmp_path: Path, ticker: str, start: str, end: str, ret: float) -> None:
    """Write data/yahoo/<ticker>.parquet: close grows linearly from 100 to 100*(1+ret)."""
    d = tmp_path / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, end)
    close = pd.Series(
        [100.0 * (1 + ret * i / max(len(idx) - 1, 1)) for i in range(len(idx))],
        index=idx,
    )
    pd.DataFrame({"close": close}).to_parquet(d / f"{ticker}.parquet")


def _write_snapshots(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "radar"
    p.mkdir(parents=True, exist_ok=True)
    with (p / "edge_snapshots.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# 1. snapshot() accrual
# ---------------------------------------------------------------------------

def test_snapshot_appends_baskets_and_tickers(tmp_path):
    _write_membership(tmp_path, {"ai_infra": "SMH", "housing": "XHB"})
    _write_radar_json(tmp_path, [
        {"basket": "ai_infra", "state": "POSITIVE_DIVERGENCE", "edge_score": 80},
        {"basket": "housing", "state": "NEGATIVE_DIVERGENCE", "edge_score": 55},
        {"basket": "sleepy", "state": "QUIET", "edge_score": 10},   # QUIET → skip
    ])
    _write_radar_ticker_json(tmp_path, [
        {"ticker": "NVDA", "state": "POSITIVE_DIVERGENCE", "edge_score": 75},
        {"ticker": "QUIET_TICKER", "state": "QUIET", "edge_score": 5},  # skip
    ])
    n = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n == 3  # ai_infra basket + housing basket + NVDA ticker

    p = tmp_path / "data" / "radar" / "edge_snapshots.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    subjects = {r["subject"] for r in rows}
    assert "ai_infra" in subjects
    assert "housing" in subjects
    assert "NVDA" in subjects
    assert "sleepy" not in subjects  # QUIET filtered
    assert "QUIET_TICKER" not in subjects


def test_snapshot_idempotent(tmp_path):
    _write_membership(tmp_path, {"ai_infra": "SMH"})
    _write_radar_json(tmp_path, [
        {"basket": "ai_infra", "state": "POSITIVE_DIVERGENCE", "edge_score": 80},
    ])
    _write_radar_ticker_json(tmp_path, [])
    n1 = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    n2 = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n1 == 1
    assert n2 == 0   # same date+subject → no double-append
    p = tmp_path / "data" / "radar" / "edge_snapshots.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(rows) == 1


def test_snapshot_no_proxy_skipped(tmp_path):
    """Baskets without an ETF proxy should be silently skipped."""
    _write_membership(tmp_path, {})   # no proxy for anything
    _write_radar_json(tmp_path, [
        {"basket": "orphan", "state": "POSITIVE_DIVERGENCE", "edge_score": 70},
    ])
    _write_radar_ticker_json(tmp_path, [])
    n = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n == 0


def test_snapshot_two_different_dates_both_kept(tmp_path):
    _write_membership(tmp_path, {"ai_infra": "SMH"})
    _write_radar_json(tmp_path, [
        {"basket": "ai_infra", "state": "POSITIVE_DIVERGENCE", "edge_score": 80},
    ])
    _write_radar_ticker_json(tmp_path, [])
    ric.snapshot(today=date(2026, 6, 19), root=tmp_path)
    ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    p = tmp_path / "data" / "radar" / "edge_snapshots.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(rows) == 2
    assert {r["date"] for r in rows} == {"2026-06-19", "2026-06-20"}


# ---------------------------------------------------------------------------
# 2. compute_ic() — too-fresh snapshots → n_matured:0
# ---------------------------------------------------------------------------

def test_compute_ic_accruing_when_too_fresh(tmp_path):
    rows = [
        {"date": "2026-06-19", "kind": "basket", "subject": "ai_infra",
         "ticker": "SMH", "edge_score": 80, "state": "POSITIVE_DIVERGENCE"},
    ]
    _write_snapshots(tmp_path, rows)
    result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)
    assert result["n_matured"] == 0
    assert result["ic_all"] is None
    assert "accruing" in result["note"].lower() or "Accruing" in result["note"]
    assert result["schema"] == "radar_ic.v1"


# ---------------------------------------------------------------------------
# 3. compute_ic() with synthetic matured obs → ic_all > 0
# ---------------------------------------------------------------------------

def test_compute_ic_positive_with_monotonic_edge_return(tmp_path):
    """Synthetic: edge_score 10..100 predicts fwd_rel_return 0.01..0.10.
    With a perfectly monotonic relationship, Spearman IC should be +1.0.
    We mock _fwd_rel_return so no real price data is needed."""

    # Snapshots dated 30 days ago — definitely matured at 21d horizon
    snap_date = "2026-05-21"   # 30d before 2026-06-20
    n_obs = 15
    edge_scores = [10 + (90 // (n_obs - 1)) * i for i in range(n_obs)]
    rows = [
        {"date": snap_date, "kind": "basket", "subject": f"basket_{i}",
         "ticker": f"ETF{i}", "edge_score": edge_scores[i],
         "state": "POSITIVE_DIVERGENCE"}
        for i in range(n_obs)
    ]
    _write_snapshots(tmp_path, rows)

    # Map each ETFi ticker to a specific return proportional to i
    fwd_return_map = {f"ETF{i}": 0.01 * (i + 1) for i in range(n_obs)}

    def _mock_fwd_rel_return(ticker, root, start_date, horizon_d):
        return fwd_return_map.get(ticker)

    # Also need _is_matured to return True — we do this by having _covers return True
    def _mock_covers(ticker, root, check_by):
        return True

    with patch.object(ric, "_fwd_rel_return", side_effect=_mock_fwd_rel_return), \
         patch.object(ric, "_covers", side_effect=_mock_covers):
        result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)

    assert result["n_matured"] == n_obs
    assert result["ic_all"] is not None
    assert result["ic_all"] > 0.9, f"Expected ic_all near 1.0, got {result['ic_all']}"


# ---------------------------------------------------------------------------
# 4. Hit-rate buckets
# ---------------------------------------------------------------------------

def test_hit_rate_by_bucket_high_edge_scores_higher(tmp_path):
    """High-edge obs (70-100) have positive returns; low-edge (0-40) negative.
    Hit rates should reflect this: 70-100 bucket > 0-40 bucket."""
    snap_date = "2026-05-21"
    # Low-bucket: edge 10-35, POSITIVE_DIVERGENCE, negative fwd returns
    low_rows = [
        {"date": snap_date, "kind": "basket", "subject": f"low_{i}",
         "ticker": f"LOW{i}", "edge_score": 10 + i * 5,
         "state": "POSITIVE_DIVERGENCE"}
        for i in range(5)  # edge 10,15,20,25,30
    ]
    # High-bucket: edge 70-95, POSITIVE_DIVERGENCE, positive fwd returns
    high_rows = [
        {"date": snap_date, "kind": "basket", "subject": f"high_{i}",
         "ticker": f"HIGH{i}", "edge_score": 70 + i * 5,
         "state": "POSITIVE_DIVERGENCE"}
        for i in range(6)  # edge 70,75,80,85,90,95
    ]
    _write_snapshots(tmp_path, low_rows + high_rows)

    low_returns = {f"LOW{i}": -0.05 - 0.01 * i for i in range(5)}
    high_returns = {f"HIGH{i}": 0.05 + 0.01 * i for i in range(6)}
    all_returns = {**low_returns, **high_returns}

    def _mock_fwd(ticker, root, start_date, horizon_d):
        return all_returns.get(ticker)

    def _mock_covers(ticker, root, check_by):
        return True

    with patch.object(ric, "_fwd_rel_return", side_effect=_mock_fwd), \
         patch.object(ric, "_covers", side_effect=_mock_covers):
        result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)

    bb = result["by_bucket"]
    low_hr = bb["0-40"]["hit_rate"]
    high_hr = bb["70-100"]["hit_rate"]
    assert low_hr is not None and high_hr is not None
    assert high_hr > low_hr, (
        f"Expected high bucket hit_rate {high_hr} > low bucket {low_hr}"
    )
    assert high_hr == 1.0   # all high-edge obs had positive returns
    assert low_hr == 0.0    # all low-edge obs had negative returns


# ---------------------------------------------------------------------------
# 5. Directional accuracy
# ---------------------------------------------------------------------------

def test_directional_accuracy_by_state(tmp_path):
    snap_date = "2026-05-21"
    rows = [
        # POSITIVE_DIVERGENCE + positive return = correct
        {"date": snap_date, "kind": "basket", "subject": "pos_ok_1",
         "ticker": "POS1", "edge_score": 80, "state": "POSITIVE_DIVERGENCE"},
        {"date": snap_date, "kind": "basket", "subject": "pos_ok_2",
         "ticker": "POS2", "edge_score": 70, "state": "POSITIVE_DIVERGENCE"},
        # POSITIVE_DIVERGENCE + negative return = incorrect
        {"date": snap_date, "kind": "basket", "subject": "pos_bad",
         "ticker": "POSBAD", "edge_score": 75, "state": "POSITIVE_DIVERGENCE"},
        # NEGATIVE_DIVERGENCE + negative return = correct
        {"date": snap_date, "kind": "basket", "subject": "neg_ok",
         "ticker": "NEG1", "edge_score": 30, "state": "NEGATIVE_DIVERGENCE"},
    ]
    _write_snapshots(tmp_path, rows)

    ret_map = {"POS1": 0.05, "POS2": 0.03, "POSBAD": -0.04, "NEG1": -0.06}

    with patch.object(ric, "_fwd_rel_return", side_effect=lambda t, *a, **k: ret_map.get(t)), \
         patch.object(ric, "_covers", return_value=True):
        result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)

    bs = result["by_state"]
    pos_acc = bs.get("POSITIVE_DIVERGENCE", {}).get("dir_accuracy")
    neg_acc = bs.get("NEGATIVE_DIVERGENCE", {}).get("dir_accuracy")
    assert pos_acc == pytest.approx(2 / 3, abs=0.01)   # 2 correct out of 3
    assert neg_acc == 1.0   # 1 correct out of 1


# ---------------------------------------------------------------------------
# 6. _spearman_ic unit tests
# ---------------------------------------------------------------------------

def test_spearman_ic_perfect_positive():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert ric._spearman_ic(xs, ys) == pytest.approx(1.0, abs=1e-4)


def test_spearman_ic_perfect_negative():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [0.5, 0.4, 0.3, 0.2, 0.1]
    assert ric._spearman_ic(xs, ys) == pytest.approx(-1.0, abs=1e-4)


def test_spearman_ic_too_few_points():
    assert ric._spearman_ic([1.0, 2.0], [0.1, 0.2]) is None


def test_spearman_ic_tied_ranks():
    # All xs same → zero variance → should return None (den=0) or 0.0
    xs = [5.0, 5.0, 5.0]
    ys = [1.0, 2.0, 3.0]
    result = ric._spearman_ic(xs, ys)
    # den = 0 → None is acceptable; some implementations return 0
    assert result is None or result == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
# 7. build script degrades cleanly when site files absent
# ---------------------------------------------------------------------------

def test_compute_ic_degrades_when_no_snapshots(tmp_path):
    """No snapshot file → n_matured:0, no exception."""
    result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)
    assert result["schema"] == "radar_ic.v1"
    assert result["n_matured"] == 0
    assert result["ic_all"] is None


def test_snapshot_degrades_when_site_files_absent(tmp_path):
    """No radar.json → snapshot() returns 0 but doesn't raise."""
    n = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n == 0


def test_full_pipeline_first_run(tmp_path):
    """End-to-end: snapshot() + compute_ic() → valid JSON, n_matured=0, no exception."""
    _write_membership(tmp_path, {"defense": "ITA"})
    _write_radar_json(tmp_path, [
        {"basket": "defense", "state": "POSITIVE_DIVERGENCE", "edge_score": 72},
    ])
    _write_radar_ticker_json(tmp_path, [])

    n = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n == 1

    result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)
    assert result["n_snapshots"] == 1
    assert result["n_matured"] == 0
    # Valid schema and required keys present
    for key in ("schema", "as_of", "n_snapshots", "n_matured", "ic_all",
                "by_bucket", "by_state", "note"):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Brief §9 — Radar clock unification tests
# ---------------------------------------------------------------------------

def test_snapshot_stamps_horizon_d_from_hypotheses(tmp_path):
    """snapshot() reads horizon_d from hypotheses in radar.json and stamps it on rows."""
    _write_membership(tmp_path, {"ai_infra": "SMH"})
    # radar.json with hypotheses carrying horizon_d=63
    p = tmp_path / "site" / "basketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "radar.json").write_text(json.dumps({
        "flags": [
            {"basket": "ai_infra", "state": "POSITIVE_DIVERGENCE", "edge_score": 80},
        ],
        "hypotheses": [
            {"subject": "ai_infra", "horizon_d": 63, "id": "2026-06-20-radar-ai_infra"},
        ],
    }))
    _write_radar_ticker_json(tmp_path, [])

    n = ric.snapshot(today=date(2026, 6, 20), root=tmp_path)
    assert n == 1

    snap_file = tmp_path / "data" / "radar" / "edge_snapshots.jsonl"
    rows = [json.loads(l) for l in snap_file.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0].get("horizon_d") == 63, (
        "Expected horizon_d=63 to be stamped on the snapshot row"
    )


def test_63d_snapshot_not_matured_by_21d_pass_before_21_days(tmp_path):
    """A snapshot stamped with horizon_d=63 must NOT be counted matured by the 21d
    IC pass when fewer than 21 calendar days of price data have elapsed.

    Concretely: snapshot dated today; we run compute_ic with horizon_d=21 today.
    The row has horizon_d=63, so it is excluded from the 21d eligible set entirely.
    """
    # Write a snapshot with horizon_d=63, dated today (0 days old)
    _write_snapshots(tmp_path, [
        {"date": "2026-06-20", "kind": "basket", "subject": "ai_infra",
         "ticker": "SMH", "edge_score": 80, "state": "POSITIVE_DIVERGENCE",
         "horizon_d": 63},
    ])

    # Even if covers returns True, the row is excluded from the 21d horizon pass
    # because its horizon_d=63 != 21.
    with patch.object(ric, "_covers", return_value=True), \
         patch.object(ric, "_fwd_rel_return", return_value=0.05):
        result = ric.compute_ic(today=date(2026, 6, 20), horizon_d=21, root=tmp_path)

    # The 21d primary block must show n_matured=0 (row excluded by horizon mismatch)
    assert result["n_matured"] == 0, (
        "horizon_d=63 snapshot must not appear in the 21d maturity count"
    )
    # But it should appear in the 63d horizon block (once enough time has passed —
    # here today==snap_date so still too fresh, but eligible set is non-empty)
    block_63 = result.get("by_horizon", {}).get("63", {})
    # Still not matured (0 days old < 63), but the eligible set is non-zero
    # We can check that the snapshot is not excluded by horizon filter:
    assert block_63 is not None, "by_horizon['63'] block must be present"
    # n_matured=0 because 0 days < 63 days required, but no error/exclusion
    assert block_63["n_matured"] == 0


def test_legacy_snapshot_without_horizon_d_gradeable_at_all_horizons(tmp_path):
    """A legacy snapshot lacking `horizon_d` should be eligible at every horizon
    (backward-compatible — treat as gradeable at all)."""
    # Snapshot 70 days old — old enough for both 21d and 63d horizons
    snap_date = "2026-04-21"   # 70 days before 2026-06-30
    rows = [
        {"date": snap_date, "kind": "basket", "subject": f"b{i}",
         "ticker": f"T{i}", "edge_score": 50 + i * 5,
         "state": "POSITIVE_DIVERGENCE"}  # no horizon_d field — legacy
        for i in range(5)
    ]
    _write_snapshots(tmp_path, rows)

    fwd_map = {f"T{i}": 0.01 * (i + 1) for i in range(5)}

    with patch.object(ric, "_fwd_rel_return", side_effect=lambda t, *a, **k: fwd_map.get(t)), \
         patch.object(ric, "_covers", return_value=True):
        result = ric.compute_ic(today=date(2026, 6, 30), horizons=[21, 63], root=tmp_path)

    # Legacy rows should appear in both horizon blocks
    block_21 = result["by_horizon"]["21"]
    block_63 = result["by_horizon"]["63"]
    assert block_21["n_matured"] == 5, "Legacy rows must be gradeable at 21d"
    assert block_63["n_matured"] == 5, "Legacy rows must be gradeable at 63d"


def test_compute_ic_emits_per_horizon_blocks(tmp_path):
    """compute_ic() output must contain by_horizon with blocks for each requested horizon."""
    result = ric.compute_ic(today=date(2026, 6, 20), horizons=[21, 63], root=tmp_path)
    assert "by_horizon" in result, "compute_ic must emit by_horizon"
    assert "21" in result["by_horizon"], "by_horizon must have '21' block"
    assert "63" in result["by_horizon"], "by_horizon must have '63' block"
    # Each block must have the required keys
    for h_key in ("21", "63"):
        block = result["by_horizon"][h_key]
        for key in ("n_matured", "ic_all", "by_bucket", "by_state", "note"):
            assert key in block, f"by_horizon['{h_key}'] missing key: {key}"


def test_compute_ic_legacy_top_level_fields_are_primary_horizon(tmp_path):
    """Legacy top-level fields (n_matured, ic_all, by_bucket, by_state) must
    reflect the primary horizon_d (21d default) — backward compat for consumers."""
    snap_date = "2026-04-21"  # 70 days before 2026-06-30
    rows = [
        {"date": snap_date, "kind": "basket", "subject": f"b{i}",
         "ticker": f"T{i}", "edge_score": 50 + i * 5,
         "state": "POSITIVE_DIVERGENCE",
         "horizon_d": 21}  # explicit 21d snapshot
        for i in range(5)
    ]
    _write_snapshots(tmp_path, rows)

    fwd_map = {f"T{i}": 0.01 * (i + 1) for i in range(5)}
    with patch.object(ric, "_fwd_rel_return", side_effect=lambda t, *a, **k: fwd_map.get(t)), \
         patch.object(ric, "_covers", return_value=True):
        result = ric.compute_ic(today=date(2026, 6, 30), horizon_d=21,
                                horizons=[21, 63], root=tmp_path)

    # Top-level n_matured must match the 21d block
    block_21 = result["by_horizon"]["21"]
    assert result["n_matured"] == block_21["n_matured"]
    assert result["ic_all"] == block_21["ic_all"]
    assert result["by_bucket"] == block_21["by_bucket"]


def test_radar_constants_exported(tmp_path):
    """Verify the new named constants exist and have the expected values in radar.py."""
    from engine import radar as r
    assert r.SEED_HORIZON_D == 63, "SEED_HORIZON_D must be 63"
    assert r.CHECK_BY_PAD_D == 91, "CHECK_BY_PAD_D must be 91"
    # Back-compat alias must still be present
    assert r.HORIZON_D == r.SEED_HORIZON_D, "HORIZON_D alias must equal SEED_HORIZON_D"


def test_hypotheses_stamped_horizon_d(tmp_path):
    """_hypotheses() must stamp horizon_d=SEED_HORIZON_D on every hypothesis."""
    from engine import radar as r

    mem = {"ai_infra": {"etf_proxy": "SMH"}}
    flags = [
        {"basket": "ai_infra", "state": "POSITIVE_DIVERGENCE", "salience": 0.8,
         "note": "test note"},
    ]
    hypotheses = r._hypotheses(flags, mem, "2026-06-20")
    assert len(hypotheses) == 1
    h = hypotheses[0]
    assert h["horizon_d"] == r.SEED_HORIZON_D, (
        f"hypothesis horizon_d {h['horizon_d']} != SEED_HORIZON_D {r.SEED_HORIZON_D}"
    )
    # check_by should be CHECK_BY_PAD_D calendar days from asof
    expected_check_by = (pd.Timestamp("2026-06-20") + pd.Timedelta(days=r.CHECK_BY_PAD_D)
                         ).date().isoformat()
    assert h["check_by"] == expected_check_by, (
        f"check_by {h['check_by']} != expected {expected_check_by}"
    )
