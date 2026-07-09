"""Tests for engine/hk_narrative.py — GDELT Narrative/Attention-Shock organ.

Coverage:
  1. Parser on a REAL saved GDELT fixture (mirrors actual timelinevol/timelinetone JSON)
  2. attention_shock_z on synthetic volume with a known spike
  3. Young-series exclusion (entity with < MIN_BASELINE_OBS obs → no state)
  4. Fail-open when the store is missing/stale or an entity is absent
  5. Ledger idempotency + CN_LANE gate
  6. snapshot() structure + display_only flag
  7. Tone percentile direction

All writes are isolated to tmp_path. No writes to data/ or site/.
git status --porcelain MUST be empty after these tests.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.hk_narrative as NARRATIVE
from collectors.hk_gdelt import ENTITIES

# Fixtures directory (real GDELT response files)
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vol_tone_parquet(
    tmp_path: Path,
    slug: str,
    n_rows: int = 60,
    vol_values: list[float] | None = None,
    tone_values: list[float] | None = None,
    spike_last: float | None = None,
) -> Path:
    """Write a synthetic parquet to tmp_path/hk_gdelt/<slug>.parquet.
    By default generates uniform vol=0.01, tone=0.5.
    If spike_last is provided, the final vol row uses that value.
    """
    d = tmp_path / "hk_gdelt"
    d.mkdir(parents=True, exist_ok=True)

    base_date = pd.Timestamp("2026-04-01", tz="UTC")
    dates = [base_date + pd.Timedelta(days=i) for i in range(n_rows)]

    if vol_values is None:
        vol_values = [0.01] * n_rows
    if tone_values is None:
        tone_values = [0.5] * n_rows

    if spike_last is not None:
        vol_values = list(vol_values)
        vol_values[-1] = spike_last

    entity = next((e for e in ENTITIES if e.slug == slug), None)
    ticker = entity.ticker if entity else "TEST.HK"

    df = pd.DataFrame({
        "entity_query": [slug] * n_rows,
        "ticker":        [ticker] * n_rows,
        "vol_intensity": vol_values[:n_rows],
        "avg_tone":      tone_values[:n_rows],
    }, index=pd.DatetimeIndex(dates, name="date"))
    p = d / f"{slug}.parquet"
    df.to_parquet(p)
    return p


def _make_coverage(tmp_path: Path, entries: dict) -> None:
    """Write coverage.json to tmp_path/hk_gdelt/coverage.json."""
    p = tmp_path / "hk_gdelt" / "coverage.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries))


# ---------------------------------------------------------------------------
# 1. Parser on REAL GDELT fixture
# ---------------------------------------------------------------------------

class TestGdeltFixtureParser:
    """Parse the real saved GDELT timelinevol + timelinetone fixture.

    The fixture is the ACTUAL API response (verified 2026-07-08) for 'Alibaba'.
    Schema: {"query_details":..., "timeline": [{"series":..., "data":[{"date":..., "value":...},...]}]}
    """

    def test_vol_fixture_parses_correctly(self):
        """Real GDELT timelinevol fixture: series key is 'Volume Intensity', date format
        is 'YYYYMMDDTHHMMSSz', values are floats."""
        fixture = json.loads(
            (_FIXTURE_DIR / "gdelt_timelinevol_alibaba.json").read_text()
        )
        timeline = fixture["timeline"]
        assert len(timeline) == 1
        series = timeline[0]
        assert series["series"] == "Volume Intensity"
        data = series["data"]
        assert len(data) > 0

        first = data[0]
        assert "date" in first
        assert "value" in first
        assert first["date"] == "20260410T000000Z"
        assert isinstance(first["value"], float)

        # Last point (2026-07-08) should be the spike we saw (Ant/Alibaba narrative)
        last = data[-1]
        assert last["date"] == "20260708T000000Z"
        assert last["value"] > 0.2  # 0.2504 — significantly above baseline

    def test_tone_fixture_parses_correctly(self):
        """Real GDELT timelinetone fixture: series key is 'Average Tone'."""
        fixture = json.loads(
            (_FIXTURE_DIR / "gdelt_timelinetone_alibaba.json").read_text()
        )
        series = fixture["timeline"][0]
        assert series["series"] == "Average Tone"
        data = series["data"]
        assert len(data) > 0

        # Tone values are signed floats (negative = negative coverage)
        values = [pt["value"] for pt in data]
        assert any(v < 0 for v in values)  # some negative tone in 90d window
        assert any(v > 0 for v in values)  # some positive tone in 90d window

    def test_vol_fixture_into_engine_parquet(self, tmp_path):
        """Confirm that volume data from the real fixture can be written to parquet
        and loaded back via load_store() with the expected column shape."""
        from collectors.hk_gdelt import _parse_gdelt_date, load_store

        vol_fixture = json.loads(
            (_FIXTURE_DIR / "gdelt_timelinevol_alibaba.json").read_text()
        )
        tone_fixture = json.loads(
            (_FIXTURE_DIR / "gdelt_timelinetone_alibaba.json").read_text()
        )
        vol_data  = vol_fixture["timeline"][0]["data"]
        tone_data = tone_fixture["timeline"][0]["data"]

        # Build parquet directly from fixture data (same logic as collector)
        vol_rows: dict = {}
        tone_rows: dict = {}
        for pt in vol_data:
            ts = _parse_gdelt_date(pt["date"])
            if ts is not None:
                vol_rows[ts] = pt["value"]
        for pt in tone_data:
            ts = _parse_gdelt_date(pt["date"])
            if ts is not None:
                tone_rows[ts] = pt["value"]

        all_dates = sorted(set(vol_rows) | set(tone_rows))
        records = [
            {
                "date":          ts,
                "entity_query":  "Alibaba",
                "ticker":        "9988.HK",
                "vol_intensity": vol_rows.get(ts, float("nan")),
                "avg_tone":      tone_rows.get(ts, float("nan")),
            }
            for ts in all_dates
        ]
        df = pd.DataFrame(records).set_index("date").sort_index()

        pq_dir = tmp_path / "hk_gdelt"
        pq_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(pq_dir / "alibaba.parquet")

        # Load back via collector's load_store
        loaded = load_store("alibaba", data_root=tmp_path)
        assert loaded is not None
        assert "vol_intensity" in loaded.columns
        assert "avg_tone" in loaded.columns
        assert len(loaded) == len(all_dates)

        # The last bar should be 2026-07-08 with the spike value
        last_row = loaded.iloc[-1]
        assert abs(last_row["vol_intensity"] - 0.2504) < 0.001


# ---------------------------------------------------------------------------
# 2. attention_shock_z on synthetic data with known spike
# ---------------------------------------------------------------------------

class TestAttentionShockZ:
    """attention_shock_z should be high when last vol is far above baseline mean."""

    def test_known_spike_yields_high_z(self, tmp_path):
        """Baseline = 30 rows of vol=0.01; spike at row 31 = 0.20.
        Expected z ≈ (0.20 - 0.01) / std; std of uniform 0.01 is ~0, so std fallback
        applies but we can test with non-uniform baseline to get a finite z.
        """
        slug = "alibaba"
        n = 31
        # Vary baseline slightly so std is non-zero
        rng = np.random.default_rng(42)
        baseline = list(rng.uniform(0.008, 0.012, n - 1))
        spike = [0.20]   # clear spike at end
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=baseline + spike,
            tone_values=[0.5] * n,
        )
        _make_coverage(tmp_path, {slug: {"date": date.today().isoformat(), "status": "ok"}})

        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["young"] is False
        z = result["attention_shock_z"]
        assert z is not None
        assert z > 5.0, f"Expected high z for large spike, got {z}"

    def test_flat_series_yields_near_zero_z(self, tmp_path):
        """Uniform vol=0.01 throughout; last value matches baseline → z ≈ 0 (or None for zero std)."""
        slug = "alibaba"
        n = 40
        _make_vol_tone_parquet(tmp_path, slug, n_rows=n)  # uniform 0.01
        _make_coverage(tmp_path, {slug: {"date": date.today().isoformat(), "status": "ok"}})

        result = NARRATIVE._compute_entity(slug, tmp_path)
        # Uniform series → std is exactly 0 → z is None (honest, not a crash)
        # OR z should be ~0 if std>0 due to floating-point
        z = result["attention_shock_z"]
        if z is not None:
            assert abs(z) < 1.0, f"Expected near-zero z for flat series, got {z}"
        # Either way, no crash and entity dict has all keys
        assert "attention_shock_z" in result
        assert "narrative_state" in result

    def test_spike_produces_attention_spike_state(self, tmp_path):
        """A >2σ spike should yield narrative_state='attention_spike'."""
        slug = "tencent"
        n = 40
        rng = np.random.default_rng(7)
        baseline = list(rng.uniform(0.008, 0.012, n - 1))
        spike_val = float(np.mean(baseline) + 10 * np.std(baseline))  # 10σ spike
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=baseline + [spike_val],
            tone_values=[0.5] * n,
        )

        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["narrative_state"] == "attention_spike"


# ---------------------------------------------------------------------------
# 3. Young-series exclusion
# ---------------------------------------------------------------------------

class TestYoungSeriesExclusion:
    """Entities with < MIN_BASELINE_OBS obs must not get a narrative_state."""

    def test_too_few_obs_returns_young_true(self, tmp_path):
        """Only 5 rows (below MIN_BASELINE_OBS=20) → young=True, state=None."""
        slug = "alibaba"
        n = 5
        _make_vol_tone_parquet(tmp_path, slug, n_rows=n)

        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["young"] is True
        assert result["narrative_state"] is None
        assert result["attention_shock_z"] is None

    def test_exactly_at_threshold_allowed(self, tmp_path):
        """Exactly MIN_BASELINE_OBS rows → should not be excluded (>= not >)."""
        slug = "alibaba"
        n = NARRATIVE.MIN_BASELINE_OBS
        rng = np.random.default_rng(99)
        baseline = list(rng.uniform(0.005, 0.015, n - 1))
        spike = [0.15]
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=baseline + spike,
            tone_values=[0.5] * n,
        )
        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["young"] is False, "Exactly at MIN_BASELINE_OBS should not be excluded"

    def test_below_threshold_no_state(self, tmp_path):
        """MIN_BASELINE_OBS - 1 rows → young=True."""
        slug = "baidu"
        n = NARRATIVE.MIN_BASELINE_OBS - 1
        _make_vol_tone_parquet(tmp_path, slug, n_rows=n)
        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["young"] is True
        assert result["narrative_state"] is None


# ---------------------------------------------------------------------------
# 4. Fail-open: missing store / absent entity
# ---------------------------------------------------------------------------

class TestFailOpen:
    """Engine must not raise when store is missing, stale, or entity is absent."""

    def test_missing_store_returns_no_data(self, tmp_path):
        """No parquet file → young=True, no crash."""
        result = NARRATIVE._compute_entity("alibaba", tmp_path)
        assert result["young"] is True
        assert result["attention_shock_z"] is None
        assert result["narrative_state"] is None
        assert result["no_data_reason"] is not None

    def test_unknown_slug_returns_safe_dict(self, tmp_path):
        """An unknown slug never crashes; returns a safe no-data dict."""
        result = NARRATIVE._compute_entity("not_a_real_entity", tmp_path)
        assert result["young"] is True
        assert result["narrative_state"] is None

    def test_snapshot_with_empty_data_root_does_not_raise(self, tmp_path):
        """snapshot() on an empty data root → freshness=missing, entities list returned."""
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert "display_only" in snap
        assert snap["display_only"] is True
        # Should return entities list (all young/missing) without raising
        assert "entities" in snap
        assert isinstance(snap["entities"], list)

    def test_snapshot_entity_count_matches_entities(self, tmp_path):
        """snapshot() always returns one entry per ENTITY (even if all missing)."""
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert len(snap["entities"]) == len(ENTITIES)

    def test_snapshot_all_young_when_no_data(self, tmp_path):
        """When no parquets exist, every entity should be young=True."""
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        for ent in snap["entities"]:
            assert ent["young"] is True, f"Expected young=True for {ent['slug']} with no data"


# ---------------------------------------------------------------------------
# 5. Ledger idempotency + CN_LANE gate
# ---------------------------------------------------------------------------

class TestLedger:
    """Ledger stamp is idempotent on (ticker, date) and gated by CN_LANE=asia."""

    def _make_snap(self, tmp_path: Path) -> dict:
        """Create a minimal snapshot dict for stamping."""
        slug = "alibaba"
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=40,
            vol_values=list(np.random.default_rng(1).uniform(0.008, 0.012, 39)) + [0.20],
        )
        return NARRATIVE.snapshot(data_root=tmp_path)

    def test_stamp_no_op_without_cn_lane(self, tmp_path):
        """Without CN_LANE=asia, stamp() must not write anything."""
        snap = self._make_snap(tmp_path)

        env = os.environ.copy()
        env.pop("CN_LANE", None)
        with mock.patch.dict(os.environ, env, clear=True):
            n = NARRATIVE.stamp(snap, data_root=tmp_path)
        assert n == 0
        ledger_path = tmp_path / "hk_impulse" / "narrative_ledger.jsonl"
        assert not ledger_path.exists(), "Ledger should not be created without CN_LANE=asia"

    def test_stamp_writes_with_cn_lane_asia(self, tmp_path):
        """With CN_LANE=asia, stamp() writes rows for entities with data."""
        snap = self._make_snap(tmp_path)

        with mock.patch.dict(os.environ, {"CN_LANE": "asia"}):
            n = NARRATIVE.stamp(snap, data_root=tmp_path)

        ledger_path = tmp_path / "hk_impulse" / "narrative_ledger.jsonl"
        assert ledger_path.exists()
        rows = NARRATIVE.load_ledger(data_root=tmp_path)
        assert len(rows) > 0
        assert n == len(rows)  # stamp returned the count it wrote

    def test_stamp_idempotent_on_same_date_ticker(self, tmp_path):
        """Calling stamp() twice on the same snapshot → same rows; no duplicates."""
        snap = self._make_snap(tmp_path)

        with mock.patch.dict(os.environ, {"CN_LANE": "asia"}):
            n1 = NARRATIVE.stamp(snap, data_root=tmp_path)
            n2 = NARRATIVE.stamp(snap, data_root=tmp_path)

        assert n2 == 0, "Second stamp on same date+ticker should append 0 rows"
        rows = NARRATIVE.load_ledger(data_root=tmp_path)
        assert len(rows) == n1  # total count unchanged

    def test_ledger_row_schema(self, tmp_path):
        """Every ledger row must have the required keys."""
        snap = self._make_snap(tmp_path)
        with mock.patch.dict(os.environ, {"CN_LANE": "asia"}):
            NARRATIVE.stamp(snap, data_root=tmp_path)

        rows = NARRATIVE.load_ledger(data_root=tmp_path)
        required_keys = {"date", "ticker", "slug", "name_en",
                         "attention_shock_z", "tone_pctile",
                         "narrative_state", "asof_freshness", "organ"}
        for r in rows:
            missing = required_keys - r.keys()
            assert not missing, f"Ledger row missing keys: {missing}"
            assert r["organ"] == "hk_narrative"

    def test_cn_lane_non_asia_strings_do_not_advance(self, tmp_path):
        """CN_LANE=weekly or '' should not advance the ledger.
        The guard uses .lower() comparison, so 'ASIA' and 'Asia' both match 'asia'.
        Each value is tested against a fresh tmp_path to avoid idempotency interference.
        """
        import tempfile
        for val in ["weekly", ""]:
            with tempfile.TemporaryDirectory() as d:
                test_root = Path(d)
                snap = self._make_snap(test_root)
                with mock.patch.dict(os.environ, {"CN_LANE": val}):
                    n = NARRATIVE.stamp(snap, data_root=test_root)
                assert n == 0, f"CN_LANE={val!r} should not advance ledger"


# ---------------------------------------------------------------------------
# 6. snapshot() structure
# ---------------------------------------------------------------------------

class TestSnapshotStructure:
    """snapshot() must always return a dict with the required top-level keys."""

    def test_display_only_true(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert snap["display_only"] is True

    def test_note_key_present(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert "note" in snap
        assert "context" in snap["note"].lower() or "参考" in snap["note"]

    def test_caveat_keys_present(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert "caveat_en" in snap
        assert "caveat_zh" in snap
        # Must contain the "weakest evidence tier" framing
        assert "weakest" in snap["caveat_en"].lower()

    def test_freshness_key_present(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert "freshness" in snap
        assert snap["freshness"] in ("ok", "degraded", "stale", "missing")

    def test_as_of_key_present(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        assert "as_of" in snap

    def test_entities_list_complete(self, tmp_path):
        snap = NARRATIVE.snapshot(data_root=tmp_path)
        slugs = {e["slug"] for e in snap["entities"]}
        expected_slugs = {e.slug for e in ENTITIES}
        assert slugs == expected_slugs

    def test_run_returns_snapshot_shape(self, tmp_path):
        """run() should return the same shape as snapshot()."""
        with mock.patch.dict(os.environ, {}):
            snap = NARRATIVE.run(data_root=tmp_path)
        assert "display_only" in snap
        assert "entities" in snap


# ---------------------------------------------------------------------------
# 7. Tone percentile direction
# ---------------------------------------------------------------------------

class TestTonePercentile:
    """tone_pctile should be high when today's tone is above historical baseline."""

    def test_high_tone_yields_high_percentile(self, tmp_path):
        """Baseline tone = 0.0; last tone = 5.0 → percentile = 100."""
        slug = "meituan"
        n = 40
        tones = [0.0] * (n - 1) + [5.0]  # last is strongly positive
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=list(np.random.default_rng(3).uniform(0.008, 0.012, n - 1)) + [0.01],
            tone_values=tones,
        )
        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["tone_pctile"] is not None
        assert result["tone_pctile"] >= 99.0, f"Expected high pctile, got {result['tone_pctile']}"

    def test_low_tone_yields_low_percentile(self, tmp_path):
        """Baseline tone = 2.0; last tone = -5.0 → percentile = 0."""
        slug = "xiaomi"
        n = 40
        tones = [2.0] * (n - 1) + [-5.0]  # last is strongly negative
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=list(np.random.default_rng(5).uniform(0.008, 0.012, n - 1)) + [0.01],
            tone_values=tones,
        )
        result = NARRATIVE._compute_entity(slug, tmp_path)
        assert result["tone_pctile"] is not None
        assert result["tone_pctile"] <= 1.0, f"Expected low pctile, got {result['tone_pctile']}"

    def test_negative_tone_shift_state(self, tmp_path):
        """Low tone percentile (< 30) → narrative_state='tone_negative_shift'."""
        slug = "jdcom"
        n = 40
        baseline_vol = list(np.random.default_rng(11).uniform(0.008, 0.012, n - 1))
        tones = [2.0] * (n - 1) + [-5.0]
        _make_vol_tone_parquet(
            tmp_path, slug, n_rows=n,
            vol_values=baseline_vol + [0.010],   # vol is flat → no spike
            tone_values=tones,
        )
        result = NARRATIVE._compute_entity(slug, tmp_path)
        # State should be tone_negative_shift (not attention_spike, since vol is baseline-level)
        assert result["narrative_state"] == "tone_negative_shift"


