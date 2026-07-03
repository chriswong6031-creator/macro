"""tests/test_missing_tape.py — Missing-Tape v0 unit tests.

Spec: research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md D8.

Tests cover all four spec requirements:
  1. Hash-diff detection (recrawl_official_tape — body_sha256 changed → "edited",
     404 → "gone", same hash → "unchanged").
  2. Divergence-z math (missing_tape_gdelt.compute_divergence_z — correct
     expanding-window z; NaN for too-short windows).
  3. Flag confidence tiers (missing_tape_attention.detect_flags — HIGH/MED/LOW
     with injected qbus volumes).
  4. Pacing/caching (recrawl: already-logged rows are NOT re-fetched; max_rows cap).

All tests are pure / network-free.  They write only to tmp_path.

Run: python tests/test_missing_tape.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --------------------------------------------------------------------------- #
# 1. Hash-diff detection
# --------------------------------------------------------------------------- #
from scripts.recrawl_official_tape import (
    body_sha256,
    _determine_status,
    _already_logged,
    _load_log,
    _save_log,
    run as recrawl_run,
    deletion_rate,
    _log_path,
    _LOG_COLS,
)


def test_body_sha256_empty():
    assert body_sha256(None) == ""
    assert body_sha256("") == ""
    assert body_sha256(b"") == ""


def test_body_sha256_consistent():
    s = "人民日报 test content 2026"
    assert body_sha256(s) == body_sha256(s.encode("utf-8"))
    assert len(body_sha256(s)) == 64


def test_body_sha256_diff():
    h1 = body_sha256("original content")
    h2 = body_sha256("edited content")
    assert h1 != h2


def test_determine_status_unchanged():
    h = body_sha256("same body")
    assert _determine_status(h, h, 200) == "unchanged"


def test_determine_status_edited():
    h1 = body_sha256("original")
    h2 = body_sha256("edited — policy text removed")
    assert _determine_status(h1, h2, 200) == "edited"


def test_determine_status_gone_404():
    assert _determine_status("abcdef", "", 404) == "gone"


def test_determine_status_gone_403():
    assert _determine_status("abcdef", "", 403) == "gone"


def test_determine_status_error_connection():
    # status_code == 0 means connection error
    assert _determine_status("abcdef", "", 0) == "error"


def test_determine_status_gone_other_4xx():
    # 410 Gone
    assert _determine_status("abcdef", "", 410) == "gone"


# --------------------------------------------------------------------------- #
# 2. Recrawl caching — already-logged rows are not re-fetched
# --------------------------------------------------------------------------- #
def test_already_logged_hit(tmp_path):
    row = {
        "item_id": "abc123",
        "url": "https://gov.cn/test",
        "recrawl_at": "2026-07-01",
        "lag_days": 3,
        "original_sha256": "sha256abc",
        "fetched_sha256": "sha256abc",
        "status": "unchanged",
        "status_code": 200,
    }
    df = pd.DataFrame([row], columns=list(_LOG_COLS))
    assert _already_logged(df, "abc123", 3) is True
    assert _already_logged(df, "abc123", 7) is False  # different lag
    assert _already_logged(df, "xyz999", 3) is False  # different id


def test_already_logged_empty():
    df = pd.DataFrame(columns=list(_LOG_COLS))
    assert _already_logged(df, "any_id", 3) is False


def test_deletion_rate_empty():
    df = pd.DataFrame(columns=list(_LOG_COLS))
    assert deletion_rate(log_df=df) == 0.0


def test_deletion_rate_calculation():
    rows = [
        {"item_id": "a", "lag_days": 3, "status": "gone"},
        {"item_id": "b", "lag_days": 3, "status": "unchanged"},
        {"item_id": "c", "lag_days": 3, "status": "gone"},
        {"item_id": "d", "lag_days": 3, "status": "edited"},
    ]
    df = pd.DataFrame(rows)
    # 2 "gone" out of 4 = 0.5
    assert deletion_rate(log_df=df) == pytest.approx(0.5)


def test_recrawl_run_no_qbus(tmp_path, monkeypatch):
    """run() completes gracefully when qbus returns no eligible rows."""
    monkeypatch.setattr(
        "scripts.recrawl_official_tape._eligible_qbus_rows",
        lambda data_root, today: [],
    )
    df = recrawl_run(dry_run=True, data_root=tmp_path, today=date(2026, 7, 2))
    assert isinstance(df, pd.DataFrame)


def test_recrawl_run_max_rows_cap(tmp_path, monkeypatch):
    """max_rows cap prevents over-fetching."""
    fetch_calls = []

    def _fake_fetch(url, timeout=20):
        fetch_calls.append(url)
        return 200, b"body content here"

    original_sha = body_sha256(b"body content here")
    eligible = [
        {
            "item_id": f"item_{i}",
            "url": f"https://gov.cn/doc/{i}",
            "body_sha256": "deadbeef000000000000000000000000"
                           "deadbeef000000000000000000000000",
            "_crawled_at": "2026-06-20T00:00:00+00:00",
        }
        for i in range(10)
    ]

    monkeypatch.setattr(
        "scripts.recrawl_official_tape._eligible_qbus_rows",
        lambda data_root, today: eligible,
    )
    monkeypatch.setattr("scripts.recrawl_official_tape._fetch_body", _fake_fetch)
    monkeypatch.setattr("scripts.recrawl_official_tape.PACE_SECONDS", 0.0)
    monkeypatch.setattr("scripts.recrawl_official_tape._emit_censorship_event",
                        lambda *a, **kw: None)

    recrawl_run(
        dry_run=True,
        max_rows=3,
        data_root=tmp_path,
        today=date(2026, 7, 2),
    )
    assert len(fetch_calls) <= 3


def test_recrawl_run_caching(tmp_path, monkeypatch):
    """Already-logged (item_id, lag) combos are skipped — no fetch call made."""
    fetch_calls = []

    def _fake_fetch(url, timeout=20):
        fetch_calls.append(url)
        return 200, b"same body"

    eligible = [
        {
            "item_id": "item_cached",
            "url": "https://gov.cn/cached",
            "body_sha256": body_sha256(b"same body"),
            "_crawled_at": "2026-06-20T00:00:00+00:00",
        }
    ]

    # Pre-populate log with both lags already done
    log_rows = [
        {"item_id": "item_cached", "url": "https://gov.cn/cached",
         "recrawl_at": "2026-06-23", "lag_days": 3, "original_sha256": "x",
         "fetched_sha256": "x", "status": "unchanged", "status_code": 200},
        {"item_id": "item_cached", "url": "https://gov.cn/cached",
         "recrawl_at": "2026-06-27", "lag_days": 7, "original_sha256": "x",
         "fetched_sha256": "x", "status": "unchanged", "status_code": 200},
    ]
    log_df = pd.DataFrame(log_rows, columns=list(_LOG_COLS))
    (tmp_path / "missing_tape").mkdir(parents=True, exist_ok=True)
    log_df.to_parquet(tmp_path / "missing_tape" / "recrawl_log.parquet", index=False)

    monkeypatch.setattr(
        "scripts.recrawl_official_tape._eligible_qbus_rows",
        lambda data_root, today: eligible,
    )
    monkeypatch.setattr("scripts.recrawl_official_tape._fetch_body", _fake_fetch)
    monkeypatch.setattr("scripts.recrawl_official_tape.PACE_SECONDS", 0.0)

    recrawl_run(dry_run=True, data_root=tmp_path, today=date(2026, 7, 2))
    assert len(fetch_calls) == 0, "Cached rows should not trigger fetches"


# --------------------------------------------------------------------------- #
# 3. Divergence-z math (GDELT leg)
# --------------------------------------------------------------------------- #
from engine.missing_tape_gdelt import compute_divergence_z


def test_divergence_z_too_short():
    """Fewer than min_window values → NaN."""
    zs = compute_divergence_z([1.0, 2.0, 3.0, 4.0], min_window=5)
    assert all(math.isnan(z) for z in zs)


def test_divergence_z_first_valid_at_min_window():
    """First non-NaN z appears at index min_window (window = all prior points)."""
    spreads = [1.0, 1.0, 1.0, 1.0, 1.0, 5.0]  # min_window=5
    zs = compute_divergence_z(spreads, min_window=5)
    # Positions 0–4 have window < 5 → NaN
    for i in range(5):
        assert math.isnan(zs[i]), f"Expected NaN at index {i}"
    # Position 5: window=[1,1,1,1,1], mean=1, std=0 → z=0 (constant window)
    assert not math.isnan(zs[5])


def test_divergence_z_high_value():
    """A spike in spread should produce a positive high z."""
    # Varied baseline (mean≈0, std>0) then a large spike
    spreads = [-1.0, 1.0, -0.5, 0.5, 0.0, -0.3, 0.3, 0.2, -0.2, 0.1, 20.0]
    zs = compute_divergence_z(spreads, min_window=5)
    assert zs[-1] > 2.0, f"Spike should produce z > 2 but got {zs[-1]}"


def test_divergence_z_negative_spike():
    """A drop in spread should produce a large negative z."""
    spreads = [-1.0, 1.0, -0.5, 0.5, 0.0, -0.3, 0.3, 0.2, -0.2, 0.1, -20.0]
    zs = compute_divergence_z(spreads, min_window=5)
    assert zs[-1] < -2.0, f"Drop should produce z < -2 but got {zs[-1]}"


def test_divergence_z_stable_series():
    """Stable series with small noise → z near 0."""
    import random
    random.seed(42)
    spreads = [random.gauss(0.5, 0.1) for _ in range(20)]
    zs = compute_divergence_z(spreads, min_window=5)
    non_nan = [z for z in zs if not math.isnan(z)]
    assert all(abs(z) < 5.0 for z in non_nan), "Stable series z should be small"


def test_divergence_z_length_matches_input():
    """Output length always equals input length."""
    spreads = [float(i) for i in range(15)]
    zs = compute_divergence_z(spreads, min_window=5)
    assert len(zs) == len(spreads)


def test_gdelt_parse_date():
    from engine.missing_tape_gdelt import _parse_gdelt_date
    assert _parse_gdelt_date("20261201120000") == "2026-12-01"
    assert _parse_gdelt_date("2026-07-02") == "2026-07-02"
    assert _parse_gdelt_date("2026") is None    # too short → None
    assert _parse_gdelt_date("bad") is None


def test_gdelt_series_to_dict():
    from engine.missing_tape_gdelt import _series_to_dict
    records = [
        {"date": "20260701000000", "value": 1.5},
        {"date": "20260702000000", "value": -0.5},
        {"date": "bad-date", "value": 99},
    ]
    d = _series_to_dict(records)
    assert d.get("2026-07-01") == pytest.approx(1.5)
    assert d.get("2026-07-02") == pytest.approx(-0.5)


def test_gdelt_update_no_network(tmp_path, monkeypatch):
    """update() returns existing df gracefully when GDELT returns no records."""
    # since W5 (#972) _fetch_gdelt returns (records, fetch_status)
    monkeypatch.setattr(
        "engine.missing_tape_gdelt._fetch_gdelt",
        lambda url, timeout=30: ([], "empty"),
    )
    from engine.missing_tape_gdelt import update
    df = update(
        today=date(2026, 7, 2),
        data_root=tmp_path,
        dry_run=True,
    )
    assert isinstance(df, pd.DataFrame)


# --------------------------------------------------------------------------- #
# 4. Flag confidence tiers (attention-collapse)
# --------------------------------------------------------------------------- #
from engine.missing_tape_attention import (
    _mean_std,
    _safe_z,
    detect_flags,
    _CN_COLLAPSE_Z_HIGH,
    _CN_COLLAPSE_Z_MED,
    _CN_COLLAPSE_Z_LOW,
    _EN_STABLE_Z_HIGH,
    _EN_STABLE_Z_MED,
    _MIN_OBS,
)


def test_mean_std_empty():
    mu, sigma = _mean_std([])
    assert mu == 0.0
    assert sigma == 1.0


def test_mean_std_unit():
    mu, sigma = _mean_std([5.0])
    assert mu == pytest.approx(5.0)
    assert sigma == 1.0  # fallback for n=1


def test_mean_std_basic():
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    mu, sigma = _mean_std(vals)
    assert mu == pytest.approx(5.0)
    # sample std (ddof=1): stdev([2,4,4,4,5,5,7,9]) ≈ 2.138
    assert sigma > 0.0
    assert abs(mu - 5.0) < 1e-9


def test_safe_z_nan_short():
    z = _safe_z(5.0, [1.0, 2.0])   # only 2 points < _MIN_OBS
    assert math.isnan(z)


def test_safe_z_numeric():
    history = [0.0] * 10  # mean=0, std=1 (fallback since var=0 -> sigma=1)
    z = _safe_z(3.0, history)
    assert z == pytest.approx(3.0)  # (3 - 0) / 1.0


def _fake_qbus_items(asof: date, cn_counts_by_subject, en_counts_by_subject):
    """Build a synthetic qbus DataFrame for detect_flags injection."""
    rows = []
    for subject, by_day in cn_counts_by_subject.items():
        for day_str, count in by_day.items():
            for _ in range(count):
                rows.append({
                    "item_id": f"cn_{subject}_{day_str}_{_}",
                    "event_key": "",
                    "desk": "china_news_intel",
                    "source": "xinhua",
                    "source_tier": 1,
                    "lang": "zh",
                    "url": f"https://xinhua.com/{subject}/{day_str}",
                    "title": f"CN news about {subject} on {day_str}",
                    "body_sha256": "",
                    "seendate": f"{day_str}T00:00:00+00:00",
                    "_crawled_at": f"{day_str}T00:00:00+00:00",
                    "timestamp_quality": "CRAWL_BOUNDED",
                    "entities": "",
                    "themes": subject,
                    "importance_raw": 1.0,
                })
    for subject, by_day in en_counts_by_subject.items():
        for day_str, count in by_day.items():
            for _ in range(count):
                rows.append({
                    "item_id": f"en_{subject}_{day_str}_{_}",
                    "event_key": "",
                    "desk": "financial_news",
                    "source": "reuters",
                    "source_tier": 1,
                    "lang": "en",
                    "url": f"https://reuters.com/{subject}/{day_str}",
                    "title": f"EN news about {subject} on {day_str}",
                    "body_sha256": "",
                    "seendate": f"{day_str}T00:00:00+00:00",
                    "_crawled_at": f"{day_str}T00:00:00+00:00",
                    "timestamp_quality": "CRAWL_BOUNDED",
                    "entities": "",
                    "themes": subject,
                    "importance_raw": 1.0,
                })
    from engine.qbus import COLUMNS
    if not rows:
        return pd.DataFrame(columns=list(COLUMNS))
    df = pd.DataFrame(rows)
    return df.reindex(columns=list(COLUMNS))


def _build_history(base_count: int, n_days: int, asof: date) -> dict[str, int]:
    """Build trailing daily counts for a subject."""
    out = {}
    for i in range(n_days, 0, -1):
        d = (asof - timedelta(days=i)).isoformat()
        out[d] = base_count
    return out


def test_detect_flags_no_collapse(tmp_path, monkeypatch):
    """No flag when CN count is stable."""
    asof = date(2026, 7, 2)
    subject = "trade_policy"
    today_str = asof.isoformat()
    cn_by_day = _build_history(10, 20, asof)
    cn_by_day[today_str] = 10   # same as history → no collapse
    en_by_day = _build_history(8, 20, asof)
    en_by_day[today_str] = 8

    df = _fake_qbus_items(asof, {subject: cn_by_day}, {subject: en_by_day})
    monkeypatch.setattr("engine.missing_tape_attention.read_items", lambda: df)
    monkeypatch.setattr("engine.missing_tape_attention._recrawl_hit_subjects",
                        lambda data_root, asof: set())

    flags = detect_flags(asof=asof, data_root=tmp_path)
    flag_subjects = {f["subject"] for f in flags}
    assert subject not in flag_subjects


def test_detect_flags_med_confidence(tmp_path, monkeypatch):
    """MED flag when CN collapses but EN stable, no recrawl corroboration."""
    asof = date(2026, 7, 2)
    subject = "property_sector"
    today_str = asof.isoformat()

    # CN: stable history of 10/day, today = 0 → large negative z
    cn_by_day = _build_history(10, 20, asof)
    cn_by_day[today_str] = 0

    # EN: stable history of 8/day, today = 8 → z ≈ 0
    en_by_day = _build_history(8, 20, asof)
    en_by_day[today_str] = 8

    df = _fake_qbus_items(asof, {subject: cn_by_day}, {subject: en_by_day})
    monkeypatch.setattr("engine.missing_tape_attention.read_items", lambda: df)
    monkeypatch.setattr("engine.missing_tape_attention._recrawl_hit_subjects",
                        lambda data_root, asof: set())

    flags = detect_flags(asof=asof, data_root=tmp_path)
    flag_subjects = {f["subject"]: f for f in flags}
    assert subject in flag_subjects, "Expected MED flag for property_sector"
    assert flag_subjects[subject]["confidence"] in ("MED", "HIGH")
    assert flag_subjects[subject]["cn_z"] < _CN_COLLAPSE_Z_LOW


def test_detect_flags_high_confidence(tmp_path, monkeypatch):
    """HIGH flag when CN collapses sharply, EN is rising, AND recrawl corroborates."""
    asof = date(2026, 7, 2)
    subject = "corruption_crackdown"
    today_str = asof.isoformat()

    # CN: stable 10/day, today = 0 → large negative z
    cn_by_day = _build_history(10, 25, asof)
    cn_by_day[today_str] = 0

    # EN: stable 5/day, today = 15 → large positive z
    en_by_day = _build_history(5, 25, asof)
    en_by_day[today_str] = 15

    df = _fake_qbus_items(asof, {subject: cn_by_day}, {subject: en_by_day})
    monkeypatch.setattr("engine.missing_tape_attention.read_items", lambda: df)
    # Inject recrawl corroboration for this subject
    monkeypatch.setattr(
        "engine.missing_tape_attention._recrawl_hit_subjects",
        lambda data_root, asof: {subject},
    )

    flags = detect_flags(asof=asof, data_root=tmp_path)
    flag_subjects = {f["subject"]: f for f in flags}
    assert subject in flag_subjects, "Expected HIGH flag for corruption_crackdown"
    assert flag_subjects[subject]["confidence"] == "HIGH"


def test_detect_flags_en_also_collapsed(tmp_path, monkeypatch):
    """No flag when BOTH CN and EN collapse — consistent global drop, not suppression."""
    asof = date(2026, 7, 2)
    subject = "global_macro"
    today_str = asof.isoformat()

    # Both lanes collapse equally
    cn_by_day = _build_history(10, 20, asof)
    cn_by_day[today_str] = 0
    en_by_day = _build_history(10, 20, asof)
    en_by_day[today_str] = 0

    df = _fake_qbus_items(asof, {subject: cn_by_day}, {subject: en_by_day})
    monkeypatch.setattr("engine.missing_tape_attention.read_items", lambda: df)
    monkeypatch.setattr("engine.missing_tape_attention._recrawl_hit_subjects",
                        lambda data_root, asof: set())

    flags = detect_flags(asof=asof, data_root=tmp_path)
    flag_subjects = {f["subject"] for f in flags}
    # Both collapsed → en_z also strongly negative → should NOT flag
    assert subject not in flag_subjects


def test_detect_flags_empty_qbus(tmp_path, monkeypatch):
    """No flags when qbus is empty."""
    monkeypatch.setattr("engine.missing_tape_attention.read_items", lambda: None)
    flags = detect_flags(asof=date(2026, 7, 2), data_root=tmp_path)
    assert flags == []


# --------------------------------------------------------------------------- #
# 5. Artifact emitter
# --------------------------------------------------------------------------- #
from engine.missing_tape import emit, _risk_level, _nan_to_none


def test_nan_to_none():
    assert _nan_to_none(float("nan")) is None
    assert _nan_to_none(None) is None
    assert _nan_to_none(1.5) == pytest.approx(1.5)


def test_risk_level_none():
    assert _risk_level(0.5, []) == "NONE"
    assert _risk_level(None, []) == "NONE"


def test_risk_level_elevated_by_z():
    assert _risk_level(2.0, []) == "ELEVATED"


def test_risk_level_high_by_z():
    assert _risk_level(3.0, []) == "HIGH"


def test_risk_level_elevated_by_med_flag():
    flags = [{"confidence": "MED", "subject": "x", "cn_z": -2.0, "en_z": 0.5,
              "today_cn": 0, "today_en": 8}]
    assert _risk_level(0.0, flags) == "ELEVATED"


def test_risk_level_high_by_flag():
    flags = [{"confidence": "HIGH", "subject": "x", "cn_z": -3.0, "en_z": 1.0,
              "today_cn": 0, "today_en": 12}]
    assert _risk_level(0.0, flags) == "HIGH"


def test_emit_dry_run(tmp_path, monkeypatch):
    """emit(dry_run=True) returns valid dict and does not write files."""
    monkeypatch.setattr(
        "engine.missing_tape.deletion_rate",
        lambda data_root: 0.0,
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.latest_divergence_z",
        lambda data_root: 1.0,
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.detect_flags",
        lambda asof, data_root: [],
        raising=False,
    )

    result = emit(
        asof=date(2026, 7, 2),
        data_root=tmp_path,
        site_root=tmp_path,
        dry_run=True,
        register_claim=False,
    )

    assert result["schema"] == "missing_tape.v0"
    assert result["as_of"] == "2026-07-02"
    assert result["is_context_only"] is True
    assert "deletion_rate" in result
    assert "divergence_z" in result
    assert "flags" in result
    assert "risk_level" in result

    # dry_run → artifact NOT written
    assert not (tmp_path / "site" / "chinadata" / "missing_tape.json").exists()


def test_emit_writes_artifact(tmp_path, monkeypatch):
    """emit() without dry_run writes valid JSON artifact."""
    monkeypatch.setattr(
        "engine.missing_tape.deletion_rate",
        lambda data_root: 0.1,
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.latest_divergence_z",
        lambda data_root: float("nan"),
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.detect_flags",
        lambda asof, data_root: [],
        raising=False,
    )

    result = emit(
        asof=date(2026, 7, 2),
        data_root=tmp_path,
        site_root=tmp_path,
        dry_run=False,
        register_claim=False,
    )

    # NaN divergence_z → None in artifact
    assert result["divergence_z"] is None

    artifact_path = tmp_path / "site" / "chinadata" / "missing_tape.json"
    assert artifact_path.exists(), "Artifact file should be written"

    with artifact_path.open() as f:
        on_disk = json.load(f)

    assert on_disk["schema"] == "missing_tape.v0"
    assert on_disk["is_context_only"] is True
    assert on_disk["divergence_z"] is None


def test_emit_json_serializable(tmp_path, monkeypatch):
    """The artifact must be fully JSON-serializable (no NaN floats)."""
    monkeypatch.setattr(
        "engine.missing_tape.deletion_rate",
        lambda data_root: 0.0,
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.latest_divergence_z",
        lambda data_root: float("nan"),
        raising=False,
    )
    monkeypatch.setattr(
        "engine.missing_tape.detect_flags",
        lambda asof, data_root: [],
        raising=False,
    )

    result = emit(
        asof=date(2026, 7, 2),
        data_root=tmp_path,
        site_root=tmp_path,
        dry_run=True,
        register_claim=False,
    )
    # Must not raise
    serialized = json.dumps(result)
    assert "NaN" not in serialized


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
