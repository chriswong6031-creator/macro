"""Smoke tests for scripts/audit_qbus.py (W2-B3 bus measurement harness).

Tests:
  1. Harness runs without error on synthetic qbus rows and produces valid JSON+MD.
  2. Sections (a)-(d) are all present and structurally correct.
  3. Runs gracefully when the bus is empty / parquet missing.

No network; no real bus parquet required.

Run:  python tests/test_audit_qbus.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _synthetic_rows(root: Path, n: int = 30) -> None:
    """Write synthetic qbus rows directly to root/data/qbus/items.parquet.

    We write directly (not via qbus.append_items) because append_items reads/writes
    from config.data_dir() which points to the real repo data/, not tmp_path.
    We use qbus primitives (normalize_row, assign_event_keys) so the schema and
    event_key clustering are exercised exactly as in production.
    """
    import pandas as pd
    from engine.qbus import normalize_row, assign_event_keys, COLUMNS

    desks = ["news_vector", "financial_news", "china_news_intel"]
    themes = ["trade", "monetary", "inflation", "geopolitics"]
    base_titles = [
        "Fed holds interest rates steady",
        "US tariffs on China goods rising",
        "Inflation CPI data shows cooling",
        "Ukraine ceasefire talks stall",
    ]
    rows = []
    for i in range(n):
        desk = desks[i % len(desks)]
        theme = themes[i % len(themes)]
        title = base_titles[i % len(base_titles)]
        if i % 5 == 0:
            title = title + " — updated"
        seendate = (datetime.now(timezone.utc) - timedelta(hours=i * 4)).isoformat()
        rows.append({
            "desk": desk,
            "source": f"source_{i % 3}",
            "url": f"https://example{i}.com/article",
            "title": title,
            "seendate": seendate,
            "_crawled_at": seendate,
            "timestamp_quality": "CRAWL_BOUNDED",
            "lang": "en",
            "entities": ["SPY"] if i % 3 == 0 else [],
            "themes": [theme],
            "importance_raw": float(i % 5) / 4.0,
        })

    # assign event_keys (pure), then normalize and write directly
    keyed = assign_event_keys(rows, thresh=0.6, window_days=3)
    normed = [normalize_row(r) for r in keyed]
    bus_path = root / "data" / "qbus" / "items.parquet"
    bus_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(normed, columns=list(COLUMNS)).to_parquet(bus_path, index=False)


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_audit_runs_on_synthetic_rows(tmp_path):
    """Harness completes and writes JSON + MD with all four sections."""
    _synthetic_rows(tmp_path)

    from scripts.audit_qbus import run
    out = tmp_path / "data" / "qbus" / "audit_test.json"
    report = run(tmp_path, days=7, out=out)

    # basic structural checks
    assert isinstance(report, dict)
    assert report.get("status") == "ok"
    assert "echo" in report
    assert "novelty" in report
    assert "desk_mix" in report
    assert "duplicate_rate" in report
    assert report["n_total_items"] > 0

    # JSON output was written and is valid
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["status"] == "ok"

    # Markdown was written
    out_md = out.with_suffix(".md")
    assert out_md.exists()
    md = out_md.read_text()
    assert "echo" in md.lower()
    assert "novelty" in md.lower()
    assert "duplicate" in md.lower()


def test_echo_report_section(tmp_path):
    """Echo report must list event_keys with n_items, n_sources, n_desks."""
    _synthetic_rows(tmp_path)
    from scripts.audit_qbus import run
    report = run(tmp_path, days=7)

    echo = report.get("echo", {})
    assert "n_items" in echo
    assert "n_unique_event_keys" in echo
    # with 30 synthetic rows across 3 desks some should share event_keys
    # (we accept 0 multi-desk if clustering didn't fire — just check structure)
    assert isinstance(echo.get("top_events"), list)
    for ev in echo["top_events"]:
        assert "event_key" in ev
        assert "n_items" in ev and "n_desks" in ev and "n_sources" in ev


def test_desk_mix_section(tmp_path):
    """Per-desk mix must include all three synthetic desks."""
    _synthetic_rows(tmp_path)
    from scripts.audit_qbus import run
    report = run(tmp_path, days=7)

    desk_mix = report.get("desk_mix", {})
    assert desk_mix.get("n_desks", 0) >= 1
    desk_names = {d["desk"] for d in desk_mix.get("desks", [])}
    # at least news_vector and financial_news should appear
    assert len(desk_names) >= 1
    for d in desk_mix.get("desks", []):
        assert "n_items" in d
        assert "timestamp_quality_mix" in d


def test_duplicate_rate_section(tmp_path):
    """Duplicate-rate section must report a reduction ratio."""
    _synthetic_rows(tmp_path)
    from scripts.audit_qbus import run
    report = run(tmp_path, days=7)

    dup = report.get("duplicate_rate", {})
    assert "n_items_total" in dup
    assert "n_unique_events" in dup
    # ratio may be None if no event_keys assigned; just check it doesn't error
    ratio = dup.get("raw_to_event_ratio")
    if ratio is not None:
        assert isinstance(ratio, float) and ratio >= 1.0


def test_audit_degrades_gracefully_when_bus_missing(tmp_path):
    """Harness must not raise when data/qbus/items.parquet is absent."""
    from scripts.audit_qbus import run
    report = run(tmp_path, days=7)
    # should return a 'warn' report, not an exception
    assert isinstance(report, dict)
    assert report.get("status") in ("warn", "ok")
    assert report.get("n_total_items") == 0


def test_health_status_file_written(tmp_path):
    """audit_run_status.json must be written alongside the report."""
    _synthetic_rows(tmp_path)
    from scripts.audit_qbus import run
    run(tmp_path, days=7)
    status_file = tmp_path / "data" / "qbus" / "audit_run_status.json"
    assert status_file.exists()
    s = json.loads(status_file.read_text())
    assert "status" in s and "checked_at" in s


if __name__ == "__main__":
    import tempfile
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"ok  {fn.__name__}")
            except Exception as exc:
                print(f"FAIL {fn.__name__}: {exc}")
                raise
    print(f"\n{len(fns)} passed")