# ---------------------------------------------------------------------------
# 8. Adapter registration (FIX 1)
# ---------------------------------------------------------------------------

class TestAdapterRegistration:
    """HkGdeltAdapter must exist with the right attributes and be in all_adapters()."""

    def test_adapter_class_exists_with_correct_group(self):
        """HkGdeltAdapter must subclass Adapter and have group='hk_gdelt'."""
        from collectors.base import Adapter
        from collectors.hk_gdelt import HkGdeltAdapter
        assert issubclass(HkGdeltAdapter, Adapter)
        assert HkGdeltAdapter.group == "hk_gdelt"
        assert HkGdeltAdapter.name == "hk_gdelt"

    def test_adapter_is_in_registry(self):
        """all_adapters() must include hk_gdelt mapped to HkGdeltAdapter."""
        from scripts.collect import all_adapters
        reg = all_adapters()
        assert "hk_gdelt" in reg, "hk_gdelt missing from scripts/collect.py all_adapters()"
        assert reg["hk_gdelt"].__name__ == "HkGdeltAdapter"


# ---------------------------------------------------------------------------
# 9. BASELINE_WINDOW bounding (FIX 3)
# ---------------------------------------------------------------------------

class TestBaselineWindow:
    """When a parquet has more rows than BASELINE_WINDOW, only the tail is used
    for z-score and percentile — the result must match a bounded computation."""

    def test_extra_rows_do_not_shift_baseline(self, tmp_path):
        """A parquet with 2×BASELINE_WINDOW rows must produce the same z-score
        as one with exactly BASELINE_WINDOW rows when the tails are identical.

        We build two parquets for the same entity:
          - 'short': exactly BASELINE_WINDOW rows, last row is a spike.
          - 'long': 2×BASELINE_WINDOW rows, same trailing BASELINE_WINDOW tail.
        The z-scores from both must agree to 3 decimal places.
        """
        BW = NARRATIVE.BASELINE_WINDOW  # 90

        rng = np.random.default_rng(42)
        tail_baseline = list(rng.uniform(0.008, 0.012, BW - 1))
        spike = [0.20]
        tail_vol = tail_baseline + spike
        tail_tone = [0.5] * BW

        # Short parquet: exactly BW rows
        _make_vol_tone_parquet(
            tmp_path, "alibaba", n_rows=BW,
            vol_values=tail_vol,
            tone_values=tail_tone,
        )
        result_short = NARRATIVE._compute_entity("alibaba", tmp_path)
        z_short = result_short["attention_shock_z"]
        assert z_short is not None

        # Long parquet: 2×BW rows — the extra rows have a very different vol level
        # (0.5) but should NOT pollute the z-score because BASELINE_WINDOW is applied.
        prefix_vol  = [0.5] * BW  # deliberately different from tail
        prefix_tone = [10.0] * BW  # deliberately different from tail
        long_vol  = prefix_vol  + tail_vol
        long_tone = prefix_tone + tail_tone

        _make_vol_tone_parquet(
            tmp_path, "alibaba", n_rows=2 * BW,
            vol_values=long_vol,
            tone_values=long_tone,
        )
        result_long = NARRATIVE._compute_entity("alibaba", tmp_path)
        z_long = result_long["attention_shock_z"]
        assert z_long is not None

        assert abs(z_short - z_long) < 0.001, (
            f"BASELINE_WINDOW not applied: z_short={z_short}, z_long={z_long}; "
            f"old rows are polluting the baseline."
        )

    def test_tone_pctile_bounded_by_window(self, tmp_path):
        """Long parquet: tone pctile must reflect only the trailing BASELINE_WINDOW rows."""
        BW = NARRATIVE.BASELINE_WINDOW

        # Tail: BW-1 rows of tone=2.0, last row tone=-5.0 → pctile = 0 in tail
        tail_tone = [2.0] * (BW - 1) + [-5.0]
        tail_vol  = list(np.random.default_rng(77).uniform(0.008, 0.012, BW - 1)) + [0.01]

        # Prefix: BW rows of very negative tone — if prefix is included,
        # pctile would be non-zero (many rows below -5.0)
        prefix_tone = [-50.0] * BW
        prefix_vol  = [0.01] * BW

        _make_vol_tone_parquet(
            tmp_path, "tencent", n_rows=2 * BW,
            vol_values=prefix_vol  + tail_vol,
            tone_values=prefix_tone + tail_tone,
        )
        result = NARRATIVE._compute_entity("tencent", tmp_path)
        pctile = result["tone_pctile"]
        assert pctile is not None
        # Within the tail window, -5.0 is below all 2.0 baseline rows → pctile = 0
        assert pctile == 0.0, (
            f"Expected tone_pctile=0.0 (tail-only window), got {pctile}; "
            f"prefix rows may be polluting the baseline."
        )
